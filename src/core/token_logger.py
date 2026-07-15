"""
Token usage logger — fire-and-forget INSERT into token_usage_log.

Lazily creates the table on first call. Swallows all errors so a DB
hiccup never breaks a query response.
"""

import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS token_usage_log (
    id                SERIAL PRIMARY KEY,
    ts                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    request_id        TEXT NOT NULL,
    session_id        TEXT,
    agent_name        TEXT NOT NULL,
    model             TEXT NOT NULL,
    quality_tier      TEXT NOT NULL DEFAULT 'standard',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    iteration         INTEGER DEFAULT NULL
);
"""

_engine: Engine | None = None
_table_ready: bool = False


def _get_engine() -> Engine | None:
    global _engine, _table_ready
    if _engine is None:
        db_url = os.getenv("FINANCIAL_DB_URL")
        if not db_url:
            return None
        _engine = create_engine(db_url, pool_size=1, max_overflow=2, pool_pre_ping=True)

    if not _table_ready:
        with _engine.connect() as conn:
            conn.execute(text(_DDL))
            conn.commit()
        _table_ready = True

    return _engine


def log_token_usage(
    *,
    request_id: str,
    session_id: str | None,
    agent_name: str,
    model: str,
    quality_tier: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    iteration: int | None,
) -> None:
    """Insert one row into token_usage_log. Never raises."""
    try:
        engine = _get_engine()
        if engine is None:
            return
        with engine.connect() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO token_usage_log
                        (request_id, session_id, agent_name, model, quality_tier,
                         prompt_tokens, completion_tokens, total_tokens, iteration)
                    VALUES
                        (:request_id, :session_id, :agent_name, :model, :quality_tier,
                         :prompt_tokens, :completion_tokens, :total_tokens, :iteration)
                    """
                ),
                {
                    "request_id":        request_id,
                    "session_id":        session_id,
                    "agent_name":        agent_name,
                    "model":             model,
                    "quality_tier":      quality_tier,
                    "prompt_tokens":     prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens":      total_tokens,
                    "iteration":         iteration,
                },
            )
            conn.commit()
    except Exception as e:
        logger.warning("token_usage_log INSERT failed (non-fatal): %s", e)


def get_usage_summary(period: str = "current_month") -> dict:
    """
    Return token usage aggregates for the given period.

    period values:
      "current_month"  — rows where ts >= date_trunc('month', now())
      "today"          — rows where ts >= date_trunc('day', now())
      "all_time"       — no date filter
    """
    from src.core.config import Config

    where: str
    if period == "today":
        where = "WHERE ts >= date_trunc('day', now())"
    elif period == "all_time":
        where = ""
    else:  # current_month (default)
        where = "WHERE ts >= date_trunc('month', now())"

    try:
        engine = _get_engine()
        if engine is None:
            return {"error": "database unavailable"}

        # `where` is one of three hardcoded SQL fragments (see above); no user input reaches it.
        # String concatenation (not f-string) avoids false-positive B608 from bandit.
        _w = (" " + where) if where else ""
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT"  # nosec B608 — _w is one of 3 hardcoded SQL fragments, never user input
                    " COALESCE(SUM(prompt_tokens), 0)     AS prompt_tokens,"
                    " COALESCE(SUM(completion_tokens), 0) AS completion_tokens,"
                    " COALESCE(SUM(total_tokens), 0)      AS total_tokens,"
                    " COUNT(*)                            AS llm_calls"
                    " FROM token_usage_log" + _w
                )
            ).fetchone()

            by_tier = conn.execute(
                text(
                    "SELECT quality_tier,"  # nosec B608 — _w is one of 3 hardcoded SQL fragments, never user input
                    " COALESCE(SUM(total_tokens), 0) AS total_tokens,"
                    " COUNT(*)                        AS llm_calls"
                    " FROM token_usage_log" + _w +
                    " GROUP BY quality_tier ORDER BY total_tokens DESC"
                )
            ).fetchall()

            by_agent = conn.execute(
                text(
                    "SELECT agent_name,"  # nosec B608 — _w is one of 3 hardcoded SQL fragments, never user input
                    " COALESCE(SUM(prompt_tokens), 0)     AS prompt_tokens,"
                    " COALESCE(SUM(completion_tokens), 0) AS completion_tokens,"
                    " COALESCE(SUM(total_tokens), 0)      AS total_tokens,"
                    " COUNT(*)                            AS llm_calls"
                    " FROM token_usage_log" + _w +
                    " GROUP BY agent_name ORDER BY total_tokens DESC"
                )
            ).fetchall()

        quota = Config.MONTHLY_TOKEN_QUOTA
        total = int(row.total_tokens)

        return {
            "period":          period,
            "quota":           quota,
            "total_tokens":    total,
            "prompt_tokens":   int(row.prompt_tokens),
            "completion_tokens": int(row.completion_tokens),
            "llm_calls":       int(row.llm_calls),
            "quota_used_pct":  round(total / quota * 100, 2) if quota else None,
            "by_tier": [
                {
                    "quality_tier": r.quality_tier,
                    "total_tokens": int(r.total_tokens),
                    "llm_calls":    int(r.llm_calls),
                }
                for r in by_tier
            ],
            "by_agent": [
                {
                    "agent_name":        r.agent_name,
                    "prompt_tokens":     int(r.prompt_tokens),
                    "completion_tokens": int(r.completion_tokens),
                    "total_tokens":      int(r.total_tokens),
                    "llm_calls":         int(r.llm_calls),
                }
                for r in by_agent
            ],
        }

    except Exception as e:
        logger.warning("get_usage_summary failed: %s", e)
        return {"error": str(e)}
