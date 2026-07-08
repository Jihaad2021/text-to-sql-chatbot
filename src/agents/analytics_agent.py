"""
AnalyticsAgent — investigasi analitik dengan tool calling.

Agent investigasi berbasis tool calling untuk intent analitik.
AI memilih tools secara mandiri berdasarkan pertanyaan dan hasil sebelumnya.

Reads from state:
    - state.query
    - state.database

Writes to state:
    - state.insights
    - state.tool_calls      (log semua tool yang dipanggil)
    - state.query_result    (hasil tool terakhir)
    - state.validated_sql   (SQL dari tool terakhir)
    - state.row_count
"""

import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState, ToolCallResult
from src.tools.tool_registry import TOOL_DEFINITIONS, execute_tool, to_anthropic_tools
from src.utils.domain_entities import render_partner_display_block, render_channel_codes_flat
from src.utils.exceptions import LLMCallError
from src.utils.thresholds import render_thresholds_block as _render_thresholds

# Domain entity constants — computed once at import from domain_entities.yaml.
_PARTNER_DISPLAY    = render_partner_display_block()
_CHANNEL_CODES_FLAT = render_channel_codes_flat()

_MAX_TOOL_ITERATIONS = 8

_MONTH_ID = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

_THRESHOLDS_BLOCK = _render_thresholds()


def _data_range_line(data_end_date: date | None, data_start_date: date | None = None) -> str:
    """Build a human-readable data range line from start and end dates."""
    if data_end_date is None:
        return "Data tersedia: (rentang tidak diketahui — DB tidak terjangkau)."
    end_str = f"{_MONTH_ID[data_end_date.month]} {data_end_date.year}"
    if data_start_date is not None:
        start_str = f"{_MONTH_ID[data_start_date.month]} {data_start_date.year}"
    else:
        start_str = f"(awal data) {data_end_date.year}"
    return f"Data tersedia: {start_str} – {end_str} (s.d. {data_end_date.isoformat()})."


def _build_system_prompt(data_end_date: date | None, data_start_date: date | None = None) -> str:
    return f"""Kamu adalah analis data senior untuk platform pembayaran digital Telkomsel.
Gunakan tools yang tersedia untuk menjawab pertanyaan analitik secara sistematis.

{_data_range_line(data_end_date, data_start_date)}
Partner: {_PARTNER_DISPLAY}.
Channel: {_CHANNEL_CODES_FLAT}.

⚠️ ATURAN WAJIB — TIDAK BOLEH DILANGGAR:
1. Kamu HARUS memanggil minimal 1 tool sebelum memberikan jawaban apapun.
2. Jangan pernah menjawab langsung dari pengetahuan umum — semua angka harus berasal dari tool call.
3. Jika tidak yakin tool mana yang tepat, mulai dengan get_summary terlebih dahulu.
4. Angka yang tidak berasal dari tool call dianggap halusinasi dan TIDAK BOLEH disebutkan.

Panduan pemilihan tool — pilih berdasarkan pertanyaan:
- Kata "anomali", "lonjakan", "penurunan tiba-tiba", "melebihi batas", "tidak wajar" → WAJIB mulai dengan `detect_anomaly`
- Kata "bandingkan", "vs", "dibanding bulan lalu", "perubahan" → WAJIB mulai dengan `compare_periods`
- Kata "distribusi", "breakdown", "kontributor", "siapa yang dominan" → mulai dengan `get_distribution`
- Kata "tren", "pertumbuhan", "dari waktu ke waktu", "setiap bulan" → mulai dengan `get_trend`
- Kata "jam", "pukul", "waktu puncak", "peak hour" → gunakan `get_hourly_pattern`
- Pertanyaan umum tanpa kata kunci di atas → mulai dengan `get_summary`

Strategi investigasi setelah tool pertama:
1. Tool pertama dipilih berdasarkan panduan di atas
2. Gunakan compare_periods untuk membuktikan ada/tidaknya perubahan vs baseline
3. Drill down dengan get_distribution untuk tahu kontributor utama jika perlu
4. Berhenti memanggil tool jika pertanyaan sudah terjawab — jangan over-investigate

{_THRESHOLDS_BLOCK}

PERIODE PARSIAL — sebutkan jika bulan sedang berjalan:
- Jika data periode yang dianalisis belum bulan penuh (misalnya {_MONTH_ID[data_end_date.month] if data_end_date else "bulan terakhir"} baru 20 hari),
  SELALU sebutkan: "data bulan itu mencakup X hari pertama" agar perbandingan tidak menyesatkan.
- Perbandingan bulan parsial vs bulan penuh harus dinormalisasi per hari (rata-rata harian).

Dalam insight final (setelah semua tools selesai):
- Jawab pertanyaan langsung di kalimat pertama
- Sertakan angka konkret (format: Rp X miliar / X juta transaksi / X%)
- Jelaskan normal atau tidak dengan menyebut angka baseline pembanding
- Bahasa Indonesia, 3-5 kalimat yang padat dan informatif"""


class AnalyticsAgent(LLMBaseAgent):
    """
    Agent investigasi berbasis tool calling.

    Menggunakan pre-defined SQL tools (get_summary, compare_periods, dll)
    alih-alih generate SQL ad-hoc, sehingga hasil lebih konsisten dan dapat diandalkan.
    """

    def __init__(self) -> None:
        super().__init__(name="analytics_agent", version="1.0.0")
        self._engines: dict[str, Engine] = self._init_engines()

    def _init_engines(self) -> dict[str, Engine]:
        engines = {}
        for db_name, url in Config.DB_URLS.items():
            if url:
                try:
                    engines[db_name] = create_engine(
                        url,
                        pool_size=Config.POOL_SIZE,
                        max_overflow=Config.MAX_OVERFLOW,
                        pool_timeout=Config.POOL_TIMEOUT,
                        pool_recycle=Config.POOL_RECYCLE,
                    )
                except Exception as e:
                    self.log(f"Could not init engine for {db_name}: {e}", level="warning")
        return engines

    def execute(self, state: AgentState) -> AgentState:
        db_engine = self._engines.get(state.database)
        if db_engine is None:
            raise LLMCallError(
                agent_name=self.name,
                message=f"No engine available for database '{state.database}'",
            )

        system_prompt = _build_system_prompt(state.data_end_date, state.data_start_date)
        if state.context_snapshot:
            system_prompt = f"{system_prompt}\n\n{state.context_snapshot}"

        if self.provider == "anthropic":
            return self._run_anthropic(state, db_engine, system_prompt)
        return self._run_openai_compatible(state, db_engine, system_prompt)

    # ── OpenAI / OpenRouter / Gemini / Groq ──────────────────────────────────

    def _run_openai_compatible(self, state: AgentState, db_engine: Engine, system_prompt: str) -> AgentState:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state.query},
        ]
        tool_calls_log: list[dict] = []
        # Track (tool_name, frozen_args) to prevent identical repeated calls
        seen_calls: set[tuple] = set()

        for iteration in range(_MAX_TOOL_ITERATIONS):
            # Force at least one tool call on the first iteration — "required" ensures the
            # mandatory-tool rule in the system prompt is structurally enforced, not just
            # instructed. Subsequent iterations use "auto" so the model can stop once done.
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="required" if iteration == 0 else "auto",
                temperature=0,
            )

            msg = response.choices[0].message

            if not msg.tool_calls:
                state.insights = msg.content or ""
                break

            # Append assistant message with tool calls
            messages.append(msg)

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                # Dedup: skip if this exact call was made before
                call_key = (tool_name, json.dumps(arguments, sort_keys=True))
                if call_key in seen_calls:
                    self.log(f"Duplicate tool call detected: '{tool_name}' with same args — injecting stop hint", level="warning")
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      (
                            f"Tool '{tool_name}' sudah dipanggil dengan argumen yang sama. "
                            "Data yang dibutuhkan sudah tersedia. Buat kesimpulan berdasarkan data yang sudah ada."
                        ),
                    })
                    continue
                seen_calls.add(call_key)

                self.log(f"Calling tool '{tool_name}' with {arguments}")
                result = execute_tool(tool_name, arguments, db_engine)

                tool_calls_log.append({
                    "tool":      tool_name,
                    "arguments": arguments,
                    "row_count": result["row_count"],
                    "sql":       result["sql"],
                })

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result["data"][:50], default=str),
                })

                if result["row_count"] > 0:
                    state.tool_results.append(ToolCallResult(
                        tool_name=tool_name,
                        data=result["data"],
                        row_count=result["row_count"],
                        sql_or_params=result["sql"],
                        description=result.get("description", ""),
                        actual_entity_count=result.get("actual_entity_count", 0),
                        cumulative_trx_share_pct=result.get("cumulative_trx_share_pct", 0.0),
                        cumulative_rev_share_pct=result.get("cumulative_rev_share_pct", 0.0),
                        dimension=result.get("dimension", ""),
                    ))
                    # Keep last tool's data in query_result for backward compat consumers
                    state.query_result = result["data"]
                    state.validated_sql = result["sql"]
                    state.row_count = result["row_count"]

            self.log(f"Iteration {iteration + 1}: {len(msg.tool_calls)} tool(s) called")

        state.tool_calls = tool_calls_log
        return state

    # ── Anthropic ─────────────────────────────────────────────────────────────

    def _run_anthropic(self, state: AgentState, db_engine: Engine, system_prompt: str) -> AgentState:
        anthropic_tools = to_anthropic_tools(TOOL_DEFINITIONS)
        messages: list[dict] = [{"role": "user", "content": state.query}]
        tool_calls_log: list[dict] = []
        seen_calls: set[tuple] = set()

        for iteration in range(_MAX_TOOL_ITERATIONS):
            # Force at least one tool call on the first iteration via tool_choice=any.
            # Subsequent iterations use auto so the model can stop once satisfied.
            tc_override = {"type": "any"} if iteration == 0 else {"type": "auto"}
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                tools=anthropic_tools,
                tool_choice=tc_override,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                state.insights = " ".join(text_blocks)
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_result_msgs = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                arguments = block.input or {}

                call_key = (tool_name, json.dumps(arguments, sort_keys=True))
                if call_key in seen_calls:
                    self.log(f"Duplicate tool call detected: '{tool_name}' — injecting stop hint", level="warning")
                    tool_result_msgs.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     (
                            f"Tool '{tool_name}' sudah dipanggil dengan argumen yang sama. "
                            "Buat kesimpulan berdasarkan data yang sudah ada."
                        ),
                    })
                    continue
                seen_calls.add(call_key)

                self.log(f"Calling tool '{tool_name}' with {arguments}")
                result = execute_tool(tool_name, arguments, db_engine)

                tool_calls_log.append({
                    "tool":      tool_name,
                    "arguments": arguments,
                    "row_count": result["row_count"],
                    "sql":       result["sql"],
                })

                tool_result_msgs.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(result["data"][:50], default=str),
                })

                if result["row_count"] > 0:
                    state.tool_results.append(ToolCallResult(
                        tool_name=tool_name,
                        data=result["data"],
                        row_count=result["row_count"],
                        sql_or_params=result["sql"],
                        description=result.get("description", ""),
                        actual_entity_count=result.get("actual_entity_count", 0),
                        cumulative_trx_share_pct=result.get("cumulative_trx_share_pct", 0.0),
                        cumulative_rev_share_pct=result.get("cumulative_rev_share_pct", 0.0),
                        dimension=result.get("dimension", ""),
                    ))
                    # Keep last tool's data in query_result for backward compat consumers
                    state.query_result = result["data"]
                    state.validated_sql = result["sql"]
                    state.row_count = result["row_count"]

            messages.append({"role": "user", "content": tool_result_msgs})
            self.log(f"Iteration {iteration + 1}: {len(tool_result_msgs)} tool(s) called")

        state.tool_calls = tool_calls_log
        return state
