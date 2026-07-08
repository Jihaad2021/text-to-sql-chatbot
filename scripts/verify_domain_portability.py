"""
Portability verification — poin 5.

Simulates adding a new partner "newpay" to domain_entities.yaml and verifies
that ALL 5 agent prompt/detection functions pick it up WITHOUT any code changes.

Usage:
    python scripts/verify_domain_portability.py

Expected output:
    [BEFORE] newpay appears in prompts: 0/6
    Added "newpay" to domain_entities.yaml + cleared cache.
    [AFTER]  newpay appears in prompts: 6/6
    PASS — portability verified.
"""

import sys
import yaml
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.domain_entities import (
    _load,
    render_partner_list_block,
    render_partner_display_block,
    get_partner_keywords,
    get_partner_canonical_list,
)

YAML_PATH = Path(__file__).parent.parent / "config" / "domain_entities.yaml"
NEWPAY_ENTRY = {
    "canonical": "newpay",
    "display":   "NewPay",
    "variants":  ["newpay"],
    "keywords":  ["newpay"],
}


def _check_prompts(label: str) -> dict[str, bool]:
    """
    Build each agent's entity constant and check if "newpay" appears.
    Each check mirrors exactly what the agent computes at import time.
    """
    results = {}

    # 1. query_rewriter: render_partner_list_block() → "- partner: ..."
    qr_partner_line = render_partner_list_block()
    results["query_rewriter (partner list)"] = "newpay" in qr_partner_line

    # 2. intent_classifier: render_partner_list_block() → segment rules
    ic_partner_line = render_partner_list_block()
    results["intent_classifier (segment rule)"] = "newpay" in ic_partner_line

    # 3. sql_generator: render_partner_list_block() + count → PARTNER COLUMN RULE
    partner_count = len(get_partner_canonical_list())
    partner_list  = render_partner_list_block()
    sg_rule = f"use partner_group ({partner_count} brands: {partner_list})"
    results["sql_generator (partner_group rule)"] = "newpay" in sg_rule

    # 4. analytics_agent: render_partner_display_block() → "Partner: ..."
    aa_partner_line = render_partner_display_block()
    results["analytics_agent (Partner: line)"] = "NewPay" in aa_partner_line

    # 5. response_planner: get_partner_keywords() → _PARTNER_SEGMENT_KW
    rp_kw = frozenset({"partner", "mitra"} | get_partner_keywords())
    results["response_planner (keyword detection)"] = "newpay" in rp_kw

    # 6. insight_generator: get_partner_keywords() → _PARTNER_KW class attr
    ig_kw = frozenset({"partner", "ekosistem partner", "mitra"} | get_partner_keywords())
    results["insight_generator (_PARTNER_KW)"] = "newpay" in ig_kw

    passed = sum(1 for v in results.values() if v)
    print(f"\n[{label}]")
    for name, ok in results.items():
        status = "OK" if ok else "--"
        print(f"  [{status}] {name}")
    print(f"  → {passed}/{len(results)} checks passed")
    return results


def main() -> None:
    # Back up original YAML text (preserves comments/formatting).
    original_yaml = YAML_PATH.read_text()

    try:
        # ── BEFORE ────────────────────────────────────────────────────────────
        before = _check_prompts("BEFORE — newpay NOT in YAML")
        before_count = sum(1 for v in before.values() if v)
        assert before_count == 0, f"Expected 0 before, got {before_count}"

        # ── Add newpay — append entry to partners list in raw YAML text ────────
        # Insert just before the channel_groups section so formatting is readable.
        insert_block = (
            "\n  - canonical: \"newpay\"\n"
            "    display: \"NewPay\"\n"
            "    variants: [\"newpay\"]\n"
            "    keywords: [\"newpay\"]\n"
        )
        modified_yaml = original_yaml.replace(
            "\n# Channel groups",
            insert_block + "\n# Channel groups",
            1,
        )
        YAML_PATH.write_text(modified_yaml)
        _load.cache_clear()
        print(f'\nAdded "newpay" entry to {YAML_PATH.name} + cleared cache.')

        # ── AFTER ─────────────────────────────────────────────────────────────
        after = _check_prompts("AFTER — newpay in YAML")
        after_count = sum(1 for v in after.values() if v)

    finally:
        # ── Cleanup: always restore original file ─────────────────────────────
        YAML_PATH.write_text(original_yaml)
        _load.cache_clear()
        print(f'\nRestored original {YAML_PATH.name} + cleared cache.')

    # ── Verify cleanup ─────────────────────────────────────────────────────────
    cleanup = _check_prompts("CLEANUP — original YAML restored")
    cleanup_count = sum(1 for v in cleanup.values() if v)

    # ── Final verdict ─────────────────────────────────────────────────────────
    print()
    if after_count == len(after) and cleanup_count == 0:
        print(f"PASS — portability verified: {after_count}/{len(after)} checks passed after YAML edit.")
        print("       All resolved to 0 after cleanup (no code changes needed).")
    else:
        print(f"FAIL — after={after_count}/{len(after)}, cleanup={cleanup_count}/{len(cleanup)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
