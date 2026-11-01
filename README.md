# Agent + Skill Store


### Headless Linux / Terminal UI

On a PC without a monitor, or over SSH, run `agent-code tui`. It provides a full-screen terminal layout with Chat, Workspace, Skills, MCP configuration, Settings, and Help pages. Model-list requests and agent work run in background threads so provider/network delays do not freeze the UI; the model picker can filter returned IDs. On Linux, `agent-code` automatically opens the TUI when no graphical display (`DISPLAY` / `WAYLAND_DISPLAY`) is available. Use `agent-code gui` to explicitly launch the desktop interface. In the TUI chat, enter `!<command>` to run a terminal command directly; recognized executable commands (for example `ls`, `git`, or `python`) are also dispatched to the workspace shell rather than the AI. `cd <directory>` changes the workspace-confined terminal directory. Use `/clear` or Ctrl+L to clear chat, and `/stop` or F5 to request stopping the current agent task (Ctrl+C stops a running task, or exits when idle).

If Tkinter is missing on a supported Linux desktop, Agent Code offers to install the distro package after asking permission (APT, DNF, Pacman, Zypper, or APK). It does not install system packages without confirmation.

> **Agent Code 2.0 stable line:** includes a CustomTkinter workspace, separate task-plan view, detailed activity panel, browser diagnostics, cooperative stop controls, and the new `agent-code doctor` diagnostic command.

A local AI agent with a headless browser, sandboxed shell, chat GUI, and a
plug-and-play skill system backed by a hosted skill registry.

[![PyPI](https://img.shields.io/pypi/v/agent-code)](https://pypi.org/project/agent-code/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/agent-code/)
[![License](https://img.shields.io/badge/app-MIT-green)](#license) [![Server license](https://img.shields.io/badge/server-AGPL--3.0-blue)](#license)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#platform-support)

**Live site:** https://agent-code-dev.github.io · **Stable install:** `pip install agent-code`

> **Release note:** this repository version is packaged as `2.0.0`. Run `agent-code doctor` after installation to check your local environment, including Firefox and Chromium detection. The GUI and browser still depend on compatible system-installed components.

---


## Full documentation

The complete offline-friendly HTML documentation is in [`docs/`](docs/index.html):

- [User guide](docs/index.html) — installation, first run, modes, permissions, activity details, browser, SSH, sandbox, troubleshooting and security.
- [Skill developer guide](docs/skills.html) — folder structure, `SKILL`, `TOOL_SCHEMAS`, `TOOL_CALLABLES`, optional `COMMANDS`, metadata, testing and packaging.
- [Add-on developer guide](docs/addons.html) — UI contributions, actions, hooks, tools, service replacement, testing and packaging.

Skills and Add-ons are separate systems: Skills add tools for the AI agent; Add-ons extend the Agent Code application. See the guides for the exact extension points supported by this release.

## What this is

One command install. Two GUIs. A hosted skill registry.

| Command | What it opens |
|---|---|
| `agent-code` | Agent Code workspace — chat GUI, headless browser, sandboxed shell, in-app Skills Store |
| `agent-code manage` | The skill store — browse, install, publish skills |
| `agent-code skills list` | List bundled skills |
| `agent-code skills install` | Install bundled skills for the current user |
| `agent-code doctor` | Check dependencies, config validity, workspace access, and browser availability |
| `agent-code doctor --json` | Print machine-readable diagnostics |
| `agent-code doctor --output report.json` | Save a local diagnostics report (API keys are not included) |

Skills are folders under `./skills/`. Install them from the in-app Skills Store or add one manually. Use **Reload Skills** to refresh the tool list without restarting Agent Code. Skill code is Python and should only be installed from sources you trust.

---

## Install

```bash
pip install agent-code
```

That's it. No clone, no config file, no build step.

Then:

```bash
agent-code              # run the agent
agent-code manage       # open the skill store
agent-code skills       # list bundled skills
agent-code skills install   # copy them into ./skills/
```

### First run

The agent needs an API key. On first launch:

1. Click **Settings** in the top-right of the agent window
2. Paste your API key
3. Optionally change the base URL and model
4. Save

Or create `agent_config.json` in the folder where you run the agent:

```json
{
  "openai_api_keys": ["sk-your-key-here"],
  "openai_base_url": "https://api.openai.com/v1",
  "openai_model": "gpt-4o",
  "cloud_sync": false
}
```

The config file wins if both exist. The Settings dialog writes to it.

### Talk to it

```
go to news.ycombinator.com and list the top 5 story titles
find a free API for cat facts and call it
create a snake game in a single HTML file
```

---

## Platform support

Agent Code targets **Python 3.10 or newer** on Windows, Linux, and macOS. Other
operating systems may work if they provide a compatible Python build, Tcl/Tk,
and a Chromium-compatible browser supported by DrissionPage, but are not yet
verified. Python version alone is not sufficient: the GUI and browser also need
their native system dependencies.

| Platform | Expected support | Requirements / caveats |
|---|---|---|
| Windows 10/11 | Supported target | Python 3.10+ with Tcl/Tk; Chromium/Chrome for browser tools |
| macOS | Supported target | Python 3.10+ with Tcl/Tk; Chromium/Chrome for browser tools |
| Linux desktop | Supported target | Python 3.10+; install your distro's Tk package and Chromium/Chrome |
| Other OS / BSD | Best effort, unverified | Must provide compatible Python, Tk, browser and system opener utilities |
| Headless server | CLI only unless a display is configured | GUI requires a desktop/display; browser may need headless dependencies |

### Linux setup

Install Tk and a Chromium-based browser using your distribution's package manager. Examples:

```bash
# Ubuntu / Debian / Kali / Mint / Pop!_OS
sudo apt install python3-tk chromium

# Fedora / RHEL family
sudo dnf install python3-tkinter chromium

# Arch / Manjaro
sudo pacman -S tk chromium
```

If your Python came from a separate environment (such as pyenv), ensure that
build includes Tcl/Tk. If `agent-code` is not found after installation, add
`~/.local/bin` to PATH or run `python -m agent_code --version`.

### Windows and macOS setup

Install Python 3.10+ with Tcl/Tk enabled and install Chromium or Google Chrome
for browser automation. If browser startup fails, check the browser installation
and DrissionPage's supported browser configuration; WebView2 is not a substitute
for the Chromium browser used by DrissionPage.

### Cross-platform SSH and sandbox behavior

The Link to SSH command parser follows the host OS quoting rules so Windows
private-key paths such as `C:\Users\Alice\.ssh\id_ed25519` keep their
backslashes. SSH configuration and keys are resolved from the current user's
home directory on each supported OS.

The app's GUI and local file-opening helpers target Windows 10/11, macOS, and
Linux. The optional Alpine sandbox is a Linux container: Linux needs a working
Podman service; Windows and macOS need Podman Desktop (or another working Podman
machine) initialized and running. The sandbox is optional; without it, shell
commands run on the host and must use that OS's available commands (for example,
PowerShell/CMD commands on Windows and POSIX commands on Linux/macOS).

### Portability note

Optional system integrations (opening a folder in the file manager, browser
startup, and platform-specific icon handling) depend on the desktop environment.
Agent Code falls back to a clear error if no system file opener is available.

---

## Agent Code 2.0 UI updates in this source build

- New navigation sidebar for workspace, installed skills, Add-ons, Skills Store, settings, and help.
- Skills Store opens as a window inside the Agent Code app and targets the same active skills directory.
- Successful skill installation/removal notifies Agent Code and refreshes its tool registry when no agent task is running; if a task is active, the refresh waits until it finishes.
- **Reload Skills** rebuilds skill metadata, commands, tool schemas, and the system prompt without restarting the app.
- API provider settings remain separate from the Skills Store account. The Store login is saved in `~/.skill-manager.json`; provider keys are saved in the Agent Code config file.

The app imports enabled `skill.py` files as Python modules. A skill can execute arbitrary code with the user's permissions, so review skill source before installing or enabling it.

---

## The skill system

A skill is a folder:

```
skills/my_skill/
├── skill.py     ← code
└── skill.md     ← metadata + docs
```

`skill.py` exports three things:

```python
SKILL = {"name": "my_skill", "description": "What this does."}

def greet(name: str = "world") -> str:
    return f"Hello, {name}!"

TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "greet",
        "description": "Return a greeting.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
    },
}]

TOOL_CALLABLES = {"greet": greet}
```

Restart the agent. The LLM can now call `greet()`.

## The add-on system

Add-ons are a separate extension layer for changing or extending **Agent Code itself** —
not a way to train, replace, or improve the selected AI model. They are designed to be
open-ended: add-ons can register agent tools, namespaced slash commands, lifecycle
hooks, and actions shown in the Add-ons page. Future core versions can expose more
extension points without requiring add-ons to become skills.

Open **Add-ons** in the sidebar. The per-user directory is:

- Linux: `~/.local/share/agent-code/addons/`
- Windows: `%LOCALAPPDATA%\AgentCode\addons\`

Each add-on is a folder containing `addon.json` and `addon.py`. Use **Create add-on
template** to generate a starter. Example manifest:

```json
{
  "name": "sample-addon",
  "version": "1.0.0",
  "description": "An example extension",
  "author": "Your name"
}
```

Example implementation:

```python
def register(api):
    api.register_tool({
        "type": "function",
        "function": {
            "name": "sample_status",
            "description": "Return the add-on status.",
            "parameters": {"type": "object", "properties": {}},
        },
    }, lambda: "Sample add-on is active")

    api.register_command("status", lambda args, log: log("Add-on active"),
                         "Show sample add-on status")
    api.on("task_started", on_task_started)
    api.register_action("Sample action", lambda: "Action completed")


def on_task_started(app, task):
    # Keep hooks fast and avoid blocking the UI thread.
    return None
```

Commands are namespaced to avoid collisions: `/sample-addon:status`. Available
lifecycle events currently include `tools_loaded`, `task_started`, `task_finished`,
`before_tool_call`, and `after_tool_call`. Add-ons may also declare capability labels
with `api.declare_capability(...)`. Tools are registered with the normal agent tool
registry and are subject to Agent Code's existing Plan Mode filtering and central
permission checks.

**Security:** add-ons are trusted Python code and run with the current user's
permissions. They are not a sandbox. Review add-on source before enabling it, and
never enable an add-on from an untrusted source. Add-ons are disabled in Core Mode.

---

Optional `COMMANDS` export adds user-facing slash commands. A command may also
register `aliases` for natural phrase dispatch; these invoke only the registered
Python skill handler (they are never interpreted as shell commands):

```python
COMMANDS = {
    "status": {
        "handler": handle_status,
        "description": "Show service status",
        "aliases": ["my service status", "check service status"],
    },
}
```

Slash commands remain supported as before. Example bundled temp-mail commands:
`/email`, `/providers`, `temp mail configure`, and `temp mail providers`.

```python
def _handle_ping(args: list, log) -> None:
    log(f"pong {' '.join(args)}", "dim")

COMMANDS = {
    "ping": {"handler": _handle_ping, "description": "Reply pong"},
}
```

Optional `skill.md` frontmatter gives the skill a name, version, and author.
Anything after the closing `---` becomes the skill's help page, visible in
the Help dialog when the user clicks the skill.

Full developer guide: read the module docstring in
[`src/agent_code/loader.py`](src/agent_code/loader.py) — the loader is
~200 lines and documents the whole skill contract.

---

## Bundled skills

`pip install agent-code` ships three skills. Run `agent-code skills install`
to copy them into your current folder's `skills/`:

| Skill | What it does |
|---|---|
| **filesystem** | Read, write, append, list files inside the sandbox workspace |
| **public_api** | Search 700+ free public APIs and call them |
| **temp_mail** | Temp inbox (mail.tm / Guerrilla) + email sending (Resend / Brevo / Mailjet) |

Installed skills appear under `./skills/<name>/` with `skill.py` and `skill.md`.
Toggle them on/off in the Skills dialog.

---

## Skill registry

The registry lets you publish skills and install them anywhere.

### Use the hosted registry (default)

A live instance is already running at `https://skills-manager.freesrv.com`.
Both the manager and the agent use it by default. If the domain is down,
they auto-fall-back to a raw IP.

```bash
agent-code manage
```

Sign in with any nickname — the account is created automatically. Then:

- Browse and search the store
- Install skills into `./skills/`
- Publish a folder as a skill
- Delete skills you own

### Self-hosting the registry

The standalone registry backend lives in `server/` and is licensed separately under **AGPL-3.0-only**. See [server/README.md](server/README.md).

---

## Command reference

### CLI

| Command | What it does |
|---|---|
| `agent-code` | Run the agent (same as `agent-code run`) |
| `agent-code run` | Run the agent GUI |
| `agent-code manage` | Open the skill store GUI |
| `agent-code skills list` | Show bundled skill names |
| `agent-code skills install` | Copy bundled skills to `./skills/` |
| `agent-code --version` | Print version |
| `agent-code --help` | Show all subcommands |

### Agent (in the chat box)

| Command | What it does |
|---|---|
| `/reset` | Clear conversation memory |
| `/history` | Print recent messages |
| `/skills` | List loaded + disabled skills + commands |
| `/save` | Force save chat locally and to cloud |
| `/open <file>` | Open a file from the workspace |
| Skill commands | Whatever skills register, e.g. `/email`, `/providers` |

### Agent buttons

| Button | Action |
|---|---|
| **Stop** | Halt the running agent loop |
| **Continue** | Resume from the last tool result |
| **Send** | Start a new task |
| **Save** | Save chat (local + cloud if enabled) |
| **Settings** | Edit API keys, base URL, model, cloud sync |
| **Skills** | Toggle installed skills on/off |
| **Help** | Two-pane help: sections + per-skill pages |

---

## Configuration reference

### `agent_config.json`

Placed in the folder where you run `agent-code`, or in the platform config dir
if no local file exists:

- **Windows:** `%APPDATA%\agent-code\agent_config.json`
- **Linux/macOS:** `~/.config/agent-code/agent_config.json`

```json
{
  "openai_api_keys": ["sk-...", "sk-..."],
  "openai_base_url": "https://api.openai.com/v1",
  "openai_model": "gpt-4o",
  "cloud_sync": false,
  "disabled_skills": [],
  "email_api": {
    "provider": "resend",
    "api_key": "re_...",
    "from_addr": "onboarding@resend.dev",
    "from_name": "Agent"
  }
}
```

| Field | Notes |
|---|---|
| `openai_api_keys` | Multiple keys rotate per request |
| `openai_base_url` | Any OpenAI-compatible endpoint |
| `openai_model` | Depends on the provider |
| `cloud_sync` | Sync `chats/current.json` to the registry |
| `disabled_skills` | List of skill folder names to skip |
| `email_api` | Optional, used by the `temp_mail` skill |

### Where files go

When you run `agent-code` from a folder, it creates:

```
<your-folder>/
├── skills/          ← installed + bundled skills
├── workspace/       ← sandbox for shell and file tools
├── chats/           ← auto-saved conversation
└── agent_config.json (if you created one here)
```

Whichever folder you launch from is the "project" for that session. Run
`agent-code` from different folders to keep separate projects.

---

## Security

The agent executes LLM-generated commands. That's the point, but it means
you need to be careful.

**Default shell mode (Podman disabled):**

- Runs commands on the host OS, so it is not a strong security boundary.
- Restricts shell operators and rejects known high-risk command patterns.
- Keeps the working directory and explicit file-path arguments inside the project workspace where detectable.

**Full Linux sandbox (Settings → Sandbox → Enable Podman sandbox):**

- Runs shell and background commands inside a persistent **Alpine Linux 3.22** container (not Ubuntu).
- The agent's system instructions identify this environment as Alpine Linux and recommend `apk` for package management.
- Configures the matching Alpine v3.22 `main` and `community` repositories explicitly, refreshes indexes with retries, and installs packages from those repositories.
- Uses Podman's bridge network for outbound internet/DNS, subject to host firewall, DNS, and Podman network configuration.
- Supports normal Bash syntax, pipelines, redirects, compound commands, scripts, and Linux commands.
- Includes Bash, core utilities, and `apk`; install more tools inside the container with `apk add --no-cache <package>`.
- Mounts only the current project workspace as a writable host path; container capabilities are dropped and `no-new-privileges` is enabled.
- Podman bridge networking is enabled for outbound internet/DNS, including package installation and network tools, when permitted by the host network, DNS, firewall, and Podman configuration. The workspace itself is shared with the host, so commands can still change or delete project files.
- The sandbox runs as root *inside the container*, not as host root. Do not treat containers as a perfect security boundary.

**Other considerations:**

- **Skills are arbitrary Python** — installing a skill is trusting its author.
- **Prompt injection via web content** — malicious page content can steer the agent.
- Turning Podman off routes shell commands back to the real host OS. Only disable it when you intentionally want host execution.

---

## Files at a glance

### Installed package

```
site-packages/agent_code/
├── __init__.py
├── __main__.py
├── cli.py
├── paths.py
├── agent.py
├── skill_manager.py
├── loader.py
└── data/
    └── skills/
        ├── filesystem/{skill.py,skill.md}
        ├── public_api/{skill.py,skill.md}
        └── temp_mail/{skill.py,skill.md}
```

### Your project folder (created on first run)

```
your-folder/
├── skills/
├── workspace/
├── chats/
└── agent_config.json (optional)
```

### This repository

```
Agent-code/
├── pyproject.toml          ← PyPI metadata
├── src/agent_code/         ← the package source
├── docs/skills.html        ← developer guide
├── README.md
├── LICENSE                 ← MIT for the Agent Code application
├── server/
│   ├── skill-server.py     ← standalone registry backend
│   ├── LICENSE             ← AGPL-3.0-only for the server
│   └── README.md
└── .gitignore
```

The registry backend is a separate component. Its AGPL-3.0-only license does not replace the MIT license for the Agent Code application; see the component-specific notices below.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `agent-code: command not found` | Add `~/.local/bin` to PATH, or use `python3 -m agent_code` |
| `browser: FAILED` | Install Chromium/Chrome and check DrissionPage browser configuration |
| `browser: FAILED` (Linux) | `sudo apt install chromium` (or `dnf` / `pacman` equivalent) |
| `_tkinter.TclError` | Install `python3-tk` (Debian-family) or `python3-tkinter` (Fedora) |
| `no display name and no $DISPLAY` | You're on a headless machine — GUI won't work there |
| `LLM ERROR: 401` | Wrong API key, or stray quotes around it in `agent_config.json` |
| `LLM ERROR: 404` | Model name doesn't match the provider |
| `BLOCKED: '<cmd>' not allowed` | Add it to `ALLOWED_CMDS`, or use a different approach |
| `[loader] FAILED to load skill` | Run `python skills/<name>/skill.py` to see the import error |
| `externally-managed-environment` (Linux) | Use `pipx install agent-code` or a virtualenv |

---

## Development

Clone the repo, install in editable mode:

```bash
git clone https://github.com/minecraftbefile-maker/Agent-code.git
cd Agent-code
pip install -e .
```

Run the agent and local skill manager:

```bash
agent-code run
agent-code manage
```

The skill loader is ~200 lines: `src/agent_code/loader.py`. Read it alongside
`docs/skills.html` — between the two you'll know everything the agent does
with a skill.

---

## License

Component-specific licenses:

| Component | License |
|---|---|
| Agent Code application (`src/agent_code/`), docs, and project files outside `server/` | **MIT** — see [`LICENSE`](LICENSE) |
| Registry backend (`server/`) | **AGPL-3.0-only** — see [`server/LICENSE`](server/LICENSE) and the [official license text](https://www.gnu.org/licenses/agpl-3.0.html) |

The registry server is separately licensed so that the network-use source-sharing terms apply to that component. Do not treat the server as MIT-licensed.

Default skills use third-party services:

- **mail.tm** — receive-only temp inbox, no signup
- **Guerrilla Mail** — fallback inbox
- **Resend / Brevo / Mailjet** — email sending, free tiers
- **public-api-lists** — public API catalog (MIT)
- **DrissionPage** — browser automation (BSD-3)
- **OpenAI Python SDK** — LLM client (Apache-2.0)

## Global skills and local user configuration (dev10)

Agent Code stores installed skills in a per-user data directory shared across projects:

- Windows: `%LOCALAPPDATA%\AgentCode\skills` (falls back to `%APPDATA%\AgentCode\skills`)
- Linux: `$XDG_DATA_HOME/agent-code/skills` or `~/.local/share/agent-code/skills`

Agent Code settings and API credentials are stored in the per-user config directory rather than in the project workspace:

- Windows: `%APPDATA%\agent-code\agent_config.json`
- Linux: `$XDG_CONFIG_HOME/agent-code/agent_config.json` or `~/.config/agent-code/agent_config.json`

The Skills Store's login/config data is stored beside the Agent Code config. Legacy project-local `skills/` folders are copied into the global skills directory when the app starts; existing global skills are never overwritten. The workspace itself remains project-local. These are local files, so users should protect their OS account and avoid sharing config files containing API keys.

### Provider presets (v2.0.0.dev12)

Open **Settings → API & Models** and choose a provider preset:

- **OpenAI** — `https://api.openai.com/v1`
- **Google AI Studio** — Gemini through Google's OpenAI-compatible endpoint: `https://generativelanguage.googleapis.com/v1beta/openai/`. Use a Gemini API key from Google AI Studio and a supported Gemini model name.
- **Anthropic** — Claude through Anthropic's OpenAI SDK compatibility endpoint: `https://api.anthropic.com/v1/`. Use an Anthropic API key and a supported Claude model name. Anthropic describes this compatibility layer as primarily for testing/comparison; native Claude API features may not all be available.
- **Custom OpenAI-compatible** — enter your own base URL and model.

Provider selection is saved in the per-user Agent Code configuration. API keys remain local to that user configuration. The Google and Anthropic presets use the OpenAI SDK compatibility surface, so compatibility depends on the provider's supported request fields and model names.

### Creating a new project

When you ask Agent Code to create a new app, game, website, or other project, it creates a fresh, uniquely named subdirectory in the active workspace first and keeps the new files inside it. Existing project folders are not used as the destination. If a folder with that name already exists, Agent Code selects a free suffix such as `-2` rather than overwriting it. Ask Agent Code to "modify this existing project" when you want in-place changes.


### Alpine sandbox compiler tools

The optional Podman sandbox uses Alpine Linux 3.22. Its `build-base` package supplies GCC (`gcc`), G++ (`g++`), Make, and C development headers; Bash, Git, curl, Python/pip, and common command-line utilities are installed as well. The container shares the project workspace at `/workspace`.

### Chat transcript shortcuts

The conversation toolbar provides **Copy answer**, **Find**, and **Latest** actions. Find searches the transcript case-insensitively and highlights the first match.


## Link to SSH (remote VM)

Open **Settings & Accounts → Link to SSH**, enter the VM hostname/IP, SSH username, port, and optionally a private-key path, then choose **Link / Connect**. Password authentication is supported; leave the password blank to use SSH agent/key-based authentication. Passwords are session-only and are not saved in the configuration. The remote host must already be trusted in `~/.ssh/known_hosts`; Agent Code rejects unknown host keys rather than silently trusting them. After connecting, the agent receives a `remote_shell` tool for commands on that host. Remote commands require user approval unless permission mode is set to Auto. Disconnect removes the remote tool.

Install the SSH dependency with `pip install paramiko` if it is not installed. Keep SSH private keys protected and only link machines you are authorized to administer.

### SSH authentication troubleshooting

Link to SSH checks a matching `~/.ssh/config` entry for `IdentityFile` and `HostName`, uses the SSH agent and default key locations, and accepts an explicit private-key path. If `ssh user@host` works but the GUI still cannot authenticate, enter the same host alias used by OpenSSH or specify its private key path. For passphrase-protected keys, unlock the key with `ssh-agent` first. Unknown host keys remain rejected until the host is trusted through your normal OpenSSH workflow.

## Quick SSH Connect

Open **Settings & Accounts → Link to SSH** and paste a connection-only command, for example `ssh root@ubuntu-server.com`, `ssh -p 2222 deploy@vm.example`, or `ssh -i ~/.ssh/id_ed25519 user@host`. Agent Code reads the selected OpenSSH config (`~/.ssh/config` by default), uses configured identities and the SSH agent, and prompts when a host key or authentication credential needs attention. Unknown host keys are never accepted silently: verify the displayed fingerprint before choosing to save it or trust it for one connection. Passwords and key passphrases are session-only. Remote commands are executed on the linked host and should be reviewed carefully. The quick-connect field intentionally rejects remote commands and arbitrary `-o` options; put advanced SSH configuration in your OpenSSH config file.

## Secure credential storage and operation progress

Provider API keys are stored through Python `keyring` in the operating system's credential store (Windows Credential Manager, macOS Keychain, or a Linux Secret Service-compatible keyring). The JSON configuration stores credential references rather than API-key values. If the OS credential store is unavailable, saving credentials fails closed instead of silently writing new secrets in plaintext. Existing legacy plaintext keys are loaded for migration and are moved to the OS store the next time settings are saved successfully. Linux desktop environments need a working Secret Service/keyring session (for example, GNOME Keyring or KWallet integration).

Long-running actions now show a modal progress window, including model-list retrieval and Alpine Podman sandbox start/stop/remove. First sandbox start can take longer because Podman may need to download the Alpine image.

## Terminal UI transcript behavior (2.0.0 maintenance update)

The terminal workspace keeps assistant replies prominent: tool results are shown as
compact summaries in Chat, while complete tool output remains in the model's tool
history and the recent Activity view. Use Page Up/Page Down (or Home/End) to scroll
the transcript. Assistant commentary returned alongside tool calls is preserved.

The TUI also avoids resending the just-submitted user prompt twice in a single
model request. Use `!command` to force direct shell execution; recognized executable
commands are dispatched directly, while natural-language requests go to the agent.

### Task completion summaries
Task reports include verified changed-file lists and, when text files can be safely decoded, aggregate line additions and deletions. Binary files are identified without fabricating line counts. See `RELEASE-NOTES-2.0.0-TASK-DIFF-SUMMARY.md`.


## Recent development

See [Visual Diff Review release notes](RELEASE-NOTES-2.0.0-VISUAL-DIFF-REVIEW.md).
