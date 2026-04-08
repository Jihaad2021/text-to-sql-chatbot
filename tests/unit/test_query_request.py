"""
Unit tests for QueryRequest Pydantic model validators.

Tests cover:
- Valid inputs are accepted
- Unknown database is rejected
- Empty / too-short question is rejected
- Whitespace-only question is rejected
- Question is stripped of leading/trailing whitespace
"""

import pytest
from pydantic import ValidationError

from src.main import QueryRequest

# ========================================
# Test: Valid inputs
# ========================================

class TestValidInputs:

    def test_valid_known_database(self):
        req = QueryRequest(question="berapa total customer?", database="sales_db")
        assert req.database == "sales_db"

    def test_all_allowed_databases_accepted(self):
        for db in ("sales_db", "products_db", "analytics_db"):
            req = QueryRequest(question="berapa total data?", database=db)
            assert req.database == db

    def test_default_database_is_sales_db(self):
        req = QueryRequest(question="berapa total customer?")
        assert req.database == "sales_db"

    def test_question_is_stripped(self):
        req = QueryRequest(question="  berapa total customer?  ", database="sales_db")
        assert req.question == "berapa total customer?"

    def test_minimum_length_question_accepted(self):
        req = QueryRequest(question="abc", database="sales_db")
        assert req.question == "abc"


# ========================================
# Test: Invalid database
# ========================================

class TestInvalidDatabase:

    def test_unknown_database_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="berapa total customer?", database="unknown_db")
        assert "Unknown database" in str(exc_info.value)

    def test_empty_database_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="berapa total customer?", database="")

    def test_sql_injection_in_database_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="test", database="sales_db; DROP TABLE users;")


# ========================================
# Test: Invalid question
# ========================================

class TestInvalidQuestion:

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            QueryRequest(question="", database="sales_db")
        assert "3 characters" in str(exc_info.value)

    def test_whitespace_only_question_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="   ", database="sales_db")

    def test_one_char_question_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="a", database="sales_db")

    def test_two_char_question_rejected(self):
        with pytest.raises(ValidationError):
            QueryRequest(question="ab", database="sales_db")
