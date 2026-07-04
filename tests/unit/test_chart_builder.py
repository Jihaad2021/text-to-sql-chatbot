"""
Unit tests for InsightGenerator._build_chart_configs() — semantic suffix grouping.

Covers:
  1. detect_anomaly schema (9 numeric cols): pct_change group → chart 1,
     target group → chart 2, baseline cols logged as not-charted.
  2. compare_periods schema: pct_change group only (no _target/_baseline),
     raw period cols (trx_a, rev_b …) logged as not-charted.
  3. Fallback path: plain SQL / get_trend (no suffix matches) → original
     positional pairing, behavior unchanged from pre-fix.
  4. Warning log is explicit — names the exact dropped columns.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from src.agents.insight_generator import InsightGenerator
from src.models.agent_state import AgentState


# ── Shared fixture ────────────────────────────────────────────────────────

@pytest.fixture
def ig():
    with patch.object(InsightGenerator, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        return InsightGenerator()


def _state(data: list[dict]) -> AgentState:
    return AgentState(
        query="test",
        database="financial_db",
        query_result=data,
        row_count=len(data),
        validated_sql="(tool)",
    )


# ── detect_anomaly schema (9 numeric cols across 3 suffix groups) ─────────

_DETECT_DATA = [
    {
        "entity": "Roblox Gift Card",
        "trx_target": 14572, "trx_baseline_avg": 10388.57, "trx_pct_change": 40.27,
        "rev_target": 15_000_000_000, "rev_baseline_avg": 10_692_857_143, "rev_pct_change": 40.29,
        "sr_target": 99.21, "sr_baseline_avg": 99.45, "sr_pct_change": -0.24,
        "is_anomaly": True,
    },
    {
        "entity": "Telkomsel Token Listrik",
        "trx_target": 8203, "trx_baseline_avg": 12140.71, "trx_pct_change": -32.43,
        "rev_target": 8_203_000_000, "rev_baseline_avg": 12_140_714_286, "rev_pct_change": -32.44,
        "sr_target": 97.89, "sr_baseline_avg": 98.76, "sr_pct_change": -0.87,
        "is_anomaly": True,
    },
    {
        "entity": "MyTelkomsel Premium",
        "trx_target": 5901, "trx_baseline_avg": 6214.28, "trx_pct_change": -5.04,
        "rev_target": 4_720_800_000, "rev_baseline_avg": 4_971_424_000, "rev_pct_change": -5.04,
        "sr_target": 99.83, "sr_baseline_avg": 99.89, "sr_pct_change": -0.06,
        "is_anomaly": False,
    },
    {
        "entity": "Google Play Voucher",
        "trx_target": 3842, "trx_baseline_avg": 4102.14, "trx_pct_change": -6.34,
        "rev_target": 3_457_800_000, "rev_baseline_avg": 3_691_928_000, "rev_pct_change": -6.34,
        "sr_target": 99.58, "sr_baseline_avg": 99.61, "sr_pct_change": -0.03,
        "is_anomaly": False,
    },
]


class TestDetectAnomalySemanticGrouping:
    """Chart 1 must contain ALL *_pct_change cols; chart 2 the *_target cols."""

    def test_chart_1_contains_all_pct_change_cols(self, ig):
        configs = ig._build_chart_configs(_state(_DETECT_DATA))
        c1_labels = [ds["label"] for ds in configs[0]["datasets"]]
        assert "Trx Pct Change" in c1_labels
        assert "Rev Pct Change" in c1_labels
        assert "Sr Pct Change"  in c1_labels

    def test_chart_1_does_not_contain_absolute_cols(self, ig):
        configs = ig._build_chart_configs(_state(_DETECT_DATA))
        c1_labels = [ds["label"] for ds in configs[0]["datasets"]]
        assert "Rev Target"      not in c1_labels, "rev_target must NOT be in chart 1"
        assert "Trx Target"      not in c1_labels
        assert "Trx Baseline Avg" not in c1_labels

    def test_chart_1_values_are_percentage_scale(self, ig):
        """All values in the pct_change chart must be small (no billion-scale values)."""
        configs = ig._build_chart_configs(_state(_DETECT_DATA))
        for ds in configs[0]["datasets"]:
            max_val = max(abs(v or 0) for v in ds["data"])
            assert max_val < 1000, (
                f"Dataset '{ds['label']}' in pct_change chart has value {max_val} — "
                f"expected percentage scale (<1000)"
            )

    def test_chart_2_contains_target_cols(self, ig):
        configs = ig._build_chart_configs(_state(_DETECT_DATA))
        assert len(configs) == 2, "Expected 2 charts: pct_change + target"
        c2_labels = [ds["label"] for ds in configs[1]["datasets"]]
        assert "Trx Target" in c2_labels
        assert "Rev Target" in c2_labels

    def test_baseline_cols_logged_as_not_charted(self, ig):
        """trx_baseline_avg, rev_baseline_avg, sr_baseline_avg must appear in a warning."""
        log_calls: list[tuple] = []
        ig.log = lambda msg, level="info": log_calls.append((level, msg))  # type: ignore[method-assign]

        ig._build_chart_configs(_state(_DETECT_DATA))

        warnings = [msg for lvl, msg in log_calls if lvl == "warning"]
        assert any(
            "trx_baseline_avg" in w and "not represented" in w
            for w in warnings
        ), f"Expected warning about baseline cols. Got warnings: {warnings}"

    def test_is_anomaly_bool_excluded_from_numeric(self, ig):
        """Boolean is_anomaly must never appear as a chart dataset."""
        configs = ig._build_chart_configs(_state(_DETECT_DATA))
        all_labels = [ds["label"] for cfg in configs for ds in cfg["datasets"]]
        assert "Is Anomaly" not in all_labels


# ── compare_periods schema (pct_change + raw period cols, no _target/_baseline) ──

_COMPARE_DATA = [
    {
        "entity": "qris", "trx_a": 14000, "trx_b": 12000, "trx_pct_change": 16.67,
        "rev_a": 15e9, "rev_b": 13e9, "rev_pct_change": 15.38,
        "sr_a": 99.5, "sr_b": 99.2, "sr_pct_change": 0.30,
    },
    {
        "entity": "gopay", "trx_a": 4000, "trx_b": 4500, "trx_pct_change": -11.11,
        "rev_a": 4e9, "rev_b": 4.5e9, "rev_pct_change": -11.11,
        "sr_a": 98.1, "sr_b": 98.5, "sr_pct_change": -0.40,
    },
    {
        "entity": "ovo", "trx_a": 2100, "trx_b": 2400, "trx_pct_change": -12.50,
        "rev_a": 2.1e9, "rev_b": 2.4e9, "rev_pct_change": -12.50,
        "sr_a": 97.3, "sr_b": 98.0, "sr_pct_change": -0.70,
    },
]


class TestComparePeriodsSuffixGrouping:
    """compare_periods: only pct_change chart (no _target/_baseline); raw period cols warned."""

    def test_exactly_one_chart_for_compare_periods(self, ig):
        configs = ig._build_chart_configs(_state(_COMPARE_DATA))
        assert len(configs) == 1, (
            f"compare_periods has no _target/_baseline cols → only 1 chart. Got {len(configs)}"
        )

    def test_pct_change_chart_has_all_three_metrics(self, ig):
        configs = ig._build_chart_configs(_state(_COMPARE_DATA))
        labels = [ds["label"] for ds in configs[0]["datasets"]]
        assert "Trx Pct Change" in labels
        assert "Rev Pct Change" in labels
        assert "Sr Pct Change"  in labels

    def test_raw_period_cols_logged_as_not_charted(self, ig):
        log_calls: list[tuple] = []
        ig.log = lambda msg, level="info": log_calls.append((level, msg))  # type: ignore[method-assign]

        ig._build_chart_configs(_state(_COMPARE_DATA))

        warnings = [msg for lvl, msg in log_calls if lvl == "warning"]
        assert any(
            "trx_a" in w and "not represented" in w
            for w in warnings
        ), f"Expected warning mentioning trx_a. Got: {warnings}"
        assert any("rev_a" in w for w in warnings), \
            "Warning must also mention rev_a (all raw period cols)"


# ── Fallback path: no suffix matches → original positional pairing ─────────

_TREND_DATA = [
    {"period": "2026-06-01", "total_trx": 410_000, "total_revenue": 18_000_000_000, "success_rate_pct": 99.1},
    {"period": "2026-06-15", "total_trx": 398_000, "total_revenue": 17_500_000_000, "success_rate_pct": 98.9},
    {"period": "2026-06-30", "total_trx": 422_000, "total_revenue": 18_700_000_000, "success_rate_pct": 99.3},
]

_PARTNER_DATA = [
    {"partner": "qris",  "total_trx": 14_000_000, "total_revenue": 635_000_000_000, "success_rate_pct": 99.6},
    {"partner": "dana",  "total_trx":  6_300_000, "total_revenue": 198_000_000_000, "success_rate_pct": 100.0},
    {"partner": "gopay", "total_trx":  4_100_000, "total_revenue": 142_000_000_000, "success_rate_pct": 98.8},
]


class TestPositionalFallback:
    """When no _pct_change/_target/_baseline_avg columns exist, use old positional pairing."""

    def test_trend_data_uses_positional_pairing(self, ig):
        configs = ig._build_chart_configs(_state(_TREND_DATA))
        assert configs[0]["title"] == "Total Trx & Total Revenue", (
            f"Expected positional pair chart title. Got: {configs[0]['title']}"
        )

    def test_partner_summary_preserves_dual_axis(self, ig):
        """Plain SQL with total_trx (14M) + total_revenue (635B) → dual_axis via magnitude gap."""
        configs = ig._build_chart_configs(_state(_PARTNER_DATA))
        assert configs[0].get("dual_axis") is True, (
            "total_revenue/total_trx ratio ~42,000× must trigger magnitude-gap dual_axis"
        )

    def test_trend_chart_type_is_line_for_time_dimension(self, ig):
        """'period' column → is_time=True → chart type must be line."""
        configs = ig._build_chart_configs(_state(_TREND_DATA))
        assert configs[0]["type"] == "line", (
            f"Time-dimension data must produce line chart. Got: {configs[0]['type']}"
        )
