"""
Component 6: Query Executor

Executes validated SQL queries safely against PostgreSQL.
Does not use LLM - purely traditional execution.

Type: Traditional (Deterministic)
Inherits: BaseAgent

Reads from state:
    - state.validated_sql
    - state.database

Writes to state:
    - state.query_result (List[Dict])
    - state.row_count (int)

Example:
    >>> executor = QueryExecutor()
    >>> state = AgentState(query="berapa total customer?", database="sales_db")
    >>> state.validated_sql = "SELECT COUNT(*) as total FROM customers;"
    >>> state = executor.run(state)
    >>> print(state.query_result)
    [{"total": 100}]
"""

import time
from typing import Dict, List, Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from dotenv import load_dotenv

from src.core.base_agent import BaseAgent
from src.core.config import Config
from src.models.agent_state import AgentState
from src.utils.exceptions import QueryExecutionError

load_dotenv()


class QueryExecutor(BaseAgent):
    """
    Execute SQL queries safely with timeout and row limits.

    Safety controls:
    - Statement timeout (PostgreSQL)
    - Row limit enforcement
    - Read-only protection (via SQL Validator)
    - Per-database connection management
    """

    def __init__(
        self,
        timeout_seconds: int = None,
        max_rows: int = None
    ):
        super().__init__(name="query_executor", version="1.0.0")
        self.timeout_seconds = timeout_seconds or Config.TIMEOUT_SECONDS
        self.max_rows = max_rows or Config.MAX_ROWS
        self.engines = self._create_engines()

        self.log(
            f"Initialized: timeout={self.timeout_seconds}s, "
            f"max_rows={self.max_rows:,}, "
            f"databases={list(self.engines.keys())}"
        )

    def execute(self, state: AgentState) -> AgentState:
        """
        Execute validated SQL query.

        Args:
            state: Pipeline state with state.validated_sql and state.database

        Returns:
            Updated state with state.query_result and state.row_count
        """
        if not state.validated_sql:
            raise QueryExecutionError(
                agent_name=self.name,
                message="No validated SQL to execute"
            )

        if state.database not in self.engines:
            raise QueryExecutionError(
                agent_name=self.name,
                message=f"Database '{state.database}' not available",
                details={"available": list(self.engines.keys())}
            )

        engine = self.engines[state.database]

        try:
            with engine.connect() as conn:
                # Set timeout (PostgreSQL specific)
                timeout_ms = self.timeout_seconds * 1000
                conn.execute(text(f"SET statement_timeout = {timeout_ms}"))

                # Execute query
                result = conn.execute(text(state.validated_sql))
                rows = result.fetchmany(self.max_rows)

                # Convert to list of dicts
                if rows:
                    columns = result.keys()
                    data = [dict(zip(columns, row)) for row in rows]
                else:
                    data = []

                state.query_result = data
                state.row_count = len(data)

                self.log(f"Query returned {state.row_count} rows")

                return state

        except OperationalError as e:
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            if 'timeout' in error_msg.lower():
                error_msg = f"Query timeout after {self.timeout_seconds}s"
            raise QueryExecutionError(
                agent_name=self.name,
                message=error_msg
            ) from e

        except ProgrammingError as e:
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            raise QueryExecutionError(
                agent_name=self.name,
                message=f"SQL error: {error_msg}"
            ) from e

        except SQLAlchemyError as e:
            raise QueryExecutionError(
                agent_name=self.name,
                message=f"Database error: {str(e)}"
            ) from e

    def _create_engines(self) -> Dict[str, Any]:
        """Create SQLAlchemy engines for all configured databases."""
        engines = {}

        for db_name, db_url in Config.DB_URLS.items():
            if not db_url:
                self.log(f"URL not found for {db_name}, skipping", level="warning")
                continue

            try:
                engine = create_engine(db_url, pool_pre_ping=True, echo=False)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                engines[db_name] = engine
                self.log(f"Connected to {db_name}")

            except Exception as e:
                self.log(f"Failed to connect to {db_name}: {str(e)}", level="error")

        if not engines:
            raise QueryExecutionError(
                agent_name="query_executor",
                message="No database connections available"
            )

        return engines

    def close(self) -> None:
        """Close all database connections."""
        for db_name, engine in self.engines.items():
            try:
                engine.dispose()
                self.log(f"Closed connection to {db_name}")
            except Exception as e:
                self.log(f"Error closing {db_name}: {str(e)}", level="error")
