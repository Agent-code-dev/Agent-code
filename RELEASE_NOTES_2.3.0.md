# Agent Code 2.3.0 — Desktop, Skills, and Add-on Store improvements

This update keeps the package version at **2.3.0**.

## Installation choices

- Full desktop: `pip install agent-code` (includes pywebview).
- Lightweight terminal-only: `pip install "agent-code[lite]"` (excludes pywebview).
- Classic CustomTkinter desktop remains included in the full install and selectable alongside the modern WebView UI.

## New capabilities

- Claude Code-compatible instruction-only `SKILL.md` and `skill.md` discovery. These do not need `skill.py` and do not execute Python.
- Add-on ZIP/folder installation, removal, enable/disable, webview UI components and CustomTkinter widget contributions, and add-on actions.
- Add-on Store catalogue, downloads, SHA-256 verification, and admin-token publishing through the Skills Store server.
- Configurable HTTPS Skills / Add-on Store URL in webview, CustomTkinter and Textual settings; curses can browse and install catalogue add-ons.
- Server-side add-on storage and routes, with admin-only publishing/deletion and public catalogue/download endpoints.
- Broader Podman package-manager detection and cross-distribution install guidance.
- Curses TUI Home/End scrolling for both transcript and activity views.

## Safety notes

Application add-ons are Python programs running with the user's account permissions; they are not sandboxed. Review add-on source before enabling it. The server only accepts admin-published add-ons and validates archive paths and size, but it does not execute or AI-review add-on code.

## Validation

- Full test suite: 242 passed, 2 skipped.
- Python compilation passed for package and server sources.
- Wheel build passed.
- `pywebview` platform markers verified: full/default install includes the webview dependency; `[lite]` excludes it.
- A live pywebview GUI launch remains unverified in this environment because pywebview and GTK/WebKit2GTK are not installed and package-network access is unavailable.


## Desktop frontend migration (still 2.3.0)

- Replaced the default PySide6 desktop with a local pywebview application built from HTML, CSS and JavaScript.
- Kept the classic CustomTkinter desktop selectable from both desktop settings and Textual settings.
- The same Python engine, permission policy, Skills, MCP servers, add-ons, Blueprints and execution modes are used by both desktop frontends.
- Added chat, live activity, Markdown rendering with Pygments highlighting, Skills, Add-ons, Add-on Store, MCP and Settings pages to the webview desktop.
- Added declarative web UI components for add-ons while preserving CustomTkinter add-on widgets.
- Linux uses GTK/WebKit2GTK; Windows uses WebView2 and macOS uses WKWebView. No PySide6 dependency remains in the package installation.

- Added Claude `SKILL.md` enable/disable controls across CustomTkinter, Textual and curses, matching the webview desktop.
- Added desktop-interface selection from CustomTkinter, Textual and curses settings as well as webview Settings.


## Agent Code Server addition

Start a password-protected browser workspace from any supported machine with `agent-code server`. The first launch prints a generated password once. Set a username and choose a password interactively with `agent-code server --username myuser --set-password`. The server is available in `agent-code[lite]` and the full installation. See `docs/server-mode.md`; use a trusted LAN/VPN or HTTPS reverse proxy for remote access.

## Simple pip installation and UI reliability follow-up (still 2.3.0)

- Keep the normal installation command simple: `pip install agent-code`. No repository shell installer or separate Agent Code system-dependency command is required.
- Linux WebView still depends on the distribution's GTK/WebKit2GTK runtime packages; those are operating-system libraries, not pip packages.
- Fixed Textual Settings layout handling and pywebview bridge readiness timing.
- The rebuilt WebUI removes nested Settings scroll areas and filters streaming fragments from Activity.


## Complete UI rebuild — 2026-11-14

The WebUI has been rebuilt as a complete multi-page workspace instead of a chat-only shell. It now includes:

- A redesigned chat surface with a task overview, meaningful activity feed, attachments, execution-mode controls, stop/continue, conversation search, export, and clear actions.
- Task plans, saved task history with resume/rerun actions, checkpoint previews, and a persistent project blueprint editor.
- A workspace file browser with safe text previews and protections against path traversal, symbolic links, secrets, binary files, and oversized files.
- Native and Claude-compatible Skills, Add-ons, the extension store, MCP server management, and expanded Settings.
- Saved provider profiles with API keys kept out of profile-list responses.
- The authenticated `agent-code server` serves the same frontend and the same AgentWebAPI as the pywebview desktop.

The Textual terminal interface also now receives agent clarification requests through a proper modal, routes answers back to the worker, fixes Add-ons navigation, and resets its busy state even when a task exits early. The legacy curses UI now handles terminal resize, closed-screen, input-timeout, and Unicode rendering errors without terminating the agent.

### Validation for this UI rebuild

- Full test suite: 267 passed, 2 skipped.
- Python compilation passed.
- JavaScript syntax validation passed with Node's parser.
- Live WebView and Textual terminal rendering could not be exercised in this build container because pywebview, Textual, and a browser runtime are not installed. These still need a launch check on a supported desktop/terminal environment.
