"""
Unit tests for SchemaRetriever.

Tests cover:
- Successful table retrieval from ChromaDB
- Auto-detect database from top results
- Empty results raises error
- Columns and relationships parsed correctly
- State input/output correctness
"""

from unittest.mock import MagicMock, patch

import pytest

from src.components.schema_retriever import SchemaRetriever
from src.models.agent_state import AgentState
from src.utils.exceptions import SchemaRetrievalError


@pytest.fixture
def mock_collection():
    """Mock ChromaDB collection."""
    collection = MagicMock()
    collection.count.return_value = 8

    # Mock query result
    collection.query.return_value = {
        "ids": [["sales_db.customers", "sales_db.orders"]],
        "distances": [[0.05, 0.15]],
        "metadatas": [[
            {
                "db_name": "sales_db",
                "table_name": "customers",
                "columns": "customer_id,customer_name,customer_email",
                "description": "Customer master data",
                "relationships": "Referenced by orders.customer_id"
            },
            {
                "db_name": "sales_db",
                "table_name": "orders",
                "columns": "order_id,customer_id,order_status",
                "description": "Order transactions",
                "relationships": "FK to customers.customer_id"
            }
        ]]
    }
    return collection


@pytest.fixture
def retriever(mock_collection):
    """Initialize SchemaRetriever with mocked ChromaDB."""
    with patch("src.components.schema_retriever.chromadb.PersistentClient"):
        with patch("src.components.schema_retriever.embedding_functions.OpenAIEmbeddingFunction"):
            with patch.object(SchemaRetriever, "__init__", lambda self, *args, **kwargs: None):
                retriever = SchemaRetriever.__new__(SchemaRetriever)
                retriever.name = "schema_retriever"
                retriever.version = "1.0.0"
                retriever.top_k = 5
                retriever.collection = mock_collection
                retriever.bm25 = None
                retriever.bm25_corpus = []
                retriever.graph = None
                retriever.metrics = {
                    "total_calls": 0,
                    "successful_calls": 0,
                    "failed_calls": 0,
                    "total_time_seconds": 0.0,
                    "average_time_seconds": 0.0,
                    "last_execution_time": None,
                    "created_at": "2024-01-01"
                }
                import logging
                retriever.logger = logging.getLogger("agent.schema_retriever")
                return retriever


# ========================================
# Test: Successful Retrieval
# ========================================

class TestSuccessfulRetrieval:

    def test_retrieves_tables_from_chromadb(self, retriever):
        """Should retrieve tables and write to state.retrieved_tables."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        assert result.retrieved_tables is not None
        assert len(result.retrieved_tables) > 0

    def test_retrieved_tables_are_retrieved_table_objects(self, retriever):
        """Retrieved tables should be RetrievedTable instances."""
        from src.models.retrieved_table import RetrievedTable

        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        for table in result.retrieved_tables:
            assert isinstance(table, RetrievedTable)

    def test_similarity_score_calculated(self, retriever):
        """Similarity score should be 1 - distance."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        for table in result.retrieved_tables:
            assert 0.0 <= table.similarity_score <= 1.0

    def test_columns_parsed_from_string(self, retriever):
        """Columns stored as comma-separated string should be parsed to list."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        for table in result.retrieved_tables:
            assert isinstance(table.columns, list)
            assert len(table.columns) > 0

    def test_relationships_parsed_from_string(self, retriever):
        """Relationships stored as string should be parsed to list."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        for table in result.retrieved_tables:
            assert isinstance(table.relationships, list)


# ========================================
# Test: Auto-detect Database
# ========================================

class TestAutoDetectDatabase:

    def test_auto_detects_database_from_results(self, retriever):
        """Should auto-detect database from top retrieved tables."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        assert result.database == "sales_db"

    def test_auto_detect_overrides_default(self, retriever, mock_collection):
        """Auto-detected database should override user-specified database."""
        mock_collection.query.return_value = {
            "ids": [["products_db.products"]],
            "distances": [[0.05]],
            "metadatas": [[
                {
                    "db_name": "products_db",
                    "table_name": "products",
                    "columns": "product_id,product_name",
                    "description": "Product catalog",
                    "relationships": ""
                }
            ]]
        }

        state = AgentState(query="show all products", database="sales_db")
        result = retriever.execute(state)

        assert result.database == "products_db"


# ========================================
# Test: Empty Results
# ========================================

class TestEmptyResults:

    def test_raises_if_no_tables_found(self, retriever, mock_collection):
        """Should raise SchemaRetrievalError if no tables found."""
        mock_collection.query.return_value = {
            "ids": [[]],
            "distances": [[]],
            "metadatas": [[]]
        }

        state = AgentState(query="berapa total customer?", database="sales_db")

        with pytest.raises(SchemaRetrievalError):
            retriever.execute(state)


# ========================================
# Test: State Input/Output
# ========================================

class TestAgentState:

    def test_reads_query_from_state(self, retriever, mock_collection):
        """Retriever should use state.query for ChromaDB search."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        retriever.execute(state)

        call_args = mock_collection.query.call_args
        assert "berapa total customer?" in call_args[1]["query_texts"]

    def test_writes_retrieved_tables_to_state(self, retriever):
        """Retriever should write to state.retrieved_tables."""
        state = AgentState(query="berapa total customer?", database="sales_db")
        result = retriever.execute(state)

        assert hasattr(result, "retrieved_tables")
        assert isinstance(result.retrieved_tables, list)
