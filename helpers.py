import os
import re
import requests
import mariadb
from collections import Counter
from datetime import datetime

STATUS_OPTIONS = ["TBR", "Reading", "Read", "DNF"]
CACHE_DIR = 'cover_cache'

def validate_isbn(isbn: str) -> bool:
    """Validate ISBN-10 or ISBN-13 format (basic check)."""
    if not isbn:
        return False
    
    # Remove hyphens and spaces for validation
    clean_isbn = isbn.replace('-', '').replace(' ', '')
    
    # Must be 10 or 13 characters after cleaning
    if len(clean_isbn) not in (10, 13):
        return False
    
    # For ISBN-10: first 9 must be digits, last can be digit or X
    if len(clean_isbn) == 10:
        if not clean_isbn[:-1].isdigit():
            return False
        if clean_isbn[-1] != 'X' and not clean_isbn[-1].isdigit():
            return False
    
    # For ISBN-13: must be all digits
    elif len(clean_isbn) == 13:
        if not clean_isbn.isdigit():
            return False
    
    return True


DB_CONFIG = {
    'user': os.getenv('BOOKVAULT_DBUSER'),
    'password': os.getenv('BOOKVAULT_DBPASS'),
    'host': os.getenv('BOOKVAULT_DBHOST'),
    'port': int(os.getenv('BOOKVAULT_DBPORT', '3306')),
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
            physical_copy BOOL DEFAULT 0,
            UNIQUE KEY unique_book (title, author)
        )
    """)
    
    # Create tags table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            color VARCHAR(7) DEFAULT '#007bff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create book_tags junction table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS book_tags (
            book_id INT,
            tag_id INT,
            PRIMARY KEY (book_id, tag_id),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
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
    response = requests.get(url, timeout=10)
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

def get_google_books_metadata_by_isbn(isbn: str):
    if not validate_isbn(isbn):
        return {}
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"
    response = requests.get(url, timeout=10)
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

def insert_book(book: dict) -> bool:
    """Insert book with validation. Returns True on success, False otherwise."""
    if not book or not isinstance(book, dict):
        return False
    
    # Validate required fields
    title = book.get("title")
    author = book.get("author")
    
    if not title or not author:
        return False
    
    if not isinstance(title, str) or not isinstance(author, str):
        return False
    
    # Validate optional ISBN if present
    isbn = book.get("isbn")
    if isbn is not None and isbn != "":
        if not validate_isbn(str(isbn)):
            book["isbn"] = None
    
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
        return True
    except mariadb.Error as e:
        print(f"Error inserting book: {e}")
        return False
    finally:
        cur.close()
        conn.close()
    
    return False

def get_all_books():
    ensure_book_metadata_columns()
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT id, title, author, cover, status, COALESCE(rating, 0) as rating, last_status_change,
                          isbn, series, publisher, publishedDate, description, selfLink, ebookpath, physical_copy
                   FROM books""")
    books = cur.fetchall()

    # Get tags for each book
    for book in books:
        cur.execute("""
            SELECT t.id, t.name, t.color 
            FROM tags t 
            JOIN book_tags bt ON t.id = bt.tag_id 
            WHERE bt.book_id = %s
        """, (book['id'],))
        book['tags'] = cur.fetchall()

        cover_url = book['cover']
        if cover_url:
            filename = os.path.join(CACHE_DIR, str(book['id']))
            if not os.path.exists(filename):
                response = requests.get(cover_url, timeout=15)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(response.content)
            book['cover'] = filename if os.path.exists(filename) else None
        if book['last_status_change']:
            book['last_status_change'] = book['last_status_change'].strftime("%Y-%m-%d %H:%M:%S")

    cur.close()
    conn.close()
    return books

def update_book_status(title: str, author: str, status: str) -> bool:
    """Update book status with validation. Returns True on success, False otherwise."""
    if not title or not author or not status:
        return False
    
    if not isinstance(title, str) or not isinstance(author, str) or not isinstance(status, str):
        return False
    
    if status not in STATUS_OPTIONS:
        return False
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now = datetime.now()
        cur.execute("""
            UPDATE books SET status = %s, last_status_change = %s WHERE title = %s AND author = %s
        """, (status, now, title, author))
        conn.commit()
        return True
    except mariadb.Error as e:
        print(f"Error updating book status: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def remove_book(title: str, author: str) -> bool:
    """Remove book with validation. Returns True on success, False otherwise."""
    if not title or not author:
        return False
    
    if not isinstance(title, str) or not isinstance(author, str):
        return False
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM books WHERE title = %s AND author = %s", (title, author))
        conn.commit()
        return True
    except mariadb.Error as e:
        print(f"Error removing book: {e}")
        return False
    finally:
        cur.close()
        conn.close()
    
    return False

def search_google_books_multiple(query: str, max_results: int = 20) -> list:
    """Search Google Books with validation. Returns list of book results."""
    if not query or not isinstance(query, str):
        return []
    
    try:
        max_results_int = int(max_results)
        if max_results_int < 1 or max_results_int > 50:
            max_results_int = 20
    except (ValueError, TypeError):
        max_results_int = 20
    
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults={max_results_int}"
    response = requests.get(url, timeout=10)
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

    # Tag breakdown
    tag_breakdown = Counter()
    for book in books:
        for tag in book.get('tags', []):
            tag_breakdown[tag['name']] += 1

    read_years = Counter()
    for book in books:
        if book['status'].strip() == "Read" and book['last_status_change']:
            year = datetime.strptime(book['last_status_change'], "%Y-%m-%d %H:%M:%S").year
            read_years[year] += 1

    return total_books, status_breakdown, author_breakdown, read_years, tag_breakdown

def update_book_status_and_rating(title: str, author: str, status: str, rating: int) -> bool:
    """Update book status and rating with validation. Returns True on success, False otherwise."""
    if not title or not author or not status:
        return False
    
    if not isinstance(title, str) or not isinstance(author, str) or not isinstance(status, str):
        return False
    
    if status not in STATUS_OPTIONS:
        return False
    
    try:
        rating_value = int(rating)
        if rating_value < 0 or rating_value > 5:
            return False
    except (ValueError, TypeError):
        return False

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
        """, (status, rating_value, now, title, author))
        conn.commit()
        return True
    except mariadb.Error as e:
        print(f"Error updating book status and rating: {e}")
        return False
    finally:
        cur.close()
        conn.close()
    
    return False

def search_google_books_by_isbn(isbn: str) -> list:
    if not validate_isbn(isbn):
        return []
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=5"
    response = requests.get(url, timeout=10)
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
    # Get all existing books once to avoid multiple DB calls
    existing_books = get_all_books()
    # Create a set of (title, author) tuples for quick lookup
    existing_book_keys = {
        (book['title'].lower().strip(), book['author'].lower().strip()) 
        for book in existing_books
    }
    
    for author in authors:
        results = search_google_books_multiple(f"inauthor:{author}", max_results=5)  # You can tune max_results
        for result in results:
            # Check if this book (by title and author) already exists in the library
            book_key = (result['title'].lower().strip(), result['author'].lower().strip())
            if book_key not in existing_book_keys:
                new_books.append(result)
    
    return new_books

def update_physical_copy(bookid, physical_copy):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE books SET physical_copy = %s WHERE id = %s", (physical_copy, bookid))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        return False

# Tag management functions
def create_tag(name, color='#007bff'):
    """Create a new tag"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO tags (name, color) VALUES (%s, %s)", (name, color))
        conn.commit()
        tag_id = cur.lastrowid
        cur.close()
        conn.close()
        return tag_id
    except mariadb.Error as e:
        print(f"Error creating tag: {e}")
        cur.close()
        conn.close()
        return None

def get_all_tags():
    """Get all available tags"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM tags ORDER BY name")
    tags = cur.fetchall()
    cur.close()
    conn.close()
    return tags

def add_tag_to_book(book_id, tag_id):
    """Add a tag to a book"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT IGNORE INTO book_tags (book_id, tag_id) VALUES (%s, %s)", (book_id, tag_id))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except mariadb.Error as e:
        print(f"Error adding tag to book: {e}")
        cur.close()
        conn.close()
        return False

def remove_tag_from_book(book_id, tag_id):
    """Remove a tag from a book"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM book_tags WHERE book_id = %s AND tag_id = %s", (book_id, tag_id))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except mariadb.Error as e:
        print(f"Error removing tag from book: {e}")
        cur.close()
        conn.close()
        return False

def get_book_tags(book_id):
    """Get all tags for a specific book"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT t.* FROM tags t 
        JOIN book_tags bt ON t.id = bt.tag_id 
        WHERE bt.book_id = %s
    """, (book_id,))
    tags = cur.fetchall()
    cur.close()
    conn.close()
    return tags

def delete_tag(tag_id):
    """Delete a tag (this will also remove it from all books)"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM tags WHERE id = %s", (tag_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except mariadb.Error as e:
        print(f"Error deleting tag: {e}")
        cur.close()
        conn.close()
        return False

def update_tag(tag_id, name, color):
    """Update a tag's name and color"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE tags SET name = %s, color = %s WHERE id = %s", (name, color, tag_id))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except mariadb.Error as e:
        print(f"Error updating tag: {e}")
        cur.close()
        conn.close()
        return False

def get_books_by_tag(tag_id):
    """Get all books that have a specific tag"""
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT b.* FROM books b 
        JOIN book_tags bt ON b.id = bt.book_id 
        WHERE bt.tag_id = %s
    """, (tag_id,))
    books = cur.fetchall()
    cur.close()
    conn.close()
    return books

def filter_books_by_tags(tag_ids):
    """Filter books by multiple tags (books that have ALL specified tags)"""
    if not tag_ids:
        return get_all_books()
    
    # Validate all tag_ids are positive integers
    validated_tag_ids = []
    for tid in tag_ids:
        try:
            tid_int = int(tid)
            if tid_int > 0:
                validated_tag_ids.append(tid_int)
        except (ValueError, TypeError):
            continue
    
    if not validated_tag_ids:
        return get_all_books()
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    placeholders = ','.join(['%s'] * len(validated_tag_ids))
    
    cur.execute(f"""
        SELECT b.id, b.title, b.author, b.cover, b.status, COALESCE(b.rating, 0) as rating, 
               b.last_status_change, b.isbn, b.series, b.publisher, b.publishedDate, 
               b.description, b.selfLink, b.ebookpath, b.physical_copy
        FROM books b
        WHERE b.id IN (
            SELECT bt.book_id 
            FROM book_tags bt 
            WHERE bt.tag_id IN ({placeholders})
            GROUP BY bt.book_id 
            HAVING COUNT(DISTINCT bt.tag_id) = %s
        )
    """, validated_tag_ids + [len(validated_tag_ids)])
    
    books = cur.fetchall()
    
    # Get tags for each book
    for book in books:
        cur.execute("""
            SELECT t.id, t.name, t.color 
            FROM tags t 
            JOIN book_tags bt ON t.id = bt.tag_id 
            WHERE bt.book_id = %s
        """, (book['id'],))
        book['tags'] = cur.fetchall()

        # Handle cover caching
        cover_url = book['cover']
        if cover_url:
            filename = os.path.join(CACHE_DIR, str(book['id']))
            if not os.path.exists(filename):
                response = requests.get(cover_url, timeout=15)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(response.content)
            book['cover'] = filename if os.path.exists(filename) else None
        if book['last_status_change']:
            book['last_status_change'] = book['last_status_change'].strftime("%Y-%m-%d %H:%M:%S")
    
    cur.close()
    conn.close()
    return books

def filter_books(status_filters=None, format_filters=None, rating_filters=None, tag_ids=None):
    """Filter books by multiple criteria"""
    ensure_book_metadata_columns()
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Base query
    query = """
        SELECT DISTINCT b.id, b.title, b.author, b.cover, b.status, COALESCE(b.rating, 0) as rating, 
               b.last_status_change, b.isbn, b.series, b.publisher, b.publishedDate, 
               b.description, b.selfLink, b.ebookpath, b.physical_copy
        FROM books b
    """
    
    conditions = []
    params = []
    
    # Add tag filter if specified
    if tag_ids:
        # Validate and sanitize tag_ids
        validated_tag_ids = []
        for tid in tag_ids:
            try:
                tid_int = int(tid)
                if tid_int > 0:
                    validated_tag_ids.append(tid_int)
            except (ValueError, TypeError):
                continue
        
        if validated_tag_ids:
            query += " JOIN book_tags bt ON b.id = bt.book_id"
            placeholders = ','.join(['%s'] * len(validated_tag_ids))
            conditions.append(f"bt.tag_id IN ({placeholders})")
            params.extend(validated_tag_ids)
    
    # Add status filter
    if status_filters:
        # Validate status values against allowed list
        valid_statuses = {'TBR', 'Reading', 'Read', 'DNF'}
        validated_statuses = [s for s in status_filters if s in valid_statuses]
        
        if validated_statuses:
            status_placeholders = ','.join(['%s'] * len(validated_statuses))
            conditions.append(f"b.status IN ({status_placeholders})")
            params.extend(validated_statuses)
    
    # Add format filters
    if format_filters:
        format_conditions = []
        if 'ebook' in format_filters:
            format_conditions.append("b.ebookpath IS NOT NULL AND b.ebookpath != ''")
        if 'physical' in format_filters:
            format_conditions.append("b.physical_copy = 1")
        if format_conditions:
            conditions.append(f"({' OR '.join(format_conditions)})")
    
    # Add rating filters
    if rating_filters:
        rating_conditions = []
        for rating_filter in rating_filters:
            if rating_filter == 'rated':
                rating_conditions.append("b.rating > 0")
            elif rating_filter == 'unrated':
                rating_conditions.append("(b.rating IS NULL OR b.rating = 0)")
            elif rating_filter.endswith('star'):
                # Validate star rating value
                try:
                    star_rating = int(rating_filter[0])
                    if 1 <= star_rating <= 5:
                        rating_conditions.append("b.rating >= %s")
                        params.append(star_rating)
                except (ValueError, IndexError):
                    continue
        if rating_conditions:
            conditions.append(f"({' OR '.join(rating_conditions)})")
    
    # Add WHERE clause if there are conditions
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    # Add GROUP BY if we're filtering by tags
    if tag_ids:
        query += " GROUP BY b.id HAVING COUNT(DISTINCT bt.tag_id) = %s"
        params.append(len(tag_ids))
    
    cur.execute(query, params)
    books = cur.fetchall()
    
    # Get tags for each book
    for book in books:
        cur.execute("""
            SELECT t.id, t.name, t.color 
            FROM tags t 
            JOIN book_tags bt ON t.id = bt.tag_id 
            WHERE bt.book_id = %s
        """, (book['id'],))
        book['tags'] = cur.fetchall()

        # Handle cover caching
        cover_url = book['cover']
        if cover_url:
            filename = os.path.join(CACHE_DIR, str(book['id']))
            if not os.path.exists(filename):
                response = requests.get(cover_url, timeout=15)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        f.write(response.content)
            book['cover'] = filename if os.path.exists(filename) else None
        if book['last_status_change']:
            book['last_status_change'] = book['last_status_change'].strftime("%Y-%m-%d %H:%M:%S")

    cur.close()
    conn.close()
    return books
