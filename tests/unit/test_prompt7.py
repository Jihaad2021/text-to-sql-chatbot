"""
Prompt 7 — Unit tests for output structure and visual planning.

Covers ResponsePlanner chart selection + InsightGenerator use_thinking across
8 query scenarios. All LLM calls are mocked — no real API hits.

Test cases:
  1. Partner distribution donut ≤ 6 entities          → donut_chart preserved
  2. MoM comparison with pct_change columns            → bar_chart upgraded to diverging_bar_chart
  3. 30-day trend with time dimension                  → line_chart
  4. Ranking 15 categories                             → table-type visual, no donut
  5. simple_select single scalar + brief               → needs_visual=False
  6. SKIP (hourly heatmap — deferred backlog item)
  7. root_cause_analysis 1-tool (compare_periods)      → tool_results[1], diverging_bar, use_thinking=True
  8. root_cause_analysis 2-tool (anomaly + compare)    → tool_results[≥2], schemas differ,
                                                          anomaly_flag correct, no dup visual_blocks
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.insight_generator import InsightGenerator
from src.agents.response_planner import ResponsePlanner
from src.models.agent_state import AgentState, ToolCallResult


# ────────────────────────────────────────────────────────────────────────
# FIXTURES
# ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def planner():
    """ResponsePlanner with mocked LLM client — no real provider needed."""
    with patch.object(ResponsePlanner, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        return ResponsePlanner()


@pytest.fixture
def anthropic_generator():
    """InsightGenerator wired to Anthropic — needed to test use_thinking path."""
    with patch.object(InsightGenerator, "_init_client",
                      return_value=("anthropic", MagicMock(), "claude-sonnet-4-6")):
        return InsightGenerator()


# ────────────────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────────────────

def _make_plan_json(
    visual_blocks: list[dict],
    response_length: str = "standard",
    sections: list[dict] | None = None,
) -> str:
    """Return a valid layout_plan JSON string for LLM mock responses."""
    sections = sections or [
        {"id": "s1", "title": None,            "instruction": "Jawab langsung."},
        {"id": "s2", "title": "## Detail",     "instruction": "Berikan detail."},
    ]
    return json.dumps({
        "narrative_sections": sections,
        "visual_blocks": visual_blocks,
        "needs_visual": bool(visual_blocks),
        "key_metrics": [],
        "response_length": response_length,
    })


# ────────────────────────────────────────────────────────────────────────
# TEST 1 — Partner distribution donut ≤ 6 entities
# ────────────────────────────────────────────────────────────────────────

class TestCase1DonutSmall:
    """6 partners with share_pct → donut_chart preserved (entity_count not > 6)."""

    def test_donut_chart_preserved(self, planner):
        state = AgentState(query="distribusi partner bulan April", database="financial_db")
        state.intent = {"category": "aggregation", "segment": "partners"}
        state.query_result = [
            {"partner": p, "total_trx": 1000, "share_pct": round(100 / 6, 1)}
            for p in ["GoPay", "Dana", "OVO", "QRIS", "ShopeePay", "LinkAja"]
        ]
        state.row_count = 6

        mock_json = _make_plan_json([
            {"type": "donut_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vb_types = [b["type"] for b in state.layout_plan["visual_blocks"]]
        assert "donut_chart" in vb_types, f"Expected donut_chart, got: {vb_types}"


# ────────────────────────────────────────────────────────────────────────
# TEST 2 — MoM comparison → diverging_bar_chart
# ────────────────────────────────────────────────────────────────────────

class TestCase2MoMDivergingBar:
    """LLM emits bar_chart for pct_change data → _enforce_chart_rules upgrades it."""

    def test_bar_upgraded_to_diverging_when_pct_change(self, planner):
        state = AgentState(query="bandingkan partner April vs Maret", database="financial_db")
        state.intent = {"category": "complex_analytics", "segment": "partners"}
        state.is_multi_step = False
        state.query_result = [
            {"partner": "GoPay",     "trx_pct_change":   5.2, "rev_pct_change":   3.1},
            {"partner": "Dana",      "trx_pct_change":  -2.0, "rev_pct_change":  -1.5},
            {"partner": "OVO",       "trx_pct_change":   0.8, "rev_pct_change":   1.2},
            {"partner": "QRIS",      "trx_pct_change":  12.3, "rev_pct_change":  10.1},
            {"partner": "ShopeePay", "trx_pct_change":  -8.0, "rev_pct_change":  -7.5},
        ]
        state.row_count = 5

        # LLM emits bar_chart — _enforce_chart_rules Rule 2 must upgrade it
        mock_json = _make_plan_json([
            {"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vb_types = [b["type"] for b in state.layout_plan["visual_blocks"]]
        assert "diverging_bar_chart" in vb_types, (
            f"Expected diverging_bar_chart after Rule 2 upgrade, got: {vb_types}"
        )
        assert "bar_chart" not in vb_types, (
            f"bar_chart should have been upgraded, not kept: {vb_types}"
        )


# ────────────────────────────────────────────────────────────────────────
# TEST 3 — 30-day trend → line_chart
# ────────────────────────────────────────────────────────────────────────

class TestCase3TrendLineChart:
    """Time-series data with 'periode' column → line_chart."""

    def test_line_chart_for_daily_trend(self, planner):
        state = AgentState(query="tren transaksi 30 hari terakhir", database="financial_db")
        state.intent = {"category": "trend_analysis", "segment": "transactions"}
        state.query_result = [
            {"periode": f"2026-05-{i:02d}", "total_trx": 1000 + i * 10}
            for i in range(1, 31)
        ]
        state.row_count = 30

        mock_json = _make_plan_json([
            {"type": "line_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vb_types = [b["type"] for b in state.layout_plan["visual_blocks"]]
        assert "line_chart" in vb_types, f"Expected line_chart, got: {vb_types}"


# ────────────────────────────────────────────────────────────────────────
# TEST 4 — Ranking 15 categories → table visual (no donut)
# ────────────────────────────────────────────────────────────────────────

class TestCase4RankingTable:
    """15 rows → distinct_entity_count > 10: table visual expected, no donut."""

    def test_table_visual_for_large_ranking(self, planner):
        state = AgentState(query="ranking 15 partner berdasarkan revenue", database="financial_db")
        state.intent = {"category": "ranking_analysis", "segment": "partners"}
        state.query_result = [
            {"rank": i, "partner": f"Partner{i}", "total_revenue": 1000 - i * 10}
            for i in range(1, 16)
        ]
        state.row_count = 15

        mock_json = _make_plan_json([
            {"type": "ranking_table", "anchor_after": None,  "purpose": "leading_answer"},
            {"type": "data_table",    "anchor_after": "s2",  "purpose": "detail_reference"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vb_types = [b["type"] for b in state.layout_plan["visual_blocks"]]
        assert any(t in vb_types for t in ("ranking_table", "data_table")), (
            f"Expected ranking_table or data_table for 15-entity ranking, got: {vb_types}"
        )
        assert "donut_chart" not in vb_types, (
            f"donut_chart must not appear for 15 entities: {vb_types}"
        )


# ────────────────────────────────────────────────────────────────────────
# TEST 5 — simple_select single scalar + brief → needs_visual=False
# ────────────────────────────────────────────────────────────────────────

class TestCase5SimpleSelectBrief:
    """1 row × 1 col with response_length=brief → needs_visual deterministically False."""

    def test_needs_visual_false_for_scalar_brief(self, planner):
        state = AgentState(query="berapa total transaksi bulan ini?", database="financial_db")
        state.intent = {"category": "simple_select", "segment": "transactions"}
        state.query_result = [{"total_trx": 1_500_000}]
        state.row_count = 1

        mock_json = _make_plan_json(
            visual_blocks=[
                {"type": "kpi_grid", "anchor_after": "s1", "purpose": "supporting_evidence"},
            ],
            response_length="brief",
            sections=[{"id": "s1", "title": None, "instruction": "Jawab langsung 1 kalimat."}],
        )
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        assert state.layout_plan["response_length"] == "brief"
        assert state.layout_plan["needs_visual"] is False, (
            f"Single scalar + brief must force needs_visual=False, "
            f"got: {state.layout_plan['needs_visual']}"
        )


# ────────────────────────────────────────────────────────────────────────
# TEST 7 — root_cause_analysis 1-tool: diverging_bar + use_thinking
# ────────────────────────────────────────────────────────────────────────

class TestCase7RootCause1Tool:
    """
    Single compare_periods tool call.

    Verifies:
      - state.tool_results contains exactly 1 entry (unchanged by ResponsePlanner)
      - _enforce_chart_rules Rule 2 upgrades bar → diverging_bar_chart (pct_change in tool data)
      - InsightGenerator passes use_thinking=True when provider=anthropic + root_cause_analysis
    """

    _COMPARE_DATA = [
        {"partner": "GoPay",     "trx_pct_change": -12.5, "rev_pct_change": -10.2, "baseline_trx": 5000},
        {"partner": "Dana",      "trx_pct_change":   2.1,  "rev_pct_change":   1.8, "baseline_trx": 4200},
        {"partner": "OVO",       "trx_pct_change":  -1.3,  "rev_pct_change":  -0.9, "baseline_trx": 3800},
        {"partner": "QRIS",      "trx_pct_change":   5.0,  "rev_pct_change":   4.5, "baseline_trx": 6100},
        {"partner": "ShopeePay", "trx_pct_change":  -3.0,  "rev_pct_change":  -2.7, "baseline_trx": 2900},
    ]

    def _state(self) -> AgentState:
        """AgentState simulating post-AnalyticsAgent state with 1 tool result."""
        state = AgentState(
            query="kenapa GoPay turun bulan lalu",
            database="financial_db",
        )
        state.intent = {
            "category": "root_cause_analysis",
            "segment": "partners",
            "confidence": 0.92,
            "reason": "drop investigation for a specific partner",
        }
        state.is_multi_step = False  # forced False by _run_analytics in pipeline
        state.tool_results = [
            ToolCallResult(
                tool_name="compare_periods",
                data=self._COMPARE_DATA,
                row_count=len(self._COMPARE_DATA),
                sql_or_params="SELECT partner, trx_pct_change ...",
                description="Compare partner May vs April",
            )
        ]
        state.query_result = self._COMPARE_DATA   # backward-compat: last tool's data
        state.row_count    = len(self._COMPARE_DATA)
        return state

    def test_tool_results_has_one_entry(self, planner):
        state = self._state()
        mock_json = _make_plan_json([
            {"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ], response_length="detailed")
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        assert len(state.tool_results) == 1

    def test_diverging_bar_in_visual_blocks(self, planner):
        """Rule 2: bar_chart + pct_change data + no time → diverging_bar_chart."""
        state = self._state()
        mock_json = _make_plan_json([
            {"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ], response_length="detailed")
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vb_types = [b["type"] for b in state.layout_plan["visual_blocks"]]
        assert "diverging_bar_chart" in vb_types, (
            f"Rule 2 must upgrade bar → diverging_bar_chart for tool_results pct_change data. "
            f"Got: {vb_types}"
        )
        assert "bar_chart" not in vb_types, (
            f"bar_chart should be fully replaced by diverging_bar_chart: {vb_types}"
        )

    def test_use_thinking_true_for_anthropic_root_cause(self, anthropic_generator):
        """InsightGenerator must forward use_thinking=True to _call_llm for root_cause + anthropic."""
        state = self._state()
        # Set layout_plan directly — this test only checks use_thinking, not chart building
        state.layout_plan = {
            "narrative_sections": [{"id": "s1", "title": None, "instruction": "Jawab langsung."}],
            "visual_blocks": [
                {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
            ],
            "needs_visual": False,  # skip chart building — not what we're testing here
            "key_metrics": ["trx_pct_change"],
            "response_length": "detailed",
            "anomaly_flag": False,
        }

        with patch.object(
            anthropic_generator, "_call_llm", return_value="GoPay turun 12.5% vs bulan lalu."
        ) as mock_llm:
            anthropic_generator.run(state)

        _, kwargs = mock_llm.call_args
        assert kwargs.get("use_thinking") is True, (
            f"Expected use_thinking=True for root_cause_analysis + anthropic provider. "
            f"_call_llm was called with: {kwargs}"
        )


# ────────────────────────────────────────────────────────────────────────
# TEST 8 — root_cause_analysis 2-tool: different schemas, anomaly_flag, no dup
# ────────────────────────────────────────────────────────────────────────

class TestCase8RootCause2Tool:
    """
    Two-tool root_cause_analysis (detect_anomaly + compare_periods).

    Asserts structural invariants regardless of which tools were actually called:
      - state.tool_results has ≥ 2 entries with different column schemas
      - anomaly_flag=True when detect_anomaly returned is_anomaly=True rows
      - anomaly_flag=False when all is_anomaly=False
      - visual_blocks contains no (type, anchor_after, purpose) duplicates
    """

    _ANOMALY_COLS  = ["partner", "total_trx", "baseline_trx", "deviation_pct", "is_anomaly"]
    _COMPARE_COLS  = ["partner", "trx_pct_change", "rev_pct_change"]

    def _state(self, include_anomaly: bool = True) -> AgentState:
        state = AgentState(
            query="ada anomali GoPay di April? bandingkan juga dengan Maret",
            database="financial_db",
        )
        state.intent = {
            "category": "root_cause_analysis",
            "segment": "partners",
            "confidence": 0.90,
            "reason": "compound anomaly + period comparison",
        }
        state.is_multi_step = False

        anomaly_data = [
            {"partner": "GoPay",     "total_trx": 4200, "baseline_trx": 5000,
             "deviation_pct": -16.0, "is_anomaly": include_anomaly},
            {"partner": "Dana",      "total_trx": 4300, "baseline_trx": 4200,
             "deviation_pct":   2.4, "is_anomaly": False},
            {"partner": "OVO",       "total_trx": 3750, "baseline_trx": 3800,
             "deviation_pct":  -1.3, "is_anomaly": False},
            {"partner": "QRIS",      "total_trx": 6200, "baseline_trx": 6100,
             "deviation_pct":   1.6, "is_anomaly": False},
            {"partner": "ShopeePay", "total_trx": 2800, "baseline_trx": 2900,
             "deviation_pct":  -3.4, "is_anomaly": False},
        ]
        compare_data = [
            {"partner": "GoPay",     "trx_pct_change": -16.0, "rev_pct_change": -14.2},
            {"partner": "Dana",      "trx_pct_change":   2.4,  "rev_pct_change":   2.1},
            {"partner": "OVO",       "trx_pct_change":  -1.3,  "rev_pct_change":  -0.9},
            {"partner": "QRIS",      "trx_pct_change":   1.6,  "rev_pct_change":   1.4},
            {"partner": "ShopeePay", "trx_pct_change":  -3.4,  "rev_pct_change":  -3.0},
        ]

        state.tool_results = [
            ToolCallResult(
                tool_name="detect_anomaly",
                data=anomaly_data,
                row_count=len(anomaly_data),
                sql_or_params="SELECT partner, total_trx, baseline_trx ...",
                description="Detect anomalies in April transactions",
            ),
            ToolCallResult(
                tool_name="compare_periods",
                data=compare_data,
                row_count=len(compare_data),
                sql_or_params="SELECT partner, trx_pct_change ...",
                description="Compare April vs March per partner",
            ),
        ]
        state.query_result = compare_data   # last tool's data
        state.row_count    = len(compare_data)
        return state

    def test_tool_results_ge_two_entries(self, planner):
        state = self._state()
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
            {"type": "data_table",          "anchor_after": "s2", "purpose": "detail_reference"},
        ], response_length="detailed")
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        assert len(state.tool_results) >= 2

    def test_tool_results_have_different_schemas(self, planner):
        """Each tool preserves its own column schema — no flat-merge into a single list."""
        state = self._state()
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        assert len(state.tool_results) >= 2
        schemas = [frozenset(tr.data[0].keys()) for tr in state.tool_results if tr.data]
        assert len(set(schemas)) >= 2, (
            f"Expected ≥2 distinct schemas across tool results (each tool keeps its own schema). "
            f"Got {len(set(schemas))} unique schema(s): {[sorted(s) for s in schemas]}"
        )

    def test_anomaly_flag_set_when_is_anomaly_true(self, planner):
        """_apply_anomaly_flag must set anomaly_flag=True when detect_anomaly returns is_anomaly=True rows."""
        state = self._state(include_anomaly=True)
        # Plan without anomaly_callout — LLM didn't emit it; auto-guard must fire
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ], response_length="detailed")
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        assert state.layout_plan["anomaly_flag"] is True, (
            f"anomaly_flag must be True when detect_anomaly returns is_anomaly=True rows. "
            f"Full plan: {state.layout_plan}"
        )

    def test_anomaly_flag_false_when_no_anomaly(self, planner):
        """anomaly_flag stays False when all is_anomaly=False and no anomaly_callout block."""
        state = self._state(include_anomaly=False)
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        assert state.layout_plan["anomaly_flag"] is False, (
            f"anomaly_flag must be False when all is_anomaly=False. "
            f"Full plan: {state.layout_plan}"
        )

    def test_no_duplicate_visual_blocks(self, planner):
        """Dedup guard must eliminate exact (type, anchor_after, purpose) duplicates."""
        state = self._state()
        # Simulate LLM emitting 4 blocks with 2 duplicate pairs
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None,  "purpose": "leading_answer"},
            {"type": "data_table",          "anchor_after": "s2",  "purpose": "detail_reference"},
            {"type": "data_table",          "anchor_after": "s2",  "purpose": "detail_reference"},  # dup
            {"type": "diverging_bar_chart", "anchor_after": None,  "purpose": "leading_answer"},    # dup
        ], response_length="detailed")
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vbs = state.layout_plan["visual_blocks"]
        vb_keys = [(b["type"], b["anchor_after"], b["purpose"]) for b in vbs]
        assert len(vb_keys) == len(set(vb_keys)), (
            f"Duplicate (type, anchor_after, purpose) entries found after dedup guard: {vb_keys}"
        )
        # The 2 unique blocks must survive
        assert len(vbs) == 2, (
            f"Expected 2 unique blocks after removing 2 duplicates, got {len(vbs)}: {vbs}"
        )


# ────────────────────────────────────────────────────────────────────────
# TEST B2 REGRESSION — analytics path with empty query_result
# ────────────────────────────────────────────────────────────────────────

class TestB2AnalyticsPathGuardRegression:
    """Regression: _enforce_chart_rules must NOT skip when query_result=[] but
    tool_results is populated (analytics agent path).

    The old guard was: `if state.is_multi_step or not state.query_result: return plan`
    which silently skipped the entire rule-set for AnalyticsAgent queries because
    AnalyticsAgent sets query_result to the last tool's data only AFTER ResponsePlanner
    runs — so query_result is [] at the time _enforce_chart_rules fires.
    """

    _COMPARE_DATA = [
        {"channel": "QRIS",      "trx_pct_change": -3.2, "rev_pct_change": -1.8},
        {"channel": "GoPay",     "trx_pct_change":  2.1, "rev_pct_change":  3.0},
        {"channel": "OVO",       "trx_pct_change": -8.4, "rev_pct_change": -6.1},
        {"channel": "Dana",      "trx_pct_change":  1.5, "rev_pct_change":  2.2},
        {"channel": "ShopeePay", "trx_pct_change": -0.7, "rev_pct_change": -0.3},
    ]

    def _state(self) -> AgentState:
        state = AgentState(
            query="bagaimana dengan channel di tanggal 30 juni?",
            database="financial_db",
        )
        state.intent = {"category": "root_cause_analysis", "segment": "channels", "confidence": 0.9, "reason": "follow-up"}
        state.is_multi_step = False
        state.tool_results = [
            ToolCallResult(
                tool_name="compare_periods",
                data=self._COMPARE_DATA,
                row_count=len(self._COMPARE_DATA),
                sql_or_params='{"date": "2026-06-30"}',
                description="Channel comparison on 2026-06-30",
            )
        ]
        # Simulate AnalyticsAgent state BEFORE backward-compat copy:
        # tool_results is populated but query_result is still empty.
        state.query_result = []
        state.row_count = 0
        return state

    def test_diverging_bar_when_query_result_empty_tool_results_populated(self, planner):
        """Rule 2 must fire even when query_result=[] if tool_results has pct_change data."""
        state = self._state()
        mock_json = _make_plan_json([
            {"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ], response_length="detailed")
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        vb_types = [b["type"] for b in state.layout_plan["visual_blocks"]]
        assert "diverging_bar_chart" in vb_types, (
            f"Rule 2 must upgrade bar → diverging_bar_chart when tool_results has "
            f"pct_change data (query_result=[]).  Got: {vb_types}"
        )
        assert "bar_chart" not in vb_types, (
            f"bar_chart should be fully replaced by diverging_bar_chart. Got: {vb_types}"
        )

    def test_guard_still_skips_when_both_empty(self, planner):
        """Guard must still skip (no data anywhere) when both query_result AND tool_results are empty."""
        state = AgentState(
            query="test empty",
            database="financial_db",
        )
        state.query_result = []
        state.row_count = 0
        state.tool_results = []

        plan = {
            "visual_blocks": [{"type": "bar_chart", "anchor_after": None, "purpose": "leading_answer"}],
            "needs_visual": True,
            "response_length": "standard",
            "key_metrics": [],
            "anomaly_flag": False,
        }
        result = planner._enforce_chart_rules(state, plan)
        vb_types = [b["type"] for b in result["visual_blocks"]]
        assert vb_types == ["bar_chart"], (
            f"With no data anywhere, guard must skip all rules (bar_chart must survive). Got: {vb_types}"
        )


# ────────────────────────────────────────────────────────────────────────
# TEST — compare_periods generates grouped_bar_chart + diverging_bar_chart
# ────────────────────────────────────────────────────────────────────────

_COMPARE_FULL = [
    {
        "entity": "qris",  "trx_a": 14_000, "trx_b": 12_000, "trx_pct_change": 16.67,
        "rev_a": 15e9, "rev_b": 13e9, "rev_pct_change": 15.38,
        "sr_a": 99.5,  "sr_b": 99.2,  "sr_pct_change": 0.30,
    },
    {
        "entity": "gopay", "trx_a": 4_000,  "trx_b": 4_500,  "trx_pct_change": -11.11,
        "rev_a": 4e9,  "rev_b": 4.5e9, "rev_pct_change": -11.11,
        "sr_a": 98.1,  "sr_b": 98.5,  "sr_pct_change": -0.40,
    },
    {
        "entity": "ovo",   "trx_a": 2_100,  "trx_b": 2_400,  "trx_pct_change": -12.50,
        "rev_a": 2.1e9, "rev_b": 2.4e9, "rev_pct_change": -12.50,
        "sr_a": 97.3,  "sr_b": 98.0,  "sr_pct_change": -0.70,
    },
]


class TestGroupedBarEnforce:
    """Rule 3 in _enforce_chart_rules: compare_periods data must produce BOTH
    grouped_bar_chart (absolute values) and diverging_bar_chart (pct_change),
    not just one or the other.
    """

    def _state_with_tool_results(self) -> AgentState:
        state = AgentState(
            query="bandingkan QRIS GoPay OVO bulan ini vs bulan lalu",
            database="financial_db",
        )
        state.intent = {"category": "comparison", "segment": "partners", "confidence": 0.9, "reason": ""}
        state.is_multi_step = False
        state.tool_results = [
            ToolCallResult(
                tool_name="compare_periods",
                data=_COMPARE_FULL,
                row_count=len(_COMPARE_FULL),
                sql_or_params='{"period_a": "2026-05", "period_b": "2026-06"}',
                description="Compare May vs June for QRIS/GoPay/OVO",
            )
        ]
        state.query_result = []   # empty until AnalyticsAgent backward-compat copy
        state.row_count = 0
        return state

    def test_two_visual_blocks_produced(self, planner):
        """LLM emits only diverging_bar_chart → Rule 3 must inject grouped_bar_chart,
        resulting in exactly 2 chart-type visual_blocks."""
        state = self._state_with_tool_results()
        # LLM returns only the pct_change chart (typical partial LLM output)
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        chart_blocks = [
            b for b in state.layout_plan["visual_blocks"]
            if b["type"] not in {"data_table", "ranking_table", "kpi_grid", "anomaly_callout"}
        ]
        vb_types = [b["type"] for b in chart_blocks]
        assert "diverging_bar_chart" in vb_types, (
            f"diverging_bar_chart must be present (pct_change data). Got: {vb_types}"
        )
        assert "grouped_bar_chart" in vb_types, (
            f"grouped_bar_chart must be injected by Rule 3 (*_a/*_b pairs). Got: {vb_types}"
        )
        assert len(chart_blocks) == 2, (
            f"Exactly 2 chart blocks expected (diverging + grouped). Got {len(chart_blocks)}: {vb_types}"
        )

    def test_grouped_bar_purpose_is_supporting_evidence(self, planner):
        """grouped_bar_chart must be supporting_evidence (not leading_answer)."""
        state = self._state_with_tool_results()
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None, "purpose": "leading_answer"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        grouped = next(
            (b for b in state.layout_plan["visual_blocks"] if b["type"] == "grouped_bar_chart"),
            None,
        )
        assert grouped is not None, "grouped_bar_chart block not found"
        assert grouped["purpose"] == "supporting_evidence", (
            f"grouped_bar_chart must have purpose='supporting_evidence'. Got: '{grouped['purpose']}'"
        )

    def test_no_duplicate_grouped_bar(self, planner):
        """If LLM already emits grouped_bar_chart, Rule 3 must not add a second one."""
        state = self._state_with_tool_results()
        mock_json = _make_plan_json([
            {"type": "diverging_bar_chart", "anchor_after": None,  "purpose": "leading_answer"},
            {"type": "grouped_bar_chart",   "anchor_after": "s1",  "purpose": "supporting_evidence"},
        ])
        with patch.object(planner, "_call_llm", return_value=mock_json):
            state = planner.run(state)

        grouped_count = sum(
            1 for b in state.layout_plan["visual_blocks"] if b["type"] == "grouped_bar_chart"
        )
        assert grouped_count == 1, (
            f"Rule 3 must not add a duplicate — expected 1 grouped_bar_chart, got {grouped_count}"
        )

    def test_has_ab_pair_columns_signal_detected(self, planner):
        """_shape_for_cols must detect has_ab_pair_columns=True for compare_periods data."""
        state = self._state_with_tool_results()
        shape = planner._build_data_shape(state)
        # Multi-step path returns steps list
        steps = shape.get("steps", [])
        assert steps, "Expected steps from tool_results path"
        assert any(s.get("has_ab_pair_columns") for s in steps), (
            f"has_ab_pair_columns must be True for compare_periods columns. Steps: {steps}"
        )
