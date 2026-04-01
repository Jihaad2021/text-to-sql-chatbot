"""
Unit tests for IntentClassifier.

Tests cover:
- Clear query classification (aggregation, simple_select, etc.)
- Ambiguous query detection
- Low confidence handling
- State input/output correctness
- LLM call is mocked (no real API calls)
"""

import pytest
from unittest.mock import patch, MagicMock

from src.components.intent_classifier import IntentClassifier, INTENT_CATEGORIES
from src.models.agent_state import AgentState


@pytest.fixture
def classifier():
    """Initialize IntentClassifier with mocked Anthropic client."""
    with patch.object(IntentClassifier, "_init_client", return_value=("openai", MagicMock())):
        return IntentClassifier()

# ========================================
# Test: Clear Intent Classification
# ========================================

class TestClearIntents:

    def test_aggregation_intent(self, classifier, sample_state):
        """Query asking for count/total should be classified as aggregation."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Query asks for count"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(sample_state)

        assert state.intent["category"] == "aggregation"
        assert state.intent["confidence"] == 0.95
        assert state.needs_clarification is False

    def test_simple_select_intent(self, classifier):
        """Query asking to show all data should be simple_select."""
        state = AgentState(query="show all customers", database="sales_db")
        mock_response = "INTENT: simple_select\nCONFIDENCE: 0.95\nREASON: Basic retrieval"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(state)

        assert state.intent["category"] == "simple_select"
        assert state.needs_clarification is False

    def test_filtered_query_intent(self, classifier):
        """Query with specific filter should be filtered_query."""
        state = AgentState(query="customers from Jakarta", database="sales_db")
        mock_response = "INTENT: filtered_query\nCONFIDENCE: 0.95\nREASON: Has location filter"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(state)

        assert state.intent["category"] == "filtered_query"
        assert state.needs_clarification is False

    def test_multi_table_join_intent(self, classifier, join_state):
        """Query requiring multiple tables should be multi_table_join."""
        mock_response = "INTENT: multi_table_join\nCONFIDENCE: 0.90\nREASON: Needs JOIN"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(join_state)

        assert state.intent["category"] == "multi_table_join"
        assert state.needs_clarification is False

    def test_complex_analytics_intent(self, classifier):
        """Query for trends/analytics should be complex_analytics."""
        state = AgentState(query="monthly revenue trend", database="sales_db")
        mock_response = "INTENT: complex_analytics\nCONFIDENCE: 0.95\nREASON: Trend analysis"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(state)

        assert state.intent["category"] == "complex_analytics"
        assert state.needs_clarification is False


# ========================================
# Test: Ambiguous Queries
# ========================================

class TestAmbiguousIntents:

    def test_vague_query_is_ambiguous(self, classifier, ambiguous_state):
        """Vague query should be classified as ambiguous."""
        mock_response = "INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Too vague"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(ambiguous_state)

        assert state.intent["category"] == "ambiguous"
        assert state.needs_clarification is True
        assert state.clarification_reason is not None

    def test_low_confidence_forces_ambiguous(self, classifier, sample_state):
        """Low confidence should force ambiguous regardless of category."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.5\nREASON: Uncertain"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(sample_state)

        assert state.intent["category"] == "ambiguous"
        assert state.needs_clarification is True

    def test_unknown_category_falls_back_to_ambiguous(self, classifier, sample_state):
        """Unknown intent category should fall back to ambiguous."""
        mock_response = "INTENT: unknown_category\nCONFIDENCE: 0.9\nREASON: Something"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(sample_state)

        assert state.intent["category"] == "ambiguous"
        assert state.needs_clarification is True


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_reads_from_state_query(self, classifier, sample_state):
        """Classifier should read query from state.query."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count query"

        with patch.object(classifier, "_call_llm", return_value=mock_response) as mock_llm:
            classifier.run(sample_state)
            call_args = mock_llm.call_args[0][0]
            assert sample_state.query in call_args

    def test_writes_intent_to_state(self, classifier, sample_state):
        """Classifier should write intent dict to state.intent."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count query"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(sample_state)

        assert state.intent is not None
        assert "category" in state.intent
        assert "confidence" in state.intent
        assert "reason" in state.intent
        assert "sql_strategy" in state.intent

    def test_sql_strategy_present_in_intent(self, classifier, sample_state):
        """Intent should include sql_strategy for SQL Generator."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count query"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(sample_state)

        assert state.intent["sql_strategy"] != ""

    def test_timing_recorded(self, classifier, sample_state):
        """Execution time should be recorded in state.timing."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count query"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            state = classifier.run(sample_state)

        assert "intent_classifier" in state.timing
        assert state.timing["intent_classifier"] > 0


# ========================================
# Test: Metrics
# ========================================

class TestMetrics:

    def test_metrics_updated_on_success(self, classifier, sample_state):
        """Metrics should update after successful execution."""
        mock_response = "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count query"

        with patch.object(classifier, "_call_llm", return_value=mock_response):
            classifier.run(sample_state)

        metrics = classifier.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1
        assert metrics["failed_calls"] == 0
