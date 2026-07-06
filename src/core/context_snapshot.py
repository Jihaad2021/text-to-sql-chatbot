"""
context_snapshot — builds a compact narrative of the current data period.

Injected into InsightGenerator, AnalyticsAgent, and any LLM prompt that needs
to know "what's happening now" without generating SQL first.

Sections produced:
  - Monthly overview + MoM comparison vs previous month
  - SR quality summary (avg, min, max, days below threshold)
  - DoD: today vs yesterday
  - Top 5 partners with MoM growth and SEHAT/PERHATIAN/KRITIS verdict
  - Top 5 products with MoM growth
  - Channel distribution (with human-readable names)
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.core.baseline_cache import BaselineCache

# Channel code → human-readable name
_CHANNEL_NAMES: dict[str, str] = {
    "i1": "MyTelkomsel App",
    "ig": "MyTelkomsel Basic",
    "f0": "UMB",
    "f4": "UMB",
    "f5": "UMB",
    "b0": "WEC",
    "b3": "WEC",
    "a0": "WEC",
}


def build_context_snapshot(engine: Engine, baseline: BaselineCache) -> str:
    """
    Return a compact narrative string describing the current data period.

    Covers: latest date, monthly totals, MoM growth, SR range, DoD,
    momentum signal, streak, hourly peak, pace projection,
    top partners + products (with SR) + channel distribution.
    """
    with engine.connect() as conn:
        latest       = _get_latest_date(conn)
        monthly      = _get_current_month_totals(conn, latest)
        prev_monthly = _get_prev_month_totals(conn, latest)
        partners     = _get_top_partners(conn, latest)
        channels     = _get_channel_split(conn, latest)
        products     = _get_top_products(conn, latest)
        sr_range     = _get_sr_daily_range(conn, latest)
        dod          = _get_dod_summary(conn, latest)
        momentum     = _get_momentum_signal(conn, latest)
        streak       = _get_decline_streak(conn, latest)
        hourly       = _get_hourly_peak(conn, latest)

    parts = [
        f"=== SNAPSHOT DATA TERKINI (s.d. {latest}) ===",
        "",
        _build_monthly_section(monthly, baseline),
        "",
        _build_mom_section(monthly, prev_monthly),
        "",
        _build_momentum_section(momentum, streak, monthly),
        "",
        _build_sr_section(sr_range),
        "",
        _build_dod_section(dod),
        "",
        _build_hourly_section(hourly),
        "",
        _build_partner_section(partners, baseline),
        "",
        _build_product_section(products),
        "",
        _build_channel_section(channels),
    ]
    return "\n".join(p for p in parts if p is not None)


# ── section builders ──────────────────────────────────────────────────────────

def _build_monthly_section(monthly: dict, baseline: BaselineCache) -> str:
    trx       = monthly.get("total_trx", 0)
    rev       = monthly.get("total_revenue", 0)
    days      = monthly.get("days", 1)
    sr        = monthly.get("success_rate", 0)
    daily_avg = trx / days if days else 0
    b         = baseline.overall

    trx_vs = ""
    if b.get("trx_mean"):
        pct = (daily_avg - b["trx_mean"]) / b["trx_mean"] * 100
        label     = baseline.classify_change(pct)
        direction = "di atas" if pct >= 0 else "di bawah"
        trx_vs    = f" ({direction} baseline harian {pct:+.1f}%, {label})"

    return (
        f"Bulan berjalan ({monthly.get('month', '')}): "
        f"{_fmt_trx(trx)} transaksi total, "
        f"Rp {_fmt_rev(rev)}, SR {sr:.1f}%, "
        f"{days} hari data.\n"
        f"Rata-rata harian: {_fmt_trx(daily_avg)} transaksi{trx_vs}."
    )


def _build_mom_section(monthly: dict, prev_monthly: dict) -> str:
    if not prev_monthly or not monthly:
        return ""

    curr_days = monthly.get("days", 1) or 1
    prev_days = prev_monthly.get("days", 1) or 1

    curr_daily_trx = monthly.get("total_trx", 0) / curr_days
    prev_daily_trx = prev_monthly.get("total_trx", 0) / prev_days
    curr_daily_rev = monthly.get("total_revenue", 0) / curr_days
    prev_daily_rev = prev_monthly.get("total_revenue", 0) / prev_days

    vol_wow = (curr_daily_trx - prev_daily_trx) / prev_daily_trx * 100 if prev_daily_trx else 0
    rev_wow = (curr_daily_rev - prev_daily_rev) / prev_daily_rev * 100 if prev_daily_rev else 0
    sr_wow  = monthly.get("success_rate", 0) - prev_monthly.get("success_rate", 0)

    vol_v = "SEHAT" if vol_wow > 0 else ("PERHATIAN" if vol_wow >= -10 else "KRITIS")
    rev_v = "SEHAT" if rev_wow > 0 else ("PERHATIAN" if rev_wow >= -10 else "KRITIS")
    sr    = monthly.get("success_rate", 0)
    sr_v  = "SEHAT" if sr > 98 else ("PERHATIAN" if sr >= 95 else "KRITIS")

    prev_month = prev_monthly.get("month", "bulan lalu")
    return (
        f"MoM vs {prev_month} (rata-rata harian ternormalisasi):\n"
        f"  Volume: {vol_wow:+.1f}% [{vol_v}]  "
        f"Revenue: {rev_wow:+.1f}% [{rev_v}]  "
        f"SR: {sr_wow:+.2f}pp [{sr_v}]"
    )


def _build_sr_section(sr: dict) -> str:
    if not sr:
        return ""
    avg     = sr.get("sr_avg", 0)
    verdict = "SEHAT" if avg > 98 else ("PERHATIAN" if avg >= 95 else "KRITIS")
    b98     = sr.get("days_below_98", 0)
    b95     = sr.get("days_below_95", 0)
    warn    = ""
    if b95:
        warn = f" ⚠ {b95} hari SR<95% (KRITIS)"
    elif b98:
        warn = f" ⚑ {b98} hari SR<98% (PERHATIAN)"
    return (
        f"SR bulan ini: avg {avg:.1f}% [{verdict}], "
        f"min {sr.get('sr_min', 0):.1f}%, max {sr.get('sr_max', 0):.1f}%{warn}"
    )


def _build_dod_section(dod: dict) -> str:
    if not dod:
        return ""
    vol_dod = dod.get("vol_dod_pct", 0)
    rev_dod = dod.get("rev_dod_pct", 0)
    verdict = "SEHAT" if abs(vol_dod) < 20 else ("PERHATIAN" if abs(vol_dod) < 40 else "KRITIS")
    arrow   = "↑" if vol_dod >= 0 else "↓"
    return (
        f"Hari terakhir ({dod.get('today_date', '')} vs {dod.get('yest_date', '')}):\n"
        f"  Transaksi: {_fmt_trx(dod.get('today_trx', 0))} ({vol_dod:+.1f}% DoD {arrow}) [{verdict}]\n"
        f"  Revenue: Rp {_fmt_rev(dod.get('today_rev', 0))} ({rev_dod:+.1f}% DoD)"
    )


def _build_momentum_section(momentum: dict, streak: dict, monthly: dict) -> str:
    if not momentum:
        return ""
    early  = momentum.get("early_avg", 0)
    recent = momentum.get("recent_avg", 0)
    pct    = (recent - early) / early * 100 if early else 0
    direction = "membaik" if pct > 0 else ("memburuk" if pct < 0 else "stabil")
    verdict   = "SEHAT" if pct > 0 else ("PERHATIAN" if pct >= -10 else "KRITIS")

    # Pace projection
    days_elapsed = monthly.get("days", 1) or 1
    total_trx    = monthly.get("total_trx", 0)
    daily_avg    = total_trx / days_elapsed if days_elapsed else 0
    # Assume 30 days per month for projection
    projected    = int(daily_avg * 30) if daily_avg else 0

    streak_days = streak.get("streak", 0)
    streak_v    = "SEHAT" if streak_days <= 1 else ("PERHATIAN" if streak_days <= 3 else "KRITIS")

    lines = [
        f"Momentum (7 hari terakhir vs 7 hari pertama bulan ini): {pct:+.1f}% → tren {direction} [{verdict}]",
        f"Streak turun berturut-turut: {streak_days} hari [{streak_v}]",
        f"Proyeksi pace akhir bulan: ~{_fmt_trx(projected)} transaksi (rata-rata {_fmt_trx(daily_avg)}/hari × 30 hari)",
    ]
    return "\n".join(lines)


def _build_hourly_section(hourly: dict) -> str:
    if not hourly:
        return ""
    peak_h    = hourly.get("peak_hour", 0)
    peak_pct  = hourly.get("peak_pct", 0)
    wd_avg    = hourly.get("weekday_avg", 0)
    we_avg    = hourly.get("weekend_avg", 0)
    wd_we_pct = (wd_avg - we_avg) / we_avg * 100 if we_avg else 0
    return (
        f"Pola transaksi harian: puncak jam {peak_h:02d}:00 ({peak_pct:.1f}% transaksi harian). "
        f"Weekday avg {_fmt_trx(wd_avg)}, weekend avg {_fmt_trx(we_avg)} "
        f"({wd_we_pct:+.1f}% weekday vs weekend)."
    )


def _build_partner_section(partners: list[dict], baseline: BaselineCache) -> str:
    lines = ["Top 5 partner bulan ini:"]
    for p in partners[:5]:
        name  = p["partner"]
        trx   = p["total_trx"]
        share = p["share_pct"]
        mom   = p.get("mom_growth")
        note  = ""
        if mom is not None:
            arrow   = "↑" if mom >= 0 else "↓"
            verdict = "SEHAT" if mom > 0 else ("PERHATIAN" if mom >= -10 else "KRITIS")
            note    = f" {arrow}{abs(mom):.1f}%MoM [{verdict}]"
        else:
            # Fallback: use baseline comparison
            b = baseline.partner.get(name)
            if b and b.get("trx_mean", 0) > 0:
                daily_avg = trx / max(p.get("days", 1), 1)
                pct = (daily_avg - b["trx_mean"]) / b["trx_mean"] * 100
                if abs(pct) >= 15:
                    label = baseline.classify_change(pct)
                    arrow = "↑" if pct > 0 else "↓"
                    note  = f" [{arrow}{abs(pct):.0f}% vs baseline, {label}]"
        lines.append(f"  {name}: {_fmt_trx(trx)} trx ({share:.1f}%){note}")
    return "\n".join(lines)


def _build_product_section(products: list[dict]) -> str:
    if not products:
        return ""
    lines = ["Top 5 produk bulan ini:"]
    sr_violations = []
    for p in products:
        name  = p["product_name"]
        trx   = p["total_trx"]
        share = p["share_pct"]
        mom   = p.get("mom_growth")
        sr    = p.get("sr")
        mom_str = ""
        if mom is not None:
            arrow   = "↑" if mom >= 0 else "↓"
            mom_str = f" {arrow}{abs(mom):.1f}%MoM"
        sr_str = f" SR {sr:.1f}%" if sr is not None else ""
        sr_flag = " ⚠" if sr is not None and sr < 98 else ""
        lines.append(f"  {name}: {_fmt_trx(trx)} trx ({share:.1f}%){mom_str}{sr_str}{sr_flag}")
        if sr is not None and sr < 95:
            sr_violations.append(f"{name} ({sr:.1f}%)")
    if sr_violations:
        lines.append(f"  ⚠ SR KRITIS (<95%): {', '.join(sr_violations)}")
    return "\n".join(lines)


def _build_channel_section(channels: list[dict]) -> str:
    lines = ["Distribusi channel bulan ini:"]
    for c in channels:
        code    = c["channel"]
        label   = _CHANNEL_NAMES.get(code, code)
        display = f"{label} ({code})" if label != code else code
        share   = c["share_pct"]
        trx     = c["total_trx"]
        lines.append(f"  {display}: {_fmt_trx(trx)} trx ({share:.1f}%)")
    return "\n".join(lines)


# ── data queries ──────────────────────────────────────────────────────────────

def _get_latest_date(conn) -> str:
    row = conn.execute(text("SELECT MAX(date)::date FROM daily_master")).fetchone()
    return str(row[0])


def _get_current_month_totals(conn, latest_date: str) -> dict:
    row = conn.execute(text("""
        SELECT
            TO_CHAR(date, 'YYYY-MM')                                               AS month,
            SUM(total_trx)                                                          AS total_trx,
            SUM(total_revenue)                                                      AS total_revenue,
            ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate,
            COUNT(DISTINCT date::date)                                              AS days
        FROM daily_master
        WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
        GROUP BY TO_CHAR(date, 'YYYY-MM')
    """), {"d": latest_date}).fetchone()
    if not row:
        return {}
    return {
        "month":         row[0],
        "total_trx":     float(row[1] or 0),
        "total_revenue": float(row[2] or 0),
        "success_rate":  float(row[3] or 0),
        "days":          int(row[4] or 1),
    }


def _get_prev_month_totals(conn, latest_date: str) -> dict:
    row = conn.execute(text("""
        SELECT
            TO_CHAR(date, 'YYYY-MM')                                               AS month,
            SUM(total_trx)                                                          AS total_trx,
            SUM(total_revenue)                                                      AS total_revenue,
            ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate,
            COUNT(DISTINCT date::date)                                              AS days
        FROM daily_master
        WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(
            (CAST(:d AS date) - INTERVAL '1 month'), 'YYYY-MM')
        GROUP BY TO_CHAR(date, 'YYYY-MM')
    """), {"d": latest_date}).fetchone()
    if not row:
        return {}
    return {
        "month":         row[0],
        "total_trx":     float(row[1] or 0),
        "total_revenue": float(row[2] or 0),
        "success_rate":  float(row[3] or 0),
        "days":          int(row[4] or 1),
    }


def _get_sr_daily_range(conn, latest_date: str) -> dict:
    row = conn.execute(text("""
        SELECT
            MIN(success_rate_pct)                                    AS sr_min,
            MAX(success_rate_pct)                                    AS sr_max,
            ROUND(AVG(success_rate_pct)::numeric, 2)                AS sr_avg,
            COUNT(*)                                                  AS days,
            SUM(CASE WHEN success_rate_pct < 95 THEN 1 ELSE 0 END)  AS days_below_95,
            SUM(CASE WHEN success_rate_pct < 98 THEN 1 ELSE 0 END)  AS days_below_98
        FROM daily_master
        WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
    """), {"d": latest_date}).fetchone()
    if not row:
        return {}
    return {
        "sr_min":        float(row[0] or 0),
        "sr_max":        float(row[1] or 0),
        "sr_avg":        float(row[2] or 0),
        "days":          int(row[3] or 0),
        "days_below_95": int(row[4] or 0),
        "days_below_98": int(row[5] or 0),
    }


def _get_top_partners(conn, latest_date: str) -> list[dict]:
    rows = conn.execute(text("""
        WITH curr AS (
            SELECT
                partner_group,
                SUM(total_trx)              AS total_trx,
                SUM(total_revenue)          AS total_revenue,
                COUNT(DISTINCT date::date)  AS days
            FROM daily_master
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY partner_group
        ),
        prev AS (
            SELECT
                partner_group,
                SUM(total_trx)             AS total_trx_prev,
                COUNT(DISTINCT date::date) AS days_prev
            FROM daily_master
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(
                (CAST(:d AS date) - INTERVAL '1 month'), 'YYYY-MM')
            GROUP BY partner_group
        ),
        total AS (SELECT SUM(total_trx) AS grand FROM curr)
        SELECT
            c.partner_group,
            c.total_trx,
            c.days,
            ROUND(c.total_trx::numeric / NULLIF(t.grand, 0) * 100, 1) AS share_pct,
            CASE
                WHEN p.total_trx_prev > 0 AND p.days_prev > 0 AND c.days > 0 THEN
                    ROUND(
                        ((c.total_trx::numeric / c.days) - (p.total_trx_prev::numeric / p.days_prev))
                        / (p.total_trx_prev::numeric / p.days_prev) * 100, 1)
                ELSE NULL
            END AS mom_growth_pct
        FROM curr c
        CROSS JOIN total t
        LEFT JOIN prev p ON p.partner_group = c.partner_group
        ORDER BY c.total_trx DESC
        LIMIT 10
    """), {"d": latest_date}).fetchall()
    return [
        {
            "partner":    r[0],  # kept as "partner" key for downstream compat
            "total_trx":  float(r[1] or 0),
            "days":       int(r[2] or 1),
            "share_pct":  float(r[3] or 0),
            "mom_growth": float(r[4]) if r[4] is not None else None,
        }
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


def _get_top_products(conn, latest_date: str) -> list[dict]:
    rows = conn.execute(text("""
        WITH curr AS (
            SELECT
                product_name,
                SUM(total_trx)             AS total_trx,
                SUM(total_revenue)         AS total_revenue,
                SUM(success_trx)           AS success_trx,
                COUNT(DISTINCT date::date) AS days
            FROM product_summary
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY product_name
        ),
        prev AS (
            SELECT
                product_name,
                SUM(total_trx)             AS total_trx_prev,
                COUNT(DISTINCT date::date) AS days_prev
            FROM product_summary
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(
                (CAST(:d AS date) - INTERVAL '1 month'), 'YYYY-MM')
            GROUP BY product_name
        ),
        total AS (SELECT SUM(total_trx) AS grand FROM curr)
        SELECT
            c.product_name,
            c.total_trx,
            c.total_revenue,
            ROUND(c.total_trx::numeric / NULLIF(t.grand, 0) * 100, 1) AS share_pct,
            CASE
                WHEN p.total_trx_prev > 0 AND p.days_prev > 0 AND c.days > 0 THEN
                    ROUND(
                        ((c.total_trx::numeric / c.days) - (p.total_trx_prev::numeric / p.days_prev))
                        / (p.total_trx_prev::numeric / p.days_prev) * 100, 1)
                ELSE NULL
            END AS mom_growth_pct,
            ROUND((c.success_trx::numeric / NULLIF(c.total_trx, 0)) * 100, 2) AS sr_pct
        FROM curr c
        CROSS JOIN total t
        LEFT JOIN prev p ON p.product_name = c.product_name
        ORDER BY c.total_trx DESC
        LIMIT 5
    """), {"d": latest_date}).fetchall()
    return [
        {
            "product_name":  r[0],
            "total_trx":     float(r[1] or 0),
            "total_revenue": float(r[2] or 0),
            "share_pct":     float(r[3] or 0),
            "mom_growth":    float(r[4]) if r[4] is not None else None,
            "sr":            float(r[5]) if r[5] is not None else None,
        }
        for r in rows
    ]


def _get_momentum_signal(conn, latest_date: str) -> dict:
    """Compare avg daily volume of first 7 days vs last 7 days of current month."""
    row = conn.execute(text("""
        WITH ordered AS (
            SELECT date::date, SUM(total_trx) AS day_trx,
                   ROW_NUMBER() OVER (ORDER BY date::date ASC)  AS rn_asc,
                   ROW_NUMBER() OVER (ORDER BY date::date DESC) AS rn_desc
            FROM daily_master
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY date::date
        )
        SELECT
            AVG(CASE WHEN rn_asc  <= 7 THEN day_trx END) AS early_avg,
            AVG(CASE WHEN rn_desc <= 7 THEN day_trx END) AS recent_avg
        FROM ordered
    """), {"d": latest_date}).fetchone()
    if not row or row[0] is None or row[1] is None:
        return {}
    return {"early_avg": float(row[0]), "recent_avg": float(row[1])}


def _get_decline_streak(conn, latest_date: str) -> dict:
    """Count consecutive days of volume decline (today < yesterday) from the most recent day."""
    rows = conn.execute(text("""
        SELECT date::date, SUM(total_trx) AS day_trx
        FROM daily_master
        WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
        GROUP BY date::date
        ORDER BY date::date DESC
        LIMIT 14
    """), {"d": latest_date}).fetchall()
    if len(rows) < 2:
        return {"streak": 0}
    streak = 0
    for i in range(len(rows) - 1):
        if float(rows[i][1] or 0) < float(rows[i + 1][1] or 0):
            streak += 1
        else:
            break
    return {"streak": streak}


def _get_hourly_peak(conn, latest_date: str) -> dict:
    """Get peak transaction hour and weekday/weekend averages from hourly_pattern_daily."""
    # Peak hour for current month
    peak_row = conn.execute(text("""
        SELECT hour,
               ROUND(AVG(total_trx)::numeric, 0) AS avg_trx
        FROM hourly_pattern_daily
        WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
        GROUP BY hour
        ORDER BY avg_trx DESC
        LIMIT 1
    """), {"d": latest_date}).fetchone()

    # Weekday vs weekend daily totals
    wdwe_row = conn.execute(text("""
        SELECT
            AVG(CASE WHEN EXTRACT(DOW FROM date::date) BETWEEN 1 AND 5 THEN day_trx END) AS wd_avg,
            AVG(CASE WHEN EXTRACT(DOW FROM date::date) IN (0, 6)         THEN day_trx END) AS we_avg
        FROM (
            SELECT date::date, SUM(total_trx) AS day_trx
            FROM daily_master
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY date::date
        ) d
    """), {"d": latest_date}).fetchone()

    if not peak_row:
        return {}

    peak_trx = float(peak_row[1] or 0)

    # Estimate peak_pct from hourly data (peak hour avg / sum of all hour avgs)
    total_hourly_row = conn.execute(text("""
        SELECT SUM(avg_trx) FROM (
            SELECT ROUND(AVG(total_trx)::numeric, 0) AS avg_trx
            FROM hourly_pattern_daily
            WHERE TO_CHAR(date, 'YYYY-MM') = TO_CHAR(CAST(:d AS date), 'YYYY-MM')
            GROUP BY hour
        ) h
    """), {"d": latest_date}).fetchone()

    total_hourly = float(total_hourly_row[0] or 1) if total_hourly_row else 1
    peak_pct = peak_trx / total_hourly * 100 if total_hourly else 0

    return {
        "peak_hour":   int(peak_row[0]),
        "peak_pct":    round(peak_pct, 1),
        "weekday_avg": float(wdwe_row[0] or 0) if wdwe_row else 0,
        "weekend_avg": float(wdwe_row[1] or 0) if wdwe_row else 0,
    }


def _get_dod_summary(conn, latest_date: str) -> dict:
    rows = conn.execute(text("""
        SELECT date::date, SUM(total_trx) AS total_trx, SUM(total_revenue) AS total_revenue
        FROM daily_master
        WHERE date::date IN (
            CAST(:d AS date),
            CAST(:d AS date) - INTERVAL '1 day'
        )
        GROUP BY date::date
        ORDER BY date::date DESC
        LIMIT 2
    """), {"d": latest_date}).fetchall()
    if len(rows) < 2:
        return {}
    today_trx = float(rows[0][1] or 0)
    yest_trx  = float(rows[1][1] or 0)
    today_rev = float(rows[0][2] or 0)
    yest_rev  = float(rows[1][2] or 0)
    return {
        "today_date":  str(rows[0][0]),
        "yest_date":   str(rows[1][0]),
        "today_trx":   today_trx,
        "yest_trx":    yest_trx,
        "today_rev":   today_rev,
        "yest_rev":    yest_rev,
        "vol_dod_pct": (today_trx - yest_trx) / yest_trx * 100 if yest_trx else 0,
        "rev_dod_pct": (today_rev - yest_rev) / yest_rev * 100 if yest_rev else 0,
    }


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
