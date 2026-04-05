import os
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from helpers import search_google_books_by_isbn, insert_book, get_all_books, filter_books, validate_isbn
from werkzeug.utils import secure_filename
from helpers import update_book_ebook_path,get_ebook_path_by_book_id,create_upload_folder,update_physical_copy

ALLOWED_EXTENSIONS = {'pdf', 'epub', 'mobi', 'azw3'}

api_bp = Blueprint('api', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@api_bp.route('/sample')
def sample_api():
    return jsonify(message="This is a sample API endpoint.")

@api_bp.route('/get_books')
def api_get_books():
    """Get books with optional filtering"""
    # Get filter parameters from query string
    status_filters = request.args.getlist('status_filter')
    format_filters = request.args.getlist('format_filter')
    rating_filters = request.args.getlist('rating_filter')
    tag_ids = request.args.getlist('tags')
    
    # Convert tag IDs to integers
    if tag_ids:
        tag_ids = [int(tag_id) for tag_id in tag_ids if tag_id.isdigit()]
    
    # Check if any filters are applied
    if status_filters or format_filters or rating_filters or tag_ids:
        books = filter_books(
            status_filters=status_filters if status_filters else None,
            format_filters=format_filters if format_filters else None,
            rating_filters=rating_filters if rating_filters else None,
            tag_ids=tag_ids if tag_ids else None
        )
    else:
        books = get_all_books()
    
    return jsonify(books)

@api_bp.route("/isbn_lookup", methods=["POST"])
def api_isbn_lookup():
    print("API ISBN Called")
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return jsonify(success=False, message="ISBN is required"), 400
    if not validate_isbn(isbn):
        return jsonify(success=False, message="Invalid ISBN format"), 400
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
    
@api_bp.route("/update_physical_copy/<int:book_id>/<int:status>", methods=["POST"])
def api_update_physical_copy(book_id,status):
    try:
        physical_copy = bool(status)
        if not physical_copy:
            return jsonify(success=False, message="Physical copy status is required"), 400
        success = update_physical_copy(book_id, physical_copy)
        if success:
            return jsonify(success=True, message="Physical copy updated successfully")
        else:
            return jsonify(success=False, message="Failed to update physical copy"), 500
    except Exception as e:
        print("Exception in Physical Copy Update %s"%e)
        return jsonify(success=False, message="Failed to update physical copy"), 500