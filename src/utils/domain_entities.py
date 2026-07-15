"""
domain_entities — single source of truth for partner/channel/product entity definitions.

Loaded once per process from config/domain_entities.yaml via _load() (lru_cache).
All render functions are pure: given the same YAML, they return the same string.
Agent files compute module-level constants at import time — same pattern as
business_thresholds.yaml / render_thresholds_block() in analytics_agent.py.

Usage in agent files:
    from src.utils.domain_entities import render_partner_list_block
    _PARTNER_LIST = render_partner_list_block()   # computed once at import

Adding a new partner:
    1. Add entry to config/domain_entities.yaml
    2. Restart the process — all prompt constants are re-computed
    3. Update financial_domain.PARTNER_GROUPS if the partner has SQL-level variants
"""

from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "domain_entities.yaml"


@lru_cache(maxsize=None)
def _load() -> dict:
    """Load and cache domain_entities.yaml. Call _load.cache_clear() in tests."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Partners ──────────────────────────────────────────────────────────────────

def get_partner_canonical_list() -> list[str]:
    """Return ordered list of canonical partner names (lowercase)."""
    return [p["canonical"] for p in _load()["partners"]]


def get_partner_display_list() -> list[str]:
    """Return ordered list of display partner names (title case)."""
    return [p["display"] for p in _load()["partners"]]


def get_partner_variants(canonical: str) -> list[str]:
    """Return all DB-level name variants for a canonical partner name.

    Used by SQLGenerator to build exhaustive IN-clauses and DOMAIN NOTES.
    """
    for p in _load()["partners"]:
        if p["canonical"] == canonical:
            return list(p["variants"])
    return [canonical]


def get_partner_keywords() -> frozenset[str]:
    """Return frozenset of all partner detection keywords (lowercase).

    Used by response_planner and insight_generator for segment detection.
    """
    result: set[str] = set()
    for p in _load()["partners"]:
        result.update(kw.lower() for kw in p.get("keywords", [p["canonical"]]))
    return frozenset(result)


def render_partner_list_block() -> str:
    """Comma-separated canonical partner names for prompt injection.

    Example: "dana, finnet, gopay, indomaret, linkaja, ovo, qris, shopeepay, telkomsel_wallet"
    """
    return ", ".join(get_partner_canonical_list())


def render_partner_display_block() -> str:
    """Comma-separated display partner names for prompt injection.

    Example: "Dana, Finnet, GoPay, Indomaret, LinkAja, OVO, QRIS, ShopeePay, Telkomsel Wallet"
    """
    return ", ".join(get_partner_display_list())


# ── Channel groups ────────────────────────────────────────────────────────────

def get_channel_codes() -> list[str]:
    """Return flat list of all channel codes in group order."""
    codes: list[str] = []
    for g in _load()["channel_groups"]:
        codes.extend(g["codes"])
    return codes


def get_channel_keywords() -> frozenset[str]:
    """Return frozenset of channel group keywords (lowercase).

    Used by response_planner and insight_generator for segment detection.
    """
    result: set[str] = set()
    for g in _load()["channel_groups"]:
        result.update(kw.lower() for kw in g.get("keywords", []))
    return frozenset(result)


def render_channel_list_block() -> str:
    """Channel codes+label in 'codes=label' format for prompt injection.

    Example: "i1=MyTelkomsel App, f0/f4/f5=UMB, b0/b3/a0=WEC, ig=MyTelkomsel Basic"
    """
    parts = []
    for g in _load()["channel_groups"]:
        codes_str = "/".join(g["codes"])
        parts.append(f"{codes_str}={g['label']}")
    return ", ".join(parts)


def render_channel_group_labels_block() -> str:
    """Comma-separated channel group labels for segment-rule prompt injection.

    Example: "MyTelkomsel App, UMB, WEC, MyTelkomsel Basic"
    """
    return ", ".join(g["label"] for g in _load()["channel_groups"])


def render_channel_codes_flat() -> str:
    """Space-or-comma separated flat channel code list for prompt injection.

    Example: "i1, f0, f4, f5, b0, b3, a0, ig"
    """
    return ", ".join(get_channel_codes())


def render_channel_groups_block() -> str:
    """Channel groups in 'label (codes)' format for the channel analysis guide.

    Example: "MyTelkomsel App (i1), UMB (f0/f4/f5), WEC (b0/b3/a0), MyTelkomsel Basic (ig)"
    """
    parts = []
    for g in _load()["channel_groups"]:
        codes_str = "/".join(g["codes"])
        parts.append(f"{g['label']} ({codes_str})")
    return ", ".join(parts)


def render_channel_rewrite_rules() -> str:
    """Human-readable channel rewrite rules for QueryRewriter prompt injection.

    Produces one line per channel group in the format the LLM expects:
        "MyTelkomsel App" atau "aplikasi mytelkomsel" → channel = 'i1'
        "UMB" → channel IN ('f0','f4','f5')
        ...
    """
    lines = []
    for g in _load()["channel_groups"]:
        codes = g["codes"]
        kws = g.get("keywords", [g["label"]])
        kw_str = " atau ".join(f'"{kw}"' for kw in kws)
        if len(codes) == 1:
            sql_part = f"channel = '{codes[0]}'"
        else:
            quoted = ",".join(f"'{c}'" for c in codes)
            sql_part = f"channel IN ({quoted})"
        lines.append(f"   {kw_str} → {sql_part}")
    return "\n".join(lines)
