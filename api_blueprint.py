import os
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from helpers import search_google_books_by_isbn, insert_book
from werkzeug.utils import secure_filename
from helpers import update_book_ebook_path,get_ebook_path_by_book_id,create_upload_folder

ALLOWED_EXTENSIONS = {'pdf', 'epub', 'mobi', 'azw3'}

api_bp = Blueprint('api', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@api_bp.route('/sample')
def sample_api():
    return jsonify(message="This is a sample API endpoint.")

@api_bp.route("/isbn_lookup", methods=["POST"])
def api_isbn_lookup():
    print("API ISBN Called")
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return "ISBN is required", 500
    results = search_google_books_by_isbn(isbn)
    if len(results) == 1:
        book = results[0]
        book['status'] = "TBR"
        insert_book(book)
        return "Book Found", 200
    elif len(results) > 1:
        return "Multiple books found?", 201
    else:
        return "Not Found", 404

@api_bp.route("/upload_ebook/<int:book_id>", methods=["POST"])
def api_upload_ebook(book_id):
    create_upload_folder()
    if "ebook" not in request.files:
        return jsonify(success=False, message="No file part"), 400
    file = request.files["ebook"]
    if file.filename == "":
        return jsonify(success=False, message="No selected file"), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f"{book_id}_{filename}")
        file.save(save_path)
        update_book_ebook_path(book_id, save_path)
        return jsonify(success=True, message="File uploaded")
    else:
        return jsonify(success=False, message="File type not allowed"), 400

@api_bp.route("/download_ebook/<int:book_id>", methods=["GET"])
def api_download_ebook(book_id):
    path = get_ebook_path_by_book_id(book_id)
    if path and os.path.exists(path):
        directory = os.path.abspath(os.path.dirname(path))
        filename = os.path.basename(path)
        return send_from_directory(directory, filename, as_attachment=True)
    else:
        return jsonify(success=False, message="Ebook not found"), 404