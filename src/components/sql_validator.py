"""
Component 5: SQL Validator

Validates and auto-fixes SQL queries using hybrid approach:
- Traditional: syntax, security, table whitelist
- AI: logic correctness (optional)

Type: Hybrid (Traditional + Agentic)
Inherits: LLMBaseAgent

Reads from state:
    - state.sql
    - state.query

Writes to state:
    - state.validated_sql (validated/fixed SQL)

Example:
    >>> validator = SQLValidator()
    >>> state = AgentState(query="berapa total customer?")
    >>> state.sql = "SELECT COUNT(*) FROM customers;"
    >>> state = validator.run(state)
    >>> print(state.validated_sql)
    SELECT COUNT(*) FROM customers;
"""

import re
import sqlparse
from typing import List, Tuple

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState
from src.utils.exceptions import SQLValidationError
from src.core.config import Config


class SQLValidator(LLMBaseAgent):
    """
    Validate and auto-fix SQL queries.

    Validation layers:
    1. Syntax validation (sqlparse)
    2. Security validation (block dangerous keywords)
    3. Table whitelist validation
    4. Logic validation via Claude (optional)
    """

    def __init__(self, enable_ai_validation: bool = None, max_retries: int = 2):
        super().__init__(name="sql_validator", version="1.0.0")
        self.enable_ai_validation = (
            enable_ai_validation
            if enable_ai_validation is not None
            else Config.ENABLE_AI_VALIDATION
        )
        self.max_retries = max_retries
        self.allowed_tables = Config.ALLOWED_TABLES
        self.dangerous_keywords = Config.DANGEROUS_KEYWORDS

        self.log(
            f"AI validation: {'enabled' if self.enable_ai_validation else 'disabled'}, "
            f"max_retries: {max_retries}"
        )

    def execute(self, state: AgentState) -> AgentState:
        """
        Validate and auto-fix SQL.

        Args:
            state: Pipeline state with state.sql

        Returns:
            Updated state with state.validated_sql
        """
        if not state.sql:
            raise SQLValidationError(
                agent_name=self.name,
                message="No SQL to validate"
            )

        current_sql = state.sql
        fixes_applied = []

        for attempt in range(self.max_retries + 1):
            errors, warnings = self._validate(current_sql, state.query)
            
            if not errors:
                state.validated_sql = current_sql
                if fixes_applied:
                    self.log(f"SQL valid after {len(fixes_applied)} fix(es)")
                else:
                    self.log("SQL valid, no fixes needed")
                return state

            if attempt >= self.max_retries:
                raise SQLValidationError(
                    agent_name=self.name,
                    message=f"SQL validation failed after {self.max_retries} retries",
                    details={"errors": errors}
                )

            # Attempt auto-fix
            if self.enable_ai_validation:
                self.log(f"Attempting auto-fix (attempt {attempt + 1}/{self.max_retries})")
                fixed_sql = self._auto_fix(current_sql, errors, state.query)

                if fixed_sql and fixed_sql != current_sql:
                    fixes_applied.append(f"Attempt {attempt + 1}: AI fix applied")
                    current_sql = fixed_sql
                else:
                    raise SQLValidationError(
                        agent_name=self.name,
                        message="Auto-fix failed to produce different SQL",
                        details={"errors": errors}
                    )
            else:
                raise SQLValidationError(
                    agent_name=self.name,
                    message="SQL validation failed, AI auto-fix disabled",
                    details={"errors": errors}
                )

    def _validate(self, sql: str, query: str = "") -> Tuple[List[str], List[str]]:
        """Run all validation layers, return (errors, warnings)."""
        errors = []
        warnings = []

        errors.extend(self._validate_syntax(sql))
        if errors:
            return errors, warnings

        errors.extend(self._validate_security(sql))
        if errors:
            return errors, warnings

        errors.extend(self._validate_tables(sql))
        if errors:
            return errors, warnings

        if self.enable_ai_validation and query:
            ai_errors, ai_warnings = self._validate_logic_ai(sql, query)
            errors.extend(ai_errors)
            warnings.extend(ai_warnings)

        return errors, warnings

    def _validate_syntax(self, sql: str) -> List[str]:
        """Layer 1: Syntax validation using sqlparse."""
        try:
            parsed = sqlparse.parse(sql)
            if not parsed or not str(parsed[0]).strip():
                return ["SYNTAX: Empty or invalid SQL"]
        except Exception as e:
            return [f"SYNTAX: Parse error - {str(e)}"]
        return []

    def _validate_security(self, sql: str) -> List[str]:
        """Layer 2: Security validation."""
        errors = []
        sql_upper = sql.upper()

        for keyword in self.dangerous_keywords:
            # Pakai word boundary agar tidak match nama kolom
            # contoh: customer_created_at tidak match CREATE
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                errors.append(f"SECURITY: Dangerous keyword '{keyword}' not allowed")

        if '--' in sql or '/*' in sql or '*/' in sql:
            errors.append("SECURITY: SQL comments not allowed")

        if ';' in sql.strip().rstrip(';'):
            errors.append("SECURITY: Multiple statements not allowed")

        if not (sql_upper.strip().startswith('SELECT') or sql_upper.strip().startswith('WITH')):
            errors.append("SECURITY: Only SELECT queries are allowed")

        return errors

    def _validate_tables(self, sql: str) -> List[str]:
        """Layer 3: Table whitelist validation."""
        errors = []

        # Extract CTE names to skip them
        cte_names = set(re.findall(
            r'\bWITH\s+(\w+)\s+AS\s*\(',
            sql,
            re.IGNORECASE
        ))

        # Extract all table names from FROM and JOIN clauses
        matches = re.findall(
            r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            sql,
            re.IGNORECASE
        )

        for table_name in matches:
            # Skip SQL keywords
            skip_words = {'select', 'where', 'extract', 'current_date', 'lateral', 'unnest'}
            if table_name.lower() in skip_words:
                continue
            # Skip CTE names
            if table_name.lower() in {c.lower() for c in cte_names}:
                continue
            if len(table_name) > 1 and table_name.lower() not in self.allowed_tables:
                errors.append(f"TABLE: Unknown table '{table_name}'")

        return errors

    def _validate_logic_ai(self, sql: str, query: str) -> Tuple[List[str], List[str]]:
        """Layer 4: AI logic validation using Claude."""
        if 'EXTRACT(' in sql.upper() or 'DATE_TRUNC' in sql.upper():
            return [], []

        prompt = f"""You are a SQL validator. Check if this SQL correctly answers the user's question.

USER QUESTION: "{query}"

SQL:
{sql}

Respond in this EXACT format:
VALID: [YES or NO]
ERRORS: [logic errors, one per line, or "None"]
WARNINGS: [warnings, one per line, or "None"]

Your response:"""

        try:
            response = self._call_llm(prompt, max_tokens=500, temperature=0)
            errors, warnings = [], []
            current_section = None

            for line in response.split('\n'):
                line = line.strip()
                if line.startswith("ERRORS:"):
                    current_section = "errors"
                    content = line.replace("ERRORS:", "").strip()
                    if content and content.lower() != "none":
                        errors.append(f"LOGIC: {content}")
                elif line.startswith("WARNINGS:"):
                    current_section = "warnings"
                    content = line.replace("WARNINGS:", "").strip()
                    if content and content.lower() != "none":
                        warnings.append(f"LOGIC: {content}")
                elif line.startswith(("-", "•")) and current_section:
                    content = line.lstrip("-•").strip()
                    if content and content.lower() != "none":
                        if current_section == "errors":
                            errors.append(f"LOGIC: {content}")
                        else:
                            warnings.append(f"LOGIC: {content}")

            return errors, warnings

        except Exception as e:
            self.log(f"AI validation failed: {str(e)}", level="warning")
            return [], [f"AI validation unavailable: {str(e)}"]

    def _auto_fix(self, sql: str, errors: List[str], query: str) -> str:
        """Auto-fix SQL using Claude."""
        prompt = f"""You are a SQL fixer. Fix the errors in this SQL query.

USER QUESTION: "{query}"

CURRENT SQL (with errors):
{sql}

ERRORS:
{chr(10).join(errors)}

Return ONLY the corrected SQL, no explanation.

Corrected SQL:"""

        try:
            fixed = self._call_llm(prompt, max_tokens=800, temperature=0)
            fixed = re.sub(r'```sql\s*', '', fixed)
            fixed = re.sub(r'```\s*', '', fixed)
            return fixed.strip()
        except Exception as e:
            self.log(f"Auto-fix failed: {str(e)}", level="error")
            return ""