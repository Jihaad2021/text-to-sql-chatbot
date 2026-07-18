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

from src.agents.schema_retriever import SchemaRetriever
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
    with patch("src.agents.schema_retriever.chromadb.PersistentClient"):
        with patch("src.agents.schema_retriever.embedding_functions.OpenAIEmbeddingFunction"):
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


# ========================================
# Test: BM25 Retrieval
# ========================================

class TestBM25Retrieval:

    @pytest.fixture
    def retriever_with_bm25(self, mock_collection):
        """Retriever with both ChromaDB and BM25 enabled."""
        mock_bm25 = MagicMock()
        mock_bm25.get_scores.return_value = [3.5, 1.2, 0.0]

        corpus = [
            {"full_name": "fin_db.public.daily_master", "db_name": "fin_db",
             "table_name": "daily_master", "description": "daily payment data",
             "columns": ["date", "partner", "total_trx"], "relationships": []},
            {"full_name": "fin_db.public.anomalies",   "db_name": "fin_db",
             "table_name": "anomalies",    "description": "anomaly records",
             "columns": ["partner", "is_anomaly"], "relationships": []},
            {"full_name": "fin_db.public.unused",       "db_name": "fin_db",
             "table_name": "unused",       "description": "not relevant",
             "columns": ["id"], "relationships": []},
        ]

        with patch.object(SchemaRetriever, "__init__", lambda self, *a, **kw: None):
            r = SchemaRetriever.__new__(SchemaRetriever)
            r.name = "schema_retriever"
            r.version = "2.0.0"
            r.top_k = 5
            r.collection = mock_collection
            r.bm25 = mock_bm25
            r.bm25_corpus = corpus
            r.graph = None
            r.metrics = {
                "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
                "total_time_seconds": 0.0, "average_time_seconds": 0.0,
                "last_execution_time": None, "created_at": "2024-01-01",
            }
            import logging
            r.logger = logging.getLogger("agent.schema_retriever")
            return r

    def test_bm25_returns_positive_score_tables(self, retriever_with_bm25):
        """BM25 should return tables with score > 0 and exclude zero-score ones."""
        results = retriever_with_bm25._retrieve_bm25("kenapa SR turun")
        names = [r["table_name"] for r in results]
        assert "daily_master" in names
        assert "anomalies" in names
        assert "unused" not in names

    def test_bm25_zero_score_excluded(self, retriever_with_bm25):
        """Table with BM25 score == 0 must be excluded from results."""
        results = retriever_with_bm25._retrieve_bm25("kenapa SR turun")
        assert all(r["score"] > 0 for r in results)

    def test_bm25_disabled_returns_empty(self, retriever):
        """Retriever with bm25=None should return empty list without error."""
        results = retriever._retrieve_bm25("any query")
        assert results == []


# ========================================
# Test: Graph Retrieval
# ========================================

class TestGraphRetrieval:

    @pytest.fixture
    def retriever_with_graph(self, mock_collection):
        """Retriever with a minimal graph containing a joins_with edge."""
        import networkx as nx
        G = nx.DiGraph()

        G.add_node("fin_db.public.daily_master",
                   type="table", name="daily_master", db="fin_db",
                   schema="public", description="daily data", columns=["date", "partner"])
        G.add_node("fin_db.public.anomalies",
                   type="table", name="anomalies", db="fin_db",
                   schema="public", description="anomaly table", columns=["partner", "is_anomaly"])

        # daily_master → anomalies via joins_with
        G.add_edge("fin_db.public.daily_master", "fin_db.public.anomalies",
                   type="joins_with", via="partner → partner")

        with patch.object(SchemaRetriever, "__init__", lambda self, *a, **kw: None):
            r = SchemaRetriever.__new__(SchemaRetriever)
            r.name = "schema_retriever"
            r.version = "2.0.0"
            r.top_k = 5
            r.collection = mock_collection
            r.bm25 = None
            r.bm25_corpus = []
            r.graph = G
            r.metrics = {
                "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
                "total_time_seconds": 0.0, "average_time_seconds": 0.0,
                "last_execution_time": None, "created_at": "2024-01-01",
            }
            import logging
            r.logger = logging.getLogger("agent.schema_retriever")
            return r

    def test_graph_outgoing_neighbor_returned(self, retriever_with_graph):
        """daily_master → anomalies: seeding with daily_master should find anomalies."""
        seeds = [{"db_name": "fin_db", "schema_name": "public", "table_name": "daily_master"}]
        results = retriever_with_graph._retrieve_graph(seeds)
        names = [r["table_name"] for r in results]
        assert "anomalies" in names

    def test_graph_incoming_predecessor_returned(self, retriever_with_graph):
        """Bidirectional: seeding with anomalies should find daily_master (predecessor)."""
        seeds = [{"db_name": "fin_db", "schema_name": "public", "table_name": "anomalies"}]
        results = retriever_with_graph._retrieve_graph(seeds)
        names = [r["table_name"] for r in results]
        assert "daily_master" in names

    def test_graph_disabled_returns_empty(self, retriever):
        """Retriever with graph=None should return empty list without error."""
        seeds = [{"db_name": "x", "schema_name": "public", "table_name": "y"}]
        results = retriever._retrieve_graph(seeds)
        assert results == []

    def test_seed_not_in_graph_returns_empty(self, retriever_with_graph):
        """Seed table not present in graph should return empty list without error."""
        seeds = [{"db_name": "fin_db", "schema_name": "public", "table_name": "nonexistent_table"}]
        results = retriever_with_graph._retrieve_graph(seeds)
        assert results == []


# ========================================
# Test: RRF Fusion
# ========================================

class TestRRFFusion:

    @pytest.fixture
    def retriever_for_rrf(self, mock_collection):
        """Minimal retriever just for testing _rrf_fusion and _to_retrieved_tables."""
        with patch.object(SchemaRetriever, "__init__", lambda self, *a, **kw: None):
            r = SchemaRetriever.__new__(SchemaRetriever)
            r.name = "schema_retriever"
            r.top_k = 5
            r.collection = None
            r.bm25 = None
            r.bm25_corpus = []
            r.graph = None
            r.metrics = {}
            import logging
            r.logger = logging.getLogger("agent.schema_retriever")
            return r

    def _table(self, table_name: str, score: float = 1.0, source: str = "chromadb") -> dict:
        return {
            "id": f"fin_db.public.{table_name}",
            "db_name": "fin_db",
            "schema_name": "public",
            "table_name": table_name,
            "description": f"{table_name} desc",
            "columns": ["id"],
            "relationships": [],
            "score": score,
            "source": source,
        }

    def test_table_in_two_sources_scores_higher(self, retriever_for_rrf):
        """A table appearing in both chroma and BM25 must outrank a table in only one."""
        chroma = [self._table("daily_master"), self._table("anomalies")]
        bm25   = [self._table("daily_master", source="bm25")]

        fused = retriever_for_rrf._rrf_fusion([chroma, bm25])
        ids = [t["id"] for t in fused]

        daily_score   = next(t["rrf_score"] for t in fused if t["table_name"] == "daily_master")
        anomaly_score = next(t["rrf_score"] for t in fused if t["table_name"] == "anomalies")
        assert daily_score > anomaly_score

    def test_rrf_returns_sorted_by_score_descending(self, retriever_for_rrf):
        """Result must be sorted highest → lowest rrf_score."""
        chroma = [
            self._table("t1"),
            self._table("t2"),
            self._table("t3"),
        ]
        bm25 = [self._table("t3", source="bm25")]

        fused = retriever_for_rrf._rrf_fusion([chroma, bm25])
        scores = [t["rrf_score"] for t in fused]
        assert scores == sorted(scores, reverse=True)

    def test_empty_result_lists_produce_empty_fusion(self, retriever_for_rrf):
        fused = retriever_for_rrf._rrf_fusion([[], [], []])
        assert fused == []

    def test_all_tables_included_in_fusion(self, retriever_for_rrf):
        chroma = [self._table("t1")]
        bm25   = [self._table("t2", source="bm25")]
        graph  = [self._table("t3", source="graph")]

        fused = retriever_for_rrf._rrf_fusion([chroma, bm25, graph])
        names = {t["table_name"] for t in fused}
        assert names == {"t1", "t2", "t3"}
