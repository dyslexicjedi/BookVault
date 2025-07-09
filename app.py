from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
import requests
import mariadb
import os
from collections import Counter
from dotenv import load_dotenv

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
        cur.execute("""
            INSERT INTO books (title, author, cover, status) VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE cover=VALUES(cover), status=status
        """, (book['title'], book['author'], book['cover'], book['status']))
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
    cur.execute("SELECT id, title, author, cover, status FROM books")
    books = cur.fetchall()

    for book in books:
        cover_url = book['cover']
        if cover_url:
            # Derive filename from URL
            filename = os.path.join(CACHE_DIR, str(book['id']))
            if not os.path.exists(filename):
                # Download and save cover
                response = requests.get(cover_url)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(response.content)
            book['cover'] = filename if os.path.exists(filename) else None

    cur.close()
    conn.close()
    return books

def update_book_status(title, author, status):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE books SET status = %s WHERE title = %s AND author = %s", (status, title, author))
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

def search_google_books_multiple(query, max_results=10):
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
    return total_books, status_breakdown, author_breakdown

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
    total_books, status_breakdown, author_breakdown = get_books_stats()
    return render_template("stats.html", total_books=total_books,
                           status_breakdown=status_breakdown,
                           author_breakdown=author_breakdown)

@app.route('/cover_cache/<path:filename>')
def serve_cover_cache(filename):
    return send_from_directory(CACHE_DIR, filename)

if __name__ == "__main__":
    create_table()
    app.run(debug=True, port=5001)
