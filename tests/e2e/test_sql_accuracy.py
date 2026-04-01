"""
E2E tests for SQL accuracy and system limitations.

Tests compare generated SQL against expected patterns
and reveal system limitations with various query types.

Requirements:
    - Valid .env with ANTHROPIC_API_KEY
    - ChromaDB indexed
    - PostgreSQL running

Run:
    pytest tests/e2e/test_sql_accuracy.py -v -s
"""

import pytest
from tests.e2e.conftest import run_full_pipeline
from src.models.agent_state import AgentState


# ========================================
# Test Cases Definition
# ========================================

SIMPLE_QUERIES = [
    {
        "query": "berapa total customer?",
        "expected_sql_contains": ["COUNT", "customers"],
        "expected_intent": "aggregation",
        "description": "Simple count"
    },
    {
        "query": "tampilkan semua customer",
        "expected_sql_contains": ["SELECT", "customers", "LIMIT"],
        "expected_intent": "simple_select",
        "description": "Simple select all"
    },
    {
        "query": "berapa total nilai pembayaran dari semua transaksi?",
        "expected_sql_contains": ["SUM", "payment_value"],
        "expected_intent": "aggregation",
        "description": "Total revenue"
    }
]

FILTERED_QUERIES = [
    {
        "query": "tampilkan customer dari Jakarta",
        "expected_sql_contains": ["WHERE", "customers", "Jakarta"],
        "expected_intent": "filtered_query",
        "description": "Filter by city"
    },
    {
        "query": "tampilkan semua orders yang statusnya delivered",
        "expected_sql_contains": ["WHERE", "orders", "delivered"],
        "expected_intent": "filtered_query",
        "description": "Filter by status"
    }
]

JOIN_QUERIES = [
    {
        "query": "top 5 customer berdasarkan total spending",
        "expected_sql_contains": ["JOIN", "customers", "ORDER BY", "LIMIT 5"],
        "expected_intent": "multi_table_join",
        "description": "Top customers by spending"
    },
    {
        "query": "jumlah order per customer",
        "expected_sql_contains": ["JOIN", "COUNT", "GROUP BY"],
        "expected_intent": "multi_table_join",
        "description": "Order count per customer"
    }
]

EDGE_CASE_QUERIES = [
    {
        "query": "show me the data",
        "expected_ambiguous": True,
        "description": "Vague query - should be ambiguous"
    },
    {
        "query": "apa itu database?",
        "expected_ambiguous": True,
        "description": "Non-data query - should be ambiguous"
    },
    {
        "query": "customer yang order bulan depan",
        "expected_empty_result": True,
        "description": "Future date - should return empty"
    }
]


# ========================================
# Test: Simple Queries Accuracy
# ========================================

class TestSimpleQueriesAccuracy:

    @pytest.mark.parametrize("test_case", SIMPLE_QUERIES)
    def test_simple_query_accuracy(self, real_agents, test_case):
        """Simple queries should generate correct SQL."""
        state = run_full_pipeline(real_agents, test_case["query"])

        print(f"\n{'='*60}")
        print(f"Description: {test_case['description']}")
        print(f"Query      : {test_case['query']}")
        print(f"Intent     : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL        :\n{state.validated_sql}")
        print(f"Row count  : {state.row_count}")
        print(f"Insights   : {state.insights}")

        # Check intent
        if "expected_intent" in test_case:
            assert state.intent["category"] == test_case["expected_intent"], \
                f"Expected intent '{test_case['expected_intent']}' but got '{state.intent['category']}'"

        # Check SQL contains expected keywords
        for keyword in test_case["expected_sql_contains"]:
            assert keyword.upper() in state.validated_sql.upper(), \
                f"Expected '{keyword}' in SQL but got:\n{state.validated_sql}"


# ========================================
# Test: Filtered Queries Accuracy
# ========================================

class TestFilteredQueriesAccuracy:

    @pytest.mark.parametrize("test_case", FILTERED_QUERIES)
    def test_filtered_query_accuracy(self, real_agents, test_case):
        """Filtered queries should generate SQL with WHERE clause."""
        state = run_full_pipeline(real_agents, test_case["query"])

        print(f"\n{'='*60}")
        print(f"Description: {test_case['description']}")
        print(f"Query      : {test_case['query']}")
        print(f"Intent     : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL        :\n{state.validated_sql}")
        print(f"Row count  : {state.row_count}")
        print(f"Insights   : {state.insights}")

        for keyword in test_case["expected_sql_contains"]:
            assert keyword.upper() in state.validated_sql.upper(), \
                f"Expected '{keyword}' in SQL but got:\n{state.validated_sql}"


# ========================================
# Test: Join Queries Accuracy
# ========================================

class TestJoinQueriesAccuracy:

    @pytest.mark.parametrize("test_case", JOIN_QUERIES)
    def test_join_query_accuracy(self, real_agents, test_case):
        """Join queries should generate SQL with JOIN clause."""
        state = run_full_pipeline(real_agents, test_case["query"], database="sales_db")
        
        print(f"\n{'='*60}")
        print(f"Description: {test_case['description']}")
        print(f"Query      : {test_case['query']}")
        print(f"Intent     : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL        :\n{state.validated_sql}")
        print(f"Row count  : {state.row_count}")
        print(f"Insights   : {state.insights}")

        for keyword in test_case["expected_sql_contains"]:
            assert keyword.upper() in state.validated_sql.upper(), \
                f"Expected '{keyword}' in SQL but got:\n{state.validated_sql}"


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
            assert state.needs_clarification is True, \
                f"Expected ambiguous but got intent: {state.intent}"

        if test_case.get("expected_empty_result"):
            assert state.row_count == 0, \
                f"Expected 0 rows but got {state.row_count}"


# ========================================
# Test: System Limitations Report
# ========================================

class TestLimitationsReport:

    def test_complex_analytics_limitation(self, real_agents):
        """
        Test complex analytics query.
        Reveals limitation: may not handle window functions well.
        """
        state = run_full_pipeline(
            real_agents,
            "revenue per bulan dalam 3 bulan terakhir"
        )

        print(f"\n{'='*60}")
        print(f"LIMITATION TEST: Complex date analytics")
        print(f"Query    : {state.query}")
        print(f"Intent   : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL      :\n{state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")
        print(f"Errors   : {state.errors}")

        # Just check pipeline completes, not strict SQL check
        # This reveals if system can handle complex date queries
        assert state.intent is not None

    def test_indonesian_query_limitation(self, real_agents):
        """
        Test full Indonesian query.
        Reveals limitation: Indonesian language understanding.
        """
        state = run_full_pipeline(
            real_agents,
            "tampilkan pelanggan dengan total pembelian terbanyak"
        )

        print(f"\n{'='*60}")
        print(f"LIMITATION TEST: Full Indonesian query")
        print(f"Query    : {state.query}")
        print(f"Intent   : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL      :\n{state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")

        assert state.intent is not None

    def test_multi_condition_limitation(self, real_agents):
        """
        Test query with multiple conditions.
        Reveals limitation: handling complex WHERE conditions.
        """
        state = run_full_pipeline(
            real_agents,
            "customer dari Jakarta yang total ordernya lebih dari 5"
        )

        print(f"\n{'='*60}")
        print(f"LIMITATION TEST: Multi-condition query")
        print(f"Query    : {state.query}")
        print(f"Intent   : {state.intent['category'] if state.intent else 'N/A'}")
        print(f"SQL      :\n{state.validated_sql}")
        print(f"Row count: {state.row_count}")
        print(f"Insights : {state.insights}")

        assert state.intent is not None

    def test_print_full_timing_report(self, real_agents):
        """Print full timing report to identify bottlenecks."""
        queries = [
            "berapa total customer?",
            "top 5 customer by spending",
            "revenue per bulan"
        ]

        print(f"\n{'='*60}")
        print(f"TIMING REPORT")
        print(f"{'='*60}")

        for query in queries:
            state = run_full_pipeline(real_agents, query)
            total = sum(state.timing.values())

            print(f"\nQuery: {query}")
            for agent, ms in state.timing.items():
                pct = (ms / total * 100) if total > 0 else 0
                print(f"  {agent:<30} {ms:>8.0f}ms ({pct:.0f}%)")
            print(f"  {'TOTAL':<30} {total:>8.0f}ms")

        assert True  # Always pass, this is for reporting only