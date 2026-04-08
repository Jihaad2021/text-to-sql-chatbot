# CLAUDE.md — Text-to-SQL Chatbot

## Project Overview

AI-powered chatbot that converts natural language (Indonesian/English) into SQL queries executed against PostgreSQL. Uses a **7-agent pipeline** with Claude Sonnet, ChromaDB (semantic search), BM25 (keyword search), and graph-based retrieval.

**Stack:** Python 3.11+ · FastAPI · Streamlit · PostgreSQL · ChromaDB · Anthropic SDK · Pydantic v2 · SQLAlchemy 2.0

---

## Architecture

### Pipeline Flow
```
Query → IntentClassifier → SchemaRetriever → RetrievalEvaluator
      → SQLGenerator → SQLValidator → QueryExecutor → InsightGenerator
```

### Key Contracts
- **`AgentState`** (`src/models/agent_state.py`) — shared mutable state passed between all agents. Never create a new state mid-pipeline.
- **`BaseAgent`** (`src/core/base_agent.py`) — abstract base for non-LLM agents. Provides `run()` (metrics + error wrapping) and `log()`.
- **`LLMBaseAgent`** (`src/core/llm_base_agent.py`) — extends `BaseAgent` for agents that call an LLM.
- Each agent implements `execute(state: AgentState) -> AgentState`. Call `run()` externally, never `execute()` directly.
- **`Config`** (`src/core/config.py`) — single source of truth for all constants and env-derived values.

---

## Coding Standards

### Python Style
- **Python 3.11+** — use modern syntax (`match`, `tomllib`, `ExceptionGroup` where appropriate).
- **Type hints on every function** — including return types. No `Any` unless genuinely unavoidable.
- **Pydantic v2** for all API request/response models and any data contract that crosses a boundary.
- Use `|` union syntax (`str | None`) instead of `Optional[str]` for new code.
- Keep functions under 40 lines. Extract helpers if a function grows beyond that.

### Configuration
- **All config values come from `Config` class or env vars.** Never hardcode paths, URLs, timeouts, or magic numbers in component files.
- Constants that are not user-configurable belong at the top of the file as `UPPER_SNAKE_CASE` with a comment explaining the value.
- The `Config` class is the only place that reads `os.getenv()`.

### Agent Pattern
Every agent must follow this pattern exactly:

```python
class MyAgent(BaseAgent):  # or LLMBaseAgent for LLM agents
    def __init__(self):
        super().__init__(name="my_agent", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        # Read from state
        # Write results back to state
        # Return state
        return state
```

- Use `self.log(message)` for info, `self.log(message, level="warning")` for warnings — never call `logger` directly inside agent classes.
- Always raise a typed exception from `src/utils/exceptions.py`. Never `raise Exception("...")` or `raise ValueError("...")` from an agent.
- Document what the agent reads and writes at the top of the module in the docstring format:
  ```
  Reads from state:
      - state.query
  Writes to state:
      - state.retrieved_tables
  ```

### Error Handling
- Use domain-specific exceptions (`SchemaRetrievalError`, `SQLGenerationError`, etc.).
- Never silence exceptions with bare `except: pass`. At minimum log before re-raising.
- `try/except` in `_init_*` methods may return `None` gracefully (component degrades). In `execute()`, failures must raise.

### Imports
- Standard library → third-party → internal (`src.*`). Blank line between groups.
- No wildcard imports (`from x import *`).
- No unused imports.

### Logging
- Use structured logging in production — log dicts, not interpolated strings, when attaching context.
- Log at the right level: `debug` for trace data, `info` for pipeline milestones, `warning` for degraded-but-recoverable, `error` for failures.

---

## Production Requirements

When making any change for production readiness, enforce these:

### Startup Validation
- All required env vars (`OPENAI_API_KEY`, `*_DB_URL`, etc.) must be validated at application startup before any agent is initialized. Fail fast with a clear message.

### Security
- Never use `allow_origins=["*"]` in production CORS. Origins must come from env var `ALLOWED_ORIGINS`.
- All SQL must pass through `SQLValidator` before execution — never bypass it.
- Never expose internal exception details (stack traces, DB URLs) in API responses.

### Performance
- Add rate limiting on the `/query` endpoint.
- DB connections must use connection pooling (SQLAlchemy pool settings in Config).
- Engine disposal in `QueryExecutor` must use `try/finally`.

### Observability
- Every request to `/query` must emit a structured log with: `request_id`, `database`, `intent`, `execution_time_ms`, `success`.
- `/health` must check actual DB connectivity and ChromaDB availability, not just return `"healthy"`.

---

## Testing

- Unit tests: `tests/unit/test_<component>.py`
- Integration tests: `tests/integration/`
- Mock all LLM calls with `patch.object(agent, '_call_llm')` — never hit real APIs in tests.
- Mock DB connections — never require a running PostgreSQL for unit tests.
- Every new agent or function must have a corresponding test.
- Run: `pytest` or `python scripts/run_tests.py`

---

## What NOT to Do

- Do not call `agent.execute(state)` directly — always use `agent.run(state)`.
- Do not add config values directly to agent `__init__` params that should come from `Config`.
- Do not return raw error strings in `QueryResponse` fields meant for data.
- Do not log sensitive data (DB URLs, API keys, raw query results with PII).
- Do not add features beyond what was asked. Fix the thing being fixed.
- Do not create new exception classes — use existing ones in `exceptions.py`.
