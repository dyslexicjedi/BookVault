# Test Suite

This directory contains unit and integration tests for the BookVault application.

## Running Tests

```bash
# Install test dependencies
pip install -r test_requirements.txt

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=helpers --cov-report=html

# Run specific test file
pytest tests/test_helpers.py -v

# Run specific test class
pytest tests/test_helpers.py::TestInsertBook -v
```

## Test Structure

- `test_helpers.py` - Unit tests for helper functions (database operations, Google Books API calls)
- `test_search.py` - Tests for search functionality (Google Books API integration)

## Coverage Targets

- Database functions: 100%
- Search functions: 100%
- Book management functions: 95%

## CI/CD

Tests are automatically run on push and pull requests via GitHub Actions.
