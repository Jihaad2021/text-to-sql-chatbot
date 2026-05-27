"""
TextToSQLPipeline — Orchestrator for the 8-agent pipeline.

Separates pipeline sequencing from the API layer.
The pipeline owns the agents, runs them in order, and exposes
health-check and resource-cleanup interfaces.

Usage:
    >>> pipeline = TextToSQLPipeline(
    ...     intent_classifier=IntentClassifier(),
    ...     query_planner=QueryPlanner(),
    ...     schema_retriever=SchemaRetriever(),
    ...     ...
    ... )
    >>> state = AgentState(query="berapa total customer?", database="financial_db")
    >>> state = pipeline.run(state)
    >>> print(state.insights)
"""

from typing import Any

from src.components.insight_generator import InsightGenerator
from src.components.intent_classifier import IntentClassifier
from src.components.query_executor import QueryExecutor
from src.components.query_planner import QueryPlanner
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.schema_retriever import SchemaRetriever
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.core.base_agent import BaseAgent
from src.models.agent_state import AgentState, StepResult
from src.utils.exceptions import QueryExecutionError

# Maximum retries for SQL generation when PostgreSQL returns an execution error
_SQL_RETRY_LIMIT = 2


class TextToSQLPipeline:
    """
    Orchestrates the 8-agent Text-to-SQL pipeline.

    Pipeline sequence:
        IntentClassifier → QueryPlanner → SchemaRetriever → RetrievalEvaluator
        → SQLGenerator → SQLValidator → QueryExecutor → InsightGenerator

    Early stop: pipeline returns after IntentClassifier if the query
    needs clarification (state.needs_clarification is True).

    Multi-step: QueryPlanner may split the query into sequential sub-queries,
    each of which runs the full SQL sub-pipeline before InsightGenerator
    synthesises all results.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        query_planner: QueryPlanner,
        schema_retriever: SchemaRetriever,
        retrieval_evaluator: RetrievalEvaluator,
        sql_generator: SQLGenerator,
        sql_validator: SQLValidator,
        query_executor: QueryExecutor,
        insight_generator: InsightGenerator,
    ) -> None:
        self.intent_classifier   = intent_classifier
        self.query_planner       = query_planner
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
            self.query_planner,
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
        # 1. Classify intent (early exit if ambiguous)
        state = self.intent_classifier.run(state)
        if state.needs_clarification:
            return state

        # 2. Plan
        state = self.query_planner.run(state)

        if state.is_multi_step:
            state = self._run_multi_step(state)
        else:
            # Single step — use sub_query from plan (may be same as original)
            state.query = state.execution_plan[0].sub_query
            state = self._run_sql_pipeline(state)

        # 3. Synthesise insights
        state = self.insight_generator.run(state)
        return state

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _run_sql_pipeline(self, state: AgentState) -> AgentState:
        """SchemaRetriever → RetrievalEvaluator → SQLGenerator → SQLValidator → QueryExecutor.

        If QueryExecutor raises a QueryExecutionError (e.g. wrong column name),
        the error is fed back to SQLGenerator for up to _SQL_RETRY_LIMIT retries.
        """
        state = self.schema_retriever.run(state)
        state = self.retrieval_evaluator.run(state)

        state.sql_error = None
        for attempt in range(1, _SQL_RETRY_LIMIT + 2):  # attempts: 1, 2, 3 (limit+1)
            state = self.sql_generator.run(state)
            state = self.sql_validator.run(state)
            try:
                state = self.query_executor.run(state)
                state.sql_error = None
                return state
            except QueryExecutionError as exc:
                if attempt <= _SQL_RETRY_LIMIT:
                    error_msg = str(exc)
                    state.sql_error = error_msg
                    state.sql = None
                    state.validated_sql = None
                    self.sql_generator.log(
                        f"Execution error on attempt {attempt}, retrying with error context: {error_msg[:120]}",
                        level="warning",
                    )
                else:
                    raise
        return state  # unreachable, satisfies mypy

    def _run_multi_step(self, state: AgentState) -> AgentState:
        """Execute each step sequentially, accumulating StepResults.

        If a step fails, it is recorded with empty data and execution continues
        so InsightGenerator can still synthesise partial results.
        """
        original_query = state.query

        for step in state.execution_plan:
            state.query = step.sub_query
            state.sql = None
            state.validated_sql = None
            state.query_result = None
            state.row_count = 0
            state.retrieved_tables = []
            state.evaluated_tables = []

            try:
                state = self._run_sql_pipeline(state)
                step_result = StepResult(
                    step_number=step.step_number,
                    description=step.description,
                    sql=state.validated_sql or "",
                    data=state.query_result or [],
                    row_count=state.row_count,
                    summary=f"Step {step.step_number} ({step.description}): {state.row_count} rows",
                )
            except Exception as exc:
                step_result = StepResult(
                    step_number=step.step_number,
                    description=step.description,
                    sql="",
                    data=[],
                    row_count=0,
                    summary=f"Step {step.step_number} failed: {exc}",
                )
                state.add_error(f"Step {step.step_number} error: {exc}")

            state.step_results.append(step_result)

        state.query = original_query
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
