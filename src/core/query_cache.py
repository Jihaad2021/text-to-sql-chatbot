"""
In-memory query result cache with TTL.

Caches the full output of a pipeline run keyed by (normalised query, database).
A cache hit skips all 8 agents, returning the stored result immediately.

Thread-safety: dict reads/writes are GIL-protected in CPython, sufficient for
our use case (one writer thread per request, no concurrent writers to the same key).
"""

import time
from dataclasses import dataclass
from typing import Any


# Fields copied from AgentState on store and restored on hit
_CACHED_FIELDS = (
    "intent",
    "validated_sql",
    "sql",
    "query_result",
    "row_count",
    "insights",
    "database",
    "is_multi_step",
    "step_results",
    "chart_config",
    "tool_calls",
)


@dataclass
class _CacheEntry:
    snapshot: dict[str, Any]
    expires_at: float


class QueryCache:
    """
    TTL-based in-memory cache for pipeline results.

    Cache key: (normalised query, database).
    Conversation history is intentionally excluded from the key — the cache
    is intended for identical standalone lookups (dashboards, repeated queries).
    Follow-up queries that depend on history will naturally miss the cache
    because their query text differs from any prior cached query.
    """

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._store: dict[tuple[str, str], _CacheEntry] = {}

    # ─────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────

    def get(self, query: str, database: str, tier: str = "standard") -> dict[str, Any] | None:
        """Return cached snapshot or None if missing/expired."""
        key = self._key(query, database, tier)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            return None
        return entry.snapshot

    def put(self, query: str, database: str, snapshot: dict[str, Any], tier: str = "standard") -> None:
        """Store a result snapshot with TTL."""
        key = self._key(query, database, tier)
        self._store[key] = _CacheEntry(
            snapshot=snapshot,
            expires_at=time.monotonic() + self._ttl,
        )

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        """Count non-expired entries."""
        now = time.monotonic()
        return sum(1 for e in self._store.values() if e.expires_at > now)

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    @staticmethod
    def _key(query: str, database: str, tier: str = "standard") -> tuple[str, str, str]:
        return (query.strip().lower(), database, tier)


def build_snapshot(state: Any) -> dict[str, Any]:
    """Extract cacheable fields from an AgentState."""
    return {field: getattr(state, field) for field in _CACHED_FIELDS}


def restore_snapshot(state: Any, snapshot: dict[str, Any]) -> Any:
    """Write cached fields back into an AgentState."""
    for field, value in snapshot.items():
        setattr(state, field, value)
    return state
