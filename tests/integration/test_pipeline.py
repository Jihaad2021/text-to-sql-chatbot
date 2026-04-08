"""
Integration tests for full 7-agent pipeline via TextToSQLPipeline.

Tests cover:
- Complete pipeline runs end-to-end
- Pipeline stops early on ambiguous query
- Pipeline stops early on validation failure
- AgentState flows correctly through all agents
- All agents mocked to avoid external dependencies
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.components.insight_generator import InsightGenerator
from src.components.intent_classifier import IntentClassifier
from src.components.query_executor import QueryExecutor
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.schema_retriever import SchemaRetriever
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.core.pipeline import TextToSQLPipeline
from src.models.agent_state import AgentState
from src.utils.exceptions import AgentExecutionError, SQLGenerationError, SQLValidationError

# ========================================
# Fixtures
# ========================================

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
def mock_collection():
    """Mock ChromaDB collection."""
    collection = MagicMock()
    collection.count.return_value = 8
    collection.query.return_value = {
        "ids": [["sales_db.customers", "sales_db.orders"]],
        "distances": [[0.05, 0.15]],
        "metadatas": [[
            {
                "db_name": "sales_db",
                "table_name": "customers",
                "columns": "customer_id,customer_name",
                "description": "Customer master data",
                "relationships": "",
            },
            {
                "db_name": "sales_db",
                "table_name": "orders",
                "columns": "order_id,customer_id",
                "description": "Order transactions",
                "relationships": "FK to customers.customer_id",
            },
        ]],
    }
    return collection


def _make_mock_retriever(mock_collection) -> SchemaRetriever:
    """Create SchemaRetriever with mocked dependencies."""
    retriever = SchemaRetriever.__new__(SchemaRetriever)
    retriever.name = "schema_retriever"
    retriever.version = "2.0.0"
    retriever.top_k = 5
    retriever.collection = mock_collection
    retriever.bm25 = None
    retriever.bm25_corpus = []
    retriever.graph = None
    retriever.metrics = {
        "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
        "total_time_seconds": 0.0, "average_time_seconds": 0.0,
        "last_execution_time": None, "created_at": "2024-01-01",
    }
    retriever.logger = logging.getLogger("agent.schema_retriever")
    return retriever


@pytest.fixture
def pipeline(mock_engine, mock_collection):
    """Fully mocked TextToSQLPipeline — no real LLM or DB calls."""
    with patch.object(IntentClassifier, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        with patch.object(RetrievalEvaluator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                with patch.object(SQLValidator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                    with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                        with patch.object(QueryExecutor, "_create_engines", return_value={"sales_db": mock_engine}):
                            with patch("builtins.open", side_effect=FileNotFoundError):
                                return TextToSQLPipeline(
                                    intent_classifier=IntentClassifier(),
                                    schema_retriever=_make_mock_retriever(mock_collection),
                                    retrieval_evaluator=RetrievalEvaluator(),
                                    sql_generator=SQLGenerator(),
                                    sql_validator=SQLValidator(enable_ai_validation=False),
                                    query_executor=QueryExecutor(),
                                    insight_generator=InsightGenerator(),
                                )


# ========================================
# Test: Complete Pipeline
# ========================================

class TestCompletePipeline:

    def test_pipeline_completes_successfully(self, pipeline):
        """Full pipeline should complete with all state fields populated."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count"):
            with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                              return_value="ESSENTIAL:\n- sales_db.customers: Required\nOPTIONAL:\nEXCLUDED:"):
                with patch.object(pipeline.sql_generator, "_call_llm",
                                  return_value="SELECT COUNT(*) as total FROM customers LIMIT 100;"):
                    with patch.object(pipeline.insight_generator, "_call_llm",
                                      return_value="Terdapat 100 customer dalam sistem."):
                        state = pipeline.run(state)

        assert state.intent is not None
        assert state.retrieved_tables is not None
        assert state.evaluated_tables is not None
        assert state.sql is not None
        assert state.validated_sql is not None
        assert state.query_result is not None
        assert state.insights is not None

    def test_state_flows_through_all_agents(self, pipeline):
        """Timing should be recorded for every agent that ran."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count"):
            with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                              return_value="ESSENTIAL:\n- sales_db.customers: Required\nOPTIONAL:\nEXCLUDED:"):
                with patch.object(pipeline.sql_generator, "_call_llm",
                                  return_value="SELECT COUNT(*) as total FROM customers LIMIT 100;"):
                    with patch.object(pipeline.insight_generator, "_call_llm",
                                      return_value="Terdapat 100 customer dalam sistem."):
                        state = pipeline.run(state)

        expected_agents = [
            "intent_classifier", "schema_retriever", "retrieval_evaluator",
            "sql_generator", "sql_validator", "query_executor", "insight_generator",
        ]
        for agent_name in expected_agents:
            assert agent_name in state.timing, f"Missing timing for {agent_name}"


# ========================================
# Test: Early Stop — Ambiguous Query
# ========================================

class TestEarlyStopAmbiguous:

    def test_pipeline_stops_on_ambiguous_query(self, pipeline):
        """Pipeline should stop after intent if query is ambiguous."""
        state = AgentState(query="show me the data", database="sales_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Too vague"):
            state = pipeline.run(state)

        assert state.needs_clarification is True
        assert state.sql is None
        assert state.query_result is None
        assert state.insights is None

    def test_early_stop_records_intent_timing(self, pipeline):
        """Even on early stop, intent_classifier timing should be recorded."""
        state = AgentState(query="show me the data", database="sales_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Too vague"):
            state = pipeline.run(state)

        assert "intent_classifier" in state.timing
        assert "schema_retriever" not in state.timing


# ========================================
# Test: Early Stop — Validation Failure
# ========================================

class TestEarlyStopValidation:

    def test_pipeline_stops_on_validation_failure(self, pipeline):
        """Pipeline should raise if SQL validation fails."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count"):
            with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                              return_value="ESSENTIAL:\n- sales_db.customers: Required\nOPTIONAL:\nEXCLUDED:"):
                with patch.object(pipeline.sql_generator, "_call_llm",
                                  return_value="SELECT * FROM customers; DELETE FROM orders;"):
                    with pytest.raises((SQLValidationError, SQLGenerationError, AgentExecutionError)):
                        pipeline.run(state)


# ========================================
# Test: Error Propagation
# ========================================

class TestErrorPropagation:

    def test_agent_error_stops_pipeline(self, pipeline):
        """AgentExecutionError from any agent should propagate out of pipeline.run()."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          side_effect=Exception("LLM unavailable")):
            with pytest.raises(AgentExecutionError):
                pipeline.run(state)

    def test_errors_recorded_in_state(self, pipeline):
        """Errors should be recorded in state.errors even when pipeline raises."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        try:
            with patch.object(pipeline.intent_classifier, "_call_llm",
                              side_effect=Exception("LLM error")):
                pipeline.run(state)
        except AgentExecutionError:
            pass

        assert len(state.errors) > 0


# ========================================
# Test: Pipeline Structure
# ========================================

class TestPipelineStructure:

    def test_agents_property_returns_all_seven(self, pipeline):
        """pipeline.agents should expose all 7 agents in order."""
        assert len(pipeline.agents) == 7

    def test_agents_property_order(self, pipeline):
        """Agents should be in pipeline execution order."""
        names = [a.name for a in pipeline.agents]
        assert names == [
            "intent_classifier",
            "schema_retriever",
            "retrieval_evaluator",
            "sql_generator",
            "sql_validator",
            "query_executor",
            "insight_generator",
        ]
