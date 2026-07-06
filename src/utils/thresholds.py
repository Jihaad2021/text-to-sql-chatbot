"""
Business thresholds — single source of truth loader.

Loads config/business_thresholds.yaml once at process startup and caches the result.
Use render_thresholds_block() to get a markdown table block ready to inject into any
LLM prompt via a template variable.

Restart the process to pick up YAML changes (lru_cache is process-scoped).
"""
import functools
from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).parent.parent.parent / "config" / "business_thresholds.yaml"


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    with _YAML_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_auto_drilldown_threshold() -> float:
    """Return DoD drop magnitude (positive %) that triggers auto drill-down.

    Stored as auto_drilldown_dod_threshold in business_thresholds.yaml so it
    can be tuned independently from the PERHATIAN/KRITIS verdict thresholds.
    Defaults to 30 if key is absent.
    """
    return float(_load().get("auto_drilldown_dod_threshold", 30))


def render_thresholds_block() -> str:
    """
    Render the full thresholds table + verdict notes as a single string.

    Output (inject via {business_thresholds_block} in any f-string prompt):

        BUSINESS THRESHOLDS:
        | Metrik                | SEHAT (Hijau) | PERHATIAN (Kuning) | KRITIS (Merah) |
        |---|---|---|---|
        | MoM Volume Growth     | > 0%          | -10% s/d 0%        | < -10%         |
        ...
        VERDICT WAJIB: ...

    Each table row is a single unbroken line (no embedded newlines). The `\n` separator
    is only between rows, not within them — safe for all markdown renderers.
    """
    data = _load()
    lines: list[str] = [
        "BUSINESS THRESHOLDS:",
        "| Metrik                | SEHAT (Hijau) | PERHATIAN (Kuning) | KRITIS (Merah) |",
        "|---|---|---|---|",
    ]
    for t in data["thresholds"]:
        lines.append(
            f"| {t['metric']:<21} | {t['sehat']:<13} | {t['perhatian']:<18} | {t['kritis']:<14} |"
        )
    lines.extend(data.get("notes", []))
    return "\n".join(lines)
