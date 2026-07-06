"""
date_range — single source of truth for the latest available data date.

Queried once at pipeline startup (not per-request) via get_latest_available_date().
Used by:
  - TextToSQLPipeline.__init__  → stored as self.data_end_date
  - pipeline.run()              → injected into state.data_end_date
  - QueryRewriter               → validates resolved period against latest date
  - AnalyticsAgent              → builds dynamic "Data tersedia" string in system prompt
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


def get_latest_available_date(engine: Engine) -> date | None:
    """Return MAX(date) from daily_master, or None if unavailable."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT MAX(date)::date FROM daily_master")
            ).fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        return None
