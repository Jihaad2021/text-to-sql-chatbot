"""
Unit tests for RetrievalEvaluator.

Tests cover:
- Skip evaluation if <= 2 tables
- Essential/optional/excluded classification
- Fallback if parse fails
- All relevant tables written to state.evaluated_tables
- State input/output correctness
"""

from unittest.mock import MagicMock, patch

import pytest

from src.components.retrieval_evaluator import RetrievalEvaluator
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
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Needed for transaction count

OPTIONAL:

EXCLUDED:
- financial_db.financial_internal: Not needed
- financial_db.product_summary: Not needed"""

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
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Required for transaction count

OPTIONAL:

EXCLUDED:
- financial_db.financial_internal: Not needed
- financial_db.product_summary: Not needed"""

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names

    def test_optional_tables_included(self, evaluator, sample_tables):
        """Optional tables should also be in evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Required

OPTIONAL:
- financial_db.financial_internal: Provides revenue context

EXCLUDED:
- financial_db.product_summary: Not needed"""

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        table_names = [t.table_name for t in result.evaluated_tables]
        assert "daily_master" in table_names
        assert "financial_internal" in table_names

    def test_excluded_tables_not_included(self, evaluator, sample_tables):
        """Excluded tables should NOT be in evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Required

OPTIONAL:

EXCLUDED:
- financial_db.financial_internal: Not needed
- financial_db.product_summary: Not needed"""

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
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Transaction data needed
- financial_db.financial_internal: Revenue data needed
- financial_db.product_summary: Product breakdown needed

OPTIONAL:

EXCLUDED:"""

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        assert len(result.evaluated_tables) == 3


# ========================================
# Test: Fallback
# ========================================

class TestFallback:

    def test_fallback_if_parse_fails(self, evaluator, sample_tables):
        """Should use all tables if response cannot be parsed."""
        state = make_state_with_tables(sample_tables)
        mock_response = "This is an unparseable response with no format."

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        assert len(result.evaluated_tables) == len(sample_tables)


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_reads_retrieved_tables_from_state(self, evaluator, sample_tables):
        """Evaluator should read from state.retrieved_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Required

OPTIONAL:

EXCLUDED:
- financial_db.financial_internal: Not needed
- financial_db.product_summary: Not needed"""

        with patch.object(evaluator, "_call_llm", return_value=mock_response):
            result = evaluator.run(state)

        assert result.evaluated_tables is not None

    def test_writes_to_evaluated_tables(self, evaluator, sample_tables):
        """Evaluator should write to state.evaluated_tables."""
        state = make_state_with_tables(sample_tables)
        mock_response = """ESSENTIAL:
- financial_db.daily_master: Required

OPTIONAL:

EXCLUDED:
- financial_db.financial_internal: Not needed
- financial_db.product_summary: Not needed"""

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
