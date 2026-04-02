"""
Unit tests for SQLValidator.

Tests cover:
- Valid SQL passes all layers
- Security validation (dangerous keywords, injection)
- Syntax validation
- Table whitelist validation
- Auto-fix with AI (mocked)
- State input/output correctness
"""

import pytest
from unittest.mock import patch, MagicMock

from src.components.sql_validator import SQLValidator
from src.models.agent_state import AgentState
from src.utils.exceptions import SQLValidationError


@pytest.fixture
def validator():
    """Initialize SQLValidator with AI validation disabled."""
    with patch.object(SQLValidator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return SQLValidator(enable_ai_validation=False)

@pytest.fixture
def validator_with_ai():
    """Initialize SQLValidator with AI validation enabled."""
    with patch.object(SQLValidator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return SQLValidator(enable_ai_validation=True)

def make_state(sql: str, query: str = "test query") -> AgentState:
    """Helper to create state with SQL."""
    state = AgentState(query=query, database="sales_db")
    state.sql = sql
    return state


# ========================================
# Test: Valid SQL
# ========================================

class TestValidSQL:

    def test_simple_select_passes(self, validator):
        """Simple SELECT query should pass validation."""
        state = make_state("SELECT * FROM customers LIMIT 10;")
        result = validator.run(state)
        assert result.validated_sql is not None

    def test_aggregation_passes(self, validator):
        """Aggregation query should pass validation."""
        state = make_state("SELECT COUNT(*) as total FROM customers;")
        result = validator.run(state)
        assert result.validated_sql is not None

    def test_join_query_passes(self, validator):
        """JOIN query with whitelisted tables should pass."""
        sql = """SELECT c.customer_name, COUNT(o.order_id) as total_orders
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_name
LIMIT 10;"""
        state = make_state(sql)
        result = validator.run(state)
        assert result.validated_sql is not None

    def test_validated_sql_written_to_state(self, validator):
        """Validated SQL should be written to state.validated_sql."""
        state = make_state("SELECT * FROM customers LIMIT 10;")
        result = validator.run(state)
        assert result.validated_sql == "SELECT * FROM customers LIMIT 10;"


# ========================================
# Test: Security Validation
# ========================================

class TestSecurityValidation:

    def test_drop_table_blocked(self, validator):
        """DROP TABLE should be blocked."""
        state = make_state("DROP TABLE customers;")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_delete_blocked(self, validator):
        """DELETE statement should be blocked."""
        state = make_state("DELETE FROM customers WHERE customer_id = 1;")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_insert_blocked(self, validator):
        """INSERT statement should be blocked."""
        state = make_state("INSERT INTO customers VALUES (1, 'test');")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_update_blocked(self, validator):
        """UPDATE statement should be blocked."""
        state = make_state("UPDATE customers SET customer_name = 'x';")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_sql_injection_blocked(self, validator):
        """SQL injection via multiple statements should be blocked."""
        state = make_state("SELECT * FROM customers; DROP TABLE orders;")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_comment_injection_blocked(self, validator):
        """SQL comments should be blocked."""
        state = make_state("SELECT * FROM customers -- WHERE 1=1")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_non_select_blocked(self, validator):
        """Non-SELECT queries should be blocked."""
        state = make_state("TRUNCATE TABLE customers;")
        with pytest.raises(SQLValidationError):
            validator.run(state)


# ========================================
# Test: Table Whitelist
# ========================================

class TestTableWhitelist:

    def test_whitelisted_table_passes(self, validator):
        """Known table should pass whitelist check."""
        state = make_state("SELECT * FROM customers LIMIT 10;")
        result = validator.run(state)
        assert result.validated_sql is not None

    def test_unknown_table_blocked(self, validator):
        """Unknown table should be blocked."""
        state = make_state("SELECT * FROM unknown_table LIMIT 10;")
        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_all_whitelisted_tables_pass(self, validator):
        """All tables in whitelist should pass."""
        whitelisted = [
            "customers", "orders", "payments",
            "products", "sellers", "order_items"
        ]
        for table in whitelisted:
            state = make_state(f"SELECT * FROM {table} LIMIT 10;")
            result = validator.run(state)
            assert result.validated_sql is not None


# ========================================
# Test: Auto-fix with AI
# ========================================

class TestAutoFix:

    def test_autofix_applied_when_possible(self, validator_with_ai):
        """Auto-fix should be attempted on invalid SQL."""
        invalid_sql = "SELECT * FROM unknown_table LIMIT 10;"
        fixed_sql = "SELECT * FROM customers LIMIT 10;"

        state = make_state(invalid_sql, query="show customers")

        with patch.object(validator_with_ai, "_auto_fix", return_value=fixed_sql):
            result = validator_with_ai.run(state)

        assert result.validated_sql == fixed_sql

    def test_raises_if_autofix_fails(self, validator_with_ai):
        """Should raise SQLValidationError if auto-fix also fails."""
        invalid_sql = "SELECT * FROM unknown_table LIMIT 10;"

        state = make_state(invalid_sql, query="show data")

        with patch.object(validator_with_ai, "_auto_fix", return_value=""):
            with pytest.raises(SQLValidationError):
                validator_with_ai.run(state)


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_raises_if_no_sql_in_state(self, validator):
        """Should raise if state.sql is empty."""
        state = AgentState(query="test", database="sales_db")
        state.sql = None

        with pytest.raises(SQLValidationError):
            validator.run(state)

    def test_timing_recorded(self, validator):
        """Execution time should be recorded in state.timing."""
        state = make_state("SELECT * FROM customers LIMIT 10;")
        result = validator.run(state)
        assert "sql_validator" in result.timing
        assert result.timing["sql_validator"] > 0
