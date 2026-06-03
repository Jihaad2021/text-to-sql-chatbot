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
from datetime import date

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState

_TABLES = ", ".join(sorted(Config.ALLOWED_TABLES))

_MONTH_MAP = {
    "januari": "2026-01", "jan": "2026-01",
    "februari": "2026-02", "feb": "2026-02",
    "maret": "2026-03", "mar": "2026-03",
    "april": "2026-04", "apr": "2026-04",
    "mei": "2026-05", "may": "2026-05",
    "juni": "2026-06", "jun": "2026-06",
    "juli": "2026-07", "jul": "2026-07",
    "agustus": "2026-08", "aug": "2026-08",
    "september": "2026-09", "sep": "2026-09",
    "oktober": "2026-10", "oct": "2026-10",
    "november": "2026-11", "nov": "2026-11",
    "desember": "2026-12", "dec": "2026-12",
}


def _inject_year(query: str) -> str:
    """Add '2026' after bare month names that have no year attached."""
    import re
    pattern = re.compile(
        r"\b(" + "|".join(_MONTH_MAP) + r")\b(?!\s+20\d{2})",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f"{m.group(0)} 2026", query)


def _build_history_block(history: list[dict]) -> str:
    if not history:
        return ""
    recent = history[-3:]
    lines = ["\nKONTEKS PERCAKAPAN SEBELUMNYA:"]
    for turn in recent:
        q = turn.get("query", "")
        a = turn.get("insights", "")
        if q:
            lines.append(f"User: {q}")
        if a:
            lines.append(f"Chatbot: {a[:200]}{'...' if len(a) > 200 else ''}")
    lines.append("")
    return "\n".join(lines)


def _build_prompt(tables: str, query: str, today: str, history: list[dict]) -> str:
    history_block = _build_history_block(history)
    return f"""\
Kamu adalah preprocessor pertanyaan untuk chatbot analytics data keuangan Telkomsel.

Database: financial_db
Tabel tersedia: {tables}
Entitas kunci: product_name, partner (gopay/ovo/dana/shopeepay/linkaja/qris/indomaret/tsel_wallet/finnet), channel (a0/b3/f0/f4/f5/i1/ig), date
Tanggal hari ini: {today}. Semua data ada di tahun 2026.
{history_block}
Tugas: tulis ulang pertanyaan berikut agar lebih presisi untuk SQL generation.
Terapkan HANYA aturan yang relevan:

0. REFERENSI KONTEKSTUAL — Jika pertanyaan menggunakan kata "ini", "itu", "tadi", "tersebut", "yang sama", atau merujuk implisit ke pertanyaan/hasil sebelumnya, gunakan KONTEKS PERCAKAPAN untuk mengganti referensi tersebut dengan entitas eksplisit.
   Contoh: (sebelumnya tanya "top 10 produk bulan mei") lalu "filter ini per channel" → "filter 10 produk dengan penjualan tertinggi bulan mei 2026 per channel"

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
        # Deterministically inject year before LLM sees the query
        state.query = _inject_year(state.query)

        try:
            today  = date.today().strftime("%Y-%m-%d")
            prompt = _build_prompt(
                tables=_TABLES,
                query=state.query,
                today=today,
                history=state.conversation_history,
            )
            raw    = self._call_llm(prompt, max_tokens=600, temperature=0)
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
