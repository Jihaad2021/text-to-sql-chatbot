"""
Unit tests for context_distiller.

Tests cover:
- _is_numeric: int, float, string number, bool, None, NaN, non-numeric
- _extract_numeric: filters bools, None, non-numeric values
- _fmt: number formatting at billion/million/thousand/small scales
- _is_date_col: keyword detection in column names
- _col_label: underscore replacement and title-casing
- _detect_trend: upward / downward / stable trend detection
- _pearson: positive correlation, negative correlation, zero variance, too few points
- _build_highlights: top entity, anomaly detection (z-score > 2), time-series change %
- _build_correlations: skipped when <4 rows or <2 numeric cols; emits positive/negative
- _build_glossary: matches column names and query text; caps at 6 entries
- distill_context: returns "" on empty data; never raises on bad input
"""

import math

import pytest

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

# ── _is_numeric ────────────────────────────────────────────────────────────────

class TestIsNumeric:

    def test_int_is_numeric(self):
        assert _is_numeric(42) is True

    def test_float_is_numeric(self):
        assert _is_numeric(3.14) is True

    def test_string_number_is_numeric(self):
        assert _is_numeric("100") is True
        assert _is_numeric("3.14") is True

    def test_bool_is_not_numeric(self):
        assert _is_numeric(True) is False
        assert _is_numeric(False) is False

    def test_none_is_not_numeric(self):
        assert _is_numeric(None) is False

    def test_nan_is_not_numeric(self):
        assert _is_numeric(float("nan")) is False

    def test_non_numeric_string_is_not_numeric(self):
        assert _is_numeric("gopay") is False
        assert _is_numeric("") is False

    def test_zero_is_numeric(self):
        assert _is_numeric(0) is True
        assert _is_numeric(0.0) is True


# ── _extract_numeric ───────────────────────────────────────────────────────────

class TestExtractNumeric:

    def test_extracts_int_and_float(self):
        data = [{"val": 10}, {"val": 20.5}]
        result = _extract_numeric(data, "val")
        assert result == [10.0, 20.5]

    def test_skips_bools(self):
        data = [{"val": True}, {"val": 5}]
        result = _extract_numeric(data, "val")
        assert result == [5.0]

    def test_skips_none_and_nan(self):
        data = [{"val": None}, {"val": float("nan")}, {"val": 3}]
        result = _extract_numeric(data, "val")
        assert result == [3.0]

    def test_missing_key_skipped(self):
        data = [{"other": 1}, {"val": 5}]
        result = _extract_numeric(data, "val")
        assert result == [5.0]


# ── _fmt ───────────────────────────────────────────────────────────────────────

class TestFmt:

    def test_billions(self):
        assert "M" in _fmt(2_500_000_000)

    def test_millions(self):
        result = _fmt(1_500_000)
        assert "jt" in result

    def test_thousands(self):
        result = _fmt(5_000)
        assert "rb" in result

    def test_small_float(self):
        result = _fmt(3.14)
        assert "3.14" in result

    def test_integer_no_decimal(self):
        result = _fmt(100.0)
        assert "." not in result or result == "100"

    def test_negative_number(self):
        result = _fmt(-1_000_000)
        assert "jt" in result


# ── _is_date_col ───────────────────────────────────────────────────────────────

class TestIsDateCol:

    def test_date_column(self):
        assert _is_date_col("date") is True
        assert _is_date_col("transaction_date") is True

    def test_periode_column(self):
        assert _is_date_col("periode") is True

    def test_bulan_column(self):
        assert _is_date_col("bulan") is True

    def test_month_column(self):
        assert _is_date_col("month") is True

    def test_non_date_column(self):
        assert _is_date_col("partner") is False
        assert _is_date_col("total_trx") is False


# ── _col_label ─────────────────────────────────────────────────────────────────

class TestColLabel:

    def test_underscores_replaced(self):
        assert "Total Trx" == _col_label("total_trx")

    def test_title_cased(self):
        assert _col_label("success_rate") == "Success Rate"

    def test_single_word(self):
        assert _col_label("revenue") == "Revenue"


# ── _detect_trend ──────────────────────────────────────────────────────────────

class TestDetectTrend:

    def test_upward_trend(self):
        values = [100, 120, 140, 160, 180]
        result = _detect_trend(values)
        assert result is not None
        assert "naik" in result

    def test_downward_trend(self):
        values = [180, 160, 140, 120, 100]
        result = _detect_trend(values)
        assert result is not None
        assert "turun" in result

    def test_flat_trend(self):
        values = [100, 101, 100, 99, 100]
        result = _detect_trend(values)
        assert result is not None
        assert "stabil" in result

    def test_zero_mean_returns_none(self):
        values = [0, 0, 0, 0]
        result = _detect_trend(values)
        assert result is None

    def test_constant_values_returns_stable(self):
        values = [100, 100, 100, 100, 100]
        result = _detect_trend(values)
        assert result is not None
        assert "stabil" in result


# ── _pearson ───────────────────────────────────────────────────────────────────

class TestPearson:

    def test_perfect_positive_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [2, 4, 6, 8, 10]
        r = _pearson(xs, ys)
        assert r is not None
        assert abs(r - 1.0) < 0.001

    def test_perfect_negative_correlation(self):
        xs = [1, 2, 3, 4, 5]
        ys = [10, 8, 6, 4, 2]
        r = _pearson(xs, ys)
        assert r is not None
        assert abs(r + 1.0) < 0.001

    def test_zero_variance_returns_none(self):
        xs = [5, 5, 5, 5, 5]
        ys = [1, 2, 3, 4, 5]
        assert _pearson(xs, ys) is None

    def test_fewer_than_4_points_returns_none(self):
        assert _pearson([1, 2, 3], [1, 2, 3]) is None

    def test_no_correlation(self):
        xs = [1, 2, 3, 4, 5, 6, 7, 8]
        ys = [3, 1, 4, 1, 5, 9, 2, 6]
        r = _pearson(xs, ys)
        assert r is not None
        assert -1.0 <= r <= 1.0


# ── _build_highlights ──────────────────────────────────────────────────────────

class TestBuildHighlights:

    def test_identifies_highest_value_entity(self):
        data = [
            {"partner": "GoPay", "total_trx": 1000},
            {"partner": "OVO",   "total_trx": 500},
        ]
        result = _build_highlights(data)
        assert "GoPay" in result
        assert "tertinggi" in result.lower()

    def test_anomaly_detected_on_outlier(self):
        data = [
            {"partner": f"P{i}", "total_trx": 100} for i in range(8)
        ] + [{"partner": "Outlier", "total_trx": 10000}]
        result = _build_highlights(data)
        assert "Anomali" in result or "outlier" in result.lower() or "Outlier" in result

    def test_time_series_shows_change_pct(self):
        data = [
            {"date": f"2026-04-{i:02d}", "total_trx": 100 + i * 10}
            for i in range(1, 6)
        ]
        result = _build_highlights(data)
        assert "%" in result or "naik" in result or "turun" in result

    def test_single_row_returns_empty(self):
        data = [{"partner": "GoPay", "total_trx": 100}]
        result = _build_highlights(data)
        assert result == ""

    def test_no_numeric_cols_returns_empty(self):
        data = [{"partner": "GoPay"}, {"partner": "OVO"}]
        result = _build_highlights(data)
        assert result == ""


# ── _build_correlations ────────────────────────────────────────────────────────

class TestBuildCorrelations:

    def test_skipped_when_fewer_than_4_rows(self):
        data = [{"a": i, "b": i * 2} for i in range(3)]
        assert _build_correlations(data) == ""

    def test_skipped_when_fewer_than_2_numeric_cols(self):
        data = [{"partner": f"P{i}", "total_trx": i * 10} for i in range(5)]
        assert _build_correlations(data) == ""

    def test_positive_correlation_detected(self):
        data = [{"trx": i * 10, "rev": i * 100} for i in range(1, 7)]
        result = _build_correlations(data)
        assert "searah" in result

    def test_negative_correlation_detected(self):
        data = [{"trx": i, "fail": 10 - i} for i in range(1, 7)]
        result = _build_correlations(data)
        assert "berlawanan" in result

    def test_weak_correlation_not_reported(self):
        data = [
            {"a": 1, "b": 5},
            {"a": 2, "b": 1},
            {"a": 3, "b": 9},
            {"a": 4, "b": 2},
            {"a": 5, "b": 7},
        ]
        result = _build_correlations(data)
        assert result == ""


# ── _build_glossary ────────────────────────────────────────────────────────────

class TestBuildGlossary:

    def test_matches_column_name(self):
        data = [{"total_trx": 100, "partner": "GoPay"}]
        result = _build_glossary(data, "query")
        assert "TOTAL_TRX" in result or "PARTNER" in result

    def test_matches_query_text(self):
        # Glossary matching is substring-based on the exact key ("sr", not "success rate")
        data = [{"value": 1}]
        result = _build_glossary(data, "berapa sr dan revenue bulan ini?")
        assert "SR" in result or "REVENUE" in result

    def test_max_6_entries(self):
        data = [{"total_trx": 1, "partner": 1, "revenue": 1,
                 "sr": 1, "fail_trx": 1, "gmv": 1, "settlement": 1}]
        result = _build_glossary(data, "sr revenue partner total_trx fail_trx settlement")
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) <= 6

    def test_no_match_returns_empty(self):
        data = [{"unknown_col": 1}]
        result = _build_glossary(data, "some irrelevant query")
        assert result == ""


# ── distill_context ────────────────────────────────────────────────────────────

class TestDistillContext:

    def test_empty_query_result_returns_empty(self):
        state = AgentState(query="test", database="financial_db")
        state.query_result = []
        assert distill_context(state) == ""

    def test_none_query_result_returns_empty(self):
        state = AgentState(query="test", database="financial_db")
        state.query_result = None
        assert distill_context(state) == ""

    def test_valid_data_returns_non_empty_string(self):
        state = AgentState(query="berapa total transaksi?", database="financial_db")
        state.query_result = [
            {"partner": "GoPay", "total_trx": 1000},
            {"partner": "OVO",   "total_trx": 800},
            {"partner": "DANA",  "total_trx": 600},
        ]
        result = distill_context(state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_never_raises_on_malformed_data(self):
        state = AgentState(query="test", database="financial_db")
        state.query_result = ["not", "a", "dict"]
        result = distill_context(state)
        assert result == ""

    def test_output_contains_highlight_section(self):
        state = AgentState(query="top partner", database="financial_db")
        state.query_result = [
            {"partner": "GoPay", "total_trx": 1000},
            {"partner": "OVO",   "total_trx": 500},
        ]
        result = distill_context(state)
        assert "HIGHLIGHT" in result
