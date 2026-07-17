"""
Unit tests for RetrievalEvaluator (v2 — JSON output).

Tests cover:
- Skip evaluation if <= 2 tables
- Essential / optional / excluded classification via JSON response
- Fallback on malformed JSON, empty result, or unknown table names
- Markdown fence stripping
- Unknown category values ignored gracefully
- All relevant tables written to state.evaluated_tables
- State input/output correctness
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.retrieval_evaluator import RetrievalEvaluator
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable


@pytest.fixture
def evaluator():
    """Initialize RetrievalEvaluator with mocked LLM client."""
    with patch.object(RetrievalEvaluator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return RetrievalEvaluator()


def make_state_with_tables(tables: list, query: str = "berapa total transaksi bulan April 2026?") -> AgentState:
    """Helper to create state with retrieved tables."""
    state = AgentState(query=query, database="financial_db")
    state.retrieved_tables = tables
    return state


def _json_response(entries: list[dict]) -> str:
    """Build a well-formed JSON response string as the LLM would return."""
    return json.dumps({"tables": entries})


# ========================================
# Test: Skip Evaluation
# ========================================

class TestSkipEvaluation:

    def test_skip_if_one_table(self, evaluator, daily_master_table):
        """Should skip evaluation if only 1 table retrieved."""
        state = make_state_with_tables([daily_master_table])

        with patch.object(evaluator, "_call_llm") as mock_llm:
            result = evaluator.run(state)
            mock_llm.assert_not_called()

        assert result.evaluated_tables == [daily_master_table]

    def test_skip_if_two_tables(self, evaluator, daily_master_table, financial_internal_table):
        """Should skip evaluation if only 2 tables retrieved."""
        state = make_state_with_tables([daily_master_table, financial_internal_table])

        with patch.object(evaluator, "_call_llm") as mock_llm:
            result = evaluator.run(state)
            mock_llm.assert_not_called()

        assert len(result.evaluated_tables) == 2

    def test_evaluate_if_three_or_more_tables(self, evaluator, sample_tables):
        """Should call LLM if 3 or more tables retrieved."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Needed"},
            {"name": "financial_db.financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response) as mock_llm:
            evaluator.run(state)
            mock_llm.assert_called_once()


# ========================================
# Test: Classification
# ========================================

class TestClassification:

    def test_essential_tables_included(self, evaluator, sample_tables):
        """Essential tables should be in evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required for transaction count"},
            {"name": "financial_db.financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names

    def test_optional_tables_included(self, evaluator, sample_tables):
        """Optional tables should also appear in evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_db.financial_internal", "category": "OPTIONAL", "reason": "Provides revenue context"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names
        assert "financial_internal" in table_names

    def test_excluded_tables_not_included(self, evaluator, sample_tables):
        """Excluded tables should NOT appear in evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_db.financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "financial_internal" not in table_names
        assert "product_summary" not in table_names

    def test_all_tables_essential_for_join_query(self, evaluator, sample_tables):
        """Join query should mark all tables as essential."""
        state = make_state_with_tables(
            sample_tables,
            query="top 5 partner berdasarkan revenue bulan April 2026"
        )
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Transaction data"},
            {"name": "financial_db.financial_internal", "category": "ESSENTIAL", "reason": "Revenue data"},
            {"name": "financial_db.product_summary", "category": "ESSENTIAL", "reason": "Product breakdown"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        assert len(result.evaluated_tables) == 3

    def test_table_name_matched_by_short_name(self, evaluator, sample_tables):
        """Parser should match table_name without db prefix."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names


# ========================================
# Test: JSON Robustness
# ========================================

class TestJsonRobustness:

    def test_strips_markdown_fences(self, evaluator, sample_tables):
        """Parser should handle responses wrapped in ```json ... ``` fences."""
        state = make_state_with_tables(sample_tables)
        payload = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_db.financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])
        mock_response = f"```json\n{payload}\n```"

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        assert any(t.table_name == "daily_master" for t in result.evaluated_tables)

    def test_unknown_category_skipped(self, evaluator, sample_tables):
        """Entries with unrecognised category values should be silently skipped."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_db.financial_internal", "category": "MAYBE", "reason": "Unknown"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names
        assert "financial_internal" not in table_names

    def test_unknown_table_name_skipped(self, evaluator, sample_tables):
        """Entries whose table name is not in the retrieved set should be ignored."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_db.ghost_table", "category": "ESSENTIAL", "reason": "Does not exist"},
            {"name": "financial_db.financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names
        assert "ghost_table" not in table_names

    def test_fallback_on_malformed_json(self, evaluator, sample_tables):
        """Should fall back to all-essential when LLM returns non-JSON text."""
        state = make_state_with_tables(sample_tables)

        with patch.object(evaluator, "_call_llm", return_value="This is not JSON at all."):
            result = evaluator.run(state)

        assert len(result.evaluated_tables) == len(sample_tables)

    def test_fallback_on_empty_tables_array(self, evaluator, sample_tables):
        """Should fall back when JSON is valid but tables array is empty."""
        state = make_state_with_tables(sample_tables)

        with patch.object(evaluator, "_call_llm", return_value='{"tables": []}'):
            result = evaluator.run(state)

        assert len(result.evaluated_tables) == len(sample_tables)

    def test_fallback_on_missing_tables_key(self, evaluator, sample_tables):
        """Should fall back when JSON has no 'tables' key."""
        state = make_state_with_tables(sample_tables)

        with patch.object(evaluator, "_call_llm", return_value='{"result": []}'):
            result = evaluator.run(state)

        assert len(result.evaluated_tables) == len(sample_tables)


# ========================================
# Test: Fallback when all DB-filtered tables drop out
# ========================================

class TestDatabaseFilter:

    def test_fallback_when_no_tables_match_database(self, evaluator, sample_tables):
        """When all relevant tables are from a different DB, fall back to all retrieved."""
        state = make_state_with_tables(sample_tables)
        # LLM returns tables from a different DB
        mock_response = _json_response([
            {"name": "other_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        # Fallback: all retrieved tables for financial_db
        assert len(result.evaluated_tables) == len(sample_tables)


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_writes_to_evaluated_tables(self, evaluator, sample_tables):
        """Evaluator should write to state.evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = _json_response([
            {"name": "financial_db.daily_master", "category": "ESSENTIAL", "reason": "Required"},
            {"name": "financial_db.financial_internal", "category": "EXCLUDED", "reason": "Not needed"},
            {"name": "financial_db.product_summary", "category": "EXCLUDED", "reason": "Not needed"},
        ])

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        assert hasattr(result, "evaluated_tables")
        assert isinstance(result.evaluated_tables, list)

    def test_timing_recorded(self, evaluator, daily_master_table):
        """Execution time should be recorded in state.timing."""
        state = make_state_with_tables([daily_master_table])
        result = evaluator.run(state)

        assert "retrieval_evaluator" in result.timing
        assert result.timing["retrieval_evaluator"] > 0
