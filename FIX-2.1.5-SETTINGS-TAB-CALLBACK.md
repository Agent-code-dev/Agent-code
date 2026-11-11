# Agent Code 2.1.5 — Settings tab callback fix

## Fixed

The Settings dialog passed `_on_settings_tab_change(tab_name)` directly to `CTkTabview.configure(command=...)`. CustomTkinter's `CTkTabview` invokes this callback with no positional arguments, causing a `TypeError` every time a tab was selected.

The callback now accepts an optional tab name and reads the active tab using `tabs.get()`, preserving lazy tab construction and the initial API & Models build.

## Validation

- `pytest -q tests/test_gui_settings_lazy.py tests/test_shared_settings_store.py tests/test_task_workspace_gui_contract.py`: 8 passed.
- `python -m compileall -q src tests`: passed.
- Wheel built successfully as `agent_code-2.1.5-py3-none-any.whl`.

Version remains 2.1.5. This is a source-level bug fix; no PyPI publication was performed.
