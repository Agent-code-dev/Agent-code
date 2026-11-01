<div align="center"><img src="src/agent_code/data/icons/agent-code.png" width="120" alt="Agent Code Logo">Agent Code 2.0

⚡ Your AI coding agent. Your tools. Your environment.

An open-source, extensible AI coding agent built with Python.

Build, modify, debug, and manage projects using AI — with customizable Skills, application Add-ons, and MCP integrations.

<br>""PyPI" (https://img.shields.io/pypi/v/agent-code?style=for-the-badge&logo=pypi&logoColor=white)" (https://pypi.org/project/agent-code/)
""Python" (https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)" (https://www.python.org/)
""License" (https://img.shields.io/badge/Application-MIT-2ea44f?style=for-the-badge&logo=opensourceinitiative&logoColor=white)" (LICENSE)
""Server" (https://img.shields.io/badge/Server-AGPL--3.0-blue?style=for-the-badge)" (server/LICENSE)

""Platform" (https://img.shields.io/badge/Windows-Linux-macOS-lightgrey?style=flat-square)" (#-platform-support)
""GitHub" (https://img.shields.io/badge/GitHub-Repository-181717?style=flat-square&logo=github)" (https://github.com/agent-code-dev/agent-code)
""Website" (https://img.shields.io/badge/Website-Visit-4285F4?style=flat-square&logo=googlechrome&logoColor=white)" (https://agent-code-dev.github.io)

<br>"Installation" (#-installation) · "Features" (#-features) · "Documentation" (#-documentation) · "Development" (#-development)

</div>---

🌟 What is Agent Code?

Agent Code is a desktop AI coding agent designed to give developers more control over their AI-assisted development environment.

Unlike tools that depend on a fixed set of capabilities, Agent Code is built around extensibility.

You can:

- 🤖 Connect different AI providers using your own API keys.
- 🧩 Extend the AI agent with Python-based Skills.
- 🔌 Extend the application itself with Add-ons.
- 🌐 Connect external tools through MCP.
- 💻 Execute supported operations locally.
- 📦 Use an isolated Linux sandbox.
- 🖥️ Connect to remote machines through SSH.
- ⚙️ Customize permissions and agent workflows.

The goal: an AI coding environment that developers can extend instead of being restricted to a predefined toolset.

---

✨ Features

<table>
<tr>
<td width="50%">🤖 AI Coding Agent

- Tool-calling architecture
- Multi-step task execution
- Project-aware workflows
- Plan and Build modes
- Error investigation and recovery
- Project checkpoints

</td>
<td width="50%">🎨 Desktop Experience

- CustomTkinter interface
- Chat-based workspace
- Markdown responses
- Activity details
- Project navigation
- Model and provider settings

</td>
</tr>
<tr>
<td width="50%">🧩 Extensibility

- Native Python Skills
- Application Add-ons
- MCP integration
- Custom agent commands
- Extension management

</td>
<td width="50%">🖥️ Execution

- Local computer
- Linux sandbox
- SSH remote execution
- Configurable permissions
- Environment-specific operations

</td>
</tr>
</table>---

🧠 Three Independent Extension Systems

One of the most important parts of Agent Code 2.0 is its extension architecture.

Skills, Add-ons, and MCP are separate systems with different responsibilities.

<div align="center">🧩 Skills| 🔌 Add-ons| 🌐 MCP
Extend the AI agent| Extend the application| Connect external tools
Python tools| Application extensions| MCP protocol
Agent commands| UI and supported services| External servers

</div>🧩 1. Skills — Extend the AI Agent

Skills provide the AI with additional tools and capabilities.

A Skill can expose:

- Python functions.
- Tool schemas.
- Agent-specific commands.
- Metadata and documentation.
- Specialized workflows.

Example structure:

skills/
└── example/
    ├── skill.py
    └── skill.md

Example:

SKILL = {
    "name": "example",
    "description": "Example Agent Code skill"
}

TOOL_SCHEMAS = [
    # Define AI-callable tools
]

TOOL_CALLABLES = {
    # Connect tool names to Python functions
}

COMMANDS = {
    # Optional agent-specific commands
}

Skills are loaded through the native loader system.

Documentation: "Skills Developer Guide" (docs/index.html)

🔌 2. Add-ons — Extend Agent Code Itself

Add-ons are different from Skills.

They are designed to extend the application rather than simply give the AI additional tools.

Supported extension areas include:

- Application actions.
- UI contributions.
- Additional application functionality.
- Agent tools and commands.
- Lifecycle hooks.
- Supported service integrations.

Example structure:

my-addon/
├── addon.json
└── addon.py

Example manifest:

{
    "name": "sample-addon",
    "version": "1.0.0",
    "description": "An example Agent Code extension",
    "author": "Developer"
}

Add-ons use the application's extension API and supported extension points.

Documentation: "Add-on Development" (ADDON-DEVELOPMENT.md)

🌐 3. MCP — Connect External Tools

Agent Code also supports Model Context Protocol (MCP).

MCP allows the agent to connect to external tool servers and use capabilities exposed through them.

This makes it possible to integrate external services without implementing every integration as a native Skill.

Skills, Add-ons, and MCP can coexist.

---

⚙️ Agent Modes

📋 Plan Mode

Focuses on understanding tasks and preparing an implementation plan.

Useful for:

- Project analysis.
- Requirement breakdown.
- Identifying files to modify.
- Planning multi-step work.

🛠️ Build Mode

Focuses on carrying out development tasks.

The agent can use its available tools to:

- Create files.
- Modify code.
- Run supported commands.
- Investigate errors.
- Implement planned changes.

⚡ Core Mode

A lightweight operating configuration without additional Skills.

It focuses on essential capabilities such as file creation, shell execution, and CURL operations.

Core Mode is separate from the regular Skills architecture.

---

🖥️ Execution Environments

Agent Code separates the agent's workflow from the environment in which tools execute.

Environment| Description
💻 Local| Execute supported operations on the host computer.
📦 Sandbox| Run supported commands inside an isolated Linux container.
🌐 SSH| Execute supported operations on a remote machine.

📦 Alpine Linux Sandbox

The optional Podman sandbox uses Alpine Linux 3.22.

It provides a Linux environment for development operations, including:

- Bash.
- Common Linux utilities.
- Git.
- CURL.
- Python.
- GCC and G++ through Alpine's build packages.
- Alpine package management with "apk".

The sandbox shares the active project workspace with the host, so changes to project files remain visible.

The container is an isolation layer, not a guarantee that every operation is completely risk-free.

🌐 SSH Remote Execution

Connect to remote machines through the SSH integration.

Supported configuration includes:

- Hostname or IP.
- SSH username.
- Port.
- Private-key path.
- Password authentication.
- SSH agent and key-based authentication.

Unknown SSH host keys are rejected rather than silently trusted.

---

🤖 AI Providers

Agent Code uses an OpenAI-compatible client architecture.

You can configure your own provider credentials and model settings.

Provider presets include:

Provider| Integration
OpenAI| OpenAI API
Google AI Studio| Gemini compatibility endpoint
Anthropic| OpenAI SDK compatibility endpoint
OpenRouter| Multi-model routing
Custom| OpenAI-compatible endpoints

Provider compatibility depends on the endpoint, model, and supported API features.

🔑 Bring Your Own Key

Agent Code does not require a mandatory recurring AI subscription.

You control your provider account, API key, model selection, and API spending.

External providers may charge for their services.

---

🔐 Permissions & Security

Agent Code includes configurable permission behavior.

Mode| Purpose
🛡️ Safe| More restrictive execution behavior.
⚙️ Normal| Balanced permissions.
⚡ Auto| More automated execution.

Always review the permissions granted to third-party extensions.

Security considerations:

- Skills are Python code and can execute with the user's permissions.
- Add-ons are trusted Python code, not isolated sandboxes.
- MCP servers may expose external operations.
- Local shell execution affects the host environment.
- Sandbox execution still shares the project workspace.
- API keys and private SSH keys should never be published.

---

💻 Platform Support

Agent Code targets Python 3.10+.

Platform| Support| Notes
🪟 Windows| Supported target| Python, Tcl/Tk, browser dependencies
🐧 Linux| Supported target| Python, Tk package, browser dependencies
🍎 macOS| Supported target| Python, Tcl/Tk, browser dependencies

Some optional features require additional system dependencies.

Linux dependencies

Ubuntu / Debian:

sudo apt update
sudo apt install python3-tk chromium

The optional Alpine sandbox requires a working Podman environment.

---

📥 Installation

Install from PyPI

The simplest installation method:

python -m pip install agent-code

Upgrade:

python -m pip install --upgrade agent-code

Install from Source

git clone https://github.com/agent-code-dev/agent-code.git

cd agent-code

python -m pip install -e .

---

🚀 Getting Started

Launch the application:

agent-code

Open the GUI explicitly:

agent-code gui

Open the terminal interface:

agent-code tui

Check your environment:

agent-code doctor

Display diagnostic information as JSON:

agent-code doctor --json

For all available commands:

agent-code --help

---

📚 Documentation

Agent Code includes documentation for users and extension developers.

Documentation| Description
📖 "User Documentation" (docs/index.html)| Installation, settings, workflows and troubleshooting.
🧩 "Skills Documentation" (docs/index.html)| Native Skills architecture and development.
🔌 "Add-on Development" (ADDON-DEVELOPMENT.md)| Creating application extensions.
📋 "Release Notes" (RELEASE-NOTES-2.0.0.md)| Version 2.0.0 changes.
🖥️ "Server Documentation" (server/README.md)| Separate Skills registry backend.

---

🛠️ Development

Clone the repository:

git clone https://github.com/agent-code-dev/agent-code.git

cd agent-code

Install in editable mode:

python -m pip install -e .

Run tests:

python -m pytest -q

Build packages:

python -m pip install build
python -m build

The project uses a "src/" package layout.

---

📁 Project Structure

Agent-code/
│
├── src/
│   └── agent_code/
│       ├── agent.py
│       ├── loader.py
│       ├── addons.py
│       ├── mcp_manager.py
│       ├── skill_manager.py
│       ├── advanced_features.py
│       ├── projects.py
│       ├── paths.py
│       ├── cli.py
│       ├── tui.py
│       └── data/
│
├── docs/
│   ├── index.html
│   └── addons.html
│
├── server/
│   ├── skill-server.py
│   ├── README.md
│   └── LICENSE
│
├── tests/
│
├── ADDON-DEVELOPMENT.md
├── RELEASE-NOTES-2.0.0.md
├── README.md
├── LICENSE
└── pyproject.toml

---

🗺️ Roadmap

Areas of continued development include:

- 🚀 Improving agent reliability.
- 🧠 Reducing unnecessary token consumption.
- 🧩 Growing the Skills ecosystem.
- 🔌 Expanding Add-on extension points.
- 🌐 Improving MCP compatibility.
- 📦 Improving sandbox execution.
- 🖥️ Improving cross-platform support.
- 🔐 Strengthening extension security.
- 🎨 Improving the desktop experience.

---

🤝 Contributing

Contributions are welcome!

You can help by:

- Reporting bugs.
- Suggesting features.
- Improving documentation.
- Creating Skills.
- Developing Add-ons.
- Testing compatibility.
- Submitting pull requests.

Repository:

https://github.com/agent-code-dev/agent-code

---

📜 License

Agent Code has component-specific licenses.

Component| License
Agent Code application| MIT
Separate registry backend ("server/")| AGPL-3.0-only

See:

- "Application LICENSE" (LICENSE)
- "Server LICENSE" (server/LICENSE)

The server's AGPL license does not replace the application's MIT license.

---

<div align="center"><img src="src/agent_code/data/icons/agent-code.png" width="64" alt="Agent Code">⚡ Agent Code 2.0

Your AI coding agent. Your tools. Your environment.

"GitHub" (https://github.com/agent-code-dev/agent-code) · "PyPI" (https://pypi.org/project/agent-code/) · "Website" (https://agent-code-dev.github.io)

<sub>Built with Python. Designed for extensibility.</sub>

</div>
