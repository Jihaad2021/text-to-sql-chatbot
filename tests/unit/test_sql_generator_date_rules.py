"""
Unit tests for SQLGenerator DATE RULES — named-month resolution fix.

Tests lock in that:
1. LATEST AVAILABLE DATA DATE appears in the prompt from state.data_end_date.
2. Named-month resolution rule (NEVER substitute a different month) is present.
3. Prompt uses the fallback date string when data_end_date is None.
4. data_end_date=None does not crash prompt building.

These tests guard against regression where:
- "bulan Juni 2026" was resolved to May (prior-period) dates by the LLM
  because (a) data_end_date was absent from the prompt and (b) no explicit
  named-month rule existed — causing the LLM to pattern-match Example 7's
  "bulan ini/bulan lalu" logic instead.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.agents.sql_generator import SQLGenerator
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable


# -----------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------

def _make_generator() -> SQLGenerator:
    with patch.object(SQLGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        with patch("builtins.open", side_effect=FileNotFoundError):
            return SQLGenerator()


def _daily_master_table() -> RetrievedTable:
    return RetrievedTable(
        db_name="financial_db",
        table_name="daily_master",
        columns=[
            "date", "partner_group", "total_trx", "success_trx",
            "fail_trx", "total_revenue",
        ],
        description="Daily aggregated payment data",
        similarity_score=0.95,
        relationships=[],
    )


def _state_for(query: str, data_end_date: date | None) -> AgentState:
    state = AgentState(query=query, database="financial_db")
    state.data_end_date = data_end_date
    state.intent = {
        "category": "recommendation",
        "confidence": 0.92,
        "reason": "User asks which partner to prioritise",
        "sql_strategy": "Rank partners by SR for the requested period",
    }
    state.evaluated_tables = [_daily_master_table()]
    return state


def _capture_prompt(generator: SQLGenerator, state: AgentState) -> str:
    """Run the generator with a mocked LLM and return the prompt that was passed."""
    mock_sql = "SELECT partner_group FROM daily_master LIMIT 100;"
    captured: list[str] = []

    def _fake_llm(prompt: str, **_kw) -> str:
        captured.append(prompt)
        return mock_sql

    with patch.object(generator, "_call_llm", side_effect=_fake_llm):
        generator.run(state)

    return captured[0]


# -----------------------------------------------------------------------
# TestDataEndDateInPrompt
# -----------------------------------------------------------------------

class TestDataEndDateInPrompt:
    """Verify that LATEST AVAILABLE DATA DATE is injected into the prompt."""

    def test_data_end_date_present_in_prompt(self):
        """When state.data_end_date is set, prompt must contain LATEST AVAILABLE DATA DATE."""
        gen   = _make_generator()
        state = _state_for("partner mana yang perlu diprioritaskan bulan Juni 2026",
                           data_end_date=date(2026, 6, 30))
        prompt = _capture_prompt(gen, state)

        assert "LATEST AVAILABLE DATA DATE" in prompt

    def test_data_end_date_value_in_prompt(self):
        """The actual date string '2026-06-30' must appear in the prompt."""
        gen   = _make_generator()
        state = _state_for("partner prioritas bulan Juni 2026", date(2026, 6, 30))
        prompt = _capture_prompt(gen, state)

        assert "2026-06-30" in prompt

    def test_data_end_date_none_uses_fallback(self):
        """When data_end_date is None, prompt should still contain a fallback date (year-12-31)."""
        gen   = _make_generator()
        state = _state_for("partner prioritas bulan Juni", data_end_date=None)
        prompt = _capture_prompt(gen, state)

        assert "LATEST AVAILABLE DATA DATE" in prompt
        # Fallback is data_year-12-31; year should appear somewhere in the date block
        assert "-12-31" in prompt

    def test_data_end_date_none_does_not_crash(self):
        """Prompt building must not raise when data_end_date is None."""
        gen   = _make_generator()
        state = _state_for("partner butuh perhatian bulan Juni", data_end_date=None)
        # Should not raise
        prompt = _capture_prompt(gen, state)
        assert "DATE RULES" in prompt


# -----------------------------------------------------------------------
# TestNamedMonthResolutionRule
# -----------------------------------------------------------------------

class TestNamedMonthResolutionRule:
    """Verify that the named-month NEVER-substitute rule is present in the prompt."""

    def test_named_month_rule_present(self):
        """Prompt must contain the named-month resolution instruction."""
        gen   = _make_generator()
        state = _state_for("partner mana yang perlu diprioritaskan bulan Juni 2026",
                           date(2026, 6, 30))
        prompt = _capture_prompt(gen, state)

        # The rule must instruct the LLM never to substitute a different month.
        assert "NEVER substitute a different month" in prompt

    def test_named_month_rule_contains_juni_example(self):
        """Prompt must contain a concrete Juni→06-01..06-30 example."""
        gen   = _make_generator()
        state = _state_for("partner Juni 2026", date(2026, 6, 30))
        prompt = _capture_prompt(gen, state)

        assert "06-01" in prompt
        assert "06-30" in prompt

    def test_named_month_rule_contains_mei_example(self):
        """Prompt must contain a concrete Mei→05-01..05-31 example."""
        gen   = _make_generator()
        state = _state_for("partner Mei 2026", date(2026, 5, 31))
        prompt = _capture_prompt(gen, state)

        assert "05-01" in prompt
        assert "05-31" in prompt


# -----------------------------------------------------------------------
# TestSQLDateGeneration  (mocked LLM returning correct SQL)
# -----------------------------------------------------------------------

class TestSQLDateGeneration:
    """Verify that when the mocked LLM returns correct June SQL, the state is set correctly."""

    def test_juni_query_sql_written_to_state(self):
        """State.sql must contain June date range when mocked LLM returns it."""
        gen   = _make_generator()
        state = _state_for("partner mana yang perlu diprioritaskan bulan Juni 2026",
                           date(2026, 6, 30))
        june_sql = (
            "SELECT partner_group, "
            "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS sr "
            "FROM daily_master "
            "WHERE date >= '2026-06-01' AND date <= '2026-06-30' "
            "GROUP BY partner_group ORDER BY sr ASC LIMIT 100;"
        )

        with patch.object(gen, "_call_llm", return_value=june_sql):
            result = gen.run(state)

        assert "'2026-06-01'" in result.sql
        assert "'2026-06-30'" in result.sql
        assert "'2026-05-" not in result.sql  # must NOT contain May dates

    def test_mei_query_sql_written_to_state(self):
        """State.sql must contain May date range when mocked LLM returns it."""
        gen   = _make_generator()
        state = _state_for("partner mana yang butuh perhatian bulan Mei 2026",
                           date(2026, 5, 31))
        mei_sql = (
            "SELECT partner_group, "
            "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS sr "
            "FROM daily_master "
            "WHERE date >= '2026-05-01' AND date <= '2026-05-31' "
            "GROUP BY partner_group ORDER BY sr ASC LIMIT 100;"
        )

        with patch.object(gen, "_call_llm", return_value=mei_sql):
            result = gen.run(state)

        assert "'2026-05-01'" in result.sql
        assert "'2026-05-31'" in result.sql
        assert "'2026-06-" not in result.sql  # must NOT bleed into June

    def test_sql_state_not_contaminated_across_calls(self):
        """Two sequential calls with different months must not bleed date ranges."""
        gen = _make_generator()

        june_sql = (
            "SELECT partner_group FROM daily_master "
            "WHERE date >= '2026-06-01' AND date <= '2026-06-30' LIMIT 100;"
        )
        mei_sql = (
            "SELECT partner_group FROM daily_master "
            "WHERE date >= '2026-05-01' AND date <= '2026-05-31' LIMIT 100;"
        )

        state_june = _state_for("partner bulan Juni 2026", date(2026, 6, 30))
        with patch.object(gen, "_call_llm", return_value=june_sql):
            r1 = gen.run(state_june)

        state_mei = _state_for("partner bulan Mei 2026", date(2026, 5, 31))
        with patch.object(gen, "_call_llm", return_value=mei_sql):
            r2 = gen.run(state_mei)

        assert "'2026-06-01'" in r1.sql
        assert "'2026-05-01'" in r2.sql
        # Cross-contamination check
        assert "'2026-05-" not in r1.sql
        assert "'2026-06-" not in r2.sql
