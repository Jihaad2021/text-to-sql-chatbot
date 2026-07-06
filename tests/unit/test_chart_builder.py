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
  5. get_distribution schema (_share_pct suffix group): share cols → chart 1
     (single-axis 0-100%), absolute cols → chart 2 (not dual-axis mixed).
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


# ── _build_grouped_bar_chart: compare_periods *_a/*_b pairs ──────────────────

_COMPARE_FULL_DATA = [
    {
        "entity": "qris", "trx_a": 14_000, "trx_b": 12_000, "trx_pct_change": 16.67,
        "rev_a": 15e9, "rev_b": 13e9, "rev_pct_change": 15.38,
        "sr_a": 99.5, "sr_b": 99.2, "sr_pct_change": 0.30,
    },
    {
        "entity": "gopay", "trx_a": 4_000, "trx_b": 4_500, "trx_pct_change": -11.11,
        "rev_a": 4e9, "rev_b": 4.5e9, "rev_pct_change": -11.11,
        "sr_a": 98.1, "sr_b": 98.5, "sr_pct_change": -0.40,
    },
    {
        "entity": "ovo", "trx_a": 2_100, "trx_b": 2_400, "trx_pct_change": -12.50,
        "rev_a": 2.1e9, "rev_b": 2.4e9, "rev_pct_change": -12.50,
        "sr_a": 97.3, "sr_b": 98.0, "sr_pct_change": -0.70,
    },
]


class TestGroupedBarChartBuilder:
    """_build_grouped_bar_chart: correct pair selection, dataset structure, logging."""

    def test_returns_dict_not_none(self, ig):
        """Must return a config, not None, for compare_periods data."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        assert cfg is not None, "Expected a chart config for compare_periods data"

    def test_chart_type_is_bar(self, ig):
        """grouped_bar_chart must use Chart.js type='bar' (grouped, not stacked)."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        assert cfg["type"] == "bar", f"Expected 'bar', got '{cfg['type']}'"

    def test_two_datasets_periode_a_and_b(self, ig):
        """Must produce exactly 2 datasets labelled 'Periode A' and 'Periode B'."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        labels = [ds["label"] for ds in cfg["datasets"]]
        assert labels == ["Periode A", "Periode B"], f"Got dataset labels: {labels}"

    def test_first_pair_by_column_order_is_trx(self, ig):
        """trx_a/trx_b appear first in column order → chart title must reference 'Trx'."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        assert "Trx" in cfg["title"], (
            f"Expected 'Trx' in title (first column-order pair). Got: '{cfg['title']}'"
        )

    def test_dataset_values_match_source_data(self, ig):
        """Periode A dataset must contain trx_a values in entity order."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        ds_a = next(ds for ds in cfg["datasets"] if ds["label"] == "Periode A")
        assert ds_a["data"] == [14_000.0, 4_000.0, 2_100.0], (
            f"Periode A values don't match trx_a column: {ds_a['data']}"
        )

    def test_labels_are_entity_names(self, ig):
        """X-axis labels must be entity names, not numeric indices."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        assert cfg["labels"] == ["qris", "gopay", "ovo"], (
            f"Expected entity names as labels. Got: {cfg['labels']}"
        )

    def test_additional_pairs_logged_as_warning(self, ig):
        """rev_a/rev_b and sr_a/sr_b beyond the first pair must be logged."""
        log_calls: list[tuple] = []
        ig.log = lambda msg, level="info": log_calls.append((level, msg))  # type: ignore[method-assign]
        ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        warnings = [msg for lvl, msg in log_calls if lvl == "warning"]
        assert any("rev_a" in w and "not represented" in w for w in warnings), (
            f"Expected warning about rev_a/rev_b not charted. Got: {warnings}"
        )

    def test_returns_none_for_no_ab_pairs(self, ig):
        """Data without *_a/*_b pairs must return None."""
        cfg = ig._build_grouped_bar_chart(_state(_DETECT_DATA))
        assert cfg is None, "detect_anomaly data has no _a/_b pairs — must return None"

    def test_returns_none_for_single_row(self, ig):
        """Single-row data must return None (nothing to group-compare)."""
        single = [_COMPARE_FULL_DATA[0]]
        cfg = ig._build_grouped_bar_chart(_state(single))
        assert cfg is None, "Single row must return None"

    def test_no_dual_axis(self, ig):
        """Grouped bar chart must NOT use dual axis (same metric, same scale)."""
        cfg = ig._build_grouped_bar_chart(_state(_COMPARE_FULL_DATA))
        assert cfg.get("dual_axis") is False, (
            f"grouped_bar_chart must have dual_axis=False. Got: {cfg.get('dual_axis')}"
        )


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


# ── _build_donut_chart: center-value (design ref 2f) ────────────────────────

_DONUT_SHARE_DATA = [
    {"partner": "qris",  "share_pct": 55.3},
    {"partner": "dana",  "share_pct": 24.1},
    {"partner": "gopay", "share_pct": 12.7},
    {"partner": "ovo",   "share_pct":  7.9},
]

_DONUT_RAW_TRX_DATA = [
    {"partner": "qris",  "total_trx": 14_000_000},
    {"partner": "dana",  "total_trx":  6_300_000},
    {"partner": "gopay", "total_trx":  4_100_000},
    {"partner": "ovo",   "total_trx":  2_400_000},
]

_DONUT_RAW_REV_DATA = [
    {"partner": "qris",  "total_revenue": 635_000_000_000},
    {"partner": "dana",  "total_revenue": 198_000_000_000},
    {"partner": "gopay", "total_revenue": 142_000_000_000},
]


class TestDonutCenterValue:
    """_build_donut_chart must populate center_value and center_label (design ref 2f)."""

    def test_share_pct_center_is_100_percent(self, ig):
        """share_pct columns always total 100% — center_value must be '100%'."""
        cfg = ig._build_donut_chart(_state(_DONUT_SHARE_DATA))
        assert cfg is not None
        assert cfg.get("center_value") == "100%", (
            f"share_pct donut must show '100%' center. Got: '{cfg.get('center_value')}'"
        )

    def test_share_pct_center_label_is_total(self, ig):
        cfg = ig._build_donut_chart(_state(_DONUT_SHARE_DATA))
        assert cfg.get("center_label") == "TOTAL", (
            f"Expected center_label='TOTAL'. Got: '{cfg.get('center_label')}'"
        )

    def test_raw_trx_center_is_sum_abbreviated(self, ig):
        """Raw absolute values: center_value = sum of all slices, abbreviated (e.g. '26.8M')."""
        cfg = ig._build_donut_chart(_state(_DONUT_RAW_TRX_DATA))
        assert cfg is not None
        cv = cfg.get("center_value", "")
        assert cv.endswith("M") or cv.endswith("jt") or cv.endswith("k") or cv.isdigit(), (
            f"Raw trx center_value should be abbreviated. Got: '{cv}'"
        )
        # total = 26_800_000 → "26.8M"
        assert "26" in cv or "27" in cv, (
            f"Sum of trx slices is 26.8M — expected '26' or '27' in center. Got: '{cv}'"
        )

    def test_raw_revenue_gets_rp_prefix(self, ig):
        """Revenue column name triggers 'Rp' prefix on center_value."""
        cfg = ig._build_donut_chart(_state(_DONUT_RAW_REV_DATA))
        assert cfg is not None
        cv = cfg.get("center_value", "")
        assert cv.startswith("Rp"), (
            f"Revenue column must produce Rp-prefixed center_value. Got: '{cv}'"
        )

    def test_raw_trx_no_rp_prefix(self, ig):
        """Non-revenue column (total_trx) must NOT have Rp prefix."""
        cfg = ig._build_donut_chart(_state(_DONUT_RAW_TRX_DATA))
        cv = cfg.get("center_value", "")
        assert not cv.startswith("Rp"), (
            f"trx column must NOT have Rp prefix. Got: '{cv}'"
        )

    def test_center_value_present_on_share_donut(self, ig):
        """center_value key must exist in returned dict (not missing/None)."""
        cfg = ig._build_donut_chart(_state(_DONUT_SHARE_DATA))
        assert "center_value" in cfg
        assert cfg["center_value"] is not None

    def test_center_label_always_present(self, ig):
        """center_label must be set regardless of column type."""
        for data in (_DONUT_SHARE_DATA, _DONUT_RAW_TRX_DATA):
            cfg = ig._build_donut_chart(_state(data))
            assert cfg.get("center_label") == "TOTAL", (
                f"center_label must always be 'TOTAL'. Got: '{cfg.get('center_label')}'"
            )


# ── _share_pct suffix grouping (Fix A) — get_distribution schema ─────────────

_DISTRIBUTION_DATA = [
    {
        "entity": "qris",  "total_trx": 14_843_101, "trx_share_pct": 53.43,
        "total_revenue": 634_960_372_700.0, "rev_share_pct": 53.63,
    },
    {
        "entity": "dana",  "total_trx":  6_322_881, "trx_share_pct": 22.76,
        "total_revenue": 198_380_152_802.0, "rev_share_pct": 16.75,
    },
    {
        "entity": "finnet", "total_trx": 2_454_675, "trx_share_pct":  8.84,
        "total_revenue": 180_632_792_740.0, "rev_share_pct": 15.26,
    },
    {
        "entity": "gopay", "total_trx":  1_848_321, "trx_share_pct":  6.65,
        "total_revenue":  72_541_284_600.0, "rev_share_pct":  6.13,
    },
    {
        "entity": "shopeepay", "total_trx": 1_588_492, "trx_share_pct": 5.72,
        "total_revenue":  41_920_800_000.0, "rev_share_pct":  3.54,
    },
    {
        "entity": "ovo",   "total_trx":  427_080, "trx_share_pct":  1.54,
        "total_revenue":  14_108_640_000.0, "rev_share_pct":  1.19,
    },
    {
        "entity": "linkaja", "total_trx": 323_190, "trx_share_pct": 1.16,
        "total_revenue":  10_665_270_000.0, "rev_share_pct":  0.90,
    },
    {
        "entity": "telkomsel_wallet", "total_trx": 11_630, "trx_share_pct": 0.04,
        "total_revenue":     386_600_000.0, "rev_share_pct":  0.03,
    },
    {
        "entity": "indomaret", "total_trx": 9_820, "trx_share_pct": 0.04,
        "total_revenue":     264_540_000.0, "rev_share_pct":  0.02,
    },
]


class TestSharePctSuffixGrouping:
    """get_distribution schema: *_share_pct cols → chart 1 (single-axis 0-100%),
    absolute cols → chart 2 (separate chart, not dual-axis campur)."""

    def test_two_chart_configs_produced(self, ig):
        """Must produce exactly 2 chart configs: one share, one absolute."""
        configs = ig._build_chart_configs(_state(_DISTRIBUTION_DATA))
        assert len(configs) == 2, (
            f"Expected 2 chart configs (share + absolute). Got {len(configs)}"
        )

    def test_first_chart_contains_only_share_pct_cols(self, ig):
        """Chart 1 datasets must be trx_share_pct and rev_share_pct — no absolute cols."""
        configs = ig._build_chart_configs(_state(_DISTRIBUTION_DATA))
        labels_c1 = [ds["label"] for ds in configs[0]["datasets"]]
        assert "Trx Share Pct" in labels_c1, f"Expected Trx Share Pct in chart 1. Got: {labels_c1}"
        assert "Rev Share Pct" in labels_c1, f"Expected Rev Share Pct in chart 1. Got: {labels_c1}"
        assert "Total Trx"     not in labels_c1, f"Absolute col must NOT be in share chart: {labels_c1}"
        assert "Total Revenue"  not in labels_c1, f"Absolute col must NOT be in share chart: {labels_c1}"

    def test_first_chart_has_no_dual_axis(self, ig):
        """Share_pct columns share the same 0-100% scale — dual_axis must be False."""
        configs = ig._build_chart_configs(_state(_DISTRIBUTION_DATA))
        assert configs[0].get("dual_axis") is False, (
            f"Share_pct chart must have dual_axis=False (same 0-100% scale). "
            f"Got: {configs[0].get('dual_axis')}"
        )

    def test_second_chart_contains_only_absolute_cols(self, ig):
        """Chart 2 datasets must be total_trx and total_revenue — no share_pct cols."""
        configs = ig._build_chart_configs(_state(_DISTRIBUTION_DATA))
        labels_c2 = [ds["label"] for ds in configs[1]["datasets"]]
        assert "Total Trx"     in labels_c2, f"Expected Total Trx in chart 2. Got: {labels_c2}"
        assert "Total Revenue"  in labels_c2, f"Expected Total Revenue in chart 2. Got: {labels_c2}"
        assert "Trx Share Pct" not in labels_c2, f"Share col must NOT be in absolute chart: {labels_c2}"
        assert "Rev Share Pct" not in labels_c2, f"Share col must NOT be in absolute chart: {labels_c2}"

    def test_share_pct_values_are_percentage_scale(self, ig):
        """Share_pct chart values must be in 0-100 range (not millions/billions)."""
        configs = ig._build_chart_configs(_state(_DISTRIBUTION_DATA))
        for ds in configs[0]["datasets"]:
            max_val = max(abs(v or 0) for v in ds["data"])
            assert max_val <= 100, (
                f"Share chart dataset '{ds['label']}' has value {max_val} > 100 — "
                f"must be percentage scale"
            )

    def test_detect_anomaly_unaffected_by_share_pct_fix(self, ig):
        """detect_anomaly schema has no *_share_pct — pct_change must still be chart 1."""
        configs = ig._build_chart_configs(_state(_DETECT_DATA))
        labels_c1 = [ds["label"] for ds in configs[0]["datasets"]]
        assert "Trx Pct Change" in labels_c1, (
            f"detect_anomaly: pct_change must still be chart 1. Got: {labels_c1}"
        )

    def test_compare_periods_unaffected_by_share_pct_fix(self, ig):
        """compare_periods schema has no *_share_pct — pct_change must still be chart 1."""
        configs = ig._build_chart_configs(_state(_COMPARE_DATA))
        labels_c1 = [ds["label"] for ds in configs[0]["datasets"]]
        assert "Trx Pct Change" in labels_c1, (
            f"compare_periods: pct_change must still be chart 1. Got: {labels_c1}"
        )
