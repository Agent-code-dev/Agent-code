# Changelog

All notable changes to `agent-code` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
