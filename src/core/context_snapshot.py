"""
context_snapshot — builds a compact narrative of the current data period.

Injected into InsightGenerator, AnalyticsAgent, and any LLM prompt that needs
to know "what's happening now" without generating SQL first.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.core.baseline_cache import BaselineCache


def build_context_snapshot(engine: Engine, baseline: BaselineCache) -> str:
    """
    Return a ~800-char narrative string describing the current data period.

    Covers: latest date, monthly totals, top partners, channel distribution,
    and whether key metrics are above/below baseline.
    """
    with engine.connect() as conn:
        latest   = _get_latest_date(conn)
        monthly  = _get_current_month_totals(conn, latest)
        partners = _get_top_partners(conn, latest)
        channels = _get_channel_split(conn, latest)

    parts = [
        f"=== SNAPSHOT DATA TERKINI (s.d. {latest}) ===",
        "",
        _build_monthly_section(monthly, baseline),
        "",
        _build_partner_section(partners, baseline),
        "",
        _build_channel_section(channels, baseline),
    ]
    return "\n".join(parts)


# ── section builders ──────────────────────────────────────────────────────────

def _build_monthly_section(monthly: dict, baseline: BaselineCache) -> str:
    trx = monthly.get("total_trx", 0)
    rev = monthly.get("total_revenue", 0)
    days = monthly.get("days", 1)
    sr  = monthly.get("success_rate", 0)

    daily_trx_avg = trx / days if days else 0
    b = baseline.overall

    trx_vs = ""
    if b.get("trx_mean"):
        pct = (daily_trx_avg - b["trx_mean"]) / b["trx_mean"] * 100
        label = baseline.classify_change(pct)
        direction = "di atas" if pct >= 0 else "di bawah"
        trx_vs = f" ({direction} baseline harian {pct:+.1f}%, {label})"

    return (
        f"Bulan berjalan ({monthly.get('month', '')}): "
        f"{_fmt_trx(trx)} transaksi total, "
        f"Rp {_fmt_rev(rev)}, SR {sr:.1f}%, "
        f"{days} hari data.\n"
        f"Rata-rata harian: {_fmt_trx(daily_trx_avg)} transaksi{trx_vs}."
    )


def _build_partner_section(partners: list[dict], baseline: BaselineCache) -> str:
    lines = ["Top 5 partner bulan ini:"]
    for p in partners[:5]:
        name = p["partner"]
        trx  = p["total_trx"]
        share = p["share_pct"]
        b = baseline.partner.get(name)
        note = ""
        if b and b["trx_mean"] > 0:
            daily_avg = trx / max(p.get("days", 1), 1)
            pct = (daily_avg - b["trx_mean"]) / b["trx_mean"] * 100
            if abs(pct) >= 15:
                label = baseline.classify_change(pct)
                direction = "↑" if pct > 0 else "↓"
                note = f" [{direction}{abs(pct):.0f}% vs baseline, {label}]"
        lines.append(f"  {name}: {_fmt_trx(trx)} trx ({share:.1f}%){note}")
    return "\n".join(lines)


def _build_channel_section(channels: list[dict], baseline: BaselineCache) -> str:
    lines = ["Distribusi channel bulan ini:"]
    for c in channels:
        name  = c["channel"]
        share = c["share_pct"]
        trx   = c["total_trx"]
        lines.append(f"  {name}: {_fmt_trx(trx)} trx ({share:.1f}%)")
    return "\n".join(lines)


# ── data queries ──────────────────────────────────────────────────────────────

def _get_latest_date(conn) -> str:
    row = conn.execute(text("SELECT MAX(date)::date FROM daily_master")).fetchone()
    return str(row[0])


def _get_current_month_totals(conn, latest_date: str) -> dict:
    row = conn.execute(text("""
        SELECT
            TO_CHAR(date, 'YYYY-MM')                                             AS month,
            SUM(total_trx)                                                        AS total_trx,
            SUM(total_revenue)                                                    AS total_revenue,
            ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate,
            COUNT(DISTINCT date::date)                                            AS days
        FROM daily_master
        WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
        GROUP BY TO_CHAR(date, 'YYYY-MM')
    """), {"d": latest_date}).fetchone()
    if not row:
        return {}
    return {
        "month":        row[0],
        "total_trx":    float(row[1] or 0),
        "total_revenue":float(row[2] or 0),
        "success_rate": float(row[3] or 0),
        "days":         int(row[4] or 1),
    }


def _get_top_partners(conn, latest_date: str) -> list[dict]:
    rows = conn.execute(text("""
        WITH monthly AS (
            SELECT
                partner,
                SUM(total_trx)              AS total_trx,
                COUNT(DISTINCT date::date)  AS days
            FROM daily_master
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY partner
        ),
        total AS (SELECT SUM(total_trx) AS grand FROM monthly)
        SELECT m.partner, m.total_trx, m.days,
               ROUND(m.total_trx::numeric / NULLIF(t.grand, 0) * 100, 1) AS share_pct
        FROM monthly m, total t
        ORDER BY m.total_trx DESC
        LIMIT 10
    """), {"d": latest_date}).fetchall()
    return [
        {"partner": r[0], "total_trx": float(r[1] or 0),
         "days": int(r[2] or 1), "share_pct": float(r[3] or 0)}
        for r in rows
    ]


def _get_channel_split(conn, latest_date: str) -> list[dict]:
    rows = conn.execute(text("""
        WITH monthly AS (
            SELECT channel, SUM(total_trx) AS total_trx
            FROM channel_payment
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY channel
        ),
        total AS (SELECT SUM(total_trx) AS grand FROM monthly)
        SELECT m.channel, m.total_trx,
               ROUND(m.total_trx::numeric / NULLIF(t.grand, 0) * 100, 1) AS share_pct
        FROM monthly m, total t
        ORDER BY m.total_trx DESC
    """), {"d": latest_date}).fetchall()
    return [
        {"channel": r[0], "total_trx": float(r[1] or 0), "share_pct": float(r[2] or 0)}
        for r in rows
    ]


# ── formatters ────────────────────────────────────────────────────────────────

def _fmt_trx(n: float) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}jt"
    if n >= 1_000:
        return f"{n/1_000:.1f}rb"
    return str(int(n))


def _fmt_rev(n: float) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f} miliar"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f} juta"
    return f"{int(n):,}"
