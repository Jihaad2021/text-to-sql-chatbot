"""
QueryRewriter — pre-processes user questions for SQL clarity.

Runs before IntentClassifier and QueryPlanner. Rewrites vague or
ambiguous questions to be more precise without changing the intent.

Non-fatal by design: if the LLM call or JSON parse fails, the original
query is preserved and the pipeline continues unchanged.

Reads from state:
    - state.query

Writes to state:
    - state.query          (rewritten if needed, unchanged otherwise)
    - state.original_query (always set to the pre-rewrite question)
    - state.rewrite_notes  (summary of what changed, or None)
"""

import json

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState

_TABLES = ", ".join(sorted(Config.ALLOWED_TABLES))

_PROMPT_TEMPLATE = """\
Kamu adalah preprocessor pertanyaan untuk chatbot analytics data keuangan Telkomsel.

Database: financial_db
Tabel tersedia: {tables}
Entitas kunci: product_name, partner (gopay/ovo/dana/shopeepay/linkaja/qris/indomaret/tsel_wallet/finnet), channel (a0/b3/f0/f4/f5/i1/ig), date

Tugas: tulis ulang pertanyaan berikut agar lebih presisi untuk SQL generation.
Terapkan HANYA aturan yang relevan:

1. NAMA ENTITAS FUZZY — Jika nama produk, partner, atau entitas mungkin tidak persis sama di database, tambahkan catatan gunakan ILIKE.
   Contoh: "produk Surprise Deal Nonton" → "produk yang mengandung 'Surprise Deal Nonton' (gunakan ILIKE '%Surprise Deal Nonton%')"

2. ANALISIS KORELASI / AKTIF vs TIDAK AKTIF — Jika pertanyaan membandingkan kondisi "ketika X aktif vs tidak aktif", menganalisis dampak/korelasi, atau membutuhkan hasil satu subquery sebagai filter subquery lain → tambahkan di awal: "Gunakan satu query SQL dengan CTE."

3. REFERENSI VAGUE — Jika ada "produk lainnya", "produk lain", atau referensi tak jelas tanpa kriteria, jelaskan kriterianya secara eksplisit.
   Contoh: "9 produk lainnya" → "9 produk dengan total_trx terbanyak selain [nama produk yang disebutkan]"

4. PERIOD WAKTU HILANG — Jika pertanyaan jelas bersifat time-series tetapi tidak menyebut periode → tambahkan "(gunakan rentang data yang tersedia)".

Aturan tambahan:
- Gunakan bahasa yang sama dengan pertanyaan asli (Indonesia atau Inggris).
- Perubahan minimal — jangan tambahkan informasi yang tidak diimplikasikan pertanyaan.
- Jika pertanyaan sudah jelas dan spesifik, kembalikan apa adanya dengan was_rewritten: false.

Balas HANYA dengan JSON valid tanpa markdown:
{{"rewritten": "...", "changes": ["perubahan 1", ...], "was_rewritten": true}}
atau:
{{"rewritten": "...", "changes": [], "was_rewritten": false}}

Pertanyaan:
{query}"""


class QueryRewriter(LLMBaseAgent):
    """
    Rewrites user queries for SQL clarity before entering the main pipeline.

    Uses a cheap model (gpt-4o-mini by default) since this is a lightweight
    preprocessing step, not reasoning-heavy generation.
    """

    def __init__(self) -> None:
        super().__init__(name="query_rewriter", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        state.original_query = state.query

        try:
            prompt   = _PROMPT_TEMPLATE.format(tables=_TABLES, query=state.query)
            raw      = self._call_llm(prompt, max_tokens=600, temperature=0)
            result   = _parse_json(raw)

            if result.get("was_rewritten") and result.get("rewritten", "").strip():
                rewritten = result["rewritten"].strip()
                changes   = result.get("changes") or []
                state.query        = rewritten
                state.rewrite_notes = "; ".join(changes) if changes else "rewritten"
                self.log(
                    f"Rewritten — original: {state.original_query[:70]!r} | "
                    f"rewritten: {rewritten[:70]!r}"
                )
                if changes:
                    self.log(f"Changes applied: {changes}")
            else:
                state.rewrite_notes = None
                self.log(f"No rewrite needed: {state.query[:80]!r}")

        except Exception as exc:
            # Non-fatal: log warning and continue with original query
            self.log(f"Rewrite failed, continuing with original: {exc}", level="warning")
            state.rewrite_notes = None

        return state


def _parse_json(text: str) -> dict:
    """Parse JSON from LLM response, stripping any markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text  = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"was_rewritten": False, "rewritten": "", "changes": []}
