"""
Component 2: Schema Retriever

Retrieves relevant table schemas using Hybrid Retrieval:
- ChromaDB (semantic/vector search)
- BM25 (keyword search)
- Graph (relationship traversal)
- RRF (Reciprocal Rank Fusion) to combine results

Type: Traditional (RAG-based)
Inherits: BaseAgent

Reads from state:
    - state.query
    - state.database

Writes to state:
    - state.retrieved_tables (List[RetrievedTable])
    - state.database (auto-detected from results)

Example:
    >>> retriever = SchemaRetriever()
    >>> state = AgentState(query="berapa total customer?")
    >>> state = retriever.execute(state)
    >>> print(state.retrieved_tables)
"""

import json
import os
import pickle
import re
from typing import Any

import chromadb
import networkx as nx
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

from src.core.base_agent import BaseAgent
from src.core.config import Config
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable
from src.utils.exceptions import SchemaRetrievalError

load_dotenv()


class SchemaRetriever(BaseAgent):
    """
    Retrieve relevant table schemas using Hybrid Retrieval.

    Combines ChromaDB + BM25 + Graph via RRF fusion for
    more accurate and robust table retrieval.
    """

    def __init__(self, top_k: int = Config.TOP_K_RETRIEVAL) -> None:
        super().__init__(name="schema_retriever", version="2.0.0")
        self.top_k = top_k

        self.collection          = self._init_chromadb()
        self.bm25, self.bm25_corpus = self._init_bm25()
        self.graph               = self._init_graph()

        self.log(
            f"Hybrid retrieval initialized: "
            f"ChromaDB={'OK' if self.collection else 'SKIP'} "
            f"BM25={'OK' if self.bm25 else 'SKIP'} "
            f"Graph={'OK' if self.graph else 'SKIP'}"
        )

    # ─────────────────────────────────────────────
    # INIT
    # ─────────────────────────────────────────────

    def _init_chromadb(self) -> chromadb.Collection | None:
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OPENAI_API_KEY not found — ChromaDB semantic search disabled")

            client = chromadb.PersistentClient(path=Config.CHROMA_PATH)
            embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=openai_key,
                model_name="text-embedding-3-small"
            )
            collection = client.get_collection(
                name="table_schemas",
                embedding_function=embedding_fn
            )
            self.log(f"ChromaDB loaded: {collection.count()} tables indexed")
            return collection

        except Exception as e:
            self.log(f"ChromaDB init failed: {e}", level="warning")
            return None

    def _init_bm25(self) -> tuple[Any, list]:
        try:
            if not os.path.exists(Config.BM25_INDEX_FILE):
                self.log(f"BM25 index not found at {Config.BM25_INDEX_FILE}", level="warning")
                return None, []

            with open(Config.BM25_INDEX_FILE, "rb") as f:
                data = pickle.load(f)

            self.log(f"BM25 loaded: {len(data['corpus'])} tables indexed")
            return data["bm25"], data["corpus"]

        except Exception as e:
            self.log(f"BM25 init failed: {e}", level="warning")
            return None, []

    def _init_graph(self) -> nx.DiGraph | None:
        try:
            if not os.path.exists(Config.GRAPH_INDEX_FILE):
                self.log(f"Graph not found at {Config.GRAPH_INDEX_FILE}", level="warning")
                return None

            with open(Config.GRAPH_INDEX_FILE, "r") as f:
                data = json.load(f)

            G = nx.node_link_graph(data, directed=True)
            table_count = sum(1 for _, d in G.nodes(data=True) if d.get("type") == "table")
            self.log(f"Graph loaded: {G.number_of_nodes()} nodes, {table_count} tables")
            return G

        except Exception as e:
            self.log(f"Graph init failed: {e}", level="warning")
            return None

    # ─────────────────────────────────────────────
    # EXECUTE
    # ─────────────────────────────────────────────

    def execute(self, state: AgentState) -> AgentState:
        """
        Retrieve relevant tables using hybrid retrieval.

        Args:
            state: Pipeline state with state.query

        Returns:
            Updated state with state.retrieved_tables and state.database
        """
        chroma_results = self._retrieve_chromadb(state.query)
        bm25_results   = self._retrieve_bm25(state.query)
        graph_results  = self._retrieve_graph(chroma_results)

        fused = self._rrf_fusion([chroma_results, bm25_results, graph_results])
        retrieved_tables = self._to_retrieved_tables(fused[:self.top_k])

        if not retrieved_tables:
            raise SchemaRetrievalError(
                agent_name=self.name,
                message="No relevant tables found for query"
            )

        # Auto-detect database
        detected_db = self._detect_database(retrieved_tables)
        db_names_in_results = [t.db_name for t in retrieved_tables]
        if state.database not in db_names_in_results:
            state.database = detected_db

        state.retrieved_tables = retrieved_tables

        self.log(
            f"Retrieved {len(retrieved_tables)} tables "
            f"(chroma:{len(chroma_results)} bm25:{len(bm25_results)} graph:{len(graph_results)}), "
            f"database: {state.database}"
        )

        return state

    # ─────────────────────────────────────────────
    # RETRIEVERS
    # ─────────────────────────────────────────────

    def _retrieve_chromadb(self, query: str) -> list[dict]:
        if not self.collection:
            return []
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(self.top_k * 2, 10)
            )
            tables = []
            if results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    meta     = results["metadatas"][0][i]
                    distance = results["distances"][0][i]
                    tables.append({
                        "id": results["ids"][0][i],
                        "db_name": meta.get("db_name", ""),
                        "schema_name": meta.get("schema_name", "public"),
                        "table_name": meta.get("table_name", ""),
                        "description": meta.get("description", ""),
                        "columns": self._parse_list(meta.get("columns", [])),
                        "relationships": self._parse_list(meta.get("relationships", []), sep=";"),
                        "score": 1.0 - distance,
                        "source": "chromadb"
                    })
            return tables
        except Exception as e:
            self.log(f"ChromaDB retrieval failed: {e}", level="warning")
            return []

    def _retrieve_bm25(self, query: str) -> list[dict]:
        if not self.bm25 or not self.bm25_corpus:
            return []
        try:
            tokens = re.findall(r'[a-zA-Z0-9]+', query.lower())
            scores = self.bm25.get_scores(tokens)

            indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            top_results = [(i, s) for i, s in indexed if s > 0][:self.top_k * 2]

            tables = []
            for idx, score in top_results:
                meta = self.bm25_corpus[idx]
                tables.append({
                    "id": meta["full_name"],
                    "db_name": meta["db_name"],
                    "schema_name": meta.get("schema_name", "public"),
                    "table_name": meta["table_name"],
                    "description": meta.get("description", ""),
                    "columns": meta.get("columns", []),
                    "relationships": meta.get("relationships", []),
                    "score": score,
                    "source": "bm25"
                })
            return tables
        except Exception as e:
            self.log(f"BM25 retrieval failed: {e}", level="warning")
            return []

    def _retrieve_graph(self, seed_tables: list[dict]) -> list[dict]:
        if not self.graph or not seed_tables:
            return []
        try:
            related: dict[str, dict] = {}
            for seed in seed_tables[:3]:
                db   = seed["db_name"]
                sch  = seed.get("schema_name", "public")
                tbl  = seed["table_name"]
                node = f"{db}.{sch}.{tbl}"

                if not self.graph.has_node(node):
                    continue

                for neighbor in self.graph.neighbors(node):
                    node_data = self.graph.nodes[neighbor]
                    if node_data.get("type") != "table":
                        continue
                    edge_data = self.graph.edges[node, neighbor]
                    if edge_data.get("type") != "joins_with":
                        continue
                    if neighbor not in related:
                        related[neighbor] = {
                            "id": neighbor,
                            "db_name": node_data.get("db", ""),
                            "schema_name": node_data.get("schema", "public"),
                            "table_name": node_data.get("name", ""),
                            "description": node_data.get("description", ""),
                            "columns": node_data.get("columns", []),
                            "relationships": [],
                            "score": 1.0,
                            "source": "graph"
                        }
            return list(related.values())
        except Exception as e:
            self.log(f"Graph retrieval failed: {e}", level="warning")
            return []

    # ─────────────────────────────────────────────
    # RRF FUSION
    # ─────────────────────────────────────────────

    def _rrf_fusion(self, result_lists: list[list[dict]]) -> list[dict]:
        """Reciprocal Rank Fusion — combine multiple ranked lists."""
        rrf_scores: dict[str, float] = {}
        table_data: dict[str, dict] = {}

        for result_list in result_lists:
            for rank, table in enumerate(result_list, start=1):
                table_id  = table["id"]
                rrf_score = 1.0 / (Config.RRF_K + rank)
                rrf_scores[table_id] = rrf_scores.get(table_id, 0) + rrf_score

                if table_id not in table_data or table.get("source") == "chromadb":
                    table_data[table_id] = table

        sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)  # type: ignore[arg-type]

        result = []
        for table_id in sorted_ids:
            table = table_data[table_id].copy()
            table["rrf_score"] = rrf_scores[table_id]
            result.append(table)

        return result

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _to_retrieved_tables(self, tables: list[dict]) -> list[RetrievedTable]:
        return [
            RetrievedTable(
                db_name=t.get("db_name", ""),
                table_name=t.get("table_name", ""),
                columns=t.get("columns", []),
                description=t.get("description", ""),
                similarity_score=t.get("rrf_score", t.get("score", 0.0)),
                relationships=t.get("relationships", [])
            )
            for t in tables
        ]

    def _detect_database(self, tables: list[RetrievedTable]) -> str:
        if not tables:
            return "sales_db"

        db_scores: dict[str, float] = {}
        for i, table in enumerate(tables[:5]):
            weight = 1.0 / (i + 1)
            db = table.db_name
            db_scores[db] = db_scores.get(db, 0) + (table.similarity_score * weight)

        return max(db_scores, key=db_scores.get)  # type: ignore[arg-type]

    def _parse_list(self, data: list | str, sep: str = ",") -> list[str]:
        if isinstance(data, list):
            return data
        return [x.strip() for x in str(data).split(sep) if x.strip()]

    def get_all_tables(self) -> list[str]:
        try:
            all_data = self.collection.get()
            return [
                f"{m['db_name']}.{m['table_name']}"
                for m in all_data["metadatas"]
            ]
        except Exception:
            return []
