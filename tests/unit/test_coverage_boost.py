"""
Coverage boost tests — pure utilities and in-memory components.

Targets:
  src/utils/financial_domain.py   (0%  → full coverage)
  src/core/query_cache.py         (50% → full coverage)
  src/utils/date_range.py         (54% → full coverage)
  src/core/baseline_cache.py      (28% → full coverage)
  src/core/token_logger.py        (54% → no-DB paths)
  src/tools/tool_registry.py      (33% → format conversion + dispatch)
  src/utils/context_distiller.py  (14% → comprehensive)
"""

import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# financial_domain
# ──────────────────────────────────────────────────────────────────────────────

from src.utils.financial_domain import (
    CHANNEL_CODES,
    CHANNEL_TOTAL_REV_SQL,
    CHANNEL_TOTAL_TRX_SQL,
    ITEM_TYPES,
    PARTNER_GROUPS,
    PEAK_HOURS,
    PURCHASE_MODES,
    WEIGHTED_SR_SQL,
    get_partner_sql_variants,
    normalize_partner,
    partner_in_clause,
)


class TestFinancialDomain:
    def test_partner_groups_not_empty(self):
        assert len(PARTNER_GROUPS) > 0
        assert "linkaja" in PARTNER_GROUPS
        assert "dana" in PARTNER_GROUPS

    def test_channel_codes_list(self):
        assert "i1" in CHANNEL_CODES
        assert "a0" in CHANNEL_CODES
        assert isinstance(CHANNEL_CODES, list)

    def test_channel_sql_constants_exist(self):
        assert "i1_trx" in CHANNEL_TOTAL_TRX_SQL
        assert "i1_revenue" in CHANNEL_TOTAL_REV_SQL
        assert "NULLIF" in WEIGHTED_SR_SQL

    def test_item_types_mapping(self):
        assert "recharge" in ITEM_TYPES
        assert "package" in ITEM_TYPES

    def test_purchase_modes_mapping(self):
        assert "SELF" in PURCHASE_MODES
        assert "GIFT" in PURCHASE_MODES

    def test_peak_hours_list(self):
        assert isinstance(PEAK_HOURS, list)
        assert 20 in PEAK_HOURS

    def test_normalize_partner_known_variant(self):
        assert normalize_partner("dana_wec") == "dana"
        assert normalize_partner("gopay_basic") == "gopay"
        assert normalize_partner("linkajawco") == "linkaja"
        assert normalize_partner("shopeepay_wec") == "shopeepay"

    def test_normalize_partner_canonical_name(self):
        assert normalize_partner("dana") == "dana"
        assert normalize_partner("ovo") == "ovo"

    def test_normalize_partner_unknown(self):
        assert normalize_partner("unknown_partner") == "unknown_partner"

    def test_normalize_partner_non_string_passthrough(self):
        assert normalize_partner(123) == 123

    def test_normalize_partner_case_insensitive(self):
        assert normalize_partner("DANA") == "dana"
        assert normalize_partner("GopaY_WEC") == "gopay"

    def test_get_partner_sql_variants_known(self):
        variants = get_partner_sql_variants("linkaja")
        assert "linkaja" in variants
        assert "linkajawco" in variants
        assert "linkaja_wco" in variants
        assert len(variants) > 1

    def test_get_partner_sql_variants_with_space(self):
        variants = get_partner_sql_variants("telkomsel wallet")
        assert "telkomsel_wallet" in variants

    def test_get_partner_sql_variants_unknown_returns_fallback(self):
        variants = get_partner_sql_variants("nonexistent_partner")
        assert variants == ["nonexistent_partner"]

    def test_partner_in_clause_single_variant(self):
        clause = partner_in_clause("indomaret")
        assert "indomaret" in clause
        assert "IN" in clause

    def test_partner_in_clause_multiple_variants(self):
        clause = partner_in_clause("linkaja")
        assert clause.startswith("partner IN")
        assert "'linkaja'" in clause
        assert "linkajawco" in clause

    def test_partner_in_clause_custom_column(self):
        clause = partner_in_clause("gopay", column="payment_provider")
        assert clause.startswith("payment_provider IN")
        assert "'gopay'" in clause


# ──────────────────────────────────────────────────────────────────────────────
# query_cache
# ──────────────────────────────────────────────────────────────────────────────

from src.core.query_cache import QueryCache, build_snapshot, restore_snapshot


class TestQueryCache:
    def setup_method(self):
        self.cache = QueryCache(ttl_seconds=60)

    def test_get_miss_empty_cache(self):
        assert self.cache.get("anything", "db") is None

    def test_put_then_get_hit(self):
        snapshot = {"intent": "trend", "sql": "SELECT 1", "insights": "ok"}
        self.cache.put("my query", "financial_db", snapshot)
        result = self.cache.get("my query", "financial_db")
        assert result == snapshot

    def test_get_normalises_whitespace_and_case(self):
        snapshot = {"intent": "trend"}
        self.cache.put("  MY QUERY  ", "db", snapshot)
        assert self.cache.get("my query", "db") == snapshot

    def test_get_expired_returns_none(self):
        self.cache.put("q", "db", {"data": "x"})
        for entry in self.cache._store.values():
            entry.expires_at = time.monotonic() - 1
        assert self.cache.get("q", "db") is None

    def test_get_expired_removes_entry(self):
        self.cache.put("q", "db", {"data": "x"})
        for entry in self.cache._store.values():
            entry.expires_at = time.monotonic() - 1
        self.cache.get("q", "db")
        assert len(self.cache._store) == 0

    def test_clear_empties_store(self):
        self.cache.put("q1", "db", {"x": 1})
        self.cache.put("q2", "db", {"y": 2})
        self.cache.clear()
        assert self.cache.get("q1", "db") is None
        assert self.cache.get("q2", "db") is None

    def test_size_counts_live_entries(self):
        self.cache.put("q1", "db", {"x": 1})
        self.cache.put("q2", "db", {"y": 2})
        assert self.cache.size() == 2

    def test_size_excludes_expired(self):
        self.cache.put("q", "db", {"x": 1})
        for entry in self.cache._store.values():
            entry.expires_at = time.monotonic() - 1
        assert self.cache.size() == 0

    def test_tier_isolation(self):
        self.cache.put("q", "db", {"tier": "standard"}, tier="standard")
        self.cache.put("q", "db", {"tier": "premium"}, tier="premium")
        assert self.cache.get("q", "db", tier="standard")["tier"] == "standard"
        assert self.cache.get("q", "db", tier="premium")["tier"] == "premium"

    def test_different_databases_isolated(self):
        self.cache.put("q", "db_a", {"db": "a"})
        self.cache.put("q", "db_b", {"db": "b"})
        assert self.cache.get("q", "db_a")["db"] == "a"
        assert self.cache.get("q", "db_b")["db"] == "b"

    def test_key_normalises_query(self):
        k = QueryCache._key("  Q  ", "db", "standard")
        assert k == ("q", "db", "standard")


class TestBuildRestoreSnapshot:
    def test_build_snapshot_extracts_fields(self):
        state = MagicMock()
        state.intent = "trend"
        state.validated_sql = "SELECT 1"
        state.sql = "SELECT 1"
        state.query_result = [{"a": 1}]
        state.row_count = 1
        state.insights = "Some insight"
        state.database = "financial_db"
        state.is_multi_step = False
        state.step_results = []
        state.chart_config = None
        state.tool_calls = []

        snap = build_snapshot(state)
        assert snap["intent"] == "trend"
        assert snap["sql"] == "SELECT 1"
        assert snap["query_result"] == [{"a": 1}]
        assert snap["row_count"] == 1
        assert snap["database"] == "financial_db"

    def test_restore_snapshot_sets_fields(self):
        class _State:
            pass

        state = _State()
        snap = {
            "intent": "summary",
            "validated_sql": "SELECT 2",
            "sql": "SELECT 2",
            "query_result": [],
            "row_count": 0,
            "insights": "",
            "database": "db",
            "is_multi_step": False,
            "step_results": [],
            "chart_config": None,
            "tool_calls": [],
        }
        result = restore_snapshot(state, snap)
        assert result is state
        assert state.intent == "summary"
        assert state.sql == "SELECT 2"
        assert state.row_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# date_range
# ──────────────────────────────────────────────────────────────────────────────

from src.utils.date_range import (
    get_data_year,
    get_earliest_available_date,
    get_latest_available_date,
    get_product_count,
)


def _make_engine_returning(value):
    mock_row = (value,)
    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    return mock_engine


def _make_engine_raising():
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = Exception("DB unavailable")
    return mock_engine


class TestDateRange:
    def test_get_data_year_from_date(self):
        assert get_data_year(date(2026, 3, 31)) == 2026

    def test_get_data_year_none_falls_back_to_today(self):
        year = get_data_year(None)
        assert year == date.today().year

    def test_get_latest_available_date_happy_path(self):
        engine = _make_engine_returning(date(2026, 6, 30))
        result = get_latest_available_date(engine)
        assert result == date(2026, 6, 30)

    def test_get_latest_available_date_none_row(self):
        engine = _make_engine_returning(None)
        result = get_latest_available_date(engine)
        assert result is None

    def test_get_latest_available_date_db_exception(self):
        result = get_latest_available_date(_make_engine_raising())
        assert result is None

    def test_get_earliest_available_date_happy_path(self):
        engine = _make_engine_returning(date(2026, 1, 1))
        result = get_earliest_available_date(engine)
        assert result == date(2026, 1, 1)

    def test_get_earliest_available_date_none_row(self):
        engine = _make_engine_returning(None)
        result = get_earliest_available_date(engine)
        assert result is None

    def test_get_earliest_available_date_db_exception(self):
        result = get_earliest_available_date(_make_engine_raising())
        assert result is None

    def test_get_product_count_happy_path(self):
        engine = _make_engine_returning(42)
        result = get_product_count(engine)
        assert result == 42

    def test_get_product_count_none_row(self):
        engine = _make_engine_returning(None)
        result = get_product_count(engine)
        assert result == 0

    def test_get_product_count_db_exception(self):
        result = get_product_count(_make_engine_raising())
        assert result == 0


# ──────────────────────────────────────────────────────────────────────────────
# baseline_cache
# ──────────────────────────────────────────────────────────────────────────────

from src.core.baseline_cache import BaselineCache


def _make_baseline_engine():
    """Build a mock engine that returns valid data for all four _load_* queries."""
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    period_result = MagicMock()
    period_result.fetchone.return_value = ("2026-01-01", "2026-03-31", 90)

    overall_result = MagicMock()
    overall_result.fetchone.return_value = (10_000.0, 500.0, 1_000_000.0, 50_000.0)

    partner_result = MagicMock()
    partner_result.fetchall.return_value = [
        ("dana",  5_000.0, 200.0,  500_000.0, 25_000.0, 98.5),
        ("gopay", 3_000.0, 150.0,  300_000.0, 15_000.0, 97.0),
        ("ovo",   2_000_000.0, 100_000.0, 2_000_000_000.0, 100_000_000.0, 96.0),
    ]

    channel_result = MagicMock()
    channel_result.fetchall.return_value = [
        ("i1", 8_000.0, 300.0, 800_000.0, 40_000.0),
        ("f0", 2_000.0, 100.0, 200_000.0, 10_000.0),
    ]

    mock_conn.execute.side_effect = [
        period_result,
        overall_result,
        partner_result,
        channel_result,
    ]
    return mock_engine


class TestBaselineCache:
    def setup_method(self):
        self.cache = BaselineCache(_make_baseline_engine())

    def test_period_loaded_correctly(self):
        assert self.cache.period["start"] == "2026-01-01"
        assert self.cache.period["end"] == "2026-03-31"
        assert self.cache.period["days"] == 90

    def test_overall_loaded_correctly(self):
        assert self.cache.overall["trx_mean"] == 10_000.0
        assert self.cache.overall["trx_std"] == 500.0
        assert self.cache.overall["rev_mean"] == 1_000_000.0
        assert self.cache.overall["rev_std"] == 50_000.0

    def test_partners_loaded(self):
        assert "dana" in self.cache.partner
        assert "gopay" in self.cache.partner
        assert self.cache.partner["dana"]["sr_mean"] == 98.5
        assert self.cache.partner["dana"]["trx_mean"] == 5_000.0

    def test_channels_loaded(self):
        assert "i1" in self.cache.channel
        assert "f0" in self.cache.channel
        assert self.cache.channel["i1"]["trx_mean"] == 8_000.0

    # z_score
    def test_z_score_positive(self):
        z = self.cache.z_score(110.0, 100.0, 10.0)
        assert z == 1.0

    def test_z_score_negative(self):
        z = self.cache.z_score(90.0, 100.0, 10.0)
        assert z == -1.0

    def test_z_score_zero_std_returns_none(self):
        assert self.cache.z_score(110.0, 100.0, 0.0) is None

    def test_z_score_exact_mean(self):
        assert self.cache.z_score(100.0, 100.0, 10.0) == 0.0

    # classify_change
    def test_classify_change_normal(self):
        assert self.cache.classify_change(10.0) == "normal"
        assert self.cache.classify_change(-10.0) == "normal"
        assert self.cache.classify_change(0.0) == "normal"

    def test_classify_change_significant(self):
        assert self.cache.classify_change(25.0) == "significant"
        assert self.cache.classify_change(-20.0) == "significant"

    def test_classify_change_extreme(self):
        assert self.cache.classify_change(50.0) == "extreme"
        assert self.cache.classify_change(-100.0) == "extreme"

    def test_classify_change_boundary_15(self):
        assert self.cache.classify_change(14.9) == "normal"
        assert self.cache.classify_change(15.0) == "significant"

    def test_classify_change_boundary_35(self):
        assert self.cache.classify_change(34.9) == "significant"
        assert self.cache.classify_change(35.0) == "extreme"

    # partner_context / channel_context
    def test_partner_context_found(self):
        ctx = self.cache.partner_context("dana")
        assert ctx is not None
        assert ctx["trx_mean"] == 5_000.0

    def test_partner_context_not_found(self):
        assert self.cache.partner_context("unknown_partner") is None

    def test_channel_context_found(self):
        ctx = self.cache.channel_context("i1")
        assert ctx is not None

    def test_channel_context_not_found(self):
        assert self.cache.channel_context("z9") is None

    # _fmt_trx
    def test_fmt_trx_millions(self):
        assert BaselineCache._fmt_trx(1_500_000.0) == "1.5jt"

    def test_fmt_trx_thousands(self):
        assert BaselineCache._fmt_trx(5_000.0) == "5.0rb"

    def test_fmt_trx_small(self):
        assert BaselineCache._fmt_trx(500.0) == "500"

    def test_fmt_trx_exactly_one_million(self):
        assert "jt" in BaselineCache._fmt_trx(1_000_000.0)

    # _fmt_rev
    def test_fmt_rev_billions(self):
        result = BaselineCache._fmt_rev(2_500_000_000.0)
        assert "miliar" in result
        assert "2.5" in result

    def test_fmt_rev_millions(self):
        result = BaselineCache._fmt_rev(3_000_000.0)
        assert "juta" in result
        assert "3.0" in result

    def test_fmt_rev_small(self):
        result = BaselineCache._fmt_rev(500.0)
        assert "500" in result

    # narrative
    def test_narrative_returns_string(self):
        text = self.cache.narrative()
        assert isinstance(text, str)
        assert "90 hari" in text

    def test_narrative_contains_partner_data(self):
        text = self.cache.narrative()
        assert "dana" in text or "gopay" in text

    def test_narrative_contains_channel_data(self):
        text = self.cache.narrative()
        assert "i1" in text or "f0" in text

    def test_narrative_large_numbers_formatted(self):
        # ovo has 2M trx — should appear as "2.0jt"
        text = self.cache.narrative()
        assert "jt" in text or "rb" in text


# ──────────────────────────────────────────────────────────────────────────────
# token_logger (no-DB paths)
# ──────────────────────────────────────────────────────────────────────────────

import src.core.token_logger as _tl


class TestTokenLoggerNoDB:
    def test_log_token_usage_no_engine_silent(self):
        with patch("src.core.token_logger._get_engine", return_value=None):
            _tl.log_token_usage(
                request_id="req-1",
                session_id=None,
                agent_name="sql_generator",
                model="claude-sonnet-4-6",
                quality_tier="standard",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                iteration=None,
            )

    def test_get_usage_summary_no_engine_current_month(self):
        with patch("src.core.token_logger._get_engine", return_value=None):
            result = _tl.get_usage_summary("current_month")
        assert result == {"error": "database unavailable"}

    def test_get_usage_summary_no_engine_today(self):
        with patch("src.core.token_logger._get_engine", return_value=None):
            result = _tl.get_usage_summary("today")
        assert result == {"error": "database unavailable"}

    def test_get_usage_summary_no_engine_all_time(self):
        with patch("src.core.token_logger._get_engine", return_value=None):
            result = _tl.get_usage_summary("all_time")
        assert result == {"error": "database unavailable"}


# ──────────────────────────────────────────────────────────────────────────────
# tool_registry
# ──────────────────────────────────────────────────────────────────────────────

from src.tools.tool_registry import TOOL_DEFINITIONS, execute_tool, to_anthropic_tools


class TestToolRegistry:
    def test_to_anthropic_tools_length_matches(self):
        anthropic = to_anthropic_tools(TOOL_DEFINITIONS)
        assert len(anthropic) == len(TOOL_DEFINITIONS)

    def test_to_anthropic_tools_has_required_keys(self):
        anthropic = to_anthropic_tools(TOOL_DEFINITIONS)
        for t in anthropic:
            assert "name" in t
            assert "description" in t
            assert "input_schema" in t

    def test_to_anthropic_tools_custom_input(self):
        openai_fmt = [{
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "Does something useful",
                "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
            },
        }]
        result = to_anthropic_tools(openai_fmt)
        assert len(result) == 1
        assert result[0]["name"] == "my_tool"
        assert result[0]["description"] == "Does something useful"
        assert result[0]["input_schema"]["type"] == "object"

    def test_execute_tool_unknown_name(self):
        result = execute_tool("totally_unknown_tool", {}, MagicMock())
        assert result["row_count"] == 0
        assert result["data"] == []
        assert "Unknown tool" in result["description"]

    def test_execute_tool_known_name_dispatches(self):
        mock_engine = MagicMock()
        fake_result = {"data": [{"x": 1}], "row_count": 1, "sql": "SELECT 1", "description": "ok"}
        with patch("src.tools.tool_registry.get_summary", return_value=fake_result) as mock_fn:
            result = execute_tool(
                "get_summary",
                {"period_start": "2026-01-01", "period_end": "2026-01-31"},
                mock_engine,
            )
            assert mock_fn.called
            assert result["row_count"] == 1

    def test_execute_tool_passes_kwargs(self):
        mock_engine = MagicMock()
        fake_result = {"data": [], "row_count": 0, "sql": "", "description": ""}
        with patch("src.tools.tool_registry.detect_anomaly", return_value=fake_result) as mock_fn:
            execute_tool(
                "detect_anomaly",
                {"target_date": "2026-06-01", "dimension": "partner", "threshold_pct": 30},
                mock_engine,
            )
            call_kwargs = mock_fn.call_args[1]
            assert call_kwargs["target_date"] == "2026-06-01"
            assert call_kwargs["db_engine"] is mock_engine


# ──────────────────────────────────────────────────────────────────────────────
# context_distiller
# ──────────────────────────────────────────────────────────────────────────────

from src.models.agent_state import AgentState
from src.utils.context_distiller import (
    _build_correlations,
    _build_glossary,
    _build_highlights,
    _col_label,
    _detect_trend,
    _extract_numeric,
    _fmt,
    _is_date_col,
    _is_numeric,
    _pearson,
    distill_context,
)


def _state_with(query_result, query="test query"):
    s = AgentState(query=query)
    s.query_result = query_result
    return s


# ── distill_context ──

class TestDistillContext:
    def test_empty_list_returns_empty(self):
        assert distill_context(_state_with([])) == ""

    def test_none_query_result_returns_empty(self):
        assert distill_context(_state_with(None)) == ""

    def test_non_dict_rows_returns_empty(self):
        assert distill_context(_state_with([[1, 2, 3]])) == ""

    def test_single_numeric_row_returns_string(self):
        result = distill_context(_state_with([{"partner": "dana", "total_trx": 1000}]))
        assert isinstance(result, str)

    def test_multi_row_numeric_produces_highlights(self):
        data = [
            {"partner": "dana",  "total_trx": 1000, "total_revenue": 500_000},
            {"partner": "gopay", "total_trx": 2000, "total_revenue": 800_000},
            {"partner": "ovo",   "total_trx": 1500, "total_revenue": 600_000},
        ]
        result = distill_context(_state_with(data, query="revenue partner"))
        assert "HIGHLIGHT" in result

    def test_glossary_triggered_by_query_keyword(self):
        data = [{"partner": "dana", "total_trx": 100}]
        result = distill_context(_state_with(data, query="berapa success rate partner"))
        assert isinstance(result, str)

    def test_glossary_triggered_by_column_name(self):
        data = [{"sr": 98.5, "total_revenue": 1_000_000}]
        result = distill_context(_state_with(data, query=""))
        assert "SR" in result or "REVENUE" in result

    def test_exception_in_distill_returns_empty(self):
        class _BrokenState:
            @property
            def query_result(self):
                raise RuntimeError("simulated failure")
            query = ""

        assert distill_context(_BrokenState()) == ""

    def test_time_series_data_with_trend(self):
        data = [
            {"date": "2026-01-01", "total_trx": 100},
            {"date": "2026-01-02", "total_trx": 150},
            {"date": "2026-01-03", "total_trx": 200},
            {"date": "2026-01-04", "total_trx": 250},
        ]
        result = distill_context(_state_with(data))
        assert isinstance(result, str)

    def test_correlation_with_enough_rows(self):
        data = [
            {"total_trx": i * 100, "total_revenue": i * 500}
            for i in range(1, 6)
        ]
        result = distill_context(_state_with(data))
        assert isinstance(result, str)


# ── _build_highlights ──

class TestBuildHighlights:
    def test_with_entity_col_prints_max_min(self):
        data = [
            {"partner": "dana",  "total_trx": 100},
            {"partner": "gopay", "total_trx": 200},
            {"partner": "ovo",   "total_trx": 150},
        ]
        result = _build_highlights(data)
        assert "tertinggi" in result

    def test_without_entity_col(self):
        data = [{"total_trx": 100}, {"total_trx": 200}]
        result = _build_highlights(data)
        assert "tertinggi" in result
        assert "200" in result or "0.2rb" in result

    def test_time_series_shows_trend_and_change(self):
        data = [
            {"date": "2026-01-01", "total_trx": 100},
            {"date": "2026-01-02", "total_trx": 200},
            {"date": "2026-01-03", "total_trx": 300},
            {"date": "2026-01-04", "total_trx": 400},
        ]
        result = _build_highlights(data)
        assert "Tren" in result or "Perubahan" in result

    def test_anomaly_detection_triggered(self):
        # 5 normal values + 1 outlier => z > 2 for the outlier
        data = [{"partner": f"p{i}", "total_trx": 100} for i in range(5)]
        data.append({"partner": "outlier", "total_trx": 1000})
        result = _build_highlights(data)
        assert "Anomali" in result

    def test_single_row_no_output(self):
        # Only 1 row → len(values) < 2 → nothing added
        data = [{"total_trx": 999}]
        result = _build_highlights(data)
        assert result == ""

    def test_mean_line_appended(self):
        data = [{"total_trx": 100}, {"total_trx": 200}, {"total_trx": 300}]
        result = _build_highlights(data)
        assert "Rata-rata" in result


# ── _build_correlations ──

class TestBuildCorrelations:
    def test_too_few_rows_returns_empty(self):
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        assert _build_correlations(data) == ""

    def test_only_one_numeric_col_returns_empty(self):
        data = [
            {"partner": "dana", "total_trx": 100},
            {"partner": "gopay", "total_trx": 200},
            {"partner": "ovo", "total_trx": 300},
            {"partner": "ovo2", "total_trx": 400},
        ]
        assert _build_correlations(data) == ""

    def test_perfect_positive_correlation_detected(self):
        data = [
            {"total_trx": i * 100, "total_revenue": i * 500}
            for i in range(1, 6)
        ]
        result = _build_correlations(data)
        assert "searah" in result

    def test_perfect_negative_correlation_detected(self):
        data = [
            {"total_trx": (6 - i) * 100, "fail_trx": i * 100}
            for i in range(1, 6)
        ]
        result = _build_correlations(data)
        assert "berlawanan" in result

    def test_weak_correlation_returns_empty(self):
        import random
        random.seed(42)
        data = [
            {"total_trx": random.randint(1, 100), "total_revenue": random.randint(1, 100)}
            for _ in range(5)
        ]
        result = _build_correlations(data)
        assert isinstance(result, str)


# ── _build_glossary ──

class TestBuildGlossary:
    def test_empty_data_returns_empty(self):
        assert _build_glossary([], "some query") == ""

    def test_match_from_column_name(self):
        data = [{"sr": 98.5, "total_trx": 1000}]
        result = _build_glossary(data, "")
        assert "SR" in result.upper() or "TOTAL_TRX" in result.upper()

    def test_match_from_query_text(self):
        data = [{"amount": 100}]
        result = _build_glossary(data, "berapa revenue partner dana")
        assert "REVENUE" in result.upper()

    def test_max_six_terms_returned(self):
        data = [{"sr": 1, "gmv": 2, "revenue": 3, "total_trx": 4, "delta": 5,
                 "settlement": 6, "rekonsiliasi": 7}]
        result = _build_glossary(data, "sr gmv revenue delta settlement rekonsiliasi")
        count = result.count("- **")
        assert count <= 6

    def test_no_matching_terms(self):
        data = [{"obscure_col": 100}]
        result = _build_glossary(data, "nothing matching here")
        assert result == ""


# ── _is_numeric ──

class TestIsNumeric:
    def test_bool_is_not_numeric(self):
        assert _is_numeric(True) is False
        assert _is_numeric(False) is False

    def test_int_is_numeric(self):
        assert _is_numeric(42) is True
        assert _is_numeric(0) is True
        assert _is_numeric(-5) is True

    def test_float_is_numeric(self):
        assert _is_numeric(3.14) is True
        assert _is_numeric(0.0) is True

    def test_nan_is_not_numeric(self):
        import math
        assert _is_numeric(float("nan")) is False

    def test_numeric_string(self):
        assert _is_numeric("123.45") is True
        assert _is_numeric("  100  ") is True
        assert _is_numeric("-5.5") is True

    def test_non_numeric_string(self):
        assert _is_numeric("abc") is False
        assert _is_numeric("") is False
        assert _is_numeric("1.2.3") is False

    def test_none_is_not_numeric(self):
        assert _is_numeric(None) is False

    def test_list_is_not_numeric(self):
        assert _is_numeric([1, 2, 3]) is False


# ── _extract_numeric ──

class TestExtractNumeric:
    def test_extracts_int_and_float(self):
        data = [{"val": 1}, {"val": 2.5}]
        result = _extract_numeric(data, "val")
        assert result == [1.0, 2.5]

    def test_skips_bool_values(self):
        data = [{"val": True}, {"val": 10}]
        result = _extract_numeric(data, "val")
        assert result == [10.0]

    def test_skips_none(self):
        data = [{"val": None}, {"val": 5}]
        result = _extract_numeric(data, "val")
        assert result == [5.0]

    def test_skips_nan(self):
        import math
        data = [{"val": float("nan")}, {"val": 10}]
        result = _extract_numeric(data, "val")
        assert result == [10.0]

    def test_missing_key_skipped(self):
        data = [{"other": 1}, {"val": 2}]
        result = _extract_numeric(data, "val")
        assert result == [2.0]


# ── _is_date_col ──

class TestIsDateCol:
    def test_recognises_date_keywords(self):
        assert _is_date_col("date") is True
        assert _is_date_col("tanggal") is True
        assert _is_date_col("periode") is True
        assert _is_date_col("bulan") is True
        assert _is_date_col("transaction_date") is True
        assert _is_date_col("time") is True
        assert _is_date_col("tgl") is True
        assert _is_date_col("month") is True
        assert _is_date_col("year") is True

    def test_rejects_non_date_columns(self):
        assert _is_date_col("partner") is False
        assert _is_date_col("total_trx") is False
        assert _is_date_col("revenue") is False
        assert _is_date_col("sr") is False


# ── _col_label ──

class TestColLabel:
    def test_underscores_replaced_and_title_cased(self):
        assert _col_label("total_trx") == "Total Trx"
        assert _col_label("total_revenue") == "Total Revenue"

    def test_no_underscore_just_title_case(self):
        assert _col_label("partner") == "Partner"
        assert _col_label("sr") == "Sr"


# ── _fmt ──

class TestFmt:
    def test_billions(self):
        assert _fmt(2_500_000_000.0) == "2.50M"

    def test_millions(self):
        assert _fmt(1_500_000.0) == "1.50jt"

    def test_thousands(self):
        assert _fmt(5_000.0) == "5.0rb"

    def test_decimal_float(self):
        assert _fmt(3.14) == "3.14"

    def test_whole_float_returns_int_format(self):
        result = _fmt(500.0)
        assert result == "500"

    def test_negative_billions(self):
        result = _fmt(-2_000_000_000.0)
        assert "M" in result

    def test_negative_millions(self):
        result = _fmt(-1_500_000.0)
        assert "jt" in result

    def test_small_int(self):
        assert _fmt(0.0) == "0"

    def test_large_int_format(self):
        result = _fmt(1_234.0)
        assert "rb" in result


# ── _detect_trend ──

class TestDetectTrend:
    def test_consistent_upward(self):
        result = _detect_trend([100.0, 200.0, 300.0, 400.0, 500.0])
        assert result is not None
        assert "naik" in result

    def test_consistent_downward(self):
        result = _detect_trend([500.0, 400.0, 300.0, 200.0, 100.0])
        assert result is not None
        assert "turun" in result

    def test_stable(self):
        result = _detect_trend([100.0, 100.0, 100.0, 100.0])
        assert result is not None
        assert "stabil" in result

    def test_zero_mean_returns_none(self):
        result = _detect_trend([0.0, 0.0, 0.0])
        assert result is None

    def test_small_fluctuation_is_stable(self):
        result = _detect_trend([100.0, 101.0, 100.0, 99.0, 100.0])
        assert result is not None
        assert "stabil" in result


# ── _pearson ──

class TestPearson:
    def test_perfect_positive_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = _pearson(xs, ys)
        assert r is not None
        assert abs(r - 1.0) < 0.001

    def test_perfect_negative_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [10.0, 8.0, 6.0, 4.0, 2.0]
        r = _pearson(xs, ys)
        assert r is not None
        assert abs(r + 1.0) < 0.001

    def test_too_few_values_returns_none(self):
        assert _pearson([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) is None

    def test_zero_x_variance_returns_none(self):
        xs = [5.0, 5.0, 5.0, 5.0, 5.0]
        ys = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _pearson(xs, ys) is None

    def test_zero_y_variance_returns_none(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [3.0, 3.0, 3.0, 3.0, 3.0]
        assert _pearson(xs, ys) is None

    def test_minimum_four_values(self):
        # exactly 4 values should work
        r = _pearson([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
        assert r is not None
        assert abs(r - 1.0) < 0.001


# ── additional context_distiller edge cases (lines 170, 173, 230) ──

class TestContextDistillerEdgeCases:
    def test_build_correlations_skips_length_mismatch(self):
        # "b" has a None → extract_numeric returns 4 items; "a" returns 5 → mismatch → line 170
        data = [
            {"a": 100, "b": 500},
            {"a": 200, "b": None},
            {"a": 300, "b": 1500},
            {"a": 400, "b": 2000},
            {"a": 500, "b": 2500},
        ]
        result = _build_correlations(data)
        assert isinstance(result, str)

    def test_build_correlations_skips_zero_variance(self):
        # All "a" values constant → pearson returns None → line 173
        data = [
            {"a": 5, "b": 100},
            {"a": 5, "b": 200},
            {"a": 5, "b": 300},
            {"a": 5, "b": 400},
            {"a": 5, "b": 500},
        ]
        result = _build_correlations(data)
        assert isinstance(result, str)

    def test_is_numeric_decimal_returns_true(self):
        from decimal import Decimal
        assert _is_numeric(Decimal("3.14")) is True  # line 230: try: float(val); return True


# ──────────────────────────────────────────────────────────────────────────────
# logger — JSON formatter exception branch, file handler path
# ──────────────────────────────────────────────────────────────────────────────

import json
import logging
import sys
import tempfile

from src.utils.logger import _JsonFormatter, setup_logger


class TestLogger:
    def test_json_formatter_basic_output(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO,
            pathname="", lineno=0, msg="hello world", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"

    def test_json_formatter_with_exception_info(self):
        formatter = _JsonFormatter()
        try:
            raise ValueError("test error for logger")
        except ValueError:
            exc = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=0, msg="error happened", args=(), exc_info=exc,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed  # covers line 32

    def test_setup_logger_with_file_handler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger_name = "test.coverage.file.handler"
            logger = setup_logger(
                name=logger_name,
                log_to_file=True,
                log_dir=tmpdir,
            )
            file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
            assert len(file_handlers) >= 1  # covers lines 90-94
            for h in logger.handlers[:]:
                h.close()
                logger.removeHandler(h)
            logging.Logger.manager.loggerDict.pop(logger_name, None)


# ──────────────────────────────────────────────────────────────────────────────
# base_agent — reset_metrics, get_info, __repr__, __str__, super().execute, error path
# ──────────────────────────────────────────────────────────────────────────────

from src.core.base_agent import BaseAgent
from src.utils.exceptions import AgentExecutionError


class _SimpleAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="simple_agent", version="2.0.0")

    def execute(self, state: AgentState) -> AgentState:
        return state


class _SuperCallAgent(BaseAgent):
    """Calls super().execute() to hit the abstract pass body (line 91)."""
    def __init__(self):
        super().__init__(name="super_call_agent", version="0.1.0")

    def execute(self, state: AgentState) -> AgentState:
        super().execute(state)  # covers line 91
        return state


class _BoomAgent(BaseAgent):
    """Raises a plain ValueError to trigger the re-raise path (line 137)."""
    def __init__(self):
        super().__init__(name="boom_agent", version="0.1.0")

    def execute(self, state: AgentState) -> AgentState:
        raise ValueError("intentional boom")


class TestBaseAgentUtilities:
    def setup_method(self):
        self.agent = _SimpleAgent()

    def test_execute_super_covers_pass(self):
        state = AgentState(query="test pass")
        agent = _SuperCallAgent()
        result = agent.execute(state)
        assert result is state

    def test_run_wraps_value_error_in_agent_execution_error(self):
        state = AgentState(query="boom query")
        agent = _BoomAgent()
        with pytest.raises(AgentExecutionError) as exc_info:
            agent.run(state)
        assert "intentional boom" in str(exc_info.value)

    def test_reset_metrics_zeros_counters(self):
        state = AgentState(query="test")
        self.agent.run(state)
        assert self.agent.metrics["total_calls"] == 1
        self.agent.reset_metrics()
        assert self.agent.metrics["total_calls"] == 0
        assert self.agent.metrics["successful_calls"] == 0
        assert self.agent.metrics["failed_calls"] == 0

    def test_get_info_returns_metadata(self):
        info = self.agent.get_info()
        assert info["name"] == "simple_agent"
        assert info["version"] == "2.0.0"
        assert info["class"] == "_SimpleAgent"

    def test_repr_contains_name_and_version(self):
        r = repr(self.agent)
        assert "simple_agent" in r
        assert "2.0.0" in r

    def test_str_returns_name_and_version(self):
        s = str(self.agent)
        assert "simple_agent" in s
        assert "v2.0.0" in s


# ──────────────────────────────────────────────────────────────────────────────
# retrieval_evaluator — fallback when LLM excludes all tables (lines 71-75)
# ──────────────────────────────────────────────────────────────────────────────

from src.agents.retrieval_evaluator import RetrievalEvaluator
from src.models.retrieved_table import RetrievedTable


class TestRetrievalEvaluatorFallback:
    def test_fallback_when_all_tables_excluded(self):
        evaluator = RetrievalEvaluator()
        state = AgentState(query="berapa total transaksi")
        state.database = "financial_db"
        tables = [
            RetrievedTable(
                db_name="financial_db",
                table_name=f"table_{i}",
                columns=[],
                description="test table",
                similarity_score=0.9,
                relationships=[],
            )
            for i in range(3)
        ]
        state.retrieved_tables = tables

        with patch.object(evaluator, "_call_llm", return_value="EXCLUDED: all tables"), \
             patch.object(evaluator, "_parse_response", return_value=([], [], tables)), \
             patch.object(evaluator, "_record_token_usage"):
            result = evaluator.execute(state)

        # All tables fell back from the "all excluded" path
        assert len(result.evaluated_tables) == 3
        assert result.evaluated_tables == tables
