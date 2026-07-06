"""
Recommendation intent routing — unit tests.

TC1: Recommendation sebagai FOLLOW-UP (ada analytic prior turn dengan row_count > 0)
     → recommendation_from_history=True, SQLGenerator tidak dipanggil,
       InsightGenerator menggunakan _build_recommendation_synthesis_prompt.

TC2: Recommendation BERDIRI SENDIRI (tidak ada analytic prior turn)
     → recommendation_from_history=False, SQL pipeline berjalan normal,
       strategy hint yang dikirim ke SQLGenerator adalah instruksi simple aggregation.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.insight_generator import (
    InsightGenerator,
    _RECOMMENDATION_RULES_BLOCK,
    _RECOMMENDATION_SYNTHESIS_INSTRUCTIONS,
)
from src.agents.intent_classifier import INTENT_SQL_STRATEGY
from src.core.pipeline import _has_analytic_prior_turn
from src.models.agent_state import AgentState


# ── _has_analytic_prior_turn helper ───────────────────────────────────────

class TestHasAnalyticPriorTurn:

    def test_true_when_root_cause_with_data(self):
        history = [{"intent_category": "root_cause_analysis", "row_count": 5}]
        assert _has_analytic_prior_turn(history) is True

    def test_true_when_ranking_with_data(self):
        history = [{"intent_category": "ranking_analysis", "row_count": 9}]
        assert _has_analytic_prior_turn(history) is True

    def test_true_when_complex_with_data(self):
        history = [{"intent_category": "complex_analytics", "row_count": 3}]
        assert _has_analytic_prior_turn(history) is True

    def test_false_when_analytic_but_zero_rows(self):
        history = [{"intent_category": "root_cause_analysis", "row_count": 0}]
        assert _has_analytic_prior_turn(history) is False

    def test_false_when_aggregation_intent(self):
        """aggregation is not in _SYNTHESIS_ELIGIBLE_INTENTS."""
        history = [{"intent_category": "aggregation", "row_count": 10}]
        assert _has_analytic_prior_turn(history) is False

    def test_false_when_empty_history(self):
        assert _has_analytic_prior_turn([]) is False

    def test_false_when_no_intent_category_field(self):
        history = [{"query": "something", "row_count": 5}]
        assert _has_analytic_prior_turn(history) is False

    def test_true_when_analytic_turn_mixed_with_others(self):
        """Only one analytic turn with data is enough."""
        history = [
            {"intent_category": "aggregation",         "row_count": 10},
            {"intent_category": "root_cause_analysis", "row_count": 7},
            {"intent_category": "recommendation",       "row_count": 0},
        ]
        assert _has_analytic_prior_turn(history) is True


# ── TC1: Follow-up recommendation → skip SQL, synthesis from history ──────

class TestRecommendationFollowUp:
    """recommendation after analytic turn → recommendation_from_history=True."""

    @pytest.fixture
    def ig(self):
        with patch.object(InsightGenerator, "_init_client",
                          return_value=("openai", MagicMock(), "gpt-4o-mini")):
            return InsightGenerator()

    def test_recommendation_from_history_flag_set(self):
        """Pipeline must set recommendation_from_history=True for follow-up queries."""
        state = AgentState(
            query="apa yang harus dilakukan?",
            database="financial_db",
            recommendation_from_history=True,
        )
        assert state.recommendation_from_history is True

    def test_insight_generator_uses_synthesis_prompt(self, ig):
        """InsightGenerator must call _build_recommendation_synthesis_prompt when flag set."""
        state = AgentState(
            query="apa yang harus dilakukan untuk meningkatkan transaksi?",
            database="financial_db",
            recommendation_from_history=True,
            conversation_history=[
                {
                    "query":           "kenapa GoPay turun bulan Juni?",
                    "insights":        "GoPay mengalami penurunan SR dari 98.5% ke 96.2% di Juni 2026.",
                    "intent_category": "root_cause_analysis",
                    "row_count":       9,
                },
            ],
        )

        synthesis_prompt_called = []
        original_build = ig._build_recommendation_synthesis_prompt

        def capture_synthesis(s):
            synthesis_prompt_called.append(True)
            return original_build(s)

        ig._build_recommendation_synthesis_prompt = capture_synthesis

        with patch.object(ig, "_call_llm", return_value="Rekomendasi: tingkatkan SR GoPay."):
            ig.run(state)

        assert synthesis_prompt_called, (
            "_build_recommendation_synthesis_prompt harus dipanggil ketika "
            "recommendation_from_history=True"
        )

    def test_synthesis_prompt_contains_full_history(self, ig):
        """Synthesis prompt must include full prior insights, not 200-char truncation."""
        long_insight = "A" * 500
        state = AgentState(
            query="apa yang harus dilakukan?",
            database="financial_db",
            recommendation_from_history=True,
            conversation_history=[
                {
                    "query":           "kenapa GoPay turun?",
                    "insights":        long_insight,
                    "intent_category": "root_cause_analysis",
                    "row_count":       5,
                },
            ],
        )

        prompt = ig._build_recommendation_synthesis_prompt(state)
        assert long_insight in prompt, (
            "Synthesis prompt must include FULL prior insights (not 200-char truncated)"
        )

    def test_sql_generator_not_called_for_followup(self, ig):
        """InsightGenerator must not generate SQL for recommendation follow-up."""
        state = AgentState(
            query="apa yang harus dilakukan?",
            database="financial_db",
            recommendation_from_history=True,
            validated_sql=None,
            query_result=[],
            row_count=0,
            conversation_history=[
                {
                    "query":           "analisis partner bulan Juni",
                    "insights":        "GoPay SR turun 2pp.",
                    "intent_category": "complex_analytics",
                    "row_count":       9,
                },
            ],
        )

        with patch.object(ig, "_call_llm", return_value="Rekomendasi: fokus ke GoPay.") as mock_llm:
            result = ig.run(state)

        mock_llm.assert_called_once()
        assert result.insights == "Rekomendasi: fokus ke GoPay."
        assert result.validated_sql is None


# ── TC2: Standalone recommendation → simple SQL strategy hint ────────────

class TestStandaloneRecommendation:
    """recommendation without prior analytic history → SQL pipeline with simple hint."""

    def test_strategy_hint_is_simple_aggregation(self):
        """INTENT_SQL_STRATEGY['recommendation'] must NOT say 'analytics tools'."""
        hint = INTENT_SQL_STRATEGY["recommendation"]
        assert "analytics tools" not in hint.lower(), (
            "Strategy hint must not reference 'analytics tools' — misleads SQLGenerator "
            "into generating anomaly-detection CTEs"
        )

    def test_strategy_hint_says_no_cte(self):
        """Strategy hint must explicitly forbid CTEs for recommendation."""
        hint = INTENT_SQL_STRATEGY["recommendation"]
        assert "NO CTE" in hint or "no CTE" in hint.lower() or "tanpa CTE" in hint.lower() or "without CTE" in hint.lower(), (
            "Strategy hint must explicitly forbid CTE to prevent multi-period comparisons"
        )

    def test_strategy_hint_mentions_simple_aggregation(self):
        """Strategy hint must direct SQLGenerator to a simple aggregation query."""
        hint = INTENT_SQL_STRATEGY["recommendation"]
        assert any(kw in hint for kw in ["aggregation", "SUM", "GROUP BY", "simple"]), (
            "Strategy hint must describe a simple aggregation query pattern"
        )

    def test_recommendation_from_history_false_by_default(self):
        """AgentState must default recommendation_from_history to False."""
        state = AgentState(query="test", database="financial_db")
        assert state.recommendation_from_history is False


# ── TC3: Standalone recommendation → threshold-based synthesis prompt ─────

class TestStandaloneRecommendationSynthesisPrompt:
    """_build_single_step_prompt() must use threshold-first ordering when
    intent.category == 'recommendation', not volume/revenue ranking."""

    @pytest.fixture
    def ig(self):
        with patch.object(InsightGenerator, "_init_client",
                          return_value=("openai", MagicMock(), "gpt-4o-mini")):
            return InsightGenerator()

    def _make_rec_state(self) -> AgentState:
        """AgentState mimicking Skenario B: 9-partner June 2026 data including
        telkomsel_wallet at SR 92.87% (KRITIS) and qris at SR 99.60% (SEHAT)."""
        return AgentState(
            query="partner mana yang perlu diprioritaskan?",
            database="financial_db",
            recommendation_from_history=False,
            intent={
                "category":     "recommendation",
                "segment":      "partners",
                "confidence":   0.9,
                "reason":       "standalone",
                "sql_strategy": "simple aggregation",
            },
            validated_sql=(
                "SELECT partner_group, SUM(total_trx) AS total_trx, "
                "ROUND((SUM(success_trx)::numeric/NULLIF(SUM(total_trx),0))*100,2) AS success_rate_pct "
                "FROM daily_master WHERE date BETWEEN '2026-06-01' AND '2026-06-30' "
                "GROUP BY partner_group ORDER BY total_trx DESC"
            ),
            query_result=[
                {"partner_group": "qris",              "total_trx": 14_843_101, "success_rate_pct": 99.60},
                {"partner_group": "dana",              "total_trx":  6_322_881, "success_rate_pct": 100.00},
                {"partner_group": "telkomsel_wallet",  "total_trx":      8_116, "success_rate_pct": 92.87},
                {"partner_group": "indomaret",         "total_trx":        549, "success_rate_pct": 100.00},
            ],
            row_count=4,
        )

    def test_prompt_contains_kritis_perhatian_sehat_ordering(self, ig):
        """Recommendation prompt must inject rules BEFORE SQL/RESULTS and add late reinforcement.

        - _RECOMMENDATION_RULES_BLOCK must appear before 'SQL EXECUTED' in the prompt
        - _RECOMMENDATION_SYNTHESIS_INSTRUCTIONS must also be present (late reinforcement)
        - Within the rules block, ordering must be KRITIS → PERHATIAN → SEHAT
        """
        state = self._make_rec_state()
        prompt = ig._build_single_step_prompt(state)

        assert _RECOMMENDATION_RULES_BLOCK in prompt, (
            "Prompt harus mengandung _RECOMMENDATION_RULES_BLOCK"
        )
        assert _RECOMMENDATION_SYNTHESIS_INSTRUCTIONS in prompt, (
            "Prompt harus mengandung _RECOMMENDATION_SYNTHESIS_INSTRUCTIONS (reinforcement di akhir)"
        )
        # Rules block must appear BEFORE the SQL/RESULTS section
        rules_pos = prompt.index(_RECOMMENDATION_RULES_BLOCK)
        sql_pos   = prompt.index("SQL EXECUTED")
        assert rules_pos < sql_pos, (
            "Rules block harus muncul SEBELUM 'SQL EXECUTED' agar LLM membacanya sebelum melihat data"
        )
        # Within the rules block, KRITIS must appear before PERHATIAN before SEHAT
        block = _RECOMMENDATION_RULES_BLOCK
        kritis_pos    = block.index("KRITIS")
        perhatian_pos = block.index("PERHATIAN")
        sehat_pos     = block.index("SEHAT")
        assert kritis_pos < perhatian_pos < sehat_pos, (
            "Rules block harus memerintahkan urutan KRITIS → PERHATIAN → SEHAT"
        )

    def test_prompt_forbids_volume_ordering(self, ig):
        """Recommendation prompt must explicitly forbid volume/revenue-based ordering."""
        state = self._make_rec_state()
        prompt = ig._build_single_step_prompt(state)
        assert "DILARANG mengurutkan" in prompt or "DILARANG menjadikan" in prompt, (
            "Prompt harus melarang pengurutan berdasarkan volume atau revenue"
        )

    def test_prompt_requires_threshold_citation(self, ig):
        """Recommendation prompt must instruct citing violated threshold per entity."""
        state = self._make_rec_state()
        prompt = ig._build_single_step_prompt(state)
        assert "threshold" in prompt.lower(), (
            "Prompt harus mewajibkan penyebutan threshold yang dilanggar"
        )
        assert "98%" in prompt or "98" in prompt, (
            "Prompt harus menyebutkan nilai threshold SR ≥98%"
        )

    def test_general_analysis_block_absent_for_recommendation(self, ig):
        """RANKED DATA / TIME SERIES block must not appear in recommendation prompts."""
        state = self._make_rec_state()
        prompt = ig._build_single_step_prompt(state)
        assert "RANKED DATA" not in prompt, (
            "RANKED DATA block harus absen di recommendation prompt — "
            "digantikan oleh INSTRUKSI SYNTHESIS REKOMENDASI"
        )
