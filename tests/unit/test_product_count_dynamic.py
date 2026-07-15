"""
Unit tests — dynamic product count propagation (FASE 1c).

Verifies that "882 distinct product_name" is not hardcoded in any prompt:
  1. get_product_count() returns the DB value via engine mock.
  2. _threshold_override_block() uses dynamic count, not hardcoded 882.
  3. _build_segment_guide() uses dynamic count for the "products" segment.
  4. Fallback: when product_count=0 (DB unreachable), both methods fall back to 882.
  5. Simulation: product_count=887 produces "887" in both prompt methods.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.insight_generator import InsightGenerator
from src.models.agent_state import AgentState
from src.utils.date_range import get_product_count

# ── get_product_count ─────────────────────────────────────────────────────────

class TestGetProductCount:
    def _mock_engine(self, count: int) -> MagicMock:
        row = MagicMock()
        row.__getitem__ = lambda self, i: count
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = row
        engine = MagicMock()
        engine.connect.return_value.__enter__ = lambda s: conn
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        return engine

    def test_returns_db_value(self):
        engine = self._mock_engine(882)
        assert get_product_count(engine) == 882

    def test_returns_new_count_887(self):
        engine = self._mock_engine(887)
        assert get_product_count(engine) == 887

    def test_returns_zero_on_exception(self):
        engine = MagicMock()
        engine.connect.side_effect = Exception("DB unreachable")
        assert get_product_count(engine) == 0

    def test_returns_zero_when_row_is_none(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        engine = MagicMock()
        engine.connect.return_value.__enter__ = lambda s: conn
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        assert get_product_count(engine) == 0


# ── _threshold_override_block ─────────────────────────────────────────────────

class TestThresholdOverrideBlock:
    def _make_generator(self) -> InsightGenerator:
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_uses_dynamic_count_887(self):
        gen = self._make_generator()
        result = gen._threshold_override_block("products", product_count=887)
        assert "887" in result
        assert "882" not in result

    def test_uses_dynamic_count_900(self):
        gen = self._make_generator()
        result = gen._threshold_override_block("products", product_count=900)
        assert "900" in result

    def test_fallback_to_882_when_count_is_zero(self):
        gen = self._make_generator()
        result = gen._threshold_override_block("products", product_count=0)
        assert "882" in result

    def test_empty_for_non_product_segment(self):
        gen = self._make_generator()
        assert gen._threshold_override_block("partners", product_count=887) == ""
        assert gen._threshold_override_block("channels", product_count=887) == ""

    def test_default_product_count_is_zero_fallback(self):
        gen = self._make_generator()
        # Called without explicit product_count → default=0 → fallback 882
        result = gen._threshold_override_block("products")
        assert "882" in result


# ── _build_segment_guide ──────────────────────────────────────────────────────

class TestBuildSegmentGuide:
    def _make_generator(self) -> InsightGenerator:
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_uses_dynamic_count_887_in_products_guide(self):
        gen = self._make_generator()
        result = gen._build_segment_guide("products", product_count=887)
        assert "887" in result
        assert "882" not in result

    def test_fallback_to_882_when_count_is_zero(self):
        gen = self._make_generator()
        result = gen._build_segment_guide("products", product_count=0)
        assert "882" in result

    def test_non_product_segment_unaffected(self):
        gen = self._make_generator()
        result = gen._build_segment_guide("partners", product_count=887)
        # partner guide should not contain "887" — it's unrelated
        assert "887" not in result

    def test_default_product_count_is_zero_fallback(self):
        gen = self._make_generator()
        result = gen._build_segment_guide("products")
        assert "882" in result


# ── AgentState field ──────────────────────────────────────────────────────────

class TestProductCountField:
    def test_default_is_zero(self):
        state = AgentState(query="test", database="financial_db")
        assert state.product_count == 0

    def test_can_set_887(self):
        state = AgentState(query="test", database="financial_db")
        state.product_count = 887
        assert state.product_count == 887


# ── Simulation: product_count=887 → prompts show "887" ───────────────────────

class TestProductCountSimulation887:
    """
    Simulates adding 5 dummy products (882 → 887).
    Confirms prompts auto-adjust without code changes.
    """

    def _make_generator(self) -> InsightGenerator:
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_threshold_override_shows_887(self):
        gen = self._make_generator()
        result = gen._threshold_override_block("products", product_count=887)
        assert "887 distinct product_name" in result

    def test_segment_guide_shows_887(self):
        gen = self._make_generator()
        result = gen._build_segment_guide("products", product_count=887)
        assert "887 distinct product_name" in result

    def test_threshold_override_no_hardcoded_882(self):
        gen = self._make_generator()
        result = gen._threshold_override_block("products", product_count=887)
        assert "882" not in result

    def test_segment_guide_no_hardcoded_882(self):
        gen = self._make_generator()
        result = gen._build_segment_guide("products", product_count=887)
        assert "882" not in result
