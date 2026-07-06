"""
context_distiller — dynamic enrichment of query results before InsightGenerator.

Analyzes state.query_result after data retrieval and appends a Markdown narrative
with ranked highlights, anomaly flags, cross-metric correlations, and a domain
glossary. The output is appended to state.context_snapshot so InsightGenerator
can reference concrete findings without re-deriving them from raw numbers.

Reads from state:
    - state.query_result
    - state.query (for glossary term matching)

Returns:
    str — Markdown context block, or "" if data is insufficient
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from src.models.agent_state import AgentState

_MAX_DISTILLER_ROWS = 100

# Maps column name fragments to Indonesian domain definitions
_GLOSSARY: dict[str, str] = {
    "sr": "Success Rate — persentase transaksi berhasil dari total transaksi",
    "success_rate": "Success Rate — persentase transaksi berhasil dari total transaksi",
    "gmv": "Gross Merchandise Value — total nilai transaksi sebelum biaya",
    "revenue": "pendapatan bersih Telkomsel dari transaksi yang berhasil (dalam Rupiah)",
    "total_trx": "total jumlah transaksi mencakup transaksi sukses dan gagal",
    "total_revenue": "total pendapatan dalam Rupiah dari seluruh transaksi sukses",
    "partner": "perusahaan mitra yang memproses transaksi melalui platform Telkomsel",
    "channel": "saluran pembayaran yang digunakan (OVO, GoPay, DANA, LinkAja, dll.)",
    "selisih": "selisih antara nilai aktual dan nilai ekspektasi atau baseline",
    "delta": "perubahan nilai antara dua periode atau dua entitas pembanding",
    "fail_trx": "jumlah transaksi yang gagal atau ditolak",
    "fail_rate": "persentase transaksi gagal dari total transaksi",
    "settlement": "proses kliring dan pemindahan dana antar pihak setelah transaksi",
    "rekonsiliasi": "pencocokan data transaksi antara sistem Telkomsel dan mitra/bank",
}


def distill_context(state: AgentState) -> str:
    """
    Build enriched Markdown context from state.query_result.

    Returns empty string when data is empty or too sparse to analyze.
    Never raises — failures return "" so InsightGenerator still runs.
    """
    try:
        return _distill(state)
    except Exception:
        return ""


def _distill(state: AgentState) -> str:
    data = (state.query_result or [])[:_MAX_DISTILLER_ROWS]
    if not data or not isinstance(data[0], dict):
        return ""

    parts: list[str] = []

    highlights = _build_highlights(data)
    if highlights:
        parts.append("## HIGHLIGHT UTAMA\n" + highlights)

    correlations = _build_correlations(data)
    if correlations:
        parts.append("## KORELASI ANTAR METRIK\n" + correlations)

    glossary = _build_glossary(data, state.query)
    if glossary:
        parts.append("## GLOSSARY DOMAIN\n" + glossary)

    return "\n\n".join(parts)


# ── Highlights ────────────────────────────────────────────────────────────────

def _build_highlights(data: list[dict]) -> str:
    cols = list(data[0].keys())
    num_cols = _numeric_columns(data, cols)
    text_cols = [c for c in cols if c not in num_cols]
    date_cols = [c for c in cols if _is_date_col(c)]
    entity_col = text_cols[0] if text_cols else None
    is_time_series = bool(date_cols)

    lines: list[str] = []

    for col in num_cols[:3]:
        values = _extract_numeric(data, col)
        if len(values) < 2:
            continue
        _add_col_highlights(lines, col, values, data, entity_col, is_time_series)

    return "\n".join(lines)


def _add_col_highlights(
    lines: list[str],
    col: str,
    values: list[float],
    data: list[dict],
    entity_col: str | None,
    is_time_series: bool,
) -> None:
    label = _col_label(col)
    mean_val = statistics.mean(values)
    stdev_val = statistics.pstdev(values) if len(values) > 2 else 0.0
    max_val = max(values)
    min_val = min(values)
    max_row = data[values.index(max_val)]
    min_row = data[values.index(min_val)]

    if entity_col:
        lines.append(f"- **{label} tertinggi**: {_fmt(max_val)} ({max_row.get(entity_col, '')})")
        if not is_time_series:
            lines.append(f"- **{label} terendah**: {_fmt(min_val)} ({min_row.get(entity_col, '')})")
    else:
        lines.append(f"- **{label} tertinggi**: {_fmt(max_val)}")

    if stdev_val > 0:
        for i, (val, row) in enumerate(zip(values, data)):
            z = (val - mean_val) / stdev_val
            if abs(z) > 2:
                direction = "jauh di atas" if z > 0 else "jauh di bawah"
                entity = row.get(entity_col, f"baris {i + 1}") if entity_col else f"baris {i + 1}"
                lines.append(
                    f"- **Anomali {label}**: {entity} {direction} rata-rata "
                    f"({_fmt(val)} vs rata-rata {_fmt(mean_val)})"
                )

    if is_time_series and len(values) >= 3:
        trend = _detect_trend(values)
        if trend:
            lines.append(f"- **Tren {label}**: {trend}")

    if is_time_series and len(values) >= 2:
        first, last = values[0], values[-1]
        if first != 0:
            pct = (last - first) / abs(first) * 100
            direction = "naik" if pct > 0 else "turun"
            lines.append(f"- **Perubahan {label}** (awal→akhir): {direction} {abs(pct):.1f}%")

    if mean_val != 0:
        lines.append(f"- **Rata-rata {label}**: {_fmt(mean_val)}")


# ── Correlations ──────────────────────────────────────────────────────────────

def _build_correlations(data: list[dict]) -> str:
    cols = list(data[0].keys())
    num_cols = _numeric_columns(data, cols)

    if len(num_cols) < 2 or len(data) < 4:
        return ""

    lines: list[str] = []
    checked = min(len(num_cols), 4)

    for i in range(checked):
        for j in range(i + 1, checked):
            col_a, col_b = num_cols[i], num_cols[j]
            vals_a = _extract_numeric(data, col_a)
            vals_b = _extract_numeric(data, col_b)
            if len(vals_a) != len(vals_b) or len(vals_a) < 4:
                continue
            corr = _pearson(vals_a, vals_b)
            if corr is None:
                continue
            label_a, label_b = _col_label(col_a), _col_label(col_b)
            if corr > 0.8:
                lines.append(
                    f"- **{label_a} ↔ {label_b}**: bergerak searah "
                    f"(korelasi {corr:.2f}) — kenaikan {label_a} diikuti kenaikan {label_b}"
                )
            elif corr < -0.8:
                lines.append(
                    f"- **{label_a} ↔ {label_b}**: bergerak berlawanan "
                    f"(korelasi {corr:.2f}) — kenaikan {label_a} diikuti penurunan {label_b}"
                )

    return "\n".join(lines)


# ── Glossary ──────────────────────────────────────────────────────────────────

def _build_glossary(data: list[dict], query: str) -> str:
    col_names = " ".join(data[0].keys()).lower() if data else ""
    query_lower = query.lower()

    found: list[str] = []
    for term, definition in _GLOSSARY.items():
        if term in col_names or term in query_lower:
            found.append(f"- **{term.upper()}**: {definition}")
        if len(found) >= 6:
            break

    return "\n".join(found)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _numeric_columns(data: list[dict], cols: list[str]) -> list[str]:
    """Return columns where ≥70% of rows have numeric values."""
    result = []
    n = len(data)
    for col in cols:
        if sum(1 for row in data if _is_numeric(row.get(col))) / n >= 0.7:
            result.append(col)
    return result


def _is_numeric(val: Any) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return not (isinstance(val, float) and math.isnan(val))
    if isinstance(val, str):
        try:
            float(val.strip())
            return True
        except ValueError:
            return False
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False


def _extract_numeric(data: list[dict], col: str) -> list[float]:
    result: list[float] = []
    for row in data:
        val = row.get(col)
        if isinstance(val, bool):
            continue
        try:
            f = float(val)
            if not math.isnan(f):
                result.append(f)
        except (TypeError, ValueError):
            pass
    return result


def _is_date_col(col: str) -> bool:
    keywords = ("date", "tanggal", "periode", "bulan", "time", "tgl", "month", "year")
    return any(kw in col.lower() for kw in keywords)


def _col_label(col: str) -> str:
    return col.replace("_", " ").title()


def _fmt(n: float) -> str:
    """Format a number for human reading in Indonesian context."""
    abs_n = abs(n)
    if abs_n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}M"
    if abs_n >= 1_000_000:
        return f"{n / 1_000_000:.2f}jt"
    if abs_n >= 1_000:
        return f"{n / 1_000:.1f}rb"
    if isinstance(n, float) and n != int(n):
        return f"{n:.2f}"
    return f"{int(n):,}"


def _detect_trend(values: list[float]) -> str | None:
    """Linear regression slope as % of mean per period."""
    n = len(values)
    x_mean = (n - 1) / 2.0
    y_mean = statistics.mean(values)
    if y_mean == 0:
        return None
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return None
    slope_pct = (numerator / denominator) / abs(y_mean) * 100
    if slope_pct > 5:
        return f"naik konsisten ({slope_pct:+.1f}% per periode)"
    if slope_pct < -5:
        return f"turun konsisten ({slope_pct:+.1f}% per periode)"
    return "stabil (tidak ada tren signifikan)"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 4:
        return None
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return numerator / (den_x * den_y)
