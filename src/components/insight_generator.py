"""
Component 7: Insight Generator

Generates natural language insights from query results using Claude.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.validated_sql
    - state.query_result
    - state.row_count
    - state.is_multi_step (bool)
    - state.step_results (list[StepResult], for multi-step queries)
    - state.conversation_history (optional)

Writes to state:
    - state.insights (str)

Example:
    >>> generator = InsightGenerator()
    >>> state = AgentState(query="berapa total customer?")
    >>> state.query_result = [{"total": 100}]
    >>> state.row_count = 1
    >>> state = generator.run(state)
    >>> print(state.insights)
    "Terdapat 100 customer yang terdaftar dalam sistem."
"""

import json

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState


class InsightGenerator(LLMBaseAgent):
    """
    Generate natural language insights from SQL query results.

    Produces conversational Indonesian insights that:
    - Directly answer the user's question
    - Format numbers properly (juta/miliar)
    - Highlight key findings
    - Handle empty results gracefully
    """

    def __init__(self) -> None:
        super().__init__(name="insight_generator", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        """
        Generate insights from query results.

        Args:
            state: Pipeline state with query_result and row_count

        Returns:
            Updated state with state.insights
        """
        try:
            prompt = self._build_prompt(state)
            insights = self._call_llm(prompt, max_tokens=1000, temperature=0.3)
            state.insights = insights
            self.log(f"Insights generated ({len(insights)} chars)")

        except Exception as e:
            self.log(f"LLM insight failed, using fallback: {e}", level="warning")
            state.insights = self._fallback(state)

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Branch to multi-step or single-step prompt based on state."""
        if state.is_multi_step and state.step_results:
            return self._build_multi_step_prompt(state)
        return self._build_single_step_prompt(state)

    def _build_single_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt for a single-step query."""
        if state.query_result and state.row_count > 0:
            results_text = json.dumps(state.query_result[:10], indent=2, default=str)
            if state.row_count > 10:
                results_text += f"\n... and {state.row_count - 10} more rows"
        else:
            results_text = "No results returned"

        history_block = self._build_history_block(state.conversation_history)

        return f"""You are a data analyst for Telkomsel's digital payment platform. Generate insights in conversational Indonesian.
{history_block}
USER QUESTION: "{state.query}"

SQL EXECUTED:
{state.validated_sql}

RESULTS ({state.row_count} rows):
{results_text}

CRITICAL — Number formatting rules:

TRANSACTION COUNTS (kolom: total_trx, success_trx, fail_trx, daily_unique_users, unique_users):
  - These are INTEGER COUNTS of transactions or users — NEVER format as Rupiah
  - Under 1,000: "452 transaksi"
  - Under 1 million: "52.000 transaksi"
  - 1M–999M: "52,6 juta transaksi"
  - 1B+: "1,2 miliar transaksi"

REVENUE / MONEY (kolom: total_revenue, net_revenue, platform_fee, net_gap, total_net_revenue, total_platform_fee):
  - These ARE Rupiah amounts — format with Rp prefix
  - Under 1 million: "Rp 500.000"
  - 1M–999M: "Rp 252,3 juta"
  - 1B+: "Rp 1,2 miliar"

PERCENTAGES (kolom: success_rate_pct, avg_success_rate):
  - Format as "92,5%"

RULES:
1. Directly answer the user's question first
2. Look at the column name in the SQL to determine if it's transactions, revenue, or percentage
3. Highlight key findings using "tertinggi", "terendah", "rata-rata"
4. Keep it concise: 2-4 sentences max

If no results (0 rows):
- Explain what data is available
- Suggest alternative queries or time ranges

Your insights in Indonesian:"""

    def _build_multi_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt that synthesises all step results."""
        history_block = self._build_history_block(state.conversation_history)
        steps_block = self._build_steps_block(state.step_results)

        return f"""You are a data analyst for Telkomsel's digital payment platform.
{history_block}
USER ORIGINAL QUESTION: "{state.query}"

ANALYSIS STEPS EXECUTED:

{steps_block}

Synthesize all step results into a coherent analytical answer in Indonesian.
Apply the same number formatting rules (transaction counts vs Rupiah revenue).
Lead with the direct answer to the original question, then supporting evidence from each step.
Max 5-6 sentences.

Your insights in Indonesian:"""

    def _build_steps_block(self, step_results: list) -> str:
        """Format step results for the multi-step prompt."""
        lines = []
        for step in step_results:
            preview = json.dumps(step.data[:10], indent=2, default=str)
            lines.append(f"STEP {step.step_number}: {step.description}")
            lines.append(f"SQL: {step.sql}")
            lines.append(f"Results ({step.row_count} rows):")
            lines.append(preview)
            lines.append("")
        return "\n".join(lines)

    def _build_history_block(self, history: list[dict]) -> str:
        """Return formatted last 2 conversation turns, or empty string."""
        if not history:
            return ""

        recent = history[-2:]
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

    def _fallback(self, state: AgentState) -> str:
        """Fallback insight if LLM call fails."""
        if not state.query_result or state.row_count == 0:
            return f"Query untuk '{state.query}' tidak mengembalikan hasil."

        if state.row_count == 1 and len(state.query_result[0]) == 1:
            key = list(state.query_result[0].keys())[0]
            value = state.query_result[0][key]
            if isinstance(value, (int, float)):
                return f"Hasil: {value:,}"
            return f"Hasil: {value}"

        return f"Query mengembalikan {state.row_count} baris data."
