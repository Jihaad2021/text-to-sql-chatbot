"""
AgentState - Shared state object passed between all agents.

This module defines the AgentState dataclass that serves as the
single source of truth flowing through the entire pipeline.

Example:
    >>> state = AgentState(query="berapa total customer?", database="financial_db")
    >>> state.current_stage = "intent_classifier"
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionStep:
    """One step in a multi-step analytical plan."""

    step_number: int
    description: str   # e.g. "Ambil revenue April per partner"
    sub_query: str     # natural language sub-query for this step
    depends_on: list[int] = field(default_factory=list)


@dataclass
class StepResult:
    """Result of executing one step."""

    step_number: int
    description: str
    sql: str
    data: list[dict]
    row_count: int
    summary: str  # short text summary injected into next-step context


@dataclass
class AgentState:
    """
    Shared state passed between all agents in the pipeline.

    Attributes:
        query: Original user question
        database: Target database name
        intent: Intent classification result
        retrieved_tables: Tables from schema retriever
        evaluated_tables: Filtered tables from retrieval evaluator
        sql: Generated SQL query
        validated_sql: SQL after validation/fix
        query_result: Raw query results from executor
        insights: Natural language insights
        errors: List of errors encountered
        timing: Execution time per agent (ms)
        current_stage: Currently executing agent
        needs_clarification: Whether query needs clarification
        clarification_reason: Why clarification is needed
        created_at: State creation timestamp
        execution_plan: Steps in a multi-step analytical plan
        step_results: Results of executed steps
        is_multi_step: Whether this is a multi-step query
        conversation_history: Prior turns passed in from client
    """

    # Input
    query: str
    database: str = "financial_db"

    # Agent outputs
    intent: Optional[Dict[str, Any]] = None
    retrieved_tables: List[Any] = field(default_factory=list)
    evaluated_tables: List[Any] = field(default_factory=list)
    sql: Optional[str] = None
    validated_sql: Optional[str] = None
    query_result: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    insights: Optional[str] = None
    sql_error: Optional[str] = None  # last DB execution error, fed back to SQLGenerator

    # Query rewriting (set by QueryRewriter before IC/QP)
    original_query: str = ""
    rewrite_notes: Optional[str] = None

    # Multi-step plan
    execution_plan: List[Any] = field(default_factory=list)  # list[ExecutionStep]
    step_results: List[Any] = field(default_factory=list)    # list[StepResult]
    is_multi_step: bool = False

    # Analytics agent tool calling log
    tool_calls: list[dict] = field(default_factory=list)

    # Pre-computed context injected by pipeline at request time
    context_snapshot: str = ""

    # Chart visualization config (built by InsightGenerator)
    chart_config: dict | None = None

    # Conversational memory — passed in from client each request
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)

    # Tracking
    errors: List[str] = field(default_factory=list)
    timing: Dict[str, float] = field(default_factory=dict)
    current_stage: Optional[str] = None
    needs_clarification: bool = False
    clarification_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_error(self, error: str) -> None:
        """Add error to error list."""
        self.errors.append(error)

    def add_timing(self, agent_name: str, elapsed_ms: float) -> None:
        """Record execution time for an agent."""
        self.timing[agent_name] = elapsed_ms

    def has_errors(self) -> bool:
        """Check if any errors have occurred."""
        return len(self.errors) > 0

    def is_complete(self) -> bool:
        """Check if pipeline has completed successfully."""
        return self.insights is not None and not self.has_errors()
