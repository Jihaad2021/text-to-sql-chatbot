"""
Startup Validation

Validates all required environment variables before the application
initializes any agents or opens any connections.

Fail-fast: raises EnvironmentError on the first critical missing config
so the error message is clear, not buried in an agent traceback.

Usage:
    >>> from src.core.startup import validate_environment
    >>> validate_environment()   # call this before agent init
"""

import logging
import os

logger = logging.getLogger("startup")

# At least one of these LLM keys must be present.
_LLM_KEYS: list[str] = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
]

# At least one of these DB URLs must be present.
_DB_URL_KEYS: list[str] = [
    "SALES_DB_URL",
    "PRODUCTS_DB_URL",
    "ANALYTICS_DB_URL",
]

# Required individually — no fallback.
_REQUIRED_KEYS: list[str] = [
    "DEFAULT_LLM",
    "DEFAULT_MODEL",
]

# Required for ChromaDB semantic search.
# If missing, SchemaRetriever degrades to BM25+Graph only (warning, not error).
_CHROMADB_KEY = "OPENAI_API_KEY"


def validate_environment() -> None:
    """
    Validate all required environment variables at startup.

    Raises:
        EnvironmentError: If any critical variable is missing.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Individual required vars
    for key in _REQUIRED_KEYS:
        if not os.getenv(key):
            errors.append(f"  - {key} is not set")

    # 2. At least one LLM key
    llm_keys_present = [k for k in _LLM_KEYS if os.getenv(k)]
    if not llm_keys_present:
        errors.append(
            f"  - No LLM API key found. Set at least one of: {', '.join(_LLM_KEYS)}"
        )

    # 3. At least one DB URL
    db_urls_present = [k for k in _DB_URL_KEYS if os.getenv(k)]
    if not db_urls_present:
        errors.append(
            f"  - No database URL found. Set at least one of: {', '.join(_DB_URL_KEYS)}"
        )

    # 4. Warn if ChromaDB key missing (degraded mode, not fatal)
    if not os.getenv(_CHROMADB_KEY):
        warnings.append(
            f"  - {_CHROMADB_KEY} not set: ChromaDB semantic search will be disabled. "
            "SchemaRetriever will use BM25 + Graph only."
        )

    # 5. Warn if DB URLs partially missing
    missing_dbs = [k for k in _DB_URL_KEYS if not os.getenv(k)]
    if missing_dbs and db_urls_present:
        for key in missing_dbs:
            warnings.append(f"  - {key} not set: queries to that database will fail at runtime")

    # Print warnings
    if warnings:
        logger.warning("Startup warnings:\n%s", "\n".join(warnings))

    # Fail on errors
    if errors:
        logger.critical(
            "Startup failed — missing required environment variables:\n%s\n"
            "Copy .env.example to .env and fill in the required values.",
            "\n".join(errors),
        )
        raise EnvironmentError(
            "Missing required environment variables. See log output above for details."
        )

    # Log what is configured
    configured_llms = ", ".join(llm_keys_present)
    configured_dbs = ", ".join(db_urls_present)
    logger.info("Environment OK — LLM providers: [%s] | Databases: [%s]", configured_llms, configured_dbs)
