"""
Integration tests for full 8-agent pipeline via TextToSQLPipeline.

Tests cover:
- Complete pipeline runs end-to-end
- Pipeline stops early on ambiguous query
- Pipeline stops early on validation failure
- AgentState flows correctly through all agents
- All agents mocked to avoid external dependencies
- SQL error feedback loop (QueryExecutionError retry)
"""

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from src.agents.insight_generator import InsightGenerator
from src.agents.intent_classifier import IntentClassifier
from src.agents.query_executor import QueryExecutor
from src.agents.query_planner import QueryPlanner
from src.agents.query_rewriter import QueryRewriter
from src.agents.retrieval_evaluator import RetrievalEvaluator
from src.agents.schema_retriever import SchemaRetriever
from src.agents.sql_generator import SQLGenerator
from src.agents.sql_validator import SQLValidator
from src.core.pipeline import TextToSQLPipeline
from src.models.agent_state import AgentState
from src.utils.exceptions import (
    AgentExecutionError,
    QueryExecutionError,
    SQLGenerationError,
    SQLValidationError,
)

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
    result.fetchmany.return_value = [{"total": 1500000}]
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
        "ids": [["financial_db.daily_master", "financial_db.financial_internal"]],
        "distances": [[0.05, 0.15]],
        "metadatas": [[
            {
                "db_name": "financial_db",
                "table_name": "daily_master",
                "columns": "channel_payment,partner,periode,total_trx,success_trx,fail_trx,net_revenue,platform_fee,net_gap",
                "description": "Daily aggregated payment transaction data per channel and partner",
                "relationships": "",
            },
            {
                "db_name": "financial_db",
                "table_name": "financial_internal",
                "columns": "partner,periode,total_trx,success_trx,fail_trx,total_revenue,platform_fee,net_revenue,net_gap",
                "description": "Internal financial records per partner with revenue breakdown",
                "relationships": "",
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


# Valid single-step plan JSON returned by mocked QueryPlanner._call_llm
_MOCK_PLAN_SINGLE = (
    '{"is_multi_step": false, "steps": ['
    '{"step_number": 1, "description": "Execute query", '
    '"sub_query": "berapa total transaksi bulan April 2026?", "depends_on": []}'
    ']}'
)


@pytest.fixture
def pipeline(mock_engine, mock_collection):
    """Fully mocked TextToSQLPipeline — no real LLM or DB calls."""
    with patch.object(QueryRewriter, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        with patch.object(IntentClassifier, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            with patch.object(QueryPlanner, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                with patch.object(RetrievalEvaluator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                    with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                        with patch.object(SQLValidator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                            with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
                                with patch.object(QueryExecutor, "_create_engines", return_value={"financial_db": mock_engine}):
                                    with patch("builtins.open", side_effect=FileNotFoundError):
                                        return TextToSQLPipeline(
                                            query_rewriter=QueryRewriter(),
                                            intent_classifier=IntentClassifier(),
                                            query_planner=QueryPlanner(),
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
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count transactions"):
            with patch.object(pipeline.query_planner, "_call_llm",
                              return_value=_MOCK_PLAN_SINGLE):
                with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                                  return_value="ESSENTIAL:\n- financial_db.daily_master: Required\nOPTIONAL:\nEXCLUDED:"):
                    with patch.object(pipeline.sql_generator, "_call_llm",
                                      return_value="SELECT SUM(total_trx) as total FROM daily_master WHERE periode = '2026-04' LIMIT 100;"):
                        with patch.object(pipeline.insight_generator, "_call_llm",
                                          return_value="Total transaksi April 2026 adalah 1.500.000."):
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
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count transactions"):
            with patch.object(pipeline.query_planner, "_call_llm",
                              return_value=_MOCK_PLAN_SINGLE):
                with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                                  return_value="ESSENTIAL:\n- financial_db.daily_master: Required\nOPTIONAL:\nEXCLUDED:"):
                    with patch.object(pipeline.sql_generator, "_call_llm",
                                      return_value="SELECT SUM(total_trx) as total FROM daily_master WHERE periode = '2026-04' LIMIT 100;"):
                        with patch.object(pipeline.insight_generator, "_call_llm",
                                          return_value="Total transaksi April 2026 adalah 1.500.000."):
                            state = pipeline.run(state)

        expected_agents = [
            "query_rewriter", "intent_classifier", "query_planner", "schema_retriever",
            "retrieval_evaluator", "sql_generator", "sql_validator",
            "query_executor", "insight_generator",
        ]
        for agent_name in expected_agents:
            assert agent_name in state.timing, f"Missing timing for {agent_name}"


# ========================================
# Test: Early Stop — Ambiguous Query
# ========================================

class TestEarlyStopAmbiguous:

    def test_pipeline_stops_on_ambiguous_query(self, pipeline):
        """Pipeline should stop after intent if query is ambiguous."""
        state = AgentState(query="show me the data", database="financial_db")

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Too vague"):
            state = pipeline.run(state)

        assert state.needs_clarification is True
        assert state.sql is None
        assert state.query_result is None
        assert state.insights is None

    def test_early_stop_records_intent_timing(self, pipeline):
        """Even on early stop, intent_classifier timing should be recorded."""
        state = AgentState(query="show me the data", database="financial_db")

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
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count transactions"):
            with patch.object(pipeline.query_planner, "_call_llm",
                              return_value=_MOCK_PLAN_SINGLE):
                with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                                  return_value="ESSENTIAL:\n- financial_db.daily_master: Required\nOPTIONAL:\nEXCLUDED:"):
                    with patch.object(pipeline.sql_generator, "_call_llm",
                                      return_value="SELECT * FROM daily_master; DELETE FROM financial_internal;"):
                        with pytest.raises((SQLValidationError, SQLGenerationError, AgentExecutionError)):
                            pipeline.run(state)


# ========================================
# Test: Error Propagation
# ========================================

class TestErrorPropagation:

    def test_agent_error_stops_pipeline(self, pipeline):
        """AgentExecutionError from any agent should propagate out of pipeline.run()."""
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          side_effect=Exception("LLM unavailable")):
            with pytest.raises(AgentExecutionError):
                pipeline.run(state)

    def test_errors_recorded_in_state(self, pipeline):
        """Errors should be recorded in state.errors even when pipeline raises."""
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        try:
            with patch.object(pipeline.intent_classifier, "_call_llm",
                              side_effect=Exception("LLM error")):
                pipeline.run(state)
        except AgentExecutionError:
            pass

        assert len(state.errors) > 0


# ========================================
# Test: SQL Error Feedback Loop
# ========================================

class TestErrorFeedbackLoop:

    def test_sql_generator_retried_on_execution_error(self, pipeline):
        """
        If QueryExecutor raises QueryExecutionError on first attempt,
        SQLGenerator should be called a second time with sql_error context.
        """
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        good_sql = "SELECT SUM(total_trx) as total FROM daily_master WHERE periode = '2026-04' LIMIT 100;"

        # Executor fails on first call, succeeds on second
        executor_call_count = {"n": 0}

        def executor_side_effect(s):
            executor_call_count["n"] += 1
            if executor_call_count["n"] == 1:
                raise QueryExecutionError(
                    agent_name="query_executor",
                    message="column \"total_trxx\" does not exist",
                )
            # Second call: populate result fields and return state
            s.query_result = [{"total": 1500000}]
            s.row_count = 1
            return s

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count transactions"):
            with patch.object(pipeline.query_planner, "_call_llm",
                              return_value=_MOCK_PLAN_SINGLE):
                with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                                  return_value="ESSENTIAL:\n- financial_db.daily_master: Required\nOPTIONAL:\nEXCLUDED:"):
                    with patch.object(pipeline.sql_generator, "_call_llm",
                                      return_value=good_sql) as mock_gen:
                        with patch.object(pipeline.query_executor, "run",
                                          side_effect=executor_side_effect):
                            with patch.object(pipeline.insight_generator, "_call_llm",
                                              return_value="Total transaksi April 2026 adalah 1.500.000."):
                                state = pipeline.run(state)

        # sql_generator._call_llm should have been invoked twice (initial + retry)
        assert mock_gen.call_count == 2

    def test_error_context_cleared_on_success(self, pipeline):
        """After a successful retry, state.sql_error should be None."""
        state = AgentState(
            query="berapa total transaksi bulan April 2026?",
            database="financial_db",
        )

        good_sql = "SELECT SUM(total_trx) as total FROM daily_master WHERE periode = '2026-04' LIMIT 100;"

        executor_call_count = {"n": 0}

        def executor_side_effect(s):
            executor_call_count["n"] += 1
            if executor_call_count["n"] == 1:
                raise QueryExecutionError(
                    agent_name="query_executor",
                    message="column \"net_revenuu\" does not exist",
                )
            s.query_result = [{"total": 1500000}]
            s.row_count = 1
            return s

        with patch.object(pipeline.intent_classifier, "_call_llm",
                          return_value="INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Count transactions"):
            with patch.object(pipeline.query_planner, "_call_llm",
                              return_value=_MOCK_PLAN_SINGLE):
                with patch.object(pipeline.retrieval_evaluator, "_call_llm",
                                  return_value="ESSENTIAL:\n- financial_db.daily_master: Required\nOPTIONAL:\nEXCLUDED:"):
                    with patch.object(pipeline.sql_generator, "_call_llm",
                                      return_value=good_sql):
                        with patch.object(pipeline.query_executor, "run",
                                          side_effect=executor_side_effect):
                            with patch.object(pipeline.insight_generator, "_call_llm",
                                              return_value="Total transaksi April 2026 adalah 1.500.000."):
                                state = pipeline.run(state)

        assert state.sql_error is None


# ========================================
# Test: Pipeline Structure
# ========================================

class TestPipelineStructure:

    def test_agents_property_returns_all_ten(self, pipeline):
        """pipeline.agents should expose all 10 agents in order."""
        assert len(pipeline.agents) == 10

    def test_agents_property_order(self, pipeline):
        """Agents should be in pipeline execution order."""
        names = [a.name for a in pipeline.agents]
        assert names == [
            "query_rewriter",
            "intent_classifier",
            "query_planner",
            "schema_retriever",
            "retrieval_evaluator",
            "sql_generator",
            "sql_validator",
            "query_executor",
            "response_planner",
            "insight_generator",
        ]
