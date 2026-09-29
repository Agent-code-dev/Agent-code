# Agent + Skill Store

A local AI agent with a headless browser, sandboxed shell, chat GUI, and a
plug-and-play skill system backed by a hosted skill registry.

[![PyPI](https://img.shields.io/pypi/v/agent-code)](https://pypi.org/project/agent-code/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/agent-code/)
[![License](https://img.shields.io/badge/license-MIT%20%2B%20GPL--3.0-green)](#license)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#platform-support)

**Live site:** https://agent-code.freesrv.com · **Install:** `pip install agent-code`

---

## What this is

One command install. Two GUIs. A hosted skill registry.

| Command | What it opens |
|---|---|
| `agent-code` | The agent — chat GUI, headless browser, sandboxed shell |
| `agent-code manage` | The skill store — browse, install, publish skills |
| `agent-code skills list` | List bundled skills |
| `agent-code skills install` | Copy bundled skills into `./skills/` |

Skills are folders under `./skills/`. Drop one in, restart the agent, its tools
appear in the LLM's tool list. No changes to the agent required.

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

| Platform | CLI (`skills list`, `skills install`) | GUI (`run`, `manage`) |
|---|---|---|
| **Windows 10/11** | ✓ | ✓ (WebView2 required) |
| **macOS 12+** | ✓ | ✓ |
| **Ubuntu / Debian / Kali / Mint** | ✓ | needs `python3-tk` |
| **Fedora / RHEL** | ✓ | needs `python3-tkinter` |
| **Arch / Manjaro** | ✓ | needs `tk` |
| **Headless server / Cloud Shell / WSL** | ✓ | ✗ (no display) |

### Linux setup

One line per distro — installs tkinter (GUI) and Chromium (browser):

```bash
# Ubuntu / Debian / Kali / Mint / Pop!_OS
sudo apt install python3-tk chromium

# Fedora / RHEL / CentOS Stream
sudo dnf install python3-tkinter chromium

# Arch / Manjaro
sudo pacman -S tk chromium
```

If `agent-code` isn't found after install, add pip's user bin to PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Or use the module form which never needs PATH:

```bash
python3 -m agent_code --version
python3 -m agent_code run
```

### Windows setup

`pip install agent-code` handles the Python side. If `agent-code run` shows
`browser: FAILED`, install the [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)
from Microsoft. It's preinstalled on Windows 11 and most up-to-date Windows 10.

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

Optional `COMMANDS` export adds user-facing slash commands:

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

Full developer guide: [`docs/skills.html`](docs/skills.html).

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

The server is GPL-3.0 and lives in this repo as `skill-server.py`. See
[Server setup](#server-setup) below.

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

## Server setup

Only needed if you want your own registry instance. The client works with
the hosted one out of the box.

```bash
mkdir -p /opt/skill-server && cd /opt/skill-server
# copy skill-server.py here
python3 skill-server.py --host 0.0.0.0 --port 8000
```

Then point the clients at it by editing `SKILL_SERVER_PRIMARY` and
`SKILL_SERVER_FALLBACK` in the source, or by setting them in `agent_config.json`.

---

## Security

The agent executes LLM-generated commands. That's the point, but it means
you need to be careful.

**Already sandboxed:**

- **Shell** — allowlist of commands, `shell=False`, `CWD=workspace/`, no
  pipes / redirects / `;` / `&` / `&&`, no absolute paths outside the workspace
- **Filesystem skill** — every path resolved and validated against `workspace/`
- **Browser** — headless, in a throwaway profile
- **Registry server** — PBKDF2 password hashing, session tokens, ownership
  checks on publish/delete, ZIP entry validation, upload size cap

**Not sandboxed:**

- **`python` is in the shell allowlist** — the agent can read arbitrary
  files. Remove `python`, `python3`, `node` from `ALLOWED_CMDS` if that matters.
- **`curl` / `wget` are allowed** — the agent can POST local data to remote
  servers.
- **Skills are arbitrary Python** — installing a skill is trusting its author.
- **Prompt injection via web content** — a malicious page can steer the agent.

For untrusted use, run the agent inside Docker.

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
├── LICENSE                 ← MIT
├── LICENSE-GPL             ← GPL-3.0
└── .gitignore
```

`skill-server.py` (the registry backend, GPL-3.0) is deployed separately on a VPS.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `agent-code: command not found` | Add `~/.local/bin` to PATH, or use `python3 -m agent_code` |
| `browser: FAILED` (Windows) | Install WebView2 Runtime from Microsoft |
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

Run the agent, manager, and site server directly:

```bash
agent-code run
agent-code manage
python -m agent_code.landing --port 8080     # if you kept the site server
```

The skill loader is ~200 lines: `src/agent_code/loader.py`. Read it alongside
`docs/skills.html` — between the two you'll know everything the agent does
with a skill.

---

## License

Split license:

| Component | License |
|---|---|
| `agent_code/` package, `docs/**`, README | **MIT** — see [`LICENSE`](LICENSE) |
| `skill-server.py` | **GPL-3.0** — see [`LICENSE-GPL`](LICENSE-GPL) |

**Why the split?** The client code is meant to be embedded, forked, and
redistributed freely. The server is meant to stay open — if you host a
modified version, you must publish your changes.

Default skills use third-party services:

- **mail.tm** — receive-only temp inbox, no signup
- **Guerrilla Mail** — fallback inbox
- **Resend / Brevo / Mailjet** — email sending, free tiers
- **public-api-lists** — public API catalog (MIT)
- **DrissionPage** — browser automation (BSD-3)
- **OpenAI Python SDK** — LLM client (Apache-2.0)
