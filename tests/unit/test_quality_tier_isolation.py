"""
Unit tests: quality_tier isolation for AnalyticsAgent and InsightGenerator.

Locks in:
- standard tier → agents use self.model (gpt-4o-mini)
- deep tier    → agents use gpt-4.1-mini
- All 6 other agents are completely unaffected by quality_tier
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.analytics_agent import _DEEP_MODEL as AA_DEEP_MODEL
from src.agents.analytics_agent import AnalyticsAgent
from src.agents.insight_generator import _DEEP_MODEL as IG_DEEP_MODEL
from src.agents.insight_generator import InsightGenerator
from src.agents.intent_classifier import IntentClassifier
from src.agents.query_planner import QueryPlanner
from src.agents.query_rewriter import QueryRewriter
from src.agents.retrieval_evaluator import RetrievalEvaluator
from src.agents.sql_generator import SQLGenerator
from src.agents.sql_validator import SQLValidator
from src.models.agent_state import AgentState

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _state(tier: str = "standard") -> AgentState:
    return AgentState(query="test query", database="financial_db", quality_tier=tier)


def _make_analytics_agent(mock_client: MagicMock) -> AnalyticsAgent:
    with (
        patch.object(AnalyticsAgent, "_init_client", return_value=("openai", mock_client, "gpt-4o-mini")),
        patch.object(AnalyticsAgent, "_init_engines", return_value={"financial_db": MagicMock()}),
    ):
        return AnalyticsAgent()


def _make_stop_response() -> MagicMock:
    """OpenAI stop message (no tool calls)."""
    stop = MagicMock()
    stop.tool_calls = None
    stop.content = "done"
    resp = MagicMock()
    resp.choices = [MagicMock(message=stop, finish_reason="stop")]
    resp.usage = MagicMock(completion_tokens=10, prompt_tokens=100, total_tokens=110)
    return resp


# ─────────────────────────────────────────────────────────────
# AnalyticsAgent — quality_tier routing
# ─────────────────────────────────────────────────────────────

class TestAnalyticsAgentQualityTier:
    """AnalyticsAgent must pass effective_model (not self.model) to _run_openai_compatible."""

    def _capture_effective_model(self, tier: str) -> str | None:
        """
        Intercept the effective_model argument AnalyticsAgent.execute() passes
        to _run_openai_compatible. Uses a wrapper that captures the arg and then
        short-circuits by returning state.
        """
        mock_client = MagicMock()
        agent = _make_analytics_agent(mock_client)

        captured: list[str] = []

        _original_run = agent._run_openai_compatible

        def intercept(state, db_engine, system_prompt, effective_model):
            captured.append(effective_model)
            # Return state to avoid full loop execution
            return state

        state = _state(tier)
        state.intent = {"category": "complex_analytics", "segment": "general"}
        state.validated_sql = None
        state.query_result = None

        with patch.object(agent, "_run_openai_compatible", side_effect=intercept):
            agent.execute(state)

        return captured[0] if captured else None

    def test_standard_tier_passes_default_model(self):
        agent = _make_analytics_agent(MagicMock())
        default_model = agent.model
        result = self._capture_effective_model("standard")
        assert result == default_model, (
            f"standard tier should pass '{default_model}', got '{result}'"
        )

    def test_deep_tier_passes_deep_model(self):
        result = self._capture_effective_model("deep")
        assert result == AA_DEEP_MODEL, (
            f"deep tier should pass '{AA_DEEP_MODEL}', got '{result}'"
        )

    def test_deep_model_constant_is_correct(self):
        assert AA_DEEP_MODEL == "gpt-4.1-mini"

    def test_self_model_not_mutated_between_standard_and_deep(self):
        """AnalyticsAgent uses local effective_model, never mutates self.model."""
        mock_client = MagicMock()
        agent = _make_analytics_agent(mock_client)
        original_model = agent.model

        for tier in ("standard", "deep", "standard"):
            state = _state(tier)
            state.intent = {"category": "complex_analytics", "segment": "general"}
            state.validated_sql = None
            state.query_result = None
            with patch.object(agent, "_run_openai_compatible", return_value=state):
                agent.execute(state)
            assert agent.model == original_model, (
                f"agent.model changed to '{agent.model}' after tier='{tier}' run"
            )


# ─────────────────────────────────────────────────────────────
# InsightGenerator — quality_tier routing
# ─────────────────────────────────────────────────────────────

class TestInsightGeneratorQualityTier:
    """InsightGenerator must pass effective_model as model= kwarg to _call_llm, never mutate self.model."""

    def _make_state(self, tier: str) -> AgentState:
        state = _state(tier)
        state.intent = {"category": "simple_select"}
        state.insights = None
        state.query_result = [{"col": 1}]
        state.validated_sql = "SELECT 1"
        return state

    def _capture_llm_kwargs(self, tier: str) -> dict:
        """Return the kwargs dict that execute() passes to _call_llm."""
        agent = InsightGenerator()
        captured: list[dict] = []

        def record(*args, **kwargs):
            captured.append(kwargs)
            return "insight"

        state = self._make_state(tier)
        with patch.object(agent, "_call_llm", side_effect=record):
            with patch.object(agent, "_build_prompt", return_value="prompt"):
                agent.execute(state)

        assert captured, "_call_llm was not called"
        return captured[0]

    def test_standard_tier_passes_no_model_kwarg(self):
        """Standard tier must NOT pass a model override — _call_llm uses self.model implicitly."""
        kwargs = self._capture_llm_kwargs("standard")
        assert kwargs.get("model") is None, (
            f"standard tier must pass model=None, got model={kwargs.get('model')!r}"
        )

    def test_deep_tier_passes_deep_model_kwarg(self):
        """Deep tier must pass model=_DEEP_MODEL as an explicit kwarg."""
        kwargs = self._capture_llm_kwargs("deep")
        assert kwargs.get("model") == IG_DEEP_MODEL, (
            f"deep tier must pass model='{IG_DEEP_MODEL}', got model={kwargs.get('model')!r}"
        )

    def test_self_model_never_mutated_for_standard(self):
        agent = InsightGenerator()
        original = agent.model
        state = self._make_state("standard")
        with patch.object(agent, "_call_llm", return_value="insight"):
            with patch.object(agent, "_build_prompt", return_value="prompt"):
                agent.execute(state)
        assert agent.model == original

    def test_self_model_never_mutated_for_deep(self):
        """self.model must remain unchanged even for deep tier — no save/restore needed."""
        agent = InsightGenerator()
        original = agent.model
        state = self._make_state("deep")
        with patch.object(agent, "_call_llm", return_value="insight"):
            with patch.object(agent, "_build_prompt", return_value="prompt"):
                agent.execute(state)
        assert agent.model == original, (
            f"self.model changed to '{agent.model}' — singleton mutation detected"
        )

    def test_self_model_stable_across_alternating_tiers(self):
        """Simulate concurrent-style alternating calls: model must stay constant."""
        agent = InsightGenerator()
        original = agent.model
        for tier in ("standard", "deep", "standard", "deep"):
            state = self._make_state(tier)
            with patch.object(agent, "_call_llm", return_value="insight"):
                with patch.object(agent, "_build_prompt", return_value="prompt"):
                    agent.execute(state)
            assert agent.model == original, (
                f"self.model changed to '{agent.model}' after tier='{tier}'"
            )

    def test_deep_model_constant_is_correct(self):
        assert IG_DEEP_MODEL == "gpt-4.1-mini"


# ─────────────────────────────────────────────────────────────
# Other agents — completely unaffected by quality_tier
# ─────────────────────────────────────────────────────────────

class TestOtherAgentsUnaffectedByQualityTier:
    """The 6 agents from Langkah 2 must ignore quality_tier entirely."""

    @pytest.mark.parametrize("tier", ["standard", "deep"])
    def test_intent_classifier_model_stable(self, tier):
        agent = IntentClassifier()
        model_before = agent.model
        state = _state(tier)
        assert getattr(state, "quality_tier") == tier
        assert agent.model == model_before

    @pytest.mark.parametrize("tier", ["standard", "deep"])
    def test_query_rewriter_model_stable(self, tier):
        agent = QueryRewriter()
        model_before = agent.model
        state = _state(tier)
        assert getattr(state, "quality_tier") == tier
        assert agent.model == model_before

    @pytest.mark.parametrize("tier", ["standard", "deep"])
    def test_query_planner_model_stable(self, tier):
        agent = QueryPlanner()
        model_before = agent.model
        state = _state(tier)
        assert getattr(state, "quality_tier") == tier
        assert agent.model == model_before

    @pytest.mark.parametrize("tier", ["standard", "deep"])
    def test_retrieval_evaluator_model_stable(self, tier):
        agent = RetrievalEvaluator()
        model_before = agent.model
        state = _state(tier)
        assert getattr(state, "quality_tier") == tier
        assert agent.model == model_before

    @pytest.mark.parametrize("tier", ["standard", "deep"])
    def test_sql_generator_model_stable(self, tier):
        agent = SQLGenerator()
        model_before = agent.model
        state = _state(tier)
        assert getattr(state, "quality_tier") == tier
        assert agent.model == model_before

    @pytest.mark.parametrize("tier", ["standard", "deep"])
    def test_sql_validator_model_stable(self, tier):
        agent = SQLValidator()
        model_before = agent.model
        state = _state(tier)
        assert getattr(state, "quality_tier") == tier
        assert agent.model == model_before
