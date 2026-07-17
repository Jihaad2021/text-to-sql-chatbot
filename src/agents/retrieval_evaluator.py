"""
Component 3: Retrieval Evaluator

Evaluates and filters retrieved tables to only keep relevant ones.
Reduces false positives from semantic search.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.retrieved_tables (list[RetrievedTable])

Writes to state:
    - state.evaluated_tables (list[RetrievedTable]) - filtered relevant tables

Example:
    >>> evaluator = RetrievalEvaluator()
    >>> state = AgentState(query="berapa total customer?")
    >>> state.retrieved_tables = [customers, orders, products]
    >>> state = evaluator.run(state)
    >>> print(state.evaluated_tables)
    [customers]  # orders and products excluded as not needed
"""

import json
import re

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable

# Valid category values the LLM may return.
_VALID_CATEGORIES = {"ESSENTIAL", "OPTIONAL", "EXCLUDED"}


class RetrievalEvaluator(LLMBaseAgent):
    """
    Filter retrieved tables to only relevant ones using an LLM.

    Categorizes each table as:
    - ESSENTIAL: Must have to answer the query
    - OPTIONAL: Provides additional context
    - EXCLUDED: Not relevant, should be removed

    Output is structured JSON so parsing never depends on free-text line format.
    """

    def __init__(self) -> None:
        super().__init__(name="retrieval_evaluator", version="2.0.0")

    def execute(self, state: AgentState) -> AgentState:
        """
        Evaluate and filter retrieved tables.

        Args:
            state: Pipeline state with state.retrieved_tables

        Returns:
            Updated state with state.evaluated_tables
        """
        retrieved = state.retrieved_tables

        if len(retrieved) <= 2:
            state.evaluated_tables = retrieved
            self.log(f"Skipped evaluation, only {len(retrieved)} tables retrieved")
            return state

        prompt = self._build_prompt(state.query, retrieved)
        response = self._call_llm(prompt, max_tokens=1000, temperature=0)
        self._record_token_usage(state, model=self.model)
        essential, optional, excluded = self._parse_response(response, retrieved)

        all_relevant = essential + optional
        evaluated = [t for t in all_relevant if t.db_name == state.database]

        if not evaluated:
            # LLM was too conservative — fall back to all retrieved tables for this DB
            self.log(
                "Evaluation yielded 0 tables for database — falling back to all retrieved tables",
                level="warning",
            )
            evaluated = [t for t in retrieved if t.db_name == state.database]

        state.evaluated_tables = evaluated

        self.log(
            f"Evaluation complete: {len(essential)} essential, "
            f"{len(optional)} optional, {len(excluded)} excluded"
        )

        return state

    def _build_prompt(self, query: str, tables: list[RetrievedTable]) -> str:
        """Build evaluation prompt that requests structured JSON output."""
        tables_info = []
        for table in tables:
            entry: dict = {
                "name": table.full_name,
                "description": table.description,
                "columns": table.columns,
            }
            if table.relationships:
                entry["relationships"] = table.relationships[:3]
            tables_info.append(entry)

        tables_json = json.dumps(tables_info, indent=2)

        return f"""You are a database schema analyst. Decide which tables are needed to answer the query.

USER QUERY: "{query}"

RETRIEVED TABLES:
{tables_json}

Categories:
- ESSENTIAL: directly required to answer the query
- OPTIONAL: adds useful context but not strictly necessary
- EXCLUDED: not relevant to this query

Respond with ONLY valid JSON — no explanation, no markdown, no text outside the JSON.

{{
  "tables": [
    {{"name": "<db_name.table_name>", "category": "ESSENTIAL|OPTIONAL|EXCLUDED", "reason": "<one sentence>"}},
    ...
  ]
}}"""

    def _parse_response(
        self,
        response: str,
        tables: list[RetrievedTable],
    ) -> tuple[list[RetrievedTable], list[RetrievedTable], list[RetrievedTable]]:
        """
        Parse JSON response into essential, optional, excluded lists.

        Falls back to all-essential if JSON is malformed or missing.
        """
        table_map = {table.full_name: table for table in tables}

        essential: list[RetrievedTable] = []
        optional: list[RetrievedTable] = []
        excluded: list[RetrievedTable] = []

        try:
            # Strip optional markdown fences the model may still emit
            cleaned = re.sub(r"```(?:json)?|```", "", response).strip()
            data = json.loads(cleaned)
            entries = data.get("tables", [])

            for entry in entries:
                name = entry.get("name", "").strip()
                category = entry.get("category", "").upper().strip()

                if category not in _VALID_CATEGORIES:
                    self.log(f"Unknown category '{category}' for '{name}' — skipping", level="warning")
                    continue

                # Match by exact full_name or by table_name suffix
                table_obj = table_map.get(name) or next(
                    (t for t in tables if t.table_name == name or t.full_name == name),
                    None,
                )
                if table_obj is None:
                    self.log(f"Table '{name}' from LLM response not found in retrieved set — skipping", level="warning")
                    continue

                if category == "ESSENTIAL":
                    essential.append(table_obj)
                elif category == "OPTIONAL":
                    optional.append(table_obj)
                else:
                    excluded.append(table_obj)

        except (json.JSONDecodeError, AttributeError, TypeError) as exc:
            self.log(f"JSON parse failed ({exc}) — using all tables as essential", level="warning")
            essential = list(tables)

        if not essential and not optional and not excluded:
            self.log("Empty evaluation result — using all tables as essential", level="warning")
            essential = list(tables)

        return essential, optional, excluded
