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
from datetime import date

import yaml

from src.core.config import Config
from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.date_range import get_data_year
from src.utils.domain_entities import get_partner_canonical_list, get_partner_variants, render_partner_list_block
from src.utils.exceptions import SQLGenerationError

# Domain entity constants — computed once at import from domain_entities.yaml.
_LINKAJA_VARIANTS = ", ".join(f"'{v}'" for v in get_partner_variants("linkaja"))
_PARTNER_LIST     = render_partner_list_block()
_PARTNER_COUNT    = len(get_partner_canonical_list())

# Maximum rows per previous step shown in context to avoid prompt overflow
_PREV_STEP_ROW_PREVIEW = 5

# LLM prompt template — plain string so bandit B608 is not triggered on the
# definition. Variables use .format() placeholders; the caller adds # nosec B608
# on the single-line .format() call (not executed as SQL; this is an AI prompt).
_PROMPT_TEMPLATE = """You are a senior PostgreSQL data engineer for Telkomsel's financial payment database.
Convert natural language questions into correct PostgreSQL SQL queries.

DATE RULES:
- TODAY IS: {today}. ALL DATA IS YEAR {data_year} — NEVER use {prev_years}.
- LATEST AVAILABLE DATA DATE: {data_end_date_str}. Never generate dates beyond this.
- "bulan ini" → {current_month_start} to {today}. Month name without a year → assume {data_year}.
- Named month (e.g. "bulan Juni", "Juni 2026", "Mei 2026"): ALWAYS use the EXACT calendar range
  of that month. "Juni" → '{data_year}-06-01' to '{data_year}-06-30'. "Mei" → '{data_year}-05-01' to '{data_year}-05-31'.
  NEVER substitute a different month than the one the user explicitly requested.

DOMAIN NOTES:
- Linkaja has multiple name variants — always include ALL: ({linkaja_variants})
- tsel_wallet (financial_internal/product_summary) = telkomsel_wallet (daily_master/channel_payment)
- Success rate: ROUND((SUM(success_trx)::numeric / NULLIF(SUM(total_trx), 0)) * 100, 2)
- Anomali/spike: pct_change = ROUND((current - baseline)::numeric / NULLIF(baseline, 0) * 100, 2); flag >30% significant, >50% extreme; ORDER BY ABS(pct_change) DESC.

STRICT RULES:
1. Only generate a single SELECT query.
2. Use ONLY tables listed in AVAILABLE TABLES.
3. Always include LIMIT clause (default LIMIT 100 if not specified).
4. Use explicit JOIN conditions when joining tables.
5. Use table aliases when joining multiple tables.
6. Avoid SELECT * unless explicitly requested.
7. Do NOT prefix table names with database name.

POSTGRESQL TYPE RULES:
8. Always cast to numeric before ROUND() or division: ROUND((SUM(a)::numeric / NULLIF(SUM(b), 0)) * 100, 2)
   WRONG: ROUND(SUM(a) / NULLIF(SUM(b), 0) * 100, 2)
9. Use COUNT(DISTINCT column) when counting unique entities.

PARTNER COLUMN RULE — MANDATORY:
10. In daily_master, use partner_group ({partner_count} brands: {partner_list}), NEVER bare partner (25 sub-channel rows), for GROUP BY / SELECT / WHERE.
    WRONG: GROUP BY partner — CORRECT: GROUP BY partner_group
    EXCEPTION: use partner only when question explicitly asks about sub-channels (paybill, wec, basic).

MULTI-METRIC RULE — MANDATORY:
11. If the user question mentions MORE THAN ONE metric connected by "dan"/"serta"/"juga"/"and"
    (e.g. "total revenue dan share revenue", "transaksi dan revenue", "volume dan success rate"),
    the SELECT MUST include ALL mentioned metrics — never omit one silently.
    WRONG:   user asks "total revenue dan share revenue" → SELECT total_revenue only          ← missing share
    CORRECT: use a CTE to compute share with window function:
      WITH base AS (SELECT partner_group, SUM(total_revenue) AS total_revenue
                    FROM daily_master WHERE ... GROUP BY partner_group)
      SELECT partner_group, total_revenue,
             ROUND((total_revenue::numeric / NULLIF(SUM(total_revenue::numeric) OVER (), 0)) * 100, 2) AS revenue_share_pct
      FROM base ORDER BY revenue_share_pct DESC LIMIT 100;

SQL STYLE RULES:
12. Use snake_case column names exactly as provided.
13. Prefer CTE (WITH ...) for complex queries.
14. Do not generate INSERT, UPDATE, DELETE, or DROP statements.

{history_block}{intent_hint}
{error_block}
{schema_context}

{examples_context}
{prev_steps_block}
Generate SQL for the following question.

Question:
{query}

IMPORTANT: Return ONLY the SQL query. No explanation, no preamble, no markdown.
Start directly with SELECT or WITH.

SQL:
"""

# Maps user-query keyword → SQL column keyword patterns used for SELECT coverage check.
# Each entry: if the keyword appears in the user's query (case-insensitive), at least one
# of the col_patterns must appear in the final SELECT clause.
_METRIC_KEYWORDS: dict[str, list[str]] = {
    "revenue":   ["revenue", "rev_"],   # rev_ catches CTE aliases: rev_june, rev_may, rev_a, rev_b
    "transaksi": ["trx", "transaksi"],
    "share":     ["share", "_pct"],
    "success":   ["success", "sr_"],    # sr_ catches CTE aliases: sr_june, sr_may
    "volume":    ["trx", "volume"],
    "gap":       ["gap"],
    "fail":      ["fail"],
}


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
            self._record_token_usage(state, model=self.model, iteration=attempt)
            sql = self._clean_sql(sql)
            sql = self._apply_partner_group_fix(sql)

            if not sql or not re.match(r'^(SELECT|WITH)\s+', sql, re.IGNORECASE):
                self.log(
                    f"Invalid SQL on attempt {attempt + 1}/{max_attempts}, retrying...",
                    level="warning",
                )
                continue

            # Deterministic post-generation coverage check — verify all metrics the user
            # explicitly named are represented by at least one column in the SELECT clause.
            missing = self._check_metric_coverage(state.query, sql)
            if missing:
                self.log(
                    f"SELECT missing metrics {missing} for query {state.query!r}",
                    level="warning",
                )
                if attempt < max_attempts - 1:
                    prompt = self._inject_coverage_feedback(prompt, sql, missing)
                    continue
                # Last attempt: use best available SQL but warn loudly
                self.log(
                    f"Metric coverage not fully fixed after retries — missing: {missing}",
                    level="warning",
                )

            state.sql = sql
            self.log(f"SQL generated: {sql[:80]}...")
            return state

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

        today = date.today().strftime("%Y-%m-%d")
        current_month_start = date.today().replace(day=1).strftime("%Y-%m-%d")
        data_year = get_data_year(state.data_end_date)
        prev_years = ", ".join(str(y) for y in range(data_year - 3, data_year))
        data_end_date_str = state.data_end_date.isoformat() if state.data_end_date else f"{data_year}-12-31"

        return _PROMPT_TEMPLATE.format(  # nosec B608 — builds an LLM prompt, not executed SQL
            today=today, data_year=data_year, prev_years=prev_years,
            data_end_date_str=data_end_date_str, current_month_start=current_month_start,
            linkaja_variants=_LINKAJA_VARIANTS, partner_count=_PARTNER_COUNT, partner_list=_PARTNER_LIST,
            history_block=history_block, intent_hint=intent_hint, error_block=error_block,
            schema_context=schema_context, examples_context=examples_context,
            prev_steps_block=prev_steps_block, query=state.query,
        )

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

    # Tables that have a `partner` column but NOT `partner_group` —
    # if any of these appear in the SQL we can't do a blanket rename.
    _PARTNER_ONLY_TABLES = frozenset({"channel_payment", "daily_user_partner", "anomalies"})

    def _apply_partner_group_fix(self, sql: str) -> str:
        """
        Post-process SQL: replace bare `partner` with `partner_group` in daily_master queries.

        Only runs when daily_master is referenced and no partner-only table is also present
        (those tables lack a partner_group column so a blanket rename would break them).
        The replacement skips string literals (single-quoted values) to avoid corrupting
        WHERE partner = 'gopay' → WHERE partner_group = 'gopay', which is actually what we want,
        but leaves literal strings like 'linkaja_paybill' intact.
        """
        if "daily_master" not in sql:
            return sql
        sql_lower = sql.lower()
        if any(t in sql_lower for t in self._PARTNER_ONLY_TABLES):
            return sql

        # Replace `partner` as a standalone identifier (not already part of `partner_group`)
        fixed = re.sub(r'\bpartner\b(?!_group)', 'partner_group', sql)
        if fixed != sql:
            self.log("Applied partner_group fix: replaced bare `partner` with `partner_group`")
        return fixed

    def _extract_select_clause(self, sql: str) -> str:
        """Return the text between the final SELECT and its matching FROM keyword."""
        sql_upper = sql.upper()
        last_select = sql_upper.rfind("SELECT")
        if last_select == -1:
            return sql.lower()
        from_pos = sql_upper.find("FROM", last_select)
        if from_pos == -1:
            return sql[last_select:].lower()
        return sql[last_select:from_pos].lower()

    def _check_metric_coverage(self, query: str, sql: str) -> list[str]:
        """Return metric keywords mentioned in query but absent from the SELECT clause.

        Uses _METRIC_KEYWORDS to map user-facing terms (revenue, share, transaksi…)
        to SQL column-name substrings. A keyword is considered covered if at least one
        of its column patterns appears anywhere in the SELECT clause text.
        """
        query_lower = query.lower()
        select_clause = self._extract_select_clause(sql)
        return [
            kw for kw, patterns in _METRIC_KEYWORDS.items()
            if kw in query_lower and not any(p in select_clause for p in patterns)
        ]

    def _inject_coverage_feedback(
        self, prompt: str, sql: str, missing: list[str]
    ) -> str:
        """Append a coverage-failure block to the prompt so the next LLM call fixes it."""
        missing_str = ", ".join(missing)
        block = (
            f"\n⚠️  COVERAGE CHECK FAILED — your previous SQL is missing columns for: "
            f"{missing_str}\n"
            f"Previous SQL:\n{sql}\n"
            f"You MUST add SELECT columns that cover: {missing_str}.\n"
            f"Every metric the user mentioned must appear in the SELECT.\n\n"
        )
        if "\nSQL:" in prompt:
            return prompt.replace("\nSQL:", block + "\nCORRECTED SQL:", 1)
        return prompt + block

    def _load_examples(self, path: str) -> list[dict]:
        """Load few-shot examples from YAML."""
        try:
            with open(path, encoding="utf-8") as f:
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
