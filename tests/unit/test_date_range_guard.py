"""
Date-range guard — unit tests.

Regression guard for false-KRITIS verdicts caused by out-of-range date periods.
Root cause: QueryRewriter used date.today() without checking MAX(date) from DB,
so "bulan ini" on 2026-07-03 resolved to 2026-07-01..2026-07-31 when data only
goes to 2026-06-30. InsightGenerator then received all-NULL SUM() rows and
produced a spurious KRITIS verdict.

Two test cases:
  TC1 — out-of-range period  → InsightGenerator LLM skipped, template returned
  TC2 — valid period, empty data → InsightGenerator LLM called normally
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.agents.insight_generator import InsightGenerator
from src.models.agent_state import AgentState

# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def generator():
    """InsightGenerator with mocked LLM so no real API calls are made."""
    with patch.object(InsightGenerator, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        ig = InsightGenerator()
    return ig


# ── TC1: out-of-range → skip LLM, return template message ────────────────

class TestOutOfRangeGuard:
    """
    When state.query_out_of_range=True, InsightGenerator must NOT call the LLM
    and must return a deterministic message mentioning the latest available date.
    """

    def test_skips_llm_when_out_of_range(self, generator):
        """LLM must not be called when query_out_of_range=True."""
        state = AgentState(
            query="bagaimana performa transaksi bulan ini?",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=True,
            out_of_range_latest="2026-06-30",
        )

        with patch.object(generator, "_call_llm") as mock_llm:
            result = generator.run(state)

        mock_llm.assert_not_called()
        assert result.insights is not None
        assert "2026-06-30" not in result.insights or "30 Juni 2026" in result.insights, (
            "Message should use Indonesian date format"
        )
        assert "30 Juni 2026" in result.insights, (
            "Template message must include the latest available date in Indonesian format"
        )
        assert "Belum ada data" in result.insights, (
            "Template message must state that no data is available for the requested period"
        )

    def test_template_contains_no_verdict(self, generator):
        """The out-of-range message must NOT contain a KRITIS/WARNING verdict."""
        state = AgentState(
            query="bagaimana performa transaksi bulan ini?",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=True,
            out_of_range_latest="2026-06-30",
        )

        with patch.object(generator, "_call_llm"):
            result = generator.run(state)

        assert "KRITIS" not in (result.insights or ""), (
            "Out-of-range message must not contain KRITIS verdict"
        )
        assert "WARNING" not in (result.insights or ""), (
            "Out-of-range message must not contain WARNING verdict"
        )


# ── TC2: valid period, genuinely empty data → LLM called normally ─────────

class TestValidPeriodEmptyData:
    """
    When state.query_out_of_range=False (period is within available range),
    even if query_result is empty, InsightGenerator must call the LLM normally
    so it can produce a verdict based on real (empty) data.
    """

    def test_llm_called_for_valid_period_empty_data(self, generator):
        """LLM must be invoked for a valid period even when row_count=0."""
        state = AgentState(
            query="bagaimana performa GoPay bulan Juni 2026?",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=False,
            out_of_range_latest=None,
            query_result=[],
            row_count=0,
            validated_sql="SELECT ... WHERE ...",
            intent={"category": "trend_analysis"},
        )

        llm_reply = "Tidak ada data transaksi GoPay yang ditemukan untuk periode Juni 2026."

        with patch.object(generator, "_call_llm", return_value=llm_reply) as mock_llm:
            result = generator.run(state)

        mock_llm.assert_called_once()
        assert result.insights == llm_reply

    def test_null_row_treated_as_empty(self, generator):
        """
        A single-row result with all-NULL values (PostgreSQL SUM() on empty set)
        should still allow the LLM to run — the null-row guard in analytics_tools._run()
        normalises it to [] before it reaches InsightGenerator.

        This test verifies that InsightGenerator itself does not mistakenly treat
        a non-empty result as out-of-range.
        """
        state = AgentState(
            query="bagaimana performa GoPay bulan Juni 2026?",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=False,   # QueryRewriter explicitly set to False
            out_of_range_latest=None,
            query_result=[],            # already normalised by analytics_tools._run()
            row_count=0,
            validated_sql="SELECT SUM(...) FROM ...",
            intent={"category": "trend_analysis"},
        )

        llm_reply = "Tidak ada data GoPay untuk Juni 2026."

        with patch.object(generator, "_call_llm", return_value=llm_reply) as mock_llm:
            result = generator.run(state)

        mock_llm.assert_called_once()
        assert "KRITIS" not in (result.insights or ""), (
            "Genuinely empty result must not produce a spurious KRITIS verdict"
        )


# ── TC3: defense-in-depth — guard clears query_result and row_count ────────

class TestOutOfRangeGuardClearsData:
    """
    Layer 2 defense: InsightGenerator guard must clear state.query_result and
    state.row_count to [] / 0 before returning, even if AnalyticsAgent already
    wrote data to state. This prevents _buildFlatBody from rendering a data
    table alongside the guard message (hasData=False after clear).
    """

    def test_query_result_cleared_when_out_of_range(self, generator):
        """state.query_result must be [] after guard fires, even if pre-populated."""
        state = AgentState(
            query="distribusi share produk bulan ini",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=True,
            out_of_range_latest="2026-06-30",
            query_result=[
                {"entity": "Super Seru Internet", "trx_share_pct": "23.59"},
                {"entity": "Super Seru", "trx_share_pct": "19.41"},
            ],
            row_count=2,
        )

        with patch.object(generator, "_call_llm"):
            result = generator.run(state)

        assert result.query_result == [], (
            "Guard must clear query_result so the UI does not render a data table"
        )

    def test_row_count_cleared_when_out_of_range(self, generator):
        """state.row_count must be 0 after guard fires."""
        state = AgentState(
            query="distribusi share produk bulan ini",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=True,
            out_of_range_latest="2026-06-30",
            query_result=[{"entity": "X", "total_trx": 100}] * 30,
            row_count=30,
        )

        with patch.object(generator, "_call_llm"):
            result = generator.run(state)

        assert result.row_count == 0, (
            "Guard must set row_count=0 so the UI meta-line shows '0 baris'"
        )

    def test_insights_still_set_after_clear(self, generator):
        """Guard message must still be set even when clearing data."""
        state = AgentState(
            query="distribusi share produk bulan ini",
            database="financial_db",
            data_end_date=date(2026, 6, 30),
            query_out_of_range=True,
            out_of_range_latest="2026-06-30",
            query_result=[{"entity": "X", "trx_share_pct": "10"}],
            row_count=1,
        )

        with patch.object(generator, "_call_llm"):
            result = generator.run(state)

        assert "30 Juni 2026" in (result.insights or ""), (
            "Guard message must still contain the latest available date"
        )
        assert result.query_result == []
        assert result.row_count == 0
