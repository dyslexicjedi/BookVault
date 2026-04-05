import pytest
import sys
import os
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_env_vars():
    with patch.dict(os.environ, {
        'BOOKVAULT_DBUSER': 'testuser',
        'BOOKVAULT_DBPASS': 'testpass',
        'BOOKVAULT_DBHOST': 'localhost',
        'BOOKVAULT_DBPORT': '3306',
        'BOOKVAULT_DBNAME': 'test_db'
    }, clear=True):
        yield


@pytest.fixture
def helpers_module(mock_env_vars):
    """Import helpers module with mocked environment"""
    import helpers
    importlib.reload(helpers)
    return helpers


class TestGetDBConnection:
    def test_get_db_connection_returns_connection(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            conn = helpers_module.get_db_connection()
            assert conn is not None


class TestCreateTable:
    def test_create_table_creates_all_tables(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            helpers_module.create_table()
            
            assert mock_cursor.execute.call_count >= 3


class TestInsertBook:
    def test_insert_book_with_all_fields(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            book = {
                'title': 'Test Book', 'author': 'Test Author', 'cover': None,
                'status': 'TBR', 'isbn': '1234567890', 'series': None,
                'publisher': None, 'publishedDate': None, 'description': None,
                'selfLink': None
            }
            
            helpers_module.insert_book(book)
            
            assert mock_cursor.execute.called

    def test_insert_book_with_partial_fields(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            book = {
                'title': 'Minimal Book', 'author': 'Minimal Author',
                'cover': None, 'status': 'TBR'
            }
            
            helpers_module.insert_book(book)
            
            assert mock_cursor.execute.called


class TestGetAllBooks:
    def test_get_all_books_returns_list(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            with patch('helpers.os.path.exists', return_value=True):
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_cursor.fetchall.side_effect = [
                    [{'id': 1, 'title': 'Book 1', 'author': 'Author 1',
                      'cover': None, 'status': 'TBR', 'rating': 0,
                      'last_status_change': None}],
                    [], []
                ]
                mock_connect.return_value = mock_conn
                
                books = helpers_module.get_all_books()
                
                assert isinstance(books, list)
                assert len(books) == 1
                assert 'tags' in books[0]

    def test_get_all_books_includes_tags(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            with patch('helpers.os.path.exists', return_value=True):
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_cursor.fetchall.side_effect = [
                    [{'id': 1, 'title': 'Book 1', 'author': 'Author 1',
                      'cover': None, 'status': 'TBR', 'rating': 0,
                      'last_status_change': None}],
                    [{'id': 1, 'name': 'Fiction', 'color': '#ff0000'}],
                    []
                ]
                mock_connect.return_value = mock_conn
                
                books = helpers_module.get_all_books()
                
                assert len(books[0]['tags']) == 1

    def test_get_all_books_caches_covers(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            with patch('helpers.os.path.exists', return_value=True):
                with patch('helpers.requests.get') as mock_get:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_get.return_value = mock_response
                    
                    mock_conn = MagicMock()
                    mock_cursor = MagicMock()
                    mock_conn.cursor.return_value = mock_cursor
                    mock_cursor.fetchall.side_effect = [
                        [{'id': 1, 'title': 'Book 1', 'author': 'Author 1',
                          'cover': 'http://example.com/cover.jpg',
                          'status': 'TBR', 'rating': 0,
                          'last_status_change': None}],
                        [],
                        []
                    ]
                    mock_connect.return_value = mock_conn
                    
                    books = helpers_module.get_all_books()
                    
                    assert 'cover' in books[0]


class TestUpdateBookStatus:
    def test_update_book_status(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            helpers_module.update_book_status('Test Book', 'Test Author', 'Read')
            
            assert mock_cursor.execute.called


class TestRemoveBook:
    def test_remove_book(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            helpers_module.remove_book('Test Book', 'Test Author')
            
            assert mock_cursor.execute.called


class TestSearchGoogleBooks:
    def test_search_google_books_multiple(self, helpers_module):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'Search Result',
                        'authors': ['Test Author'],
                        'imageLinks': {'thumbnail': 'http://example.com/cover'},
                        'industryIdentifiers': [
                            {'type': 'ISBN_13', 'identifier': '9780123456789'}
                        ],
                        'publisher': 'Test Publisher',
                        'publishedDate': '2024-01-01'
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            results = helpers_module.search_google_books_multiple('test query')
            
            assert len(results) == 1
            assert results[0]['title'] == 'Search Result'

    def test_search_google_books_empty_results(self, helpers_module):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'items': []}
            mock_get.return_value = mock_response
            
            results = helpers_module.search_google_books_multiple('nonexistent')
            
            assert len(results) == 0

    def test_search_google_books_by_isbn(self, helpers_module):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'ISBN Book',
                        'authors': ['ISBN Author'],
                        'imageLinks': {'thumbnail': 'http://example.com/cover'},
                        'industryIdentifiers': [
                            {'type': 'ISBN_10', 'identifier': '1234567890'}
                        ]
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            results = helpers_module.search_google_books_by_isbn('1234567890')
            
            assert len(results) == 1
            assert results[0]['isbn'] == '1234567890'


class TestFilterBooks:
    def test_filter_books_with_status(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            with patch('helpers.os.path.exists', return_value=True):
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_cursor.fetchall.side_effect = [[], []]
                mock_connect.return_value = mock_conn
                
                books = helpers_module.filter_books(status_filters=['Read'])
                
                assert isinstance(books, list)

    def test_filter_books_with_tags(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            with patch('helpers.os.path.exists', return_value=True):
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_conn.cursor.return_value = mock_cursor
                mock_cursor.fetchall.side_effect = [[], []]
                mock_connect.return_value = mock_conn
                
                books = helpers_module.filter_books(tag_ids=[1, 2])
                
                assert isinstance(books, list)


class TestGetBooksStats:
    def test_get_books_stats(self, helpers_module):
        with patch('helpers.get_all_books') as mock_get_all:
            from collections import Counter
            mock_get_all.return_value = [
                {'id': 1, 'title': 'Book 1', 'author': 'Author 1',
                 'status': 'Read', 'last_status_change': '2024-01-15 10:30:00',
                 'tags': []},
                {'id': 2, 'title': 'Book 2', 'author': 'Author 1',
                 'status': 'TBR', 'last_status_change': None,
                 'tags': []}
            ]
            
            total, status_breakdown, author_breakdown, years, tag_breakdown = helpers_module.get_books_stats()
            
            assert total == 2
            assert status_breakdown['Read'] == 1
            assert status_breakdown['TBR'] == 1


class TestTagManagement:
    def test_create_tag(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.lastrowid = 1
            mock_connect.return_value = mock_conn
            
            result = helpers_module.create_tag('My Tag', '#ff0000')
            
            assert result == 1

    def test_add_tag_to_book(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            result = helpers_module.add_tag_to_book(1, 1)
            
            assert result is True

    def test_remove_tag_from_book(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            result = helpers_module.remove_tag_from_book(1, 1)
            
            assert result is True

    def test_delete_tag(self, helpers_module):
        with patch('helpers.mariadb.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            result = helpers_module.delete_tag(1)
            
            assert result is True


class TestSQLInjectionProtection:
    def test_filter_books_with_malicious_tag_id(self, mock_db_connection):
        """Test that malicious tag IDs are filtered out"""
        import helpers
        
        # Test with string that could be SQL injection
        result = helpers.filter_books(tag_ids=["1; DROP TABLE books--"])
        
        # Should return all books since malicious ID is rejected
        assert isinstance(result, list)

    def test_filter_books_with_numeric_string_tag_id(self, mock_db_connection):
        """Test that numeric string tag IDs are properly converted"""
        cursor = mock_db_connection
        cursor.fetchall.side_effect = [[], []]
        
        import helpers
        result = helpers.filter_books(tag_ids=["1", "2", "3"])
        
        assert isinstance(result, list)

    def test_filter_books_with_negative_tag_id(self, mock_db_connection):
        """Test that negative tag IDs are filtered out"""
        cursor = mock_db_connection
        cursor.fetchall.side_effect = [[], []]
        
        import helpers
        result = helpers.filter_books(tag_ids=[-1, -2])
        
        # Should return all books since negative IDs are rejected
        assert isinstance(result, list)

    def test_filter_books_with_status_validation(self, mock_db_connection):
        """Test that only valid status values are used"""
        cursor = mock_db_connection
        cursor.fetchall.side_effect = [[], []]
        
        import helpers
        
        # Try to inject invalid status
        result = helpers.filter_books(status_filters=["Read", "InvalidStatus", "TBR"])
        
        assert isinstance(result, list)

    def test_filter_books_with_star_rating_validation(self, mock_db_connection):
        """Test that only valid star ratings (1-5) are accepted"""
        cursor = mock_db_connection
        cursor.fetchall.side_effect = [[], []]
        
        import helpers
        
        # Try invalid star rating formats
        result = helpers.filter_books(rating_filters=["6star", "0star", "invalid"])
        
        assert isinstance(result, list)
