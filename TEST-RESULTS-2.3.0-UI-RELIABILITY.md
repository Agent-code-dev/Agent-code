# Agent Code 2.3.0 — Linux installer and UI reliability checks

This update keeps the project version at **2.3.0**.

## Changes

- Full pip installation now installs the Python packages for both desktop frontends, including CustomTkinter.
- Linux no longer asks pip to build `PyGObject==3.50.0` through `pywebview[gtk]`. The package installs plain pywebview; GTK3, WebKitGTK 4.1, PyGObject, Cairo and Tk are native operating-system dependencies.
- Added `scripts/install-linux.sh` for Ubuntu/Debian. It installs native packages first, checks imports with the active system Python, then runs `python3 -m pip install --user -e .`.
- Added `agent-code install-system-deps` for an already-installed package. It lists native packages and asks before running apt; `--yes` skips only the confirmation prompt.
- Fixed Textual Settings scroll viewport sizing and re-applies scroll layout after Settings tab activation.
- Fixed pywebview bridge startup timing so the readiness event is always registered, even if the bridge appears after the UI script loads.
- Added offline feedback after repeated web UI polling failures and reset the failure counter after a successful response.
- Refined the web UI's AI-workspace theme, responsive behavior, cards, composer, focus states and settings controls.

## Validation

- `PYTHONPATH=src pytest -q`: **257 passed, 2 skipped**.
- `node --check src/agent_code/web_ui/app.js`: passed.
- `bash -n scripts/install-linux.sh`: passed.
- `python -m compileall -q src tests`: passed.
- `PYTHONPATH=src python -m agent_code --version`: reports `agent-code 2.3.0`.
- `agent-code install-system-deps --help`: passed.
- Wheel build passed; verified the wheel includes `system_deps.py` and the web UI assets, and does not declare `pywebview[gtk]`.

## Not yet verified

A live GUI session was not launched in this build environment. GTK/WebKit rendering, CustomTkinter window behavior and real terminal mouse-wheel behavior must still be checked on the target Ubuntu desktop. These tests are not represented as passed merely because static tests passed.
