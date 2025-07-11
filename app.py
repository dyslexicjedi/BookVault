from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
import requests
import mariadb
import os
from collections import Counter
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

app = Flask(__name__)

STATUS_OPTIONS = ["TBR", "Reading", "Read", "DNF"]
CACHE_DIR = 'cover_cache'

# MariaDB connection parameters
DB_CONFIG = {
    'user': os.getenv('BOOKVAULT_DBUSER'),
    'password': os.getenv('BOOKVAULT_DBPASS'),
    'host': os.getenv('BOOKVAULT_DBHOST'),
    'port': int(os.getenv('BOOKVAULT_DBPORT')),
    'database': os.getenv('BOOKVAULT_DBNAME')
}

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
            UNIQUE KEY unique_book (title, author)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def insert_book(book):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now = datetime.now()
        cur.execute("""
            INSERT INTO books (title, author, cover, status, last_status_change) VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE cover=VALUES(cover), status=status
        """, (book['title'], book['author'], book['cover'], book['status'], now))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error inserting book: {e}")
    finally:
        cur.close()
        conn.close()

def get_all_books():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, title, author, cover, status, COALESCE(rating, 0) as rating, last_status_change FROM books")
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
        # Format last_status_change as string if present
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

# Add this function to delete a book from DB
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
        results.append({
            "title": book_info.get("title", "Unknown title"),
            "author": ", ".join(book_info.get("authors", ["Unknown author"])),
            "cover": book_info.get("imageLinks", {}).get("thumbnail",
                                                        "https://via.placeholder.com/128x195?text=No+Cover")
        })
    return results

def get_books_stats():
    books = get_all_books()
    total_books = len(books)
    status_breakdown = Counter(book['status'].strip() for book in books)
    author_breakdown = Counter(book['author'].strip() for book in books)

    # Count books read by year of last_status_change
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
        # Add rating column if not exists (execute once)
        cur.execute("""
            ALTER TABLE books
            ADD COLUMN IF NOT EXISTS rating INT DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_status_change DATETIME DEFAULT NULL
        """)
    except mariadb.Error:
        # Ignore if column already exists
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

# Add this helper function for ISBN lookup
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
        results.append({
            "title": book_info.get("title", "Unknown title"),
            "author": ", ".join(book_info.get("authors", ["Unknown author"])),
            "cover": book_info.get("imageLinks", {}).get("thumbnail",
                                                        "https://via.placeholder.com/128x195?text=No+Cover")
        })
    return results


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Use different form keys to distinguish actions:
        selected = request.form.get("selected_book")
        if selected:
            # JSON string passed from form hidden input, parse it:
            import json
            book = json.loads(selected)
            book['status'] = "TBR"
            insert_book(book)
            return redirect(url_for("index"))

        query = request.form.get("search")
        if query:
            results = search_google_books_multiple(query)
            if len(results) > 1:
                # Show choices to user
                books = get_all_books()
                return render_template("index.html", books=books, status_options=STATUS_OPTIONS, search_results=results)
            elif len(results) == 1:
                book = results[0]
                book['status'] = "TBR"
                insert_book(book)
                return redirect(url_for("index"))
            else:
                # no results found, just reload
                return redirect(url_for("index"))

    books = get_all_books()
    return render_template("index.html", books=books, status_options=STATUS_OPTIONS)

@app.route("/api/get_books")
def get_books():
    books = get_all_books()
    return books

@app.route("/update_status", methods=["POST"])
def update_status():
    data = request.json
    title = data.get("title")
    author = data.get("author")
    new_status = data.get("status")
    if new_status in STATUS_OPTIONS:
        update_book_status(title, author, new_status)
    return jsonify(success=True)

# Add this new route
@app.route("/remove_book", methods=["POST"])
def remove_book_route():
    data = request.json
    title = data.get("title")
    author = data.get("author")
    remove_book(title, author)
    return jsonify(success=True)

@app.route("/stats")
def stats():
    total_books, status_breakdown, author_breakdown, read_years = get_books_stats()
    return render_template("stats.html", total_books=total_books,
                           status_breakdown=status_breakdown,
                           author_breakdown=author_breakdown,
                           read_years=read_years)

@app.route('/cover_cache/<path:filename>')
def serve_cover_cache(filename):
    return send_from_directory(CACHE_DIR, filename)

@app.route("/update_status_rating", methods=["POST"])
def update_status_rating():
    data = request.json
    title = data.get("title")
    author = data.get("author")
    new_status = data.get("status")
    rating = data.get("rating", 0)
    if new_status in STATUS_OPTIONS:
        update_book_status_and_rating(title, author, new_status, rating)
    return jsonify(success=True)

@app.route("/isbn_lookup", methods=["POST"])
def isbn_lookup():
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return redirect(url_for("index"))
    # Search Google Books by ISBN
    results = search_google_books_by_isbn(isbn)
    if len(results) == 1:
        book = results[0]
        book['status'] = "TBR"
        insert_book(book)
        return redirect(url_for("index"))
    elif len(results) > 1:
        books = get_all_books()
        return render_template("index.html", books=books, status_options=STATUS_OPTIONS, search_results=results)
    else:
        # No results found
        return redirect(url_for("index"))

if __name__ == "__main__":
    create_table()
    app.run(debug=True, port=5001, host='0.0.0.0')
