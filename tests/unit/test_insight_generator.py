"""
Unit tests for InsightGenerator.

Tests cover:
- Insight generation from query results
- Empty results handled gracefully
- Fallback if LLM fails
- Indonesian language output
- State input/output correctness
- BUG 1 fix: _strip_partner_section removes partner block for channel queries
- BUG 2 fix: _find_missing_kritis_entities + KRITIS guard appends omitted KRITIS entities
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.agents.insight_generator import InsightGenerator
from src.models.agent_state import AgentState, ToolCallResult
from src.utils.exceptions import InsightGenerationError


@pytest.fixture
def generator():
    """Initialize InsightGenerator with mocked OpenAI client."""
    with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
        return InsightGenerator()


@pytest.fixture
def anthropic_generator():
    """InsightGenerator wired to Anthropic provider — needed to test use_thinking path."""
    with patch.object(InsightGenerator, "_init_client",
                      return_value=("anthropic", MagicMock(), "claude-sonnet-4-6")):
        return InsightGenerator()


# ========================================
# Test: Insight Generation
# ========================================

class TestInsightGeneration:

    def test_generates_insights_from_results(self, generator, state_with_results):
        """Should generate insights and write to state.insights."""
        mock_insight = "Terdapat 100 customer yang terdaftar dalam sistem."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_results)

        assert state.insights is not None
        assert len(state.insights) > 0

    def test_insights_written_to_state(self, generator, state_with_results):
        """Insights should be written to state.insights."""
        mock_insight = "Terdapat 100 customer yang terdaftar dalam sistem."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_results)

        assert state.insights == mock_insight

    def test_query_included_in_prompt(self, generator, state_with_results):
        """User query should be included in LLM prompt."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight) as mock_llm:
            generator.run(state_with_results)
            prompt = mock_llm.call_args[0][0]

        assert state_with_results.query in prompt

    def test_results_included_in_prompt(self, generator, state_with_results):
        """Query results should be included in LLM prompt."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight) as mock_llm:
            generator.run(state_with_results)
            prompt = mock_llm.call_args[0][0]

        assert "100" in prompt


# ========================================
# Test: Empty Results
# ========================================

class TestEmptyResults:

    def test_handles_empty_results_gracefully(self, generator, state_with_sql):
        """Should handle empty results without raising error."""
        state_with_sql.query_result = []
        state_with_sql.row_count = 0

        mock_insight = "Tidak ada data yang ditemukan untuk query ini."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_sql)

        assert state.insights is not None

    def test_empty_results_mentioned_in_prompt(self, generator, state_with_sql):
        """Prompt should indicate 0 rows for empty results."""
        state_with_sql.query_result = []
        state_with_sql.row_count = 0

        mock_insight = "Tidak ada data."

        with patch.object(generator, "_call_llm", return_value=mock_insight) as mock_llm:
            generator.run(state_with_sql)
            prompt = mock_llm.call_args[0][0]

        assert "0" in prompt


# ========================================
# Test: Fallback
# ========================================

class TestFallback:

    def test_fallback_if_llm_fails(self, generator, state_with_results):
        """Should use fallback insight if LLM call fails."""
        with patch.object(generator, "_call_llm", side_effect=Exception("LLM error")):
            state = generator.run(state_with_results)

        assert state.insights is not None
        assert len(state.insights) > 0

    def test_fallback_single_value_result(self, generator):
        """Fallback should format single value result."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state.validated_sql = "SELECT COUNT(*) as total FROM customers;"
        state.query_result = [{"total": 100}]
        state.row_count = 1

        with patch.object(generator, "_call_llm", side_effect=Exception("LLM error")):
            state = generator.run(state)

        assert "100" in state.insights

    def test_fallback_empty_result(self, generator):
        """Fallback should handle empty results."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        state.validated_sql = "SELECT COUNT(*) as total FROM customers;"
        state.query_result = []
        state.row_count = 0

        with patch.object(generator, "_call_llm", side_effect=Exception("LLM error")):
            state = generator.run(state)

        assert state.insights is not None


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_timing_recorded(self, generator, state_with_results):
        """Execution time should be recorded in state.timing."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            state = generator.run(state_with_results)

        assert "insight_generator" in state.timing
        assert state.timing["insight_generator"] > 0

    def test_metrics_updated_on_success(self, generator, state_with_results):
        """Metrics should update after successful execution."""
        mock_insight = "Terdapat 100 customer."

        with patch.object(generator, "_call_llm", return_value=mock_insight):
            generator.run(state_with_results)

        metrics = generator.get_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["successful_calls"] == 1


# ========================================
# Test: Extended thinking gate
# ========================================

class TestExtendedThinking:
    """Verify use_thinking is derived from intent category string, not the dict itself."""

    def test_use_thinking_true_for_root_cause_with_anthropic(self, anthropic_generator, state_with_results):
        """Anthropic provider + root_cause_analysis intent → use_thinking=True passed to _call_llm."""
        state_with_results.intent = {
            "category": "root_cause_analysis",
            "confidence": 0.92,
            "reason": "causal investigation query",
            "sql_strategy": "analytical",
        }
        with patch.object(anthropic_generator, "_call_llm", return_value="insight") as mock_llm:
            anthropic_generator.run(state_with_results)

        _, kwargs = mock_llm.call_args
        assert kwargs.get("use_thinking") is True, (
            "root_cause_analysis with Anthropic provider must trigger extended thinking"
        )

    def test_use_thinking_false_for_simple_select_with_anthropic(self, anthropic_generator, state_with_results):
        """Anthropic provider + simple_select intent → use_thinking=False (not in _THINKING_INTENTS)."""
        state_with_results.intent = {
            "category": "simple_select",
            "confidence": 0.95,
            "reason": "basic retrieval",
            "sql_strategy": "simple",
        }
        with patch.object(anthropic_generator, "_call_llm", return_value="insight") as mock_llm:
            anthropic_generator.run(state_with_results)

        _, kwargs = mock_llm.call_args
        assert kwargs.get("use_thinking") is False, (
            "simple_select must not trigger extended thinking"
        )


# ========================================
# Test: FIX #2 — monitoring guard year false positive
# ========================================

def _make_dist_tr(actual_entity_count: int = 9, row_count: int = 9) -> ToolCallResult:
    return ToolCallResult(
        tool_name="get_distribution",
        data=[],
        row_count=row_count,
        sql_or_params="SELECT ...",
        description="partner breakdown",
        actual_entity_count=actual_entity_count,
        dimension="partner",
    )


class TestMonitoringGuardYearFalsePositive:
    """Ensure the FIX 5 monitoring guard does not fire on year digits inside date strings."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_year_in_query_does_not_trigger_warning(self):
        """Query containing '2026' (year) must NOT trigger warning even if insights mention '2026'."""
        gen = self._gen()
        # This query was the real false-positive trigger: QueryRewriter appended '2026'
        query = "kapan saja penurunan transaksi terjadi di bulan Juni 2026?"
        # Insights contain '2026' only in date strings, not as a row-count claim
        insight_text = (
            "Volume transaksi mengalami penurunan pada **30 Juni 2026**, dengan 592.400 "
            "transaksi, turun 37,7% vs hari sebelumnya."
        )
        state = AgentState(query=query, database="financial_db")
        state.query_result = [{"period": "2026-06-30", "total_trx": 592400}]
        state.row_count = 1
        state.tool_results = [_make_dist_tr(actual_entity_count=9, row_count=9)]

        warning_calls = []
        original_log = gen.log

        def capture_log(msg, level="info"):
            if level == "warning" and "query number" in msg:
                warning_calls.append(msg)
            original_log(msg, level=level)

        with patch.object(gen, "log", side_effect=capture_log):
            with patch.object(gen, "_call_llm", return_value=insight_text):
                gen.run(state)

        assert warning_calls == [], (
            f"Year '2026' in query must not trigger monitoring warning. Got: {warning_calls}"
        )

    def test_explicit_row_count_request_still_triggers_warning(self):
        """Query with explicit top-N number ('top 50') that mismatches actual count MUST warn."""
        gen = self._gen()
        query = "tampilkan top 50 partner bulan Juni"
        # Insight mentions '50' — but actual row_count is only 9
        insight_text = (
            "Berikut 50 partner dengan transaksi tertinggi pada bulan Juni 2026."
        )
        state = AgentState(query=query, database="financial_db")
        state.query_result = [{"entity": "qris", "total_trx": 100}]
        state.row_count = 9
        state.tool_results = [_make_dist_tr(actual_entity_count=50, row_count=9)]

        warning_calls = []
        original_log = gen.log

        def capture_log(msg, level="info"):
            if level == "warning" and "query number" in msg:
                warning_calls.append(msg)
            original_log(msg, level=level)

        with patch.object(gen, "log", side_effect=capture_log):
            with patch.object(gen, "_call_llm", return_value=insight_text):
                gen.run(state)

        assert len(warning_calls) == 1, (
            f"Explicit top-50 request with '50' in insight must trigger warning. Got: {warning_calls}"
        )


# ========================================
# Test: BUG 1 — _strip_partner_section
# ========================================

class TestStripPartnerSection:
    """_strip_partner_section must remove the Top 5 partner block for channel queries."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_removes_partner_block_from_context(self):
        """Partner section must be absent after stripping."""
        ctx = (
            "Bulan berjalan: 27.8jt transaksi\n\n"
            "Top 5 partner bulan ini:\n"
            "  dana: 6.3jt trx ↓5.6%MoM [PERHATIAN]\n"
            "  gopay: 1.9jt trx ↓4.9%MoM [PERHATIAN]\n\n"
            "Distribusi channel bulan ini:\n"
            "  i1: 96.2%\n"
        )
        result = self._gen()._strip_partner_section(ctx)
        assert "Top 5 partner" not in result
        assert "dana" not in result
        assert "gopay" not in result

    def test_preserves_channel_section(self):
        """Channel distribution block must remain intact after stripping."""
        ctx = (
            "header\n\n"
            "Top 5 partner bulan ini:\n"
            "  dana: 6.3jt trx\n\n"
            "Distribusi channel bulan ini:\n"
            "  i1: 96.2%\n"
            "  f0: 1.6%\n"
        )
        result = self._gen()._strip_partner_section(ctx)
        assert "Distribusi channel" in result
        assert "i1" in result

    def test_noop_when_no_partner_block(self):
        """Context without a partner block must be returned unchanged."""
        ctx = "Distribusi channel bulan ini:\n  i1: 96.2%\n"
        gen = self._gen()
        assert gen._strip_partner_section(ctx) == ctx

    def test_channel_query_single_step_prompt_excludes_partner_names(self):
        """For segment=channels (single-step), partner names must not appear in the LLM prompt."""
        gen = self._gen()
        state = AgentState(query="channel mana yang perlu perhatian?", database="financial_db")
        state.intent = {"category": "recommendation", "segment": "channels"}
        state.context_snapshot = (
            "header\n\n"
            "Top 5 partner bulan ini:\n"
            "  dana: 6.3jt trx ↓5.6%MoM [PERHATIAN]\n"
            "  gopay: 1.9jt trx ↓4.9%MoM [PERHATIAN]\n\n"
            "Distribusi channel bulan ini:\n"
            "  i1: 96.2%\n"
        )
        state.query_result = [{"channel": "i1", "total_trx": 1000}]
        state.row_count = 1
        state.validated_sql = "SELECT channel FROM channel_payment"

        with patch.object(gen, "_call_llm", return_value="i1 dominan.") as mock_llm:
            gen.run(state)
            prompt = mock_llm.call_args[0][0]

        assert "dana" not in prompt
        assert "gopay" not in prompt
        assert "Distribusi channel" in prompt

    def test_channel_query_multi_step_prompt_excludes_partner_names(self):
        """For segment=channels (multi-step), partner names must not appear in the LLM prompt."""
        from src.models.agent_state import StepResult
        gen = self._gen()
        state = AgentState(query="channel mana yang perlu perhatian?", database="financial_db")
        state.intent = {"category": "recommendation", "segment": "channels"}
        state.is_multi_step = True
        state.step_results = [
            StepResult(
                step_number=1, description="channel breakdown",
                sql="SELECT channel, SUM(total_trx) FROM channel_payment GROUP BY channel",
                data=[{"channel": "i1", "total_trx": 1000}], row_count=1, summary="",
            )
        ]
        state.context_snapshot = (
            "header\n\n"
            "Top 5 partner bulan ini:\n"
            "  dana: 6.3jt trx ↓5.6%MoM [PERHATIAN]\n"
            "  gopay: 1.9jt trx ↓4.9%MoM [PERHATIAN]\n\n"
            "Distribusi channel bulan ini:\n"
            "  i1: 96.2%\n"
        )

        with patch.object(gen, "_call_llm", return_value="i1 dominan.") as mock_llm:
            gen.run(state)
            prompt = mock_llm.call_args[0][0]

        assert "dana" not in prompt
        assert "gopay" not in prompt
        assert "Distribusi channel" in prompt


# ========================================
# Test: BUG 2 — _find_missing_kritis_entities + KRITIS guard
# ========================================

class TestFindMissingKritisEntities:
    """_find_missing_kritis_entities must return KRITIS entities absent from insight text."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_returns_unlisted_kritis_entity(self):
        """KRITIS entity not mentioned in insights must appear in result."""
        rows = [
            {"partner_group": "dana", "total_trx": 6000000, "success_rate_pct": Decimal("99.5")},
            {"partner_group": "telkomsel_wallet", "total_trx": 8116, "success_rate_pct": Decimal("92.87")},
        ]
        missing = self._gen()._find_missing_kritis_entities(rows, "dana performa baik.")
        assert len(missing) == 1
        assert missing[0][0] == "telkomsel_wallet"
        assert abs(missing[0][1] - 92.87) < 0.01

    def test_not_missing_when_mentioned_in_insights(self):
        """Entity whose name appears in insights must not be flagged."""
        rows = [{"partner_group": "telkomsel_wallet", "success_rate_pct": Decimal("92.87")}]
        missing = self._gen()._find_missing_kritis_entities(
            rows, "telkomsel_wallet berstatus KRITIS dengan SR 92.87%."
        )
        assert missing == []

    def test_noop_when_no_sr_column(self):
        """Result without SR column must return empty list."""
        rows = [{"partner_group": "dana", "total_trx": 100}]
        assert self._gen()._find_missing_kritis_entities(rows, "dana ok.") == []

    def test_noop_when_sr_above_threshold(self):
        """Entities with SR >= 95% must not appear in result."""
        rows = [
            {"partner_group": "dana", "success_rate_pct": Decimal("99.9")},
            {"partner_group": "finnet", "success_rate_pct": Decimal("95.0")},
        ]
        assert self._gen()._find_missing_kritis_entities(rows, "no one mentioned.") == []

    def test_case_insensitive_match(self):
        """Match must be case-insensitive (insight uses title case, result uses lowercase)."""
        rows = [{"partner_group": "telkomsel_wallet", "success_rate_pct": Decimal("92.87")}]
        missing = self._gen()._find_missing_kritis_entities(
            rows, "Telkomsel_Wallet perlu perhatian."
        )
        assert missing == []


class TestKritisGuardInExecute:
    """execute() must append KRITIS section when recommendation result has unlisted KRITIS entity."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_kritis_entity_appended_when_missing_from_llm_output(self):
        """telkomsel_wallet KRITIS must appear in final insights even when LLM omits it."""
        gen = self._gen()
        state = AgentState(query="partner mana yang perlu diprioritaskan?", database="financial_db")
        state.intent = {"category": "recommendation", "segment": "partners"}
        state.query_result = [
            {"partner_group": "dana", "total_trx": 6000000, "success_rate_pct": Decimal("99.5")},
            {"partner_group": "telkomsel_wallet", "total_trx": 8116, "success_rate_pct": Decimal("92.87")},
        ]
        state.row_count = 2
        state.validated_sql = "SELECT partner_group, success_rate_pct FROM ..."

        with patch.object(gen, "_call_llm", return_value="dana performa baik."):
            state = gen.run(state)

        assert "telkomsel_wallet" in state.insights.lower()
        assert "KRITIS" in state.insights
        assert "92.87" in state.insights

    def test_no_duplication_when_kritis_already_mentioned(self):
        """If LLM already mentions the KRITIS entity, guard must not append a duplicate."""
        gen = self._gen()
        state = AgentState(query="partner mana yang perlu diprioritaskan?", database="financial_db")
        state.intent = {"category": "recommendation", "segment": "partners"}
        state.query_result = [
            {"partner_group": "telkomsel_wallet", "total_trx": 8116, "success_rate_pct": Decimal("92.87")},
        ]
        state.row_count = 1
        state.validated_sql = "SELECT ..."
        llm_output = "telkomsel_wallet berstatus KRITIS dengan SR 92.87%."

        with patch.object(gen, "_call_llm", return_value=llm_output):
            state = gen.run(state)

        # Guard must NOT fire — count occurrences of the entity name
        count = state.insights.lower().count("telkomsel_wallet")
        assert count == 1, f"Expected 1 occurrence, got {count}"


# ========================================
# Test: PRIORITAS 3 — Recommendation synthesis domain constraints
# ========================================

class TestRecommendationSynthesisPromptDomain:
    """_build_recommendation_synthesis_prompt must enforce Finance & RA domain + 3-criteria format."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def _get_prompt(self, query="apa yang harus dilakukan?", segment="partners"):
        gen = self._gen()
        state = AgentState(query=query, database="financial_db")
        state.intent = {"category": "recommendation", "segment": segment}
        state.conversation_history = [{"query": "partner mana KRITIS?", "insights": "telkomsel_wallet SR 92.87% KRITIS."}]
        return gen._build_recommendation_synthesis_prompt(state)

    def test_persona_is_finance_ra(self):
        """Prompt must open with Finance & Revenue Assurance persona, not generic analyst."""
        prompt = self._get_prompt()
        assert "Finance & Revenue Assurance" in prompt

    def test_in_scope_actions_listed(self):
        """Prompt must enumerate in-scope Finance & RA actions."""
        prompt = self._get_prompt()
        assert "eskalasi" in prompt.lower()
        assert "SLA" in prompt
        assert "audit kontrak" in prompt.lower()

    def test_out_of_scope_actions_listed(self):
        """Prompt must explicitly prohibit marketing/UX/product actions."""
        prompt = self._get_prompt()
        assert "promosi" in prompt.lower()
        assert "OUT-OF-SCOPE" in prompt or "DILARANG" in prompt

    def test_no_escape_hatch_rule(self):
        """Rule 5 escape hatch (perlu diinvestigasi lebih lanjut) must be gone."""
        prompt = self._get_prompt()
        # Old escape hatch phrasing must not appear
        assert "perlu diinvestigasi lebih lanjut" not in prompt.lower()

    def test_prohibits_circular_recommendation(self):
        """Prompt must explicitly prohibit analisis/investigasi lebih lanjut as main recommendation."""
        prompt = self._get_prompt()
        assert "analisis" in prompt.lower() and "DILARANG" in prompt

    def test_three_criteria_required(self):
        """Prompt must require all 3 actionable criteria: tindakan, prioritas, dampak/risiko."""
        prompt = self._get_prompt()
        assert "(i)" in prompt
        assert "(ii)" in prompt
        assert "(iii)" in prompt

    def test_few_shot_correct_example_present(self):
        """Prompt must contain a BENAR (Finance & RA) recommendation example."""
        prompt = self._get_prompt()
        assert "BENAR" in prompt or "CONTOH BENAR" in prompt

    def test_few_shot_wrong_example_present(self):
        """Prompt must contain SALAH examples showing circular and out-of-scope patterns."""
        prompt = self._get_prompt()
        assert "SALAH" in prompt or "CONTOH SALAH" in prompt or "JANGAN TIRU" in prompt


# ========================================
# Test: PRIORITAS 4 poin 5 — Product MoM threshold exception
# ========================================

class TestProductSegmentThresholdException:
    """_build_segment_guide(products) must prohibit MoM verdict for individual products."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_product_guide_has_threshold_exception_header(self):
        """Product segment guide must include explicit THRESHOLD EXCEPTION note."""
        gen = self._gen()
        guide = gen._build_segment_guide("products")
        assert "THRESHOLD EXCEPTION" in guide or "threshold exception" in guide.lower()

    def test_product_guide_prohibits_per_product_verdict(self):
        """Product guide must explicitly prohibit assigning PERHATIAN/KRITIS to individual products."""
        gen = self._gen()
        guide = gen._build_segment_guide("products")
        assert "DILARANG" in guide
        assert "PERHATIAN" in guide
        assert "KRITIS" in guide

    def test_product_guide_requires_descriptive_language(self):
        """Product guide must instruct use of descriptive language without verdict per-product."""
        gen = self._gen()
        guide = gen._build_segment_guide("products")
        assert "deskriptif" in guide.lower()

    def test_partner_guide_unaffected(self):
        """Threshold exception must NOT appear in partner segment guide."""
        gen = self._gen()
        guide = gen._build_segment_guide("partners")
        assert "THRESHOLD EXCEPTION" not in guide

    def test_channel_guide_unaffected(self):
        """Threshold exception must NOT appear in channel segment guide."""
        gen = self._gen()
        guide = gen._build_segment_guide("channels")
        assert "THRESHOLD EXCEPTION" not in guide


# ========================================
# Test: PRIORITAS 4 poin 5 — threshold_override_block injection
# ========================================

class TestThresholdOverrideBlock:
    """_threshold_override_block must return non-empty only for products, injected in all prompts."""

    def _gen(self):
        with patch.object(InsightGenerator, "_init_client", return_value=("openai", MagicMock(), "gpt-4o")):
            return InsightGenerator()

    def test_products_returns_override(self):
        gen = self._gen()
        block = gen._threshold_override_block("products")
        assert block  # non-empty
        assert "DILARANG" in block
        assert "KRITIS" in block or "PERHATIAN" in block

    def test_non_products_returns_empty(self):
        gen = self._gen()
        for seg in ("partners", "channels", "transactions", "", "unknown"):
            assert gen._threshold_override_block(seg) == "", f"Expected empty for segment={seg!r}"

    def test_override_injected_in_single_step_prompt(self):
        """For products segment, single-step prompt must contain override block text."""
        gen = self._gen()
        state = AgentState(query="produk terbesar bulan ini?", database="financial_db")
        state.intent = {"category": "analysis", "segment": "products"}
        state.query_result = [{"entity": "GoPay", "total_trx": 1000000, "trx_pct_change": -25.0}]
        state.row_count = 1
        state.validated_sql = "SELECT entity, total_trx FROM ..."
        prompt = gen._build_single_step_prompt(state)
        assert "EXCEPTION PRODUK" in prompt or "exception produk" in prompt.lower()

    def test_override_absent_for_partner_single_step(self):
        """For partners segment, single-step prompt must NOT contain product override."""
        gen = self._gen()
        state = AgentState(query="partner terbesar bulan ini?", database="financial_db")
        state.intent = {"category": "analysis", "segment": "partners"}
        state.query_result = [{"entity": "dana", "trx_a": 1000000, "trx_pct_change": -5.0}]
        state.row_count = 1
        state.validated_sql = "SELECT entity, trx_a FROM ..."
        prompt = gen._build_single_step_prompt(state)
        assert "EXCEPTION PRODUK" not in prompt


    def test_early_product_warning_at_top_of_prompt(self):
        """For products segment, early warning must appear before SQL/data section."""
        gen = self._gen()
        state = AgentState(query="produk mana yang turun?", database="financial_db")
        state.intent = {"category": "analysis", "segment": "products"}
        state.query_result = [{"entity": "GoPay", "trx_pct_change": -22.7}]
        state.row_count = 1
        state.validated_sql = "SELECT ..."
        prompt = gen._build_single_step_prompt(state)
        warning_pos = prompt.find("ATURAN WAJIB UNTUK ANALISIS PRODUK")
        sql_pos = prompt.find("SQL EXECUTED")
        assert warning_pos >= 0, "Early product warning not found"
        assert warning_pos < sql_pos, "Warning must appear before data section"

    def test_product_threshold_table_excludes_mom_row(self):
        """Products segment threshold table must omit MoM Volume Growth row."""
        gen = self._gen()
        state = AgentState(query="produk mana yang turun?", database="financial_db")
        state.intent = {"category": "analysis", "segment": "products"}
        state.query_result = [{"entity": "GoPay", "trx_pct_change": -22.7}]
        state.row_count = 1
        state.validated_sql = "SELECT ..."
        prompt = gen._build_single_step_prompt(state)
        # Threshold table starts with "BUSINESS THRESHOLDS:"
        tbl_start = prompt.find("BUSINESS THRESHOLDS:")
        tbl_end   = prompt.find("\n\n", tbl_start) if tbl_start >= 0 else -1
        table_text = prompt[tbl_start:tbl_end] if tbl_start >= 0 else ""
        assert "| MoM Volume Growth" not in table_text, "MoM row must be excluded for products"
        assert "| Perubahan transaksi" not in table_text, "Perubahan transaksi row must be excluded"
        assert "| Success Rate" in table_text, "SR row must still be present"

