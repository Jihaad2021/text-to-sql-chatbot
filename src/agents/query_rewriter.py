"""
QueryRewriter — pre-processes user questions for SQL clarity.

Runs before IntentClassifier and QueryPlanner. Rewrites vague or
ambiguous questions to be more precise without changing the intent.

Non-fatal by design: if the LLM call or JSON parse fails, the original
query is preserved and the pipeline continues unchanged.

Reads from state:
    - state.query
    - state.data_end_date

Writes to state:
    - state.query              (rewritten if needed, unchanged otherwise)
    - state.original_query     (always set to the pre-rewrite question)
    - state.rewrite_notes      (summary of what changed, or None)
    - state.query_out_of_range (True if resolved period_start > data_end_date)
    - state.out_of_range_latest (YYYY-MM-DD of latest available date, when out-of-range)
"""

import json
import re
from datetime import date, datetime

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.date_range import get_data_year
from src.utils.domain_entities import (
    render_partner_list_block,
    render_channel_list_block,
    render_channel_rewrite_rules,
)

_TABLES = ", ".join(sorted(Config.ALLOWED_TABLES))

# Domain entity constants — computed once at import from domain_entities.yaml.
# To add a partner/channel: edit config/domain_entities.yaml and restart.
_PARTNER_LIST   = render_partner_list_block()
_CHANNEL_LIST   = render_channel_list_block()
_CHANNEL_RULES  = render_channel_rewrite_rules()

# Month name tokens (Indonesian + English abbreviations) used for bare-month detection.
# Values are intentionally absent — only the keys matter for the regex pattern.
_MONTH_NAMES: frozenset[str] = frozenset({
    "januari", "jan", "februari", "feb", "maret", "mar",
    "april", "apr", "mei", "may", "juni", "jun",
    "juli", "jul", "agustus", "aug", "september", "sep",
    "oktober", "oct", "november", "nov", "desember", "dec",
})

# Compiled once from the stable set of month name tokens.
# Year injection is done at call time via the `year` parameter.
_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(_MONTH_NAMES, key=len, reverse=True)) + r")\b(?!\s+20\d{2})",
    re.IGNORECASE,
)


def _inject_year(query: str, year: int) -> str:
    """Append `year` after bare month names that have no year attached."""
    return _MONTH_PATTERN.sub(lambda m: f"{m.group(0)} {year}", query)


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


def _build_prompt(tables: str, query: str, today: str, data_year: int, history: list[dict]) -> str:
    history_block = _build_history_block(history)
    return f"""\
Kamu adalah preprocessor pertanyaan untuk chatbot analytics data keuangan Telkomsel.

Database: financial_db
Tabel tersedia: {tables}
Entitas kunci:
- partner: {_PARTNER_LIST}
- channel codes: {_CHANNEL_LIST}
- metrik: SR/success rate → kolom success_rate_pct, MoM → perbandingan bulan ini vs bulan lalu, ARPU → total_revenue/unique_users
Tanggal hari ini: {today}. Semua data ada di tahun {data_year}.
{history_block}
Tugas: tulis ulang pertanyaan berikut agar lebih presisi untuk SQL generation.
Terapkan HANYA aturan yang relevan:

0. REFERENSI KONTEKSTUAL — Jika pertanyaan menggunakan kata "ini", "itu", "tadi", "tersebut", "yang sama", atau merujuk implisit ke pertanyaan/hasil sebelumnya, gunakan KONTEKS PERCAKAPAN untuk mengganti referensi tersebut dengan entitas eksplisit.
   Contoh: (sebelumnya tanya "top 10 produk bulan mei") lalu "filter ini per channel" → "filter 10 produk dengan penjualan tertinggi bulan mei {data_year} per channel"

1. NAMA ENTITAS FUZZY — Jika nama produk, partner, atau entitas mungkin tidak persis sama di database, tambahkan catatan gunakan ILIKE.
   Contoh: "produk Surprise Deal Nonton" → "produk yang mengandung 'Surprise Deal Nonton' (gunakan ILIKE '%Surprise Deal Nonton%')"

2. ANALISIS KORELASI / AKTIF vs TIDAK AKTIF — Jika pertanyaan membandingkan kondisi "ketika X aktif vs tidak aktif", menganalisis dampak/korelasi, atau membutuhkan hasil satu subquery sebagai filter subquery lain → tambahkan di awal: "Gunakan satu query SQL dengan CTE."

3. REFERENSI VAGUE — Jika ada "produk lainnya", "produk lain", atau referensi tak jelas tanpa kriteria, jelaskan kriterianya secara eksplisit.
   Contoh: "9 produk lainnya" → "9 produk dengan total_trx terbanyak selain [nama produk yang disebutkan]"

4. PERIOD WAKTU HILANG — Jika pertanyaan jelas bersifat time-series tetapi tidak menyebut periode → tambahkan "(gunakan rentang data yang tersedia)".

5. NAMA CHANNEL HUMAN-READABLE — Jika user menyebut nama channel dalam bentuk manusia, ganti dengan kode database:
{_CHANNEL_RULES}

6. PARTNER GROUP — Jika pertanyaan menyebut partner (gopay, dana, finnet, dll.), performa partner, ranking partner, atau perbandingan partner: tambahkan di awal rewritten query: "Gunakan kolom partner_group (bukan partner) di daily_master."
   Pengecualian: jika user eksplisit menyebut sub-channel seperti paybill, wec, basic → pakai kolom partner.

Aturan tambahan:
- Gunakan bahasa yang sama dengan pertanyaan asli (Indonesia atau Inggris).
- Perubahan minimal — jangan tambahkan informasi yang tidak diimplikasikan pertanyaan.
- Jika pertanyaan sudah jelas dan spesifik, kembalikan apa adanya dengan was_rewritten: false.

Selain rewrite, identifikasi TANGGAL AWAL PERIODE yang diminta user:
- "bulan ini" → hari pertama bulan dari {today} (e.g. "{data_year}-07-01")
- "bulan lalu" → hari pertama bulan sebelumnya
- nama bulan spesifik → hari pertama bulan itu (e.g. "juni {data_year}" → "{data_year}-06-01")
- "tahun ini" / "YTD" → "{data_year}-01-01"
- "kuartal ini" → hari pertama kuartal berjalan
- pertanyaan tanpa periode waktu / tidak relevan → null

Balas HANYA dengan JSON valid tanpa markdown:
{{"rewritten": "...", "changes": ["perubahan 1", ...], "was_rewritten": true, "period_start": "YYYY-MM-DD"}}
atau:
{{"rewritten": "...", "changes": [], "was_rewritten": false, "period_start": null}}

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
        data_year = get_data_year(state.data_end_date)
        # Deterministically inject data year before LLM sees the query
        state.query = _inject_year(state.query, data_year)

        try:
            today  = date.today().strftime("%Y-%m-%d")
            prompt = _build_prompt(
                tables=_TABLES,
                query=state.query,
                today=today,
                data_year=data_year,
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

            # ── Out-of-range guard ────────────────────────────────────
            period_start_str = result.get("period_start")
            if period_start_str and state.data_end_date:
                try:
                    period_start = datetime.strptime(
                        period_start_str, "%Y-%m-%d"
                    ).date()
                    if period_start > state.data_end_date:
                        state.query_out_of_range = True
                        state.out_of_range_latest = state.data_end_date.isoformat()
                        self.log(
                            f"Out-of-range: period_start={period_start_str} > "
                            f"data_end_date={state.data_end_date}",
                            level="warning",
                        )
                except ValueError:
                    pass  # malformed date from LLM — skip guard silently

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
