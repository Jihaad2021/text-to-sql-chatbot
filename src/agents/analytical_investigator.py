"""
Component: Analytical Investigator

Decides the next sub-query to run in an adaptive root-cause investigation loop.
Called once per iteration; returns either a next sub-query to execute or signals
that the investigation is complete.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query (original user question)
    - state.investigation_steps (previous iterations)

Writes to state:
    - state.investigation_decision ({"action": "query"|"done", "sub_query": str|None})
"""

import json

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState, InvestigationStep

_MAX_ITERATIONS = 6
_PREV_ROWS_PREVIEW = 5


class AnalyticalInvestigator(LLMBaseAgent):
    """
    Determine the next investigation step for root-cause analysis queries.

    Each call to execute() looks at all previous InvestigationSteps and
    decides whether to issue one more sub-query or declare the investigation done.
    """

    def __init__(self) -> None:
        super().__init__(name="analytical_investigator", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        prompt = self._build_prompt(state)
        response = self._call_llm(prompt, max_tokens=400, temperature=0)
        decision = self._parse_decision(response)

        state.investigation_decision = decision
        self.log(
            f"Decision: {decision.get('action')} — "
            f"{(decision.get('sub_query') or '')[:80]}"
        )
        return state

    def _build_prompt(self, state: AgentState) -> str:
        steps_block = self._format_previous_steps(state.investigation_steps)
        return f"""You are investigating a question about Telkomsel digital payment analytics.

ORIGINAL QUESTION: "{state.query}"

Available investigation dimensions: waktu/tanggal, produk, channel pembayaran, partner (GoPay/OVO/DANA/LinkAja/dll), anomali transaksi.

{steps_block}
Rules:
- Do NOT re-query data that has already been fetched in previous steps.
- Stop (action: "done") when the root cause is identifiable from the data collected so far.
- Prefer drilling into surprising findings from previous steps.
- Cross-tabulating product × partner is a strong signal to distinguish promo vs organic: if all partners rise proportionally → organic; if only 2-3 partners spike while others are flat → promo.
- Maximum {_MAX_ITERATIONS} iterations total; stop before that if the answer is clear.

Return ONLY valid JSON — no markdown, no explanation:
{{"action": "query", "sub_query": "natural language question for next iteration"}}
or
{{"action": "done"}}

Your response:"""

    def _format_previous_steps(self, steps: list[InvestigationStep]) -> str:
        if not steps:
            return "PREVIOUS STEPS: none — this is the first iteration.\n"

        lines = ["PREVIOUS STEPS:"]
        for step in steps:
            preview = json.dumps(step.data[:_PREV_ROWS_PREVIEW], default=str)
            lines.append(
                f"Iteration {step.iteration}: {step.sub_query}\n"
                f"  Rows: {step.row_count} | Preview: {preview}"
            )
        lines.append("")
        return "\n".join(lines)

    def _parse_decision(self, response: str) -> dict:
        """Parse LLM JSON response; fall back to done on any parse failure."""
        cleaned = response.strip()
        # Strip markdown fences if the model ignores the no-markdown instruction
        if cleaned.startswith("```"):
            cleaned = "\n".join(
                line for line in cleaned.splitlines()
                if not line.strip().startswith("```")
            )
        try:
            decision = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            self.log(f"Failed to parse investigator response: {response[:200]}", level="warning")
            return {"action": "done"}

        action = decision.get("action", "done")
        if action not in ("query", "done"):
            return {"action": "done"}

        return {
            "action": action,
            "sub_query": decision.get("sub_query") if action == "query" else None,
        }
