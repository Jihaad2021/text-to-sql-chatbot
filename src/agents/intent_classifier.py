"""
Component 1: Intent Classifier

Classifies user queries into intent categories and detects ambiguous queries.
Results are used by SQL Generator to determine query strategy.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.conversation_history

Writes to state:
    - state.intent (dict: category, confidence, reason, sql_strategy)
    - state.needs_clarification (bool)
    - state.clarification_reason (str, if ambiguous)

Example:
    >>> classifier = IntentClassifier()
    >>> state = AgentState(query="berapa total customer?")
    >>> state = classifier.run(state)
    >>> print(state.intent)
    {
        "category": "aggregation",
        "confidence": 0.95,
        "reason": "Query asks for count/total",
        "sql_strategy": "Use aggregate functions (COUNT/SUM/AVG) with GROUP BY if needed"
    }
"""

from datetime import date

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState

# Valid intent categories
INTENT_CATEGORIES = {
    "simple_select": "Basic SELECT query, no filters or aggregations",
    "filtered_query": "SELECT with WHERE clause filters",
    "aggregation": "Requires COUNT, SUM, AVG, MIN, MAX",
    "multi_table_join": "Requires JOIN across multiple tables",
    "complex_analytics": "Advanced analytics with subqueries, trends, grouping",
    "root_cause_analysis": "Investigative query asking why something happened, root cause of a spike/drop, or multi-dimensional analysis",
    "ambiguous": "Unclear query that needs clarification",
}

# Strategy hint per category (passed to SQL Generator via state.intent)
INTENT_SQL_STRATEGY = {
    "simple_select": "Use basic SELECT with LIMIT 100",
    "filtered_query": "Use SELECT with WHERE clause",
    "aggregation": "Use aggregate functions (COUNT/SUM/AVG) with GROUP BY if needed",
    "multi_table_join": "Use JOIN across relevant tables",
    "complex_analytics": "Use subqueries, CTEs, or window functions if needed",
    "root_cause_analysis": "Adaptive investigation across multiple dimensions (time, product, channel, partner)",
    "ambiguous": "Cannot generate SQL - needs clarification",
}


class IntentClassifier(LLMBaseAgent):
    """
    Classify user query intent using Claude.

    Determines:
    - Query category (simple_select, aggregation, etc.)
    - Whether query needs clarification
    - SQL generation strategy hint for SQL Generator
    """

    def __init__(self) -> None:
        super().__init__(name="intent_classifier", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        """
        Classify intent of user query.

        Args:
            state: Pipeline state with state.query and state.conversation_history

        Returns:
            Updated state with intent classification results
        """
        prompt = self._build_prompt(state)
        response = self._call_llm(prompt, max_tokens=500, temperature=0)
        intent = self._parse_response(response)

        state.intent = intent
        state.needs_clarification = (
            intent["category"] == "ambiguous" or intent["confidence"] < 0.7
        )

        if state.needs_clarification:
            state.clarification_reason = intent["reason"]

        self.log(
            f"Intent: {intent['category']} "
            f"(confidence: {intent['confidence']:.2f}, "
            f"needs_clarification: {state.needs_clarification})"
        )

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Build classification prompt, including recent conversation context if available."""
        categories_text = "\n".join([
            f"{i + 1}. {cat} - {desc}"
            for i, (cat, desc) in enumerate(INTENT_CATEGORIES.items())
        ])

        history_block = self._build_history_block(state.conversation_history)

        today = date.today().strftime("%Y-%m-%d")

        return f"""You are a SQL query intent classifier for a financial payment analytics system (Telkomsel digital payments).

TODAY'S DATE: {today}
Resolve relative time references using this date: "bulan ini" = current month, "minggu ini" = current week, "hari ini" = today.

Classify the user query into ONE of these categories:

{categories_text}
{history_block}
USER QUERY: "{state.query}"

Respond in this EXACT format:
INTENT: [category]
CONFIDENCE: [0.0 to 1.0]
REASON: [brief explanation]

Rules:
- Mark as "ambiguous" ONLY if query is genuinely vague (e.g. "tampilkan data" with no context)
- Queries asking for totals, sums, averages, rankings → "aggregation" (high confidence)
- Queries asking for trends, per-period breakdowns → "complex_analytics"
- Queries with time filters (bulan, tanggal, "bulan ini", "hari ini") → "filtered_query" or "aggregation"
- Queries containing "kenapa", "mengapa", "apa penyebab", "investigasi", "analisis mendalam", "kenapa naik", "kenapa turun", "apa yang menyebabkan" → "root_cause_analysis"
- Consider both Indonesian and English queries
- Do NOT mark as "ambiguous" if the query has a clear analytical intent, even with complex wording
- Use conversation context to resolve follow-up queries (e.g. "sekarang breakdown per channel")

Your response:"""

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

    def _parse_response(self, response: str) -> dict[str, str | float]:
        """Parse LLM response into intent dict."""
        intent_str = "ambiguous"
        confidence = 0.0
        reason = ""

        for line in response.strip().split("\n"):
            line = line.strip()
            if line.startswith("INTENT:"):
                intent_str = line.replace("INTENT:", "").strip().lower()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                except ValueError:
                    confidence = 0.5
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()

        if intent_str not in INTENT_CATEGORIES:
            intent_str = "ambiguous"

        if confidence < 0.5:
            intent_str = "ambiguous"
            reason = reason or f"Low confidence ({confidence:.2f})"

        return {
            "category": intent_str,
            "confidence": confidence,
            "reason": reason,
            "sql_strategy": INTENT_SQL_STRATEGY[intent_str],
        }
