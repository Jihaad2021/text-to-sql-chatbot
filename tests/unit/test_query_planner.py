"""
Unit tests for QueryPlanner.

Tests cover:
- _parse_response: valid JSON → plan dict
- _parse_response: strips markdown fences
- _parse_response: broken JSON → single-step fallback
- _parse_response: missing required keys → fallback
- _validate_plan: SQL sub_query → rejected (triggers fallback)
- _validate_plan: analytical sub_query → warns but does not raise
- _single_step_fallback: wraps original query
- execute: writes is_multi_step and execution_plan to state
- execute: single-step LLM response → 1 step
- execute: multi-step LLM response → multiple ExecutionStep objects
- _build_history_block: empty → empty string
- _build_history_block: with history → recent turns included
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.query_planner import QueryPlanner
from src.models.agent_state import AgentState, ExecutionStep


@pytest.fixture
def planner():
    """QueryPlanner with mocked LLM client so no real API calls are made."""
    with patch.object(QueryPlanner, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return QueryPlanner()


def _single_step_json(query: str = "berapa total transaksi April?") -> str:
    return json.dumps({
        "is_multi_step": False,
        "steps": [
            {"step_number": 1, "description": "Total transaksi", "sub_query": query, "depends_on": []}
        ]
    })


def _multi_step_json() -> str:
    return json.dumps({
        "is_multi_step": True,
        "steps": [
            {"step_number": 1, "description": "Data April", "sub_query": "total transaksi April 2026", "depends_on": []},
            {"step_number": 2, "description": "Data Maret", "sub_query": "total transaksi Maret 2026", "depends_on": []},
        ]
    })


# ── _parse_response ────────────────────────────────────────────────────────────

class TestParseResponse:

    def test_valid_single_step_json(self, planner):
        raw = _single_step_json()
        plan = planner._parse_response(raw, "fallback query")
        assert plan["is_multi_step"] is False
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["sub_query"] == "berapa total transaksi April?"

    def test_valid_multi_step_json(self, planner):
        raw = _multi_step_json()
        plan = planner._parse_response(raw, "fallback query")
        assert plan["is_multi_step"] is True
        assert len(plan["steps"]) == 2

    def test_strips_markdown_fences(self, planner):
        raw = "```json\n" + _single_step_json() + "\n```"
        plan = planner._parse_response(raw, "fallback query")
        assert plan["is_multi_step"] is False

    def test_broken_json_falls_back_to_single_step(self, planner):
        plan = planner._parse_response("{ not valid json", "original query")
        assert plan["is_multi_step"] is False
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["sub_query"] == "original query"

    def test_missing_is_multi_step_key_falls_back(self, planner):
        raw = json.dumps({"steps": [{"step_number": 1, "sub_query": "x", "description": "d", "depends_on": []}]})
        plan = planner._parse_response(raw, "original query")
        assert plan["steps"][0]["sub_query"] == "original query"

    def test_empty_steps_list_falls_back(self, planner):
        raw = json.dumps({"is_multi_step": False, "steps": []})
        plan = planner._parse_response(raw, "original query")
        assert plan["steps"][0]["sub_query"] == "original query"

    def test_sql_in_sub_query_falls_back(self, planner):
        raw = json.dumps({
            "is_multi_step": False,
            "steps": [
                {"step_number": 1, "description": "d", "sub_query": "SELECT * FROM daily_master", "depends_on": []}
            ]
        })
        plan = planner._parse_response(raw, "original query")
        assert plan["steps"][0]["sub_query"] == "original query"


# ── _validate_plan ─────────────────────────────────────────────────────────────

class TestValidatePlan:

    def test_analytical_sub_query_warns_but_does_not_raise(self, planner, caplog):
        import logging
        plan = {
            "is_multi_step": True,
            "steps": [
                {"step_number": 1, "description": "Step 1", "sub_query": "total transaksi April", "depends_on": []},
                {"step_number": 2, "description": "Step 2", "sub_query": "bandingkan hasil langkah 1 dan langkah 2", "depends_on": [1]},
            ]
        }
        with caplog.at_level(logging.WARNING):
            planner._validate_plan(plan)
        assert any("analytical" in r.message.lower() or "bandingkan" in r.message.lower() for r in caplog.records)


# ── _single_step_fallback ──────────────────────────────────────────────────────

class TestSingleStepFallback:

    def test_wraps_query_as_sub_query(self, planner):
        plan = planner._single_step_fallback("berapa revenue GoPay?")
        assert plan["is_multi_step"] is False
        assert plan["steps"][0]["sub_query"] == "berapa revenue GoPay?"

    def test_fallback_has_exactly_one_step(self, planner):
        plan = planner._single_step_fallback("any query")
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["step_number"] == 1
        assert plan["steps"][0]["depends_on"] == []


# ── execute ────────────────────────────────────────────────────────────────────

class TestExecute:

    def test_single_step_writes_state(self, planner):
        state = AgentState(query="berapa total transaksi April?", database="financial_db")
        with patch.object(planner, "_call_llm", return_value=_single_step_json()):
            result = planner.run(state)

        assert result.is_multi_step is False
        assert len(result.execution_plan) == 1
        assert isinstance(result.execution_plan[0], ExecutionStep)

    def test_multi_step_writes_state(self, planner):
        state = AgentState(query="bandingkan April vs Maret", database="financial_db")
        with patch.object(planner, "_call_llm", return_value=_multi_step_json()):
            result = planner.run(state)

        assert result.is_multi_step is True
        assert len(result.execution_plan) == 2

    def test_execution_plan_steps_have_correct_fields(self, planner):
        state = AgentState(query="bandingkan April vs Maret", database="financial_db")
        with patch.object(planner, "_call_llm", return_value=_multi_step_json()):
            result = planner.run(state)

        step1 = result.execution_plan[0]
        assert step1.step_number == 1
        assert step1.sub_query == "total transaksi April 2026"
        assert isinstance(step1.depends_on, list)

    def test_llm_failure_falls_back_to_single_step(self, planner):
        state = AgentState(query="any query", database="financial_db")
        with patch.object(planner, "_call_llm", return_value="BROKEN"):
            result = planner.run(state)

        assert result.is_multi_step is False
        assert len(result.execution_plan) == 1
        assert result.execution_plan[0].sub_query == "any query"


# ── _build_history_block ───────────────────────────────────────────────────────

class TestBuildHistoryBlock:

    def test_empty_history_returns_empty_string(self, planner):
        assert planner._build_history_block([]) == ""

    def test_history_block_includes_recent_turns(self, planner):
        history = [
            {"query": "berapa transaksi bulan lalu?", "insights": "Bulan lalu ada 1 juta transaksi."},
            {"query": "dan bulan ini?", "insights": "Bulan ini sudah 800 ribu."},
        ]
        block = planner._build_history_block(history)
        assert "berapa transaksi bulan lalu?" in block
        assert "dan bulan ini?" in block

    def test_history_block_truncates_long_insights(self, planner):
        long_insight = "X" * 300
        history = [{"query": "test", "insights": long_insight}]
        block = planner._build_history_block(history)
        assert "..." in block
        assert len(block) < 600

    def test_history_block_capped_at_max_turns(self, planner):
        history = [{"query": f"query {i}", "insights": "short"} for i in range(10)]
        block = planner._build_history_block(history)
        assert "query 9" in block
        assert "query 0" not in block
