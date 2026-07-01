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

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.tools.tool_registry import TOOL_DEFINITIONS, execute_tool, to_anthropic_tools
from src.utils.exceptions import LLMCallError

_MAX_TOOL_ITERATIONS = 8

_SYSTEM_PROMPT = """Kamu adalah analis data senior untuk platform pembayaran digital Telkomsel.
Gunakan tools yang tersedia untuk menjawab pertanyaan analitik secara sistematis.

Data tersedia: Maret 2026 – Juni 2026.
Partner: QRIS, Dana, GoPay, OVO, Finnet, ShopeePay, LinkAja, Indomaret, Telkomsel Wallet.
Channel: i1, a0, b0, b3, f0, f4, f5, ig.

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

BUSINESS THRESHOLDS (gunakan ini untuk kontekstualisasi hasil):
- Success Rate: ≥97% = normal (tidak perlu disebutkan), 95–96.99% = perlu perhatian, <95% = kritis
  → HANYA flag nilai yang BENAR-BENAR di bawah 97%. Nilai 99.x% adalah normal meski tidak 100%.
- Perubahan transaksi harian vs baseline: <15% = normal, 15–35% = signifikan, >35% = ekstrim
- Perubahan revenue vs baseline: <10% = normal, 10–25% = signifikan, >25% = ekstrim
- Lonjakan positif >35% biasanya indikasi promo atau event; negatif >35% indikasi gangguan sistem

PERIODE PARSIAL — sebutkan jika bulan sedang berjalan:
- Jika data periode yang dianalisis belum bulan penuh (misalnya Juni 2026 baru 20 hari),
  SELALU sebutkan: "data Juni mencakup X hari pertama" agar perbandingan tidak menyesatkan.
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

        system_prompt = _SYSTEM_PROMPT
        if state.context_snapshot:
            system_prompt = f"{_SYSTEM_PROMPT}\n\n{state.context_snapshot}"

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
        all_tool_data: list[dict] = []

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
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

                # Accumulate all tool data for InsightGenerator
                if result["row_count"] > 0:
                    all_tool_data.extend(result["data"])

                # Keep last tool result accessible from state
                if result["row_count"] > 0:
                    state.query_result = result["data"]
                    state.validated_sql = result["sql"]
                    state.row_count = result["row_count"]

            self.log(f"Iteration {iteration + 1}: {len(msg.tool_calls)} tool(s) called")

        state.tool_calls = tool_calls_log
        # Expose all tool data so InsightGenerator can see results from every call
        if all_tool_data:
            state.query_result = all_tool_data
            state.row_count = len(all_tool_data)
        return state

    # ── Anthropic ─────────────────────────────────────────────────────────────

    def _run_anthropic(self, state: AgentState, db_engine: Engine, system_prompt: str) -> AgentState:
        anthropic_tools = to_anthropic_tools(TOOL_DEFINITIONS)
        messages: list[dict] = [{"role": "user", "content": state.query}]
        tool_calls_log: list[dict] = []
        seen_calls: set[tuple] = set()
        all_tool_data: list[dict] = []

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                tools=anthropic_tools,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                text_blocks = [b.text for b in response.content if hasattr(b, "text")]
                state.insights = " ".join(text_blocks)
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                arguments = block.input or {}

                call_key = (tool_name, json.dumps(arguments, sort_keys=True))
                if call_key in seen_calls:
                    self.log(f"Duplicate tool call detected: '{tool_name}' — injecting stop hint", level="warning")
                    tool_results.append({
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

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(result["data"][:50], default=str),
                })

                if result["row_count"] > 0:
                    all_tool_data.extend(result["data"])
                    state.query_result = result["data"]
                    state.validated_sql = result["sql"]
                    state.row_count = result["row_count"]

            messages.append({"role": "user", "content": tool_results})
            self.log(f"Iteration {iteration + 1}: {len(tool_results)} tool(s) called")

        state.tool_calls = tool_calls_log
        if all_tool_data:
            state.query_result = all_tool_data
            state.row_count = len(all_tool_data)
        return state
