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

import copy
from concurrent.futures import ThreadPoolExecutor
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
from src.core.config import Config
from src.core.query_cache import QueryCache, build_snapshot, restore_snapshot
from src.models.agent_state import AgentState, ExecutionStep, StepResult
from src.utils.exceptions import QueryExecutionError

# Maximum retries for SQL generation when PostgreSQL returns an execution error
_SQL_RETRY_LIMIT = 2


class TextToSQLPipeline:
    """
    Orchestrates the 8-agent Text-to-SQL pipeline.

    Pipeline sequence:
        IntentClassifier ┐
                         ├─ (parallel) ─► merge → SchemaRetriever → RetrievalEvaluator
        QueryPlanner     ┘
        → SQLGenerator → SQLValidator → QueryExecutor → InsightGenerator

    Optimisations:
        - IntentClassifier and QueryPlanner run in parallel (both only need state.query)
        - Identical queries are served from an in-memory TTL cache
        - QueryExecutor errors trigger SQLGenerator self-correction (up to 2 retries)

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

        self._cache = QueryCache(ttl_seconds=Config.CACHE_TTL_SECONDS)

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

        Checks the result cache first. On a miss, runs IntentClassifier and
        QueryPlanner in parallel, then proceeds with the SQL sub-pipeline.
        Returns early (after intent classification) if the query is ambiguous.

        Args:
            state: Initial pipeline state with state.query and state.database

        Returns:
            Fully populated AgentState after all steps complete
        """
        # Save original query — state.query may be replaced by sub_query later
        original_query = state.query

        # ── Cache check ──────────────────────────────────────────
        if Config.CACHE_TTL_SECONDS > 0:
            cached = self._cache.get(original_query, state.database)
            if cached:
                self.intent_classifier.log(f"Cache hit for query: {original_query[:60]}")
                return restore_snapshot(state, cached)

        # ── 1 + 2: IntentClassifier ∥ QueryPlanner ───────────────
        state = self._run_initial_agents_parallel(state)

        if state.needs_clarification:
            return state

        # ── 3–7: SQL sub-pipeline + InsightGenerator ─────────────
        if state.is_multi_step:
            state = self._run_multi_step(state)
        else:
            state.query = state.execution_plan[0].sub_query
            state = self._run_sql_pipeline(state)

        state = self.insight_generator.run(state)

        # ── Cache store (keyed by original query, not sub_query) ──
        if Config.CACHE_TTL_SECONDS > 0:
            self._cache.put(original_query, state.database, build_snapshot(state))

        return state

    # ─────────────────────────────────────────────
    # PARALLEL INITIAL AGENTS
    # ─────────────────────────────────────────────

    def _run_initial_agents_parallel(self, state: AgentState) -> AgentState:
        """Run IntentClassifier and QueryPlanner concurrently.

        Both agents only read state.query and state.conversation_history,
        so they can safely run on independent deep-copies. Their results are
        merged back into the shared state before returning.

        If QueryPlanner fails, the pipeline falls back to a single-step plan
        so IntentClassifier's result is never lost.
        """
        ic_state = copy.deepcopy(state)
        qp_state = copy.deepcopy(state)

        with ThreadPoolExecutor(max_workers=2) as executor:
            ic_future = executor.submit(self.intent_classifier.run, ic_state)
            qp_future = executor.submit(self.query_planner.run, qp_state)

            try:
                ic_result = ic_future.result()
            except Exception as exc:
                # Copy error to original state before re-raising so callers can inspect it
                state.add_error(str(exc))
                raise

            try:
                qp_result = qp_future.result()
            except Exception as exc:
                # QP failed — use single-step fallback so IC result is preserved
                self.query_planner.log(
                    f"QueryPlanner failed in parallel run, using single-step fallback: {exc}",
                    level="warning",
                )
                qp_result = qp_state
                qp_result.is_multi_step = False
                qp_result.execution_plan = [
                    ExecutionStep(
                        step_number=1,
                        description="Execute original query",
                        sub_query=state.query,
                        depends_on=[],
                    )
                ]

        # Merge IC results
        state.intent               = ic_result.intent
        state.needs_clarification  = ic_result.needs_clarification
        state.clarification_reason = ic_result.clarification_reason
        state.timing.update(ic_result.timing)
        state.errors.extend(ic_result.errors)

        # Merge QP results (execution plan is used even on clarification path
        # so it's available if the caller inspects it, but pipeline returns early)
        state.is_multi_step   = qp_result.is_multi_step
        state.execution_plan  = qp_result.execution_plan
        state.timing.update(qp_result.timing)
        if qp_result.errors:
            state.errors.extend(qp_result.errors)

        return state

    # ─────────────────────────────────────────────
    # SQL SUB-PIPELINE
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
        return state  # unreachable — satisfies mypy

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
            Dict with keys: databases, retrieval, agents, overall_healthy, cache
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
            "cache": {
                "entries": self._cache.size(),
                "ttl_seconds": Config.CACHE_TTL_SECONDS,
            },
        }

    # ─────────────────────────────────────────────
    # MISC
    # ─────────────────────────────────────────────

    def get_all_tables(self) -> list[str]:
        """Delegate to SchemaRetriever for /databases endpoint."""
        return self.schema_retriever.get_all_tables()

    def close(self) -> None:
        """Dispose all database connection pools."""
        self.query_executor.close()
