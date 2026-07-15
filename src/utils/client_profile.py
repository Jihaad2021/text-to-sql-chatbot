"""
Client profile helpers — single source of truth loader for client identity and persona.

Loads config/client_profile.yaml once at process startup and caches the result.
Use the render_* functions to inject client identity and persona scope into any LLM
prompt via template variables.

Restart the process to pick up YAML changes (lru_cache is process-scoped).

Reads from state: (none — module-level utilities)
"""
import functools
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "client_profile.yaml"


@functools.lru_cache(maxsize=None)
def _load() -> dict:
    with _CONFIG_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def render_client_identity_block() -> str:
    """Return English data analyst persona opener for insight prompt builders.

    Example: "You are a data analyst for Telkomsel's digital payment platform"

    Used as module-level constant in insight_generator (3 prompt builders).
    """
    client = _load()["client"]
    return f"You are a data analyst for {client['name']}'s {client['domain_description']}"


def get_client_platform() -> str:
    """Return "{name}'s {domain_description}" platform identifier string.

    Example: "Telkomsel's digital payment platform"

    Used by response_planner's persona line which has a different role prefix
    from insight_generator's render_client_identity_block().
    """
    client = _load()["client"]
    return f"{client['name']}'s {client['domain_description']}"


def render_persona_header_block() -> str:
    """Return Indonesian persona header for recommendation synthesis prompt.

    Produces the opening block injected at the top of
    _build_recommendation_synthesis_prompt():

        Kamu adalah Finance & Revenue Assurance analyst untuk platform pembayaran digital Telkomsel.
        Domain tugasmu: monitoring performa transaksi, eskalasi anomali ke tim ops/partner management, ...
        BUKAN tugasmu: keputusan marketing/promosi, desain produk, ...
    """
    client  = _load()["client"]
    persona = _load()["persona"]
    name           = client["name"]
    domain_desc_id = client["domain_description_id"]
    role               = persona["role"]
    domain_actions     = ", ".join(persona["domain_actions"])
    not_domain_actions = ", ".join(persona["not_domain_actions"])
    return (
        f"Kamu adalah {role} untuk {domain_desc_id} {name}.\n"
        f"Domain tugasmu: {domain_actions}.\n"
        f"BUKAN tugasmu: {not_domain_actions}."
    )


def render_persona_scope_block() -> str:
    """Return IN-SCOPE / OUT-OF-SCOPE block for recommendation synthesis instructions.

    Produces the scope constraint block injected into
    _build_recommendation_synthesis_prompt() at the WAJIB DIIKUTI — DOMAIN step:

        IN-SCOPE: eskalasi ke ops/partner management, permintaan klarifikasi SLA, ...
           OUT-OF-SCOPE — DILARANG: kampanye promosi, keputusan marketing, ...
    """
    persona      = _load()["persona"]
    in_scope     = ", ".join(persona["in_scope_actions"])
    out_of_scope = ", ".join(persona["out_of_scope_actions"])
    return (
        f"IN-SCOPE: {in_scope}.\n"
        f"   OUT-OF-SCOPE — DILARANG: {out_of_scope}."
    )
