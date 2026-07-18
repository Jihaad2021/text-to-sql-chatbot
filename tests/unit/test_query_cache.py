"""
Unit tests for QueryCache and snapshot helpers.

Tests cover:
- get: cache miss → None
- get: cache hit → returns snapshot
- get: expired entry → None (entry evicted)
- put: stores snapshot retrievable by same key
- clear: empties all entries
- size: counts only non-expired entries
- _key: normalises query (strip + lowercase), includes database and tier
- build_snapshot: copies all _CACHED_FIELDS from state
- restore_snapshot: writes fields back onto state
- Tier isolation: same query + db, different tier → separate entries
- DB isolation: same query, different db → separate entries
"""

import time
from unittest.mock import patch

import pytest

from src.core.query_cache import _CACHED_FIELDS, QueryCache, build_snapshot, restore_snapshot
from src.models.agent_state import AgentState


@pytest.fixture
def cache():
    return QueryCache(ttl_seconds=60)


def _snapshot() -> dict:
    return {field: None for field in _CACHED_FIELDS}


# ── get / put ──────────────────────────────────────────────────────────────────

class TestGetPut:

    def test_miss_returns_none(self, cache):
        assert cache.get("any query", "financial_db") is None

    def test_hit_returns_stored_snapshot(self, cache):
        snap = {"insights": "total transaksi 1 juta", "validated_sql": "SELECT 1"}
        cache.put("berapa total?", "financial_db", snap)
        result = cache.get("berapa total?", "financial_db")
        assert result == snap

    def test_expired_entry_returns_none(self, cache):
        snap = {"insights": "old"}
        cache.put("query", "db", snap)
        # Simulate time past TTL
        with patch("src.core.query_cache.time.monotonic", return_value=time.monotonic() + 61):
            result = cache.get("query", "db")
        assert result is None

    def test_expired_entry_is_evicted(self, cache):
        cache.put("query", "db", {"insights": "old"})
        with patch("src.core.query_cache.time.monotonic", return_value=time.monotonic() + 61):
            cache.get("query", "db")
        assert cache.size() == 0

    def test_different_database_is_different_entry(self, cache):
        cache.put("query", "financial_db", {"insights": "A"})
        assert cache.get("query", "other_db") is None

    def test_different_tier_is_different_entry(self, cache):
        cache.put("query", "db", {"insights": "standard"}, tier="standard")
        assert cache.get("query", "db", tier="detailed") is None

    def test_same_query_same_tier_hits(self, cache):
        cache.put("query", "db", {"insights": "ok"}, tier="detailed")
        result = cache.get("query", "db", tier="detailed")
        assert result is not None


# ── _key normalisation ─────────────────────────────────────────────────────────

class TestKeyNormalisation:

    def test_query_stripped_and_lowercased(self, cache):
        cache.put("  BERAPA TOTAL?  ", "db", {"insights": "ok"})
        result = cache.get("berapa total?", "db")
        assert result is not None

    def test_case_difference_hits_same_entry(self, cache):
        cache.put("Berapa Revenue GoPay?", "financial_db", {"insights": "x"})
        result = cache.get("berapa revenue gopay?", "financial_db")
        assert result is not None

    def test_different_whitespace_misses(self, cache):
        """Internal whitespace is NOT normalised — only strip+lower."""
        cache.put("a b", "db", {"insights": "x"})
        assert cache.get("a  b", "db") is None


# ── clear / size ───────────────────────────────────────────────────────────────

class TestClearSize:

    def test_clear_empties_cache(self, cache):
        cache.put("q1", "db", {"insights": "1"})
        cache.put("q2", "db", {"insights": "2"})
        cache.clear()
        assert cache.size() == 0

    def test_size_counts_non_expired_entries(self, cache):
        cache.put("q1", "db", {"insights": "1"})
        cache.put("q2", "db", {"insights": "2"})
        assert cache.size() == 2

    def test_size_excludes_expired_entries(self, cache):
        cache.put("q1", "db", {"insights": "live"})
        # Inject an already-expired entry by manipulating internal store
        key = QueryCache._key("expired", "db")
        from src.core.query_cache import _CacheEntry
        cache._store[key] = _CacheEntry(snapshot={}, expires_at=time.monotonic() - 1)
        assert cache.size() == 1

    def test_empty_cache_size_is_zero(self, cache):
        assert cache.size() == 0


# ── build_snapshot / restore_snapshot ─────────────────────────────────────────

class TestSnapshotHelpers:

    def test_build_snapshot_copies_all_cached_fields(self):
        state = AgentState(query="test", database="financial_db")
        state.insights = "some insight"
        state.validated_sql = "SELECT 1"
        snap = build_snapshot(state)
        for field in _CACHED_FIELDS:
            assert field in snap

    def test_build_snapshot_captures_actual_values(self):
        state = AgentState(query="test", database="financial_db")
        state.insights = "answer text"
        state.row_count = 42
        snap = build_snapshot(state)
        assert snap["insights"] == "answer text"
        assert snap["row_count"] == 42

    def test_restore_snapshot_writes_fields_back(self):
        state = AgentState(query="test", database="financial_db")
        snap = {field: None for field in _CACHED_FIELDS}
        snap["insights"] = "restored insight"
        snap["row_count"] = 7
        restore_snapshot(state, snap)
        assert state.insights == "restored insight"
        assert state.row_count == 7

    def test_restore_returns_state(self):
        state = AgentState(query="test", database="financial_db")
        snap = {field: None for field in _CACHED_FIELDS}
        result = restore_snapshot(state, snap)
        assert result is state

    def test_round_trip_preserves_values(self):
        state = AgentState(query="test", database="financial_db")
        state.insights = "round trip"
        state.validated_sql = "SELECT 2"
        state.row_count = 5

        snap = build_snapshot(state)
        new_state = AgentState(query="other", database="financial_db")
        restore_snapshot(new_state, snap)

        assert new_state.insights == "round trip"
        assert new_state.validated_sql == "SELECT 2"
        assert new_state.row_count == 5
