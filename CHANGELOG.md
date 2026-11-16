## 2.3.0 — Podman host URL guidance

- Updated the full and Core system prompts to teach the agent the correct host-to-container URL mapping: `http://localhost:<port>` on the host becomes `http://host.containers.internal:<port>` inside Podman.
- Clarified the reverse direction: container services must bind to `0.0.0.0` and publish a port before the host/browser can reach them through host localhost.
- Added regression tests for the prompt guidance.


## 2.3.0 — Complete workspace UI rebuild and terminal reliability

### Full UI/runtime audit follow-up (2026-11-15)
- Re-audited the delivered 2.3.0 source archive across the WebUI/pywebview desktop, CustomTkinter desktop, Textual TUI, and curses legacy TUI entry points.
- Confirmed the supplied `style.css` is already byte-for-byte identical to `src/agent_code/web_ui/style.css`; retained it without introducing conflicting overrides.
- Added a main-thread SIGINT handler to the CustomTkinter desktop so Ctrl+C schedules orderly Tk shutdown instead of interrupting an active Tk callback. Shutdown stops the agent, cancels pending user prompts, saves the local chat, and closes runtime resources.
- Re-ran the complete test suite and static compilation checks. Browser-based smoke testing was attempted but this environment blocks Chromium navigation (`ERR_BLOCKED_BY_ADMINISTRATOR`), and GTK/pywebview/Podman are unavailable here; those live integrations remain unverified.


- Rebuilt the WebUI from the ground up with a consistent application shell, compact navigation, clear page hierarchy, responsive chat workspace, improved composer, task overview, and a focused activity rail.
- Added dedicated Tasks & Plans, Project Blueprint, Workspace browser, Activity, Skills, Add-ons, Extension Store, MCP, and Settings pages.
- Added workspace file browsing with path-boundary, symlink, secret-file, binary-file, and file-size protections.
- Added project blueprint editing, provider profile save/load/delete, task history resume/rerun, interrupted-task continuation, checkpoint review, chat export/search, and one-click activity/chat clearing.
- Expanded WebUI/server API allow-list for the new authenticated workspace, task, blueprint, and provider-profile operations. The desktop and authenticated server continue to serve the same frontend assets.
- Removed external font dependencies so the local desktop UI renders without internet access. Added keyboard focus visibility, reduced-motion support, and mobile layouts.
- Filtered stream chunks and token deltas from Activity while preserving meaningful task and tool events.
- Fixed Textual TUI's missing AskUserBroker/event queue wiring, added a keyboard-accessible question modal, corrected Add-ons navigation IDs, and guaranteed worker busy-state cleanup on early exits. Rebuilt the legacy curses Settings screen as a keyboard-driven settings center with provider, model, API-key, execution, permission, reasoning, activity, Podman, container, desktop, and store controls; added a dedicated Add-on Store navigation page; forwarded reasoning effort to supported model protocols; and made Ctrl+C shut down workers and pending questions cleanly. Hardened the curses TUI against terminal resize, closed-screen, input-timeout, and Unicode rendering errors.
- Preserved CustomTkinter, Textual, and curses interfaces; version remains 2.3.0 and the simple `pip install agent-code` installation remains unchanged.

# Changelog

All notable changes to `agent-code` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.3.0] - 2026-11-14

### Added
- Added `agent-code server`, an authenticated cross-platform HTTP server that serves the existing web UI and reuses the Agent Code engine for browser access from other machines.
- Added generated one-time web credentials, configurable username/password setup, PBKDF2 password hashing, HttpOnly/SameSite session cookies, 12-hour idle expiry, login rate limiting, and same-origin API checks. Passwords are never written to chat transcripts or logs.
- Added browser-native file and image attachments for remote web sessions, plus server documentation for LAN/VPN use and HTTPS reverse-proxy deployment.
- Added FastAPI and Uvicorn as runtime dependencies so the server is available in both full and `lite` installations.
- Added the full desktop installation with `pip install agent-code` and the lightweight terminal-only extra `pip install "agent-code[lite]"`, which excludes pywebview.
- Added a modern local pywebview desktop with responsive HTML/CSS/JavaScript, chat, live activity, Markdown tables and links, Pygments code highlighting, Skills, Add-ons, Add-on Store, MCP and Settings pages.
- Kept the classic CustomTkinter desktop available through `agent-code[classic-ui]` and made the desktop interface selectable from webview, CustomTkinter and Textual settings.
- Added declarative webview add-on components while preserving CustomTkinter widget contributions; add-on tools, commands and hooks continue to run through the shared engine.
- Added Claude Code-compatible instruction skills from `SKILL.md` / `skill.md` without requiring a Python module. Project, user and Agent Code skill directories are scanned with bounded file sizes.
- Added an Add-on Store client using the configurable HTTPS Skills Store server, including catalogue search, downloads and optional SHA-256 verification. Webview, CustomTkinter, Textual and curses interfaces can browse/install add-ons.
- Added portable package-manager detection for Podman setup across apt, dnf, yum, pacman, zypper, apk, xbps, emerge, Nix, Guix and FreeBSD pkg.
- Improved curses TUI Home/End scrolling and Textual activity/chat scroll preservation.
- Kept the Blueprint store and Max execution mode introduced earlier in 2.3.0.

### Changed
- Expanded the legacy `agent-code tui-legacy` settings center, fixed AskUserBroker initialization order, added compatible Podman container selection, and preserved multiple API keys when adding a new key.
- Replaced the experimental PySide6 desktop with pywebview. Linux uses GTK/WebKit2GTK, Windows uses WebView2 and macOS uses WKWebView. The classic CustomTkinter desktop remains selectable.
- Kept the package version at 2.3.0 as requested.

### Validation
- Full test suite: 251 passed, 2 skipped. Server authentication, password hashing, login/session enforcement, host validation, web asset delivery and API access have dedicated tests.
- Python compilation passed.
- Wheel build passed and includes the local web UI assets.
- The `lite` dependency marker excludes pywebview; the default install includes pywebview without requesting the GTK pip extra. Linux desktop bindings are provided by distro runtime packages.
- Linux installer uses prebuilt native runtime packages and `pip --only-binary=:all:`; no third-party source compilation is requested.
- A live desktop launch was not possible in this environment because pywebview and the native GTK/WebKit2 runtime are not installed. GUI runtime testing is still required on Linux, Windows and macOS.

---

## [2.2.0] - 2026-11-11

### Added
- Project context now honors root `.agentignore` and `.gitignore` patterns, including common directory exclusions and ordered negation rules.
- Hard sensitive-path exclusions remain non-overridable, even when ignore rules attempt to re-include those files.
- Project context reports which ignore files were loaded and how many rules were applied.
- Added conservative test-command discovery for Python, Rust, Go, and Node projects. Node package scripts always require explicit user approval, including under Auto permission mode.
- Added GitHub Actions CI and tag-triggered publishing workflow for GitHub Releases and PyPI Trusted Publishing.
- Added a Codespaces release guide covering tests, build, tag, GitHub release, and PyPI publication.

### Changed
- Bumped package version from 2.1.8 to 2.2.0.

---

## [2.1.8] - 2026-11-11

### Added
- **Ultra Unrestricted Agent Code**: explicit, opt-in permission mode in Desktop Settings and Textual TUI. After a warning confirmation it auto-approves available tools, enables host shell/background commands, and permits host working directories outside the workspace.
- Ultra mode remains constrained by the current OS account's permissions, active blacklist checks, and Plan Mode's read-only boundary; it does not elevate to root/Administrator.
- Added regression tests for opt-in, warning confirmation, execution scope, and permission-gate ordering.

### Changed
- Bumped package version to 2.1.8.

---

## [2.1.4] - 2026-11-07

### Fixed
- Rebuilt desktop Settings tab construction around first-visit lazy loading. MCP manager, SSH controls, Podman controls, and other settings panels are no longer instantiated together when Settings opens.
- Moved Podman status probing off the Tk UI thread and marshalled only the result update back to the UI thread.
- Preserved persisted values for settings tabs that the user has not opened before pressing Save.
- Added regression checks for lazy panel construction, save behavior, and non-blocking Podman status checks.

### Changed
- Bumped package version to 2.1.4.

## [2.1.0] - 2026-11-04

### Added
- **Unified Tool Namespace (UTN):** every active Core, Native Skill, MCP, Add-on, and system tool is registered through one global collision-safe registry. Provider-facing names are automatically prefixed by their source (`core_`, Skill name, MCP server, or Add-on name), while original handlers remain correctly mapped.
- **Skill Execution Environments:** Skills can declare `host`, `sandbox`, `ssh`, or `auto` execution in `SKILL` metadata. Remote-only Skills are inspected without importing their Python module on Host; Sandbox execution uses a read-only mounted Skills directory and SSH execution uses a temporary uploaded package that is cleaned up after the call. Missing targets fail closed without Host fallback.
- **Runtime Coordination:** added progress tracking, planning policy, verification state, lifecycle hooks, and centralized permission classification.
- **Subagent Delegation Enforcement:** explicit user requests to use subagents now require an actual delegated task and result integration. Subagents have bounded concurrency and their own duplicate-call guard.
- **Automatic Verification:** completed Build tasks with tracked file changes run a safe detected validation command before finalizing when validation has not already been performed.
- **Agent Loop Guard:** blocks repeated identical tool calls, detects highly similar repeated searches, and reuses unchanged file-read results using file metadata signatures.

### Fixed
- **TUI Transcript Rendering:** corrected the bottom-anchored viewport calculation that hid the newest lines and final assistant answer. Rendering now wraps and clips by terminal cell width, improving wide-character display and narrow-terminal behavior.
- **Tool Dispatch:** all execution and permission checks now resolve the original tool identity behind its provider-facing namespace, including Plan Mode, Todo tools, and `finish_plan`.
- **Skill Loading Safety:** remote-only Skills with literal metadata and schemas are no longer imported into the Host process during discovery. Mixed Host/remote Skills are rejected and must be split.
- **Skill Server Compatibility:** restored the `extract_python_sources` compatibility alias for bounded archive validation.

### Changed
- Updated Skills and Add-on developer documentation for automatic tool namespacing and execution target declarations.
- Bumped package version to 2.1.0.

## [2.0.0]

### ✨ Added
- **Desktop Workspace (CustomTkinter GUI)**: A completely rebuilt, lightweight desktop interface. Features conversation view, project navigation, Markdown rendering, and live model/provider selection.
- **Terminal UI (TUI)**: Full feature parity for headless servers and SSH sessions. Automatically falls back to TUI when no display is detected.
- **Podman Alpine Sandbox**: A secure execution environment. The agent gets root access *inside* the container (to install packages and run scripts) while keeping the host OS completely safe. Only the workspace folder is mounted.
- **Core Mode (Token Saver)**: A hyper-optimized mode that disables heavy skills and uses a minimal system prompt, restricting the agent to `shell`, `file`, and `curl` tools. Perfect for free APIs or rate limits.
- **Three-Tier Extensibility**: 
  - **Native Skills**: Safe, sandboxed Python folders that add agent tools.
  - **Add-ons**: Powerful Python extensions that modify the app itself (inject CustomTkinter UI, replace services, hook lifecycle events). *Proof of concept: The `agent-code-remote` Telegram Addon.*
  - **MCP (Model Context Protocol)**: Full support for external tool servers via `stdio` and `SSE`.
- **Fault Tolerance & Recovery**: API timeouts and 503 errors are intercepted silently. Errors are kept out of the LLM context to save tokens, and a one-click **"Continue"** button resumes interrupted tasks exactly where they stopped.
- **Checkpoint & Recovery System**: Review file changes, diffs, and recovery hashes before restoring a previous state.

### 🔧 Changed
- **Architecture Overhaul**: Moved from a monolithic structure to a modular app with an integrated Add-on manager and Skills Store.
- **Context Window Optimization**: Dynamic system prompts and compact tool results reduce overall token usage.
- **Security**: API keys are now stored securely using OS Credential Managers (Windows Credential Manager, macOS Keychain, Linux Secret Service).

### 🐛 Fixed
- **Provider Rate Limits**: Bounded retries with exponential backoff to handle flaky free API providers.
- **Force Stop Behavior**: Three-click force stop now reliably interrupts agent communication without closing the browser app.

### ⚠️ Known Limitations
- **Add-on Security**: Add-ons run with full OS permissions and are **not sandboxed**. Users should only install trusted code.
- **Server Licensing**: The `server/` directory (registration backend) is licensed under AGPL-3.0-only, while the core app is MIT.

---

## [1.0.5]
*(Final stable release of the 1.x line)*

### 🐛 Fixed
- Various stability fixes and minor UI rendering issues in the original Tkinter GUI.
- Improved error handling when loading plug-and-play skills from the local directory.

---

## [1.0.4]

### ✨ Added
- Added `/usage` command to track token consumption.
- Added `/env` command to list active environment variables the agent can read.
- Synced documentation with recent UI updates.

---

## [1.0.3]

### 🔧 Changed
- Updated default model configurations for OpenAI-compatible endpoints.
- Improved markdown parsing speed in the chat interface.

---

## [1.0.2]

### 🐛 Fixed
- Resolved an issue where the headless browser (DrissionPage) would occasionally fail to launch on Windows.
- Fixed a bug where the agent could enter an infinite loop if a shell command timed out.

---

## [1.0.1]

### ✨ Added
- Initial PyPI release patches.
- Fixed missing dependencies in the `setup.py` that caused `ModuleNotFoundError` on fresh installs.

---

## [1.0.0]
*(Initial Release)*

### ✨ Added
- **Initial Public Release**: The first version of `agent-code`.
- **Headless Browser**: Real Chromium integration via DrissionPage.
- **Sandboxed Shell**: Allowlisted shell commands restricted to the `workspace/` directory.
- **Plug-and-Play Skills**: Drop-in `skill.py` folders to add new agent tools.
- **Claude Code Workflow**: The agent plans with todos, reads files before editing, and prefers `edit_file` to prevent overwriting.
- **Subagents**: Isolated research tasks with fresh context.
- **Any OpenAI-Compatible API**: Support for OpenAI, Together, Groq, DeepSeek, and local vLLM.

---
> *Note: For a complete list of all commits and historical release assets, please visit the [GitHub Releases](https://github.com/Agent-code-dev/Agent-code/releases) page.*

## [2.0.1] - 2026-11-02

### Fixed
- Increased the model response timeout budget to support long-running generations and large file output without treating normal generation latency as a provider failure.
- Fixed duplicate assistant-message insertion in the desktop agent transcript.
- TUI now streams assistant text live, assembles streamed tool-call fragments before execution, and closes the stream when the user requests stop.
- TUI Activity page now retains and displays a much larger chronological event history, including tool arguments and result details, with independent scrolling.
- TUI reports provider failures with their exception type and removes empty streaming placeholders after failed requests.

### Changed
- Bumped package version to 2.0.1.

## [2.1.1] - 2026-11-05

### Fixed
- Fixed the MCP settings crash caused by an undefined `connected` variable while rendering server actions.
- Fixed TUI prompt input being interrupted by the main curses polling timeout; prompts now temporarily use blocking input and restore the UI timeout afterward.
- Fixed TUI API-key entry and made the TUI use the same OS credential-vault references as the desktop GUI. Failed vault writes are reported instead of silently saving credentials as plaintext.

### Added
- Added Skills management to the TUI: list installed Skills, enable/disable a selected Skill, and install bundled Skills.
- Added an Add-ons manager page to the TUI: list, enable/disable, and create starter Add-ons.
- Added native Skill and Add-on tools to TUI agent requests, preserving their namespaced tool identities.

## [2.1.5] - 2026-11-07
- Unified GUI, Textual TUI, and runtime settings persistence in `settings_store.py`.
- Added atomic, permission-restricted config writes and centralized OS-vault secret handling.

## 2.1.5 — Task Workspace history integration

- Added a bounded per-user task archive so new tasks no longer overwrite the previous task record.
- Added newest-first task discovery, task detail inspection, trajectory display, and safe objective re-run from the Textual TUI Tasks page.
- Persisted desktop GUI task start and terminal status into the same per-user task archive.
- Added tests for multi-task retention, ordering, corrupt history files, ID validation, and pruning.

## 2.1.5 — Desktop Task Workspace
- Added a desktop sidebar entry for Task Workspace.
- Added a GUI task archive browser with task status, timestamps, objective, plan, and trajectory details.
- Added refresh and objective re-run as a new task, preserving archived history.

## 2.1.5 — Task Recovery Checkpoints
- Persist restartable conversation checkpoints after completed tool results.
- Add desktop GUI recovery action alongside objective rerun.
- Omit binary/image payloads from checkpoint snapshots and preserve task history atomically.


## [2.1.6] - 2026-11-11

- Add a local SQLite model-protocol catalog for provider/model capabilities.
- Preserve Qwen `reasoning_content` through streamed tool-call turns.
- Support explicit MiniMax native `<minimax:tool_call>` text blocks as a fallback while retaining structured API `tool_calls` as the default.
- Add bounded parsing, known-tool validation, and incremental transcript filtering for native MiniMax tool markup.
- Add protocol registry and parser regression tests.

## [2.1.7] - 2026-11-11

- Add prompt-injection defense and explicit untrusted-data boundaries across desktop, Sub-Agent, and TUI histories.
- Add alias-configured blacklist files for file access and search visibility.
- Add opt-in unrestricted host shell, disabled by default and guarded by per-command confirmation; Podman remains container-isolated.
- Integrate model protocol capability handling into Sub-Agent and TUI requests, including reasoning metadata and MiniMax native text-call fallback.
- Cache protocol database initialization and add regression coverage for the new security and protocol paths.

## 2.3.0 — Blueprint and Max execution foundations

- Added a versioned, atomic project blueprint store at `.agent-code/blueprint.json` and injects active blueprint context into desktop-agent tasks.
- Added Max execution mode: prioritizes complete, high-quality implementation, useful research, deeper verification, and fixing failures over token minimization. Existing permissions, workspace boundaries, and confirmation requirements remain in force.
- Added Plan / Build / Max selection to the Textual TUI settings and Max mode to the desktop execution selector and legacy terminal mode cycle.
- Fixed Textual log scrolling behavior by disabling forced auto-scroll, preserving the user's viewport, appending activity deltas instead of clearing/rebuilding the log on every poll, and following new output only when already at the bottom.
- Added a new PySide6 desktop frontend and made it the default desktop interface; the classic CustomTkinter desktop remains selectable in Settings.
- Added a Qt-native chat layout with a resizable activity pane, keyboard send shortcuts, task controls, provider/model settings, and Plan / Build / Max selection.
- Added Markdown rendering through markdown-it-py with tables, links, fenced code blocks, and Pygments syntax highlighting in the Qt transcript.
- The first Qt release uses a hidden compatibility host for legacy engine callbacks and dialogs while keeping the visible application in Qt; removing the remaining Tk runtime dependency is a follow-up refactor.
- Added PySide6 and Pygments runtime dependencies. Package version remains 2.3.0.

- Replaced the previous PySide6 desktop with a modern pywebview UI while keeping CustomTkinter selectable; the package no longer installs PySide6.
- Added a shared JS/Python bridge, modern responsive HTML/CSS UI, Markdown-it/Pygments rendering, live activity, Skills, Add-ons, Add-on Store, MCP and Settings pages.
- Added add-on web components and kept CustomTkinter widget contributions; both desktops share the same Python engine and settings.

## 2.3.0 — Simplified installation

- Simplified the standard installation instructions to `pip install agent-code`.
- Removed the repository-specific Linux installation script and the `agent-code install-system-deps` CLI command.
- Kept OS-native GTK/WebKit2GTK runtime requirements documented separately because pip cannot install operating-system libraries.
- Kept the package version at 2.3.0.

### Web UI usability fixes (2.3.0)
- Reworked the desktop web UI to use a fixed viewport layout with a more balanced chat/activity split and improved visual hierarchy.
- Settings now use a compact two-column layout on desktop without a nested vertical scrollbar; small screens retain natural page scrolling.
- Activity view filters streaming token/chunk events so it shows meaningful agent actions only.
- Added Clear activity and Clear chat controls. Clearing activity does not stop a running task.

## 2.3.0 — WebUI parity and compact settings refresh
- Reworked the WebUI settings into fixed-height category panels so Settings no longer adds a page-level vertical scrollbar on desktop.
- Added the CustomTkinter settings missing from WebUI: multiple API keys, provider profiles/model discovery, permission and unrestricted-shell controls, cloud sync, Skills Store server/account, SSH connection configuration and connect/disconnect, Podman sandbox controls, Core Mode, browser executable/engine, and desktop interface selection.
- Added a native Skills Store workspace with sign-in/register, catalogue search, installed/mine/flagged filters, detail inspection, safety warnings, and safe staged skill installation.
- Exposed the new settings, Skills Store, model discovery, Podman, and SSH actions through the authenticated server API allowlist.
- SSH connections reject unknown host keys instead of silently trusting them; SSH passwords are session-only and are not written to configuration.

### 2.3.0 — Selectable Podman execution container
- Added a Podman container picker to Settings → Sandbox, with refresh, select, start, stop, and remove actions.
- Added discovery of existing containers and restricts selectable containers to those mounting the current project read-write at `/workspace`.
- Persisted the selected container in shared Agent Code configuration so WebUI, desktop, and server execution use the same container.
- Routed foreground and background shell commands through the selected container and validate the workspace mount before execution.
- Kept the Agent Code-managed Alpine container as the default and fallback.

### 2.3.0 — UI/runtime reliability follow-up
- Applied the supplied Agent Code dark stylesheet to the shared WebUI used by Desktop and Server.
- Renamed the primary sidebar catalogue destination to **Add-on Store**.
- Added a dedicated Add-on Store page to the Textual terminal UI and made catalogue search/install actions available there.
- Fixed the curses TUI `re` local-variable shadowing that caused `UnboundLocalError` during a normal tool result.
- Made WebView and CustomTkinter Ctrl+C shutdown paths save chat state, cancel pending questions, stop background work, and close browser/MCP resources without printing an uncaught KeyboardInterrupt traceback.
- Added opt-in model-aware thinking effort for OpenAI GPT-5/o-series models and OpenRouter; unknown endpoints do not receive unsupported reasoning parameters.
- Added regression coverage for reasoning request options, task-history access, supplied CSS, and Add-on Store navigation.

## 2.3.0 desktop simplification

- Removed the pywebview desktop launcher and its package dependency. `agent-code` now launches CustomTkinter only.
- Kept the authenticated WebUI, static assets, AgentWebAPI, and `agent-code server` as a separate browser-based server interface.
- Removed desktop frontend switching from CustomTkinter, Textual, curses, and server WebUI settings. Older `desktop_ui=webview` configuration values are ignored; no migration is required.
- Updated installation, server, add-on, and interface documentation to describe the separated desktop and server interfaces.
- Verified: 287 tests passed, 2 skipped; Python compilation passed.

### Textual Settings layout fix

- Compact the settings filter and match summary into a single fixed-height row so the settings category tabs retain the remaining terminal viewport instead of being pushed below the visible area.
- Keep the settings tab content independently sized to fill the available space.
- Added a regression test for the compact settings-search layout.
- Validation: 288 tests passed, 2 skipped; Python compilation passed. Interactive Textual rendering was not run because Textual is not installed in the audit environment.

### Textual TUI visual refresh

- Replaced the saturated blue/cyan/green accent palette with a restrained graphite and slate theme.
- Standardized screen, sidebar, navigation, inputs, buttons, cards, logs, settings, and clarification dialogs around neutral surfaces and quiet borders.
- Muted chat role labels to avoid bright, synthetic-looking accent colors while retaining clear role distinction.
- Kept the existing layout, navigation, settings behavior, and WebUI/server styling unchanged.
- Verification: 289 tests passed, 2 skipped; Python compilation passed.

### 2.3.0 — Product-wide visual refresh
- Replaced the CustomTkinter desktop's purple/neon accent palette with a restrained graphite and slate palette.
- Updated the classic curses TUI to use a monochrome terminal palette instead of cyan/green/yellow highlights.
- Applied a flat, neutral graphite visual layer to the server WebUI, removing rendered gradients, glow effects, and saturated accent styling while preserving layout and behavior.
- Kept the Textual TUI's existing restrained graphite theme consistent with the other interfaces.
- Verified the complete test suite: 289 passed, 2 skipped; Python compilation and WebUI JavaScript syntax checks passed.


### Task history NameError fix
- Fixed a missing `uuid` import in the desktop agent runtime. Starting a desktop task could raise `NameError` while creating its task-history ID; the same missing import could also break generated tool-call IDs.
- Added a regression test that verifies the UUID dependency is available to the agent module.

### Markdown rendering reliability (2.3.0 maintenance)
- Improved the built-in Markdown fallback so pipe tables, bold, italic, strikethrough, inline code, and links remain readable when the optional parser cannot initialize.
- Markdown parser failures now roll back partial output before falling back, instead of appending the raw Markdown source after a partially rendered answer.
- Added regression coverage for fallback table and inline formatting.


## 2.3.0 — Unrestricted shell and selectable Podman environments

- Unrestricted mode now executes complete shell syntax through the user's current OS account shell, including pipelines, redirects, scripts, and compound commands. Existing explicit protected-path/action blacklist checks remain active.
- When Podman is enabled, it takes precedence over host execution even in unrestricted mode; unrestricted shell syntax runs inside the selected container.
- Added managed container OS choices: Alpine Linux, Ubuntu 24.04 LTS, Debian 13, and Fedora. Each choice uses its matching package manager and a workspace-specific container name.
- Added Podman host-gateway aliases and automatic loopback URL translation (`localhost` / `127.0.0.1` to `host.containers.internal`) for container shell commands, so services running on the user's machine can be reached from the container.
- Exposed the container OS selector in CustomTkinter, Textual, and Server WebUI settings.

### Podman sandbox controls
- Added a network-access switch for the Agent Code-managed container. Disabling it creates the container with `--network none`; enabling it uses bridge networking and host-gateway aliases.
- Added configurable memory, CPU, and process-count limits with bounded validation.
- Added read-write/read-only workspace mount selection.
- Exposed the controls in CustomTkinter, Textual TUI, and Server WebUI settings. These options apply when the managed container is created; recreate an existing managed container for changed isolation/resource settings to take effect.
- Custom-selected existing containers retain their own Podman configuration; Agent Code does not silently mutate their network, mounts, or resource limits.

## 2.3.0 — Workspace IDE and final audit

- Added a lightweight Workspace IDE to the authenticated WebUI with file creation, UTF-8 editing, save status, and copy support.
- Added a confined workspace write API: rejects traversal, absolute paths, symlinks, sensitive credential paths, binary/oversized editing, and writes outside the active workspace; saves through an atomic temporary-file replacement.
- Kept the IDE within the existing server WebUI; CustomTkinter remains the only desktop interface.
- Tightened the Podman networking guidance in the agent prompt while preserving the host-gateway URL rule.
- Final validation: 300 tests passed, 2 skipped; Python compileall and WebUI JavaScript syntax checks passed.
