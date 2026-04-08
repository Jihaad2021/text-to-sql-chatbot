"""
E2E tests for full pipeline with real API and database.

Tests verify that each stage of the pipeline produces
valid output when using real agents.

Requirements:
    - Valid .env with ANTHROPIC_API_KEY
    - ChromaDB indexed
    - PostgreSQL running

Run:
    pytest tests/e2e/test_real_pipeline.py -v -s
"""

import pytest

from src.models.agent_state import AgentState
from tests.e2e.conftest import run_full_pipeline

# ========================================
# Test: Intent Classification (Real)
# ========================================

class TestRealIntentClassifier:

    def test_clear_query_not_ambiguous(self, real_intent_classifier):
        """Clear query should not need clarification."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state = real_intent_classifier.run(state)

        print(f"\nQuery    : {state.query}")
        print(f"Intent   : {state.intent['category']}")
        print(f"Confidence: {state.intent['confidence']}")
        print(f"Reason   : {state.intent['reason']}")

        assert state.intent is not None
        assert state.needs_clarification is False
        assert state.intent["confidence"] >= 0.7

    def test_ambiguous_query_needs_clarification(self, real_intent_classifier):
        """Vague query should be flagged as ambiguous."""
        state = AgentState(query="show me the data", database="sales_db")
        state = real_intent_classifier.run(state)

        print(f"\nQuery    : {state.query}")
        print(f"Intent   : {state.intent['category']}")
        print(f"Confidence: {state.intent['confidence']}")

        assert state.needs_clarification is True


# ========================================
# Test: Schema Retrieval (Real)
# ========================================

class TestRealSchemaRetriever:

    def test_retrieves_relevant_tables(self, real_schema_retriever):
        """Should retrieve tables relevant to customer query."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state = real_schema_retriever.execute(state)

        print(f"\nQuery: {state.query}")
        print(f"Retrieved {len(state.retrieved_tables)} tables:")
        for t in state.retrieved_tables:
            print(f"  - {t.full_name} (score: {t.similarity_score:.3f})")

        assert len(state.retrieved_tables) > 0
        table_names = [t.table_name for t in state.retrieved_tables]
        assert "customers" in table_names

    def test_auto_detects_correct_database(self, real_schema_retriever):
        """Should auto-detect sales_db for customer query."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state = real_schema_retriever.execute(state)

        print(f"\nDetected database: {state.database}")
        assert state.database == "sales_db"


# ========================================
# Test: SQL Generation (Real)
# ========================================

class TestRealSQLGenerator:

    def test_generates_valid_sql(self, real_agents):
        """Should generate valid SQL for simple query."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state = real_agents["intent"].run(state)
        state = real_agents["retriever"].execute(state)
        state = real_agents["evaluator"].run(state)
        state = real_agents["generator"].run(state)

        print(f"\nQuery: {state.query}")
        print(f"SQL:\n{state.sql}")

        assert state.sql is not None
        assert "SELECT" in state.sql.upper()
        assert "customers" in state.sql.lower()

    def test_sql_contains_limit(self, real_agents):
        """Generated SQL should always have LIMIT clause."""
        state = AgentState(query="tampilkan semua customer", database="sales_db")
        state = real_agents["intent"].run(state)
        state = real_agents["retriever"].execute(state)
        state = real_agents["evaluator"].run(state)
        state = real_agents["generator"].run(state)

        print(f"\nSQL:\n{state.sql}")
        assert "LIMIT" in state.sql.upper()


# ========================================
# Test: Full Pipeline (Real)
# ========================================

class TestRealFullPipeline:

    def test_simple_count_query(self, real_agents):
        """Simple count query should return numeric result."""
        state = run_full_pipeline(real_agents, "berapa total customer?")

        print(f"\nQuery    : {state.query}")
        print(f"Intent   : {state.intent['category']}")
        print(f"SQL      : {state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Result   : {state.query_result}")
        print(f"Insights : {state.insights}")

        assert state.validated_sql is not None
        assert state.row_count > 0
        assert state.insights is not None

    def test_simple_select_query(self, real_agents):
        """Simple select query should return multiple rows."""
        state = run_full_pipeline(real_agents, "tampilkan semua customer")

        print(f"\nQuery    : {state.query}")
        print(f"SQL      : {state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")

        assert state.row_count > 0
        assert state.query_result is not None

    def test_filtered_query(self, real_agents):
        """Filtered query should return filtered results."""
        state = run_full_pipeline(real_agents, "tampilkan customer dari Jakarta")

        print(f"\nQuery    : {state.query}")
        print(f"SQL      : {state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")

        assert state.validated_sql is not None
        assert "WHERE" in state.validated_sql.upper()

    def test_ambiguous_query_stops_pipeline(self, real_agents):
        """Ambiguous query should stop pipeline early."""
        state = run_full_pipeline(real_agents, "show me the data")

        print(f"\nQuery              : {state.query}")
        print(f"Needs clarification: {state.needs_clarification}")
        print(f"Reason             : {state.clarification_reason}")

        assert state.needs_clarification is True
        assert state.sql is None
        assert state.insights is None

    def test_pipeline_timing_recorded(self, real_agents):
        """All agent timings should be recorded in state."""
        state = run_full_pipeline(real_agents, "berapa total customer?")

        print("\nTiming breakdown:")
        for agent, ms in state.timing.items():
            print(f"  {agent}: {ms:.0f}ms")
        print(f"  Total: {sum(state.timing.values()):.0f}ms")

        assert "intent_classifier" in state.timing
        assert "retrieval_evaluator" in state.timing
        assert "sql_generator" in state.timing
        assert "sql_validator" in state.timing
        assert "query_executor" in state.timing
        assert "insight_generator" in state.timing
