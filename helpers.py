from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, current_app
import requests
import mariadb
import os
from collections import Counter
from dotenv import load_dotenv
from datetime import datetime
import json

STATUS_OPTIONS = ["TBR", "Reading", "Read", "DNF"]
CACHE_DIR = 'cover_cache'

DB_CONFIG = {
    'user': os.getenv('BOOKVAULT_DBUSER'),
    'password': os.getenv('BOOKVAULT_DBPASS'),
    'host': os.getenv('BOOKVAULT_DBHOST'),
    'port': int(os.getenv('BOOKVAULT_DBPORT')),
    'database': os.getenv('BOOKVAULT_DBNAME')
}

def create_upload_folder():
    upload_folder = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

def get_db_connection():
    conn = mariadb.connect(**DB_CONFIG)
    return conn

def create_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255),
            author VARCHAR(255),
            cover VARCHAR(512),
            status ENUM('TBR', 'Reading', 'Read', 'DNF') DEFAULT 'TBR',
            last_status_change DATETIME DEFAULT NULL,
            ebookpath VARCHAR(255),
            UNIQUE KEY unique_book (title, author)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def ensure_book_metadata_columns():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS isbn VARCHAR(32)")
    except mariadb.Error:
        pass
    try:
        cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS series VARCHAR(255)")
    except mariadb.Error:
        pass
    try:
        cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS publisher VARCHAR(255)")
    except mariadb.Error:
        pass
    try:
        cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS publishedDate VARCHAR(32)")
    except mariadb.Error:
        pass
    try:
        cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS description TEXT")
    except mariadb.Error:
        pass
    try:
        cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS selfLink VARCHAR(512)")
    except mariadb.Error:
        pass
    conn.commit()
    cur.close()
    conn.close()

def get_google_books_metadata(title, author):
    query = f"intitle:{title} inauthor:{author}"
    url = f"https://www.googleapis.com/books/v1/volumes?q={requests.utils.quote(query)}&maxResults=1"
    response = requests.get(url)
    if response.status_code != 200:
        return {}
    data = response.json()
    items = data.get("items", [])
    if not items:
        return {}
    info = items[0].get("volumeInfo", {})
    identifiers = info.get("industryIdentifiers", [])
    isbn = None
    for ident in identifiers:
        if "ISBN" in ident.get("type", ""):
            isbn = ident["identifier"]
            break
    seriesinfo = items[0].get("seriesInfo", {})
    series = seriesinfo.get("title") or info.get("subtitle")
    return {
        "isbn": isbn,
        "series": series,
        "publisher": info.get("publisher"),
        "publishedDate": info.get("publishedDate"),
        "description": info.get("description"),
        "selfLink": items[0].get("selfLink"),
    }

def get_google_books_metadata_by_isbn(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"
    response = requests.get(url)
    if response.status_code != 200:
        return {}
    data = response.json()
    items = data.get("items", [])
    if not items:
        return {}
    info = items[0].get("volumeInfo", {})
    identifiers = info.get("industryIdentifiers", [])
    final_isbn = None
    for ident in identifiers:
        if "ISBN" in ident.get("type", ""):
            final_isbn = ident["identifier"]
            break
    seriesinfo = items[0].get("seriesInfo", {})
    series = seriesinfo.get("title") or info.get("subtitle")
    return {
        "isbn": final_isbn,
        "series": series,
        "publisher": info.get("publisher"),
        "publishedDate": info.get("publishedDate"),
        "description": info.get("description"),
        "selfLink": items[0].get("selfLink"),
    }

def insert_book(book):
    ensure_book_metadata_columns()
    # If API book, attempt to enrich with metadata
    if "isbn" not in book or book.get("isbn") is None:
        if book.get("title") and book.get("author"):
            meta = get_google_books_metadata(book["title"], book["author"])
        elif book.get("isbn"):
            meta = get_google_books_metadata_by_isbn(book["isbn"])
        else:
            meta = {}
        for field in ["isbn", "series", "publisher", "publishedDate", "description", "selfLink"]:
            if field in meta and meta[field] is not None:
                book[field] = meta[field]
            else:
                book.setdefault(field, None)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now = datetime.now()
        cur.execute("""
            INSERT INTO books
                (title, author, cover, status, last_status_change, isbn, series, publisher, publishedDate, description, selfLink)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cover=VALUES(cover),
                status=status,
                isbn=VALUES(isbn),
                series=VALUES(series),
                publisher=VALUES(publisher),
                publishedDate=VALUES(publishedDate),
                description=VALUES(description),
                selfLink=VALUES(selfLink)
        """, (
            book['title'], book['author'], book['cover'], book['status'], now,
            book.get('isbn'), book.get('series'), book.get('publisher'),
            book.get('publishedDate'), book.get('description'), book.get('selfLink')
        ))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error inserting book: {e}")
    finally:
        cur.close()
        conn.close()

def get_all_books():
    ensure_book_metadata_columns()
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT id, title, author, cover, status, COALESCE(rating, 0) as rating, last_status_change,
                          isbn, series, publisher, publishedDate, description, selfLink, ebookpath
                   FROM books""")
    books = cur.fetchall()

    for book in books:
        cover_url = book['cover']
        if cover_url:
            filename = os.path.join(CACHE_DIR, str(book['id']))
            if not os.path.exists(filename):
                response = requests.get(cover_url)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(response.content)
            book['cover'] = filename if os.path.exists(filename) else None
        if book['last_status_change']:
            book['last_status_change'] = book['last_status_change'].strftime("%Y-%m-%d %H:%M:%S")

    cur.close()
    conn.close()
    return books

def update_book_status(title, author, status):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now = datetime.now()
        cur.execute("""
            UPDATE books SET status = %s, last_status_change = %s WHERE title = %s AND author = %s
        """, (status, now, title, author))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error updating book status: {e}")
    finally:
        cur.close()
        conn.close()

def remove_book(title, author):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM books WHERE title = %s AND author = %s", (title, author))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error removing book: {e}")
    finally:
        cur.close()
        conn.close()

def search_google_books_multiple(query, max_results=20):
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults={max_results}"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    data = response.json()
    items = data.get("items", [])
    results = []
    for item in items:
        book_info = item["volumeInfo"]
        identifiers = book_info.get("industryIdentifiers", [])
        isbn = None
        for ident in identifiers:
            if "ISBN" in ident.get("type", ""):
                isbn = ident["identifier"]
                break
        seriesinfo = item.get("seriesInfo", {})
        series = seriesinfo.get("title") or book_info.get("subtitle")
        results.append({
            "title": book_info.get("title", "Unknown title"),
            "author": ", ".join(book_info.get("authors", ["Unknown author"])),
            "cover": book_info.get("imageLinks", {}).get("thumbnail",
                                                        "https://via.placeholder.com/128x195?text=No+Cover"),
            "isbn": isbn,
            "series": series,
            "publisher": book_info.get("publisher"),
            "publishedDate": book_info.get("publishedDate"),
            "description": book_info.get("description"),
            "selfLink": item.get("selfLink"),
        })
    return results

def get_books_stats():
    books = get_all_books()
    total_books = len(books)
    status_breakdown = Counter(book['status'].strip() for book in books)
    author_breakdown = Counter(book['author'].strip() for book in books)

    read_years = Counter()
    for book in books:
        if book['status'].strip() == "Read" and book['last_status_change']:
            year = datetime.strptime(book['last_status_change'], "%Y-%m-%d %H:%M:%S").year
            read_years[year] += 1

    return total_books, status_breakdown, author_breakdown, read_years

def update_book_status_and_rating(title, author, status, rating):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            ALTER TABLE books
            ADD COLUMN IF NOT EXISTS rating INT DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_status_change DATETIME DEFAULT NULL
        """)
    except mariadb.Error:
        pass
    try:
        now = datetime.now()
        cur.execute("""
            UPDATE books SET status = %s, rating = %s, last_status_change = %s WHERE title = %s AND author = %s
        """, (status, rating, now, title, author))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error updating book status and rating: {e}")
    finally:
        cur.close()
        conn.close()

def search_google_books_by_isbn(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=5"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    data = response.json()
    items = data.get("items", [])
    results = []
    for item in items:
        book_info = item["volumeInfo"]
        identifiers = book_info.get("industryIdentifiers", [])
        fetched_isbn = None
        for ident in identifiers:
            if "ISBN" in ident.get("type", ""):
                fetched_isbn = ident["identifier"]
                break
        seriesinfo = item.get("seriesInfo", {})
        series = seriesinfo.get("title") or book_info.get("subtitle")
        results.append({
            "title": book_info.get("title", "Unknown title"),
            "author": ", ".join(book_info.get("authors", ["Unknown author"])),
            "cover": book_info.get("imageLinks", {}).get("thumbnail",
                                                        "https://via.placeholder.com/128x195?text=No+Cover"),
            "isbn": fetched_isbn,
            "series": series,
            "publisher": book_info.get("publisher"),
            "publishedDate": book_info.get("publishedDate"),
            "description": book_info.get("description"),
            "selfLink": item.get("selfLink"),
        })
    return results

def update_book_ebook_path(bookid, save_path):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("Update books set ebookpath = %s where id = %s", (save_path, bookid))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        return False
    
def get_ebook_path_by_book_id(bookid):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT ebookpath FROM books WHERE id = %s", (bookid,))
        data = cur.fetchone()
        cur.close()
        conn.close()
        if data:
            return data[0]
        return None
    except Exception as e:
        return None

def get_read_authors():
    conn = get_db_connection()
    cur = conn.cursor()
    query = "SELECT DISTINCT author FROM books WHERE status = 'Read'"
    cur.execute(query)
    authors = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return authors

def find_new_books_by_authors(authors):
    new_books = []
    for author in authors:
        results = search_google_books_multiple(f"inauthor:{author}", max_results=5)  # You can tune max_results
        # Filter out books that already exist in the database.
        existing_titles = {book['title'].lower() for book in get_all_books() if book['author'].strip() == author}
        for result in results:
            if result['title'].lower() not in existing_titles:
                new_books.append(result)
    return new_books