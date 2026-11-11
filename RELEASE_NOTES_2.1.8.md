# Agent Code 2.1.8 — Ultra Unrestricted Mode

## Added

- Added **Ultra Unrestricted Agent Code** to Desktop Settings → Permissions and Textual TUI → Settings → Execution.
- The setting is OFF by default and requires a separate warning confirmation when enabled.
- While active, Agent Code automatically approves its available tools, allows direct file-tool paths outside the workspace, and runs shell/background commands on the host with working directories outside the workspace.
- The mode is persisted in `agent_config.json`; disabling it restores the selected normal permission profile.
- The existing unrestricted host-shell option remains available with per-command approval when Ultra mode is off.

## Boundaries that remain

- Commands and file operations run as the currently logged-in OS account. Agent Code does not bypass Linux permissions, sudo authentication, Windows UAC, or administrator/root boundaries.
- Active blacklist aliases remain checked. Shell blacklist inspection is best-effort, not a sandbox.
- Plan Mode remains read-only.
- Podman shell isolation is intentionally bypassed while Ultra mode is enabled because this mode explicitly targets the host.

## Validation

- `python -m compileall -q src tests` — passed.
- Targeted protocol and permission tests — passed.
- Runnable suite excluding the two GUI-dependent Skill Store modules — 199 passed, 2 skipped.
- The two excluded modules require `customtkinter`, which is not installed in the build environment. GUI runtime behavior was not validated here.
