"""
E2E tests for SQL accuracy and system limitations — Telkomsel financial payment domain.

Tests compare generated SQL against expected patterns
and reveal system limitations with various query types.

Requirements:
    - Valid .env with ANTHROPIC_API_KEY
    - ChromaDB indexed
    - PostgreSQL running with financial_db

Run:
    pytest tests/e2e/test_sql_accuracy.py -v -s
"""

import pytest

from src.models.agent_state import AgentState
from tests.e2e.conftest import run_full_pipeline

# ========================================
# Test Cases Definition
# ========================================

SIMPLE_QUERIES = [
    {
        "query": "berapa total transaksi bulan April 2026?",
        "expected_sql_contains": ["SUM", "total_trx", "daily_master"],
        "expected_intent": "aggregation",
        "description": "Total transaction count April 2026",
    },
    {
        "query": "success rate per partner bulan Mei 2026",
        "expected_sql_contains": ["success_trx", "total_trx", "partner"],
        "expected_intent": "aggregation",
        "description": "Success rate grouped by partner",
    },
    {
        "query": "berapa total revenue bulan April?",
        "expected_sql_contains": ["SUM", "net_revenue"],
        "expected_intent": "aggregation",
        "description": "Total net revenue for April",
    },
]

FILTERED_QUERIES = [
    {
        "query": "transaksi gopay bulan April 2026",
        "expected_sql_contains": ["WHERE", "partner", "gopay"],
        "expected_intent": "filtered_query",
        "description": "Filter transactions by GoPay partner",
    },
    {
        "query": "partner dengan success rate di bawah 80%",
        "expected_sql_contains": ["WHERE", "success_trx", "total_trx"],
        "expected_intent": "filtered_query",
        "description": "Partners below 80% success rate threshold",
    },
]

JOIN_QUERIES = [
    {
        "query": "top 5 partner berdasarkan revenue bulan April 2026",
        "expected_sql_contains": ["partner", "ORDER BY", "LIMIT 5"],
        "expected_intent": "multi_table_join",
        "description": "Top 5 partners ranked by revenue",
    },
    {
        "query": "transaksi harian per channel bulan April",
        "expected_sql_contains": ["channel_payment", "periode", "GROUP BY"],
        "expected_intent": "multi_table_join",
        "description": "Daily transaction breakdown by payment channel",
    },
]

EDGE_CASE_QUERIES = [
    {
        "query": "show me the data",
        "expected_ambiguous": True,
        "description": "Vague query - should be ambiguous",
    },
    {
        "query": "apa itu gopay?",
        "expected_ambiguous": True,
        "description": "Non-data question - should be ambiguous",
    },
    {
        "query": "transaksi partner bulan depan",
        "expected_empty_result": True,
        "description": "Future date - should return empty result",
    },
]


# ========================================
# Test: Simple Queries Accuracy
# ========================================

class TestSimpleQueriesAccuracy:

    @pytest.mark.parametrize("test_case", SIMPLE_QUERIES)
    def test_simple_query_accuracy(self, real_agents, test_case):
        """Simple queries should generate correct SQL against financial_db."""
        state = run_full_pipeline(real_agents, test_case["query"])

        print(f"\n{'='*60}")
        print(f"Description: {test_case['description']}")
        print(f"Query      : {test_case['query']}")
        print(f"Intent     : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL        :\n{state.validated_sql}")
        print(f"Row count  : {state.row_count}")
        print(f"Insights   : {state.insights}")

        if "expected_intent" in test_case:
            assert state.intent["category"] == test_case["expected_intent"], (
                f"Expected intent '{test_case['expected_intent']}' "
                f"but got '{state.intent['category']}'"
            )

        for keyword in test_case["expected_sql_contains"]:
            assert keyword.upper() in state.validated_sql.upper(), (
                f"Expected '{keyword}' in SQL but got:\n{state.validated_sql}"
            )


# ========================================
# Test: Filtered Queries Accuracy
# ========================================

class TestFilteredQueriesAccuracy:

    @pytest.mark.parametrize("test_case", FILTERED_QUERIES)
    def test_filtered_query_accuracy(self, real_agents, test_case):
        """Filtered queries should generate SQL with WHERE clause referencing financial_db columns."""
        state = run_full_pipeline(real_agents, test_case["query"])

        print(f"\n{'='*60}")
        print(f"Description: {test_case['description']}")
        print(f"Query      : {test_case['query']}")
        print(f"Intent     : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL        :\n{state.validated_sql}")
        print(f"Row count  : {state.row_count}")
        print(f"Insights   : {state.insights}")

        for keyword in test_case["expected_sql_contains"]:
            assert keyword.upper() in state.validated_sql.upper(), (
                f"Expected '{keyword}' in SQL but got:\n{state.validated_sql}"
            )


# ========================================
# Test: Join Queries Accuracy
# ========================================

class TestJoinQueriesAccuracy:

    @pytest.mark.parametrize("test_case", JOIN_QUERIES)
    def test_join_query_accuracy(self, real_agents, test_case):
        """Join/aggregation queries should generate SQL referencing financial_db tables."""
        state = run_full_pipeline(real_agents, test_case["query"], database="financial_db")

        print(f"\n{'='*60}")
        print(f"Description: {test_case['description']}")
        print(f"Query      : {test_case['query']}")
        print(f"Intent     : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL        :\n{state.validated_sql}")
        print(f"Row count  : {state.row_count}")
        print(f"Insights   : {state.insights}")

        for keyword in test_case["expected_sql_contains"]:
            assert keyword.upper() in state.validated_sql.upper(), (
                f"Expected '{keyword}' in SQL but got:\n{state.validated_sql}"
            )


# ========================================
# Test: Edge Cases & Limitations
# ========================================

class TestEdgeCasesAndLimitations:

    @pytest.mark.parametrize("test_case", EDGE_CASE_QUERIES)
    def test_edge_cases(self, real_agents, test_case):
        """Edge cases should be handled gracefully."""
        state = run_full_pipeline(real_agents, test_case["query"])

        print(f"\n{'='*60}")
        print(f"Description        : {test_case['description']}")
        print(f"Query              : {test_case['query']}")
        print(f"Needs clarification: {state.needs_clarification}")
        print(f"SQL                : {state.validated_sql}")
        print(f"Row count          : {state.row_count}")
        print(f"Insights           : {state.insights}")

        if test_case.get("expected_ambiguous"):
            assert state.needs_clarification is True, (
                f"Expected ambiguous but got intent: {state.intent}"
            )

        if test_case.get("expected_empty_result"):
            assert state.row_count == 0, (
                f"Expected 0 rows but got {state.row_count}"
            )


# ========================================
# Test: System Limitations Report
# ========================================

class TestLimitationsReport:

    def _run_and_report(self, real_agents, query: str, label: str) -> AgentState:
        """Run pipeline and return partial state even if later stages fail."""
        state = AgentState(query=query, database="financial_db")
        try:
            state = run_full_pipeline(real_agents, query)
        except Exception as exc:
            print(f"\n[LIMITATION] Pipeline raised: {type(exc).__name__}: {exc}")
        return state

    def test_complex_analytics_limitation(self, real_agents):
        """
        Test complex analytics query with period comparison.
        Reveals limitation: may not handle multi-step comparisons or window functions well.
        """
        state = self._run_and_report(
            real_agents,
            "bandingkan revenue April 2026 vs Maret 2026 per partner",
            "Complex period comparison",
        )

        print(f"\n{'='*60}")
        print("LIMITATION TEST: Complex period comparison")
        print(f"Query    : {state.query}")
        print(f"Intent   : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL      :\n{state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")
        print(f"Errors   : {state.errors}")

        assert state.intent is not None

    def test_indonesian_query_limitation(self, real_agents):
        """
        Test full Indonesian financial query.
        Reveals limitation: Indonesian language understanding for domain-specific terms.
        """
        state = self._run_and_report(
            real_agents,
            "tampilkan mitra dengan jumlah transaksi gagal terbanyak bulan April 2026",
            "Full Indonesian financial query",
        )

        print(f"\n{'='*60}")
        print("LIMITATION TEST: Full Indonesian financial query")
        print(f"Query    : {state.query}")
        print(f"Intent   : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL      :\n{state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")

        assert state.intent is not None

    def test_multi_condition_limitation(self, real_agents):
        """
        Test query with multiple financial conditions.
        Reveals limitation: handling compound WHERE conditions across revenue and volume.
        """
        state = self._run_and_report(
            real_agents,
            "partner dengan net_revenue di atas 100 juta dan success rate di atas 90% bulan April 2026",
            "Multi-condition financial query",
        )

        print(f"\n{'='*60}")
        print("LIMITATION TEST: Multi-condition financial query")
        print(f"Query    : {state.query}")
        print(f"Intent   : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL      :\n{state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")

        assert state.intent is not None

    def test_print_full_timing_report(self, real_agents):
        """Print full timing report to identify bottlenecks."""
        queries = [
            "berapa total transaksi bulan April 2026?",
            "top 5 partner berdasarkan revenue bulan April 2026",
            "success rate per channel payment bulan April 2026",
        ]

        print(f"\n{'='*60}")
        print("TIMING REPORT")
        print(f"{'='*60}")

        for query in queries:
            state = run_full_pipeline(real_agents, query)
            total = sum(state.timing.values())

            print(f"\nQuery: {query}")
            for agent, ms in state.timing.items():
                pct = (ms / total * 100) if total > 0 else 0
                print(f"  {agent:<30} {ms:>8.0f}ms ({pct:.0f}%)")
            print(f"  {'TOTAL':<30} {total:>8.0f}ms")

        assert True  # Always pass; this is a reporting-only test
