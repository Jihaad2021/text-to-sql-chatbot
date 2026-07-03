"""
Tool Registry — schemas and dispatcher for AnalyticsAgent tool calling.

Defines tool definitions in OpenAI format and provides:
- TOOL_DEFINITIONS: list of tool schemas (OpenAI/OpenRouter/Gemini compatible)
- to_anthropic_tools(): convert to Anthropic tool format
- execute_tool(): dispatch tool name → analytics_tools function
"""

from sqlalchemy.engine import Engine

from src.tools.analytics_tools import (
    compare_periods,
    detect_anomaly,
    get_distribution,
    get_hourly_pattern,
    get_summary,
    get_trend,
)

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_summary",
            "description": (
                "Ambil total transaksi, revenue, dan success rate untuk periode tertentu. "
                "Gunakan ini sebagai langkah pertama untuk memahami gambaran umum."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_start": {"type": "string", "description": "Tanggal mulai (YYYY-MM-DD)"},
                    "period_end":   {"type": "string", "description": "Tanggal akhir (YYYY-MM-DD)"},
                    "dimension": {
                        "type": "string",
                        "enum": ["all", "partner", "channel", "product"],
                        "description": "Breakdown dimensi. 'all' = satu baris total.",
                    },
                },
                "required": ["period_start", "period_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": (
                "Bandingkan dua periode waktu dan hitung % perubahan per entitas, "
                "mencakup transaksi, revenue, DAN success rate (SR). "
                "Gunakan untuk pertanyaan tentang kenaikan/penurunan success rate (SR), "
                "transaksi, atau revenue antar periode."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_a_start": {"type": "string", "description": "Mulai periode A (YYYY-MM-DD)"},
                    "period_a_end":   {"type": "string", "description": "Akhir periode A (YYYY-MM-DD)"},
                    "period_b_start": {"type": "string", "description": "Mulai periode B/baseline (YYYY-MM-DD)"},
                    "period_b_end":   {"type": "string", "description": "Akhir periode B/baseline (YYYY-MM-DD)"},
                    "dimension": {
                        "type": "string",
                        "enum": ["partner", "channel", "product"],
                        "description": "Dimensi perbandingan.",
                    },
                },
                "required": ["period_a_start", "period_a_end", "period_b_start", "period_b_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_anomaly",
            "description": (
                "Deteksi entitas (partner/channel/produk) yang mengalami perubahan ekstrim "
                "pada suatu tanggal dibanding rata-rata 7 hari sebelumnya, "
                "mencakup transaksi, revenue, DAN success rate (SR). "
                "Gunakan untuk pertanyaan tentang lonjakan, penurunan tidak normal, "
                "atau anomali pada success rate (SR)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {"type": "string", "description": "Tanggal yang ingin diperiksa (YYYY-MM-DD)"},
                    "dimension": {
                        "type": "string",
                        "enum": ["partner", "channel", "product"],
                        "description": "Dimensi yang ingin diperiksa.",
                    },
                    "threshold_pct": {
                        "type": "number",
                        "description": "Threshold % perubahan untuk dianggap anomali. Default 30.",
                    },
                },
                "required": ["target_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trend",
            "description": (
                "Ambil tren transaksi, revenue, dan success rate (SR) sepanjang waktu "
                "(harian/mingguan/bulanan). "
                "Gunakan untuk melihat pola pergerakan metrik — termasuk SR — dari waktu ke waktu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date":   {"type": "string", "description": "Tanggal mulai (YYYY-MM-DD)"},
                    "end_date":     {"type": "string", "description": "Tanggal akhir (YYYY-MM-DD)"},
                    "dimension": {
                        "type": "string",
                        "enum": ["all", "partner", "channel"],
                        "description": "'all' = total keseluruhan. Partner/channel = top 5.",
                    },
                    "granularity": {
                        "type": "string",
                        "enum": ["daily", "weekly", "monthly"],
                        "description": "Granularitas waktu.",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_distribution",
            "description": (
                "Lihat kontribusi (%) setiap partner, channel, atau produk terhadap total. "
                "Gunakan untuk menjawab 'siapa yang paling berkontribusi'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_start": {"type": "string", "description": "Tanggal mulai (YYYY-MM-DD)"},
                    "period_end":   {"type": "string", "description": "Tanggal akhir (YYYY-MM-DD)"},
                    "dimension": {
                        "type": "string",
                        "enum": ["partner", "channel", "product"],
                        "description": "Dimensi distribusi.",
                    },
                },
                "required": ["period_start", "period_end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hourly_pattern",
            "description": (
                "Lihat pola transaksi per jam untuk satu tanggal tertentu. "
                "Gunakan untuk mengidentifikasi jam bermasalah dalam sehari."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {"type": "string", "description": "Tanggal yang ingin dilihat (YYYY-MM-DD)"},
                },
                "required": ["target_date"],
            },
        },
    },
]


def to_anthropic_tools(openai_tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool format to Anthropic tool format."""
    result = []
    for t in openai_tools:
        fn = t["function"]
        result.append({
            "name":         fn["name"],
            "description":  fn["description"],
            "input_schema": fn["parameters"],
        })
    return result


def execute_tool(name: str, arguments: dict, db_engine: Engine) -> dict:
    """Dispatch tool name to the corresponding analytics function."""
    dispatch: dict = {
        "get_summary":       get_summary,
        "compare_periods":   compare_periods,
        "detect_anomaly":    detect_anomaly,
        "get_trend":         get_trend,
        "get_distribution":  get_distribution,
        "get_hourly_pattern": get_hourly_pattern,
    }

    fn = dispatch.get(name)
    if fn is None:
        return {"data": [], "row_count": 0, "sql": "", "description": f"Unknown tool: {name}"}

    return fn(db_engine=db_engine, **arguments)
