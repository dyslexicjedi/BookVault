from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
import requests
import mariadb
import os
from collections import Counter
from datetime import datetime
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
load_dotenv(override=True)

from api_blueprint import api_bp
from helpers import (
    insert_book,
    search_google_books_by_isbn,
    search_google_books_multiple,
    get_all_books,
    update_book_status,
    remove_book,
    get_books_stats,
    create_table,
    update_book_status_and_rating,
    get_read_authors,
    find_new_books_by_authors,
    get_all_tags,
    create_tag,
    add_tag_to_book,
    remove_tag_from_book,
    filter_books_by_tags,
    delete_tag,
    update_tag
)

# Configuration
STATUS_OPTIONS = ["TBR", "Reading", "Read", "DNF"]
CACHE_DIR = 'cover_cache'
UPLOAD_FOLDER = 'ebooks'

DB_CONFIG = {
    'user': os.getenv('BOOKVAULT_DBUSER'),
    'password': os.getenv('BOOKVAULT_DBPASS'),
    'host': os.getenv('BOOKVAULT_DBHOST'),
    'port': int(os.getenv('BOOKVAULT_DBPORT')),
    'database': os.getenv('BOOKVAULT_DBNAME')
}

# App setup
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Handle book selection
        selected = request.form.get("selected_book")
        if selected:
            import json
            book = json.loads(selected)
            book['status'] = "TBR"
            insert_book(book)
            return redirect(url_for("index"))

        # Handle search
        query = request.form.get("search")
        if query:
            results = search_google_books_multiple(query)
            if len(results) > 1:
                books = get_all_books()
                tags = get_all_tags()
                return render_template("index.html", books=books, status_options=STATUS_OPTIONS, search_results=results, tags=tags)
            elif len(results) == 1:
                book = results[0]
                book['status'] = "TBR"
                insert_book(book)
                return redirect(url_for("index"))
            else:
                return redirect(url_for("index"))

    # Handle tag filtering
    selected_tags = request.args.getlist('tags')
    if selected_tags:
        # Convert string IDs to integers
        tag_ids = [int(tag_id) for tag_id in selected_tags if tag_id.isdigit()]
        books = filter_books_by_tags(tag_ids)
    else:
        books = get_all_books()
    
    tags = get_all_tags()
    return render_template("index.html", books=books, status_options=STATUS_OPTIONS, tags=tags, selected_tags=selected_tags)

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
    color_scheme = [
        "#3498db",  # Blue
        "#e74c3c",  # Red
        "#2ecc71",  # Green
        "#f39c12",  # Orange
        "#9b59b6",  # Purple
        "#1abc9c",  # Turquoise
        "#34495e",  # Dark Blue
        "#e67e22",  # Carrot
        "#16a085",  # Green Sea
        "#8e44ad"   # Wisteria
    ]
    total_books, status_breakdown, author_breakdown, read_years, tag_breakdown = get_books_stats()
    return render_template("stats.html", 
                          total_books=total_books,
                          status_breakdown=status_breakdown,
                          author_breakdown=author_breakdown,
                          read_years=read_years,
                          tag_breakdown=tag_breakdown,
                          color_scheme=color_scheme)

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
    
@app.route("/recommendations")
def recommendations():
    authors = get_read_authors()
    new_books = find_new_books_by_authors(authors)
    return render_template("recommendations.html", books=new_books)

@app.route("/add_recommended_book", methods=["POST"])
def add_recommended_book():
    # Extract book data from the form
    book = {
        'title': request.form.get('title'),
        'author': request.form.get('author'),
        'cover': request.form.get('cover'),
        'status': 'TBR',
        'isbn': request.form.get('isbn', None),
        'series': request.form.get('series', None),
        'publisher': request.form.get('publisher', None),
        'publishedDate': request.form.get('publishedDate', None),
        'description': request.form.get('description', None),
        'selfLink': request.form.get('selfLink', None)
    }
    # Insert the book into the database
    insert_book(book)
    # Redirect back to the recommendations
    return redirect(url_for('recommendations'))

# Tag management routes
@app.route("/tags")
def manage_tags():
    tags = get_all_tags()
    return render_template("tags.html", tags=tags)

@app.route("/create_tag", methods=["POST"])
def create_tag_route():
    data = request.json
    name = data.get("name", "").strip()
    color = data.get("color", "#007bff")
    
    if name:
        tag_id = create_tag(name, color)
        if tag_id:
            return jsonify(success=True, tag_id=tag_id)
        else:
            return jsonify(success=False, message="Tag already exists or error creating tag")
    return jsonify(success=False, message="Tag name is required")

@app.route("/update_tag", methods=["POST"])
def update_tag_route():
    data = request.json
    tag_id = data.get("tag_id")
    name = data.get("name", "").strip()
    color = data.get("color", "#007bff")
    
    if tag_id and name:
        success = update_tag(tag_id, name, color)
        return jsonify(success=success)
    return jsonify(success=False, message="Tag ID and name are required")

@app.route("/delete_tag", methods=["POST"])
def delete_tag_route():
    data = request.json
    tag_id = data.get("tag_id")
    
    if tag_id:
        success = delete_tag(tag_id)
        return jsonify(success=success)
    return jsonify(success=False, message="Tag ID is required")

@app.route("/add_tag_to_book", methods=["POST"])
def add_tag_to_book_route():
    data = request.json
    book_id = data.get("book_id")
    tag_id = data.get("tag_id")
    
    if book_id and tag_id:
        success = add_tag_to_book(book_id, tag_id)
        return jsonify(success=success)
    return jsonify(success=False, message="Book ID and Tag ID are required")

@app.route("/remove_tag_from_book", methods=["POST"])
def remove_tag_from_book_route():
    data = request.json
    book_id = data.get("book_id")
    tag_id = data.get("tag_id")
    
    if book_id and tag_id:
        success = remove_tag_from_book(book_id, tag_id)
        return jsonify(success=success)
    return jsonify(success=False, message="Book ID and Tag ID are required")

app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == "__main__":
    create_table()
    app.run(debug=True, port=5001, host='0.0.0.0')
