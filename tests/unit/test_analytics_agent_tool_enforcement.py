"""
AnalyticsAgent — unit tests for tool call enforcement.

Regression guard for the "success rate" zero-tool failure discovered via
10-run forensic (2026-07-03): Gemini 2.5 Flash would bypass tool calls for
queries containing "success rate" / "SR", violating the mandatory-tool rule.

Root causes fixed:
  1. compare_periods / detect_anomaly descriptions now explicitly mention
     "success rate (SR)" so the LLM recognises tool relevance.
  2. tool_choice="required" on iteration 0 enforces the rule structurally.

Test strategy:
  - Mock the LLM client so no real API calls are made.
  - TC1: query with "success rate" → tool_calls must be non-empty.
  - TC2: query without success rate keyword → tool_calls still non-empty.
  Both tests assert that state.tool_calls is populated and state.row_count > 0.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.analytics_agent import AnalyticsAgent
from src.models.agent_state import AgentState

# ── Shared mock data ──────────────────────────────────────────────────────

_COMPARE_ROW = {
    "entity":        "gopay",
    "trx_a":         5_000_000,
    "trx_b":         5_500_000,
    "trx_pct_change": -9.09,
    "rev_a":         100_000_000,
    "rev_b":         110_000_000,
    "rev_pct_change": -9.09,
    "sr_a":          97.5,
    "sr_b":          98.2,
    "sr_pct_change": -0.7,
}

_COMPARE_DATA = [_COMPARE_ROW] * 5


def _make_openai_tool_call_response(tool_name: str, arguments: dict) -> MagicMock:
    """Build a minimal OpenAI-style message mock that contains a single tool call."""
    tc = MagicMock()
    tc.function.name      = tool_name
    tc.function.arguments = json.dumps(arguments)
    tc.id                 = "call_abc123"

    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content    = None

    stop_msg = MagicMock()
    stop_msg.tool_calls = None
    stop_msg.content    = "GoPay success rate turun 0.7 pp dari 98.2% menjadi 97.5%."

    choice1 = MagicMock()
    choice1.message = msg

    choice2 = MagicMock()
    choice2.message = stop_msg

    resp1 = MagicMock()
    resp1.choices = [choice1]

    resp2 = MagicMock()
    resp2.choices = [choice2]

    return [resp1, resp2]


def _make_execute_tool_result(data: list[dict]) -> dict:
    return {
        "data":        data,
        "row_count":   len(data),
        "sql":         "SELECT ...",
        "description": "Compare partner periods",
    }


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def agent():
    """AnalyticsAgent with mocked LLM client and DB engine."""
    with patch.object(AnalyticsAgent, "_init_client",
                      return_value=("openrouter", MagicMock(), "google/gemini-2.5-flash")), \
         patch.object(AnalyticsAgent, "_init_engines",
                      return_value={"financial_db": MagicMock()}):
        return AnalyticsAgent()


# ── TC1: query with "success rate" keyword MUST call a tool ──────────────

class TestSuccessRateQueryEnforcement:
    """
    Regression test for the zero-tool failure on "success rate" queries.

    Before fix: Gemini concluded no tool covers "success rate" and answered
    without calling any tool (tool_calls=None, row_count=0).
    After fix: tool descriptions mention SR + tool_choice="required" on iter 0.
    """

    def test_success_rate_query_calls_tool(self, agent):
        """Query containing 'success rate' must result in at least one tool call."""
        state = AgentState(
            query="kenapa success rate GoPay turun bulan Juni 2026?",
            database="financial_db",
        )

        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {
                "period_a_start": "2026-06-01",
                "period_a_end":   "2026-06-30",
                "period_b_start": "2026-05-01",
                "period_b_end":   "2026-05-31",
                "dimension":      "partner",
            },
        )
        agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            result = agent.run(state)

        assert result.tool_calls, (
            "tool_calls must be non-empty for 'success rate' query — "
            "Type B failure (no tool called) must not occur"
        )
        assert result.row_count > 0, "row_count must be > 0 when tool returned data"
        # sr_pct_change must be present in the returned data
        assert "sr_pct_change" in result.query_result[0], (
            "compare_periods result must include sr_pct_change column"
        )

    def test_sr_abbreviation_query_calls_tool(self, agent):
        """Query using 'SR' abbreviation must also result in a tool call."""
        state = AgentState(
            query="analisis penurunan SR GoPay di Juni 2026",
            database="financial_db",
        )

        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {
                "period_a_start": "2026-06-01",
                "period_a_end":   "2026-06-30",
                "period_b_start": "2026-05-01",
                "period_b_end":   "2026-05-31",
            },
        )
        agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            result = agent.run(state)

        assert result.tool_calls, (
            "tool_calls must be non-empty for 'SR' abbreviation query"
        )
        assert result.row_count > 0


# ── TC2: tool_choice="required" on iteration 0 ───────────────────────────

class TestToolChoiceRequired:
    """
    Structural enforcement: the first API call must use tool_choice="required",
    not "auto". Verifies fix 2 is wired correctly regardless of query content.
    """

    def test_first_iteration_uses_required(self, agent):
        """tool_choice must be 'required' on the first completions.create call."""
        state = AgentState(
            query="kenapa success rate GoPay turun bulan Juni 2026?",
            database="financial_db",
        )

        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {"period_a_start": "2026-06-01", "period_a_end": "2026-06-30",
             "period_b_start": "2026-05-01", "period_b_end": "2026-05-31"},
        )
        agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            agent.run(state)

        first_call_kwargs = agent.client.chat.completions.create.call_args_list[0].kwargs
        assert first_call_kwargs.get("tool_choice") == "required", (
            "First iteration must use tool_choice='required' to structurally "
            "enforce the mandatory-tool rule"
        )

    def test_subsequent_iteration_uses_auto(self, agent):
        """tool_choice on iteration 1+ must be 'auto' (not 'required')."""
        state = AgentState(
            query="kenapa success rate GoPay turun bulan Juni 2026?",
            database="financial_db",
        )

        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {"period_a_start": "2026-06-01", "period_a_end": "2026-06-30",
             "period_b_start": "2026-05-01", "period_b_end": "2026-05-31"},
        )
        agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            agent.run(state)

        # Second call (iteration 1) should be "auto"
        calls = agent.client.chat.completions.create.call_args_list
        if len(calls) > 1:
            second_call_kwargs = calls[1].kwargs
            assert second_call_kwargs.get("tool_choice") == "auto", (
                "Subsequent iterations must use tool_choice='auto'"
            )


# ── TC3: max_tokens / max_completion_tokens per iteration ────────────────

class TestMaxTokensPerIteration:
    """
    Regression guard for the missing max_tokens bug (2026-07-10).

    Before fix: _run_openai_compatible() called completions.create() without any
    token limit — reasoning models (o4-mini etc.) can bill reasoning tokens as
    output and cost 10× without a cap.
    After fix: every iteration passes max_tokens=_OPENAI_MAX_TOKENS_PER_ITER for
    standard models, or max_completion_tokens=_OPENAI_MAX_TOKENS_PER_ITER for
    reasoning models.
    """

    def test_standard_model_passes_max_tokens(self, agent):
        """Standard (non-reasoning) model → each call must have max_tokens set."""
        state = AgentState(
            query="kenapa success rate GoPay turun bulan Juni 2026?",
            database="financial_db",
        )
        # Fixture uses "google/gemini-2.5-flash" — not a reasoning model.
        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {"period_a_start": "2026-06-01", "period_a_end": "2026-06-30",
             "period_b_start": "2026-05-01", "period_b_end": "2026-05-31"},
        )
        agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            agent.run(state)

        from src.agents.analytics_agent import _OPENAI_MAX_TOKENS_PER_ITER
        for i, call in enumerate(agent.client.chat.completions.create.call_args_list):
            kw = call.kwargs
            assert "max_tokens" in kw, (
                f"Iteration {i}: max_tokens must be set for standard models — "
                "missing means unbounded output (cost risk)"
            )
            assert kw["max_tokens"] == _OPENAI_MAX_TOKENS_PER_ITER, (
                f"Iteration {i}: max_tokens must equal _OPENAI_MAX_TOKENS_PER_ITER "
                f"({_OPENAI_MAX_TOKENS_PER_ITER}), got {kw['max_tokens']}"
            )
            assert "max_completion_tokens" not in kw, (
                f"Iteration {i}: standard model must NOT use max_completion_tokens"
            )

    def test_standard_model_keeps_temperature_zero(self, agent):
        """Standard model must retain temperature=0 (deterministic responses)."""
        state = AgentState(
            query="analisis SR GoPay Juni 2026",
            database="financial_db",
        )
        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {"period_a_start": "2026-06-01", "period_a_end": "2026-06-30",
             "period_b_start": "2026-05-01", "period_b_end": "2026-05-31"},
        )
        agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            agent.run(state)

        for i, call in enumerate(agent.client.chat.completions.create.call_args_list):
            kw = call.kwargs
            assert kw.get("temperature") == 0, (
                f"Iteration {i}: temperature must be 0 for standard models"
            )

    def test_reasoning_model_passes_max_completion_tokens(self):
        """Reasoning model (o4-mini) → must use max_completion_tokens, no temperature."""
        with patch.object(AnalyticsAgent, "_init_client",
                          return_value=("openai", MagicMock(), "o4-mini")), \
             patch.object(AnalyticsAgent, "_init_engines",
                          return_value={"financial_db": MagicMock()}):
            reasoning_agent = AnalyticsAgent()

        state = AgentState(
            query="kenapa success rate GoPay turun bulan Juni 2026?",
            database="financial_db",
        )
        api_responses = _make_openai_tool_call_response(
            "compare_periods",
            {"period_a_start": "2026-06-01", "period_a_end": "2026-06-30",
             "period_b_start": "2026-05-01", "period_b_end": "2026-05-31"},
        )
        reasoning_agent.client.chat.completions.create.side_effect = api_responses

        with patch("src.agents.analytics_agent.execute_tool",
                   return_value=_make_execute_tool_result(_COMPARE_DATA)):
            reasoning_agent.run(state)

        from src.agents.analytics_agent import _OPENAI_MAX_TOKENS_PER_ITER
        for i, call in enumerate(reasoning_agent.client.chat.completions.create.call_args_list):
            kw = call.kwargs
            assert "max_completion_tokens" in kw, (
                f"Iteration {i}: reasoning model must use max_completion_tokens"
            )
            assert kw["max_completion_tokens"] == _OPENAI_MAX_TOKENS_PER_ITER, (
                f"Iteration {i}: max_completion_tokens must equal "
                f"_OPENAI_MAX_TOKENS_PER_ITER ({_OPENAI_MAX_TOKENS_PER_ITER})"
            )
            assert "max_tokens" not in kw, (
                f"Iteration {i}: reasoning model must NOT use max_tokens"
            )
            assert "temperature" not in kw, (
                f"Iteration {i}: reasoning model must NOT receive temperature param"
            )

    def test_max_tokens_value_matches_constant(self):
        """_OPENAI_MAX_TOKENS_PER_ITER must equal 2000 (documented ceiling design)."""
        from src.agents.analytics_agent import _OPENAI_MAX_TOKENS_PER_ITER
        assert _OPENAI_MAX_TOKENS_PER_ITER == 2000, (
            "Constant must be 2000: 2000 tok/iter × 8 iterations = 16k ceiling. "
            "Change _MAX_TOOL_ITERATIONS or this constant together, not independently."
        )
