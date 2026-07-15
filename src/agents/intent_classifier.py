"""
Component 1: Intent Classifier

Classifies user queries into intent categories and detects ambiguous queries.
Results are used by SQL Generator to determine query strategy.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.conversation_history

Writes to state:
    - state.intent (dict: category, confidence, reason, sql_strategy)
    - state.needs_clarification (bool)
    - state.clarification_reason (str, if ambiguous)

Example:
    >>> classifier = IntentClassifier()
    >>> state = AgentState(query="berapa total customer?")
    >>> state = classifier.run(state)
    >>> print(state.intent)
    {
        "category": "aggregation",
        "confidence": 0.95,
        "reason": "Query asks for count/total",
        "sql_strategy": "Use aggregate functions (COUNT/SUM/AVG) with GROUP BY if needed"
    }
"""

import re
from datetime import date

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.domain_entities import render_channel_group_labels_block, render_partner_list_block

# Domain entity constants — computed once at import from domain_entities.yaml.
_PARTNER_LIST         = render_partner_list_block()
_CHANNEL_GROUP_LABELS = render_channel_group_labels_block()

# ── Deterministic root_cause override — three-step check ─────────────────────
#
# Step 1: explicit causal phrases → always override (no further check needed)
_ROOT_CAUSE_EXPLICIT = re.compile(
    r'\b(apa\s+penyebab|apa\s+yang\s+menyebabkan|penyebab\s+(?:naik|turun|penurunan|kenaikan))\b',
    re.IGNORECASE,
)

# Step 2: why-question words
_WHY_QUESTION = re.compile(r'\b(kenapa|mengapa)\b', re.IGNORECASE)

# Step 3a: event/change signals — indicates a specific incident, not a persistent state
_CHANGE_EVENT = re.compile(
    r'\b(turun|naik|anjlok|melonjak|drop|spike|lonjakan|penurunan|kenaikan|'
    r'menurun|meningkat|tiba-tiba|mendadak|surut|jatuh|merosot|crash|amblas)\b',
    re.IGNORECASE,
)

# Step 3b: specific-time signals — implies a recent or pinpointed event
_TIME_SPECIFIC = re.compile(
    r'\b(kemarin|hari\s+ini|minggu\s+ini|minggu\s+lalu|bulan\s+lalu|tadi|'
    r'tanggal\s+\d+|belakangan\s+ini|beberapa\s+hari|malam\s+ini|pagi\s+ini)\b',
    re.IGNORECASE,
)

# Step 3c: persistent-pattern words — presence suppresses the override even when
# kenapa/mengapa is present, because "selalu rendah" is a ranking observation,
# not a root-cause event investigation.
_PERSISTENT_PATTERN = re.compile(
    r'\b(selalu|biasanya|terus[\s-]menerus|konsisten|umumnya|cenderung|'
    r'dari\s+dulu|sejak\s+awal|historis)\b',
    re.IGNORECASE,
)


def _is_root_cause_override(query: str) -> bool:
    """Return True if query should be forced to root_cause_analysis.

    Priority order:
    1. Explicit causal phrase (apa penyebab, penyebab naik/turun, etc.) → always True.
    2. Why-word + _CHANGE_EVENT → True, even if persistent-pattern word is present.
       "kenapa GoPay selalu turun di akhir bulan" → True (change beats persistent).
    3. Why-word + no persistent-pattern + _TIME_SPECIFIC → True.
       "kenapa SR tinggi hari ini?" → True (specific time, no change/persistent).
    4. Why-word + persistent-pattern + no change → False.
       "kenapa DANA selalu rendah" → False (static position, not an event).
    """
    if _ROOT_CAUSE_EXPLICIT.search(query):
        return True
    if _WHY_QUESTION.search(query):
        if _CHANGE_EVENT.search(query):          # change event wins over persistent
            return True
        if not _PERSISTENT_PATTERN.search(query) and _TIME_SPECIFIC.search(query):
            return True
    return False

# Valid intent categories
INTENT_CATEGORIES = {
    "simple_select":       "Basic SELECT query, no filters or aggregations",
    "filtered_query":      "SELECT with WHERE clause filters",
    "aggregation":         "Requires COUNT, SUM, AVG, MIN, MAX",
    "multi_table_join":    "Requires JOIN across multiple tables",
    "complex_analytics":   "Advanced analytics with subqueries, trends, grouping",
    "root_cause_analysis": "Investigative query asking why something happened, root cause of a spike/drop, or multi-dimensional analysis",
    "ranking_analysis":    "Queries asking for leaderboards, top/bottom N rankings, who is best/worst, anomaly detection across all entities",
    "recommendation":      "Queries asking for suggestions, recommendations, or 'what should we do / what needs attention'",
    "out_of_scope":        "Question requires data or capabilities not available in this pipeline (forecasting, multi-period >2 months, user cohort, revenue margin, failure pattern per hour, channel substitution)",
    "ambiguous":           "Unclear query that needs clarification",
}

# Strategy hint per category (passed to SQL Generator via state.intent)
INTENT_SQL_STRATEGY = {
    "simple_select":       "Use basic SELECT with LIMIT 100",
    "filtered_query":      "Use SELECT with WHERE clause",
    "aggregation":         "Use aggregate functions (COUNT/SUM/AVG) with GROUP BY if needed",
    "multi_table_join":    "Use JOIN across relevant tables",
    "complex_analytics":   "Use subqueries, CTEs, or window functions if needed",
    "root_cause_analysis": "Adaptive investigation across multiple dimensions (time, product, channel, partner)",
    "ranking_analysis":    "Use RANK() / ROW_NUMBER() window functions or ORDER BY + LIMIT; compare all entities to find top/bottom performers and outliers",
    "recommendation":      (
        "Generate ONE simple aggregation query: SELECT partner_group, SUM(total_trx) AS total_trx,"
        " SUM(total_revenue) AS total_revenue,"
        " ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx),0))*100,2) AS success_rate_pct"
        " FROM daily_master WHERE date BETWEEN [start] AND [end]"
        " GROUP BY partner_group ORDER BY total_trx DESC LIMIT 20."
        " NO CTE, NO comparison, NO anomaly detection."
        " InsightGenerator will synthesise recommendations from this summary."
    ),
    "out_of_scope":        "No SQL needed — return redirect message explaining the data limitation",
    "ambiguous":           "Cannot generate SQL - needs clarification",
}

# Business segments — five dimensions from the dashboard question catalog
SEGMENT_CATEGORIES = {
    "transactions": "Questions about overall volume, revenue, SR, ARPU, users, daily/weekly trends, anomalies",
    "products":     "Questions about product portfolio, product momentum (gainers/losers), product SR, product concentration",
    "partners":     "Questions about partner ecosystem health, partner momentum, partner risk, partner efficiency",
    "channels":     "Questions about channel distribution, channel health, channel concentration",
    "general":      "Cross-segment, root cause, momentum direction, or other",
}

# Out-of-scope messages per topic — returned as state.insights when detected
_OUT_OF_SCOPE_MESSAGES: dict[str, str] = {
    "forecasting":    "Pertanyaan ini membutuhkan model *forecasting* yang belum tersedia. Pipeline saat ini hanya menyediakan estimasi pace sederhana berdasarkan rata-rata harian bulan berjalan — bukan proyeksi akurat jangka panjang.",
    "multi_period":   "Pertanyaan ini membutuhkan data historis multi-periode (lebih dari 2 bulan) yang belum tersedia. Pipeline saat ini membandingkan bulan berjalan dengan bulan sebelumnya saja.",
    "user_behavior":  "Analisis user behavior detail — frekuensi repeat transaction, cohort, atau lifetime value — belum tersedia. Data yang ada hanya menyediakan jumlah unique user per hari/partner.",
    "revenue_margin": "Data margin efektif atau biaya per produk belum tersedia di pipeline saat ini. Revenue yang tersedia adalah gross revenue dari settlement.",
    "failure_pattern":"Analisis pola failure per jam membutuhkan data granular per jam yang belum tersedia dalam format yang bisa di-query.",
    "substitution":   "Analisis substitusi antar channel — apakah turunnya satu channel berkorelasi dengan naiknya channel lain — membutuhkan data cross-channel yang belum tersedia.",
    "default":        "Pertanyaan ini membutuhkan data atau analisis yang belum tersedia di pipeline saat ini. Ini termasuk dalam kategori pengembangan ke depan.",
}


class IntentClassifier(LLMBaseAgent):
    """
    Classify user query intent using Claude.

    Determines:
    - Query category (simple_select, aggregation, etc.)
    - Whether query needs clarification
    - SQL generation strategy hint for SQL Generator
    """

    def __init__(self) -> None:
        super().__init__(name="intent_classifier", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        """
        Classify intent of user query.

        Args:
            state: Pipeline state with state.query and state.conversation_history

        Returns:
            Updated state with intent classification results
        """
        prompt = self._build_prompt(state)
        response = self._call_llm(prompt, max_tokens=500, temperature=0)
        self._record_token_usage(state, model=self.model)
        intent = self._parse_response(response)

        # Hard override: "kenapa / mengapa / apa penyebab" questions are always
        # root_cause_analysis regardless of what the LLM classified them as.
        # Check original_query because QueryRewriter may have removed "kenapa" from state.query.
        check_query = state.original_query or state.query
        if _is_root_cause_override(check_query):
            if intent["category"] not in ("root_cause_analysis", "ambiguous"):
                self.log(
                    f"Override: '{intent['category']}' → 'root_cause_analysis' (why-question detected)",
                    level="warning",
                )
                intent = {
                    **intent,
                    "category": "root_cause_analysis",
                    "sql_strategy": INTENT_SQL_STRATEGY["root_cause_analysis"],
                }

        state.intent = intent
        # out_of_scope is NOT ambiguous — it's a clear query that we can't answer.
        # The pipeline handles it with an early return + informative message.
        state.needs_clarification = (
            intent["category"] == "ambiguous" or intent["confidence"] < 0.7
        )

        if state.needs_clarification:
            state.clarification_reason = intent["reason"]

        self.log(
            f"Intent: {intent['category']} segment={intent.get('segment', '?')} "
            f"(confidence: {intent['confidence']:.2f}, "
            f"needs_clarification: {state.needs_clarification})"
        )

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Build classification prompt, including recent conversation context if available."""
        categories_text = "\n".join([
            f"  {cat} — {desc}"
            for cat, desc in INTENT_CATEGORIES.items()
        ])
        segments_text = "\n".join([
            f"  {seg} — {desc}"
            for seg, desc in SEGMENT_CATEGORIES.items()
        ])

        history_block = self._build_history_block(state.conversation_history)
        today = date.today().strftime("%Y-%m-%d")

        return f"""You are an intent classifier for a Telkomsel digital payment analytics chatbot.

TODAY'S DATE: {today}
Resolve relative time: "bulan ini"=current month, "minggu ini"=current week, "hari ini"=today.

STEP 1 — Classify query into ONE intent category:
{categories_text}

STEP 2 — Identify the business segment:
{segments_text}

{history_block}USER QUERY: "{state.query}"

Respond in this EXACT format (4 lines):
INTENT: [category]
SEGMENT: [segment]
CONFIDENCE: [0.0 to 1.0]
REASON: [brief explanation]

INTENT RULES:
- "ambiguous" ONLY if query is genuinely vague (e.g. "tampilkan data" with no context)
- Totals, sums, averages → "aggregation"
- Trends, per-period breakdowns → "complex_analytics"
- "kenapa/mengapa/apa penyebab/investigasi/analisis mendalam" → ALWAYS "root_cause_analysis"
- "ranking/peringkat/top N/bottom N/siapa terbaik/siapa terburuk/anomali dari semua" → "ranking_analysis"
- "rekomendasi/saran/apa yang harus dilakukan/perlu perhatian/prioritas" → "recommendation"
- OUT OF SCOPE — classify as "out_of_scope" if query asks for:
  • Forecasting/proyeksi akurat bulan depan atau lebih (bukan proyeksi pace bulan berjalan)
  • Komparasi 3+ bulan historis ("3 bulan terakhir", "tren kuartal", "YoY")
  • User behavior: repeat frequency, cohort, retention, lifetime value
  • Revenue margin atau biaya per produk
  • Pola failure per jam
  • Apakah satu channel menggantikan channel lain (substitusi channel)
- Do NOT mark ambiguous if query has clear analytical intent

SEGMENT RULES:
- "transactions" if query is about overall volume, revenue, SR, ARPU, user count, daily/weekly/period trends
- "products" if query mentions specific products, product names, portfolio, produk, paket, pulsa, konten
- "partners" if query mentions partners ({_PARTNER_LIST}) or ekosistem partner
- "channels" if query mentions channel, saluran, {_CHANNEL_GROUP_LABELS}
- "general" for cross-segment, root cause across dimensions, or unclear segment

EXAMPLES — kasus batas yang sering salah diklasifikasi (gunakan sebagai referensi):

[1] Terlihat seperti recommendation → sebenarnya root_cause_analysis
QUERY: "Apa yang perlu kita waspadai dari penurunan volume transaksi QRIS tanggal 30 Juni?"
INTENT: root_cause_analysis
SEGMENT: partners
CONFIDENCE: 0.90
REASON: "Perlu diwaspadai" terdengar seperti recommendation, tapi query meminta investigasi penyebab anomali spesifik — bukan saran tindakan. Tes: apakah LLM diminta menjelaskan MENGAPA sesuatu terjadi, atau menyarankan APA yang harus dilakukan? Di sini = mengapa → root_cause_analysis.

[2] Menyebut "kenapa" → tetap ranking_analysis
QUERY: "Tampilkan ranking semua partner dari SR tertinggi ke terendah — kenapa DANA selalu di posisi terbawah?"
INTENT: ranking_analysis
SEGMENT: partners
CONFIDENCE: 0.85
REASON: Inti permintaan adalah leaderboard diurutkan berdasarkan SR. "Kenapa DANA di bawah" adalah pertanyaan tentang posisi relatif dalam ranking, bukan investigasi event penurunan. Pembeda kunci: "kenapa DANA TURUN bulan ini?" (root_cause — event spesifik) vs "kenapa DANA SELALU rendah?" (konteks ranking — posisi relatif).

[3] Ambiguous genuine — perlu klarifikasi
QUERY: "Lihat performa produk bulan ini"
INTENT: ambiguous
SEGMENT: products
CONFIDENCE: 0.35
REASON: "Performa" tidak spesifik — bisa volume, SR, revenue, atau ranking. Tidak ada metrik atau dimensi yang bisa menghasilkan SQL yang tepat tanpa asumsi. Perlu klarifikasi: "performa berdasarkan metrik apa?"

[4] Out-of-scope (forecasting masa depan)
QUERY: "Proyeksikan success rate Telkomsel untuk bulan Juli berdasarkan tren Juni 2026"
INTENT: out_of_scope
SEGMENT: transactions
CONFIDENCE: 0.95
REASON: Membutuhkan model forecasting untuk periode masa depan. Pipeline hanya menyediakan proyeksi pace sederhana bulan berjalan (rata-rata harian × sisa hari), bukan prediksi bulan depan yang akurat.

[5] Complex analytics biasa — bukan root_cause, bukan ranking
QUERY: "Tampilkan tren harian volume transaksi dan success rate per partner sepanjang Juni 2026"
INTENT: complex_analytics
SEGMENT: partners
CONFIDENCE: 0.95
REASON: Membutuhkan grouping multi-dimensi (per hari × per partner) dengan dua metrik sekaligus — tipikal complex_analytics. Tidak ada kata "kenapa/mengapa", tidak ada leaderboard, tidak ada permintaan saran.

Your response:"""

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

    def _parse_response(self, response: str) -> dict[str, str | float]:
        """Parse LLM response into intent dict with segment and optional out_of_scope_message."""
        intent_str = "ambiguous"
        segment    = "general"
        confidence = 0.0
        reason     = ""

        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("INTENT:"):
                intent_str = line.replace("INTENT:", "").strip().lower()
            elif line.startswith("SEGMENT:"):
                segment = line.replace("SEGMENT:", "").strip().lower()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                except ValueError:
                    confidence = 0.5
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        if intent_str not in INTENT_CATEGORIES:
            intent_str = "ambiguous"
        if segment not in SEGMENT_CATEGORIES:
            segment = "general"

        if confidence < 0.5 and intent_str not in ("out_of_scope",):
            intent_str = "ambiguous"
            reason = reason or f"Low confidence ({confidence:.2f})"

        result: dict = {
            "category":     intent_str,
            "segment":      segment,
            "confidence":   confidence,
            "reason":       reason,
            "sql_strategy": INTENT_SQL_STRATEGY[intent_str],
        }

        if intent_str == "out_of_scope":
            result["out_of_scope_message"] = self._pick_oos_message(reason)

        return result

    def _pick_oos_message(self, reason: str) -> str:
        """Select the most relevant out-of-scope redirect message based on the reason."""
        r = reason.lower()
        if any(w in r for w in ("forecast", "proyeksi", "prediksi", "bulan depan")):
            return _OUT_OF_SCOPE_MESSAGES["forecasting"]
        if any(w in r for w in ("3 bulan", "kuartal", "yoy", "multi-periode", "historis")):
            return _OUT_OF_SCOPE_MESSAGES["multi_period"]
        if any(w in r for w in ("repeat", "cohort", "retention", "lifetime", "frekuensi user")):
            return _OUT_OF_SCOPE_MESSAGES["user_behavior"]
        if any(w in r for w in ("margin", "biaya per produk", "revenue margin")):
            return _OUT_OF_SCOPE_MESSAGES["revenue_margin"]
        if any(w in r for w in ("failure per jam", "pola failure")):
            return _OUT_OF_SCOPE_MESSAGES["failure_pattern"]
        if any(w in r for w in ("substitusi", "channel lain", "beralih")):
            return _OUT_OF_SCOPE_MESSAGES["substitution"]
        return _OUT_OF_SCOPE_MESSAGES["default"]
