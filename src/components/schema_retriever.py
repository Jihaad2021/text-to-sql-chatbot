"""
Component 2: Schema Retriever

Retrieves relevant table schemas using ChromaDB semantic search (RAG).
Does not use LLM - purely traditional retrieval.

Type: Traditional (RAG-based)
Inherits: BaseAgent

Reads from state:
    - state.query
    - state.database

Writes to state:
    - state.retrieved_tables (List[RetrievedTable])
    - state.database (auto-detected from top retrieved tables)

Example:
    >>> retriever = SchemaRetriever()
    >>> state = AgentState(query="berapa total customer?")
    >>> state = retriever.run(state)
    >>> print(state.retrieved_tables)
    [RetrievedTable(db_name='sales_db', table_name='customers', score=0.95)]
"""

import os
from typing import List
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

from src.core.base_agent import BaseAgent
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable
from src.utils.exceptions import SchemaRetrievalError

load_dotenv()


class SchemaRetriever(BaseAgent):
    """
    Retrieve relevant table schemas using ChromaDB semantic search.

    Uses OpenAI embeddings to find tables most semantically similar
    to the user query. Auto-detects target database from results.
    """

    def __init__(self, chroma_path: str = "./chroma_db", top_k: int = 5):
        """
        Initialize Schema Retriever with ChromaDB.

        Args:
            chroma_path: Path to ChromaDB persistent storage
            top_k: Number of tables to retrieve

        Raises:
            SchemaRetrievalError: If ChromaDB collection not found
        """
        super().__init__(name="schema_retriever", version="1.0.0")

        self.top_k = top_k

        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=chroma_path)
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_key,
            model_name="text-embedding-3-small"
        )

        try:
            self.collection = self.chroma_client.get_collection(
                name="table_schemas",
                embedding_function=self.embedding_function
            )
            count = self.collection.count()
            self.log(f"ChromaDB loaded: {count} tables indexed")

        except Exception as e:
            raise SchemaRetrievalError(
                agent_name=self.name,
                message=f"Failed to load ChromaDB collection: {str(e)}"
            )

    def execute(self, state: AgentState) -> AgentState:
        """
        Retrieve relevant tables for user query.

        Args:
            state: Pipeline state with state.query

        Returns:
            Updated state with:
            - state.retrieved_tables (List[RetrievedTable])
            - state.database (auto-detected)
        """
        results = self.collection.query(
            query_texts=[state.query],
            n_results=min(self.top_k, 10)
        )

        retrieved_tables = self._parse_results(results)

        if not retrieved_tables:
            raise SchemaRetrievalError(
                agent_name=self.name,
                message="No relevant tables found for query"
            )

        # Auto-detect database from top 3 results
        state.database = self._detect_database(retrieved_tables)
        state.retrieved_tables = retrieved_tables

        self.log(
            f"Retrieved {len(retrieved_tables)} tables, "
            f"auto-detected database: {state.database}"
        )

        return state

    def _parse_results(self, results: dict) -> List[RetrievedTable]:
        """Parse ChromaDB results into RetrievedTable list."""
        tables = []

        if not results["ids"] or not results["ids"][0]:
            return tables

        for i in range(len(results["ids"][0])):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            similarity = 1.0 - distance

            # Parse columns
            columns_data = metadata.get("columns", [])
            columns = (
                columns_data if isinstance(columns_data, list)
                else [c.strip() for c in str(columns_data).split(",") if c.strip()]
            )

            # Parse relationships
            relationships_data = metadata.get("relationships", [])
            relationships = (
                relationships_data if isinstance(relationships_data, list)
                else [r.strip() for r in str(relationships_data).split(";") if r.strip()]
            )

            tables.append(RetrievedTable(
                db_name=metadata.get("db_name", ""),
                table_name=metadata.get("table_name", ""),
                columns=columns,
                description=metadata.get("description", ""),
                similarity_score=similarity,
                relationships=relationships
            ))

        return tables

    def _detect_database(self, tables: List[RetrievedTable]) -> str:
        """Auto-detect database from table with highest similarity score."""
        if not tables:
            return "sales_db"
        
        # Gunakan database dari tabel paling relevan (score tertinggi)
        return tables[0].db_name
    
    def get_all_tables(self) -> List[str]:
        """Get all indexed table names (for debugging)."""
        try:
            all_data = self.collection.get()
            return [
                f"{m['db_name']}.{m['table_name']}"
                for m in all_data["metadatas"]
            ]
        except Exception:
            return []