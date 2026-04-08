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

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable


class RetrievalEvaluator(LLMBaseAgent):
    """
    Filter retrieved tables to only relevant ones using Claude.

    Categorizes each table as:
    - ESSENTIAL: Must have to answer the query
    - OPTIONAL: Provides additional context
    - EXCLUDED: Not relevant, should be removed
    """

    def __init__(self) -> None:
        super().__init__(name="retrieval_evaluator", version="1.0.0")

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
        """Build evaluation prompt."""
        tables_info = ""
        for i, table in enumerate(tables, 1):
            tables_info += f"\nTable {i}: {table.full_name}\n"
            tables_info += f"Description: {table.description}\n"
            tables_info += f"Columns: {', '.join(table.columns[:10])}"
            if len(table.columns) > 10:
                tables_info += f"... (+{len(table.columns) - 10} more)"
            tables_info += f"\nSimilarity Score: {table.similarity_score:.3f}\n"
            if table.relationships:
                tables_info += f"Relationships: {'; '.join(table.relationships[:3])}\n"

        return f"""You are a database schema analyzer. Evaluate which tables are needed to answer the query.

USER QUERY: "{query}"

RETRIEVED TABLES:
{tables_info}

Categorize each table as ESSENTIAL, OPTIONAL, or EXCLUDED.

- ESSENTIAL: Absolutely required to answer the query
- OPTIONAL: Provides additional context but not strictly necessary
- EXCLUDED: Not relevant to this query

Respond in this EXACT format:

ESSENTIAL:
- [db_name.table_name]: [brief reason]

OPTIONAL:
- [db_name.table_name]: [brief reason]

EXCLUDED:
- [db_name.table_name]: [brief reason]

Your response:"""

    def _parse_response(
        self,
        response: str,
        tables: list[RetrievedTable],
    ) -> tuple[list[RetrievedTable], list[RetrievedTable], list[RetrievedTable]]:
        """Parse LLM response into essential, optional, excluded lists."""
        table_map = {table.full_name: table for table in tables}

        essential: list[RetrievedTable] = []
        optional: list[RetrievedTable] = []
        excluded: list[RetrievedTable] = []
        current_category: str | None = None

        for line in response.split("\n"):
            line = line.strip()

            if line.startswith("ESSENTIAL:"):
                current_category = "essential"
            elif line.startswith("OPTIONAL:"):
                current_category = "optional"
            elif line.startswith("EXCLUDED:"):
                current_category = "excluded"
            elif line.startswith("-") and current_category and ":" in line:
                table_part = line.split(":")[0].strip("- ").strip()
                for full_name, table_obj in table_map.items():
                    if table_part in full_name or full_name in table_part:
                        if current_category == "essential":
                            essential.append(table_obj)
                        elif current_category == "optional":
                            optional.append(table_obj)
                        elif current_category == "excluded":
                            excluded.append(table_obj)
                        break

        if not essential and not optional and not excluded:
            self.log("Parse failed, using all tables as essential", level="warning")
            essential = list(tables)

        return essential, optional, excluded
