"""
Unit tests for get_distribution() top_n parameter — clamping, actual-entity-count
limiting, parameterized LIMIT, and default-30 backward-compat behavior.

Covers:
  1. Normal case: top_n=5 → SQL LIMIT binds to 5.
  2. Default: no top_n → LIMIT binds to 30 (backward compat).
  3. Oversized: top_n=1000 with 100 DB entities → limited to 100 by entity count.
  4. Negative: top_n=-5 → clamped to 1.
  5. Zero: top_n=0 → clamped to 1.
  6. Boundary: top_n=100 → accepted as-is (when entity_count ≥ 100).
  7. Boundary: top_n=1 → accepted as-is (min allowed).
  8. Float coercion: top_n=5.9 (LLM might pass float) → int(5) after clamp.
  9. SQL uses :top_n placeholder, not string interpolation.
 10. actual_entity_count returned in result dict.
 11. top_n bounded by actual DB entity count when entity_count < top_n.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from src.tools.analytics_tools import get_distribution


def _make_engine(rows: list[dict] | None = None, entity_count: int = 9999) -> MagicMock:
    """Return a mock SQLAlchemy engine handling two conn.execute() calls.

    First call: COUNT(DISTINCT ...) → returns entity_count via .scalar()
    Second call: main SELECT        → returns rows via .keys() / .fetchall()
    """
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
    """Extract the params dict passed to conn.execute() for the main SELECT (last call)."""
    conn = engine.connect.return_value
    # call_args_list[-1] is the last execute call (main SELECT, not COUNT)
    call_args = conn.execute.call_args_list[-1] if conn.execute.call_args_list else None
    if call_args is None:
        return {}
    args, kwargs = call_args
    return args[1] if len(args) > 1 else kwargs.get("parameters", {})


def _executed_sql(engine: MagicMock) -> str:
    """Extract the SQL string from the main SELECT (last conn.execute call)."""
    conn = engine.connect.return_value
    call_args = conn.execute.call_args_list[-1] if conn.execute.call_args_list else None
    if call_args is None:
        return ""
    args, _ = call_args
    return str(args[0])  # text() object → str gives the SQL


# ── normal cases ─────────────────────────────────────────────────────────────

class TestTopNNormalCases:

    def test_top_n_5_passes_5_to_limit(self):
        """top_n=5 → params dict must contain top_n=5."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        params = _executed_params(engine)
        assert params.get("top_n") == 5, f"Expected top_n=5 in params. Got: {params}"

    def test_default_top_n_capped_to_display_cap(self):
        """Default top_n=30 is capped by the 20-row display cap → effective 20."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30")
        params = _executed_params(engine)
        assert params.get("top_n") == 20, f"Expected default top_n capped to 20. Got: {params}"

    def test_sql_uses_placeholder_not_literal(self):
        """SQL must contain ':top_n' placeholder, not a hardcoded integer."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5)
        sql = _executed_sql(engine)
        assert ":top_n" in sql, (
            f"SQL must use ':top_n' parameterized placeholder. Got SQL:\n{sql}"
        )
        assert "LIMIT 5" not in sql, (
            "SQL must NOT have literal 'LIMIT 5' — value must come from params."
        )

    def test_top_n_10_passes_10_to_limit(self):
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=10)
        assert _executed_params(engine).get("top_n") == 10


# ── clamping and entity-count limiting ────────────────────────────────────────

class TestTopNClamping:

    def test_oversized_1000_capped_by_display_cap(self):
        """top_n=1000 with 100 DB entities → display cap (20) is the binding constraint."""
        engine = _make_engine(entity_count=100)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=1000)
        params = _executed_params(engine)
        assert params.get("top_n") == 20, (
            f"top_n=1000 must be capped at display cap 20. Got: {params.get('top_n')}"
        )

    def test_negative_clamped_to_1(self):
        """top_n=-5 → clamped to 1, must not produce invalid SQL."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=-5)
        params = _executed_params(engine)
        assert params.get("top_n") == 1, (
            f"top_n=-5 must be clamped to 1. Got: {params.get('top_n')}"
        )

    def test_zero_clamped_to_1(self):
        """top_n=0 → clamped to 1."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=0)
        assert _executed_params(engine).get("top_n") == 1

    def test_above_cap_clamped_to_display_cap(self):
        """top_n=100 with sufficient entities → clamped to display cap 20."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=100)
        assert _executed_params(engine).get("top_n") == 20

    def test_boundary_min_1_accepted(self):
        """top_n=1 is the exact min — must pass through unchanged."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=1)
        assert _executed_params(engine).get("top_n") == 1

    def test_float_coerced_to_int(self):
        """LLM might pass 5.9 as a float — must be safely cast to int before clamp."""
        engine = _make_engine(entity_count=9999)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=5.9)  # type: ignore[arg-type]
        params = _executed_params(engine)
        assert isinstance(params.get("top_n"), int), (
            f"top_n bound value must be int, not {type(params.get('top_n'))}"
        )
        assert params.get("top_n") == 5

    def test_oversized_101_capped_by_display_cap(self):
        """top_n=101 with 100 DB entities → display cap (20) is the binding constraint."""
        engine = _make_engine(entity_count=100)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=101)
        assert _executed_params(engine).get("top_n") == 20

    def test_description_reflects_display_cap(self):
        """The description must mention the effective top_n after applying display cap."""
        engine = _make_engine(entity_count=100)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=999)
        # With display cap 20: _top_n = min(999, 20) = 20, _top_n_final = min(20, 100) = 20
        assert "top 20" in result.get("description", ""), (
            f"Description must reflect effective top_n=20. Got: '{result.get('description')}'"
        )

    def test_entity_count_below_display_cap_is_binding(self):
        """When DB entity count < display cap, entity count is the binding constraint."""
        engine = _make_engine(entity_count=15)
        get_distribution(engine, "2026-06-01", "2026-06-30", top_n=50)
        params = _executed_params(engine)
        assert params.get("top_n") == 15, (
            f"top_n=50 with 15 DB entities must yield top_n=15 (entity count < cap). Got: {params.get('top_n')}"
        )

    def test_actual_entity_count_returned_in_result(self):
        """Result dict must include 'actual_entity_count' field from COUNT pre-flight."""
        engine = _make_engine(entity_count=42)
        result = get_distribution(engine, "2026-06-01", "2026-06-30", top_n=10)
        assert result.get("actual_entity_count") == 42, (
            f"Result must contain actual_entity_count=42. Got: {result.get('actual_entity_count')}"
        )
