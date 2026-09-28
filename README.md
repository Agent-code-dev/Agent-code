# Agent + Skill Store

A local AI agent with a headless browser, sandboxed shell, chat GUI, and a
plug-and-play skill system backed by a hosted skill registry.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT%20%2B%20GPL--3.0-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## What this is

Two programs on your machine, plus a registry server that's already hosted for you.

| File | Runs on | Job |
|---|---|---|
| **`agent.py`** | your machine | The agent. Chat GUI, headless browser, sandboxed shell, tool loop, skill toggles. |
| **`skill-manager.py`** | your machine | App-store GUI. Sign in, browse, install, publish skills. |
| **`skill-server.py`** | a server (hosted for you) | Registry + state sync. GPL-3.0. |

Skills are folders under `skills/`. Drop one in, restart the agent, its tools
appear in the LLM's tool list. No changes to `agent.py` required.

---

## About the server

You **don't need to run the server yourself.** A live instance is already
hosted and configured:

    https://skills-manager.freesrv.com

Both `agent.py` and `skill-manager.py` point at it by default. The manager
tries the HTTPS domain first and automatically falls back to a raw IP
(`http://78.154.103.43:9074`) if the domain goes down.

If you'd rather run your own, the source is included under GPL-3.0 (see
[License](#license)). You can fork it, self-host it, extend the endpoints, or
replace the storage backend. See [self-hosting the server](#self-hosting-the-server).

The agent **never auto-installs skills**. You do that explicitly through the manager.

---

## Features

- **Headless Chromium** via DrissionPage — no popup window, real JS rendering
- **Sandboxed shell** — allowlist + workspace jail, no pipes or metachars
- **Plug-and-play skills** — each is a folder with `skill.py` + `skill.md`
- **Skill registry** — publish, browse, install (hosted, or self-host)
- **Stop / Continue** buttons — halt a run mid-turn, resume from last tool result
- **Local chat save** — `chats/current.json`, auto-saved every turn
- **Cloud sync** — optional, via the same registry (HTTPS + IP fallback)
- **Multi-key LLM** — rotate OpenAI-compatible API keys transparently
- **Custom base URL** — OpenAI, Together, Groq, DeepSeek, local vLLM, anything OpenAI-shaped
- **Dark tkinter GUI** — Settings, Skills, Help dialogs, plus skill-loaded `/commands`
- **Two-pane Help** — every skill gets its own help page, loaded from its `skill.md`

Bundled default skills: `filesystem`, `public_api`, `temp_mail`.

---

## Quick start

### 1. Install dependencies

    pip install DrissionPage openai

Windows: install WebView2 Runtime if the browser self-test fails.
Linux: `sudo apt install python3-tk`.

### 2. Configure

Create `agent_config.json`:

    {
      "openai_api_keys": ["sk-your-key-here"],
      "openai_base_url": "https://api.openai.com/v1",
      "openai_model": "gpt-4o",
      "cloud_sync": false
    }

Or edit it from the GUI later via **Settings**.

### 3. Run

    python agent.py

Or on Windows, double-click `run.bat`.

### 4. Talk to it

    go to news.ycombinator.com and list the top 5 story titles
    find a free API for cat facts and call it
    create a snake game in a single HTML file

---

## The skill system

A skill is a folder:

    skills/my_skill/
    ├── skill.py     ← code
    └── skill.md     ← metadata + docs

`skill.py` exports three things:

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

That's it. Restart the agent, the LLM can call `greet()`.

Optional `COMMANDS` export adds user-facing slash commands:

    def _handle_ping(args: list, log) -> None:
        log(f"pong {' '.join(args)}", "dim")

    COMMANDS = {
        "ping": {"handler": _handle_ping, "description": "Reply pong"},
    }

Optional `skill.md` frontmatter gives the skill a name, version, and author.
Anything after the closing `---` becomes the skill's help page, visible in
the Help dialog when the user clicks the skill.

Full developer guide: `docs/skills.html` — open in any browser.

---

## Skill registry

### Use the hosted server (default)

No setup needed. Both clients already point at
`https://skills-manager.freesrv.com`. Just:

    # Register a nickname (password is prompted)
    python skill-manager.py register yourname

    # Or launch the GUI
    python skill-manager.py

The GUI lets you:

- Browse the store with search
- Install skills into `./skills/`
- Publish a folder as a skill
- See your published skills and download counts
- Delete skills you own

### Self-hosting the server

Only needed if you want your own instance or to modify it. The server is
~450 lines of stdlib Python — no framework, no external dependencies.

Deploy:

    mkdir -p /opt/skill-server && cd /opt/skill-server
    # copy skill-server.py here
    python3 skill-server.py --host 0.0.0.0 --port 8000

It creates `skill_server.db` (SQLite) and `skill_storage/` on first run.

Put TLS in front with Caddy:

    skills.example.com {
        reverse_proxy 127.0.0.1:8000
    }

Or nginx:

    server {
        listen 443 ssl;
        server_name skills.example.com;

        location /login {
            limit_req zone=login burst=3 nodelay;
            proxy_pass http://127.0.0.1:8000;
        }
        location / {
            proxy_pass http://127.0.0.1:8000;
        }
    }

Point the clients at it by editing the constants at the top of both files:

    SKILL_SERVER_PRIMARY  = "https://skills.example.com"
    SKILL_SERVER_FALLBACK = "http://1.2.3.4:8000"

---

## Architecture

    [agent.py]                        [skill-manager.py]
         │                                     │
         │  reads token from                   │  signs in, gets token
         │  ~/.skill-manager.json              │
         │                                     │
         └──────── HTTP/HTTPS ─────────────────┘
                          │
                          ▼
           https://skills-manager.freesrv.com    (primary, hosted)
           http://78.154.103.43:9074             (fallback IP)
                          │
                          ▼
                  [skill-server.py]  (already deployed)
                  - /register /login /logout
                  - /me
                  - /skills  GET / POST / DELETE
                  - /skills/<name>/download
                  - /state   GET / POST

You can swap the server URL in both clients at any time.

---

## Command reference

### Agent (in the chat box)

| Command | What it does |
|---|---|
| `/reset` | Clear conversation memory |
| `/history` | Print recent messages |
| `/skills` | List loaded + disabled skills + available commands |
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

### Skill manager

| Command | What it does |
|---|---|
| `register <nick>` | Create an account |
| `login <nick>` | Sign in |
| `logout` | Sign out |
| `whoami` | Show your account + published skills |
| `list [--search Q]` | Browse the store |
| `show <name>` | Full metadata for one skill |
| `install <name> [--force]` | Download + extract to `./skills/` |
| `uninstall <name>` | Remove from `./skills/` |
| `installed` | List locally installed skills |
| `publish <path> --name N --description D [--version V]` | Package and upload a folder |

---

## Configuration reference

### `agent_config.json`

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

| Field | Notes |
|---|---|
| `openai_api_keys` | Multiple keys rotate per request |
| `openai_base_url` | Any OpenAI-compatible endpoint |
| `openai_model` | Depends on the provider |
| `cloud_sync` | Sync `chats/current.json` to the registry |
| `disabled_skills` | List of skill folder names to skip |
| `email_api` | Optional, used by the `temp_mail` skill |

### `~/.skill-manager.json`

Managed automatically by `skill-manager.py`. Contains the auth token and
cached skill list. Never commit this.

---

## Security

The agent executes LLM-generated commands. That's the point, but it means
you need to be careful.

**Already sandboxed:**

- **Shell** — allowlist of commands, `shell=False`, `CWD=workspace/`, no
  pipes / redirects / `;` / `&` / `&&`, no absolute paths outside the workspace
- **Filesystem skill** — every path resolved and validated against `workspace/`
- **Browser** — headless, in a throwaway profile
- **Server** — PBKDF2 password hashing, session tokens, ownership checks on
  publish/delete, ZIP entry validation, upload size cap

**Not sandboxed:**

- **`python` is in the shell allowlist** — the agent can read arbitrary
  files. If that matters, remove `python`, `python3`, `node` from `ALLOWED_CMDS`.
- **`curl` / `wget` are allowed** — the agent can POST local data to remote
  servers. Remove them if that's a concern.
- **Skills are arbitrary Python** — installing a skill is trusting its author.
- **Prompt injection via web content** — a malicious page can steer the
  agent. Mitigated by the sandbox, not eliminated.

For untrusted use, run the whole thing in Docker.

---

## Files at a glance

    man-code/
    ├── agent.py                 ← the agent
    ├── skill-manager.py         ← the client
    ├── agent_config.json        ← your keys (gitignored)
    ├── agent_config.example.json
    ├── run.bat                  ← Windows launcher for the agent
    ├── store.bat                ← Windows launcher for the manager
    ├── README.md
    ├── LICENSE                  ← MIT (client code)
    ├── LICENSE-GPL              ← GPL-3.0 (server code)
    ├── .gitignore
    ├── docs/
    │   └── skills.html          ← developer guide for writing skills
    ├── chats/
    │   └── current.json         ← auto-saved conversation (gitignored)
    ├── skills/
    │   ├── loader.py            ← loads every enabled skill
    │   ├── filesystem/
    │   ├── public_api/
    │   └── temp_mail/
    └── workspace/               ← agent's sandbox (gitignored)

`skill-server.py` is **not** in this tree. It lives on the server and is
maintained separately.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `browser: FAILED` | Install WebView2 (Windows) or check Chromium. |
| `LLM ERROR: 401` | Wrong API key, or quotes around the value. |
| `LLM ERROR: 404` | Model name doesn't match the provider. |
| `BLOCKED: '<cmd>' not allowed` | Add the command to `ALLOWED_CMDS` in `agent.py`. |
| `NOT_FOUND: <selector>` | CSS selector didn't match. Run `browser_snapshot`. |
| `[loader] FAILED to load skill` | Run `python skills/<name>/skill.py` to see the error. |
| Registry times out | Fallback IP should kick in; check console for `[fallback]`. |
| `Cloudflare blocked` | Add a WAF skip rule for the API paths on your server. |

---

## License

This project uses a split license:

| Component | License |
|---|---|
| `agent.py`, `skill-manager.py`, `skills/**`, `docs/**`, `*.bat` | **MIT** — see `LICENSE` |
| `skill-server.py` | **GPL-3.0** — see `LICENSE-GPL` |

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