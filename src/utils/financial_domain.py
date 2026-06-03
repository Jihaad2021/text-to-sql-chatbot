"""
Financial Domain Knowledge — Telkomsel Payment Platform

Centralizes partner normalization, channel constants, and business
thresholds derived from the platform's operational definitions.
Used by SQL Generator and Insight Generator agents.
"""

# ── PARTNER GROUPS ────────────────────────────────────────────────────────────
# Maps canonical group name → all raw name variants found in the database.
# Source: inconsistent naming across daily_master, channel_payment,
#         financial_internal, and product_summary tables.
PARTNER_GROUPS: dict[str, list[str]] = {
    "dana":             ["dana", "dana_wec"],
    "finnet":           ["finnet", "finnet_cc", "finnet_va"],
    "gopay":            ["gopay", "gopay_basic", "gopay_wec"],
    "indomaret":        ["indomaret"],
    "linkaja":          ["linkaja", "linkaja_app", "linkaja_basic",
                         "linkaja_wec", "linkajawco", "linkaja_wco"],
    "ovo":              ["ovo", "ovo_wec"],
    "qris":             ["qris"],
    "shopeepay":        ["shopeepay", "shopeepay_basic", "shopeepay_wec"],
    "telkomsel_wallet": ["telkomsel_wallet", "tsel_wallet"],
}

# Reverse map: raw_name.lower() → canonical group name
_REVERSE_MAP: dict[str, str] = {
    raw.lower(): group
    for group, raws in PARTNER_GROUPS.items()
    for raw in raws
}


def normalize_partner(name: str) -> str:
    """Map any raw partner/payment_provider name to its canonical group."""
    if not isinstance(name, str):
        return name
    return _REVERSE_MAP.get(name.lower(), name.lower())


def get_partner_sql_variants(group_name: str) -> list[str]:
    """
    Return all DB-level name variants for a partner group.

    Use to build SQL IN clauses so inconsistent naming is handled:
        WHERE partner IN ('linkajawco', 'linkaja_wco', 'linkaja')
    """
    key = group_name.lower().replace(" ", "_")
    return PARTNER_GROUPS.get(key, [group_name])


def partner_in_clause(group_name: str, column: str = "partner") -> str:
    """
    Build a SQL fragment for a partner group that handles all name variants.

    Example:
        partner_in_clause("linkaja") →
        "partner IN ('linkajawco', 'linkaja_wco', 'linkaja', 'linkaja_app', 'linkaja_basic', 'linkaja_wec')"
    """
    variants = get_partner_sql_variants(group_name)
    quoted = ", ".join(f"'{v}'" for v in variants)
    return f"{column} IN ({quoted})"


# ── CHANNEL CODES ─────────────────────────────────────────────────────────────
# Internal Telkomsel distribution channel codes used in:
#   - daily_product_channel (columns: a0_trx, a0_revenue, b3_trx, ...)
#   - channel_payment (column: channel)
CHANNEL_CODES: list[str] = ["a0", "b3", "f0", "f4", "f5", "i1", "ig"]

# SQL to compute total trx/revenue across all channels in daily_product_channel
CHANNEL_TOTAL_TRX_SQL = (
    "a0_trx + b3_trx + f0_trx + f4_trx + f5_trx + i1_trx + ig_trx"
)
CHANNEL_TOTAL_REV_SQL = (
    "a0_revenue + b3_revenue + f0_revenue + f4_revenue + f5_revenue + i1_revenue + ig_revenue"
)


# ── SUCCESS RATE THRESHOLDS ───────────────────────────────────────────────────
SR_ALERT    = 80.0   # Below this → ALERT (merah/red)
SR_WATCH    = 85.0   # Below this → Watch (kuning/amber)
SR_GOOD     = 88.0   # Above this → Good (hijau/green)
SR_EXCELLENT = 95.0  # Above this → Excellent


def classify_sr(sr_value: float) -> str:
    """Classify a success rate value into a business status label."""
    if sr_value < SR_ALERT:
        return "ALERT"
    if sr_value < SR_WATCH:
        return "Watch"
    if sr_value >= SR_EXCELLENT:
        return "Excellent"
    return "Normal"


# ── WEIGHTED SR FORMULA ───────────────────────────────────────────────────────
# Use this instead of AVG(success_rate_pct) to get accurate cross-group SR.
WEIGHTED_SR_SQL = "ROUND(SUM(success_trx) / NULLIF(SUM(total_trx), 0) * 100, 2)"


# ── ITEM TYPE MAPPING ─────────────────────────────────────────────────────────
ITEM_TYPES: dict[str, str] = {
    "recharge": "Pengisian pulsa (top-up)",
    "package":  "Paket data / internet",
    "topping":  "Layanan tambahan / VAS (streaming, antivirus, dll)",
}

PURCHASE_MODES: dict[str, str] = {
    "SELF": "Beli untuk nomor sendiri",
    "GIFT": "Beli untuk nomor orang lain (hadiah)",
}


# ── PEAK HOUR CONSTANTS ───────────────────────────────────────────────────────
PEAK_HOURS         = [18, 19, 20, 21]   # Jam puncak transaksi
BUSINESS_HOURS     = (8, 22)            # Jam operasional (start, end inclusive)
NIGHT_HOURS_END    = 6                  # Jam malam: 0–6


# ── DATA RANGE ────────────────────────────────────────────────────────────────
DATA_START_DATE = "2026-03-01"
DATA_END_DATE   = "2026-06-02"
