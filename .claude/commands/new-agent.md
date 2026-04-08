Scaffold a new agent following the project's established pattern.

The user will provide: agent name, type (traditional or LLM), what it reads from AgentState, and what it writes to AgentState.

Generate the file at `src/components/<agent_name>.py` with:

1. **Module docstring** — Description, Type (Traditional/LLM-based), Inherits, Reads from state, Writes to state, and an Example.

2. **Imports** — Standard lib → third-party → internal (`src.*`). Only import what is used.

3. **Class** — Inherits `BaseAgent` for traditional agents or `LLMBaseAgent` for LLM agents.

4. **`__init__`** — Call `super().__init__(name="<agent_name>", version="1.0.0")`. Load config from `Config`, not hardcoded values.

5. **`execute(self, state: AgentState) -> AgentState`** — Read from state fields, do the work, write results back to state, log completion, return state. Raise the appropriate typed exception (from `exceptions.py`) on failure.

6. **Private helper methods** — Each doing one thing. Full return type hints.

Also generate the unit test file at `tests/unit/test_<agent_name>.py` with:
- A pytest fixture creating the agent
- A test for the happy path (mock any LLM or DB calls)
- A test for failure (agent raises the correct typed exception)

Then tell the user:
- What to add to `src/utils/exceptions.py` if a new exception type is needed
- What fields to add to `AgentState` if new state fields are needed
- How to wire the agent into the pipeline in `src/main.py`

Agent spec: $ARGUMENTS
