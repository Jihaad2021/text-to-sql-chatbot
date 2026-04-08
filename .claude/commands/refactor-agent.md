Refactor the specified agent file to be production-ready, following the standards in CLAUDE.md.

Read the target file first. Then apply these changes, in order:

1. **Config values** — Replace any hardcoded paths, timeouts, or magic numbers with references to `src/core/config.py`. Add the constant to Config if it's missing.

2. **Type hints** — Add missing return type annotations to all methods. Use `str | None` syntax (not `Optional[str]`).

3. **Resource cleanup** — Wrap any DB engine or file handle usage in `try/finally` to ensure disposal.

4. **Logging** — Ensure all logging inside the agent class uses `self.log()`. Replace any direct `logger.xxx()` calls.

5. **Exceptions** — Replace any `raise Exception(...)` or `raise ValueError(...)` with the appropriate typed exception from `src/utils/exceptions.py`.

6. **Structured log on execute** — Ensure the `execute()` method logs a completion message with key state values (query preview, result count, etc.).

7. **Docstring** — Verify the module docstring has the correct "Reads from state" / "Writes to state" sections.

Do NOT:
- Change the business logic or algorithm
- Add new features
- Rename public methods or class names (would break tests)
- Modify the `AgentState` fields being read/written

After making changes, list what was changed and why.

Target agent file: $ARGUMENTS
