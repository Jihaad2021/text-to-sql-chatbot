"""
Unit tests for auto drill-down logic in pipeline.py.

Tests helper functions (_find_date_col, _find_trx_col, _BRIEF_MODE_RE) and the
three key scenarios for _run_auto_drilldown:
  (a) DoD below threshold → no drill-down, tool_results unchanged
  (b) DoD above threshold → get_distribution called, ToolCallResult appended
  (c) state.tool_results already populated → drill-down skipped entirely
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.pipeline import _BRIEF_MODE_RE, _find_date_col, _find_trx_col
from src.models.agent_state import AgentState, ToolCallResult


# ── helper function unit tests ────────────────────────────────────────────────


class TestFindDateCol:
    def test_date_key(self):
        assert _find_date_col({"date": "2026-06-30", "total_trx": 100}) == "date"

    def test_tanggal_key(self):
        assert _find_date_col({"tanggal": "2026-06-30", "total_trx": 100}) == "tanggal"

    def test_no_date_col(self):
        assert _find_date_col({"partner_group": "gopay", "total_trx": 100}) is None

    def test_case_insensitive(self):
        assert _find_date_col({"DATE": "2026-06-30"}) == "DATE"


class TestFindTrxCol:
    def test_total_trx(self):
        assert _find_trx_col({"date": "2026-06-30", "total_trx": 100}) == "total_trx"

    def test_total_transaksi(self):
        assert _find_trx_col({"date": "2026-06-30", "total_transaksi": 100}) == "total_transaksi"

    def test_volume(self):
        assert _find_trx_col({"date": "2026-06-30", "volume": 100}) == "volume"

    def test_no_trx_col(self):
        assert _find_trx_col({"date": "2026-06-30", "total_revenue": 999}) is None


class TestBriefModeRegex:
    def test_cukup_angka(self):
        assert _BRIEF_MODE_RE.search("cukup angka")

    def test_tampilkan_saja(self):
        assert _BRIEF_MODE_RE.search("tampilkan saja")

    def test_hanya_data(self):
        assert _BRIEF_MODE_RE.search("hanya data")

    def test_show_only(self):
        assert _BRIEF_MODE_RE.search("show only")

    def test_singkat_saja(self):
        assert _BRIEF_MODE_RE.search("singkat saja")

    def test_normal_query_no_match(self):
        assert not _BRIEF_MODE_RE.search("kapan saja penurunan transaksi terjadi di bulan Juni?")

    def test_case_insensitive(self):
        assert _BRIEF_MODE_RE.search("Cukup Angka")


# ── _run_auto_drilldown integration scenarios ─────────────────────────────────


def _make_pipeline_stub():
    """Return a minimal TextToSQLPipeline-like object with _run_auto_drilldown."""
    from src.core.pipeline import TextToSQLPipeline

    # Build a pipeline instance using only MagicMock agents so no DB/LLM needed
    p = object.__new__(TextToSQLPipeline)
    p.query_executor = MagicMock()
    p.query_executor.engines = {"financial_db": MagicMock()}
    return p


_DAILY_ROWS_NO_ANOMALY = [
    {"date": "2026-06-28", "total_trx": 950_000},
    {"date": "2026-06-29", "total_trx": 960_000},  # +1.05% — well below threshold
    {"date": "2026-06-30", "total_trx": 870_000},  # -9.4%  — below 30% threshold
]

_DAILY_ROWS_WITH_ANOMALY = [
    {"date": "2026-06-28", "total_trx": 950_000},
    {"date": "2026-06-29", "total_trx": 950_480},
    {"date": "2026-06-30", "total_trx": 592_437},  # -37.7% — above threshold
]

_DIST_RESULT = {
    "data": [{"entity": "qris", "total_trx": 300_000, "trx_share_pct": 50.7,
              "total_revenue": 1e9, "rev_share_pct": 55.0}],
    "row_count": 1,
    "sql": "SELECT ...",
    "description": "partner breakdown 2026-06-30",
    "actual_entity_count": 9,
    "cumulative_trx_share_pct": 50.7,
    "cumulative_rev_share_pct": 55.0,
    "dimension": "partner",
}


class TestAutoDrilldownScenarios:

    # ── (a) DoD below threshold → no drill-down ───────────────────────────────

    def test_below_threshold_no_drilldown(self):
        """DoD −9.4% < threshold 30% → tool_results stays empty, flag stays False."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="tren transaksi harian bulan Juni 2026")
        state.query_result = _DAILY_ROWS_NO_ANOMALY

        with patch("src.core.pipeline.get_distribution") as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_not_called()
        assert result.tool_results == []
        assert result.auto_drilldown_triggered is False

    # ── (b) DoD above threshold → drill-down triggered ────────────────────────

    def test_above_threshold_drilldown_called(self):
        """DoD −37.7% > threshold 30% → get_distribution called, ToolCallResult appended."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="kapan saja penurunan transaksi terjadi di bulan Juni?")
        state.query_result = _DAILY_ROWS_WITH_ANOMALY

        with patch("src.core.pipeline.get_distribution", return_value=_DIST_RESULT) as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_called_once()
        call_kwargs = mock_dist.call_args
        # Worst day must be 2026-06-30
        assert "2026-06-30" in call_kwargs.args or call_kwargs.kwargs.get("period_start") == "2026-06-30"
        assert len(result.tool_results) == 1
        tr = result.tool_results[0]
        assert isinstance(tr, ToolCallResult)
        assert tr.tool_name == "get_distribution"
        assert tr.dimension == "partner"
        assert "2026-06-30" in tr.description
        assert result.auto_drilldown_triggered is True

    # ── (c) partner get_distribution already in tool_results → skip ──────────

    def test_skip_when_partner_drilldown_exists(self):
        """Partner get_distribution already present → drill-down must be skipped."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="kapan saja penurunan transaksi terjadi di bulan Juni?")
        state.query_result = _DAILY_ROWS_WITH_ANOMALY
        state.tool_results = [
            ToolCallResult(
                tool_name="get_distribution",
                data=[],
                row_count=0,
                sql_or_params="SELECT ...",
                description="partner breakdown already present",
                dimension="partner",
            )
        ]

        with patch("src.core.pipeline.get_distribution") as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_not_called()
        assert len(result.tool_results) == 1  # unchanged
        assert result.auto_drilldown_triggered is False

    def test_not_skipped_when_only_get_trend_exists(self):
        """get_trend in tool_results (AnalyticsAgent path) must NOT block drill-down."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="kapan saja penurunan transaksi terjadi di bulan Juni?")
        # Simulate AnalyticsAgent: query_result = last tool's data (get_trend rows)
        state.query_result = [
            {"period": "2026-06-29", "total_trx": 950480},
            {"period": "2026-06-30", "total_trx": 592437},  # -37.7%
        ]
        state.tool_results = [
            ToolCallResult(
                tool_name="get_trend",
                data=state.query_result,
                row_count=2,
                sql_or_params="SELECT ...",
                description="Trend daily all 2026-06-01→2026-06-30",
            )
        ]

        with patch("src.core.pipeline.get_distribution", return_value=_DIST_RESULT) as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_called_once()
        assert len(result.tool_results) == 2  # get_trend + new get_distribution
        assert result.auto_drilldown_triggered is True

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_brief_mode_skipped(self):
        """Brief-mode query → no drill-down even when anomaly is present."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="tampilkan saja tren transaksi harian bulan Juni 2026")
        state.query_result = _DAILY_ROWS_WITH_ANOMALY

        with patch("src.core.pipeline.get_distribution") as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_not_called()
        assert result.auto_drilldown_triggered is False

    def test_single_row_skipped(self):
        """Only one row → cannot compute DoD, skip gracefully."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="total transaksi 30 Juni 2026")
        state.query_result = [{"date": "2026-06-30", "total_trx": 592_437}]

        with patch("src.core.pipeline.get_distribution") as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_not_called()

    def test_no_date_col_skipped(self):
        """No date column → skip gracefully."""
        pipeline = _make_pipeline_stub()
        state = AgentState(query="total transaksi per partner")
        state.query_result = [
            {"partner_group": "qris", "total_trx": 14_000_000},
            {"partner_group": "dana", "total_trx": 6_000_000},
        ]

        with patch("src.core.pipeline.get_distribution") as mock_dist:
            result = pipeline._run_auto_drilldown(state)

        mock_dist.assert_not_called()
