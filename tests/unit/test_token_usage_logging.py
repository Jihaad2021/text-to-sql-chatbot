"""
Unit tests: token usage logging infrastructure.

Covers:
- LLMBaseAgent._last_usage set by provider methods
- LLMBaseAgent._record_token_usage reads _last_usage and calls log_token_usage
- _record_token_usage is a no-op when _last_usage is None
- session_id / request_id / quality_tier flow from AgentState to log_token_usage
"""

from unittest.mock import MagicMock, call, patch

import pytest

from src.agents.intent_classifier import IntentClassifier
from src.models.agent_state import AgentState


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _state(**kwargs) -> AgentState:
    defaults = {
        "query": "test",
        "database": "financial_db",
        "request_id": "req-123",
        "session_id": "s1234567890",
        "quality_tier": "standard",
    }
    defaults.update(kwargs)
    return AgentState(**defaults)


def _make_agent() -> IntentClassifier:
    """IntentClassifier is the simplest LLMBaseAgent — use it as the test subject."""
    return IntentClassifier()


# ─────────────────────────────────────────────────────────────
# _last_usage set by _call_openai
# ─────────────────────────────────────────────────────────────

class TestLastUsageSetByProvider:

    def test_last_usage_set_after_openai_call(self):
        agent = _make_agent()
        if agent.provider not in ("openai", "openrouter", "gemini", "groq"):
            pytest.skip(f"provider={agent.provider}")

        usage_mock = MagicMock()
        usage_mock.prompt_tokens     = 42
        usage_mock.completion_tokens = 10
        usage_mock.total_tokens      = 52

        response_mock = MagicMock()
        response_mock.usage = usage_mock
        response_mock.choices[0].message.content = "yes"

        assert agent._last_usage is None

        with patch.object(agent.client.chat.completions, "create", return_value=response_mock):
            agent._call_llm("hello")

        assert agent._last_usage == {
            "prompt_tokens":     42,
            "completion_tokens": 10,
            "total_tokens":      52,
        }

    def test_last_usage_none_before_any_call(self):
        agent = _make_agent()
        assert agent._last_usage is None


# ─────────────────────────────────────────────────────────────
# _record_token_usage
# ─────────────────────────────────────────────────────────────

class TestRecordTokenUsage:

    def test_noop_when_last_usage_is_none(self):
        agent = _make_agent()
        agent._last_usage = None
        state = _state()

        with patch("src.core.token_logger.log_token_usage") as mock_log:
            agent._record_token_usage(state, model="gpt-4o-mini")
            mock_log.assert_not_called()

    def test_calls_log_token_usage_when_last_usage_set(self):
        agent = _make_agent()
        agent._last_usage = {
            "prompt_tokens":     100,
            "completion_tokens": 50,
            "total_tokens":      150,
        }
        state = _state()

        with patch("src.core.token_logger.log_token_usage") as mock_log:
            agent._record_token_usage(state, model="gpt-4o-mini")
            mock_log.assert_called_once_with(
                request_id="req-123",
                session_id="s1234567890",
                agent_name=agent.name,
                model="gpt-4o-mini",
                quality_tier="standard",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                iteration=None,
            )

    def test_passes_iteration_when_provided(self):
        agent = _make_agent()
        agent._last_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        state = _state()

        with patch("src.core.token_logger.log_token_usage") as mock_log:
            agent._record_token_usage(state, model="gpt-4o-mini", iteration=2)
            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            assert kwargs["iteration"] == 2

    def test_passes_deep_quality_tier(self):
        agent = _make_agent()
        agent._last_usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        state = _state(quality_tier="deep")

        with patch("src.core.token_logger.log_token_usage") as mock_log:
            agent._record_token_usage(state, model="gpt-4.1-mini")
            _, kwargs = mock_log.call_args
            assert kwargs["quality_tier"] == "deep"
            assert kwargs["model"] == "gpt-4.1-mini"

    def test_fallback_request_id_when_none(self):
        agent = _make_agent()
        agent._last_usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        state = _state(request_id=None)

        with patch("src.core.token_logger.log_token_usage") as mock_log:
            agent._record_token_usage(state, model="gpt-4o-mini")
            _, kwargs = mock_log.call_args
            assert kwargs["request_id"] == "unknown"

    def test_session_id_can_be_none(self):
        agent = _make_agent()
        agent._last_usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        state = _state(session_id=None)

        with patch("src.core.token_logger.log_token_usage") as mock_log:
            agent._record_token_usage(state, model="gpt-4o-mini")
            _, kwargs = mock_log.call_args
            assert kwargs["session_id"] is None


# ─────────────────────────────────────────────────────────────
# AgentState fields
# ─────────────────────────────────────────────────────────────

class TestAgentStateFields:

    def test_session_id_defaults_to_none(self):
        state = AgentState(query="x")
        assert state.session_id is None

    def test_request_id_defaults_to_none(self):
        state = AgentState(query="x")
        assert state.request_id is None

    def test_session_id_set(self):
        state = AgentState(query="x", session_id="s123")
        assert state.session_id == "s123"

    def test_request_id_set(self):
        state = AgentState(query="x", request_id="req-abc")
        assert state.request_id == "req-abc"


# ─────────────────────────────────────────────────────────────
# Intent classifier integration: _record_token_usage called
# ─────────────────────────────────────────────────────────────

class TestIntentClassifierLogsUsage:
    """Verify IntentClassifier.execute() calls _record_token_usage after _call_llm."""

    def test_execute_calls_record_token_usage(self):
        agent = _make_agent()
        state = _state()

        mock_intent = {
            "category": "simple_select",
            "segment": "general",
            "confidence": 0.9,
            "needs_clarification": False,
            "clarification_reason": None,
        }

        with patch.object(agent, "_call_llm", return_value='{"category":"simple_select","segment":"general","confidence":0.9,"needs_clarification":false,"clarification_reason":null}'):
            with patch.object(agent, "_record_token_usage") as mock_record:
                agent.execute(state)
                mock_record.assert_called_once()
                _, kwargs = mock_record.call_args
                assert kwargs["model"] == agent.model
