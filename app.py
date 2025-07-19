from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
import requests
import mariadb
import os
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=True)



from api_blueprint import api_bp
from helpers import insert_book,search_google_books_by_isbn,search_google_books_multiple,get_all_books,update_book_status,remove_book,get_books_stats,create_table,update_book_status_and_rating



app = Flask(__name__)

STATUS_OPTIONS = ["TBR", "Reading", "Read", "DNF"]
CACHE_DIR = 'cover_cache'

DB_CONFIG = {
    'user': os.getenv('BOOKVAULT_DBUSER'),
    'password': os.getenv('BOOKVAULT_DBPASS'),
    'host': os.getenv('BOOKVAULT_DBHOST'),
    'port': int(os.getenv('BOOKVAULT_DBPORT')),
    'database': os.getenv('BOOKVAULT_DBNAME')
}

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        selected = request.form.get("selected_book")
        if selected:
            import json
            book = json.loads(selected)
            book['status'] = "TBR"
            insert_book(book)
            return redirect(url_for("index"))

        query = request.form.get("search")
        if query:
            results = search_google_books_multiple(query)
            if len(results) > 1:
                books = get_all_books()
                return render_template("index.html", books=books, status_options=STATUS_OPTIONS, search_results=results)
            elif len(results) == 1:
                book = results[0]
                book['status'] = "TBR"
                insert_book(book)
                return redirect(url_for("index"))
            else:
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
        return redirect(url_for("index"))

app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == "__main__":
    create_table()
    app.run(debug=True, port=5001, host='0.0.0.0')
