"""
Unit tests for ResponsePlanner.

Tests cover:
- _parse_plan: parses valid JSON, strips markdown fences, sanitizes fields
- _parse_plan: leading_answer with non-null anchor → auto-fixed to null
- _parse_plan: detail_reference → forced to last section id
- _parse_plan: invalid visual type → block skipped
- _parse_plan: duplicate blocks → deduped
- _parse_plan: invalid response_length → defaults to "standard"
- _parse_plan: anomaly_callout block → anomaly_flag=True
- _compute_needs_visual: no blocks → False
- _compute_needs_visual: row_count < 2 → False
- _compute_needs_visual: single scalar + "brief" → False
- _compute_needs_visual: ≥2 rows → True
- _compute_needs_visual: multi-step with any step ≥2 rows → True
- _enforce_chart_rules: donut + entity_count > 6 → bar_chart
- _enforce_chart_rules: bar + pct_change + no time → diverging_bar_chart
- _enforce_chart_rules: ab_pairs → grouped_bar_chart injected
- _apply_anomaly_flag: detect_anomaly returns is_anomaly → flag set
- _apply_anomaly_flag: already True → unchanged
- execute: no data → default plan returned immediately
- _default_plan: root_cause_analysis → "detailed"
- _default_plan: aggregation → "standard"
- _build_data_shape: time column detection
- _shape_for_cols: has_time=False when distinct time values < 2
"""

import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from src.agents.response_planner import ResponsePlanner
from src.models.agent_state import AgentState, StepResult, ToolCallResult


@pytest.fixture
def planner():
    """ResponsePlanner with mocked LLM client."""
    with patch.object(ResponsePlanner, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        p = ResponsePlanner()
        p.model = "gpt-4o-mini"
        return p


def _minimal_plan_json(
    sections=None,
    visual_blocks=None,
    response_length="standard",
    needs_visual=True,
    key_metrics=None,
) -> str:
    if sections is None:
        sections = [{"id": "s1", "title": None, "instruction": "Direct answer."}]
    if visual_blocks is None:
        visual_blocks = [{"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"}]
    return json.dumps({
        "narrative_sections": sections,
        "visual_blocks":      visual_blocks,
        "needs_visual":       needs_visual,
        "key_metrics":        key_metrics or ["total_trx"],
        "response_length":    response_length,
    })


# ── _parse_plan ────────────────────────────────────────────────────────────────

class TestParsePlan:

    def test_valid_json_returns_clean_plan(self, planner):
        plan = planner._parse_plan(_minimal_plan_json())
        assert "narrative_sections" in plan
        assert "visual_blocks" in plan
        assert plan["response_length"] == "standard"

    def test_strips_markdown_fences(self, planner):
        raw = "```json\n" + _minimal_plan_json() + "\n```"
        plan = planner._parse_plan(raw)
        assert plan["narrative_sections"]

    def test_invalid_visual_type_skipped(self, planner):
        raw = _minimal_plan_json(visual_blocks=[
            {"type": "magic_hologram", "anchor_after": None, "purpose": "leading_answer"}
        ])
        plan = planner._parse_plan(raw)
        assert all(b["type"] != "magic_hologram" for b in plan["visual_blocks"])

    def test_leading_answer_anchor_auto_fixed_to_null(self, planner):
        """LLM frequently emits anchor_after='s1' for leading_answer — must be nulled."""
        raw = _minimal_plan_json(visual_blocks=[
            {"type": "bar_chart", "anchor_after": "s1", "purpose": "leading_answer"}
        ])
        plan = planner._parse_plan(raw)
        block = next(b for b in plan["visual_blocks"] if b["purpose"] == "leading_answer")
        assert block["anchor_after"] is None

    def test_detail_reference_forced_to_last_section(self, planner):
        sections = [
            {"id": "s1", "title": None, "instruction": "x"},
            {"id": "s2", "title": "## Detail", "instruction": "y"},
        ]
        raw = _minimal_plan_json(
            sections=sections,
            visual_blocks=[
                {"type": "data_table", "anchor_after": "s1", "purpose": "detail_reference"}
            ]
        )
        plan = planner._parse_plan(raw)
        block = next(b for b in plan["visual_blocks"] if b["purpose"] == "detail_reference")
        assert block["anchor_after"] == "s2"

    def test_invalid_purpose_defaults_to_supporting_evidence(self, planner):
        raw = _minimal_plan_json(visual_blocks=[
            {"type": "bar_chart", "anchor_after": "s1", "purpose": "unknown_purpose"}
        ])
        plan = planner._parse_plan(raw)
        assert plan["visual_blocks"][0]["purpose"] == "supporting_evidence"

    def test_duplicate_blocks_deduped(self, planner):
        raw = _minimal_plan_json(visual_blocks=[
            {"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"},
            {"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        plan = planner._parse_plan(raw)
        leading = [b for b in plan["visual_blocks"] if b["purpose"] == "leading_answer"]
        assert len(leading) == 1

    def test_invalid_response_length_defaults_to_standard(self, planner):
        raw = _minimal_plan_json(response_length="ultra_detailed")
        plan = planner._parse_plan(raw)
        assert plan["response_length"] == "standard"

    def test_anomaly_callout_sets_anomaly_flag(self, planner):
        raw = _minimal_plan_json(visual_blocks=[
            {"type": "anomaly_callout", "anchor_after": "s1", "purpose": "supporting_evidence"}
        ])
        plan = planner._parse_plan(raw)
        assert plan["anomaly_flag"] is True

    def test_no_anomaly_callout_anomaly_flag_false(self, planner):
        raw = _minimal_plan_json()
        plan = planner._parse_plan(raw)
        assert plan["anomaly_flag"] is False

    def test_empty_sections_gets_default(self, planner):
        raw = json.dumps({"narrative_sections": [], "visual_blocks": [],
                          "needs_visual": False, "key_metrics": [], "response_length": "standard"})
        plan = planner._parse_plan(raw)
        assert len(plan["narrative_sections"]) >= 1
        assert plan["narrative_sections"][0]["id"] == "s1"

    def test_blocks_sorted_leading_answer_first(self, planner):
        sections = [{"id": "s1", "title": None, "instruction": "x"}]
        raw = _minimal_plan_json(
            sections=sections,
            visual_blocks=[
                {"type": "data_table", "anchor_after": "s1", "purpose": "detail_reference"},
                {"type": "bar_chart",  "anchor_after": None, "purpose": "leading_answer"},
            ]
        )
        plan = planner._parse_plan(raw)
        assert plan["visual_blocks"][0]["purpose"] == "leading_answer"


# ── _compute_needs_visual ──────────────────────────────────────────────────────

class TestComputeNeedsVisual:

    def _state_with_result(self, rows: list[dict], row_count: int | None = None) -> AgentState:
        state = AgentState(query="test", database="financial_db")
        state.query_result = rows
        state.row_count = row_count if row_count is not None else len(rows)
        return state

    def test_no_visual_blocks_returns_false(self, planner):
        state = self._state_with_result([{"a": 1}, {"b": 2}])
        plan = {"visual_blocks": [], "response_length": "standard"}
        assert planner._compute_needs_visual(state, plan) is False

    def test_row_count_less_than_2_returns_false(self, planner):
        state = self._state_with_result([{"total": 100}], row_count=1)
        plan = {"visual_blocks": [{"type": "bar_chart"}], "response_length": "standard"}
        assert planner._compute_needs_visual(state, plan) is False

    def test_single_scalar_with_brief_returns_false(self, planner):
        state = self._state_with_result([{"total": 100}], row_count=1)
        plan = {"visual_blocks": [{"type": "kpi_grid"}], "response_length": "brief"}
        assert planner._compute_needs_visual(state, plan) is False

    def test_two_rows_with_blocks_returns_true(self, planner):
        state = self._state_with_result([{"partner": "GoPay", "total": 1}, {"partner": "OVO", "total": 2}])
        plan = {"visual_blocks": [{"type": "bar_chart"}], "response_length": "standard"}
        assert planner._compute_needs_visual(state, plan) is True

    def test_multi_step_any_step_with_two_rows_returns_true(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.is_multi_step = True
        state.step_results = [
            StepResult(step_number=1, description="d1", sql="s1", data=[{"x": 1}], row_count=1, summary=""),
            StepResult(step_number=2, description="d2", sql="s2",
                       data=[{"x": 1}, {"x": 2}], row_count=2, summary=""),
        ]
        plan = {"visual_blocks": [{"type": "line_chart"}], "response_length": "standard"}
        assert planner._compute_needs_visual(state, plan) is True

    def test_tool_results_with_two_rows_returns_true(self, planner):
        state = AgentState(query="test", database="financial_db")
        tr = ToolCallResult(
            tool_name="detect_anomaly",
            data=[{"partner": "GoPay", "is_anomaly": True}, {"partner": "OVO", "is_anomaly": False}],
            row_count=2,
            sql_or_params="{}",
            description="anomaly check",
        )
        state.tool_results = [tr]
        plan = {"visual_blocks": [{"type": "bar_chart"}], "response_length": "standard"}
        assert planner._compute_needs_visual(state, plan) is True


# ── _enforce_chart_rules ───────────────────────────────────────────────────────

class TestEnforceChartRules:

    def _state_with_data(self, cols: list[str], rows: list[dict]) -> AgentState:
        state = AgentState(query="test", database="financial_db")
        state.query_result = rows
        state.row_count = len(rows)
        state.is_multi_step = False
        state.step_results = []
        state.tool_results = []
        return state

    def test_donut_with_more_than_6_entities_becomes_bar(self, planner):
        rows = [{"share_pct": i, "partner": f"P{i}"} for i in range(8)]
        state = self._state_with_data(["share_pct", "partner"], rows)
        plan = {
            "visual_blocks": [{"type": "donut_chart", "anchor_after": None, "purpose": "leading_answer"}],
            "narrative_sections": [{"id": "s1"}],
        }
        result = planner._enforce_chart_rules(state, plan)
        assert any(b["type"] == "bar_chart" for b in result["visual_blocks"])

    def test_bar_with_pct_change_and_no_time_becomes_diverging_bar(self, planner):
        rows = [
            {"partner": "GoPay", "pct_change": 5.0},
            {"partner": "OVO",   "pct_change": -2.0},
        ]
        state = self._state_with_data(["partner", "pct_change"], rows)
        plan = {
            "visual_blocks": [{"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"}],
            "narrative_sections": [{"id": "s1"}],
        }
        result = planner._enforce_chart_rules(state, plan)
        assert any(b["type"] == "diverging_bar_chart" for b in result["visual_blocks"])

    def test_ab_pairs_inject_grouped_bar_chart(self, planner):
        rows = [{"partner": "GoPay", "trx_a": 100, "trx_b": 90}]
        state = self._state_with_data(["partner", "trx_a", "trx_b"], rows)
        plan = {
            "visual_blocks": [{"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"}],
            "narrative_sections": [{"id": "s1"}],
        }
        result = planner._enforce_chart_rules(state, plan)
        assert any(b["type"] == "grouped_bar_chart" for b in result["visual_blocks"])

    def test_ab_pairs_no_duplicate_grouped_bar_injected(self, planner):
        """If grouped_bar_chart already exists, rule should not inject a second one."""
        rows = [{"partner": "GoPay", "trx_a": 100, "trx_b": 90}]
        state = self._state_with_data(["partner", "trx_a", "trx_b"], rows)
        plan = {
            "visual_blocks": [
                {"type": "grouped_bar_chart", "anchor_after": "s1", "purpose": "supporting_evidence"},
            ],
            "narrative_sections": [{"id": "s1"}],
        }
        result = planner._enforce_chart_rules(state, plan)
        grouped = [b for b in result["visual_blocks"] if b["type"] == "grouped_bar_chart"]
        assert len(grouped) == 1

    def test_multi_step_state_skips_chart_rule_enforcement(self, planner):
        """Chart rules only run on single-step paths."""
        state = AgentState(query="test", database="financial_db")
        state.is_multi_step = True
        state.query_result = []
        state.tool_results = []
        plan = {
            "visual_blocks": [{"type": "donut_chart", "anchor_after": None, "purpose": "leading_answer"}],
            "narrative_sections": [{"id": "s1"}],
        }
        result = planner._enforce_chart_rules(state, plan)
        assert result["visual_blocks"][0]["type"] == "donut_chart"


# ── _apply_anomaly_flag ────────────────────────────────────────────────────────

class TestApplyAnomalyFlag:

    def test_detect_anomaly_with_is_anomaly_row_sets_flag(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.tool_results = [
            ToolCallResult(
                tool_name="detect_anomaly",
                data=[{"partner": "GoPay", "is_anomaly": True}],
                row_count=1,
                sql_or_params="{}",
                description="anomaly",
            )
        ]
        plan = {"anomaly_flag": False}
        result = planner._apply_anomaly_flag(state, plan)
        assert result["anomaly_flag"] is True

    def test_detect_anomaly_no_anomaly_rows_flag_stays_false(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.tool_results = [
            ToolCallResult(
                tool_name="detect_anomaly",
                data=[{"partner": "GoPay", "is_anomaly": False}],
                row_count=1,
                sql_or_params="{}",
                description="anomaly",
            )
        ]
        plan = {"anomaly_flag": False}
        result = planner._apply_anomaly_flag(state, plan)
        assert result["anomaly_flag"] is False

    def test_anomaly_flag_already_true_unchanged(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.tool_results = []
        plan = {"anomaly_flag": True}
        result = planner._apply_anomaly_flag(state, plan)
        assert result["anomaly_flag"] is True

    def test_no_tool_results_flag_unchanged(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.tool_results = []
        plan = {"anomaly_flag": False}
        result = planner._apply_anomaly_flag(state, plan)
        assert result["anomaly_flag"] is False


# ── execute ────────────────────────────────────────────────────────────────────

class TestExecute:

    def test_no_data_returns_default_plan(self, planner):
        state = AgentState(query="test", database="financial_db")
        result = planner.run(state)
        assert result.layout_plan is not None
        assert "narrative_sections" in result.layout_plan
        assert result.layout_plan["needs_visual"] is False

    def test_execute_with_data_calls_llm(self, planner):
        state = AgentState(query="berapa total transaksi?", database="financial_db")
        state.query_result = [{"total": 100}, {"total": 200}]
        state.row_count = 2

        llm_response = _minimal_plan_json()
        with patch.object(planner, "_call_llm", return_value=llm_response):
            result = planner.run(state)

        assert result.layout_plan is not None
        assert "narrative_sections" in result.layout_plan

    def test_llm_exception_falls_back_to_default_plan(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.query_result = [{"total": 100}]
        state.row_count = 1

        with patch.object(planner, "_call_llm", side_effect=RuntimeError("API down")):
            result = planner.run(state)

        assert result.layout_plan is not None
        assert result.layout_plan["needs_visual"] is False

    def test_complex_analytics_intent_forces_detailed_length(self, planner):
        state = AgentState(query="analisis tren", database="financial_db")
        state.intent = {"category": "complex_analytics", "confidence": 0.9,
                        "reason": "complex", "sql_strategy": "..."}
        state.query_result = [{"x": 1}, {"x": 2}]
        state.row_count = 2

        llm_response = _minimal_plan_json(response_length="standard")
        with patch.object(planner, "_call_llm", return_value=llm_response):
            result = planner.run(state)

        assert result.layout_plan["response_length"] == "detailed"


# ── _default_plan ──────────────────────────────────────────────────────────────

class TestDefaultPlan:

    def test_root_cause_intent_gives_detailed_length(self, planner):
        plan = planner._default_plan({"category": "root_cause_analysis"})
        assert plan["response_length"] == "detailed"

    def test_complex_analytics_intent_gives_detailed_length(self, planner):
        plan = planner._default_plan({"category": "complex_analytics"})
        assert plan["response_length"] == "detailed"

    def test_aggregation_intent_gives_standard_length(self, planner):
        plan = planner._default_plan({"category": "aggregation"})
        assert plan["response_length"] == "standard"

    def test_default_plan_has_required_keys(self, planner):
        plan = planner._default_plan("empty")
        for key in ("narrative_sections", "visual_blocks", "needs_visual", "key_metrics",
                    "response_length", "anomaly_flag"):
            assert key in plan


# ── _build_data_shape ──────────────────────────────────────────────────────────

class TestBuildDataShape:

    def test_time_column_detected(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.query_result = [{"date": "2026-04-01", "total": 100}, {"date": "2026-04-02", "total": 200}]
        state.row_count = 2
        state.is_multi_step = False
        state.step_results = []
        state.tool_results = []
        shape = planner._build_data_shape(state)
        assert shape["has_time_dimension"] is True

    def test_single_distinct_date_is_not_time_series(self, planner):
        """WHERE date = '2026-04-01' returns 1 distinct date → not a real time series."""
        state = AgentState(query="test", database="financial_db")
        state.query_result = [
            {"date": "2026-04-01", "partner": "GoPay", "total": 100},
            {"date": "2026-04-01", "partner": "OVO",   "total": 80},
        ]
        state.row_count = 2
        state.is_multi_step = False
        state.step_results = []
        state.tool_results = []
        shape = planner._build_data_shape(state)
        assert shape["has_time_dimension"] is False

    def test_pct_change_column_detected(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.query_result = [{"partner": "GoPay", "pct_change": 5.0}]
        state.row_count = 1
        state.is_multi_step = False
        state.step_results = []
        state.tool_results = []
        shape = planner._build_data_shape(state)
        assert shape["has_pct_change_column"] is True

    def test_ab_pairs_detected(self, planner):
        state = AgentState(query="test", database="financial_db")
        state.query_result = [{"partner": "GoPay", "trx_a": 100, "trx_b": 90}]
        state.row_count = 1
        state.is_multi_step = False
        state.step_results = []
        state.tool_results = []
        shape = planner._build_data_shape(state)
        assert shape["has_ab_pair_columns"] is True
