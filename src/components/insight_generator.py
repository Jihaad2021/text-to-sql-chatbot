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
from src.utils.exceptions import InsightGenerationError


class InsightGenerator(LLMBaseAgent):
    """
    Generate natural language insights from SQL query results.

    Produces conversational Indonesian insights that:
    - Directly answer the user's question
    - Format numbers properly (juta/miliar)
    - Highlight key findings
    - Handle empty results gracefully
    """

    def __init__(self):
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
            self.log(f"LLM insight failed, using fallback: {str(e)}", level="warning")
            state.insights = self._fallback(state)

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Build insight generation prompt."""
        if state.query_result and state.row_count > 0:
            results_text = json.dumps(state.query_result[:10], indent=2, default=str)
            if state.row_count > 10:
                results_text += f"\n... and {state.row_count - 10} more rows"
        else:
            results_text = "No results returned"

        return f"""You are a data analyst assistant. Generate insights from query results in conversational Indonesian.

USER QUESTION: "{state.query}"

SQL EXECUTED:
{state.validated_sql}

RESULTS ({state.row_count} rows):
{results_text}

Generate insights that:
1. Directly answer the user's question in clear Indonesian
2. Format numbers properly:
   - Under 1 million: "Rp 500.000"
   - 1M to 999M: "Rp 252,3 juta"
   - 1B and above: "Rp 1,2 miliar"
   - Rule: only use "miliar" if value >= 1,000,000,000
3. Highlight key findings using "tertinggi", "terendah", "rata-rata"
4. Keep it concise: 2-4 sentences max

If no results (0 rows):
- Explain what data is available
- Suggest alternative queries or time ranges
- Do NOT just say "tidak ada data"

Your insights in Indonesian:"""

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