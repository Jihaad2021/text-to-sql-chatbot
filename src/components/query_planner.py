"""
Component 1b: Query Planner

Decides whether a query should be executed as a single step or broken into
multiple analytical steps. Runs after IntentClassifier and before SchemaRetriever.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.conversation_history

Writes to state:
    - state.execution_plan (list[ExecutionStep])
    - state.is_multi_step (bool)

Example:
    >>> planner = QueryPlanner()
    >>> state = AgentState(query="bandingkan revenue April vs Maret 2026")
    >>> state = planner.run(state)
    >>> print(state.is_multi_step)
    True
"""

import json

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState, ExecutionStep
from src.utils.exceptions import AgentExecutionError

# Maximum steps allowed in a single plan
MAX_STEPS = 4

# Maximum recent conversation turns to include in the prompt
MAX_HISTORY_TURNS = 3


class QueryPlanner(LLMBaseAgent):
    """
    Determine whether a query requires multi-step analytical planning.

    For simple queries, produces a single-step plan wrapping the original query.
    For complex queries (comparisons, root-cause, rank+drill), splits into steps.
    Falls back to single-step on any JSON parse failure.
    """

    def __init__(self) -> None:
        super().__init__(name="query_planner", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        """
        Analyse query and build an execution plan.

        Args:
            state: Pipeline state with state.query and state.conversation_history

        Returns:
            Updated state with state.execution_plan and state.is_multi_step
        """
        prompt = self._build_prompt(state)
        response = self._call_llm(prompt, max_tokens=800, temperature=0)
        plan = self._parse_response(response, state.query)

        state.is_multi_step = plan["is_multi_step"]
        state.execution_plan = [
            ExecutionStep(
                step_number=s["step_number"],
                description=s["description"],
                sub_query=s["sub_query"],
                depends_on=s.get("depends_on", []),
            )
            for s in plan["steps"]
        ]

        self.log(
            f"Plan: {'multi-step' if state.is_multi_step else 'single-step'}, "
            f"{len(state.execution_plan)} step(s)"
        )
        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Build the planning prompt, injecting recent conversation if available."""
        history_block = self._build_history_block(state.conversation_history)

        return f"""You are an analytical query planner for Telkomsel's digital payment platform.
Your job is to decide whether a user query should be answered in one SQL step or split
into multiple sequential steps.

DOMAIN: Telkomsel financial payment analytics — partners (GoPay, OVO, Dana, LinkAja, etc.),
transaction counts, revenue, success rates, time periods (daily/monthly/quarterly).
{history_block}
SPLIT INTO MULTIPLE STEPS when the query involves ANY of:
1. Comparison across time periods (e.g. "April vs Maret", "bulan ini vs bulan lalu")
2. Root-cause / "kenapa" / "mengapa" questions that need context first
3. Rank then drill-down (e.g. "top 3 partner, lalu lihat detail per hari")
4. Two independent metrics that are better answered separately then combined

KEEP AS SINGLE STEP when:
- Simple aggregation over one time period
- Single metric query (e.g. "berapa total transaksi April?")
- Filtered lookup with no comparison

RULES:
- Maximum {MAX_STEPS} steps.
- sub_query MUST be a natural language question — NEVER SQL code. A sub_query like
  "SELECT partner, SUM(total_trx)..." is WRONG. Write it as "total transaksi per partner bulan April 2026".
- sub_query must be in the same language as the original query (Indonesian or English).
- Each sub_query must be self-contained and unambiguous (include time periods explicitly).
- depends_on lists step numbers this step should run after (usually [] for independent steps).
- Return ONLY strict JSON — no markdown, no explanation.

OUTPUT FORMAT:
{{
  "is_multi_step": false,
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "sub_query": "...",
      "depends_on": []
    }}
  ]
}}

USER QUERY: "{state.query}"

JSON:"""

    def _build_history_block(self, history: list[dict]) -> str:
        """Return a formatted recent conversation block, or empty string."""
        if not history:
            return ""

        recent = history[-MAX_HISTORY_TURNS:]
        lines = ["\nRECENT CONVERSATION:"]
        for turn in recent:
            q = turn.get("query", "")
            a = turn.get("insights", "")
            if q:
                lines.append(f"Q: {q}")
            if a:
                lines.append(f"A: {a[:200]}{'...' if len(a) > 200 else ''}")
        lines.append("")
        return "\n".join(lines)

    def _parse_response(self, response: str, original_query: str) -> dict:
        """
        Parse LLM JSON response into a plan dict.

        Falls back to a single-step plan wrapping the original query on any error.
        """
        try:
            # Strip any accidental markdown fences
            clean = response.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            plan = json.loads(clean)
            self._validate_plan(plan)
            return plan
        except Exception as e:
            self.log(
                f"Plan parse failed ({e}), falling back to single-step",
                level="warning",
            )
            return self._single_step_fallback(original_query)

    def _validate_plan(self, plan: dict) -> None:
        """Raise AgentExecutionError if the plan structure is invalid."""
        if "is_multi_step" not in plan or "steps" not in plan:
            raise AgentExecutionError(
                agent_name=self.name,
                message="Plan missing required keys 'is_multi_step' or 'steps'",
            )
        if not isinstance(plan["steps"], list) or len(plan["steps"]) == 0:
            raise AgentExecutionError(
                agent_name=self.name,
                message="Plan 'steps' must be a non-empty list",
            )

    def _single_step_fallback(self, query: str) -> dict:
        """Return a trivial single-step plan for the original query."""
        return {
            "is_multi_step": False,
            "steps": [
                {
                    "step_number": 1,
                    "description": "Execute original query",
                    "sub_query": query,
                    "depends_on": [],
                }
            ],
        }
