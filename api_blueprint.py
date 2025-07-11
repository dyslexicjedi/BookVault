from flask import Blueprint, jsonify, request
from helpers import search_google_books_by_isbn,insert_book

api_bp = Blueprint('api', __name__)

@api_bp.route('/sample')
def sample_api():
    return jsonify(message="This is a sample API endpoint.")

@api_bp.route("/isbn_lookup", methods=["POST"])
def api_isbn_lookup():
    print("API ISBN Called")
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return "ISBN is required", 500
    # Search Google Books by ISBN
    results = search_google_books_by_isbn(isbn)
    if len(results) == 1:
        book = results[0]
        book['status'] = "TBR"
        insert_book(book)
        return "Book Found", 200
    elif len(results) > 1:
        return "Multiple books found?", 201
    else:
        # No results found
        return "Not Found", 404