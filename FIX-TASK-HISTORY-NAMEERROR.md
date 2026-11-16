# Task History NameError Fix — Agent Code 2.3.0

## Root cause
`src/agent_code/agent.py` calls `uuid.uuid4()` when creating a new task-history ID and when generating fallback tool-call IDs, but the module did not import `uuid`. The first new desktop task therefore failed during task-history initialization with `NameError`.

## Fix
Added the missing module-level `import uuid` and a regression test that parses the agent module and verifies the import remains present.

## Verification
- `python -m pytest -q`: 290 passed, 2 skipped.
- `python -m compileall -q src tests`: passed.
- `node --check src/agent_code/web_ui/app.js`: passed.

The fix addresses the missing-name error. No live GUI interaction test was performed in this environment.
