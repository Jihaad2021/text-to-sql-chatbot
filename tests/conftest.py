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
        query="berapa total customer?",
        database="sales_db"
    )


@pytest.fixture
def ambiguous_state():
    """AgentState with an ambiguous query."""
    return AgentState(
        query="show me the data",
        database="sales_db"
    )


@pytest.fixture
def join_state():
    """AgentState with a multi-table join query."""
    return AgentState(
        query="top 5 customer berdasarkan total spending",
        database="sales_db"
    )


# ========================================
# RetrievedTable Fixtures
# ========================================

@pytest.fixture
def customers_table():
    """Mock customers table."""
    return RetrievedTable(
        db_name="sales_db",
        table_name="customers",
        columns=["customer_id", "customer_name", "customer_email", "customer_city"],
        description="Customer master data including buyer information and contact details",
        similarity_score=0.95,
        relationships=["Referenced by orders.customer_id (1:N)"]
    )


@pytest.fixture
def orders_table():
    """Mock orders table."""
    return RetrievedTable(
        db_name="sales_db",
        table_name="orders",
        columns=["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
        description="Sales transactions and order history",
        similarity_score=0.85,
        relationships=["FK to customers.customer_id", "Referenced by payments.order_id"]
    )


@pytest.fixture
def payments_table():
    """Mock payments table."""
    return RetrievedTable(
        db_name="sales_db",
        table_name="payments",
        columns=["payment_id", "order_id", "payment_type", "payment_value"],
        description="Payment transactions and revenue data",
        similarity_score=0.80,
        relationships=["FK to orders.order_id"]
    )


@pytest.fixture
def sample_tables(customers_table, orders_table, payments_table):
    """List of mock retrieved tables."""
    return [customers_table, orders_table, payments_table]


# ========================================
# State with pre-filled data (for downstream agents)
# ========================================

@pytest.fixture
def state_with_intent(sample_state):
    """AgentState with intent already classified."""
    sample_state.intent = {
        "category": "aggregation",
        "confidence": 0.95,
        "reason": "Query asks for count/total",
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
    state_with_tables.sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"
    state_with_tables.validated_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"
    return state_with_tables


@pytest.fixture
def state_with_results(state_with_sql):
    """AgentState with query results."""
    state_with_sql.query_result = [{"total": 100}]
    state_with_sql.row_count = 1
    return state_with_sql


# ========================================
# Mock LLM Response
# ========================================

@pytest.fixture
def mock_llm_aggregation():
    """Mock LLM response for aggregation intent."""
    return "INTENT: aggregation\nCONFIDENCE: 0.95\nREASON: Query asks for count"


@pytest.fixture
def mock_llm_ambiguous():
    """Mock LLM response for ambiguous intent."""
    return "INTENT: ambiguous\nCONFIDENCE: 1.0\nREASON: Query is too vague"


@pytest.fixture
def mock_llm_sql():
    """Mock LLM response for SQL generation."""
    return "SELECT COUNT(*) as total FROM customers LIMIT 100;"


@pytest.fixture
def mock_llm_insight():
    """Mock LLM response for insight generation."""
    return "Terdapat 100 customer yang terdaftar dalam sistem."
