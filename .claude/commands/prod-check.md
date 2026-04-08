Check the file or component specified by the user for production readiness issues, based on the standards in CLAUDE.md.

Review the target file(s) and report issues grouped by severity:

**CRITICAL** — Must fix before production (security holes, missing validation, data exposure)
**IMPORTANT** — Should fix (reliability, observability, correctness)
**MINOR** — Nice to fix (style, type hints, naming)

For each issue, include:
- The exact file path and line number
- A one-line description of the problem
- The fix (show the corrected code snippet, not just a description)

Checklist to verify:
- [ ] No hardcoded URLs, paths, or secrets — all from Config or env vars
- [ ] All public methods have return type hints
- [ ] No `raise Exception(...)` or `raise ValueError(...)` — must use typed exceptions from exceptions.py
- [ ] Agents use `self.log()`, not direct `logger` calls
- [ ] `execute()` reads from state and writes back to state — no side effects to external systems without error handling
- [ ] `try/finally` used wherever resources (DB engines, file handles) are opened
- [ ] No `allow_origins=["*"]` in CORS config
- [ ] No sensitive data logged (API keys, DB URLs, raw PII)
- [ ] No bare `except: pass` or `except Exception: pass` without logging
- [ ] No magic numbers — constants are named and documented

After listing issues, provide a summary: how many per severity, and which to tackle first.

Target: $ARGUMENTS
