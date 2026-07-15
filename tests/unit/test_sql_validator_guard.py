"""
SQLValidator silent-rewrite guard tests.

Verifies three invariants introduced as defense-in-depth against AI-layer
semantic mutation:

  1. SQL that passes layers 1-3 (syntax/security/whitelist) is returned
     UNCHANGED — byte-for-byte — even when the AI layer reports errors.
     This covers the "Mode 1" audit failure: nano silently rewrote valid SQL
     (LAG→SUM, subquery filter→flat aggregation).

  2. When the AI layer fires on structurally-valid SQL, a WARNING is logged
     and _auto_fix is never called.

  3. Structural errors (layers 1-3) still trigger auto-fix as before — the
     guard must not block the legitimate repair path.

All tests mock _call_llm / _validate_logic_ai / _auto_fix — no real API calls.
"""

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from src.agents.sql_validator import SQLValidator
from src.models.agent_state import AgentState
from src.utils.exceptions import SQLValidationError

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def validator_ai():
    """SQLValidator with AI validation enabled, client mocked out."""
    with patch.object(SQLValidator, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4.1-mini")):
        return SQLValidator(enable_ai_validation=True, max_retries=2)


@pytest.fixture
def validator_no_ai():
    """SQLValidator with AI validation disabled."""
    with patch.object(SQLValidator, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4.1-mini")):
        return SQLValidator(enable_ai_validation=False)


def _state(sql: str, query: str = "berapa total transaksi?") -> AgentState:
    s = AgentState(query=query, database="financial_db")
    s.sql = sql
    return s


# ── 1. SQL identity — window functions ──────────────────────────────────────

class TestSQLIdentityWindowFunction:
    """
    SQL containing LAG/LEAD/RANK window functions must survive the validator
    UNCHANGED when layers 1-3 pass.  'Unchanged' means string-identical —
    not just 'still valid'.
    """

    WINDOW_SQL = (
        "SELECT partner_group, date, total_trx,\n"
        "       LAG(total_trx) OVER (PARTITION BY partner_group ORDER BY date) AS prev_trx\n"
        "FROM daily_master\n"
        "ORDER BY partner_group, date"
    )

    def test_window_function_sql_identical_after_validation(self, validator_ai):
        state = _state(self.WINDOW_SQL, query="bandingkan transaksi partner bulan ini vs lalu")

        # AI layer: claims there is an error (replicating nano false-positive)
        with patch.object(validator_ai, "_validate_logic_ai",
                          return_value=(["LOGIC: Juni should be Q2"], [])):
            with patch.object(validator_ai, "_record_token_usage"):
                result = validator_ai.run(state)

        assert result.validated_sql == self.WINDOW_SQL, (
            f"validated_sql must be byte-identical to input.\n"
            f"Expected:\n{self.WINDOW_SQL}\n\n"
            f"Got:\n{result.validated_sql}"
        )

    def test_auto_fix_not_called_on_window_function_sql(self, validator_ai):
        """_auto_fix must never be invoked when only the AI layer complains."""
        state = _state(self.WINDOW_SQL)

        with patch.object(validator_ai, "_validate_logic_ai",
                          return_value=(["LOGIC: some AI complaint"], [])):
            with patch.object(validator_ai, "_auto_fix") as mock_fix:
                with patch.object(validator_ai, "_record_token_usage"):
                    validator_ai.run(state)

        mock_fix.assert_not_called()

    def test_window_function_guard_logs_warning(self, validator_ai, caplog):
        """A WARNING must be emitted when AI errors are suppressed."""
        state = _state(self.WINDOW_SQL)

        with patch.object(validator_ai, "_validate_logic_ai",
                          return_value=(["LOGIC: false positive"], [])):
            with patch.object(validator_ai, "_record_token_usage"):
                with caplog.at_level(logging.WARNING):
                    validator_ai.run(state)

        assert any(
            "silent-rewrite guard" in r.message.lower()
            for r in caplog.records
        ), "Expected warning containing 'silent-rewrite guard'"


# ── 2. SQL identity — subquery filter ───────────────────────────────────────

class TestSQLIdentitySubquery:
    """
    SQL with WHERE ... IN (SELECT ...) subqueries must pass through unchanged.
    Nano audit found this was rewritten to a flat aggregation silently.
    """

    SUBQUERY_SQL = (
        "SELECT partner_group, SUM(total_trx) AS total\n"
        "FROM daily_master\n"
        "WHERE partner_group IN (\n"
        "    SELECT partner_group FROM daily_master\n"
        "    WHERE periode >= '2026-06-01'\n"
        "    GROUP BY partner_group\n"
        "    HAVING SUM(total_trx) < 1000\n"
        ")\n"
        "GROUP BY partner_group"
    )

    def test_subquery_sql_identical_after_validation(self, validator_ai):
        state = _state(self.SUBQUERY_SQL, query="partner mana yang transaksinya rendah bulan Juni?")

        with patch.object(validator_ai, "_validate_logic_ai",
                          return_value=(["LOGIC: subquery might be simplified"], [])):
            with patch.object(validator_ai, "_record_token_usage"):
                result = validator_ai.run(state)

        assert result.validated_sql == self.SUBQUERY_SQL, (
            f"Subquery SQL must be unchanged.\nExpected:\n{self.SUBQUERY_SQL}\n\nGot:\n{result.validated_sql}"
        )

    def test_subquery_auto_fix_not_called(self, validator_ai):
        state = _state(self.SUBQUERY_SQL)

        with patch.object(validator_ai, "_validate_logic_ai",
                          return_value=(["LOGIC: AI complaint"], [])):
            with patch.object(validator_ai, "_auto_fix") as mock_fix:
                with patch.object(validator_ai, "_record_token_usage"):
                    validator_ai.run(state)

        mock_fix.assert_not_called()


# ── 3. SQL identity — CTE with aggregation ──────────────────────────────────

class TestSQLIdentityCTE:
    """CTE queries that pass layers 1-3 must be returned identical."""

    CTE_SQL = (
        "WITH monthly AS (\n"
        "    SELECT partner_group,\n"
        "           SUM(total_trx) AS total\n"
        "    FROM daily_master\n"
        "    WHERE total_trx > 0\n"
        "    GROUP BY partner_group\n"
        ")\n"
        "SELECT partner_group, total FROM monthly ORDER BY total DESC"
    )

    def test_cte_sql_unchanged_when_ai_fires(self, validator_ai):
        state = _state(self.CTE_SQL)

        with patch.object(validator_ai, "_validate_logic_ai",
                          return_value=(["LOGIC: use DATE_TRUNC instead"], [])):
            with patch.object(validator_ai, "_record_token_usage"):
                result = validator_ai.run(state)

        assert result.validated_sql == self.CTE_SQL

    def test_cte_sql_unchanged_when_ai_silent(self, validator_ai):
        """When AI returns no errors, SQL must still be identical."""
        state = _state(self.CTE_SQL)

        with patch.object(validator_ai, "_validate_logic_ai", return_value=([], [])):
            with patch.object(validator_ai, "_record_token_usage"):
                result = validator_ai.run(state)

        assert result.validated_sql == self.CTE_SQL


# ── 4. Structural errors still trigger auto-fix ──────────────────────────────

class TestStructuralErrorStillAutoFixes:
    """
    The guard must NOT block auto-fix when layers 1-3 detect real errors.
    Unknown table → auto-fix path must still be reachable.
    """

    def test_unknown_table_triggers_autofix(self, validator_ai):
        invalid_sql = "SELECT * FROM unknown_table LIMIT 10;"
        fixed_sql   = "SELECT * FROM daily_master LIMIT 10;"
        state = _state(invalid_sql, query="show data")

        with patch.object(validator_ai, "_auto_fix", return_value=fixed_sql):
            result = validator_ai.run(state)

        assert result.validated_sql == fixed_sql

    def test_autofix_called_exactly_once_for_single_structural_error(self, validator_ai):
        invalid_sql = "SELECT * FROM bad_table LIMIT 5;"
        fixed_sql   = "SELECT * FROM daily_master LIMIT 5;"
        state = _state(invalid_sql)

        with patch.object(validator_ai, "_auto_fix", return_value=fixed_sql) as mock_fix:
            validator_ai.run(state)

        assert mock_fix.call_count == 1

    def test_autofix_disabled_raises_on_structural_error(self, validator_no_ai):
        state = _state("SELECT * FROM forbidden_table LIMIT 1;")
        with pytest.raises(SQLValidationError):
            validator_no_ai.run(state)


# ── 5. Clean valid SQL — no AI, no auto-fix ──────────────────────────────────

class TestCleanSQL:
    """Simple guard-regression: clean SQL must pass unchanged in all modes."""

    SIMPLE_SQL = "SELECT SUM(total_trx) FROM daily_master WHERE periode = '2026-06-01'"

    def test_clean_sql_unchanged_ai_enabled(self, validator_ai):
        state = _state(self.SIMPLE_SQL)
        with patch.object(validator_ai, "_validate_logic_ai", return_value=([], [])):
            with patch.object(validator_ai, "_record_token_usage"):
                result = validator_ai.run(state)
        assert result.validated_sql == self.SIMPLE_SQL

    def test_clean_sql_unchanged_ai_disabled(self, validator_no_ai):
        state = _state(self.SIMPLE_SQL)
        result = validator_no_ai.run(state)
        assert result.validated_sql == self.SIMPLE_SQL

    def test_validate_logic_ai_not_called_when_ai_disabled(self, validator_no_ai):
        state = _state(self.SIMPLE_SQL)
        with patch.object(validator_no_ai, "_validate_logic_ai") as mock_ai:
            validator_no_ai.run(state)
        mock_ai.assert_not_called()
