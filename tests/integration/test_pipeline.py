"""
Integration tests for full 7-agent pipeline.

Tests cover:
- Complete pipeline runs end-to-end
- Pipeline stops early on ambiguous query
- Pipeline stops early on validation failure
- AgentState flows correctly through all agents
- All agents mocked to avoid external dependencies
"""

import pytest
from unittest.mock import patch, MagicMock

from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable
from src.components.intent_classifier import IntentClassifier
from src.components.schema_retriever import SchemaRetriever
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.components.query_executor import QueryExecutor
from src.components.insight_generator import InsightGenerator
from src.utils.exceptions import AgentExecutionError, SQLValidationError, SQLGenerationError


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
                "relationships": ""
            },
            {
                "db_name": "sales_db",
                "table_name": "orders",
                "columns": "order_id,customer_id",
                "description": "Order transactions",
                "relationships": "FK to customers.customer_id"
            }
        ]]
    }
    return collection

def _make_mock_retriever(mock_collection):
    """Create SchemaRetriever with mocked dependencies."""
    import logging
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
        "last_execution_time": None, "created_at": "2024-01-01"
    }
    retriever.logger = logging.getLogger("agent.schema_retriever")
    return retriever

@pytest.fixture
def all_agents(mock_engine, mock_collection):
    """Initialize all agents with mocked dependencies."""
    with patch.object(IntentClassifier, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
     with patch.object(RetrievalEvaluator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
      with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
       with patch.object(SQLValidator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
         with patch("src.components.schema_retriever.chromadb.PersistentClient"):
          with patch("src.components.schema_retriever.embedding_functions.OpenAIEmbeddingFunction"):
           with patch.object(QueryExecutor, "_create_engines", return_value={"sales_db": mock_engine}):
            with patch("builtins.open", side_effect=FileNotFoundError):
                return {
                    "intent": IntentClassifier(),
                    "retriever": _make_mock_retriever(mock_collection),
                    "evaluator": RetrievalEvaluator(),
                    "generator": SQLGenerator(),
                    "validator": SQLValidator(enable_ai_validation=False),
                    "executor": QueryExecutor(),
                    "insight": InsightGenerator()
                }


def run_pipeline(agents: dict, state: AgentState) -> AgentState:
    """Helper to run full pipeline."""
    state = agents["intent"].run(state)
    if state.needs_clarification:
        return state

    state = agents["retriever"].execute(state)
    state = agents["evaluator"].run(state)
    state = agents["generator"].run(state)
    state = agents["validator"].run(state)
    state = agents["executor"].run(state)
    state = agents["insight"].run(state)
    return state


# ========================================
# Test: Complete Pipeline
# ========================================

class TestCompletePipeline:

    def test_pipeline_completes_successfully(self, all_agents, mock_collection):
        """Full pipeline should complete with all state fields populated."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        # Setup retriever
        all_agents["retriever"].collection = mock_collection
        all_agents["retriever"].top_k = 5
        all_agents["retriever"].name = "schema_retriever"
        all_agents["retriever"].version = "1.0.0"
        all_agents["retriever"].metrics = {
            "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
            "total_time_seconds": 0.0, "average_time_seconds": 0.0,
            "last_execution_time": None, "created_at": "2024-01-01"
        }
        import logging
        all_agents["retriever"].logger = logging.getLogger("agent.schema_retriever")

        with patch.object(all_agents["intent"], "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count"):
            with patch.object(all_agents["evaluator"], "_call_llm",
                              return_value="ESSENTIAL:\n- sales_db.customers: Required\nOPTIONAL:\nEXCLUDED:"):
                with patch.object(all_agents["generator"], "_call_llm",
                                  return_value="SELECT COUNT(*) as total FROM customers LIMIT 100;"):
                    with patch.object(all_agents["insight"], "_call_llm",
                                      return_value="Terdapat 100 customer dalam sistem."):
                        state = run_pipeline(all_agents, state)

        assert state.intent is not None
        assert state.retrieved_tables is not None
        assert state.evaluated_tables is not None
        assert state.sql is not None
        assert state.validated_sql is not None
        assert state.query_result is not None
        assert state.insights is not None

    def test_state_flows_through_all_agents(self, all_agents, mock_collection):
        """Each agent should read and write to the same state object."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        all_agents["retriever"].collection = mock_collection
        all_agents["retriever"].top_k = 5
        all_agents["retriever"].name = "schema_retriever"
        all_agents["retriever"].version = "1.0.0"
        all_agents["retriever"].metrics = {
            "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
            "total_time_seconds": 0.0, "average_time_seconds": 0.0,
            "last_execution_time": None, "created_at": "2024-01-01"
        }
        import logging
        all_agents["retriever"].logger = logging.getLogger("agent.schema_retriever")

        with patch.object(all_agents["intent"], "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count"):
            with patch.object(all_agents["evaluator"], "_call_llm",
                              return_value="ESSENTIAL:\n- sales_db.customers: Required\nOPTIONAL:\nEXCLUDED:"):
                with patch.object(all_agents["generator"], "_call_llm",
                                  return_value="SELECT COUNT(*) as total FROM customers LIMIT 100;"):
                    with patch.object(all_agents["insight"], "_call_llm",
                                      return_value="Terdapat 100 customer dalam sistem."):
                        state = run_pipeline(all_agents, state)

        # All timing should be recorded
        assert "intent_classifier" in state.timing
        assert "retrieval_evaluator" in state.timing
        assert "sql_generator" in state.timing
        assert "sql_validator" in state.timing
        assert "query_executor" in state.timing
        assert "insight_generator" in state.timing


# ========================================
# Test: Early Stop - Ambiguous Query
# ========================================

class TestEarlyStopAmbiguous:

    def test_pipeline_stops_on_ambiguous_query(self, all_agents):
        """Pipeline should stop after intent if query is ambiguous."""
        state = AgentState(query="show me the data", database="sales_db")

        with patch.object(all_agents["intent"], "_call_llm",
                          return_value="INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Too vague"):
            state = all_agents["intent"].run(state)

        assert state.needs_clarification is True
        assert state.sql is None
        assert state.query_result is None
        assert state.insights is None


# ========================================
# Test: Early Stop - Validation Failure
# ========================================

class TestEarlyStopValidation:

    def test_pipeline_stops_on_validation_failure(self, all_agents, mock_collection):
        """Pipeline should stop if SQL validation fails."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        all_agents["retriever"].collection = mock_collection
        all_agents["retriever"].top_k = 5
        all_agents["retriever"].name = "schema_retriever"
        all_agents["retriever"].version = "1.0.0"
        all_agents["retriever"].metrics = {
            "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
            "total_time_seconds": 0.0, "average_time_seconds": 0.0,
            "last_execution_time": None, "created_at": "2024-01-01"
        }
        import logging
        all_agents["retriever"].logger = logging.getLogger("agent.schema_retriever")

        with patch.object(all_agents["intent"], "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count"):
            with patch.object(all_agents["evaluator"], "_call_llm",
                              return_value="ESSENTIAL:\n- sales_db.customers: Required\nOPTIONAL:\nEXCLUDED:"):
                # Generator returns dangerous SQL
                with patch.object(all_agents["generator"], "_call_llm",
                                  return_value="SELECT * FROM customers; DELETE FROM orders;"):
                
                    with pytest.raises((SQLValidationError, SQLGenerationError)):
                        state = all_agents["intent"].run(state)
                        state = all_agents["retriever"].execute(state)
                        state = all_agents["evaluator"].run(state)
                        state = all_agents["generator"].run(state)
                        state = all_agents["validator"].run(state)


# ========================================
# Test: Error Propagation
# ========================================

class TestErrorPropagation:

    def test_agent_error_stops_pipeline(self, all_agents):
        """AgentExecutionError from any agent should stop pipeline."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        with patch.object(all_agents["intent"], "_call_llm",
                          side_effect=Exception("LLM unavailable")):
            with pytest.raises(AgentExecutionError):
                all_agents["intent"].run(state)

    def test_errors_recorded_in_state(self, all_agents):
        """Errors should be recorded in state.errors."""
        state = AgentState(query="berapa total customer?", database="sales_db")

        try:
            with patch.object(all_agents["intent"], "_call_llm",
                              side_effect=Exception("LLM error")):
                all_agents["intent"].run(state)
        except AgentExecutionError:
            pass

        assert len(state.errors) > 0
