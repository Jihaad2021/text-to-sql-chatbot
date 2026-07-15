"""
Unit tests for COALESCE NULL normalization in compare_periods and detect_anomaly.

Covers:
  1. compare_periods(product) emits COALESCE expression in CTEs
  2. compare_periods(partner) does NOT emit COALESCE
  3. compare_periods(channel) does NOT emit COALESCE
  4. detect_anomaly(product) emits COALESCE expression in both target and baseline CTEs
  5. detect_anomaly(partner) does NOT emit COALESCE
  6. detect_anomaly(channel) does NOT emit COALESCE
"""

from unittest.mock import MagicMock, patch

import pytest

from src.tools.analytics_tools import compare_periods, detect_anomaly

_COALESCE_EXPR = "coalesce(nullif(nullif(product_name, 'null'), ''), '[tidak teridentifikasi]')"


def _make_engine(rows: list | None = None) -> MagicMock:
    """Return a mock DB engine that returns the given rows."""
    rows = rows or []
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter(rows))
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    engine = MagicMock()
    engine.connect.return_value = mock_conn
    return engine


def _captured_sql(fn, *args, **kwargs) -> str:
    """Run fn with a mock engine, return the SQL string that was executed."""
    sqls: list[str] = []

    def _capture_run(engine, sql, desc, **kw):
        sqls.append(sql)
        return {"data": [], "row_count": 0, "sql": sql, "description": desc}

    with patch("src.tools.analytics_tools._run", side_effect=_capture_run):
        fn(_make_engine(), *args, **kwargs)

    return " ".join(sqls).lower()


# ── compare_periods ────────────────────────────────────────────────────────────

class TestComparePeriodsCOALESCE:

    def test_product_uses_coalesce_in_period_a(self):
        sql = _captured_sql(
            compare_periods,
            "2026-05-01", "2026-05-31",
            "2026-06-01", "2026-06-30",
            dimension="product",
        )
        assert "coalesce" in sql, "compare_periods(product) must use COALESCE for entity"
        assert "nullif" in sql
        assert "tidak teridentifikasi" in sql

    def test_product_coalesce_appears_in_both_ctes(self):
        sql = _captured_sql(
            compare_periods,
            "2026-05-01", "2026-05-31",
            "2026-06-01", "2026-06-30",
            dimension="product",
        )
        # COALESCE must appear in period_a AND period_b CTEs (= at least 2 occurrences)
        assert sql.count("coalesce(nullif(nullif(product_name") >= 2

    def test_partner_no_coalesce(self):
        sql = _captured_sql(
            compare_periods,
            "2026-05-01", "2026-05-31",
            "2026-06-01", "2026-06-30",
            dimension="partner",
        )
        assert "coalesce(nullif(nullif" not in sql, "partner must NOT use product COALESCE"

    def test_channel_no_coalesce(self):
        sql = _captured_sql(
            compare_periods,
            "2026-05-01", "2026-05-31",
            "2026-06-01", "2026-06-30",
            dimension="channel",
        )
        assert "coalesce(nullif(nullif" not in sql, "channel must NOT use product COALESCE"


# ── detect_anomaly ─────────────────────────────────────────────────────────────

class TestDetectAnomalyCOALESCE:

    def test_product_uses_coalesce_in_target(self):
        sql = _captured_sql(
            detect_anomaly,
            "2026-06-30",
            dimension="product",
        )
        assert "coalesce" in sql, "detect_anomaly(product) must use COALESCE in target CTE"
        assert "tidak teridentifikasi" in sql

    def test_product_coalesce_in_baseline_inner(self):
        sql = _captured_sql(
            detect_anomaly,
            "2026-06-30",
            dimension="product",
        )
        # COALESCE must appear at least twice (target CTE + baseline inner subquery)
        assert sql.count("coalesce(nullif(nullif(product_name") >= 2

    def test_partner_no_coalesce(self):
        sql = _captured_sql(
            detect_anomaly,
            "2026-06-30",
            dimension="partner",
        )
        assert "coalesce(nullif(nullif" not in sql, "partner must NOT use product COALESCE"

    def test_channel_no_coalesce(self):
        sql = _captured_sql(
            detect_anomaly,
            "2026-06-30",
            dimension="channel",
        )
        assert "coalesce(nullif(nullif" not in sql, "channel must NOT use product COALESCE"

    def test_baseline_outer_groups_by_entity_not_raw_column(self):
        """Outer baseline CTE must GROUP BY entity (alias), not raw product_name column."""
        sql = _captured_sql(
            detect_anomaly,
            "2026-06-30",
            dimension="product",
        )
        # The outer baseline should reference 'entity' after the inner aliases it,
        # not repeat the full COALESCE expression again at the outer GROUP BY level.
        # We verify by checking 'group by entity' appears (from the outer baseline).
        assert "group by entity" in sql
