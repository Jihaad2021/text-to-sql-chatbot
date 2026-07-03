"""
Component 7: Insight Generator

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

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.thresholds import render_thresholds_block

# Chart.js-producing visual_block types — used to route per-block builders.
# Non-chart types (kpi_grid, anomaly_callout, data_table, ranking_table) are
# excluded from chart_configs entirely.
_CHARTJS_VISUAL_TYPES = {"line_chart", "bar_chart", "donut_chart", "diverging_bar_chart"}


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

    def execute(self, state: AgentState) -> AgentState:
        """
        Generate insights from query results.

        Args:
            state: Pipeline state with query_result and row_count

        Returns:
            Updated state with state.insights and state.chart_config
        """
        plan = state.layout_plan or {}

        try:
            prompt = self._build_prompt(state)
            intent = getattr(state, "intent", None)
            use_thinking = (
                self.provider == "anthropic"
                and intent in self._THINKING_INTENTS
            )
            insights = self._call_llm(
                prompt, max_tokens=1500, temperature=0.3, use_thinking=use_thinking
            )
            # Guard: if ResponsePlanner asked for brief, strip any extra sections
            # the LLM added beyond the direct answer (defense-in-depth after context trim).
            if plan.get("response_length") == "brief":
                insights = self._truncate_brief_sections(insights)
            state.insights = insights
            state.insights_sections = self._parse_insight_sections(insights)
            if use_thinking:
                self.log(f"Extended thinking used for intent: {intent}")
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
        """Branch to multi-step or single-step prompt based on state."""
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
        # For brief: strip partner/product/channel breakdown so the LLM isn't tempted to
        # pull that data into extra sections beyond the direct answer.
        _ctx = (
            self._trim_context_for_brief(state.context_snapshot)
            if response_length == "brief" and state.context_snapshot
            else state.context_snapshot
        )

        history_block  = self._build_history_block(state.conversation_history)
        context_block  = f"\n{_ctx}\n" if _ctx else ""
        layout_block   = self._build_layout_block(state.layout_plan)
        # Use segment from IntentClassifier if available, fallback to keyword detection
        segment        = (
            (state.intent or {}).get("segment")
            if isinstance(state.intent, dict)
            else None
        ) or self._detect_segment(state.query)
        segment_guide             = self._build_segment_guide(segment)
        business_thresholds_block = render_thresholds_block()

        elaboration_block = self._build_single_elaboration(response_length, has_context)

        return f"""You are a data analyst for Telkomsel's digital payment platform. Generate insights in conversational Indonesian.
{context_block}{history_block}
USER QUESTION: "{state.query}"

{elaboration_block}

SQL EXECUTED:
{state.validated_sql}

RESULTS ({state.row_count} rows):
{results_text}

CRITICAL — Number formatting rules:

TRANSACTION COUNTS (kolom: total_trx, success_trx, fail_trx, unique_users_daily, unique_users, unique_users_monthly):
  - These are INTEGER COUNTS of transactions or users — NEVER format as Rupiah
  - Under 1,000: "452 transaksi"
  - Under 1 million: "52.000 transaksi"
  - 1M–999M: "52,6 juta transaksi"
  - 1B+: "1,2 miliar transaksi"

REVENUE / MONEY (kolom: total_revenue, net_revenue, platform_fee, net_gap, total_net_revenue, total_platform_fee):
  - These ARE Rupiah amounts — format with Rp prefix
  - Under 1 million: "Rp 500.000"
  - 1M–999M: "Rp 252,3 juta"
  - 1B+: "Rp 1,2 miliar"

PERCENTAGES (kolom: success_rate_pct, avg_success_rate):
  - Format as "92,5%"

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

DATA INTEGRITY — ANTI-HALLUCINATION (wajib diikuti):
- Gunakan angka dari RESULTS atau dari CONTEXT SNAPSHOT — keduanya valid
- DILARANG mengarang angka yang tidak ada di salah satu dari keduanya
- Jika data terpotong, JANGAN sebut nilai min/max yang tidak bisa diverifikasi

METODOLOGI ANALISIS — ikuti urutan ini:
1. IDENTIFIKASI → dimensi apa? (volume / revenue / SR / growth / konsentrasi / risiko)
2. AMBIL DATA → gunakan angka dari RESULTS + CONTEXT SNAPSHOT
3. HITUNG SINYAL → perubahan %, selisih absolut, ranking, anomali
4. BERI VERDICT → SEHAT / PERHATIAN / KRITIS berdasarkan threshold di bawah

{business_thresholds_block}

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

{segment_guide}{layout_block}Your insights in Indonesian:"""

    def _build_multi_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt that synthesises all step results."""
        history_block = self._build_history_block(state.conversation_history)
        steps_block   = self._build_steps_block(state.step_results)
        context_block = f"\n{state.context_snapshot}\n" if state.context_snapshot else ""
        layout_block              = self._build_layout_block(state.layout_plan)
        business_thresholds_block = render_thresholds_block()

        response_length   = (state.layout_plan or {}).get("response_length", "standard")
        has_context       = bool(state.context_snapshot)
        elaboration_block = self._build_multi_elaboration(response_length, has_context)

        return f"""You are a data analyst for Telkomsel's digital payment platform.
{context_block}{history_block}
USER ORIGINAL QUESTION: "{state.query}"

{elaboration_block}

ANALYSIS STEPS EXECUTED:

{steps_block}

CRITICAL — Number formatting rules:

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

PERCENTAGES: format as "92,5%"

COMPARISON INSTRUCTIONS — when multiple steps represent two groups being compared:
1. Compute the absolute difference between the two groups
2. Compute the ratio (e.g. "X kali lipat lebih tinggi")
3. Compute the percentage change: ((A - B) / B) * 100
4. State clearly which group is higher/lower
5. Do NOT skip the math — calculate it yourself from the raw numbers in the step results

{business_thresholds_block}

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

{layout_block}Your insights in Indonesian:"""

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
        if response_length == "brief":
            return (
                "PANJANG JAWABAN (brief): jawab dalam 1–2 kalimat — bandingkan kedua periode/grup dengan angka "
                "konkret dan verdict SEHAT/PERHATIAN/KRITIS. Tidak perlu elaborasi tambahan.\n"
                "DILARANG mengarang angka yang tidak ada di step results di atas."
            )
        if response_length == "detailed" and has_context:
            return (
                _std + "\n"
                "- Tambahkan konteks historis: mengacu pada CONTEXT SNAPSHOT, jelaskan bagaimana temuan ini "
                "dibandingkan dengan pola historis multi-bulan atau baseline yang tersedia."
            )
        return _std  # standard, or detailed without context snapshot

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

    # Segment keywords for detection
    _PARTNER_KW  = {"partner", "gopay", "dana", "ovo", "linkaja", "ekosistem partner", "mitra"}
    _PRODUCT_KW  = {"produk", "product", "pulsa", "paket", "internet", "konten", "portfolio produk"}
    _CHANNEL_KW  = {"channel", "saluran", "umb", "mytelkomsel", "wec", "kanal"}
    _TXNKW       = {"transaksi", "volume", "revenue", "pendapatan", "sr", "success rate",
                    "arpu", "user", "pengguna", "harian", "mingguan", "tren", "anomali"}

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

    def _build_segment_guide(self, segment: str) -> str:
        """Return compact segment-specific answer pattern guidance."""
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
                "- Template pembuka: \"Portfolio [N] produk — [growing] tumbuh, [declining] turun — Verdict: [SEHAT/PERHATIAN/KRITIS]\"\n\n"
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
                "- Analisis per group lebih informatif: MyTelkomsel App (i1), UMB (f0/f4/f5), WEC (b0/b3/a0), Basic (ig).\n"
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
        if not data or len(data) <= 1 or len(data) > self._MAX_CHART_ROWS:
            return []

        def _to_num(v: object) -> float | None:
            if isinstance(v, bool): return None
            if isinstance(v, (int, float)): return float(v)
            if isinstance(v, str):
                try: return float(v.replace(',', '').replace(' ', ''))
                except ValueError: return None
            try: return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError): return None

        cols         = list(data[0].keys())
        numeric_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
        text_cols    = [c for c in cols if c not in numeric_cols]

        if not numeric_cols:
            return []

        x_col   = text_cols[0] if text_cols else None
        is_time = x_col and any(kw in x_col.lower() for kw in self._TIME_KEYWORDS)
        labels  = [str(row.get(x_col, i)) for i, row in enumerate(data)] if x_col \
                  else [str(i + 1) for i in range(len(data))]

        def _is_pct_col(col: str) -> bool:
            low = col.lower()
            return any(kw in low for kw in ('_pct', 'rate', 'share', 'percent', 'ratio', '_mom', 'growth'))

        configs: list[dict] = []
        metric_groups = [numeric_cols[i:i+2] for i in range(0, min(len(numeric_cols), 4), 2)]

        for group in metric_groups[:2]:
            if is_time:
                chart_type = 'line'
            elif len(data) <= 6 and len(group) == 1:
                chart_type = 'doughnut'
            else:
                chart_type = 'bar'

            # Dual axis: when one col is absolute and the other is a percentage/ratio
            use_dual = (
                len(group) == 2
                and chart_type != 'doughnut'
                and _is_pct_col(group[0]) != _is_pct_col(group[1])
            )

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
                    ds['yAxisID'] = 'y1' if _is_pct_col(y_col) else 'y'
                datasets.append(ds)

            configs.append({
                'type':      chart_type,
                'labels':    labels,
                'datasets':  datasets,
                'title':     ' & '.join(c.replace('_', ' ').title() for c in group),
                'dual_axis': use_dual,
            })

        return configs

    def _build_donut_chart(self, state: AgentState) -> dict | None:
        """Build a Chart.js doughnut config from query_result.

        Selects the first *share_pct / *pct / *kontribusi column as values,
        first text column as segment labels.
        """
        data = state.query_result
        if not data:
            return None

        def _to_num(v: object) -> float | None:
            if isinstance(v, bool): return None
            if isinstance(v, (int, float)): return float(v)
            if isinstance(v, str):
                try: return float(v.replace(',', '').replace(' ', ''))
                except ValueError: return None
            try: return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError): return None

        cols     = list(data[0].keys())
        num_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
        txt_cols = [c for c in cols if c not in num_cols]

        _SHARE_KW = ('share_pct', 'share', 'kontribusi', 'pct', 'percent', 'proportion', 'distribusi')
        val_col = next(
            (c for c in num_cols if any(kw in c.lower() for kw in _SHARE_KW)),
            num_cols[0] if num_cols else None,
        )
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

        return {
            'type':      'doughnut',
            'labels':    labels,
            'datasets':  [{
                'label':           val_col.replace('_', ' ').title(),
                'data':            values,
                'backgroundColor': self._CHART_COLORS[:len(data)],
            }],
            'title':     val_col.replace('_', ' ').title(),
            'dual_axis': False,
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

        def _to_num(v: object) -> float | None:
            if isinstance(v, bool): return None
            if isinstance(v, (int, float)): return float(v)
            if isinstance(v, str):
                try: return float(v.replace(',', '').replace(' ', ''))
                except ValueError: return None
            try: return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError): return None

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

    def _build_chart_for_type(self, vblock_type: str, state: AgentState) -> dict | None:
        """Route a single visual_block type to its chart config builder."""
        if vblock_type in ('line_chart', 'bar_chart'):
            configs = self._build_chart_configs(state)
            return configs[0] if configs else None
        if vblock_type == 'donut_chart':
            return self._build_donut_chart(state)
        if vblock_type == 'diverging_bar_chart':
            return self._build_diverging_bar_chart(state)
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
        configs: list[dict] = []
        for vb in visual_blocks:
            btype = vb.get("type", "")
            if btype not in _CHARTJS_VISUAL_TYPES:
                if btype not in _KNOWN_NON_CHART:
                    self.log(f"visual_block type '{btype}' not in _CHARTJS_VISUAL_TYPES — skipped", level="warning")
                continue
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
        def _to_num(v: object) -> float | None:
            if isinstance(v, bool): return None
            if isinstance(v, (int, float)): return float(v)
            if isinstance(v, str):
                try: return float(v.replace(',', ''))
                except ValueError: return None
            try: return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError): return None

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
            if isinstance(v, bool): return False
            if isinstance(v, (int, float)): return True
            if isinstance(v, str):
                try: float(v.replace(',', '')); return True
                except ValueError: return False
            try: float(v); return True  # type: ignore[arg-type]
            except (TypeError, ValueError): return False

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
            if isinstance(v, (int, float)): return float(v)
            try: return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError): pass
            try: return float(str(v).replace(',', ''))
            except ValueError: return 0.0

        values = [_to_f(s.data[0].get(metric)) for s in valid]
        color  = self._CHART_COLORS[0]

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
