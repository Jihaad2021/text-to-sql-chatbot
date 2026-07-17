"""
Component 10: Insight Generator

Generates natural language insights from query results using Claude.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.validated_sql
    - state.query_result
    - state.row_count
    - state.is_multi_step (bool)
    - state.step_results (list[StepResult], for multi-step queries)
    - state.conversation_history (optional)

Writes to state:
    - state.insights (str)

Example:
    >>> generator = InsightGenerator()
    >>> state = AgentState(query="berapa total customer?")
    >>> state.query_result = [{"total": 100}]
    >>> state.row_count = 1
    >>> state = generator.run(state)
    >>> print(state.insights)
    "Terdapat 100 customer yang terdaftar dalam sistem."
"""

import json
import re
from datetime import datetime

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.client_profile import (
    render_client_identity_block,
    render_persona_header_block,
    render_persona_scope_block,
)
from src.utils.domain_entities import get_channel_keywords, get_partner_keywords, render_channel_groups_block
from src.utils.thresholds import get_sr_verdict_boundaries, render_thresholds_block

# Domain entity constants — computed once at import from domain_entities.yaml.
_CHANNEL_GROUPS_BLOCK = render_channel_groups_block()
_CLIENT_IDENTITY      = render_client_identity_block()
_PERSONA_HEADER       = render_persona_header_block()
_PERSONA_SCOPE        = render_persona_scope_block()
_SR_KRITIS, _SR_SEHAT = get_sr_verdict_boundaries()

# Verdict keywords used by the closing-paragraph guard.
_VERDICT_KEYWORDS: frozenset[str] = frozenset({"SEHAT", "PERHATIAN", "KRITIS"})

# Model used when quality_tier="deep". All other agents are unaffected.
_DEEP_MODEL = "gpt-4.1-mini"

_MONTH_ID = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _format_date_id(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'DD Nama_Bulan YYYY' in Indonesian."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {_MONTH_ID[d.month]} {d.year}"
    except ValueError:
        return date_str

# Chart.js-producing visual_block types — used to route per-block builders.
# Non-chart types (kpi_grid, anomaly_callout, data_table, ranking_table) are
# excluded from chart_configs entirely.
_CHARTJS_VISUAL_TYPES = {"line_chart", "bar_chart", "donut_chart", "diverging_bar_chart", "grouped_bar_chart"}

# Recommendation rules block — injected BEFORE SQL/RESULTS so the LLM processes
# the threshold-first ordering instruction before forming a volume-based approach.
_RECOMMENDATION_RULES_BLOCK = f"""
⚠️ ANALISIS REKOMENDASI — IKUTI TIGA LANGKAH INI SECARA BERURUTAN:

LANGKAH 1 — KLASIFIKASI (lakukan ini diam-diam, sebelum menulis output):
Untuk setiap baris data, tentukan statusnya:
  SR < {_SR_KRITIS}%         → KRITIS  (intervensi segera)
  {_SR_KRITIS}% ≤ SR < {_SR_SEHAT}%   → PERHATIAN  (monitoring ketat)
  SR ≥ {_SR_SEHAT}%         → SEHAT

LANGKAH 2 — URUTKAN berdasarkan status (bukan volume atau revenue):
  KRITIS (paling mendesak) → PERHATIAN → SEHAT

LANGKAH 3 — TULIS OUTPUT dalam format ini:

Partner yang paling membutuhkan perhatian berdasarkan tingkat keberhasilan transaksi.

## 🔴 KRITIS — Perlu Tindakan Segera
- **[nama_partner]**: SR **X,XX%** (standar **≥{_SR_SEHAT}%** | selisih **-Y,YY pp**) — [rekomendasi spesifik]

## 🟡 PERHATIAN — Perlu Monitoring Ketat
- **[nama_partner]**: SR **X,XX%** (standar **≥{_SR_SEHAT}%** | selisih **-Y,YY pp**) — [rekomendasi]

## 🟢 SEHAT — Pertahankan Performa
- **[nama_partner]**: SR **X,XX%** ✓

ATURAN KERAS:
✗ DILARANG mengurutkan berdasarkan total transaksi atau pendapatan
✗ DILARANG menyebut partner SEHAT sebagai yang "perlu diprioritaskan"
✗ DILARANG melewati satu partner tanpa mengklasifikasi SR-nya
"""

# Standard RULES/FORMAT/CONTOH block for non-recommendation single-step queries.
_STANDARD_RULES_AND_FORMAT_BLOCK = """
RULES:
1. Jawab pertanyaan literal terlebih dahulu — 1–2 kalimat singkat tanpa sub-judul
2. Lihat nama kolom di SQL untuk menentukan apakah itu transaksi, revenue, atau persentase
3. Setiap section setelah jawaban langsung: gunakan bullet points, BUKAN paragraf panjang

FORMAT OUTPUT — WAJIB DIIKUTI:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Bagian pembuka: 1–2 kalimat singkat langsung menjawab (tanpa sub-judul)
✓ Setiap section berikutnya:
   - Tulis ## Sub-Judul terlebih dahulu
   - Temuan ditulis sebagai BULLET POINTS (- ), bukan paragraf
   - Tiap bullet: maks 1–2 kalimat, langsung ke angka dan fakta
   - Boleh 1 kalimat intro sebelum bullet, tapi TIDAK LEBIH
✓ Angka kunci WAJIB di-bold: **28,4 juta**, **Rp 3,2 miliar**, **99,2%**
✓ Ranking → gunakan 1. 2. 3. (numbered list)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ DILARANG: paragraf >2 kalimat berturut-turut tanpa bullet
✗ DILARANG: blok kode SQL, backticks (```)
✗ DILARANG: nama kolom teknis (total_trx → "transaksi", net_revenue → "pendapatan bersih")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONTOH FORMAT YANG BENAR:
Total transaksi GoPay bulan April mencapai **12,3 juta transaksi**, lebih tinggi dari OVO.

## Perbandingan Utama
- GoPay: **12,3 juta transaksi** — naik **8%** dari Maret
- OVO: **10,1 juta transaksi** — turun **3%** dari Maret
- Selisih: GoPay unggul **2,2 juta transaksi (22% lebih tinggi)**

## Success Rate
- GoPay: **99,4%** — dalam batas normal (≥97%)
- OVO: **98,9%** — dalam batas normal (≥97%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# Late-position reinforcement for recommendation synthesis (threshold-first, not volume ranking).
# Injected after business_thresholds_block as a closing reminder.
_RECOMMENDATION_SYNTHESIS_INSTRUCTIONS = f"""
INSTRUKSI SYNTHESIS REKOMENDASI — WAJIB DIIKUTI (menggantikan urutan standar):

Langkah 1 — SCAN THRESHOLD: Periksa SETIAP baris data terhadap threshold resmi di atas.
  - SR < {_SR_KRITIS}%         → KRITIS
  - {_SR_KRITIS}% ≤ SR < {_SR_SEHAT}%   → PERHATIAN
  - SR ≥ {_SR_SEHAT}%         → SEHAT

Langkah 2 — URUTKAN berdasarkan tingkat keparahan, BUKAN volume atau revenue:
  KRITIS dulu → PERHATIAN → SEHAT (sebagai konteks saja)

Langkah 3 — SETIAP entitas WAJIB menyebutkan tiga hal:
  a) Angka aktual (contoh: SR **92,87%**)
  b) Threshold yang berlaku (contoh: threshold minimum **{_SR_SEHAT}%**)
  c) Selisih dari threshold (contoh: **-5,13 pp dari standar**)

FORMAT OUTPUT WAJIB:

## 🔴 KRITIS — Perlu Tindakan Segera
- **[nama_partner]**: SR **X,XX%** (standar **≥{_SR_SEHAT}%** | selisih **-Y,YY pp**) — [rekomendasi tindakan spesifik]

## 🟡 PERHATIAN — Perlu Monitoring Ketat
- **[nama_partner]**: SR **X,XX%** (standar **≥{_SR_SEHAT}%** | selisih **-Y,YY pp**) — [rekomendasi tindakan]

## 🟢 SEHAT — Referensi Performa Baik
- **[nama_partner]**: SR **X,XX%** ✓ — pertahankan performa

LARANGAN KERAS:
✗ DILARANG mengurutkan partner berdasarkan total_trx atau revenue
✗ DILARANG menjadikan partner dengan volume terbesar sebagai prioritas utama jika SR-nya ≥{_SR_SEHAT}%
✗ DILARANG melewati satu entitas pun tanpa mengecek threshold SR-nya
✗ DILARANG menyebut partner SEHAT sebagai yang perlu "diprioritaskan"
"""

# Shared number-to-float converter used by all chart builders.
# Returns None for non-numeric inputs so callers can distinguish 0 from "not a number".
def _to_num(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(',', '').replace(' ', ''))
        except ValueError:
            return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# Number formatting rules injected into every insight prompt — single source of truth.
_NUMBER_FORMAT_BLOCK = """CRITICAL — Number formatting rules:

TRANSACTION COUNTS (kolom: total_trx, success_trx, fail_trx, unique_users_daily, unique_users, unique_users_monthly):
  - INTEGER COUNTS — NEVER format as Rupiah
  - Under 1,000: "452 transaksi"
  - Under 1 million: "52.000 transaksi"
  - 1M–999M: "52,6 juta transaksi"
  - 1B+: "1,2 miliar transaksi"

REVENUE / MONEY (kolom: total_revenue, net_revenue, platform_fee, net_gap, total_net_revenue, total_platform_fee):
  - Rupiah amounts — format with Rp prefix
  - Under 1 million: "Rp 500.000"
  - 1M–999M: "Rp 252,3 juta"
  - 1B+: "Rp 1,2 miliar"

PERCENTAGES (kolom: success_rate_pct, avg_success_rate): format as "92,5%"
"""

# Standard analysis block for non-recommendation single-step queries.
_GENERAL_ANALYSIS_BLOCK = """
RANKED DATA: bullet tiap entitas — nilai, persentase kontribusi, delta vs periode lain
TIME SERIES: bullet per temuan penting — puncak, lembah, lonjakan tiba-tiba (>30%)

PERIODE PARSIAL — wajib disebutkan jika ada:
- Jika data mencakup bulan yang belum selesai (misalnya Juni 2026 baru ~20 hari), SELALU cantumkan:
  "data Juni mencakup X hari pertama" sehingga pembaca tidak salah membandingkan dengan bulan penuh.
- Saat membandingkan bulan parsial vs bulan penuh, gunakan rata-rata harian untuk normalisasi,
  bukan total absolut langsung.

If no results (0 rows):
- Explain what data is available
- Suggest alternative queries or time ranges
"""


class InsightGenerator(LLMBaseAgent):
    """
    Generate natural language insights from SQL query results.

    Produces conversational Indonesian insights that:
    - Directly answer the user's question
    - Format numbers properly (juta/miliar)
    - Highlight key findings
    - Handle empty results gracefully
    """

    def __init__(self) -> None:
        super().__init__(name="insight_generator", version="1.0.0")

    # Intents that benefit from extended thinking (deeper reasoning before answering)
    _THINKING_INTENTS = {
        "root_cause_analysis",
        "complex_analytics",
        "ranking_analysis",
        "anomaly_detection",
    }

    # Threshold metrics excluded for product segment: MoM/transaction-change thresholds
    # were calibrated at partner/channel level — per-product individual volatility makes
    # them meaningless. Removing them from the prompt prevents false PERHATIAN/KRITIS.
    _PRODUCT_EXCLUDED_THRESHOLDS: frozenset[str] = frozenset({
        "MoM Volume Growth",
        "Perubahan transaksi",
    })

    def execute(self, state: AgentState) -> AgentState:
        """
        Generate insights from query results.

        Args:
            state: Pipeline state with query_result and row_count

        Returns:
            Updated state with state.insights and state.chart_config
        """
        # ── Out-of-range guard ────────────────────────────────────────────
        # Period starts after data_end_date → skip LLM entirely, return deterministic message.
        if state.query_out_of_range and state.out_of_range_latest:
            latest_fmt = _format_date_id(state.out_of_range_latest)
            state.insights = (
                f"Data terbaru yang tersedia adalah sampai **{latest_fmt}**. "
                f"Belum ada data untuk periode yang diminta."
            )
            # Defense-in-depth: clear any data that AnalyticsAgent or SQL pipeline may have
            # written to state before the guard fired, so the UI never renders a data table
            # alongside the guard message (hasData=False → _buildFlatBody skips table).
            state.query_result = []
            state.row_count = 0
            self.log(
                f"Skipped LLM — query_out_of_range=True, latest={state.out_of_range_latest}",
                level="warning",
            )
            return state

        plan = state.layout_plan or {}

        # Option B guard: remove any layout section whose title mentions "distribusi" /
        # "distribution" when get_distribution was not actually called. Prevents
        # InsightGenerator from filling a "Distribusi" section with compare_periods data.
        if state.tool_results and state.layout_plan:
            called_tools = {tr.tool_name for tr in state.tool_results}
            if "get_distribution" not in called_tools:
                state.layout_plan["narrative_sections"] = [
                    s for s in state.layout_plan.get("narrative_sections", [])
                    if not any(
                        kw in (s.get("title") or "").lower()
                        for kw in ("distribusi", "distribution")
                    )
                ]
                plan = state.layout_plan

        try:
            prompt = self._build_prompt(state)
            intent = getattr(state, "intent", None)
            intent_category = (
                intent.get("category", "") if isinstance(intent, dict) else (intent or "")
            )
            use_thinking = (
                self.provider == "anthropic"
                and intent_category in self._THINKING_INTENTS
            )
            # Compute effective model per-request without mutating self.model —
            # InsightGenerator is a singleton shared across all concurrent requests.
            effective_model: str | None = None
            if getattr(state, "quality_tier", "standard") == "deep":
                effective_model = _DEEP_MODEL
                self.log(f"quality_tier=deep → using model '{_DEEP_MODEL}' (default: '{self.model}')")
            insights = self._call_llm(
                prompt, max_tokens=1500, temperature=0.3, use_thinking=use_thinking,
                model=effective_model,
            )
            self._record_token_usage(state, model=effective_model or self.model)
            # Guard: if ResponsePlanner asked for brief, strip any extra sections
            # the LLM added beyond the direct answer (defense-in-depth after context trim).
            if plan.get("response_length") == "brief":
                insights = self._truncate_brief_sections(insights)

            # Verdict closing guard: detailed tool-results responses must end with an
            # explicit SEHAT/PERHATIAN/KRITIS label. If the LLM omitted it despite
            # PENUTUP WAJIB, derive verdict deterministically and append one sentence.
            if (
                state.tool_results
                and plan.get("response_length") == "detailed"
                and not self._has_explicit_verdict_in_closing(insights)
            ):
                verdict = self._derive_verdict_from_tool_results(state.tool_results)
                insights = insights.rstrip() + f"\n\nVerdict keseluruhan: **{verdict}**."
                self.log(
                    f"Verdict guard appended '{verdict}' — closing lacked explicit verdict",
                    level="warning",
                )

            state.insights = insights
            state.insights_sections = self._parse_insight_sections(insights)

            # BUG 2 guard: deterministically append any KRITIS entities that the LLM
            # omitted from a recommendation insight — safety net so critical partners/
            # channels are never silently missing from the output.
            if (
                isinstance(state.intent, dict)
                and state.intent.get("category") == "recommendation"
                and state.query_result
            ):
                missing_kritis = self._find_missing_kritis_entities(
                    state.query_result, insights
                )
                if missing_kritis:
                    lines = ["\n\n## 🔴 KRITIS — Entitas Berikut Belum Dibahas"]
                    for entity, sr in missing_kritis:
                        lines.append(f"- **{entity}**: SR {sr:.2f}% — di bawah ambang KRITIS (95%)")
                    kritis_block = "\n".join(lines)
                    state.insights = insights + kritis_block
                    self.log(
                        f"KRITIS guard appended {len(missing_kritis)} missing entity(ies): "
                        + ", ".join(e for e, _ in missing_kritis),
                        level="warning",
                    )

            # FIX 5 monitoring: warn when insight may use user's raw query number
            # instead of actual row_count from tool results.
            if state.tool_results:
                for _tr in state.tool_results:
                    if _tr.tool_name == "get_distribution" and getattr(_tr, "actual_entity_count", 0) > 0:
                        _req_match = re.search(r'\b(\d{2,5})\b', state.query or "")
                        if _req_match:
                            _req_n = int(_req_match.group(1))
                            if 2000 <= _req_n <= 2099:
                                continue  # year digit in query, not a requested row count
                            if _req_n != _tr.row_count and str(_req_n) in insights:
                                self.log(
                                    f"Insight may use user's query number ({_req_n}) "
                                    f"instead of actual row_count ({_tr.row_count}); "
                                    f"actual_entity_count={_tr.actual_entity_count}",
                                    level="warning",
                                )

            if use_thinking:
                self.log(f"Extended thinking used for intent: {intent_category}")
            sections_found = len(state.insights_sections) if state.insights_sections else 0
            self.log(f"Insights generated ({len(insights)} chars, {sections_found} section(s) parsed)")

        except Exception as e:
            self.log(f"LLM insight failed, using fallback: {e}", level="warning")
            state.insights = self._fallback(state)
            state.insights_sections = None

        # ── Chart configs ──────────────────────────────────────────────
        if not plan.get("needs_visual", True):
            # ResponsePlanner determined no visual is useful for this response
            state.chart_configs = []
            state.chart_config  = None
            self.log("needs_visual=false — chart build skipped")
        else:
            state.chart_configs = self._build_chart_configs_with_anchors(state, plan)
            state.chart_config  = state.chart_configs[0] if state.chart_configs else None
            if state.chart_configs:
                self.log(f"Charts built: {len(state.chart_configs)} config(s)")

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Branch to the right prompt based on state."""
        if state.recommendation_from_history:
            return self._build_recommendation_synthesis_prompt(state)
        if state.tool_results:
            return self._build_tool_results_prompt(state)
        if state.is_multi_step and state.step_results:
            return self._build_multi_step_prompt(state)
        return self._build_single_step_prompt(state)

    # Max rows shown to LLM. 100 covers full partner×month matrices (25 partners × 4 months = 100)
    # without blowing the context budget.
    _MAX_PROMPT_ROWS = 100

    def _build_single_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt for a single-step query."""
        if state.query_result and state.row_count > 0:
            results_text = json.dumps(
                state.query_result[:self._MAX_PROMPT_ROWS], indent=2, default=str
            )
            if state.row_count > self._MAX_PROMPT_ROWS:
                hidden = state.row_count - self._MAX_PROMPT_ROWS
                results_text += (
                    f"\n\n⚠️ DATA TERPOTONG: {hidden} baris tidak ditampilkan "
                    f"(total {state.row_count} baris). "
                    f"JANGAN menyebut angka spesifik (min, max, ranking) dari baris yang tidak terlihat. "
                    f"Gunakan deskripsi tren umum saja untuk bagian yang terpotong."
                )
        else:
            results_text = "No results returned"

        response_length = (state.layout_plan or {}).get("response_length", "standard")
        has_context     = bool(state.context_snapshot)
        # Apply channel-dimension partner strip first, then brief trim on top.
        _ctx = self._ctx_for_segment(state)
        if response_length == "brief" and _ctx:
            _ctx = self._trim_context_for_brief(_ctx)

        segment        = (
            (state.intent or {}).get("segment")
            if isinstance(state.intent, dict)
            else None
        ) or self._detect_segment(state.query)

        history_block  = self._build_history_block(state.conversation_history)
        context_block  = f"\n{_ctx}\n" if _ctx else ""
        layout_block   = self._build_layout_block(state.layout_plan)
        segment_guide             = self._build_segment_guide(segment, state.product_count)
        business_thresholds_block = self._thresholds_for_segment(segment)
        threshold_override        = self._threshold_override_block(segment, state.product_count)
        early_product_warning     = self._early_product_warning(segment)
        intent_category = (
            (state.intent or {}).get("category", "")
            if isinstance(state.intent, dict)
            else ""
        )
        if intent_category == "recommendation":
            # For recommendation: inject rules BEFORE data so the LLM processes
            # threshold-first ordering before it sees any volume numbers.
            early_rules_block = _RECOMMENDATION_RULES_BLOCK
            late_rules_block = ""
            late_synthesis_block = _RECOMMENDATION_SYNTHESIS_INSTRUCTIONS
            general_analysis_block = ""
        else:
            early_rules_block = ""
            late_rules_block = _STANDARD_RULES_AND_FORMAT_BLOCK
            late_synthesis_block = ""
            general_analysis_block = _GENERAL_ANALYSIS_BLOCK

        elaboration_block = self._build_single_elaboration(response_length, has_context)

        return f"""{_CLIENT_IDENTITY}. Generate insights in conversational Indonesian.
{early_product_warning}{context_block}{history_block}
USER QUESTION: "{state.query}"

{elaboration_block}
{early_rules_block}
SQL EXECUTED:
{state.validated_sql}

RESULTS ({state.row_count} rows):
{results_text}

{_NUMBER_FORMAT_BLOCK}{late_rules_block}

DATA INTEGRITY — ANTI-HALLUCINATION (wajib diikuti):
- Gunakan angka dari RESULTS atau dari CONTEXT SNAPSHOT — keduanya valid
- DILARANG mengarang angka yang tidak ada di salah satu dari keduanya
- Jika data terpotong, JANGAN sebut nilai min/max yang tidak bisa diverifikasi

METODOLOGI ANALISIS — ikuti urutan ini:
1. IDENTIFIKASI → dimensi apa? (volume / revenue / SR / growth / konsentrasi / risiko)
2. AMBIL DATA → gunakan angka dari RESULTS + CONTEXT SNAPSHOT
3. HITUNG SINYAL → perubahan %, selisih absolut, ranking, anomali
4. BERI VERDICT → SEHAT / PERHATIAN / KRITIS berdasarkan threshold di bawah

{business_thresholds_block}{threshold_override}{late_synthesis_block}{general_analysis_block}
{segment_guide}{layout_block}Your insights in Indonesian:"""

    def _build_tool_results_block(self, tool_results: list) -> str:
        """Format AnalyticsAgent tool call results for the investigation prompt.

        Shows each tool's result separately so the LLM can reason per-tool
        rather than getting a heterogeneous row soup.
        """
        lines = []
        for i, tr in enumerate(tool_results, 1):
            if tr.row_count == 0 or not tr.data:
                lines.append(f"TOOL {i} — {tr.tool_name}: {tr.description}")
                lines.append("Status: returned 0 rows — no data available for this tool")
                lines.append("")
            else:
                preview = json.dumps(tr.data[:15], indent=2, default=str)
                lines.append(f"TOOL {i} — {tr.tool_name}: {tr.description}")
                lines.append(f"SQL: {tr.sql_or_params}")
                actual = getattr(tr, "actual_entity_count", 0)
                count_note = f", actual_entity_count={actual}" if actual > 0 else ""
                lines.append(f"Results ({tr.row_count} rows{count_note}):")
                # Partial-display flag: fewer rows shown than entities available.
                if actual > tr.row_count:
                    lines.append(
                        f"⚠️ PARTIAL DISPLAY: Hanya {tr.row_count} dari {actual} entitas yang "
                        f"tersedia ditampilkan. Insight WAJIB menyebutkan ini secara eksplisit, "
                        f"contoh: 'ditampilkan {tr.row_count} dari {actual} produk teratas'."
                    )
                # Cumulative share: computed deterministically from returned rows.
                cum_trx = getattr(tr, "cumulative_trx_share_pct", 0.0)
                cum_rev = getattr(tr, "cumulative_rev_share_pct", 0.0)
                if cum_trx > 0 or cum_rev > 0:
                    lines.append(
                        f"CUMULATIVE SHARE (dihitung dari {tr.row_count} baris di atas): "
                        f"trx_share={cum_trx}%, rev_share={cum_rev}%"
                    )
                lines.append(preview)
                lines.append("")
        return "\n".join(lines)

    def _build_tool_results_prompt(self, state: AgentState) -> str:
        """Build insight prompt for analytics queries with structured tool call results.

        Used when state.tool_results is non-empty (AnalyticsAgent path).
        Presents each tool's result with its own label so the LLM can
        reason per-tool, unlike the old flat-concat approach.
        """
        history_block             = self._build_history_block(state.conversation_history)
        tools_block               = self._build_tool_results_block(state.tool_results)
        _ctx                      = self._ctx_for_segment(state)
        context_block             = f"\n{_ctx}\n" if _ctx else ""
        layout_block      = self._build_layout_block(state.layout_plan)
        segment = (
            (state.intent or {}).get("segment")
            if isinstance(state.intent, dict)
            else None
        ) or self._detect_segment(state.query)
        business_thresholds_block = self._thresholds_for_segment(segment)
        threshold_override        = self._threshold_override_block(segment, state.product_count)
        segment_guide             = self._build_segment_guide(segment, state.product_count)
        early_product_warning     = self._early_product_warning(segment)

        response_length   = (state.layout_plan or {}).get("response_length", "standard")
        has_context       = bool(state.context_snapshot)
        elaboration_block = self._build_multi_elaboration(response_length, has_context)

        # Build mandatory-findings block: covers both partial-display AND cumulative share.
        # Both findings must appear in the insight when present; they are complementary,
        # not mutually exclusive — show "20 dari 882" AND "20 ini = X% total".
        partial_display_block = ""
        for _tr in (state.tool_results or []):
            _actual   = getattr(_tr, "actual_entity_count", 0)
            _cum_trx  = getattr(_tr, "cumulative_trx_share_pct", 0.0)
            _cum_rev  = getattr(_tr, "cumulative_rev_share_pct", 0.0)
            _dim      = getattr(_tr, "dimension", "") or "entitas"
            _row      = _tr.row_count
            _has_partial  = _actual > _row
            _has_cum_share = _cum_trx > 0 or _cum_rev > 0

            if not (_has_partial or _has_cum_share):
                continue

            mandatory_lines = [
                "⚠️ MANDATORY FINDINGS — WAJIB muncul di insight, angka TIDAK BOLEH diubah:\n",
            ]
            if _has_partial:
                mandatory_lines.append(
                    f"  [PARTIAL] Dari {_actual} {_dim} yang tersedia di database, "
                    f"ditampilkan {_row} teratas. "
                    f"Sebutkan: \"ditampilkan {_row} dari {_actual} {_dim}\".\n"
                )
            if _has_cum_share:
                mandatory_lines.append(
                    f"  [KONSENTRASI] {_row} {_dim} teratas ini merepresentasikan "
                    f"{_cum_trx}% dari total transaksi dan {_cum_rev}% dari total revenue. "
                    f"Sebutkan angka ini verbatim.\n"
                )
            mandatory_lines.append(
                "  Kedua temuan di atas HARUS muncul di paragraf pertama atau kedua insight.\n\n"
            )
            partial_display_block = "".join(mandatory_lines)
            break

        return f"""{_CLIENT_IDENTITY}.
{early_product_warning}{context_block}{history_block}
USER QUESTION: "{state.query}"

{elaboration_block}

INVESTIGATION TOOLS EXECUTED:

{tools_block}

{_NUMBER_FORMAT_BLOCK}
{business_thresholds_block}{threshold_override}

DATA INTEGRITY — ANTI-HALLUCINATION (wajib diikuti):
- HANYA gunakan angka yang BENAR-BENAR muncul di tool results di atas
- DILARANG mengarang atau menginterpolasi angka spesifik
- Setiap klaim kausal HARUS didukung angka konkret dari tool result
- Jika ada outlier >50% dari rata-rata, sorot secara eksplisit
- ENTITY COUNT RULE: DILARANG mengklaim jumlah entitas dari angka yang disebut user (contoh: user minta "top 1000 produk" → JANGAN tulis "1000 produk"). WAJIB gunakan row_count aktual yang tertulis di header "Results (N rows)" di atas. Jika actual_entity_count tersedia, boleh tambahkan konteks: "menampilkan N dari M entitas".
- PARTIAL DISPLAY RULE: Jika ada pesan "⚠️ PARTIAL DISPLAY" di tool results, insight WAJIB menyebutkan secara eksplisit bahwa hanya sebagian yang ditampilkan. DILARANG menulis seolah-olah semua entitas sudah tercakup.

FORMAT OUTPUT — gunakan markdown untuk struktur yang jelas:
- Mulai dengan jawaban langsung atas pertanyaan utama (penyebab utama / verdict)
- Gunakan ## untuk setiap sub-topik investigasi
- Gunakan **teks** untuk bold angka kunci
- Gunakan - untuk bullet list
- JANGAN menyertakan blok kode SQL, backticks triple (```), atau teks teknis
- Bahasa Indonesia

{partial_display_block}SYNTHESIS RULES:
1. Lead with the direct causal answer to the question
2. Quote key numbers from each relevant tool result with correct formatting
3. Cross-reference findings across tools to build a causal chain
4. Acknowledge if a tool returned 0 rows or inconclusive data
5. Panjang jawaban proporsional dengan jumlah tool dan temuan — jangan potong jika ada bukti penting

{segment_guide}{layout_block}Your insights in Indonesian:"""

    def _build_multi_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt that synthesises all step results."""
        history_block = self._build_history_block(state.conversation_history)
        steps_block   = self._build_steps_block(state.step_results)
        _ctx          = self._ctx_for_segment(state)
        context_block = f"\n{_ctx}\n" if _ctx else ""
        layout_block = self._build_layout_block(state.layout_plan)
        segment = (
            (state.intent or {}).get("segment")
            if isinstance(state.intent, dict)
            else None
        ) or self._detect_segment(state.query)
        business_thresholds_block = self._thresholds_for_segment(segment)
        threshold_override        = self._threshold_override_block(segment, state.product_count)
        segment_guide             = self._build_segment_guide(segment, state.product_count)
        early_product_warning     = self._early_product_warning(segment)

        response_length   = (state.layout_plan or {}).get("response_length", "standard")
        has_context       = bool(state.context_snapshot)
        elaboration_block = self._build_multi_elaboration(response_length, has_context)

        return f"""{_CLIENT_IDENTITY}.
{early_product_warning}{context_block}{history_block}
USER ORIGINAL QUESTION: "{state.query}"

{elaboration_block}

ANALYSIS STEPS EXECUTED:

{steps_block}

{_NUMBER_FORMAT_BLOCK}
COMPARISON INSTRUCTIONS — when multiple steps represent two groups being compared:
1. Compute the absolute difference between the two groups
2. Compute the ratio (e.g. "X kali lipat lebih tinggi")
3. Compute the percentage change: ((A - B) / B) * 100
4. State clearly which group is higher/lower
5. Do NOT skip the math — calculate it yourself from the raw numbers in the step results

{business_thresholds_block}{threshold_override}

DATA INTEGRITY — ANTI-HALLUCINATION (wajib diikuti):
- HANYA gunakan angka yang BENAR-BENAR muncul di step results di atas
- DILARANG mengarang atau menginterpolasi angka spesifik
- Selalu sebutkan nilai TERTINGGI dan TERENDAH jika data diurutkan
- Jika ada outlier >50% dari rata-rata, sorot secara eksplisit

FORMAT OUTPUT — gunakan markdown untuk struktur yang jelas:
- Mulai dengan jawaban langsung atas pertanyaan utama
- Gunakan ## untuk setiap sub-topik atau analisis per tahap
- Gunakan **teks** untuk bold angka kunci
- Gunakan - untuk bullet list, 1. untuk ranking
- JANGAN menyertakan blok kode SQL, backticks triple (```), atau teks teknis
- Bahasa Indonesia

SYNTHESIS RULES:
1. Lead with the direct answer to the original question
2. Show the key numbers from each step with correct formatting
3. State the comparison result with computed ratio or percentage
4. Elaborasi: tambahkan konteks tren, outlier, atau implikasi bisnis yang relevan dari data yang ada
5. If a step has 0 rows or failed, acknowledge it briefly and work with the available data
6. Panjang jawaban proporsional dengan data — tidak perlu dipotong jika ada temuan penting

{segment_guide}{layout_block}Your insights in Indonesian:"""

    def _truncate_brief_sections(self, text: str) -> str:
        """Post-processing guard for brief responses.

        If the LLM added any <!-- SECTION:sN --> markers despite the brief
        instruction, truncate everything from the first marker onward.
        The direct answer always appears before any section marker.
        """
        import re
        m = re.search(r'<!-- SECTION:\w+ -->', text)
        if m is None:
            return text  # already compliant
        truncated = text[:m.start()].rstrip()
        all_markers = re.findall(r'<!-- SECTION:\w+ -->', text)
        self.log(
            f"brief guard: truncated {len(all_markers)} extra section(s) added by LLM",
            level="warning",
        )
        return truncated

    def _trim_context_for_brief(self, ctx: str) -> str:
        """Strip partner/product/channel detail from context_snapshot for brief prompts.

        Keeps only the first 3 blank-line-separated blocks:
        header → monthly overview → MoM section.
        Appending a note so the LLM knows the snapshot is intentionally short.
        """
        blank_count = 0
        lines: list[str] = []
        for line in ctx.splitlines():
            if line.strip() == "":
                blank_count += 1
                if blank_count >= 3:
                    lines.append("[detail partner/produk/channel dihilangkan — query brief]")
                    break
            lines.append(line)
        return "\n".join(lines)

    # ── BUG 2: deterministic KRITIS entity guard ──────────────────────────
    # Column names to probe for success rate and entity name in query_result rows.
    _SR_COLS: tuple[str, ...] = ("success_rate_pct", "avg_success_rate", "sr")
    _ENTITY_COLS: tuple[str, ...] = ("partner_group", "channel", "product_name")

    def _find_missing_kritis_entities(
        self,
        query_result: list[dict],
        insights: str,
    ) -> list[tuple[str, float]]:
        """Return (entity_name, sr) pairs that are KRITIS (<95%) but absent from insights."""
        missing: list[tuple[str, float]] = []
        insights_lower = insights.lower()
        for row in query_result:
            sr_val: float | None = None
            for col in self._SR_COLS:
                if col in row and row[col] is not None:
                    try:
                        sr_val = float(row[col])
                    except (TypeError, ValueError):
                        pass
                    break
            if sr_val is None or sr_val >= 95.0:
                continue
            entity: str | None = None
            for col in self._ENTITY_COLS:
                if col in row and row[col]:
                    entity = str(row[col])
                    break
            if entity and entity.lower() not in insights_lower:
                missing.append((entity, sr_val))
        return missing

    # ── Verdict closing guard ─────────────────────────────────────────────────

    def _has_explicit_verdict_in_closing(self, text: str) -> bool:
        """Return True if SEHAT/PERHATIAN/KRITIS appears in the last ~3 sentences."""
        closing = text[-400:] if len(text) > 400 else text
        return any(kw in closing for kw in _VERDICT_KEYWORDS)

    def _derive_verdict_from_tool_results(self, tool_results: list) -> str:
        """Derive SEHAT/PERHATIAN/KRITIS from tool_results data.

        Priority: KRITIS > PERHATIAN > SEHAT.
        Scans all rows in all tool results for SR values against module-level
        thresholds. Treats a non-empty detect_anomaly result as PERHATIAN when
        SR is otherwise clean.
        """
        _SR_COL_NAMES = ("success_rate_pct", "avg_success_rate", "sr_pct", "sr")
        has_anomaly = False
        worst_sr: float | None = None

        for tr in tool_results:
            if tr.tool_name == "detect_anomaly" and tr.row_count > 0:
                has_anomaly = True
            for row in (tr.data or []):
                for col in _SR_COL_NAMES:
                    val = row.get(col)
                    if val is None:
                        continue
                    try:
                        sr = float(val)
                        if worst_sr is None or sr < worst_sr:
                            worst_sr = sr
                    except (TypeError, ValueError):
                        pass

        if worst_sr is not None and worst_sr < _SR_KRITIS:
            return "KRITIS"
        if worst_sr is not None and worst_sr < _SR_SEHAT:
            return "PERHATIAN"
        if has_anomaly:
            return "PERHATIAN"
        return "SEHAT"

    def _early_product_warning(self, segment: str) -> str:
        """Return a strong preamble injected at the TOP of the prompt for product segment.

        Position matters: instructions at the start of a prompt carry more weight than
        instructions buried after data blocks. For gpt-4o-mini, even with the MoM threshold
        row removed, the model's training priors still generate KRITIS/PERHATIAN verdicts for
        large per-product MoM swings. This preamble pre-empts that behaviour.
        """
        if segment != "products":
            return ""
        return (
            "\n⛔ ATURAN WAJIB UNTUK ANALISIS PRODUK:\n"
            "DILARANG KERAS menggunakan kata KRITIS atau PERHATIAN untuk menggambarkan\n"
            "perubahan volume MoM produk individual — tidak peduli seberapa besar % perubahannya.\n"
            "Gunakan HANYA bahasa deskriptif: 'GoPay turun 22,7% MoM', 'OVO naik 5%'.\n"
            "Verdict SEHAT/PERHATIAN/KRITIS HANYA boleh untuk: konsentrasi revenue portofolio\n"
            "keseluruhan, atau SR yang benar-benar di bawah threshold.\n\n"
        )

    def _thresholds_for_segment(self, segment: str) -> str:
        """Return thresholds block with product-level volume metrics excluded for 'products' segment."""
        if segment == "products":
            return render_thresholds_block(exclude_metrics=self._PRODUCT_EXCLUDED_THRESHOLDS)
        return render_thresholds_block()

    def _threshold_override_block(self, segment: str, product_count: int = 0) -> str:
        """Return a strong inline override right after the thresholds block for product segment.

        The business thresholds (MoM Volume Growth, Perubahan transaksi) were calibrated at
        partner/channel level — they do NOT apply to individual product_name rows where
        natural promo-driven volatility makes the same %-change thresholds meaningless.
        Injecting this block immediately after render_thresholds_block() prevents the LLM from
        applying PERHATIAN/KRITIS to per-product MoM swings.
        """
        if segment != "products":
            return ""
        count = product_count or 882
        return (
            "\n⛔ EXCEPTION PRODUK — berlaku langsung setelah threshold di atas:\n"
            "Threshold 'MoM Volume Growth' dan 'Perubahan transaksi' TIDAK BERLAKU untuk produk individual.\n"
            f"Produk individual ({count} distinct product_name) mengalami fluktuasi MoM alami karena promo/musiman.\n"
            "DILARANG: tulis verdict KRITIS atau PERHATIAN untuk perubahan volume produk individual.\n"
            "WAJIB: gunakan bahasa deskriptif — 'GoPay turun 22,7% MoM' — tanpa verdict per-produk.\n"
            "Verdict keseluruhan (SEHAT/PERHATIAN/KRITIS) HANYA boleh berdasarkan konsentrasi revenue\n"
            "portofolio atau diversifikasi — BUKAN perubahan volume per-produk.\n"
        )

    def _strip_partner_section(self, ctx: str) -> str:
        """Remove the 'Top 5 partner' block from context_snapshot for channel queries.

        Partner MoM data (e.g. 'dana ↓5.6% [PERHATIAN]') bleeds into channel dimension
        answers when the same snapshot is injected unchanged — the LLM reports partner
        names as channels needing attention. Channel queries only need the channel
        distribution section; partner detail is irrelevant and harmful.
        """
        return re.sub(r"Top 5 partner bulan ini:.*?(?:\n\n|$)", "", ctx, flags=re.DOTALL)

    def _ctx_for_segment(self, state: AgentState) -> str:
        """Return context_snapshot with partner section stripped when segment is 'channels'.

        Single call site used by ALL four prompt builders so the same BUG 1 fix applies
        regardless of which prompt path (single-step, multi-step, tool-results, synthesis)
        the pipeline takes.
        """
        ctx = state.context_snapshot or ""
        if not ctx:
            return ctx
        segment = (
            (state.intent or {}).get("segment")
            if isinstance(state.intent, dict)
            else None
        ) or self._detect_segment(state.query)
        if segment == "channels":
            ctx = self._strip_partner_section(ctx)
        return ctx

    def _build_single_elaboration(self, response_length: str, has_context: bool) -> str:
        """Return the elaboration instruction block for single-step prompts."""
        _std = (
            "ELABORASI WAJIB — Jawaban harus minimal 4–5 kalimat. Jangan berhenti di satu fakta.\n"
            "Bahkan ketika RESULTS hanya berisi satu angka, WAJIB elaborasi menggunakan CONTEXT SNAPSHOT di atas.\n"
            "Jawab poin-poin berikut menggunakan struktur markdown (## sub-judul, **bold** angka):\n\n"
            "1. JAWAB LANGSUNG: sebutkan angkanya dengan format yang benar.\n"
            "2. KOMPARASI: bandingkan angka ini dengan data di CONTEXT SNAPSHOT (baseline harian, bulan berjalan, rata-rata). "
            "Hitung selisih atau persentase perubahan jika bisa. Angka dari CONTEXT SNAPSHOT boleh digunakan — itu data valid.\n"
            "3. POSISI: apakah angka ini tinggi, rendah, atau normal untuk konteks bisnis ini? Gunakan BUSINESS THRESHOLDS di bawah.\n"
            "4. IMPLIKASI: apa yang angka ini berarti — ada yang perlu diperhatikan? Tren apa yang terlihat?\n"
            "5. KONTEKS TAMBAHAN: sebutkan satu hal lain yang relevan (kontributor terbesar, anomali, periode parsial, dll) "
            "jika ada di data atau context.\n"
            "DILARANG mengarang angka yang tidak ada di RESULTS maupun CONTEXT SNAPSHOT."
        )
        if response_length == "brief":
            return (
                "PANJANG JAWABAN (brief): jawab dalam 1–2 kalimat — angka utama dan verdict SEHAT/PERHATIAN/KRITIS. "
                "Tidak perlu elaborasi, komparasi, atau konteks tambahan.\n"
                "DILARANG mengarang angka yang tidak ada di RESULTS maupun CONTEXT SNAPSHOT."
            )
        if response_length == "detailed" and has_context:
            return (
                _std + "\n"
                "6. KONTEKS HISTORIS: mengacu pada CONTEXT SNAPSHOT, jelaskan bagaimana kondisi ini dibandingkan "
                "dengan pola historis yang lebih luas — tren multi-bulan, perubahan baseline, atau posisi relatif "
                "terhadap periode sebelumnya."
            )
        return _std  # standard, or detailed without context snapshot

    def _build_multi_elaboration(self, response_length: str, has_context: bool) -> str:
        """Return the elaboration instruction block for multi-step prompts."""
        _std = (
            "ELABORASI PERTANYAAN — setelah menjawab pertanyaan utama, tambahkan konteks analitik yang relevan "
            "dari hasil langkah-langkah di bawah:\n"
            "- Bandingkan antar grup/periode jika ada dua step yang merepresentasikan dua sisi\n"
            "- Sebutkan kontributor dominan dan outlier yang signifikan\n"
            "- Berikan implikasi bisnis singkat: apakah kondisi ini perlu perhatian atau sudah normal?\n"
            "Gunakan threshold bisnis di bawah untuk kontekstualisasi. DILARANG mengarang angka."
        )
        # Closing paragraph required for detailed responses — wraps all sections with a
        # verdict summary. Not a recommendation (that's the "recommendation" intent domain),
        # just a concise synthesis so the answer doesn't end mid-data.
        _closing_detailed = (
            "\n\nPENUTUP WAJIB (tulis setelah semua section selesai, tanpa sub-judul):\n"
            "2–3 kalimat yang merangkum: (1) verdict keseluruhan SEHAT/PERHATIAN/KRITIS "
            "berdasarkan majority temuan di atas, (2) satu area yang paling memerlukan perhatian "
            "beserta angka konkretnya (jika ada). "
            "DILARANG menulis rekomendasi tindakan spesifik — hanya rangkuman temuan."
        )
        if response_length == "brief":
            return (
                "PANJANG JAWABAN (brief): jawab dalam 1–2 kalimat — bandingkan kedua periode/grup dengan angka "
                "konkret dan verdict SEHAT/PERHATIAN/KRITIS. Tidak perlu elaborasi tambahan.\n"
                "DILARANG mengarang angka yang tidak ada di step results di atas."
            )
        if response_length == "detailed" and has_context:
            return (
                _std
                + "\n- Tambahkan konteks historis: mengacu pada CONTEXT SNAPSHOT, jelaskan bagaimana temuan ini "
                "dibandingkan dengan pola historis multi-bulan atau baseline yang tersedia."
                + _closing_detailed
            )
        if response_length == "detailed":
            return _std + _closing_detailed
        return _std  # standard

    def _build_layout_block(self, plan: dict | None) -> str:
        """Convert layout_plan into prompt instructions for structured output."""
        if not plan:
            return ""

        sections = plan.get("narrative_sections", [])
        length   = plan.get("response_length", "standard")
        metrics  = plan.get("key_metrics", [])
        anomaly  = plan.get("anomaly_flag", False)

        length_map = {
            "brief":    "3–4 bullet per section",
            "standard": "4–6 bullet per section",
            "detailed": "5–8 bullet per section",
        }
        bullet_count = length_map.get(length, "4–6 bullet per section")

        lines = [
            "══════════════════════════════════════════",
            "WAJIB: IKUTI STRUKTUR BERIKUT — JANGAN ABAIKAN",
            "══════════════════════════════════════════",
            "PENTING — SECTION MARKERS:",
            "  Sebelum memulai setiap bagian yang memiliki sub-judul (bukan bagian pertama),",
            "  tulis marker berikut pada baris sendiri, sebelum sub-judul:",
            "      <!-- SECTION:sN -->",
            "  di mana N adalah nomor bagian (s2, s3, s4).",
            "  Bagian pertama (s1) TIDAK perlu marker — langsung tulis isinya.",
            "  Contoh:",
            "      Gopay memimpin dengan 45% share — Verdict: SEHAT",
            "      <!-- SECTION:s2 -->",
            "      ## Tren Volume",
            "      - Tren naik 12% MoM...",
            "══════════════════════════════════════════",
        ]
        for i, s in enumerate(sections, 1):
            sid   = s.get("id", f"s{i}")
            title = s.get("title")
            instr = s.get("instruction", "")
            if title:
                lines.append(f"  {i}. Tulis marker <!-- SECTION:{sid} --> lalu SUB-JUDUL: {title}")
                lines.append(f"     Format: bullet points (- ), {bullet_count}")
                lines.append(f"     Isi: {instr}")
            else:
                lines.append(f"  {i}. Langsung tulis 1–2 kalimat (tanpa sub-judul, tanpa marker): {instr}")

        if metrics:
            lines.append(f"\nMetrik yang HARUS di-bold: {', '.join(metrics)}")
        if anomaly:
            lines.append("⚑ WAJIB: ada anomali — tulis bullet khusus yang menjelaskan anomali beserta angkanya.")
        lines.append("══════════════════════════════════════════\n")

        return "\n".join(lines) + "\n"

    # Segment keywords for detection — partner/channel names from domain_entities.yaml.
    # Base non-entity keywords kept here; entity names injected from module-level helpers.
    _PARTNER_KW  = frozenset({"partner", "ekosistem partner", "mitra"} | get_partner_keywords())
    _PRODUCT_KW  = frozenset({"produk", "product", "pulsa", "paket", "internet", "konten", "portfolio produk"})
    _CHANNEL_KW  = frozenset({"channel", "saluran", "kanal"} | get_channel_keywords())
    _TXNKW       = frozenset({"transaksi", "volume", "revenue", "pendapatan", "sr", "success rate",
                    "arpu", "user", "pengguna", "harian", "mingguan", "tren", "anomali"})

    def _detect_segment(self, query: str) -> str:
        q = (query or "").lower()
        if any(w in q for w in self._PARTNER_KW):
            return "partners"
        if any(w in q for w in self._PRODUCT_KW):
            return "products"
        if any(w in q for w in self._CHANNEL_KW):
            return "channels"
        if any(w in q for w in self._TXNKW):
            return "transactions"
        return "general"

    def _build_segment_guide(self, segment: str, product_count: int = 0) -> str:
        """Return compact segment-specific answer pattern guidance."""
        count = product_count or 882
        guides: dict[str, str] = {
            "transactions": (
                "POLA JAWABAN — TRANSAKSI:\n"
                "- Selalu sebut: total volume, MoM growth %, rata-rata harian, SR.\n"
                "- Template pembuka: \"Volume [naik/turun] [X]%MoM — [N] transaksi, [D] hari — Verdict: [SEHAT/PERHATIAN/KRITIS]\"\n"
                "- Anomali: sebutkan hari spesifik jika |vol − mean| > 2× std dev.\n"
                "- SR: flag hanya jika di bawah 98%. Nilai ≥98% = SEHAT, tidak perlu komentar khusus.\n\n"
            ),
            "products": (
                "POLA JAWABAN — PRODUK:\n"
                "- Portfolio: hitung berapa produk tumbuh vs turun dari data, sebut top-5 share.\n"
                "- Konsentrasi revenue: Top-3 <50%=Terdiversifikasi, 50–70%=Moderat, >70%=Ketergantungan tinggi.\n"
                "- Produk turun: estimasi dampak revenue = |wow%| × total_revenue / 100.\n"
                "- Template pembuka: \"Portfolio [N] produk — [growing] tumbuh, [declining] turun — Verdict: [SEHAT/PERHATIAN/KRITIS]\"\n"
                "PENTING — THRESHOLD EXCEPTION untuk produk:\n"
                "Threshold MoM Volume Growth dan Perubahan transaksi di blok THRESHOLDS di atas\n"
                f"TIDAK BERLAKU untuk produk individual (ada {count} distinct product_name;\n"
                "volatilitas MoM alami per-produk jauh lebih tinggi dari partner/channel).\n"
                "DILARANG: assign verdict PERHATIAN/KRITIS berdasarkan fluktuasi MoM volume produk individual.\n"
                "WAJIB: gunakan bahasa deskriptif — \"produk X turun Y% MoM\" — TANPA verdict per-produk.\n"
                "Verdict keseluruhan (SEHAT/PERHATIAN/KRITIS) hanya boleh berdasarkan konsentrasi\n"
                "revenue portofolio atau diversifikasi, BUKAN fluktuasi volume per-produk individual.\n\n"
            ),
            "partners": (
                "POLA JAWABAN — PARTNER (5 dimensi health):\n"
                "1. Volume: avg MoM growth seluruh partner → threshold >0% SEHAT\n"
                "2. Konsentrasi: top-2 revenue share → <50% SEHAT, 50–70% PERHATIAN, >70% KRITIS\n"
                "3. SR: ada partner SR<95%? → 0=SEHAT, 1=PERHATIAN, ≥2=KRITIS\n"
                "4. Distribusi: >60% partner tumbuh=SEHAT, 40–60%=PERHATIAN, <40%=KRITIS\n"
                "5. Streak: 0–1 hari=SEHAT, 2–3=PERHATIAN, ≥4=KRITIS\n"
                "Majority verdict dari 5 dimensi = overall verdict. Sebut partner Watch/ALERT secara eksplisit.\n"
                "Template pembuka: \"Ekosistem [N] partner — Verdict: [SEHAT/PERHATIAN/KRITIS]\"\n\n"
            ),
            "channels": (
                "POLA JAWABAN — CHANNEL:\n"
                f"- Analisis per group lebih informatif: {_CHANNEL_GROUPS_BLOCK}.\n"
                "- Konsentrasi: satu group >60% = risiko ketergantungan tinggi.\n"
                "- Efisiensi: revenue/trx tinggi + share rendah = value-driven; share tinggi + rev/trx rendah = volume-driven.\n"
                "- Template pembuka: \"Channel [nama] mendominasi [X]% share — Verdict: [SEHAT/PERHATIAN/KRITIS]\"\n\n"
            ),
        }
        return guides.get(segment, "")

    def _build_steps_block(self, step_results: list) -> str:
        """Format step results for the multi-step prompt."""
        lines = []
        for step in step_results:
            if step.row_count == 0 or not step.data:
                lines.append(f"STEP {step.step_number}: {step.description}")
                lines.append("Status: FAILED or returned 0 rows — skip this step")
                lines.append("")
            else:
                preview = json.dumps(step.data[:10], indent=2, default=str)
                lines.append(f"STEP {step.step_number}: {step.description}")
                lines.append(f"SQL: {step.sql}")
                lines.append(f"Results ({step.row_count} rows):")
                lines.append(preview)
                lines.append("")
        return "\n".join(lines)

    def _build_synthesis_history_block(self, history: list[dict]) -> str:
        """Return full conversation history for recommendation synthesis.

        Unlike _build_history_block (which truncates insights to 200 chars for
        regular prompts), this version shows up to 2000 chars per turn so the
        LLM can synthesise actionable recommendations from complete prior findings.
        """
        if not history:
            return ""

        recent = history[-3:]
        lines = ["\nRECENT CONVERSATION (full detail untuk sintesis rekomendasi):"]
        for turn in recent:
            q   = turn.get("query", "")
            a   = turn.get("insights", "")
            cat = turn.get("intent_category", "")
            rc  = turn.get("row_count", 0)
            if q:
                label = f"[{cat}, {rc} rows] " if cat else ""
                lines.append(f"User: {label}{q}")
            if a:
                lines.append(f"Chatbot: {a[:2000]}{'...' if len(a) > 2000 else ''}")
        lines.append("")
        return "\n".join(lines)

    def _build_recommendation_synthesis_prompt(self, state: AgentState) -> str:
        """Build prompt for recommendation follow-up that synthesises from conversation history.

        No SQL was executed for this turn. The LLM must derive all recommendations
        exclusively from prior conversation turns.
        """
        history_block = self._build_synthesis_history_block(state.conversation_history)
        _ctx          = self._ctx_for_segment(state)
        context_block = f"\n{_ctx}\n" if _ctx else ""
        segment = (
            (state.intent or {}).get("segment")
            if isinstance(state.intent, dict)
            else None
        ) or self._detect_segment(state.query)
        thresholds         = self._thresholds_for_segment(segment)
        segment_guide      = self._build_segment_guide(segment, state.product_count)
        threshold_override = self._threshold_override_block(segment, state.product_count)

        return f"""{_PERSONA_HEADER}
{context_block}{history_block}
USER QUESTION: "{state.query}"

INSTRUKSI KHUSUS — SINTESIS REKOMENDASI DARI HISTORI:
Pertanyaan ini adalah follow-up dari analisis di atas. Tidak ada SQL baru yang dijalankan untuk turn ini.

WAJIB DIIKUTI — ANTI-HALUSINASI:
1. Sintesis rekomendasi HANYA dari data dan temuan yang BENAR-BENAR muncul di RECENT CONVERSATION di atas.
2. DILARANG mengarang angka baru, klaim baru, atau konteks yang tidak ada di percakapan sebelumnya.
3. DILARANG menyebut "data tidak tersedia" atau meminta data tambahan — data sudah ada di histori.
4. Setiap rekomendasi HARUS didukung kutipan angka/temuan konkret dari percakapan sebelumnya.

WAJIB DIIKUTI — DOMAIN & TINDAKAN:
5. Rekomendasi HARUS berupa tindakan konkret dalam domain Finance & RA:
   {_PERSONA_SCOPE}
6. DILARANG "lakukan analisis/investigasi lebih lanjut" sebagai rekomendasi utama.
   Data di histori sudah cukup untuk rekomendasi konkret. Kalau ada gap data yang benar-benar
   teridentifikasi, sebutkan SATU kalimat — bukan dijadikan item rekomendasi tersendiri.

WAJIB DIIKUTI — FORMAT SETIAP REKOMENDASI (3 kriteria):
Tiap item WAJIB mencakup:
(i) tindakan konkret — apa persisnya yang dilakukan dan kepada siapa
(ii) prioritas — kenapa ini lebih mendesak dari rekomendasi lain
(iii) dampak/risiko — apa yang terjadi kalau tidak ditindak

CONTOH BENAR (Finance & RA in-scope):
**Eskalasi telkomsel_wallet ke Partner Management hari ini**
SR 92.87% sudah 3 hari berturut-turut di bawah ambang KRITIS 95% (i).
Prioritas #1 karena SLA mensyaratkan minimal 95%; setiap hari yang terlewat berisiko memicu
klausa penalti kontrak (ii). Kalau tidak ditindak dalam 24 jam, potensi claim penalti dan
kerusakan hubungan komersial jangka panjang (iii).

CONTOH SALAH — JANGAN TIRU:
❌ "Lakukan analisis lebih mendalam untuk memahami root cause" — circular, data sudah ada
❌ "Tingkatkan promosi untuk mendorong volume GoPay" — marketing, out-of-scope RA
❌ "Perbaiki UX checkout untuk mengurangi drop-off" — product/UX, out-of-scope RA

{thresholds}{threshold_override}

FORMAT OUTPUT:
- Mulai dengan ringkasan situasi berdasarkan temuan di histori (1-2 kalimat)
- Lanjutkan dengan rekomendasi berurutan dari paling kritis:
  **1. [Judul tindakan konkret]**
  [tindakan (i)] | [kenapa prioritas (ii)] | [dampak kalau tidak ditindak (iii)]
  **2. [Judul tindakan konkret]** — ...
- Bahasa Indonesia

{segment_guide}Your insights in Indonesian:"""

    def _build_history_block(self, history: list[dict]) -> str:
        """Return formatted last 2 conversation turns, or empty string."""
        if not history:
            return ""

        recent = history[-2:]
        lines = ["\nRECENT CONVERSATION:"]
        for turn in recent:
            q = turn.get("query", "")
            a = turn.get("insights", "")
            if q:
                lines.append(f"Q: {q}")
            if a:
                lines.append(f"A: {a[:200]}{'...' if len(a) > 200 else ''}")
        lines.append("")
        return "\n".join(lines)

    # ── Chart config ──────────────────────────────────────────

    _CHART_COLORS = [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
        '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
    ]
    # Match style.css --pos / --danger so diverging bar colours are consistent
    # with SEHAT (green) / KRITIS (red) verdict badges used elsewhere in the UI.
    _COLOR_POS = '#0E8A55'
    _COLOR_NEG = '#E4002B'

    _TIME_KEYWORDS = {'date', 'month', 'week', 'year', 'day', 'hour',
                      'tanggal', 'bulan', 'minggu', 'tahun', 'jam', 'period', 'waktu'}
    _MAX_CHART_ROWS = 50

    def _build_chart_configs(self, state: AgentState) -> list[dict]:
        """Build a list of Chart.js configs from query results."""
        if state.is_multi_step and state.step_results:
            return self._charts_from_multi_step(state.step_results)

        data = state.query_result
        if not data or len(data) <= 1:
            return []

        cols         = list(data[0].keys())
        numeric_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
        text_cols    = [c for c in cols if c not in numeric_cols]

        if not numeric_cols:
            return []

        x_col   = text_cols[0] if text_cols else None
        is_time = x_col and any(kw in x_col.lower() for kw in self._TIME_KEYWORDS)
        labels  = [str(row.get(x_col, i)) for i, row in enumerate(data)] if x_col \
                  else [str(i + 1) for i in range(len(data))]

        # Downsample rather than silently dropping charts for large datasets.
        # Time-series: evenly-spaced indices preserve the trend shape.
        # Categorical: sort by first numeric col descending, keep top-N.
        if len(data) > self._MAX_CHART_ROWS:
            original_count = len(data)
            if is_time:
                n    = self._MAX_CHART_ROWS
                step = (original_count - 1) / (n - 1) if n > 1 else 1
                idxs = sorted({round(i * step) for i in range(n)})
                data = [data[i] for i in idxs]
            else:
                data = sorted(data, key=lambda r: _to_num(r.get(numeric_cols[0])) or 0, reverse=True)[:self._MAX_CHART_ROWS]
            labels = [str(row.get(x_col, i)) for i, row in enumerate(data)] if x_col \
                     else [str(i + 1) for i in range(len(data))]
            self.log(
                f"Chart data sampled: {original_count} → {len(data)} rows "
                f"({'even-interval time-series' if is_time else 'top-N by magnitude'})",
                level="warning",
            )

        def _is_pct_col(col: str) -> bool:
            low = col.lower()
            return any(kw in low for kw in ('_pct', 'rate', 'share', 'percent', 'ratio', '_mom', 'growth'))

        def _series_max(col: str) -> float:
            """Max absolute value across all data rows for a column."""
            vals = [abs(_to_num(row.get(col)) or 0.0) for row in data]
            return max(vals) if vals else 0.0

        configs: list[dict] = []

        # ── Semantic suffix-based grouping ────────────────────────────────
        # Tools like detect_anomaly and compare_periods use a consistent naming
        # convention ({metric}_target, {metric}_baseline_avg, {metric}_pct_change).
        # Grouping by suffix produces semantically coherent charts instead of
        # the accidental cross-category pairs caused by blind positional slicing
        # (e.g. the old code paired trx_pct_change with rev_target because they
        # happened to sit at indices 2 and 3).
        #
        # Priority order (most actionable first):
        #   1. *_pct_change  → primary chart  (all pct_change cols in ONE chart)
        #   2. *_target      → secondary chart (prefer over baseline)
        #   3. *_baseline_avg → secondary chart (if no target group)
        # Columns not placed in any chart are logged explicitly so production
        # monitoring can detect unexpected schema changes.
        #
        # Fallback: when NO column matches any suffix, use the original positional
        # pairing for non-tool data (get_trend, get_summary, plain SQL results).
        _SUFFIX_MAP: dict[str, str] = {
            'pct_change':   '_pct_change',
            'target':       '_target',
            'baseline_avg': '_baseline_avg',
            'share_pct':    '_share_pct',   # get_distribution schema: derivative share%, 0-100 scale
        }
        _sfx_groups: dict[str, list[str]] = {k: [] for k in _SUFFIX_MAP}
        for _c in numeric_cols:
            for _key, _sfx in _SUFFIX_MAP.items():
                if _c.endswith(_sfx):
                    _sfx_groups[_key].append(_c)
                    break

        _has_suffix = any(_sfx_groups.values())
        if _has_suffix:
            chart_groups: list[list[str]] = []
            _charted: set[str] = set()
            # Priority 1: *_pct_change → primary chart (compare_periods / detect_anomaly)
            if _sfx_groups['pct_change']:
                chart_groups.append(_sfx_groups['pct_change'])
                _charted.update(_sfx_groups['pct_change'])
            # Priority 2: *_share_pct → primary chart when no *_pct_change present.
            # get_distribution emits trx_share_pct / rev_share_pct alongside total_trx /
            # total_revenue.  Grouping the share cols together keeps them on a single
            # 0-100% Y-axis and avoids accidental dual-axis pairing with the absolute cols.
            if not _sfx_groups['pct_change'] and _sfx_groups['share_pct'] and len(chart_groups) < 2:
                chart_groups.append(_sfx_groups['share_pct'])
                _charted.update(_sfx_groups['share_pct'])
            # Priority 3: *_target preferred over *_baseline_avg (detect_anomaly secondary)
            if len(chart_groups) < 2:
                _secondary = _sfx_groups['target'] or _sfx_groups['baseline_avg']
                if _secondary:
                    chart_groups.append(_secondary)
                    _charted.update(_secondary)
            # Priority 4: unmatched absolute columns → fill remaining slot.
            # ONLY when *_share_pct was charted (get_distribution schema): after share_pct
            # takes slot 1, total_trx / total_revenue take slot 2.
            # Guard is required: for detect_anomaly/compare_periods the unmatched _a/_b cols
            # are raw period values handled by the grouped_bar_chart path — don't grab them.
            _unmatched = [c for c in numeric_cols if c not in _charted]
            if len(chart_groups) < 2 and _unmatched and _sfx_groups['share_pct']:
                chart_groups.append(_unmatched[:2])
                _charted.update(_unmatched[:2])
            # Warn about every numeric column not represented in any chart
            _not_charted = [c for c in numeric_cols if c not in _charted]
            if _not_charted:
                self.log(
                    f"Columns not represented in any chart (semantic groups filled 2 charts): {_not_charted}",
                    level="warning",
                )
        else:
            # No suffix patterns found — fall back to original positional pairing.
            chart_groups = [numeric_cols[i:i+2] for i in range(0, min(len(numeric_cols), 4), 2)]
            _n_fallback_charted = min(len(numeric_cols), 4)
            if len(numeric_cols) > _n_fallback_charted:
                _not_charted_fb = numeric_cols[_n_fallback_charted:]
                self.log(
                    f"Columns not represented in any chart (positional fallback, cap 4): {_not_charted_fb}",
                    level="warning",
                )

        for group in chart_groups[:2]:
            if is_time:
                chart_type = 'line'
            elif len(data) <= 6 and len(group) == 1:
                chart_type = 'doughnut'
            else:
                chart_type = 'bar'

            # Dual axis: type mismatch (pct vs absolute) OR >10× magnitude gap.
            # Type-mismatch: primary axis (y) = non-pct col, secondary (y1) = pct col.
            # Magnitude-gap: primary axis (y) = smaller series, secondary (y1) = larger series.
            # Both protect against one series flattening to ~0 when sharing the same Y scale.
            use_dual = False
            dual_primary_col: str | None = None  # col assigned to 'y' (primary / left axis)

            if len(group) == 2 and chart_type != 'doughnut':
                type_mismatch = _is_pct_col(group[0]) != _is_pct_col(group[1])
                maxes = [_series_max(c) for c in group]
                magnitude_gap = min(maxes) > 0 and (max(maxes) / min(maxes)) > 10

                if type_mismatch:
                    use_dual = True
                    # non-pct col → primary axis (y)
                    dual_primary_col = group[0] if not _is_pct_col(group[0]) else group[1]
                elif magnitude_gap:
                    use_dual = True
                    # smaller-magnitude col → primary axis (y) so both series are visible
                    dual_primary_col = group[0] if maxes[0] <= maxes[1] else group[1]

            datasets = []
            for i, y_col in enumerate(group):
                color = self._CHART_COLORS[i % len(self._CHART_COLORS)]
                values = [_to_num(row.get(y_col)) for row in data]
                ds: dict = {
                    'label': y_col.replace('_', ' ').title(),
                    'data':  values,
                }
                if chart_type == 'doughnut':
                    ds['backgroundColor'] = self._CHART_COLORS[:len(data)]
                else:
                    ds['backgroundColor'] = color + '99'
                    ds['borderColor']     = color
                    ds['borderWidth']     = 1
                if chart_type == 'line':
                    ds['tension'] = 0.3
                    ds['fill']    = False
                if use_dual:
                    ds['yAxisID'] = 'y' if y_col == dual_primary_col else 'y1'
                datasets.append(ds)

            # Explicit pct flags for the renderer's axis formatter (FIX 1).
            # Prevents the y1 tick callback from blindly appending '%' to revenue values.
            if use_dual and dual_primary_col:
                _y_col  = dual_primary_col
                _y1_col = next((c for c in group if c != dual_primary_col), None)
            else:
                _y_col  = group[0] if group else None
                _y1_col = None
            configs.append({
                'type':      chart_type,
                'labels':    labels,
                'datasets':  datasets,
                'title':     ' & '.join(c.replace('_', ' ').title() for c in group),
                'dual_axis': use_dual,
                'y_is_pct':  _is_pct_col(_y_col) if _y_col else False,
                'y1_is_pct': _is_pct_col(_y1_col) if _y1_col else False,
            })

        return configs

    def _build_donut_chart(self, state: AgentState, col_idx: int = 0) -> dict | None:
        """Build a Chart.js doughnut config from query_result.

        Selects the col_idx-th *share_pct / *pct / *kontribusi column as values,
        first text column as segment labels.  col_idx > 0 is used for multi-donut
        layouts (e.g. trx_share_pct donut and rev_share_pct donut separately).
        """
        data = state.query_result
        if not data:
            return None

        cols     = list(data[0].keys())
        num_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
        txt_cols = [c for c in cols if c not in num_cols]

        _SHARE_KW = ('share_pct', 'share', 'kontribusi', 'pct', 'percent', 'proportion', 'distribusi')
        _share_cols = [c for c in num_cols if any(kw in c.lower() for kw in _SHARE_KW)]
        if _share_cols:
            # Pick the col_idx-th share col (capped to last if idx exceeds count)
            val_col = _share_cols[min(col_idx, len(_share_cols) - 1)]
        else:
            val_col = num_cols[0] if num_cols else None
        if val_col is None:
            return None

        # Drop zero-share rows: they'd render as invisible slices.
        # They still appear in the narrative and data_table.
        data = [row for row in data if _to_num(row.get(val_col)) not in (None, 0.0)]
        if not data:
            return None

        label_col = txt_cols[0] if txt_cols else None
        labels    = [str(row.get(label_col, i)) for i, row in enumerate(data)] if label_col \
                    else [str(i + 1) for i in range(len(data))]
        values    = [_to_num(row.get(val_col)) for row in data]

        # ── Center value (design ref 2f: donat + nilai tengah) ──────────────
        # share_pct columns always total 100% by definition — no need to sum.
        # Raw absolute value columns: sum all slices and abbreviate.
        _is_share_col = any(kw in val_col.lower() for kw in _SHARE_KW)
        if _is_share_col:
            center_value = "100%"
        else:
            def _fmt_abbr(n: float) -> str:
                a = abs(n)
                if a >= 1e12:
                    return f"{n / 1e12:.1f}T"
                if a >= 1e9:
                    return f"{n / 1e9:.1f}M"
                if a >= 1e6:
                    return f"{n / 1e6:.1f}jt"
                if a >= 1e3:
                    return f"{n / 1e3:.0f}k"
                return f"{n:.0f}"
            _REVENUE_KW = ('revenue', 'pendapatan', 'net_gap', 'fee', 'anggaran', 'biaya')
            rp = "Rp" if any(kw in val_col.lower() for kw in _REVENUE_KW) else ""
            total = sum(v for v in values if v is not None)
            center_value = rp + _fmt_abbr(total)

        return {
            'type':         'doughnut',
            'labels':       labels,
            'datasets':     [{
                'label':           val_col.replace('_', ' ').title(),
                'data':            values,
                'backgroundColor': self._CHART_COLORS[:len(data)],
            }],
            'title':        val_col.replace('_', ' ').title(),
            'dual_axis':    False,
            'center_value': center_value,
            'center_label': 'TOTAL',
        }

    def _build_diverging_bar_chart(self, state: AgentState) -> dict | None:
        """Build a horizontal Chart.js bar config with green/red per-bar colors.

        Selects the first *pct_change / *_mom / *growth_pct column as values.
        Positive values get _COLOR_POS (SEHAT green), negative get _COLOR_NEG (KRITIS red),
        matching the verdict badge colours in style.css.
        index_axis='y' signals renderer.js to render horizontal bars.
        """
        data = state.query_result
        if not data:
            return None

        cols     = list(data[0].keys())
        num_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
        txt_cols = [c for c in cols if c not in num_cols]

        _PCT_KW = ('pct_change', 'pct_growth', 'pct_diff', '_mom', 'growth_pct', 'change_pct', 'perubahan_pct')
        val_col = next(
            (c for c in num_cols if any(kw in c.lower() for kw in _PCT_KW)),
            num_cols[0] if num_cols else None,
        )
        if val_col is None:
            return None

        # Sort by absolute magnitude (largest movers first) and cap rows for readability
        if len(data) > self._MAX_CHART_ROWS:
            original_count = len(data)
            data = sorted(data, key=lambda r: abs(_to_num(r.get(val_col)) or 0), reverse=True)[:self._MAX_CHART_ROWS]
            self.log(
                f"Diverging bar sampled: {original_count} → {len(data)} rows (top-N by |magnitude|)",
                level="warning",
            )

        label_col     = txt_cols[0] if txt_cols else None
        labels        = [str(row.get(label_col, i)) for i, row in enumerate(data)] if label_col \
                        else [str(i + 1) for i in range(len(data))]
        values        = [_to_num(row.get(val_col)) for row in data]
        bg_colors     = [self._COLOR_POS + '99' if (v or 0) >= 0 else self._COLOR_NEG + '99' for v in values]
        border_colors = [self._COLOR_POS        if (v or 0) >= 0 else self._COLOR_NEG        for v in values]

        return {
            'type':       'bar',
            'labels':     labels,
            'datasets':   [{
                'label':           val_col.replace('_', ' ').title(),
                'data':            values,
                'backgroundColor': bg_colors,
                'borderColor':     border_colors,
                'borderWidth':     1,
            }],
            'title':      val_col.replace('_', ' ').title(),
            'dual_axis':  False,
            'index_axis': 'y',
        }

    def _build_grouped_bar_chart(self, state: AgentState) -> dict | None:
        """Build a Chart.js grouped bar config showing two periods side-by-side per entity.

        Finds *_a / *_b column pairs in state.query_result. Selects the first pair
        by column order (stable: matches compare_periods schema order trx_a → rev_a → sr_a).
        Additional pairs beyond the first are logged as not-charted.

        Output: Chart.js type='bar' with two datasets ('Periode A', 'Periode B').
        Chart.js renders multiple datasets as side-by-side grouped bars by default
        (no stacked:true, no indexAxis override needed).
        """
        data = state.query_result
        if not data or len(data) < 2:
            return None

        cols     = list(data[0].keys())
        txt_cols = [c for c in cols if _to_num(data[0].get(c)) is None]
        num_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]

        # Find *_a / *_b pairs preserving original column order for stable selection.
        # Iterating num_cols in order ensures trx_a/trx_b comes before rev_a/rev_b
        # in compare_periods results, giving the most-transaction-count chart priority.
        pairs: list[tuple[str, str, str]] = []  # (prefix, col_a, col_b)
        seen_prefixes: set[str] = set()
        for c in num_cols:
            if not c.endswith('_a'):
                continue
            prefix = c[:-2]
            if prefix in seen_prefixes:
                continue
            col_b = prefix + '_b'
            if col_b in num_cols:
                pairs.append((prefix, c, col_b))
                seen_prefixes.add(prefix)

        if not pairs:
            return None

        # One chart per block — log any pairs that don't fit
        if len(pairs) > 1:
            dropped = [f"{p[1]}/{p[2]}" for p in pairs[1:]]
            self.log(
                f"grouped_bar_chart: showing first pair only ({pairs[0][1]}/{pairs[0][2]}); "
                f"additional *_a/*_b pairs not represented in this chart: {dropped}",
                level="warning",
            )

        prefix, col_a, col_b = pairs[0]
        entity_col = txt_cols[0] if txt_cols else None
        labels = (
            [str(row.get(entity_col, i)) for i, row in enumerate(data)]
            if entity_col
            else [str(i + 1) for i in range(len(data))]
        )

        if len(data) > self._MAX_CHART_ROWS:
            self.log(
                f"grouped_bar_chart: capped at {self._MAX_CHART_ROWS} entities",
                level="warning",
            )
            data   = data[:self._MAX_CHART_ROWS]
            labels = labels[:self._MAX_CHART_ROWS]

        values_a = [_to_num(row.get(col_a)) for row in data]
        values_b = [_to_num(row.get(col_b)) for row in data]

        color_a = self._CHART_COLORS[0]   # blue  — Periode A
        color_b = self._CHART_COLORS[1]   # green — Periode B
        title   = f"{prefix.replace('_', ' ').title()} — Periode A vs B"

        return {
            'type':     'bar',
            'labels':   labels,
            'datasets': [
                {
                    'label':           'Periode A',
                    'data':            values_a,
                    'backgroundColor': color_a + '99',
                    'borderColor':     color_a,
                    'borderWidth':     1,
                },
                {
                    'label':           'Periode B',
                    'data':            values_b,
                    'backgroundColor': color_b + '99',
                    'borderColor':     color_b,
                    'borderWidth':     1,
                },
            ],
            'title':     title,
            'dual_axis': False,
        }

    def _build_chart_for_type(self, vblock_type: str, state: AgentState) -> dict | None:
        """Route a single visual_block type to its chart config builder."""
        if vblock_type in ('line_chart', 'bar_chart'):
            configs = self._build_chart_configs(state)
            return configs[0] if configs else None
        if vblock_type == 'donut_chart':
            return self._build_donut_chart(state)
        if vblock_type == 'diverging_bar_chart':
            return self._build_diverging_bar_chart(state)
        if vblock_type == 'grouped_bar_chart':
            return self._build_grouped_bar_chart(state)
        return None

    def _build_chart_configs_with_anchors(self, state: AgentState, plan: dict) -> list[dict]:
        """
        Build chart configs per visual_block using type-specific builders.

        Each chart-producing visual_block gets exactly one config via _build_chart_for_type().
        Non-chart types and unknown types are skipped. If a builder returns None (insufficient
        data), the block is skipped with a warning.

        Fallback: if state.layout_plan is None (ResponsePlanner did not run), delegates to
        _build_chart_configs() — the legacy positional path — to preserve backward compatibility.
        """
        if state.layout_plan is None:
            return self._build_chart_configs(state)

        visual_blocks = plan.get("visual_blocks", [])
        if not visual_blocks:
            return []

        _KNOWN_NON_CHART = {"kpi_grid", "anomaly_callout", "data_table", "ranking_table"}
        _BAR_LINE_TYPES  = {"bar_chart", "line_chart"}

        # Pre-build bar/line configs once.  Multiple bar_chart visual_blocks receive
        # consecutive configs (configs[0], configs[1], …) so the second block gets the
        # *_share_pct chart while the first gets the absolute chart — not both configs[0].
        _bar_line_built: bool = False
        _bar_line_configs: list[dict] = []
        _bar_line_idx: int = 0

        # donut_chart blocks increment this counter so each consecutive donut block
        # picks the next share_pct column (col 0 = trx_share_pct, col 1 = rev_share_pct).
        _donut_col_idx: int = 0

        configs: list[dict] = []
        for vb in visual_blocks:
            btype = vb.get("type", "")
            if btype not in _CHARTJS_VISUAL_TYPES:
                if btype not in _KNOWN_NON_CHART:
                    self.log(f"visual_block type '{btype}' not in _CHARTJS_VISUAL_TYPES — skipped", level="warning")
                continue

            if btype in _BAR_LINE_TYPES:
                if not _bar_line_built:
                    _bar_line_configs = self._build_chart_configs(state)
                    _bar_line_built = True
                if _bar_line_idx < len(_bar_line_configs):
                    cfg: dict | None = _bar_line_configs[_bar_line_idx]
                else:
                    self.log(
                        f"No bar/line config at index {_bar_line_idx} — only {len(_bar_line_configs)} built",
                        level="warning",
                    )
                    cfg = None
                _bar_line_idx += 1
            elif btype == "donut_chart":
                cfg = self._build_donut_chart(state, col_idx=_donut_col_idx)
                _donut_col_idx += 1
            else:
                cfg = self._build_chart_for_type(btype, state)

            if cfg is None:
                self.log(f"_build_chart_for_type('{btype}') returned None — insufficient data", level="warning")
                continue
            configs.append({
                **cfg,
                "anchor_after": vb.get("anchor_after"),
                "purpose":      vb.get("purpose"),
            })
        return configs

    def _parse_insight_sections(self, text: str) -> dict[str, str] | None:
        """
        Split insights string into per-section dict using <!-- SECTION:sN --> markers.

        Returns None when no markers are found (single-section response or LLM forgot
        markers) — callers should treat None as "use state.insights as-is."

        The marker on its own line is invisible when rendered by marked.js (GFM):
        it becomes a DOM comment node, not visible text.

        state.insights (full string) always remains the authoritative backward-compat
        field. This dict is opt-in for new renderer logic.
        """
        # Split on markers; keeps the section id as a captured group between content chunks
        parts = re.split(r'\n?<!--\s*SECTION:(s\d+)\s*-->\n?', text)
        if len(parts) < 3:
            # No markers found (parts = [full_text]) or only one section
            return None

        # parts[0] = s1 content, parts[1] = "s2", parts[2] = s2 content, ...
        sections: dict[str, str] = {"s1": parts[0].strip()}
        for i in range(1, len(parts) - 1, 2):
            sid     = parts[i]
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections[sid] = content

        return sections if len(sections) > 1 else None

    def _charts_from_multi_step(self, step_results: list) -> list[dict]:
        """Build one Chart.js config per step, plus an overall comparison chart."""
        configs: list[dict] = []
        for step in step_results:
            if not step.data or step.row_count == 0:
                continue
            data = step.data[:self._MAX_CHART_ROWS]
            if len(data) < 2:
                continue
            cols         = list(data[0].keys())
            numeric_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
            text_cols    = [c for c in cols if c not in numeric_cols]
            if not numeric_cols:
                continue
            x_col      = text_cols[0] if text_cols else None
            is_time    = x_col and any(kw in x_col.lower() for kw in self._TIME_KEYWORDS)
            labels     = [str(row.get(x_col, i)) for i, row in enumerate(data)] if x_col \
                         else [str(i + 1) for i in range(len(data))]
            y_col      = numeric_cols[0]
            color      = self._CHART_COLORS[step.step_number % len(self._CHART_COLORS)]
            chart_type = 'line' if is_time else 'bar'
            configs.append({
                'type':   chart_type,
                'labels': labels,
                'title':  step.description or f'Tahap {step.step_number}',
                'datasets': [{
                    'label':           y_col.replace('_', ' ').title(),
                    'data':            [_to_num(row.get(y_col)) for row in data],
                    'backgroundColor': color + '99',
                    'borderColor':     color,
                    'borderWidth':     1,
                    'tension':         0.3 if chart_type == 'line' else 0,
                    'fill':            False,
                }],
            })

        overall = self._chart_from_steps(step_results)
        if overall:
            overall['title'] = 'Perbandingan Keseluruhan'
            configs.append(overall)

        return configs

    def _chart_from_steps(self, step_results: list) -> dict | None:
        """Bar chart comparing one numeric metric across steps."""
        valid = [s for s in step_results if s.data and s.row_count > 0]
        if len(valid) < 2:
            return None

        def _is_num(v: object) -> bool:
            if isinstance(v, bool):
                return False
            if isinstance(v, (int, float)):
                return True
            if isinstance(v, str):
                try:
                    float(v.replace(',', ''))
                    return True
                except ValueError:
                    return False
            try:
                float(v)  # type: ignore[arg-type]
                return True
            except (TypeError, ValueError):
                return False

        first_cols = list(valid[0].data[0].keys())
        numeric_keys = [
            c for c in first_cols
            if all(_is_num(s.data[0].get(c)) for s in valid)
        ]
        if not numeric_keys:
            return None

        metric = numeric_keys[0]
        labels = [s.description or f"Tahap {s.step_number}" for s in valid]
        def _to_f(v: object) -> float:
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
            try:
                return float(str(v).replace(',', ''))
            except ValueError:
                return 0.0

        values = [_to_f(s.data[0].get(metric)) for s in valid]

        return {
            'type': 'bar',
            'labels': labels,
            'datasets': [{
                'label':           metric.replace('_', ' ').title(),
                'data':            values,
                'backgroundColor': [self._CHART_COLORS[i % len(self._CHART_COLORS)] + '99'
                                    for i in range(len(valid))],
                'borderColor':     [self._CHART_COLORS[i % len(self._CHART_COLORS)]
                                    for i in range(len(valid))],
                'borderWidth': 1,
            }],
        }

    def _fallback(self, state: AgentState) -> str:
        """Fallback insight if LLM call fails."""
        if not state.query_result or state.row_count == 0:
            return f"Query untuk '{state.query}' tidak mengembalikan hasil."

        if state.row_count == 1 and len(state.query_result[0]) == 1:
            key = list(state.query_result[0].keys())[0]
            value = state.query_result[0][key]
            if isinstance(value, (int, float)):
                return f"Hasil: {value:,}"
            return f"Hasil: {value}"

        return f"Query mengembalikan {state.row_count} baris data."
