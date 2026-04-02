"""
Unit tests for SQLGenerator.

Tests cover:
- SQL generation from query and tables
- Intent strategy hint used in prompt
- Empty evaluated_tables raises error
- SQL cleaning (markdown removal)
- State input/output correctness
"""

import pytest
from unittest.mock import patch, MagicMock

from src.components.sql_generator import SQLGenerator
from src.models.agent_state import AgentState
from src.utils.exceptions import SQLGenerationError


@pytest.fixture
def generator():
    """Initialize SQLGenerator with mocked LLM client."""
    with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        with patch("builtins.open", side_effect=FileNotFoundError):
            return SQLGenerator()


# ========================================
# Test: SQL Generation
# ========================================

class TestSQLGeneration:

    def test_generates_sql_from_query(self, generator, state_with_tables):
        """Should generate SQL and write to state.sql."""
        mock_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql):
            state = generator.run(state_with_tables)

        assert state.sql is not None
        assert "SELECT" in state.sql.upper()

    def test_aggregation_query_generates_count(self, generator, state_with_tables):
        """Aggregation query should generate COUNT SQL."""
        mock_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql):
            state = generator.run(state_with_tables)

        assert "COUNT" in state.sql.upper()

    def test_join_query_generates_join_sql(self, generator, state_with_tables):
        """Join query should generate SQL with JOIN."""
        state_with_tables.query = "top 5 customers by spending"
        state_with_tables.intent = {
            "category": "multi_table_join",
            "confidence": 0.90,
            "reason": "Needs JOIN",
            "sql_strategy": "Use JOIN across relevant tables"
        }
        mock_sql = """SELECT c.customer_name, SUM(p.payment_value) as total
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN payments p ON o.order_id = p.order_id
GROUP BY c.customer_name
ORDER BY total DESC
LIMIT 5;"""

        with patch.object(generator, "_call_llm", return_value=mock_sql):
            state = generator.run(state_with_tables)

        assert "JOIN" in state.sql.upper()


# ========================================
# Test: SQL Cleaning
# ========================================

class TestSQLCleaning:

    def test_removes_markdown_sql_block(self, generator, state_with_tables):
        """Should remove ```sql markdown from response."""
        mock_response = "```sql\nSELECT COUNT(*) FROM customers LIMIT 100;\n```"

        with patch.object(generator, "_call_llm", return_value=mock_response):
            state = generator.run(state_with_tables)

        assert "```" not in state.sql

    def test_removes_plain_markdown_block(self, generator, state_with_tables):
        """Should remove ``` markdown from response."""
        mock_response = "```\nSELECT COUNT(*) FROM customers LIMIT 100;\n```"

        with patch.object(generator, "_call_llm", return_value=mock_response):
            state = generator.run(state_with_tables)

        assert "```" not in state.sql


# ========================================
# Test: Intent Strategy in Prompt
# ========================================

class TestIntentStrategy:

    def test_intent_strategy_included_in_prompt(self, generator, state_with_tables):
        """Intent sql_strategy should be included in LLM prompt."""
        mock_sql = "SELECT COUNT(*) FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql) as mock_llm:
            generator.run(state_with_tables)
            prompt = mock_llm.call_args[0][0]

        assert state_with_tables.intent["sql_strategy"] in prompt

    def test_table_schema_included_in_prompt(self, generator, state_with_tables):
        """Table names should be included in LLM prompt."""
        mock_sql = "SELECT COUNT(*) FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql) as mock_llm:
            generator.run(state_with_tables)
            prompt = mock_llm.call_args[0][0]

        assert "customers" in prompt


# ========================================
# Test: Error Handling
# ========================================

class TestErrorHandling:

    def test_raises_if_no_evaluated_tables(self, generator, state_with_intent):
        """Should raise SQLGenerationError if no evaluated tables."""
        state_with_intent.evaluated_tables = []

        with pytest.raises(SQLGenerationError):
            generator.run(state_with_intent)

    def test_raises_if_llm_returns_empty(self, generator, state_with_tables):
        """Should raise SQLGenerationError if LLM returns empty string."""
        with patch.object(generator, "_call_llm", return_value=""):
            with pytest.raises(SQLGenerationError):
                generator.run(state_with_tables)


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_writes_sql_to_state(self, generator, state_with_tables):
        """Generated SQL should be written to state.sql."""
        mock_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql):
            state = generator.run(state_with_tables)

        assert state.sql == mock_sql

    def test_timing_recorded(self, generator, state_with_tables):
        """Execution time should be recorded in state.timing."""
        mock_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql):
            state = generator.run(state_with_tables)

        assert "sql_generator" in state.timing
        assert state.timing["sql_generator"] > 0

    def test_metrics_updated_on_success(self, generator, state_with_tables):
        """Metrics should update after successful execution."""
        mock_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"

        with patch.object(generator, "_call_llm", return_value=mock_sql):
            generator.run(state_with_tables)

        metrics = generator.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
