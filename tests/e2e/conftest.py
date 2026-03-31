"""
conftest_e2e.py - Fixtures for e2e tests using real API and database.

Unlike unit tests, these fixtures initialize REAL agents with:
- Real Anthropic API calls
- Real ChromaDB connection
- Real PostgreSQL connection

Requirements:
- .env file with valid credentials
- ChromaDB indexed (run scripts/index_schemas.py first)
- PostgreSQL running and accessible

Run e2e tests:
    pytest tests/e2e/ -v -s
"""

import pytest
from src.models.agent_state import AgentState
from src.components.intent_classifier import IntentClassifier
from src.components.schema_retriever import SchemaRetriever
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.components.query_executor import QueryExecutor
from src.components.insight_generator import InsightGenerator


# ========================================
# Real Agent Fixtures
# ========================================

@pytest.fixture(scope="session")
def real_intent_classifier():
    """Real IntentClassifier with Anthropic API."""
    return IntentClassifier()


@pytest.fixture(scope="session")
def real_schema_retriever():
    """Real SchemaRetriever with ChromaDB."""
    return SchemaRetriever()


@pytest.fixture(scope="session")
def real_retrieval_evaluator():
    """Real RetrievalEvaluator with Anthropic API."""
    return RetrievalEvaluator()


@pytest.fixture(scope="session")
def real_sql_generator():
    """Real SQLGenerator with Anthropic API."""
    return SQLGenerator()


@pytest.fixture(scope="session")
def real_sql_validator():
    """Real SQLValidator (AI validation disabled for speed)."""
    return SQLValidator(enable_ai_validation=False)


@pytest.fixture(scope="session")
def real_query_executor():
    """Real QueryExecutor with PostgreSQL."""
    return QueryExecutor()


@pytest.fixture(scope="session")
def real_insight_generator():
    """Real InsightGenerator with Anthropic API."""
    return InsightGenerator()


@pytest.fixture(scope="session")
def real_agents(
    real_intent_classifier,
    real_schema_retriever,
    real_retrieval_evaluator,
    real_sql_generator,
    real_sql_validator,
    real_query_executor,
    real_insight_generator
):
    """All real agents bundled together."""
    return {
        "intent": real_intent_classifier,
        "retriever": real_schema_retriever,
        "evaluator": real_retrieval_evaluator,
        "generator": real_sql_generator,
        "validator": real_sql_validator,
        "executor": real_query_executor,
        "insight": real_insight_generator
    }


# ========================================
# Helper: Run Full Pipeline
# ========================================

def run_full_pipeline(agents: dict, query: str, database: str = "sales_db") -> AgentState:
    """
    Run complete pipeline with real agents.

    Args:
        agents: Dict of real agents
        query: User query string
        database: Target database

    Returns:
        Final AgentState after all agents
    """
    state = AgentState(query=query, database=database)

    # Step 1: Intent
    state = agents["intent"].run(state)
    if state.needs_clarification:
        return state

    # Step 2: Retrieval
    state = agents["retriever"].execute(state)

    # Step 3: Evaluation
    state = agents["evaluator"].run(state)

    # Step 4: SQL Generation
    state = agents["generator"].run(state)

    # Step 5: Validation
    state = agents["validator"].run(state)

    # Step 6: Execution
    state = agents["executor"].run(state)

    # Step 7: Insights
    state = agents["insight"].run(state)

    return state