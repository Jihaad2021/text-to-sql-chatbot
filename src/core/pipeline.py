"""
TextToSQLPipeline — Orchestrator for the 7-agent pipeline.

Separates pipeline sequencing from the API layer.
The pipeline owns the agents, runs them in order, and exposes
health-check and resource-cleanup interfaces.

Usage:
    >>> pipeline = TextToSQLPipeline(
    ...     intent_classifier=IntentClassifier(),
    ...     schema_retriever=SchemaRetriever(),
    ...     ...
    ... )
    >>> state = AgentState(query="berapa total customer?", database="sales_db")
    >>> state = pipeline.run(state)
    >>> print(state.insights)
"""

from typing import Any

from src.components.insight_generator import InsightGenerator
from src.components.intent_classifier import IntentClassifier
from src.components.query_executor import QueryExecutor
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.schema_retriever import SchemaRetriever
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.core.base_agent import BaseAgent
from src.models.agent_state import AgentState


class TextToSQLPipeline:
    """
    Orchestrates the 7-agent Text-to-SQL pipeline.

    Pipeline sequence:
        IntentClassifier → SchemaRetriever → RetrievalEvaluator
        → SQLGenerator → SQLValidator → QueryExecutor → InsightGenerator

    Early stop: pipeline returns after IntentClassifier if the query
    needs clarification (state.needs_clarification is True).
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        schema_retriever: SchemaRetriever,
        retrieval_evaluator: RetrievalEvaluator,
        sql_generator: SQLGenerator,
        sql_validator: SQLValidator,
        query_executor: QueryExecutor,
        insight_generator: InsightGenerator,
    ) -> None:
        self.intent_classifier   = intent_classifier
        self.schema_retriever    = schema_retriever
        self.retrieval_evaluator = retrieval_evaluator
        self.sql_generator       = sql_generator
        self.sql_validator       = sql_validator
        self.query_executor      = query_executor
        self.insight_generator   = insight_generator

    @property
    def agents(self) -> list[BaseAgent]:
        """All agents in pipeline order."""
        return [
            self.intent_classifier,
            self.schema_retriever,
            self.retrieval_evaluator,
            self.sql_generator,
            self.sql_validator,
            self.query_executor,
            self.insight_generator,
        ]

    # ─────────────────────────────────────────────
    # CORE
    # ─────────────────────────────────────────────

    def run(self, state: AgentState) -> AgentState:
        """
        Execute the full pipeline against a shared AgentState.

        Returns early (after intent classification) if the query is ambiguous.

        Args:
            state: Initial pipeline state with state.query and state.database

        Returns:
            Fully populated AgentState after all steps complete
        """
        state = self.intent_classifier.run(state)

        if state.needs_clarification:
            return state

        state = self.schema_retriever.run(state)
        state = self.retrieval_evaluator.run(state)
        state = self.sql_generator.run(state)
        state = self.sql_validator.run(state)
        state = self.query_executor.run(state)
        state = self.insight_generator.run(state)

        return state

    # ─────────────────────────────────────────────
    # HEALTH
    # ─────────────────────────────────────────────

    def check_health(self) -> dict[str, Any]:
        """
        Check real connectivity for all external dependencies.

        Returns:
            Dict with keys: databases, retrieval, agents, overall_healthy
        """
        db_status = self.query_executor.check_connectivity()

        chroma_status = (
            f"healthy ({self.schema_retriever.collection.count()} tables)"
            if self.schema_retriever.collection
            else "degraded (OPENAI_API_KEY not set)"
        )
        bm25_status  = "healthy" if self.schema_retriever.bm25  else "degraded (index not found)"
        graph_status = "healthy" if self.schema_retriever.graph else "degraded (graph not found)"

        return {
            "overall_healthy": all(v == "healthy" for v in db_status.values()),
            "databases": db_status,
            "retrieval": {
                "chromadb": chroma_status,
                "bm25":     bm25_status,
                "graph":    graph_status,
            },
            "agents": {
                agent.name: agent.get_metrics()
                for agent in self.agents
            },
        }

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def get_all_tables(self) -> list[str]:
        """Delegate to SchemaRetriever for /databases endpoint."""
        return self.schema_retriever.get_all_tables()

    def close(self) -> None:
        """Dispose all database connection pools."""
        self.query_executor.close()
