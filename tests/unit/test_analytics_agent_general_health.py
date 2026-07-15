"""
Unit tests — AnalyticsAgent general-health checklist (Fase 5).

Covers:
  1. _is_general_health() detection: True only for complex_analytics + general.
  2. _extract_period_from_calls() extracts dates from various tool arg shapes.
  3. _prior_month_range() returns correct prior-month boundaries.
  4. Post-loop guard fires (forces missing tools) for general health queries.
  5. Guard does NOT fire for specific-segment complex_analytics queries.
  6. InsightGenerator section filter removes "distribusi" when get_distribution absent.
  7. InsightGenerator section filter keeps "distribusi" when get_distribution present.
  8. InsightGenerator verdict closing guard appends SEHAT/PERHATIAN/KRITIS when absent.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.analytics_agent import (
    _GENERAL_HEALTH_TOOLS,
    _extract_period_from_calls,
    _is_general_health,
    _prior_month_range,
)
from src.models.agent_state import AgentState, ToolCallResult

# ── _is_general_health ───────────────────────────────────────────────────────

class TestIsGeneralHealth:
    def test_true_for_complex_analytics_general(self):
        state = AgentState(query="analisis kesehatan bisnis")
        state.intent = {"category": "complex_analytics", "segment": "general"}
        assert _is_general_health(state) is True

    def test_false_for_complex_analytics_partners(self):
        state = AgentState(query="analisis gopay")
        state.intent = {"category": "complex_analytics", "segment": "partners"}
        assert _is_general_health(state) is False

    def test_false_for_complex_analytics_channels(self):
        state = AgentState(query="analisis channel")
        state.intent = {"category": "complex_analytics", "segment": "channels"}
        assert _is_general_health(state) is False

    def test_false_for_other_category_general(self):
        state = AgentState(query="berapa total transaksi")
        state.intent = {"category": "aggregation", "segment": "general"}
        assert _is_general_health(state) is False

    def test_false_for_root_cause_general(self):
        state = AgentState(query="kenapa turun")
        state.intent = {"category": "root_cause_analysis", "segment": "general"}
        assert _is_general_health(state) is False

    def test_false_when_intent_is_string(self):
        state = AgentState(query="x")
        state.intent = "complex_analytics"
        assert _is_general_health(state) is False

    def test_false_when_intent_is_none(self):
        state = AgentState(query="x")
        state.intent = None
        assert _is_general_health(state) is False


# ── _extract_period_from_calls ───────────────────────────────────────────────

class TestExtractPeriodFromCalls:
    def test_extracts_from_get_summary_style(self):
        log = [{"tool": "get_summary", "arguments": {"period_start": "2026-06-01", "period_end": "2026-06-30"}, "row_count": 1, "sql": ""}]
        result = _extract_period_from_calls(log)
        assert result == {"period_start": "2026-06-01", "period_end": "2026-06-30"}

    def test_extracts_from_get_trend_style(self):
        log = [{"tool": "get_trend", "arguments": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "row_count": 30, "sql": ""}]
        result = _extract_period_from_calls(log)
        assert result == {"period_start": "2026-06-01", "period_end": "2026-06-30"}

    def test_extracts_from_compare_periods_style(self):
        log = [{"tool": "compare_periods", "arguments": {
            "period_a_start": "2026-06-01", "period_a_end": "2026-06-30",
            "period_b_start": "2026-05-01", "period_b_end": "2026-05-31",
        }, "row_count": 9, "sql": ""}]
        result = _extract_period_from_calls(log)
        assert result == {"period_start": "2026-06-01", "period_end": "2026-06-30"}

    def test_returns_none_for_empty_log(self):
        assert _extract_period_from_calls([]) is None

    def test_returns_none_when_no_date_args(self):
        log = [{"tool": "get_hourly_pattern", "arguments": {}, "row_count": 24, "sql": ""}]
        assert _extract_period_from_calls(log) is None

    def test_uses_first_matching_call(self):
        log = [
            {"tool": "get_summary", "arguments": {"period_start": "2026-06-01", "period_end": "2026-06-30"}, "row_count": 1, "sql": ""},
            {"tool": "get_summary", "arguments": {"period_start": "2026-05-01", "period_end": "2026-05-31"}, "row_count": 1, "sql": ""},
        ]
        result = _extract_period_from_calls(log)
        assert result["period_start"] == "2026-06-01"


# ── _prior_month_range ───────────────────────────────────────────────────────

class TestPriorMonthRange:
    def test_june_prior_is_may(self):
        first, last = _prior_month_range("2026-06-30")
        assert first == "2026-05-01"
        assert last  == "2026-05-31"

    def test_january_prior_is_december(self):
        first, last = _prior_month_range("2026-01-31")
        assert first == "2025-12-01"
        assert last  == "2025-12-31"

    def test_march_prior_is_february(self):
        first, last = _prior_month_range("2026-03-31")
        assert first == "2026-02-01"
        assert last  == "2026-02-28"

    def test_mid_month_end_still_uses_correct_prior(self):
        # period_end mid-month: prior is still the full prior month
        first, last = _prior_month_range("2026-06-15")
        assert first == "2026-05-01"
        assert last  == "2026-05-31"


# ── Post-loop guard integration (mocked execute_tool) ────────────────────────

def _make_openai_responses(tool_responses: list[tuple[str, dict]], final_text: str) -> list[MagicMock]:
    """Build list of OpenAI message mocks: one per tool call, then a stop message."""
    msgs = []
    for tool_name, args in tool_responses:
        tc = MagicMock()
        tc.function.name      = tool_name
        tc.function.arguments = json.dumps(args)
        tc.id                 = f"call_{tool_name}"
        msg = MagicMock()
        msg.tool_calls = [tc]
        msg.content    = None
        msgs.append(msg)
    stop = MagicMock()
    stop.tool_calls = None
    stop.content    = final_text
    msgs.append(stop)
    return msgs


_PERIOD = {"period_start": "2026-06-01", "period_end": "2026-06-30"}
_DUMMY_RESULT = {"data": [{"total_trx": 1}], "row_count": 1, "sql": "SELECT 1", "description": "test"}


def _make_analytics_agent(mock_client: MagicMock):
    """Build AnalyticsAgent with mocked LLM client and DB engine (no real connections)."""
    from src.agents.analytics_agent import AnalyticsAgent
    with (
        patch.object(AnalyticsAgent, "_init_client", return_value=("openai", mock_client, "gpt-4o-mini")),
        patch.object(AnalyticsAgent, "_init_engines", return_value={"financial_db": MagicMock()}),
    ):
        return AnalyticsAgent()


class TestGeneralHealthGuardFires:
    """Guard must force all 5 tools when segment=general, even if LLM only calls 3."""

    def _make_state(self) -> AgentState:
        state = AgentState(query="analisis kesehatan bisnis bulan Juni 2026", database="financial_db")
        state.intent = {"category": "complex_analytics", "segment": "general"}
        return state

    def test_guard_forces_missing_tools(self):
        mock_client    = MagicMock()
        llm_responses  = _make_openai_responses(
            [("get_summary", {**_PERIOD, "dimension": "all"})],
            "Kesimpulan mock.",
        )
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=m)]) for m in llm_responses
        ]

        with patch("src.agents.analytics_agent.execute_tool", return_value=_DUMMY_RESULT):
            agent = _make_analytics_agent(mock_client)
            state = self._make_state()
            agent._run_openai_compatible(state, MagicMock(), "system prompt", "gpt-4o-mini")

        called_tools = {tc["tool"] for tc in state.tool_calls}
        assert _GENERAL_HEALTH_TOOLS <= called_tools, (
            f"Missing tools after guard: {_GENERAL_HEALTH_TOOLS - called_tools}"
        )

    def test_guard_does_not_duplicate_already_called_tools(self):
        mock_client   = MagicMock()
        llm_tool_calls = [
            ("get_summary",      {**_PERIOD, "dimension": "all"}),
            ("get_trend",        {"start_date": "2026-06-01", "end_date": "2026-06-30", "granularity": "daily"}),
            ("compare_periods",  {"dimension": "partner", "period_a_start": "2026-06-01", "period_a_end": "2026-06-30", "period_b_start": "2026-05-01", "period_b_end": "2026-05-31"}),
            ("get_distribution", {**_PERIOD, "dimension": "partner"}),
            ("detect_anomaly",   {"dimension": "partner", "target_date": "2026-06-30"}),
        ]
        llm_responses = _make_openai_responses(llm_tool_calls, "Done.")
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=m)]) for m in llm_responses
        ]

        with patch("src.agents.analytics_agent.execute_tool", return_value=_DUMMY_RESULT):
            agent = _make_analytics_agent(mock_client)
            state = self._make_state()
            agent._run_openai_compatible(state, MagicMock(), "system prompt", "gpt-4o-mini")

        tool_names = [tc["tool"] for tc in state.tool_calls]
        assert len(tool_names) == len(set(tool_names)), "Duplicate tool calls detected"
        assert set(tool_names) == _GENERAL_HEALTH_TOOLS


class TestGeneralHealthGuardDoesNotFireForSpecificSegment:
    """Guard must NOT activate when segment is partners/channels/products."""

    def _run_with_intent(self, category: str, segment: str) -> list[str]:
        mock_client   = MagicMock()
        llm_responses = _make_openai_responses(
            [("get_summary", {**_PERIOD, "dimension": "all"})],
            "OK.",
        )
        mock_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=m)]) for m in llm_responses
        ]

        with patch("src.agents.analytics_agent.execute_tool", return_value=_DUMMY_RESULT):
            agent = _make_analytics_agent(mock_client)
            state = AgentState(query="test", database="financial_db")
            state.intent = {"category": category, "segment": segment}
            agent._run_openai_compatible(state, MagicMock(), "sys", "gpt-4o-mini")

        return [tc["tool"] for tc in state.tool_calls]

    def test_partners_segment_does_not_force_checklist(self):
        assert len(self._run_with_intent("complex_analytics", "partners")) == 1

    def test_channels_segment_does_not_force_checklist(self):
        assert len(self._run_with_intent("complex_analytics", "channels")) == 1

    def test_aggregation_general_does_not_force_checklist(self):
        assert len(self._run_with_intent("aggregation", "general")) == 1


# ── InsightGenerator section filter ─────────────────────────────────────────

def _make_insight_generator():
    """Build InsightGenerator with mocked LLM client (no real API calls)."""
    from src.agents.insight_generator import InsightGenerator
    with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o-mini")):
        return InsightGenerator()


class TestSectionDistributionFilter:
    """Option B: filter sections with 'distribusi' when get_distribution not called."""

    def _make_layout_with_distribution(self) -> dict:
        return {
            "narrative_sections": [
                {"id": "s1", "title": None, "instruction": "ringkasan"},
                {"id": "s2", "title": "## Perbandingan Periode", "instruction": "perbandingan"},
                {"id": "s3", "title": "## Distribusi Performa", "instruction": "distribusi"},
            ],
            "response_length": "detailed",
            "needs_visual": True,
            "key_metrics": [],
            "anomaly_flag": False,
        }

    def _make_tool_result(self, tool_name: str) -> ToolCallResult:
        return ToolCallResult(
            tool_name=tool_name,
            data=[{"entity": "gopay", "total_trx": 1}],
            row_count=1,
            sql_or_params="SELECT 1",
            description="",
        )

    def test_distribution_section_removed_when_no_get_distribution(self):
        state = AgentState(query="analisis kesehatan")
        state.layout_plan  = self._make_layout_with_distribution()
        state.tool_results = [
            self._make_tool_result("get_summary"),
            self._make_tool_result("compare_periods"),
        ]
        state.intent = {"category": "complex_analytics", "segment": "general"}

        ig = _make_insight_generator()
        with (
            patch.object(ig, "_call_llm", return_value="insight text"),
            patch.object(ig, "_build_chart_configs_with_anchors", return_value=[]),
            patch.object(ig, "_parse_insight_sections", return_value={}),
        ):
            ig.execute(state)

        section_titles = [s.get("title") for s in state.layout_plan.get("narrative_sections", [])]
        assert not any(
            t and "distribusi" in t.lower() for t in section_titles
        ), f"Distribution section not removed; titles: {section_titles}"

    def test_distribution_section_kept_when_get_distribution_present(self):
        state = AgentState(query="analisis distribusi partner")
        state.layout_plan  = self._make_layout_with_distribution()
        state.tool_results = [
            self._make_tool_result("get_summary"),
            self._make_tool_result("get_distribution"),
        ]
        state.intent = {"category": "complex_analytics", "segment": "partners"}

        ig = _make_insight_generator()
        with (
            patch.object(ig, "_call_llm", return_value="insight text"),
            patch.object(ig, "_build_chart_configs_with_anchors", return_value=[]),
            patch.object(ig, "_parse_insight_sections", return_value={}),
        ):
            ig.execute(state)

        section_titles = [s.get("title") for s in state.layout_plan.get("narrative_sections", [])]
        assert any(
            t and "distribusi" in t.lower() for t in section_titles
        ), f"Distribution section wrongly removed; titles: {section_titles}"

    def test_non_distribution_sections_unaffected(self):
        state = AgentState(query="tren partner")
        state.layout_plan = {
            "narrative_sections": [
                {"id": "s1", "title": None, "instruction": "ringkasan"},
                {"id": "s2", "title": "## Tren Volume", "instruction": "tren"},
                {"id": "s3", "title": "## Perbandingan", "instruction": "compare"},
            ],
            "response_length": "standard",
            "needs_visual": True,
            "key_metrics": [],
            "anomaly_flag": False,
        }
        state.tool_results = [self._make_tool_result("get_summary")]
        state.intent = {"category": "aggregation", "segment": "general"}

        ig = _make_insight_generator()
        with (
            patch.object(ig, "_call_llm", return_value="insight text"),
            patch.object(ig, "_build_chart_configs_with_anchors", return_value=[]),
            patch.object(ig, "_parse_insight_sections", return_value={}),
        ):
            ig.execute(state)

        assert len(state.layout_plan["narrative_sections"]) == 3


# ── Verdict closing guard ────────────────────────────────────────────────────

def _make_tool_result_with_sr(tool_name: str, sr_value: float | None) -> ToolCallResult:
    data = [{"partner_group": "gopay", "success_rate_pct": sr_value}] if sr_value is not None else []
    return ToolCallResult(
        tool_name=tool_name,
        data=data,
        row_count=len(data),
        sql_or_params="SELECT 1",
        description="test",
    )


def _make_anomaly_result() -> ToolCallResult:
    return ToolCallResult(
        tool_name="detect_anomaly",
        data=[{"partner_group": "gopay", "deviation_pct": 42.0}],
        row_count=1,
        sql_or_params="SELECT 1",
        description="anomaly",
    )


def _detailed_layout_plan() -> dict:
    return {
        "narrative_sections": [{"id": "s1", "title": None, "instruction": "ringkasan"}],
        "response_length": "detailed",
        "needs_visual": False,
        "key_metrics": [],
        "anomaly_flag": False,
    }


class TestVerdictClosingGuard:
    """Verdict guard must append SEHAT/PERHATIAN/KRITIS to closing when absent."""

    def _run_ig(
        self,
        llm_response: str,
        tool_results: list,
        response_length: str = "detailed",
    ) -> str:
        """Run InsightGenerator.execute() and return state.insights."""
        state = AgentState(query="analisis kesehatan bisnis", database="financial_db")
        state.intent = {"category": "complex_analytics", "segment": "general"}
        state.tool_results = tool_results
        plan = _detailed_layout_plan()
        plan["response_length"] = response_length
        state.layout_plan = plan

        ig = _make_insight_generator()
        with (
            patch.object(ig, "_call_llm", return_value=llm_response),
            patch.object(ig, "_build_chart_configs_with_anchors", return_value=[]),
            patch.object(ig, "_parse_insight_sections", return_value={}),
        ):
            ig.execute(state)
        return state.insights

    # ── Guard fires ──────────────────────────────────────────────────────────

    def test_guard_appends_kritis_when_sr_below_kritis(self):
        from src.utils.thresholds import get_sr_verdict_boundaries
        sr_kritis, _ = get_sr_verdict_boundaries()
        tr = _make_tool_result_with_sr("get_summary", sr_kritis - 0.5)
        result = self._run_ig("Bisnis berjalan normal minggu ini.", [tr])
        assert "KRITIS" in result
        assert "Verdict keseluruhan" in result

    def test_guard_appends_perhatian_when_sr_between_thresholds(self):
        from src.utils.thresholds import get_sr_verdict_boundaries
        sr_kritis, sr_sehat = get_sr_verdict_boundaries()
        mid_sr = (sr_kritis + sr_sehat) / 2
        tr = _make_tool_result_with_sr("get_summary", mid_sr)
        result = self._run_ig("Performa minggu ini cukup stabil.", [tr])
        assert "PERHATIAN" in result
        assert "Verdict keseluruhan" in result

    def test_guard_appends_sehat_when_all_clean(self):
        from src.utils.thresholds import get_sr_verdict_boundaries
        _, sr_sehat = get_sr_verdict_boundaries()
        tr = _make_tool_result_with_sr("get_summary", sr_sehat + 0.5)
        result = self._run_ig("Semua indikator dalam batas normal.", [tr])
        assert "SEHAT" in result
        assert "Verdict keseluruhan" in result

    def test_guard_appends_perhatian_when_detect_anomaly_has_rows(self):
        tr_clean = _make_tool_result_with_sr("get_summary", None)  # no SR data
        tr_anomaly = _make_anomaly_result()
        result = self._run_ig("Tren volume menunjukkan pola yang menarik.", [tr_clean, tr_anomaly])
        assert "PERHATIAN" in result
        assert "Verdict keseluruhan" in result

    # ── Guard does not fire ──────────────────────────────────────────────────

    def test_guard_does_not_fire_when_sehat_in_closing(self):
        tr = _make_tool_result_with_sr("get_summary", 99.0)
        long_text = "Analisis lengkap menunjukkan kondisi baik. " * 5 + "Verdict: SEHAT."
        result = self._run_ig(long_text, [tr])
        # "Verdict keseluruhan" should NOT be appended (already compliant)
        assert result.count("Verdict keseluruhan") == 0

    def test_guard_does_not_fire_when_perhatian_in_closing(self):
        tr = _make_tool_result_with_sr("get_summary", 96.0)
        long_text = "Analisis menunjukkan beberapa area perlu diperhatikan. " * 5 + "Status PERHATIAN diperlukan."
        result = self._run_ig(long_text, [tr])
        assert result.count("Verdict keseluruhan") == 0

    def test_guard_does_not_fire_when_kritis_in_closing(self):
        tr = _make_tool_result_with_sr("get_summary", 92.0)
        long_text = "Kondisi sangat memprihatinkan. " * 5 + "Situasi ini KRITIS dan memerlukan tindakan."
        result = self._run_ig(long_text, [tr])
        assert result.count("Verdict keseluruhan") == 0

    def test_guard_does_not_fire_for_non_detailed_response(self):
        tr = _make_tool_result_with_sr("get_summary", 92.0)
        result = self._run_ig("Volume transaksi naik 5% MoM.", [tr], response_length="standard")
        assert "Verdict keseluruhan" not in result

    def test_guard_does_not_fire_when_no_tool_results(self):
        """Single-step SQL path: no tool_results → guard must not activate."""
        state = AgentState(query="berapa total transaksi", database="financial_db")
        state.intent = {"category": "aggregation", "segment": "general"}
        state.tool_results = []
        state.layout_plan = _detailed_layout_plan()

        ig = _make_insight_generator()
        with (
            patch.object(ig, "_call_llm", return_value="Total transaksi bulan ini normal."),
            patch.object(ig, "_build_chart_configs_with_anchors", return_value=[]),
            patch.object(ig, "_parse_insight_sections", return_value={}),
        ):
            ig.execute(state)

        assert "Verdict keseluruhan" not in state.insights
