"""
Unit tests for get_distribution() cumulative share computation and 20-row display cap.

Covers:
  1. cumulative_trx_share_pct = sum of trx_share_pct from returned rows
  2. cumulative_rev_share_pct = sum of rev_share_pct from returned rows
  3. Both are 0.0 when result has no rows
  4. dimension stored in result
  5. Display cap 20 applied: top_n=1000 → params["top_n"] == 20
  6. User request below cap preserved: top_n=5 → params["top_n"] == 5
  7. Entity count below cap is binding: entity_count=7 → params["top_n"] == 7
"""

from unittest.mock import MagicMock

import pytest

from src.tools.analytics_tools import get_distribution


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_engine(rows: list[dict] | None = None, entity_count: int = 9999) -> MagicMock:
    rows = rows or []

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = entity_count

    mock_main_result = MagicMock()
    mock_main_result.keys.return_value = list(rows[0].keys()) if rows else []
    mock_main_result.fetchall.return_value = [tuple(r.values()) for r in rows]

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = [mock_count_result, mock_main_result]
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = MagicMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn
    return mock_engine


def _executed_params(engine: MagicMock) -> dict:
    conn = engine.connect.return_value
    call_args = conn.execute.call_args_list[-1] if conn.execute.call_args_list else None
    if call_args is None:
        return {}
    args, kwargs = call_args
    return args[1] if len(args) > 1 else kwargs.get("parameters", {})


_SAMPLE_ROWS = [
    {"entity": "qris",      "total_trx": 14843101, "trx_share_pct": 53.43, "total_revenue": 634960372700.0, "rev_share_pct": 53.63},
    {"entity": "dana",      "total_trx":  6321802, "trx_share_pct": 22.76, "total_revenue": 198380152802.0, "rev_share_pct": 16.75},
    {"entity": "finnet",    "total_trx":  2457193, "trx_share_pct":  8.84, "total_revenue": 180632792740.0, "rev_share_pct": 15.26},
    {"entity": "shopeepay", "total_trx":  1893211, "trx_share_pct":  6.81, "total_revenue":  75070943919.0, "rev_share_pct":  6.34},
    {"entity": "gopay",     "total_trx":  1542007, "trx_share_pct":  5.55, "total_revenue":  66480898375.0, "rev_share_pct":  5.61},
]


# ── cumulative share computation ──────────────────────────────────────────────

class TestCumulativeShare:

    def test_cumulative_trx_share_is_sum_of_rows(self):
        """cumulative_trx_share_pct must equal the exact sum of trx_share_pct from returned rows."""
        engine = _make_engine(rows=_SAMPLE_ROWS, entity_count=9)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        expected = round(sum(r["trx_share_pct"] for r in _SAMPLE_ROWS), 2)
        assert result["cumulative_trx_share_pct"] == expected, (
            f"cumulative_trx_share_pct mismatch. Expected {expected}, got {result['cumulative_trx_share_pct']}"
        )

    def test_cumulative_rev_share_is_sum_of_rows(self):
        """cumulative_rev_share_pct must equal the exact sum of rev_share_pct from returned rows."""
        engine = _make_engine(rows=_SAMPLE_ROWS, entity_count=9)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        expected = round(sum(r["rev_share_pct"] for r in _SAMPLE_ROWS), 2)
        assert result["cumulative_rev_share_pct"] == expected, (
            f"cumulative_rev_share_pct mismatch. Expected {expected}, got {result['cumulative_rev_share_pct']}"
        )

    def test_cumulative_share_known_values(self):
        """Assert exact cumulative totals for the 5-row sample (hand-verifiable)."""
        engine = _make_engine(rows=_SAMPLE_ROWS, entity_count=9)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        # 53.43 + 22.76 + 8.84 + 6.81 + 5.55 = 97.39
        assert result["cumulative_trx_share_pct"] == 97.39, (
            f"Expected 97.39, got {result['cumulative_trx_share_pct']}"
        )
        # 53.63 + 16.75 + 15.26 + 6.34 + 5.61 = 97.59
        assert result["cumulative_rev_share_pct"] == 97.59, (
            f"Expected 97.59, got {result['cumulative_rev_share_pct']}"
        )

    def test_cumulative_share_zero_when_no_rows(self):
        """Empty result → cumulative shares are 0.0, not None or error."""
        engine = _make_engine(rows=[], entity_count=9)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        assert result["cumulative_trx_share_pct"] == 0.0
        assert result["cumulative_rev_share_pct"] == 0.0

    def test_cumulative_share_single_row(self):
        """Single-row result → cumulative == that row's share values."""
        row = [{"entity": "qris", "total_trx": 100, "trx_share_pct": 100.0,
                "total_revenue": 1000.0, "rev_share_pct": 100.0}]
        engine = _make_engine(rows=row, entity_count=1)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=1)
        assert result["cumulative_trx_share_pct"] == 100.0
        assert result["cumulative_rev_share_pct"] == 100.0


# ── dimension stored in result ────────────────────────────────────────────────

class TestDimensionInResult:

    def test_dimension_partner_stored(self):
        engine = _make_engine(entity_count=9)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", dimension="partner")
        assert result["dimension"] == "partner"

    def test_dimension_product_stored(self):
        engine = _make_engine(entity_count=100)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", dimension="product")
        assert result["dimension"] == "product"

    def test_dimension_channel_stored(self):
        engine = _make_engine(entity_count=20)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", dimension="channel")
        assert result["dimension"] == "channel"


# ── display cap = 20 ──────────────────────────────────────────────────────────

class TestDisplayCap:

    def test_cap_20_applied_to_large_top_n(self):
        """top_n=1000 with ample DB entities → capped at 20."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=1000)
        assert _executed_params(engine).get("top_n") == 20

    def test_user_request_below_cap_preserved(self):
        """top_n=5 → exactly 5, not forced up to 20."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        assert _executed_params(engine).get("top_n") == 5

    def test_entity_count_below_cap_is_binding(self):
        """entity_count=7 → top_n_final=7 even though cap is 20."""
        engine = _make_engine(entity_count=7)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=1000)
        assert _executed_params(engine).get("top_n") == 7

    def test_top_n_exactly_at_cap_preserved(self):
        """top_n=20 with ample entities → exactly 20."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=20)
        assert _executed_params(engine).get("top_n") == 20

    def test_top_n_21_clamped_to_20(self):
        """top_n=21 (just above cap) → clamped to 20."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=21)
        assert _executed_params(engine).get("top_n") == 20


# ── COALESCE NULL normalization (product dimension only) ──────────────────────

class TestNullNormalization:
    """
    Tests that SQL NULL, string 'NULL', and empty string are merged into one
    '[Tidak Teridentifikasi]' group when dimension='product'.

    Uses a two-call mock (COUNT + SELECT) like _make_engine, but passes data rows
    with NULL and 'NULL' entity values so we can assert they're merged.

    NOTE: The mock only controls what the DB *returns* — the COALESCE logic lives
    in the SQL text sent TO the DB.  We verify correctness by checking:
      1. The SQL text contains the COALESCE expression for product dimension.
      2. The SQL text does NOT contain the COALESCE expression for other dimensions.
      3. cumulative_share is correctly summed from whatever rows the mock returns
         (mirrors the real DB behaviour where both rows collapse to one).
    """

    def _make_engine_two_call(self, count_val: int, rows: list[dict]) -> MagicMock:
        mock_count = MagicMock()
        mock_count.scalar.return_value = count_val
        mock_main = MagicMock()
        mock_main.keys.return_value = list(rows[0].keys()) if rows else []
        mock_main.fetchall.return_value = [tuple(r.values()) for r in rows]
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = [mock_count, mock_main]
        mock_conn.__enter__ = lambda self: self
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        return mock_engine

    def _get_sql_sent(self, engine: MagicMock) -> str:
        """Return the SQL string from the last (main SELECT) execute call."""
        conn = engine.connect.return_value
        calls = conn.execute.call_args_list
        args, _ = calls[-1]
        return str(args[0]).lower()

    def _get_count_sql(self, engine: MagicMock) -> str:
        """Return the SQL string from the first (COUNT) execute call."""
        conn = engine.connect.return_value
        calls = conn.execute.call_args_list
        args, _ = calls[0]
        return str(args[0]).lower()

    # ── product dimension uses COALESCE ──────────────────────────────────────

    def test_product_sql_contains_coalesce(self):
        """product dimension must emit COALESCE normalization in SELECT and GROUP BY."""
        rows = [{"entity": "[Tidak Teridentifikasi]", "total_trx": 2831491,
                 "trx_share_pct": 10.19, "total_revenue": 1.0, "rev_share_pct": 5.0}]
        engine = self._make_engine_two_call(100, rows)
        get_distribution(engine, "2026-06-01", "2026-06-30", dimension="product", top_n=5)
        sql = self._get_sql_sent(engine)
        assert "coalesce" in sql, "product SELECT must use COALESCE normalization"
        assert "tidak teridentifikasi" in sql, "product SELECT must include the fallback label"

    def test_product_count_sql_contains_coalesce(self):
        """pre-flight COUNT for product must also use COALESCE to count merged entities."""
        rows = [{"entity": "x", "total_trx": 1, "trx_share_pct": 100.0,
                 "total_revenue": 1.0, "rev_share_pct": 100.0}]
        engine = self._make_engine_two_call(1, rows)
        get_distribution(engine, "2026-06-01", "2026-06-30", dimension="product", top_n=5)
        count_sql = self._get_count_sql(engine)
        assert "coalesce" in count_sql, "COUNT pre-flight must use COALESCE for product"

    # ── other dimensions do NOT use COALESCE ─────────────────────────────────

    def test_partner_sql_no_coalesce(self):
        """partner dimension must NOT emit COALESCE — partner_group has no NULL variants."""
        rows = [{"entity": "qris", "total_trx": 100, "trx_share_pct": 100.0,
                 "total_revenue": 1.0, "rev_share_pct": 100.0}]
        engine = self._make_engine_two_call(9, rows)
        get_distribution(engine, "2026-06-01", "2026-06-30", dimension="partner", top_n=5)
        sql = self._get_sql_sent(engine)
        assert "coalesce" not in sql, "partner SELECT must NOT use COALESCE"

    def test_channel_sql_no_coalesce(self):
        """channel dimension must NOT emit COALESCE — channel has no NULL variants."""
        rows = [{"entity": "gopay", "total_trx": 100, "trx_share_pct": 100.0,
                 "total_revenue": 1.0, "rev_share_pct": 100.0}]
        engine = self._make_engine_two_call(5, rows)
        get_distribution(engine, "2026-06-01", "2026-06-30", dimension="channel", top_n=5)
        sql = self._get_sql_sent(engine)
        assert "coalesce" not in sql, "channel SELECT must NOT use COALESCE"

    # ── cumulative share still sums correctly after merge ────────────────────

    def test_cumulative_share_after_null_merge(self):
        """After NULL merge, cumulative_share = sum of all returned rows (including merged row)."""
        # Simulate DB returning one merged '[Tidak Teridentifikasi]' row whose
        # share = null_sql_share + null_string_share (6.41 + 3.79 = 10.20)
        rows = [
            {"entity": "Super Seru", "total_trx": 5000000, "trx_share_pct": 55.0,
             "total_revenue": 1e9, "rev_share_pct": 50.0},
            {"entity": "[Tidak Teridentifikasi]", "total_trx": 2831491, "trx_share_pct": 10.20,
             "total_revenue": 1e8, "rev_share_pct": 8.0},
            {"entity": "Produk Lain", "total_trx": 500000, "trx_share_pct": 5.5,
             "total_revenue": 5e7, "rev_share_pct": 4.0},
        ]
        engine = self._make_engine_two_call(100, rows)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", dimension="product", top_n=5)
        expected_trx = round(55.0 + 10.20 + 5.5, 2)
        expected_rev = round(50.0 + 8.0 + 4.0, 2)
        assert result["cumulative_trx_share_pct"] == expected_trx
        assert result["cumulative_rev_share_pct"] == expected_rev
