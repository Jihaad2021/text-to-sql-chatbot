"""
Pipeline early-return guard — unit tests for query_out_of_range.

When QueryRewriter sets state.query_out_of_range=True, pipeline.run() must:
  1. Return immediately after QueryRewriter — before IntentClassifier, AnalyticsAgent,
     or any SQL pipeline agent runs.
  2. Set state.insights to the deterministic out-of-range message (with Indonesian date).
  3. Leave state.query_result=[] and state.row_count=0 (never written by downstream agents).

These tests verify Layer 1 of the two-layer fix. Layer 2 (InsightGenerator clearing data)
is covered by test_date_range_guard.TestOutOfRangeGuardClearsData.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.core.pipeline import TextToSQLPipeline
from src.models.agent_state import AgentState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pipeline() -> TextToSQLPipeline:
    """Build a pipeline whose agents are all mocked — no real DB or LLM needed."""
    with (
        patch("src.core.pipeline.QueryRewriter"),
        patch("src.core.pipeline.IntentClassifier"),
        patch("src.core.pipeline.QueryPlanner"),
        patch("src.core.pipeline.SchemaRetriever"),
        patch("src.core.pipeline.RetrievalEvaluator"),
        patch("src.core.pipeline.SQLGenerator"),
        patch("src.core.pipeline.SQLValidator"),
        patch("src.core.pipeline.QueryExecutor"),
        patch("src.core.pipeline.ResponsePlanner"),
        patch("src.core.pipeline.InsightGenerator"),
        patch("src.core.pipeline.AnalyticsAgent"),
        patch("src.core.pipeline.get_latest_available_date", return_value=date(2026, 6, 30)),
        patch("src.core.pipeline.build_context_snapshot", return_value=""),
    ):
        pipeline = TextToSQLPipeline.__new__(TextToSQLPipeline)
        pipeline.query_rewriter    = MagicMock()
        pipeline.intent_classifier = MagicMock()
        pipeline.query_planner     = MagicMock()
        pipeline.schema_retriever  = MagicMock()
        pipeline.retrieval_evaluator = MagicMock()
        pipeline.sql_generator     = MagicMock()
        pipeline.sql_validator     = MagicMock()
        pipeline.query_executor    = MagicMock()
        pipeline.response_planner  = MagicMock()
        pipeline.insight_generator = MagicMock()
        pipeline.analytics_agent   = MagicMock()
        pipeline.data_end_date     = date(2026, 6, 30)
        pipeline.data_start_date   = date(2026, 3, 1)
        pipeline.context_snapshot  = ""
        pipeline._cache            = MagicMock()
        pipeline._cache.get.return_value = None  # no cache hit
        return pipeline


def _state_with_out_of_range() -> AgentState:
    """AgentState where QueryRewriter has already set query_out_of_range=True."""
    state = AgentState(
        query="distribusi share produk bulan ini",
        database="financial_db",
        original_query="distribusi share produk bulan ini",
    )
    return state


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPipelineOutOfRangeEarlyReturn:
    """
    Layer 1: pipeline.run() must short-circuit immediately after QueryRewriter
    when query_out_of_range=True — identical in spirit to the out_of_scope guard.
    """

    def _setup_rewriter_out_of_range(self, pipeline: TextToSQLPipeline) -> None:
        """Make query_rewriter.run() set out_of_range on the passed state."""
        def _rewriter_run(state: AgentState) -> AgentState:
            state.query_out_of_range = True
            state.out_of_range_latest = "2026-06-30"
            return state

        pipeline.query_rewriter.run.side_effect = _rewriter_run

    def test_analytics_agent_not_called(self):
        """AnalyticsAgent.run() must never be called when query_out_of_range=True."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        pipeline.run(_state_with_out_of_range())

        pipeline.analytics_agent.run.assert_not_called()

    def test_intent_classifier_not_called(self):
        """IntentClassifier must not run — pipeline returns before parallel agents."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        pipeline.run(_state_with_out_of_range())

        pipeline.intent_classifier.run.assert_not_called()

    def test_insight_generator_not_called(self):
        """InsightGenerator must not run — guard message set directly by pipeline."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        pipeline.run(_state_with_out_of_range())

        pipeline.insight_generator.run.assert_not_called()

    def test_insights_contains_indonesian_date(self):
        """state.insights must contain the latest date in Indonesian format."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        result = pipeline.run(_state_with_out_of_range())

        assert "30 Juni 2026" in (result.insights or ""), (
            f"Expected '30 Juni 2026' in insights. Got: {result.insights!r}"
        )

    def test_insights_contains_guard_text(self):
        """state.insights must contain the 'Belum ada data' guard phrase."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        result = pipeline.run(_state_with_out_of_range())

        assert "Belum ada data" in (result.insights or ""), (
            f"Expected 'Belum ada data' in insights. Got: {result.insights!r}"
        )

    def test_query_result_remains_empty(self):
        """No downstream agent runs → state.query_result not populated by any agent."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        result = pipeline.run(_state_with_out_of_range())

        # AgentState.query_result defaults to None; early-return means no agent sets it.
        # Both None and [] mean "no data" — verify nothing was written by downstream agents.
        assert not result.query_result, (
            f"query_result must be falsy after early-return. Got: {result.query_result}"
        )

    def test_row_count_remains_zero(self):
        """No downstream agent runs → state.row_count stays 0."""
        pipeline = _make_pipeline()
        self._setup_rewriter_out_of_range(pipeline)

        result = pipeline.run(_state_with_out_of_range())

        assert result.row_count == 0, (
            f"row_count must be 0 after early-return. Got: {result.row_count}"
        )

    def test_in_range_query_does_not_early_return(self):
        """When query_out_of_range=False, pipeline must NOT early-return.
        _run_initial_agents_parallel must be called (downstream agents proceed normally)."""
        pipeline = _make_pipeline()

        # QueryRewriter does NOT set out_of_range — query is within data range
        def _rewriter_normal(state: AgentState) -> AgentState:
            state.query_out_of_range = False
            return state

        pipeline.query_rewriter.run.side_effect = _rewriter_normal

        # Stub the parallel agents step — set intent to analytics so routing is deterministic.
        def _parallel_with_analytics_intent(state: AgentState) -> AgentState:
            state.intent = {"category": "complex_analytics"}
            return state

        with (
            patch.object(pipeline, "_run_initial_agents_parallel",
                         side_effect=_parallel_with_analytics_intent) as mock_parallel,
            patch.object(pipeline, "_run_analytics", side_effect=lambda s: s),
            patch.object(pipeline, "response_planner") as mock_rp,
            patch.object(pipeline, "insight_generator") as mock_ig,
        ):
            mock_rp.run.side_effect = lambda s: s
            mock_ig.run.side_effect = lambda s: s
            pipeline.run(_state_with_out_of_range())

        # If early-return did NOT fire, _run_initial_agents_parallel was called
        mock_parallel.assert_called_once()
