# BookVault

BookVault is a simple web application to manage and track your personal book collection. It allows you to search for books via the Google Books API, add them to your library, update their reading status and rating, and view statistics about your collection.

## Features

- Search and add books by title or author.
- View your book collection with cover images, titles, authors, status, and rating.
- Edit a book's reading status and star rating.
- View statistics including total books, breakdown by status, and by author.
- Uses MariaDB for persistent storage.
- Caches book cover images locally to reduce bandwidth.
- Responsive UI styled with Bootstrap 5.

## Getting Started

### Prerequisites

- Python 3.8+
- MariaDB Server
- `pip` (Python package manager)

### Installation

1. Clone this repository:

   ```bash
   git clone <repo-url>
   cd bookvault
   ```

2. Create and activate a Python virtual environment (optional but recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install required Python packages:

   ```bash
   pip install -r requirements.txt
   ```

4. Setup your MariaDB database and user.

5. Create a `.env` file in the project root with the following variables:
    BOOKVAULT_DBUSER=your_db_username 
    BOOKVAULT_DBPASS=your_db_password 
    BOOKVAULT_DBHOST=localhost 
    BOOKVAULT_DBPORT=3306 
    BOOKVAULT_DBNAME=your_db_name


6. Run the application:

    ```bash
    python app.py
    ```

7. Open your browser and go to http://localhost:5001

## Usage
* Use the search bar on the main page to find books and add them to your collection.
* Click the pencil (edit) icon on a book card to update its reading status and rating.
* Visit the "View Statistics" page for insights into your library.
* The app caches book cover images locally under the cover_cache directory.

## Project Structure
* app.py: Main Flask application.
* templates/: HTML templates for the UI (index.html, stats.html).
* cover_cache/: Cached cover images (created at runtime).
* requirements.txt: Python dependencies.

## Dependencies
* Flask
* requests
* mariadb
* python-dotenv
* Bootstrap 5 (CDN for frontend styling)

## License
    This project is licensed under the MIT License.

## Acknowledgments
* Google Books API for book data.
* Bootstrap for frontend UI components and styling.
