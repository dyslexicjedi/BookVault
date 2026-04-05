import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['BOOKVAULT_DBUSER'] = 'testuser'
os.environ['BOOKVAULT_DBPASS'] = 'testpass'
os.environ['BOOKVAULT_DBHOST'] = 'localhost'
os.environ['BOOKVAULT_DBPORT'] = '3306'
os.environ['BOOKVAULT_DBNAME'] = 'test_db'


@pytest.fixture
def mock_db_connection():
    with patch('helpers.mariadb.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 1
        
        mock_connect.return_value = mock_conn
        
        yield mock_cursor


@pytest.fixture  
def app(mock_db_connection):
    from app import app
    
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['DEBUG'] = False
    
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mocked_google_books():
    with patch('helpers.requests.get') as mock_get:
        yield mock_get
