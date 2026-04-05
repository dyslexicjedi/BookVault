import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestGoogleBooksSearch:
    def test_successful_title_author_search(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'The Great Gatsby',
                        'authors': ['F. Scott Fitzgerald'],
                        'imageLinks': {'thumbnail': 'http://example.com/cover'},
                        'industryIdentifiers': [
                            {'type': 'ISBN_13', 'identifier': '9780743273565'}
                        ],
                        'publisher': 'Scribner',
                        'publishedDate': '1925-04-10'
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_multiple('Gatsby Fitzgerald')
            
            assert len(results) == 1

    def test_search_with_missing_image(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'Book Without Cover',
                        'authors': ['Unknown Author'],
                        'industryIdentifiers': []
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_multiple('test')
            
            assert len(results) == 1
            assert 'placeholder' in results[0]['cover']

    def test_search_with_empty_isbn(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'Book',
                        'authors': ['Author'],
                        'industryIdentifiers': []
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_multiple('test')
            
            assert len(results) == 1

    def test_search_api_error(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_multiple('test')
            
            assert len(results) == 0

    def test_search_no_items_in_response(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_multiple('test')
            
            assert len(results) == 0


class TestISBNSearch:
    def test_valid_isbn_lookup(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'ISBN Book',
                        'authors': ['Author'],
                        'imageLinks': {'thumbnail': 'http://example.com/cover'},
                        'industryIdentifiers': [
                            {'type': 'ISBN_10', 'identifier': '1234567890'}
                        ]
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_by_isbn('1234567890')
            
            assert len(results) == 1

    def test_invalid_isbn_format(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'items': []}
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_by_isbn('invalid-isbn')
            
            assert len(results) == 0


class TestSeriesExtraction:
    def test_extract_series_from_subtitle(self):
        with patch('helpers.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'items': [{
                    'volumeInfo': {
                        'title': 'Book',
                        'subtitle': 'Harry Potter and the Sorcerer\'s Stone',
                        'authors': ['Author'],
                        'imageLinks': {'thumbnail': 'http://example.com/cover'}
                    }
                }]
            }
            mock_get.return_value = mock_response
            
            import helpers
            results = helpers.search_google_books_multiple('test')
            
            assert results[0]['series'] == "Harry Potter and the Sorcerer's Stone"
