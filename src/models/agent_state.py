"""
AgentState - Shared state object passed between all agents.

This module defines the AgentState dataclass that serves as the
single source of truth flowing through the entire pipeline.

Example:
    >>> state = AgentState(query="berapa total customer?", database="financial_db")
    >>> state.current_stage = "intent_classifier"
"""

from dataclasses import dataclass, field
from datetime import date, datetime
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
class ToolCallResult:
    """Result from a single AnalyticsAgent tool call (detect_anomaly, compare_periods, etc.).

    Stored in state.tool_results (one entry per tool call that returned data).
    Supersedes the flat-concat approach of all_tool_data so each tool's schema
    remains intact and accessible to ResponsePlanner and InsightGenerator.
    """

    tool_name: str          # e.g. "detect_anomaly", "compare_periods"
    data: list[dict]        # rows returned by the tool
    row_count: int
    sql_or_params: str      # SQL executed, or JSON-serialised call args for reference
    description: str        # one-line summary from analytics_tools (e.g. "Compare partner May vs Apr")
    actual_entity_count: int = 0       # total distinct entities in DB for this period (get_distribution only)
    cumulative_trx_share_pct: float = 0.0   # sum of trx_share_pct across all returned rows
    cumulative_rev_share_pct: float = 0.0   # sum of rev_share_pct across all returned rows
    dimension: str = ""                     # e.g. "partner", "product", "channel" (get_distribution only)


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

    # Analytics agent tool calling log (lightweight — tool name + args + row_count only)
    tool_calls: list[dict] = field(default_factory=list)

    # Structured per-tool results from AnalyticsAgent (one entry per tool that returned data).
    # Each entry preserves the tool's own column schema — no flat-concat mixing.
    # state.query_result is kept for backward compat and holds the last tool's data.
    tool_results: list[Any] = field(default_factory=list)  # list[ToolCallResult]

    # Pre-computed context injected by pipeline at request time
    context_snapshot: str = ""

    # MAX(date) from daily_master — injected by pipeline at startup, never None in prod
    data_end_date: date | None = None

    # MIN(date) from daily_master — injected by pipeline at startup alongside data_end_date
    data_start_date: date | None = None

    # COUNT(DISTINCT product_name) from product_summary — injected by pipeline at startup.
    # Used by InsightGenerator to report dynamic product count in prompt exceptions.
    # 0 means "not loaded" (DB unreachable); callers fall back to hardcoded 882.
    product_count: int = 0

    # Set by QueryRewriter when the resolved period starts after data_end_date.
    # InsightGenerator skips LLM and returns a template message when True.
    query_out_of_range: bool = False
    out_of_range_latest: str | None = None  # YYYY-MM-DD of latest available date

    # Set by pipeline when recommendation intent can be answered from conversation history
    recommendation_from_history: bool = False

    # Chart visualization config (built by InsightGenerator)
    chart_config: dict | None = None
    # Multiple chart configs — each may carry anchor_after + purpose from visual_blocks
    chart_configs: list[dict] = field(default_factory=list)

    # Layout plan from ResponsePlanner — guides InsightGenerator structure
    layout_plan: dict | None = None

    # Structured narrative sections parsed from insights string (Option B+C).
    # None when ResponsePlanner produced no section markers or only one section.
    # {"s1": "...", "s2": "...", ...} otherwise.
    # state.insights (full string) is always the authoritative backward-compat field.
    insights_sections: dict[str, str] | None = None

    # Conversational memory — passed in from client each request
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)

    # Set by pipeline when auto drill-down was triggered for a DoD anomaly day
    auto_drilldown_triggered: bool = False

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
