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

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

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
    - Per-database connection pooling
    """

    def __init__(
        self,
        timeout_seconds: int | None = None,
        max_rows: int | None = None,
    ) -> None:
        super().__init__(name="query_executor", version="1.0.0")
        self.timeout_seconds = timeout_seconds or Config.TIMEOUT_SECONDS
        self.max_rows = max_rows or Config.MAX_ROWS
        self.engines: dict[str, Engine] = self._create_engines()

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
        timeout_ms = self.timeout_seconds * 1000

        try:
            with engine.connect() as conn:
                conn.execute(text(f"SET statement_timeout = {timeout_ms}"))
                result = conn.execute(text(state.validated_sql))
                rows = result.fetchmany(self.max_rows)

                columns = list(result.keys())
                data = [dict(zip(columns, row)) for row in rows] if rows else []

                state.query_result = data
                state.row_count = len(data)

                self.log(f"Query returned {state.row_count} rows from {state.database}")
                return state

        except OperationalError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            if "timeout" in error_msg.lower():
                error_msg = f"Query timeout after {self.timeout_seconds}s"
            raise QueryExecutionError(agent_name=self.name, message=error_msg) from e

        except ProgrammingError as e:
            error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
            raise QueryExecutionError(
                agent_name=self.name,
                message=f"SQL error: {error_msg}"
            ) from e

        except SQLAlchemyError as e:
            raise QueryExecutionError(
                agent_name=self.name,
                message=f"Database error: {e}"
            ) from e

    def _create_engines(self) -> dict[str, Engine]:
        """Create pooled SQLAlchemy engines for all configured databases."""
        engines: dict[str, Engine] = {}

        for db_name, db_url in Config.DB_URLS.items():
            if not db_url:
                self.log(f"URL not set for {db_name}, skipping", level="warning")
                continue

            engine = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_size=Config.POOL_SIZE,
                max_overflow=Config.MAX_OVERFLOW,
                pool_timeout=Config.POOL_TIMEOUT,
                pool_recycle=Config.POOL_RECYCLE,
                echo=False,
            )
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                engines[db_name] = engine
                self.log(f"Connected to {db_name}")
            except Exception as e:
                self.log(f"Failed to connect to {db_name}: {e}", level="error")
                engine.dispose()

        if not engines:
            raise QueryExecutionError(
                agent_name="query_executor",
                message="No database connections available"
            )

        return engines

    def check_connectivity(self) -> dict[str, str]:
        """
        Ping each database and return a status dict.

        Returns:
            {"sales_db": "healthy", "products_db": "error: ..."}
        """
        status: dict[str, str] = {}
        for db_name, engine in self.engines.items():
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                status[db_name] = "healthy"
            except Exception as e:
                status[db_name] = f"error: {e}"
        return status

    def close(self) -> None:
        """Dispose all database connection pools."""
        for db_name, engine in self.engines.items():
            try:
                engine.dispose()
                self.log(f"Closed connection pool for {db_name}")
            except Exception as e:
                self.log(f"Error closing {db_name}: {e}", level="error")
