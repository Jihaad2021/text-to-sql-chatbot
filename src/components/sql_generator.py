"""
Component 4: SQL Generator

Generates SQL queries from natural language using Claude.
Uses intent category from IntentClassifier as strategy hint.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.evaluated_tables (List[RetrievedTable])
    - state.intent (dict: category, sql_strategy)

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

import re
import yaml
from typing import List

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.models.retrieved_table import RetrievedTable
from src.utils.exceptions import SQLGenerationError


class SQLGenerator(LLMBaseAgent):
    """
    Generate SQL from natural language using Claude.

    Uses intent category as strategy hint to improve SQL generation accuracy.
    Supports few-shot examples from YAML config.
    """

    def __init__(self, examples_path: str = "config/few_shot_examples.yaml"):
        super().__init__(name="sql_generator", version="1.0.0")
        self.examples = self._load_examples(examples_path)
        self.log(f"Few-shot examples loaded: {len(self.examples)}")

    def execute(self, state: AgentState) -> AgentState:
        """
        Generate SQL query from user query and evaluated tables.

        Args:
            state: Pipeline state with query, evaluated_tables, and intent

        Returns:
            Updated state with state.sql
        """
        if not state.evaluated_tables:
            raise SQLGenerationError(
                agent_name=self.name,
                message="No evaluated tables available for SQL generation"
            )

        prompt = self._build_prompt(state)
        sql = self._call_llm(prompt, max_tokens=1000, temperature=0)
        sql = self._clean_sql(sql)

        if not sql:
            raise SQLGenerationError(
                agent_name=self.name,
                message="Generated SQL is empty"
            )

        state.sql = sql
        self.log(f"SQL generated: {sql[:80]}...")

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Build SQL generation prompt using intent strategy and table schemas."""

        # Intent strategy hint
        intent_hint = ""
        if state.intent:
            intent_hint = f"""
QUERY STRATEGY: {state.intent.get('sql_strategy', '')}
QUERY TYPE: {state.intent.get('category', '')}
"""

        # Table schemas
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

        # Few-shot examples
        examples_context = "EXAMPLE QUERIES:\n\n"
        for i, example in enumerate(self.examples[:7], 1):
            examples_context += f"Example {i}:\n"
            examples_context += f"Question: {example['question']}\n"
            examples_context += f"SQL:\n{example['sql']}\n\n"

        return f"""You are a PostgreSQL SQL expert. Generate accurate, safe SQL queries.

RULES:
1. Use PostgreSQL syntax only
2. Always add LIMIT clause (default: LIMIT 100)
3. Return ONLY the SQL query, no explanation
4. Use proper JOINs when querying multiple tables
5. Handle dates with EXTRACT() or DATE_TRUNC()
6. Use snake_case for all identifiers
{intent_hint}
{schema_context}
{examples_context}
NOW GENERATE SQL FOR:
Question: {state.query}

SQL:"""

    def _clean_sql(self, sql: str) -> str:
        """Remove markdown formatting from SQL."""
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*', '', sql)
        return sql.strip()

    def _load_examples(self, path: str) -> list:
        """Load few-shot examples from YAML."""
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('examples', [])
        except FileNotFoundError:
            self.log(f"Examples file not found: {path}, using defaults", level="warning")
            return self._default_examples()

    def _default_examples(self) -> list:
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
                'sql': '''SELECT c.customer_name, SUM(p.payment_value) as total_spent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN payments p ON o.order_id = p.order_id
GROUP BY c.customer_name
ORDER BY total_spent DESC
LIMIT 5;'''
            }
        ]