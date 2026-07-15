"""
Domain entity portability verification — subprocess edition.

Simulates adding a new partner "newpay" to domain_entities.yaml and verifies
that ALL 6 agent prompt/detection functions pick it up WITHOUT any code changes.

Strategy: subprocess isolation.
  Each check runs in a FRESH Python process (verify_child.py) that imports all
  agent modules AFTER the YAML has been modified on disk. Module-level constants
  (_PARTNER_LIST, _PARTNER_DISPLAY, _PARTNER_SEGMENT_KW, InsightGenerator._PARTNER_KW)
  are evaluated at import time in that fresh process — identical to a server restart.
  This is the only approach that verifies end-to-end injection into actual LLM
  prompt strings, not just intermediate helper function outputs.

Why NOT the in-process approach (old verify_domain_portability.py):
  _load.cache_clear() refreshes the YAML loader, but module-level constants in
  agent files that were already imported are FROZEN and cannot be updated without
  a process restart. The subprocess approach correctly simulates that restart.

Usage:
    python scripts/verify_domain_portability.py

Expected output (all 6 checks pass, 0 pass after cleanup):
    [BEFORE — newpay NOT in YAML]
      [--] query_rewriter   ...
      → 0/6 checks passed
    Added "newpay" to domain_entities.yaml. Spawning fresh child process...
    [AFTER — newpay in YAML (fresh process)]
      [OK] query_rewriter   ...
      → 6/6 checks passed
    Restored original domain_entities.yaml.
    [CLEANUP — original YAML restored (fresh process)]
      [--] query_rewriter   ...
      → 0/6 checks passed
    PASS — end-to-end portability verified via subprocess isolation.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

YAML_PATH  = Path(__file__).parent.parent / "config" / "domain_entities.yaml"
CHILD_PATH = Path(__file__).parent / "verify_child.py"

# Raw YAML block to insert. Uses list-item indentation that matches the
# existing partners entries in domain_entities.yaml.
NEWPAY_BLOCK = (
    "- canonical: newpay\n"
    "  display: NewPay\n"
    "  variants:\n"
    "  - newpay\n"
    "  keywords:\n"
    "  - newpay\n"
)


def _run_child(label: str) -> dict[str, dict]:
    """Spawn verify_child.py in a fresh process and return its parsed JSON results."""
    env = os.environ.copy()
    # Ensure at least one API key env var is set so LLMBaseAgent.__init__ resolves
    # a provider without raising. A dummy value is safe — no actual LLM call is made.
    env.setdefault("ANTHROPIC_API_KEY", "sk-ant-verify-only-no-real-calls")

    result = subprocess.run(
        [sys.executable, str(CHILD_PATH)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )

    if result.returncode != 0 or not result.stdout.strip():
        print(f"  Child process failed (returncode={result.returncode})")
        if result.stderr:
            print(f"  stderr:\n{result.stderr[:800]}")
        return {}

    try:
        data: dict[str, dict] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"  Could not parse child JSON: {exc}")
        print(f"  stdout[:300]: {result.stdout[:300]}")
        return {}

    passed = sum(1 for v in data.values() if v.get("pass"))
    total  = len(data)

    print(f"\n[{label}]")
    for name, info in data.items():
        status = "OK" if info.get("pass") else "FAIL"
        print(f"  [{status}] {name}")
        if "detail" in info:
            print(f"         {info['detail']}")
        if "error" in info:
            print(f"         ERROR: {info['error']}")
    print(f"  → {passed}/{total} checks passed")

    return data


def _insert_newpay(original: str) -> str:
    """
    Insert the newpay entry into the partners list in the raw YAML text.

    We look for the `channel_groups:` root key (no leading spaces) as the
    boundary marker — partners always precede it in domain_entities.yaml.
    Raises RuntimeError if the marker is not found so the caller can bail
    before writing a broken YAML to disk.
    """
    marker = "\nchannel_groups:"
    if marker not in original:
        raise RuntimeError(
            "Insertion marker '\\nchannel_groups:' not found in YAML. "
            "Cannot safely insert newpay block."
        )
    return original.replace(marker, "\n" + NEWPAY_BLOCK + "\nchannel_groups:", 1)


def main() -> None:
    original_yaml = YAML_PATH.read_text()

    try:
        # ── BEFORE: verify newpay is absent in a fresh process ────────────────
        before = _run_child("BEFORE — newpay NOT in YAML")
        before_count = sum(1 for v in before.values() if v.get("pass"))
        if before_count != 0:
            print(f"\nABORT: {before_count} checks unexpectedly passed BEFORE insertion.")
            sys.exit(1)

        # ── Inject newpay into the YAML on disk ───────────────────────────────
        modified_yaml = _insert_newpay(original_yaml)
        YAML_PATH.write_text(modified_yaml)
        print(f'\nAdded "newpay" to {YAML_PATH.name}. Spawning fresh child process...')

        # ── AFTER: fresh process imports agents with the new YAML ─────────────
        after = _run_child("AFTER — newpay in YAML (fresh process)")
        after_count = sum(1 for v in after.values() if v.get("pass"))

    finally:
        # Always restore, even on exception or KeyboardInterrupt.
        YAML_PATH.write_text(original_yaml)
        print(f'\nRestored original {YAML_PATH.name}.')

    # ── CLEANUP: verify newpay is absent again in a fresh process ─────────────
    print("Spawning cleanup verification (restored YAML)...")
    cleanup = _run_child("CLEANUP — original YAML restored (fresh process)")
    cleanup_count = sum(1 for v in cleanup.values() if v.get("pass"))

    # ── Final verdict ─────────────────────────────────────────────────────────
    total = len(after)
    print()
    if after_count == total and cleanup_count == 0:
        print("PASS — end-to-end portability verified via subprocess isolation.")
        print(f"  {after_count}/{total} prompt-level checks pass with newpay in YAML.")
        print(f"  {cleanup_count}/{total} pass after YAML restored (correct: none).")
        print()
        print("  Structural guarantee: module-level constants (_PARTNER_LIST,")
        print("  _PARTNER_DISPLAY, _PARTNER_SEGMENT_KW, InsightGenerator._PARTNER_KW)")
        print("  are all verified in a fresh process — equivalent to server restart.")
    else:
        print(f"FAIL — after={after_count}/{total}, cleanup={cleanup_count}/{total}")
        # Print per-agent detail for failed AFTER checks
        for name, info in after.items():
            if not info.get("pass"):
                err = info.get("error") or info.get("detail", "no detail")
                print(f"  AFTER  FAIL: {name} — {err}")
        for name, info in cleanup.items():
            if info.get("pass"):
                err = info.get("detail", "no detail")
                print(f"  CLEANUP PASS (should be FAIL): {name} — {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
