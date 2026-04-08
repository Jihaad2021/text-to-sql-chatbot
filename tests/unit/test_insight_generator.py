"""
Unit tests for InsightGenerator.

Tests cover:
- Insight generation from query results
- Empty results handled gracefully
- Fallback if LLM fails
- Indonesian language output
- State input/output correctness
"""

from unittest.mock import MagicMock, patch

import pytest

from src.components.insight_generator import InsightGenerator
from src.models.agent_state import AgentState
from src.utils.exceptions import InsightGenerationError


@pytest.fixture
def generator():
    """Initialize InsightGenerator with mocked Anthropic client."""
    with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return InsightGenerator()


# ========================================
# Test: Insight Generation
# ========================================

class TestInsightGeneration:

    def test_generates_insights_from_results(self, generator, state_with_results):
        """Should generate insights and write to state.insights."""
        mock_insight = "Terdapat 100 customer yang terdaftar dalam sistem."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_results)

        assert state.insights is not None
        assert len(state.insights) > 0

    def test_insights_written_to_state(self, generator, state_with_results):
        """Insights should be written to state.insights."""
        mock_insight = "Terdapat 100 customer yang terdaftar dalam sistem."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_results)

        assert state.insights == mock_insight

    def test_query_included_in_prompt(self, generator, state_with_results):
        """User query should be included in LLM prompt."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight) as mock_llm:
            generator.run(state_with_results)
            prompt = mock_llm.call_args[0][0]

        assert state_with_results.query in prompt

    def test_results_included_in_prompt(self, generator, state_with_results):
        """Query results should be included in LLM prompt."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight) as mock_llm:
            generator.run(state_with_results)
            prompt = mock_llm.call_args[0][0]

        assert "100" in prompt


# ========================================
# Test: Empty Results
# ========================================

class TestEmptyResults:

    def test_handles_empty_results_gracefully(self, generator, state_with_sql):
        """Should handle empty results without raising error."""
        state_with_sql.query_result = []
        state_with_sql.row_count = 0

        mock_insight = "Tidak ada data yang ditemukan untuk query ini."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_sql)

        assert state.insights is not None

    def test_empty_results_mentioned_in_prompt(self, generator, state_with_sql):
        """Prompt should indicate 0 rows for empty results."""
        state_with_sql.query_result = []
        state_with_sql.row_count = 0

        mock_insight = "Tidak ada data."

        with patch.object(generator, "_call_llm", return_value=mock_insight) as mock_llm:
            generator.run(state_with_sql)
            prompt = mock_llm.call_args[0][0]

        assert "0" in prompt


# ========================================
# Test: Fallback
# ========================================

class TestFallback:

    def test_fallback_if_llm_fails(self, generator, state_with_results):
        """Should use fallback insight if LLM call fails."""
        with patch.object(generator, "_call_llm", side_effect=Exception("LLM error")):
            state = generator.run(state_with_results)

        assert state.insights is not None
        assert len(state.insights) > 0

    def test_fallback_single_value_result(self, generator):
        """Fallback should format single value result."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state.validated_sql = "SELECT COUNT(*) as total FROM customers;"
        state.query_result = [{"total": 100}]
        state.row_count = 1

        with patch.object(generator, "_call_llm", side_effect=Exception("LLM error")):
            state = generator.run(state)

        assert "100" in state.insights

    def test_fallback_empty_result(self, generator):
        """Fallback should handle empty results."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state.validated_sql = "SELECT COUNT(*) as total FROM customers;"
        state.query_result = []
        state.row_count = 0

        with patch.object(generator, "_call_llm", side_effect=Exception("LLM error")):
            state = generator.run(state)

        assert state.insights is not None


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_timing_recorded(self, generator, state_with_results):
        """Execution time should be recorded in state.timing."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_results)

        assert "insight_generator" in state.timing
        assert state.timing["insight_generator"] > 0

    def test_metrics_updated_on_success(self, generator, state_with_results):
        """Metrics should update after successful execution."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            generator.run(state_with_results)

        metrics = generator.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
