"""
Unit tests for SQLGenerator metric-coverage validation.

Tests three layers:
  1. _extract_select_clause  — correct extraction for simple and CTE SQL
  2. _check_metric_coverage  — correct missing-metric detection
  3. execute()               — regeneration triggered when coverage fails; covered on retry
"""

from unittest.mock import MagicMock, patch, call

import pytest

from src.agents.sql_generator import SQLGenerator
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_generator() -> SQLGenerator:
    with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return SQLGenerator()


def _state(query: str) -> AgentState:
    table = RetrievedTable(
        db_name="financial_db",
        table_name="daily_master",
        description="Daily transaction data",
        columns=["partner_group", "date", "total_trx", "total_revenue"],
        similarity_score=1.0,
    )
    return AgentState(query=query, database="financial_db", evaluated_tables=[table])


# ── _extract_select_clause ────────────────────────────────────────────────────

class TestExtractSelectClause:

    def test_simple_select(self):
        gen = _make_generator()
        sql = "SELECT partner_group, total_revenue FROM daily_master LIMIT 9"
        clause = gen._extract_select_clause(sql)
        assert "total_revenue" in clause
        assert "partner_group" in clause
        assert "from" not in clause  # stops before FROM

    def test_cte_returns_final_select(self):
        gen = _make_generator()
        sql = (
            "WITH base AS (SELECT partner_group, SUM(total_trx) AS trx FROM daily_master "
            "GROUP BY partner_group) "
            "SELECT partner_group, trx, trx_share_pct FROM base LIMIT 9"
        )
        clause = gen._extract_select_clause(sql)
        # Should capture the LAST SELECT (final result), not the CTE inner SELECT
        assert "trx_share_pct" in clause

    def test_with_aliases(self):
        gen = _make_generator()
        sql = (
            "SELECT partner_group, SUM(total_revenue) AS total_revenue, "
            "ROUND((SUM(total_revenue)::numeric / SUM(SUM(total_revenue)) OVER ()) * 100, 2) "
            "AS revenue_share_pct FROM daily_master GROUP BY partner_group LIMIT 9"
        )
        clause = gen._extract_select_clause(sql)
        assert "revenue_share_pct" in clause
        assert "total_revenue" in clause


# ── _check_metric_coverage ────────────────────────────────────────────────────

class TestCheckMetricCoverage:

    def test_revenue_and_share_both_present(self):
        gen = _make_generator()
        sql = (
            "SELECT partner_group, SUM(total_revenue) AS total_revenue, "
            "ROUND(SUM(total_revenue)::numeric * 100 / NULLIF(SUM(SUM(total_revenue)) OVER (), 0), 2) "
            "AS revenue_share_pct FROM daily_master GROUP BY partner_group"
        )
        missing = gen._check_metric_coverage(
            "Bandingkan total revenue dan share revenue per partner", sql
        )
        assert missing == [], f"Expected no missing metrics, got: {missing}"

    def test_share_missing_from_select(self):
        gen = _make_generator()
        sql = "SELECT partner_group, SUM(total_revenue) AS total_revenue FROM daily_master GROUP BY partner_group"
        missing = gen._check_metric_coverage(
            "Bandingkan total revenue dan share revenue per partner", sql
        )
        assert "share" in missing, f"Expected 'share' in missing, got: {missing}"
        assert "revenue" not in missing  # revenue IS present

    def test_revenue_missing_from_select(self):
        gen = _make_generator()
        sql = "SELECT partner_group, SUM(total_trx) AS total_transaksi FROM daily_master GROUP BY partner_group"
        missing = gen._check_metric_coverage(
            "Bandingkan transaksi dan revenue per partner", sql
        )
        assert "revenue" in missing
        assert "transaksi" not in missing

    def test_single_metric_no_false_positive(self):
        gen = _make_generator()
        sql = "SELECT partner_group, SUM(total_trx) AS total_transaksi, ROUND(SUM(total_trx)::numeric / SUM(SUM(total_trx)) OVER () * 100, 2) AS share_transaksi FROM daily_master GROUP BY partner_group"
        missing = gen._check_metric_coverage(
            "Distribusi share transaksi per partner bulan Juni 2026", sql
        )
        assert missing == [], f"Should be fully covered, got: {missing}"

    def test_keyword_not_in_query_not_checked(self):
        """Metrics not mentioned in the query must not trigger false missing."""
        gen = _make_generator()
        sql = "SELECT partner_group, SUM(total_trx) AS total_transaksi FROM daily_master GROUP BY partner_group"
        # query only mentions transaksi, not revenue/share
        missing = gen._check_metric_coverage(
            "Total transaksi per partner bulan Juni 2026", sql
        )
        assert "revenue" not in missing
        assert "share" not in missing

    def test_both_revenue_and_share_missing(self):
        gen = _make_generator()
        sql = "SELECT partner_group, SUM(total_trx) AS total_trx FROM daily_master GROUP BY partner_group"
        missing = gen._check_metric_coverage(
            "Bandingkan revenue dan share revenue per partner", sql
        )
        assert "revenue" in missing
        assert "share" in missing


# ── execute() — regeneration on coverage failure ─────────────────────────────

class TestExecuteCoverageRetry:

    SQL_MISSING_SHARE = (
        "SELECT partner_group, SUM(total_revenue) AS total_revenue "
        "FROM daily_master GROUP BY partner_group LIMIT 9"
    )
    SQL_WITH_SHARE = (
        "SELECT partner_group, SUM(total_revenue) AS total_revenue, "
        "ROUND((SUM(total_revenue)::numeric / NULLIF(SUM(SUM(total_revenue)) OVER (), 0)) * 100, 2) "
        "AS revenue_share_pct FROM daily_master GROUP BY partner_group LIMIT 9"
    )

    def test_regenerates_when_share_missing(self):
        """execute() should call LLM a second time when first SQL is missing 'share'."""
        gen = _make_generator()
        state = _state("Bandingkan total revenue dan share revenue per partner bulan Juni 2026")

        with patch.object(gen, "_call_llm", side_effect=[
            self.SQL_MISSING_SHARE,
            self.SQL_WITH_SHARE,
        ]) as mock_llm:
            result = gen.execute(state)

        assert mock_llm.call_count == 2, "Expected exactly 2 LLM calls (1 miss + 1 retry)"
        assert "revenue_share_pct" in result.sql, "Final SQL must contain share column"

    def test_coverage_feedback_injected_in_second_prompt(self):
        """The second LLM call's prompt must mention the missing metric."""
        gen = _make_generator()
        state = _state("Bandingkan total revenue dan share revenue per partner bulan Juni 2026")
        captured_prompts: list[str] = []

        def capture(prompt, **_):
            captured_prompts.append(prompt)
            if len(captured_prompts) == 1:
                return self.SQL_MISSING_SHARE
            return self.SQL_WITH_SHARE

        with patch.object(gen, "_call_llm", side_effect=capture):
            gen.execute(state)

        assert len(captured_prompts) == 2
        second_prompt = captured_prompts[1]
        assert "share" in second_prompt.lower(), "Coverage feedback must name the missing metric"
        assert "COVERAGE CHECK FAILED" in second_prompt

    def test_no_extra_call_when_coverage_passes_first_try(self):
        """When SQL already covers all metrics, only 1 LLM call should be made."""
        gen = _make_generator()
        state = _state("Bandingkan total revenue dan share revenue per partner bulan Juni 2026")

        with patch.object(gen, "_call_llm", return_value=self.SQL_WITH_SHARE) as mock_llm:
            result = gen.execute(state)

        assert mock_llm.call_count == 1
        assert "revenue_share_pct" in result.sql

    def test_uses_best_sql_after_max_retries(self):
        """If coverage never fixes, execute() must still return the last valid SQL."""
        gen = _make_generator()
        state = _state("Bandingkan total revenue dan share revenue per partner bulan Juni 2026")

        with patch.object(gen, "_call_llm", return_value=self.SQL_MISSING_SHARE):
            result = gen.execute(state)

        assert result.sql is not None
        assert re.match(r"^SELECT", result.sql.strip(), re.IGNORECASE)

    def test_inject_coverage_feedback_modifies_prompt(self):
        """_inject_coverage_feedback must embed the missing keyword into the prompt."""
        gen = _make_generator()
        original = "...some prompt...\nSQL:"
        modified = gen._inject_coverage_feedback(original, self.SQL_MISSING_SHARE, ["share"])
        assert "share" in modified
        assert "COVERAGE CHECK FAILED" in modified
        assert "CORRECTED SQL:" in modified


import re  # used in test_uses_best_sql_after_max_retries
