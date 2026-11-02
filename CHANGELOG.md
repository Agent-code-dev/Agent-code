# Changelog

All notable changes to `agent-code` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
