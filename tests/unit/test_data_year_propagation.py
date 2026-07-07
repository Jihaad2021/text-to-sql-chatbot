"""
Unit tests — dynamic data year propagation (FASE 1a).

Verifies that NO component hardcodes "2026":
  1. get_data_year() returns the correct year from data_end_date.
  2. _inject_year() injects the dynamic year, not a hardcoded constant.
  3. QueryRewriter._build_prompt() propagates the year from data_end_date.
  4. SQLGenerator._build_prompt() uses data_end_date.year in DATE RULES.
  5. AnalyticsAgent._data_range_line() uses dynamic start + end dates.
  6. Simulation: all three agents produce "2027" (not "2026") when
     state.data_end_date = date(2027, 6, 30) and
     state.data_start_date = date(2027, 3, 1).
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.agents.analytics_agent import _build_system_prompt, _data_range_line
from src.agents.query_rewriter import QueryRewriter, _build_prompt, _inject_year
from src.agents.sql_generator import SQLGenerator
from src.models.agent_state import AgentState
from src.utils.date_range import get_data_year


# ── get_data_year ─────────────────────────────────────────────────────────────

class TestGetDataYear:
    def test_returns_year_from_date(self):
        assert get_data_year(date(2027, 6, 30)) == 2027

    def test_returns_year_2026(self):
        assert get_data_year(date(2026, 3, 1)) == 2026

    def test_none_falls_back_to_today(self):
        year = get_data_year(None)
        assert year == date.today().year


# ── _inject_year ──────────────────────────────────────────────────────────────

class TestInjectYear:
    def test_injects_2027_for_bare_month(self):
        result = _inject_year("performa bulan juni", 2027)
        assert "2027" in result
        assert "2026" not in result

    def test_injects_2026_when_year_is_2026(self):
        result = _inject_year("data maret saja", 2026)
        assert "2026" in result

    def test_does_not_double_inject_when_year_already_present(self):
        result = _inject_year("bulan juni 2026", 2027)
        # Already has a year → should NOT inject a second one
        assert result.count("2026") == 1
        assert "2027" not in result

    def test_injects_into_multiple_months(self):
        result = _inject_year("bandingkan mei dan juni", 2027)
        assert result.count("2027") == 2

    def test_english_month_name(self):
        result = _inject_year("compare june vs may", 2027)
        assert "2027" in result


# ── QueryRewriter prompt ──────────────────────────────────────────────────────

class TestQueryRewriterPromptYear:
    def _make_prompt(self, year: int) -> str:
        return _build_prompt(
            tables="daily_master",
            query="berapa total transaksi bulan juni?",
            today="2027-07-01",
            data_year=year,
            history=[],
        )

    def test_prompt_contains_2027(self):
        prompt = self._make_prompt(2027)
        assert "2027" in prompt

    def test_prompt_does_not_contain_hardcoded_2026(self):
        prompt = self._make_prompt(2027)
        # "2026" must NOT appear — year must come purely from parameter
        assert "2026" not in prompt

    def test_ytd_date_uses_dynamic_year(self):
        prompt = self._make_prompt(2027)
        assert "2027-01-01" in prompt

    def test_example_date_uses_dynamic_year(self):
        prompt = self._make_prompt(2027)
        assert "2027-07-01" in prompt or "2027-06-01" in prompt


# ── SQLGenerator prompt ───────────────────────────────────────────────────────

class TestSQLGeneratorPromptYear:
    def _make_state(self, year: int) -> AgentState:
        from src.models.agent_state import AgentState
        from unittest.mock import MagicMock
        state = AgentState(query="test query", database="financial_db")
        state.data_end_date = date(year, 6, 30)
        mock_table = MagicMock()
        mock_table.table_name = "daily_master"
        mock_table.db_name = "financial_db"
        mock_table.description = "Daily transaction data"
        mock_table.columns = ["date", "total_trx"]
        mock_table.relationships = []
        state.evaluated_tables = [mock_table]
        state.intent = {"category": "aggregation", "sql_strategy": "use SUM"}
        state.conversation_history = []
        state.step_results = []
        state.sql_error = None
        state.sql = None
        return state

    def _make_generator(self) -> SQLGenerator:
        with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            with patch.object(SQLGenerator, "_load_examples", return_value=[]):
                return SQLGenerator()

    def test_prompt_contains_2027_not_2026_in_date_rules(self):
        gen = self._make_generator()
        state = self._make_state(2027)
        prompt = gen._build_prompt(state)
        assert "2027" in prompt
        # The DATE RULES block must not reference 2026 as the data year
        date_rules_start = prompt.find("DATE RULES:")
        date_rules_end = prompt.find("\n\n", date_rules_start)
        date_rules_block = prompt[date_rules_start:date_rules_end]
        assert "2027" in date_rules_block
        assert "ALL DATA IS YEAR 2027" in date_rules_block

    def test_prev_years_list_excludes_2027(self):
        gen = self._make_generator()
        state = self._make_state(2027)
        prompt = gen._build_prompt(state)
        # "NEVER use 2024, 2025, 2026" must appear (not 2027)
        assert "NEVER use" in prompt
        assert "2026" in prompt  # 2026 is in the NEVER list
        # "ALL DATA IS YEAR 2027" must appear, not "ALL DATA IS YEAR 2026"
        assert "ALL DATA IS YEAR 2027" in prompt
        assert "ALL DATA IS YEAR 2026" not in prompt


# ── AnalyticsAgent data range ─────────────────────────────────────────────────

class TestDataRangeLine:
    def test_uses_dynamic_end_year(self):
        line = _data_range_line(date(2027, 6, 30), date(2027, 3, 1))
        assert "2027" in line
        assert "2026" not in line

    def test_uses_dynamic_start_month(self):
        line = _data_range_line(date(2027, 6, 30), date(2027, 3, 1))
        assert "Maret" in line
        assert "Juni" in line

    def test_none_end_date_returns_unknown_message(self):
        line = _data_range_line(None)
        assert "2026" not in line
        assert "2027" not in line

    def test_no_start_date_uses_fallback(self):
        line = _data_range_line(date(2027, 6, 30), None)
        assert "2027" in line
        assert "2026" not in line

    def test_system_prompt_propagates_2027(self):
        prompt = _build_system_prompt(date(2027, 6, 30), date(2027, 3, 1))
        assert "2027" in prompt
        assert "Maret 2027" in prompt
        assert "Juni 2027" in prompt
        # "Maret 2026" must NOT appear — that was the old hardcoded value
        assert "Maret 2026" not in prompt


# ── Full simulation: data_end_date=2027 → no "2026" in any prompt ─────────────

class TestYearSimulation2027:
    """
    Simulates a scenario where data_end_date=date(2027,6,30).
    Confirms the system would auto-adapt to 2027 without any code change.
    """

    def test_inject_year_adapts_to_2027(self):
        state = AgentState(query="performa bulan juni", database="financial_db")
        state.data_end_date = date(2027, 6, 30)
        from src.utils.date_range import get_data_year
        year = get_data_year(state.data_end_date)
        rewritten = _inject_year(state.query, year)
        assert "2027" in rewritten
        assert "2026" not in rewritten

    def test_rewriter_prompt_has_no_hardcoded_2026(self):
        prompt = _build_prompt(
            tables="daily_master",
            query="berapa transaksi bulan maret?",
            today="2027-07-01",
            data_year=2027,
            history=[],
        )
        assert "2027" in prompt
        assert "2026" not in prompt

    def test_analytics_data_range_has_no_hardcoded_2026(self):
        line = _data_range_line(date(2027, 6, 30), date(2027, 3, 1))
        assert "2027" in line
        assert "2026" not in line

    def test_data_start_date_field_exists_on_agent_state(self):
        state = AgentState(query="test", database="financial_db")
        state.data_start_date = date(2027, 3, 1)
        assert state.data_start_date == date(2027, 3, 1)
