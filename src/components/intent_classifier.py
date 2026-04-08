"""
Component 1: Intent Classifier

Classifies user queries into intent categories and detects ambiguous queries.
Results are used by SQL Generator to determine query strategy.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query

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

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState

# Valid intent categories
INTENT_CATEGORIES = {
    "simple_select": "Basic SELECT query, no filters or aggregations",
    "filtered_query": "SELECT with WHERE clause filters",
    "aggregation": "Requires COUNT, SUM, AVG, MIN, MAX",
    "multi_table_join": "Requires JOIN across multiple tables",
    "complex_analytics": "Advanced analytics with subqueries, trends, grouping",
    "ambiguous": "Unclear query that needs clarification",
}

# Strategy hint per category (passed to SQL Generator via state.intent)
INTENT_SQL_STRATEGY = {
    "simple_select": "Use basic SELECT with LIMIT 100",
    "filtered_query": "Use SELECT with WHERE clause",
    "aggregation": "Use aggregate functions (COUNT/SUM/AVG) with GROUP BY if needed",
    "multi_table_join": "Use JOIN across relevant tables",
    "complex_analytics": "Use subqueries, CTEs, or window functions if needed",
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
            state: Pipeline state with state.query

        Returns:
            Updated state with intent classification results
        """
        prompt = self._build_prompt(state.query)
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

    def _build_prompt(self, query: str) -> str:
        """Build classification prompt."""
        categories_text = "\n".join([
            f"{i + 1}. {cat} - {desc}"
            for i, (cat, desc) in enumerate(INTENT_CATEGORIES.items())
        ])

        return f"""You are a SQL query intent classifier for an e-commerce analytics system.

Classify the user query into ONE of these categories:

{categories_text}

USER QUERY: "{query}"

Respond in this EXACT format:
INTENT: [category]
CONFIDENCE: [0.0 to 1.0]
REASON: [brief explanation]

Rules:
- Mark as "ambiguous" if query is vague or unclear
- Mark as "ambiguous" if confidence < 0.7
- Consider both Indonesian and English queries

Your response:"""

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

        if confidence < 0.7:
            intent_str = "ambiguous"
            reason = reason or f"Low confidence ({confidence:.2f})"

        return {
            "category": intent_str,
            "confidence": confidence,
            "reason": reason,
            "sql_strategy": INTENT_SQL_STRATEGY[intent_str],
        }
