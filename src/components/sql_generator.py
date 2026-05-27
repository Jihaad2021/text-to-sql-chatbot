"""
Component 4: SQL Generator

Generates SQL queries from natural language using Claude.
Uses intent category from IntentClassifier as strategy hint.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.evaluated_tables (list[RetrievedTable])
    - state.intent (dict: category, sql_strategy)
    - state.step_results (list[StepResult], optional — for multi-step queries)

Writes to state:
    - state.sql (generated SQL string)

Example:
    >>> generator = SQLGenerator()
    >>> state = AgentState(query="berapa total customer?")
    >>> state.evaluated_tables = [customers_table]
    >>> state.intent = {"category": "aggregation", "sql_strategy": "Use COUNT/SUM"}
    >>> state = generator.run(state)
    >>> print(state.sql)
    SELECT COUNT(*) as total FROM customers;
"""

import json
import re

import yaml

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.exceptions import SQLGenerationError

# Maximum rows per previous step shown in context to avoid prompt overflow
_PREV_STEP_ROW_PREVIEW = 5


class SQLGenerator(LLMBaseAgent):
    """
    Generate SQL from natural language using Claude.

    Uses intent category as strategy hint to improve SQL generation accuracy.
    Supports few-shot examples from YAML config.
    """

    def __init__(self, examples_path: str = Config.EXAMPLES_PATH) -> None:
        super().__init__(name="sql_generator", version="1.0.0")
        self.examples = self._load_examples(examples_path)
        self.log(f"Few-shot examples loaded: {len(self.examples)}")

    def execute(self, state: AgentState) -> AgentState:
        """
        Generate SQL query from user query and evaluated tables.
        Retries up to 3 times if LLM returns non-SQL text.

        Args:
            state: Pipeline state with query, evaluated_tables, and intent

        Returns:
            Updated state with state.sql

        Raises:
            SQLGenerationError: If no evaluated tables or SQL generation fails
        """
        if not state.evaluated_tables:
            raise SQLGenerationError(
                agent_name=self.name,
                message="No evaluated tables available for SQL generation"
            )

        prompt = self._build_prompt(state)
        max_attempts = 3

        for attempt in range(max_attempts):
            sql = self._call_llm(prompt, max_tokens=1000, temperature=0)
            sql = self._clean_sql(sql)

            if sql and re.match(r'^(SELECT|WITH)\s+', sql, re.IGNORECASE):
                state.sql = sql
                self.log(f"SQL generated: {sql[:80]}...")
                return state

            self.log(
                f"Invalid SQL on attempt {attempt + 1}/{max_attempts}, retrying...",
                level="warning"
            )

        raise SQLGenerationError(
            agent_name=self.name,
            message="Failed to generate valid SQL after retries"
        )

    def _build_prompt(self, state: AgentState) -> str:
        """Build SQL generation prompt using intent strategy and table schemas."""
        intent_hint = ""
        if state.intent:
            intent_hint = f"""
QUERY STRATEGY: {state.intent.get('sql_strategy', '')}
QUERY TYPE: {state.intent.get('category', '')}
"""

        schema_context = "AVAILABLE TABLES:\n\n"
        for table in state.evaluated_tables:
            schema_context += f"Table: {table.table_name} (in {table.db_name})\n"
            schema_context += f"Description: {table.description}\n"
            schema_context += f"Columns: {', '.join(table.columns)}\n"
            if table.relationships:
                schema_context += "Relationships:\n"
                for rel in table.relationships:
                    schema_context += f"  - {rel}\n"
            schema_context += "\n"

        examples_context = "EXAMPLE QUERIES:\n\n"
        for i, example in enumerate(self.examples[:7], 1):
            examples_context += f"Example {i}:\n"
            examples_context += f"Question: {example['question']}\n"
            examples_context += f"SQL:\n{example['sql']}\n\n"

        prev_steps_block = self._build_prev_steps_block(state)
        history_block = self._build_history_block(state.conversation_history)
        error_block = self._build_error_block(state.sql_error, state.sql)

        return f"""You are a senior PostgreSQL data engineer working with a Telkomsel financial payment database.

Your task is to convert natural language questions into safe and correct PostgreSQL SQL queries.

DOMAIN NOTES:
- Linkaja has multiple name variants in the DB — always include ALL of them:
  ('linkaja', 'linkaja_wco', 'linkajawco', 'linkaja_app', 'linkaja_basic', 'linkaja_wec')
- tsel_wallet (in financial_internal/product_summary) = telkomsel_wallet (in daily_master/channel_payment)
- Success rate formula: ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)

STRICT RULES:
1. Only generate a single SELECT query.
2. Use ONLY tables listed in AVAILABLE TABLES.
3. Always include LIMIT clause (default LIMIT 100 if not specified).
4. Use explicit JOIN conditions when joining tables.
5. Use table aliases when joining multiple tables.
6. Avoid SELECT * unless explicitly requested.
7. Do NOT prefix table names with database name.

POSTGRESQL TYPE RULES — MANDATORY:
8. ROUND() requires numeric type — ALWAYS cast the expression: ROUND((expr)::numeric, 2)
   WRONG:   ROUND(AVG(col), 2)
   CORRECT: ROUND(AVG(col)::numeric, 2)
   WRONG:   ROUND(SUM(a) / NULLIF(SUM(b), 0) * 100, 2)
   CORRECT: ROUND((SUM(a)::numeric / NULLIF(SUM(b), 0)) * 100, 2)
9. Avoid integer division — cast numerator to numeric before division.
10. Use COUNT(DISTINCT column) when counting unique entities.

SQL STYLE RULES:
11. Use snake_case column names exactly as provided.
12. Prefer CTE (WITH ...) for complex queries.
13. Do not generate INSERT, UPDATE, DELETE, or DROP statements.

{history_block}{intent_hint}
{error_block}
{schema_context}

{examples_context}
{prev_steps_block}
Generate SQL for the following question.

Question:
{state.query}

IMPORTANT: Return ONLY the SQL query. No explanation, no preamble, no markdown.
Start directly with SELECT or WITH.

SQL:
"""

    def _build_error_block(self, sql_error: str | None, failed_sql: str | None) -> str:
        """Return a correction block when a previous SQL attempt failed at execution."""
        if not sql_error:
            return ""
        lines = [
            "\n⚠️  PREVIOUS SQL FAILED — YOU MUST FIX IT:\n",
            f"Error from PostgreSQL: {sql_error}",
        ]
        if failed_sql:
            lines.append(f"Failed SQL:\n{failed_sql}")
        lines.append(
            "\nAnalyse the error carefully — check column names, table names, types, and casts. "
            "Generate a corrected SQL that avoids the same error.\n"
        )
        return "\n".join(lines)

    def _build_history_block(self, history: list[dict]) -> str:
        """Inject last 2 conversation turns so follow-up queries resolve correctly."""
        if not history:
            return ""
        recent = history[-2:]
        lines = ["RECENT CONVERSATION (use to resolve references like 'sekarang', 'yang tadi', 'periode tersebut'):\n"]
        for turn in recent:
            q = turn.get("query", "")
            sql = turn.get("sql_summary", "")
            if q:
                lines.append(f"Previous question: {q}")
            if sql:
                lines.append(f"Previous SQL used: {sql}")
        lines.append("")
        return "\n".join(lines)

    def _build_prev_steps_block(self, state: AgentState) -> str:
        """Return a formatted block of previous step results, or empty string."""
        if not state.step_results:
            return ""

        lines = ["PREVIOUS STEP RESULTS:\n"]
        for step in state.step_results:
            preview = step.data[:_PREV_STEP_ROW_PREVIEW]
            rows_json = json.dumps(preview, indent=2, default=str)
            lines.append(f"Step {step.step_number} ({step.description}):")
            lines.append(f"SQL: {step.sql}")
            lines.append(f"Results ({step.row_count} rows): {rows_json}\n")

        lines.append("Use these results to inform your SQL for the current step.\n")
        return "\n".join(lines)

    def _clean_sql(self, sql: str) -> str:
        """Remove markdown and extract only SQL from response."""
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*', '', sql)

        match = re.search(r'(WITH\s+|SELECT\s+)', sql, re.IGNORECASE)
        if match:
            sql = sql[match.start():]

        return sql.strip()

    def _load_examples(self, path: str) -> list[dict]:
        """Load few-shot examples from YAML."""
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
                return config.get('examples', [])
        except FileNotFoundError:
            self.log(f"Examples file not found: {path}, using defaults", level="warning")
            return self._default_examples()

    def _default_examples(self) -> list[dict]:
        return [
            {
                'question': 'Show all customers',
                'sql': 'SELECT * FROM customers LIMIT 100;'
            },
            {
                'question': 'How many orders were placed?',
                'sql': 'SELECT COUNT(*) as total_orders FROM orders;'
            },
            {
                'question': 'Top 5 customers by total spending',
                'sql': (
                    'SELECT c.customer_name, SUM(p.payment_value) as total_spent\n'
                    'FROM customers c\n'
                    'JOIN orders o ON c.customer_id = o.customer_id\n'
                    'JOIN payments p ON o.order_id = p.order_id\n'
                    'GROUP BY c.customer_name\n'
                    'ORDER BY total_spent DESC\n'
                    'LIMIT 5;'
                )
            },
        ]
