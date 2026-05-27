"""
conftest.py - Shared fixtures for all tests.

Fixtures defined here are automatically available to all test files
without needing to import them.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable

# ========================================
# AgentState Fixtures
# ========================================

@pytest.fixture
def sample_state():
    """Basic AgentState with a simple aggregation query."""
    return AgentState(
        query="berapa total transaksi bulan April 2026?",
        database="financial_db"
    )


@pytest.fixture
def ambiguous_state():
    """AgentState with an ambiguous query."""
    return AgentState(
        query="show me the data",
        database="financial_db"
    )


@pytest.fixture
def join_state():
    """AgentState with a multi-table join query."""
    return AgentState(
        query="top 5 partner berdasarkan revenue bulan April 2026",
        database="financial_db"
    )


# ========================================
# RetrievedTable Fixtures
# ========================================

@pytest.fixture
def daily_master_table():
    """Mock daily_master table."""
    return RetrievedTable(
        db_name="financial_db",
        table_name="daily_master",
        columns=[
            "channel_payment", "partner", "periode",
            "total_trx", "success_trx", "fail_trx",
            "net_revenue", "platform_fee", "net_gap",
        ],
        description="Daily aggregated payment transaction data per channel and partner",
        similarity_score=0.95,
        relationships=["Referenced by channel_payment.channel_code via channel_payment"]
    )


@pytest.fixture
def financial_internal_table():
    """Mock financial_internal table."""
    return RetrievedTable(
        db_name="financial_db",
        table_name="financial_internal",
        columns=[
            "partner", "periode",
            "total_trx", "success_trx", "fail_trx",
            "total_revenue", "platform_fee", "net_revenue", "net_gap",
        ],
        description="Internal financial records per partner with revenue breakdown",
        similarity_score=0.85,
        relationships=[]
    )


@pytest.fixture
def product_summary_table():
    """Mock product_summary table."""
    return RetrievedTable(
        db_name="financial_db",
        table_name="product_summary",
        columns=[
            "tsel_wallet", "product_name", "periode",
            "total_trx", "success_trx", "fail_trx", "total_revenue",
        ],
        description="Product-level transaction and revenue summary for Telkomsel wallet products",
        similarity_score=0.80,
        relationships=[]
    )


@pytest.fixture
def sample_tables(daily_master_table, financial_internal_table, product_summary_table):
    """List of mock retrieved tables."""
    return [daily_master_table, financial_internal_table, product_summary_table]


# ========================================
# State with pre-filled data (for downstream agents)
# ========================================

@pytest.fixture
def state_with_intent(sample_state):
    """AgentState with intent already classified."""
    sample_state.intent = {
        "category": "aggregation",
        "confidence": 0.95,
        "reason": "Query asks for count/total of transactions",
        "sql_strategy": "Use aggregate functions (COUNT/SUM/AVG) with GROUP BY if needed"
    }
    sample_state.needs_clarification = False
    return sample_state


@pytest.fixture
def state_with_tables(state_with_intent, sample_tables):
    """AgentState with retrieved and evaluated tables."""
    state_with_intent.retrieved_tables = sample_tables
    state_with_intent.evaluated_tables = sample_tables
    return state_with_intent


@pytest.fixture
def state_with_sql(state_with_tables):
    """AgentState with generated SQL."""
    state_with_tables.sql = (
        "SELECT SUM(total_trx) as total FROM daily_master "
        "WHERE periode = '2026-04' LIMIT 100;"
    )
    state_with_tables.validated_sql = (
        "SELECT SUM(total_trx) as total FROM daily_master "
        "WHERE periode = '2026-04' LIMIT 100;"
    )
    return state_with_tables


@pytest.fixture
def state_with_results(state_with_sql):
    """AgentState with query results."""
    state_with_sql.query_result = [{"total": 1500000}]
    state_with_sql.row_count = 1
    return state_with_sql


# ========================================
# Mock LLM Response
# ========================================

@pytest.fixture
def mock_llm_aggregation():
    """Mock LLM response for aggregation intent."""
    return "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Query asks for total transactions"


@pytest.fixture
def mock_llm_ambiguous():
    """Mock LLM response for ambiguous intent."""
    return "INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Query is too vague"


@pytest.fixture
def mock_llm_sql():
    """Mock LLM response for SQL generation."""
    return (
        "SELECT SUM(total_trx) as total FROM daily_master "
        "WHERE periode = '2026-04' LIMIT 100;"
    )


@pytest.fixture
def mock_llm_insight():
    """Mock LLM response for insight generation."""
    return "Total transaksi pada bulan April 2026 adalah 1.500.000 transaksi."
