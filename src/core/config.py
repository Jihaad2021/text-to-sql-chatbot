"""
Centralized Configuration

All tuneable values live here. Components read from Config, never from
os.getenv() directly (except this module and startup.py).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root is two levels above this file (src/core/config.py → project root)
_ROOT = Path(__file__).parent.parent.parent


class Config:
    # ── LLM ──────────────────────────────────────────────────────
    MODEL = os.getenv("LLM_MODEL", None)
    MAX_TOKENS = 1000

    # ── Query Executor ────────────────────────────────────────────
    TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "30"))
    MAX_ROWS = int(os.getenv("QUERY_MAX_ROWS", "10000"))

    # SQLAlchemy connection pool
    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 min

    # ── Schema Retriever ──────────────────────────────────────────
    # Env-var overrides take precedence; defaults are resolved relative to the
    # project root so the app works regardless of the working directory at launch.
    CHROMA_PATH = os.getenv("CHROMA_PATH") or str(_ROOT / "chroma_db")
    EXAMPLES_PATH = os.getenv("FEW_SHOT_EXAMPLES_PATH") or str(_ROOT / "config" / "few_shot_examples.yaml")
    BM25_INDEX_FILE = os.getenv("BM25_INDEX_FILE") or str(_ROOT / "data" / "bm25_index.pkl")
    GRAPH_INDEX_FILE = os.getenv("GRAPH_INDEX_FILE") or str(_ROOT / "data" / "schema_graph.json")
    TOP_K_RETRIEVAL = int(os.getenv("TOP_K_RETRIEVAL", "5"))

    # RRF (Reciprocal Rank Fusion) constant.
    # Higher value = rank differences matter less. Standard value is 60.
    RRF_K = int(os.getenv("RRF_K", "60"))

    # ── SQL Validator ─────────────────────────────────────────────
    ENABLE_AI_VALIDATION = os.getenv("ENABLE_AI_VALIDATION", "false").lower() == "true"

    # ── Query Cache ───────────────────────────────────────────────
    # TTL for in-memory result cache. Set to 0 to disable caching.
    CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))

    # ── API ───────────────────────────────────────────────────────
    # Max requests per minute per IP on the /query endpoint.
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

    # ── Token quota (passive monitoring only — never blocks requests) ─────────
    MONTHLY_TOKEN_QUOTA = int(os.getenv("MONTHLY_TOKEN_QUOTA", "5000000"))

    # ── Logging ───────────────────────────────────────────────────
    # "text" for human-readable (dev), "json" for structured (production).
    LOG_FORMAT = os.getenv("LOG_FORMAT", "text")

    # ── Databases ─────────────────────────────────────────────────
    ALLOWED_TABLES = {
        'financial_internal', 'daily_master', 'daily_product_channel',
        'channel_payment', 'product_price_list', 'anomalies',
        'daily_unique_users', 'daily_user_partner',
        'hourly_pattern_daily', 'product_summary',
    }

    DANGEROUS_KEYWORDS = {
        'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE',
        'INSERT', 'UPDATE', 'GRANT', 'REVOKE', 'EXECUTE',
        'PROCEDURE', 'FUNCTION'
    }

    DB_URLS: dict[str, str | None] = {
        'financial_db': os.getenv('FINANCIAL_DB_URL'),
    }
