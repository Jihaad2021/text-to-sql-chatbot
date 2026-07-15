"""
Analytics Tools — deterministic SQL functions for financial analytics.

Each tool executes pre-defined, tested SQL and returns structured data.
Called by AnalyticsAgent via tool calling; never generate SQL ad-hoc.

Return contract for all tools:
    {
        "data":        list[dict],   # query result rows
        "row_count":   int,
        "sql":         str,          # SQL that was executed
        "description": str,          # one-line summary of what was returned
    }
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Dimension → table/column/SR-formula reference map.
# DOCUMENTATION ONLY — not read by any SQL-generation code.
# All tools build their SQL independently (see each function below).
# Update this dict whenever a new dimension is added so the mapping
# stays visible in one place for grep/audit.
#
# sr_type values:
#   "raw_counts"     — table stores success_trx + total_trx; SR = SUM/SUM
#   "precomputed_avg"— table stores success_rate_pct directly; SR = AVG
#   None             — tool does not emit an SR column for this dimension
_DIMENSION_REGISTRY: dict[str, dict] = {
    # dimension  : table             entity_col      sr_type            notes
    "all"        : {"table": "daily_master",    "entity_col": None,            "sr_type": "raw_counts",      "tools": ["get_summary", "get_trend"]},
    "partner"    : {"table": "daily_master",    "entity_col": "partner_group", "sr_type": "raw_counts",      "tools": ["get_summary", "compare_periods", "detect_anomaly", "get_trend", "get_distribution"]},
    "channel"    : {"table": "channel_payment", "entity_col": "channel",       "sr_type": "precomputed_avg", "tools": ["get_summary", "compare_periods", "detect_anomaly", "get_trend", "get_distribution"]},
    "product"    : {"table": "product_summary", "entity_col": "product_name",  "sr_type": "raw_counts",      "tools": ["get_summary", "compare_periods", "detect_anomaly", "get_distribution"],
                    # product_name can be NULL → COALESCE(NULLIF(NULLIF(product_name,'NULL'),''),'[Tidak Teridentifikasi]')
                    # get_trend intentionally omitted: product_summary has no daily timeseries structure
                    "entity_expr": "COALESCE(NULLIF(NULLIF(product_name,'NULL'),''),'[Tidak Teridentifikasi]')"},
    # get_hourly_pattern has no dimension parameter; fixed to hourly_pattern_daily
    # with pre-computed hour/total_trx/success_rate_pct columns — excluded from registry.
}

# ── SQL templates ─────────────────────────────────────────────────────────────
# Plain strings (no f-string) so bandit B608 is not triggered on the template
# definitions. Identifiers ({table}, {entity_expr}, etc.) are substituted via
# .format() at call time — those callers verify the value against a whitelist
# before substituting. Data values use SQLAlchemy bound params (:period_start,
# :period_end, etc.) so they are never string-interpolated into SQL.

_SUMMARY_ALL_SQL = """
SELECT
    SUM(total_trx)     AS total_trx,
    SUM(total_revenue) AS total_revenue,
    ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate_pct
FROM daily_master
WHERE date >= :period_start AND date <= :period_end
"""

_SUMMARY_ENTITY_SQL = """
SELECT
    {entity_expr}                                                                         AS entity,
    SUM(total_trx)                                                                       AS total_trx,
    SUM(total_revenue)                                                                   AS total_revenue,
    {sr_expr}                                                                            AS success_rate_pct
FROM {table}
WHERE date >= :period_start AND date <= :period_end
GROUP BY {entity_expr}
ORDER BY total_trx DESC
LIMIT 50
"""

_COMPARE_SQL = """
WITH period_a AS (
    SELECT {entity_expr} AS entity,
           SUM(total_trx) AS trx_a, SUM(total_revenue) AS rev_a,
           {sr_agg} AS sr_a
    FROM {table}
    WHERE date >= :period_a_start AND date <= :period_a_end
    GROUP BY {entity_expr}
),
period_b AS (
    SELECT {entity_expr} AS entity,
           SUM(total_trx) AS trx_b, SUM(total_revenue) AS rev_b,
           {sr_agg} AS sr_b
    FROM {table}
    WHERE date >= :period_b_start AND date <= :period_b_end
    GROUP BY {entity_expr}
)
SELECT
    COALESCE(a.entity, b.entity)                                                              AS entity,
    COALESCE(a.trx_a, 0)                                                                      AS trx_a,
    COALESCE(b.trx_b, 0)                                                                      AS trx_b,
    ROUND((COALESCE(a.trx_a,0) - COALESCE(b.trx_b,0))::numeric
          / NULLIF(b.trx_b::numeric, 0) * 100, 2)                                             AS trx_pct_change,
    COALESCE(a.rev_a, 0)                                                                      AS rev_a,
    COALESCE(b.rev_b, 0)                                                                      AS rev_b,
    ROUND((COALESCE(a.rev_a,0) - COALESCE(b.rev_b,0))::numeric
          / NULLIF(b.rev_b::numeric, 0) * 100, 2)                                             AS rev_pct_change,
    a.sr_a                                                                                     AS sr_a,
    b.sr_b                                                                                     AS sr_b,
    ROUND(COALESCE(a.sr_a, 0) - COALESCE(b.sr_b, 0), 2)                                       AS sr_pct_change
FROM period_a a
FULL OUTER JOIN period_b b USING (entity)
ORDER BY ABS(ROUND((COALESCE(a.trx_a,0) - COALESCE(b.trx_b,0))::numeric
             / NULLIF(b.trx_b::numeric, 0) * 100, 2)) DESC NULLS LAST
LIMIT 30
"""

_ANOMALY_SQL = """
WITH target AS (
    SELECT {entity_expr} AS entity,
           SUM(total_trx)     AS trx_target,
           SUM(total_revenue) AS rev_target,
           {sr_target_expr}   AS sr_target
    FROM {table}
    WHERE date::date = :target_date::date
    GROUP BY {entity_expr}
),
baseline AS (
    SELECT entity,
           ROUND(AVG(daily_trx)::numeric, 2) AS trx_baseline_avg,
           ROUND(AVG(daily_rev)::numeric, 2) AS rev_baseline_avg,
           ROUND(AVG(daily_sr)::numeric,  2) AS sr_baseline_avg
    FROM (
        SELECT {entity_expr} AS entity,
               date,
               SUM(total_trx)     AS daily_trx,
               SUM(total_revenue) AS daily_rev,
               {sr_daily_expr}
        FROM {table}
        WHERE date::date > (:target_date::date - INTERVAL '7 days')
          AND date::date < :target_date::date
        GROUP BY {entity_expr}, date
    ) d
    GROUP BY entity
)
SELECT
    t.entity,
    t.trx_target,
    b.trx_baseline_avg,
    ROUND((t.trx_target - b.trx_baseline_avg)::numeric / NULLIF(b.trx_baseline_avg, 0) * 100, 2) AS trx_pct_change,
    t.rev_target,
    b.rev_baseline_avg,
    ROUND((t.rev_target::numeric - b.rev_baseline_avg) / NULLIF(b.rev_baseline_avg, 0) * 100, 2)  AS rev_pct_change,
    t.sr_target,
    b.sr_baseline_avg,
    ROUND(t.sr_target - b.sr_baseline_avg, 2)                                                      AS sr_pct_change,
    ABS(ROUND((t.trx_target - b.trx_baseline_avg)::numeric / NULLIF(b.trx_baseline_avg, 0) * 100, 2)) > :threshold_pct AS is_anomaly
FROM target t
JOIN baseline b USING (entity)
ORDER BY ABS(ROUND((t.trx_target - b.trx_baseline_avg)::numeric / NULLIF(b.trx_baseline_avg, 0) * 100, 2)) DESC
LIMIT 30
"""

_TREND_ALL_SQL = """
SELECT
    {date_trunc}   AS period,
    SUM(total_trx)     AS total_trx,
    SUM(total_revenue) AS total_revenue,
    ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS success_rate_pct
FROM daily_master
WHERE date >= :start_date AND date <= :end_date
GROUP BY {date_trunc}
ORDER BY period
LIMIT 200
"""

_TREND_CHANNEL_SQL = """
WITH top5 AS (
    SELECT channel FROM channel_payment
    WHERE date >= :start_date AND date <= :end_date
    GROUP BY channel ORDER BY SUM(total_trx) DESC LIMIT 5
)
SELECT
    {date_trunc}                                                         AS period,
    cp.channel                                                           AS entity,
    SUM(cp.total_trx)                                                    AS total_trx,
    SUM(cp.total_revenue)                                                AS total_revenue,
    ROUND(AVG(cp.success_rate_pct)::numeric, 2)                          AS success_rate_pct
FROM channel_payment cp
JOIN top5 USING (channel)
WHERE cp.date >= :start_date AND cp.date <= :end_date
GROUP BY {date_trunc}, cp.channel
ORDER BY period, total_trx DESC
LIMIT 200
"""

_TREND_PARTNER_SQL = """
WITH top5 AS (
    SELECT partner_group FROM daily_master
    WHERE date >= :start_date AND date <= :end_date
    GROUP BY partner_group ORDER BY SUM(total_trx) DESC LIMIT 5
)
SELECT
    {date_trunc}                                                                               AS period,
    dm.partner_group                                                                           AS entity,
    SUM(dm.total_trx)                                                                          AS total_trx,
    SUM(dm.total_revenue)                                                                      AS total_revenue,
    ROUND((SUM(dm.success_trx)::numeric / NULLIF(SUM(dm.total_trx), 0)) * 100, 2)             AS success_rate_pct
FROM daily_master dm
JOIN top5 USING (partner_group)
WHERE dm.date >= :start_date AND dm.date <= :end_date
GROUP BY {date_trunc}, dm.partner_group
ORDER BY period, total_trx DESC
LIMIT 200
"""

_DIST_COUNT_SQL = """
SELECT COUNT(DISTINCT {entity_expr}) AS entity_count
FROM {table}
WHERE date >= :period_start AND date <= :period_end
"""

_DIST_SQL = """
WITH totals AS (
    SELECT SUM(total_trx) AS grand_trx, SUM(total_revenue) AS grand_rev
    FROM {table}
    WHERE date >= :period_start AND date <= :period_end
)
SELECT
    {entity_expr}                                                                 AS entity,
    SUM(total_trx)                                                               AS total_trx,
    ROUND(SUM(total_trx)::numeric / NULLIF(t.grand_trx::numeric, 0) * 100, 2)   AS trx_share_pct,
    SUM(total_revenue)                                                           AS total_revenue,
    ROUND(SUM(total_revenue)::numeric / NULLIF(t.grand_rev::numeric, 0) * 100, 2) AS rev_share_pct
FROM {table}
CROSS JOIN totals t
WHERE date >= :period_start AND date <= :period_end
GROUP BY {entity_expr}, t.grand_trx, t.grand_rev
ORDER BY total_trx DESC
LIMIT :top_n
"""

_HOURLY_SQL = """
SELECT
    hour,
    total_trx,
    ROUND(success_rate_pct::numeric, 2) AS success_rate_pct
FROM hourly_pattern_daily
WHERE date::date = :target_date::date
ORDER BY hour
"""


def get_summary(
    db_engine: Engine,
    period_start: str,
    period_end: str,
    dimension: str = "all",
) -> dict:
    """Total transaksi, revenue, dan success rate untuk suatu periode."""
    _params = {"period_start": period_start, "period_end": period_end}
    if dimension == "all":
        sql = _SUMMARY_ALL_SQL
    else:
        if dimension == "channel":
            table, entity_expr = "channel_payment", "channel"
            sr_expr = "ROUND(AVG(success_rate_pct)::numeric, 2)"
        elif dimension == "product":
            table = "product_summary"
            entity_expr = "COALESCE(NULLIF(NULLIF(product_name,'NULL'),''),'[Tidak Teridentifikasi]')"
            sr_expr = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)"
        else:
            table, entity_expr = "daily_master", "partner_group"
            sr_expr = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)"
        sql = _SUMMARY_ENTITY_SQL.format(entity_expr=entity_expr, table=table, sr_expr=sr_expr)  # nosec B608 — identifiers from whitelist

    return _run(db_engine, sql.strip(), f"Summary {dimension} {period_start}→{period_end}", params=_params)


def compare_periods(
    db_engine: Engine,
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    dimension: str = "partner",
) -> dict:
    """Bandingkan dua periode dan hitung % perubahan per entitas termasuk success rate (SR)."""
    # SR aggregation differs by table: channel_payment stores success_rate_pct directly;
    # daily_master and product_summary compute it from success_trx / total_trx.
    if dimension == "channel":
        table, group_col = "channel_payment", "channel"
        sr_agg = "ROUND(AVG(success_rate_pct)::numeric, 2)"
    elif dimension == "product":
        table, group_col = "product_summary", "product_name"
        sr_agg = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)"
    else:
        table, group_col = "daily_master", "partner_group"
        sr_agg = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)"

    # Same COALESCE normalization as get_distribution: merge NULL/string-'NULL'/empty
    # product_name rows into one '[Tidak Teridentifikasi]' entity.
    if dimension == "product":
        entity_expr = f"COALESCE(NULLIF(NULLIF({group_col}, 'NULL'), ''), '[Tidak Teridentifikasi]')"
    else:
        entity_expr = group_col

    sql = _COMPARE_SQL.format(entity_expr=entity_expr, table=table, sr_agg=sr_agg)  # nosec B608 — identifiers from whitelist
    desc = f"Compare {dimension}: {period_a_start}→{period_a_end} vs {period_b_start}→{period_b_end}"
    return _run(db_engine, sql.strip(), desc, params={
        "period_a_start": period_a_start, "period_a_end": period_a_end,
        "period_b_start": period_b_start, "period_b_end": period_b_end,
    })


def detect_anomaly(
    db_engine: Engine,
    target_date: str,
    dimension: str = "partner",
    threshold_pct: float = 30.0,
) -> dict:
    """Deteksi entitas dengan perubahan >threshold_pct% vs rata-rata 7 hari sebelumnya, termasuk success rate (SR)."""
    if dimension == "channel":
        table, group_col = "channel_payment", "channel"
        sr_target_expr = "ROUND(AVG(success_rate_pct)::numeric, 2)"
        sr_daily_expr  = "ROUND(AVG(success_rate_pct)::numeric, 2) AS daily_sr"
    elif dimension == "product":
        table, group_col = "product_summary", "product_name"
        sr_target_expr = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)"
        sr_daily_expr  = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS daily_sr"
    else:
        table, group_col = "daily_master", "partner_group"
        sr_target_expr = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)"
        sr_daily_expr  = "ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2) AS daily_sr"

    # Same COALESCE normalization as get_distribution: merge NULL/string-'NULL'/empty
    # product_name rows into one '[Tidak Teridentifikasi]' entity.
    if dimension == "product":
        entity_expr = f"COALESCE(NULLIF(NULLIF({group_col}, 'NULL'), ''), '[Tidak Teridentifikasi]')"
    else:
        entity_expr = group_col

    sql = _ANOMALY_SQL.format(  # nosec B608 — identifiers from whitelist; dates/threshold use bound params
        entity_expr=entity_expr, table=table,
        sr_target_expr=sr_target_expr, sr_daily_expr=sr_daily_expr,
    )
    desc = f"Anomaly detection {dimension} on {target_date} vs 7-day baseline (threshold {threshold_pct}%)"
    return _run(db_engine, sql.strip(), desc, params={"target_date": target_date, "threshold_pct": threshold_pct})


def get_trend(
    db_engine: Engine,
    start_date: str,
    end_date: str,
    dimension: str = "all",
    granularity: str = "daily",
) -> dict:
    """Tren transaksi dan revenue per periode (daily/weekly/monthly)."""
    if granularity == "monthly":
        date_trunc = "TO_CHAR(date, 'YYYY-MM')"
    elif granularity == "weekly":
        date_trunc = "TO_CHAR(DATE_TRUNC('week', date), 'YYYY-MM-DD')"
    else:
        date_trunc = "date::date::text"

    _date_params = {"start_date": start_date, "end_date": end_date}
    if dimension == "all":
        sql = _TREND_ALL_SQL.format(date_trunc=date_trunc)  # nosec B608 — date_trunc is a hardcoded SQL expr
    elif dimension == "channel":
        sql = _TREND_CHANNEL_SQL.format(date_trunc=date_trunc)  # nosec B608 — date_trunc is a hardcoded SQL expr
    else:  # partner
        sql = _TREND_PARTNER_SQL.format(date_trunc=date_trunc)  # nosec B608 — date_trunc is a hardcoded SQL expr

    desc = f"Trend {granularity} {dimension} {start_date}→{end_date}"
    return _run(db_engine, sql.strip(), desc, params=_date_params)


def get_distribution(
    db_engine: Engine,
    period_start: str,
    period_end: str,
    dimension: str = "partner",
    top_n: int = 30,
) -> dict:
    """Distribusi kontribusi (%) setiap entitas terhadap total."""
    # Display cap: at most 20 rows regardless of what the user requested.
    # This cap is the strictest bound; user can always request fewer (e.g. "top 5" → 5).
    # LIMIT is passed as a bound parameter (not string-interpolated) for safety.
    _DISPLAY_CAP = 20
    _top_n = max(1, min(int(top_n), _DISPLAY_CAP))

    if dimension == "channel":
        table, group_col = "channel_payment", "channel"
    elif dimension == "product":
        table, group_col = "product_summary", "product_name"
    else:
        table, group_col = "daily_master", "partner_group"

    # For product dimension, normalize NULL SQL, string 'NULL', and empty string into
    # one unified label so they don't consume multiple ranking slots.
    # partner_group and channel have no known NULL variants (confirmed via DB check).
    if dimension == "product":
        entity_expr = (
            f"COALESCE(NULLIF(NULLIF({group_col}, 'NULL'), ''), '[Tidak Teridentifikasi]')"
        )
    else:
        entity_expr = group_col

    # Pre-flight: count distinct entities AFTER normalization so actual_entity_count
    # reflects merged groups (e.g. NULL + 'NULL' → 1 entity, not 2).
    _date_params = {"period_start": period_start, "period_end": period_end}
    count_sql = _DIST_COUNT_SQL.format(entity_expr=entity_expr, table=table)  # nosec B608 — identifiers from whitelist
    try:
        with db_engine.connect() as conn:
            actual_entity_count = int(conn.execute(text(count_sql.strip()), _date_params).scalar() or 0)
    except Exception:
        actual_entity_count = 0

    _top_n_final = min(_top_n, actual_entity_count) if actual_entity_count > 0 else _top_n

    sql = _DIST_SQL.format(entity_expr=entity_expr, table=table)  # nosec B608 — identifiers from whitelist

    desc = f"Distribution by {dimension} {period_start}→{period_end} top {_top_n_final}"
    result = _run(db_engine, sql.strip(), desc, params={**_date_params, "top_n": _top_n_final})
    result["actual_entity_count"] = actual_entity_count
    result["dimension"] = dimension

    # Compute cumulative share from returned rows (share_pct columns are already
    # calculated against the full-period grand total, so summing them gives the
    # correct concentration figure for the displayed subset).
    data = result.get("data") or []
    result["cumulative_trx_share_pct"] = round(
        sum(float(r.get("trx_share_pct") or 0) for r in data), 2
    )
    result["cumulative_rev_share_pct"] = round(
        sum(float(r.get("rev_share_pct") or 0) for r in data), 2
    )
    return result


def get_hourly_pattern(
    db_engine: Engine,
    target_date: str,
) -> dict:
    """Pola transaksi per jam untuk satu tanggal tertentu."""
    return _run(db_engine, _HOURLY_SQL.strip(), f"Hourly pattern on {target_date}", params={"target_date": target_date})


# ── internal helper ──────────────────────────────────────────────────────────

def _run(db_engine: Engine, sql: str, description: str, params: dict | None = None) -> dict:
    """Execute SQL and return standard result dict."""
    with db_engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    # PostgreSQL SUM/AVG aggregates on an empty set return 1 row with all-NULL values.
    # Normalise this to an empty list so callers see row_count=0, not row_count=1 with NULLs.
    if len(rows) == 1 and all(v is None for v in rows[0].values()):
        rows = []

    return {
        "data":        rows,
        "row_count":   len(rows),
        "sql":         sql,
        "description": description,
    }
