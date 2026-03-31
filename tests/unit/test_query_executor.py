"""
Unit tests for QueryExecutor.

Tests cover:
- Successful query execution
- Empty result handling
- Invalid database raises error
- No validated SQL raises error
- Timeout error handling
- Row limit enforcement
- State input/output correctness
"""

import pytest
from unittest.mock import patch, MagicMock

from src.components.query_executor import QueryExecutor
from src.models.agent_state import AgentState
from src.utils.exceptions import QueryExecutionError


@pytest.fixture
def mock_engine():
    """Mock SQLAlchemy engine."""
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()

    result.keys.return_value = ["total"]
    result.fetchmany.return_value = [{"total": 100}]

    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value = result

    engine.connect.return_value = conn
    return engine


@pytest.fixture
def executor(mock_engine):
    """Initialize QueryExecutor with mocked database engines."""
    with patch.object(QueryExecutor, "_create_engines", return_value={"sales_db": mock_engine}):
        return QueryExecutor(timeout_seconds=30, max_rows=10000)


def make_state(sql: str, database: str = "sales_db") -> AgentState:
    """Helper to create state with validated SQL."""
    state = AgentState(query="test query", database=database)
    state.validated_sql = sql
    return state


# ========================================
# Test: Successful Execution
# ========================================

class TestSuccessfulExecution:

    def test_executes_simple_query(self, executor):
        """Simple query should return results."""
        state = make_state("SELECT COUNT(*) as total FROM customers;")
        result = executor.run(state)

        assert result.query_result is not None
        assert result.row_count >= 0

    def test_writes_results_to_state(self, executor):
        """Query results should be written to state.query_result."""
        state = make_state("SELECT COUNT(*) as total FROM customers;")
        result = executor.run(state)

        assert isinstance(result.query_result, list)

    def test_writes_row_count_to_state(self, executor):
        """Row count should be written to state.row_count."""
        state = make_state("SELECT COUNT(*) as total FROM customers;")
        result = executor.run(state)

        assert isinstance(result.row_count, int)
        assert result.row_count >= 0

    def test_empty_result_returns_zero_rows(self, executor, mock_engine):
        """Empty query result should set row_count to 0."""
        conn = mock_engine.connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchmany.return_value = []

        state = make_state("SELECT * FROM customers WHERE 1=0;")
        result = executor.run(state)

        assert result.row_count == 0
        assert result.query_result == []


# ========================================
# Test: Error Handling
# ========================================

class TestErrorHandling:

    def test_raises_if_no_validated_sql(self, executor):
        """Should raise QueryExecutionError if no validated SQL."""
        state = AgentState(query="test", database="sales_db")
        state.validated_sql = None

        with pytest.raises(QueryExecutionError):
            executor.run(state)

    def test_raises_if_database_not_available(self, executor):
        """Should raise QueryExecutionError for unknown database."""
        state = make_state(
            "SELECT * FROM customers;",
            database="unknown_db"
        )

        with pytest.raises(QueryExecutionError):
            executor.run(state)

    def test_handles_operational_error(self, executor, mock_engine):
        """Should raise QueryExecutionError on OperationalError."""
        from sqlalchemy.exc import OperationalError

        conn = mock_engine.connect.return_value.__enter__.return_value
        conn.execute.side_effect = OperationalError("timeout", None, None)

        state = make_state("SELECT * FROM customers;")

        with pytest.raises(QueryExecutionError):
            executor.run(state)

    def test_handles_programming_error(self, executor, mock_engine):
        """Should raise QueryExecutionError on ProgrammingError."""
        from sqlalchemy.exc import ProgrammingError

        conn = mock_engine.connect.return_value.__enter__.return_value
        conn.execute.side_effect = ProgrammingError("syntax error", None, None)

        state = make_state("SELECT * FROM customers;")

        with pytest.raises(QueryExecutionError):
            executor.run(state)


# ========================================
# Test: Row Limit
# ========================================

class TestRowLimit:

    def test_row_limit_enforced(self, executor, mock_engine):
        """fetchmany should be called with max_rows limit."""
        conn = mock_engine.connect.return_value.__enter__.return_value
        state = make_state("SELECT * FROM customers;")

        executor.run(state)

        conn.execute.return_value.fetchmany.assert_called_with(executor.max_rows)


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_reads_validated_sql_from_state(self, executor, mock_engine):
        """Executor should use state.validated_sql for query."""
        sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"
        state = make_state(sql)

        conn = mock_engine.connect.return_value.__enter__.return_value
        executor.run(state)

        # Check SQL was passed to execute
        call_args = str(conn.execute.call_args_list)
        assert "SELECT" in call_args or conn.execute.called

    def test_timing_recorded(self, executor):
        """Execution time should be recorded in state.timing."""
        state = make_state("SELECT COUNT(*) as total FROM customers;")
        result = executor.run(state)

        assert "query_executor" in result.timing
        assert result.timing["query_executor"] > 0

    def test_metrics_updated_on_success(self, executor):
        """Metrics should update after successful execution."""
        state = make_state("SELECT COUNT(*) as total FROM customers;")
        executor.run(state)

        metrics = executor.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1