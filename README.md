Agent Code 2.0

An extensible, open-source AI coding agent for your desktop.

Agent Code is a Python-based AI coding agent designed to help developers understand, create, modify, and manage software projects through an AI-powered desktop application.

Instead of locking developers into a fixed collection of capabilities, Agent Code provides multiple extension systems that allow users and developers to customize the agent and the application itself.

Bring your own AI provider, extend the agent with Skills, connect external tools through MCP, and customize the application using Add-ons.

Open source. Extensible. Provider-independent.

---

Table of Contents

- "Overview" (#overview)
- "Features" (#features)
- "How Agent Code Works" (#how-agent-code-works)
- "AI Providers" (#ai-providers)
- "Execution Environments" (#execution-environments)
- "Skills System" (#skills-system)
- "Add-ons System" (#add-ons-system)
- "MCP Integration" (#mcp-integration)
- "Agent Modes" (#agent-modes)
- "Permissions and Security" (#permissions-and-security)
- "Installation" (#installation)
- "Running Agent Code" (#running-agent-code)
- "Configuration" (#configuration)
- "Project Structure" (#project-structure)
- "Creating Extensions" (#creating-extensions)
- "Development" (#development)
- "Troubleshooting" (#troubleshooting)
- "Roadmap" (#roadmap)
- "Contributing" (#contributing)
- "License" (#license)

---

Overview

Most AI coding assistants provide a predefined set of tools and workflows.

Agent Code takes a more extensible approach.

It is designed around three independent extension systems:

System| Purpose
Skills| Give the AI agent additional tools and capabilities.
Add-ons| Extend or customize the Agent Code application itself.
MCP| Connect the agent to external MCP-compatible tool servers.

These systems solve different problems and are not interchangeable.

For example:

- A Skill can provide an additional filesystem or browser capability.
- An Add-on can introduce a new application feature or customize supported parts of the interface.
- MCP can connect the agent to tools provided by an external service.

The result is a coding agent that can evolve without requiring every new capability to become part of the application core.

Features

AI Coding Agent

- AI-powered project assistance.
- File creation and modification.
- Tool-calling workflows.
- Project-aware development.
- Multi-step task execution.
- Planning and implementation workflows.
- Error recovery and debugging assistance.
- Activity tracking.
- Checkpoints and project recovery functionality.

Desktop Application

Agent Code uses Python and CustomTkinter to provide a native desktop-style interface.

The application is designed to support different operating systems without requiring an Electron-based application runtime.

Features include:

- Chat-based interface.
- Markdown-rendered responses.
- Project management.
- Activity visibility controls.
- Model selection.
- Provider configuration.
- Extension management.
- Integrated development workflows.

Extensibility

Agent Code supports three distinct extension mechanisms:

- Native Python Skills.
- Application Add-ons.
- External MCP servers.

Developers can extend the platform without having to rebuild the entire application.

Developer Tools

- Python-based extension development.
- Configurable AI providers.
- Local execution.
- Sandbox execution.
- SSH execution.
- Project context.
- Command execution.
- Configurable permissions.

---

How Agent Code Works

Agent Code follows a tool-based architecture.

The AI model receives a system prompt, available tool definitions, and relevant project context.

When the model requests an action, Agent Code resolves the requested tool through its tool registry and executes it using the appropriate execution environment.

The result is returned to the AI model, allowing it to continue the task.

Conceptually:

                  USER
                    |
                    v
              Agent Code UI
                    |
                    v
                AI Agent
                    |
          +---------+---------+
          |         |         |
          v         v         v
        Skills    MCP     Core Tools
          |         |         |
          +---------+---------+
                    |
                    v
            Execution Layer
                    |
          +---------+---------+
          |         |         |
          v         v         v
        Local    Sandbox     SSH
                    |
                    v
              Tool Results
                    |
                    v
                 AI Agent
                    |
                    v
                Response

This is a conceptual overview rather than a complete representation of every internal component.

---

AI Providers

Agent Code is designed to work with multiple AI providers rather than requiring users to use one specific model service.

The project supports an OpenAI-compatible client architecture.

Depending on the provider and endpoint, users can configure:

- API keys.
- API endpoints.
- Model identifiers.
- Provider settings.
- Model selection.

Bring Your Own Key (BYOK)

Users can connect their own provider credentials.

This gives developers control over:

- Which provider they use.
- Which model they select.
- Their API spending.
- Their provider account.

Agent Code does not require a mandatory recurring AI subscription.

However, external AI providers may charge for API usage or impose their own account requirements.

Provider Configuration

Provider configuration is managed through the application.

Supported configurations depend on the provider's API compatibility and the capabilities implemented by Agent Code.

---

Execution Environments

Agent Code separates tool capabilities from where those tools execute.

A Skill or tool may use a different execution location depending on its requirements.

Local Execution

Execute supported operations on the user's computer.

Useful when a task requires:

- Access to local project files.
- Local development tools.
- Locally installed software.
- Local configuration and credentials.

Sandbox Execution

Execute supported commands inside a sandbox environment.

Useful for isolating development tasks from the host environment.

Sandbox availability and capabilities depend on the configured runtime.

SSH Execution

Connect to a remote machine and execute supported operations remotely.

Useful when working with:

- Remote development machines.
- Hosted environments.
- Remote project directories.
- Linux servers.

The execution location is separate from the agent's planning and implementation modes.

---

Skills System

Skills extend what the AI agent can do.

A Skill can provide:

- Additional tools.
- Tool schemas.
- Python functions.
- Agent-specific commands.
- Skill metadata.
- Instructions describing its capabilities.

Skills are loaded using Agent Code's native loader architecture.

Skill Structure

A typical Skill directory looks like this:

skills/
└── example/
    ├── skill.py
    └── skill.md

The Python module exports the required tool definitions and callable functions.

Conceptually:

SKILL = {
    "name": "example",
    "description": "An example Agent Code skill"
}

TOOL_SCHEMAS = [
    # Tool definitions
]

TOOL_CALLABLES = {
    # Tool implementations
}

COMMANDS = {
    # Optional agent-specific commands
}

"COMMANDS" is optional.

The exact function signatures and schema requirements are defined by the native Skills loader.

Skill Commands

Skills can expose commands that are handled by the agent's command dispatcher.

These commands are not automatically ordinary operating-system shell commands.

This distinction allows Skills to provide specialized agent workflows.

Skill Execution Location

Skills can select an appropriate execution environment for supported operations.

For example, a Skill might need local access to a configuration file while using a sandbox for an isolated development operation.

---

Add-ons System

Add-ons extend Agent Code itself.

This is different from Skills, which extend the AI agent's available capabilities.

The Add-ons architecture is intended to allow third-party developers to create extensions that customize supported parts of the application.

Possible extension areas include:

- User interface components.
- Additional application pages.
- Buttons and actions.
- Application functionality.
- Supported services.
- Provider integrations.
- Server-related integrations.
- Application workflows.

The intention is to make Agent Code extensible beyond themes and visual customization.

Add-ons vs Skills

Capability| Skills| Add-ons
Give the AI additional tools| Yes| Not their primary purpose
Add agent commands| Yes| Not their primary purpose
Extend application UI| No| Yes
Add application pages| No| Yes
Customize supported application functionality| No| Yes
Integrate external services| Through agent tools| Through supported application extensions

Add-ons operate within the extension interfaces and capabilities exposed by Agent Code.

They should not be assumed to have unrestricted access to every internal application component.

---

MCP Integration

Agent Code supports Model Context Protocol (MCP) integration.

MCP allows the agent to communicate with external tool servers and use capabilities exposed through those servers.

This provides another way to extend the agent without implementing every integration as a native Skill.

Skills vs MCP

Skills| MCP
Native Agent Code extensions| External tool-server integration
Python-based| MCP protocol-based
Loaded through the Skills loader| Connected through the MCP manager
Can expose native commands| Exposes tools provided by MCP servers

Both systems can coexist.

---

Agent Modes

Agent Code separates how the agent approaches a task from where its tools execute.

Plan Mode

Plan Mode focuses on understanding a task and preparing an implementation approach.

It is useful for:

- Understanding project requirements.
- Reviewing existing code.
- Identifying files that may need changes.
- Breaking work into smaller tasks.
- Preparing an implementation plan.

Build Mode

Build Mode focuses on carrying out development tasks.

It can use available tools to:

- Create files.
- Modify existing files.
- Execute supported commands.
- Investigate errors.
- Implement planned changes.

Core Mode

Core Mode provides a lightweight operating configuration without additional Skills.

It is intended to keep the agent's available capabilities minimal.

Core Mode focuses on essential operations such as file creation, shell execution, and CURL-based operations.

It does not replace the regular Skills architecture.

---

Permissions and Security

Agent Code provides configurable execution permissions.

The permission model is intended to balance convenience and control.

Available permission behavior includes:

- Safe.
- Normal.
- Auto.

The precise permissions depend on the operation and execution environment.

Users should review the permissions granted to Skills, Add-ons, MCP servers, and execution environments before using third-party extensions.

Security Recommendations

- Keep API keys private.
- Never commit configuration files containing credentials.
- Review third-party Skills before installing them.
- Only install Add-ons from sources you trust.
- Review MCP server configurations.
- Be careful when allowing commands to execute automatically.
- Use sandbox execution when appropriate.
- Avoid granting unnecessary permissions.

Agent Code is an extensible development tool. Extensions and external services may introduce their own security risks.

---

Installation

Requirements

- Python 3.10 or newer.
- An operating system supported by Python and the required dependencies.
- Internet access for installing dependencies and communicating with remote AI providers.
- An AI provider configuration.

Some optional features require additional software or system dependencies.

Install from PyPI

Install the published package:

python -m pip install agent-code

Upgrade:

python -m pip install --upgrade agent-code

Install from Source

Clone the repository:

git clone https://github.com/agent-code-dev/agent-code.git

cd agent-code

Install in editable mode:

python -m pip install -e .

For development dependencies, install the appropriate development requirements defined by the project.

---

Running Agent Code

The Python package provides application entry points.

Run:

python -m agent_code

For command-line help:

python -m agent_code --help

The exact available commands depend on the installed version.

---

Configuration

Agent Code stores its application configuration through its configuration management system.

Configuration includes settings such as:

- AI provider.
- API endpoint.
- Model selection.
- API credentials.
- Application preferences.
- Execution settings.

Use the application's settings interface whenever possible.

Do not publish personal API credentials or private configuration files.

---

Project Structure

The main application uses a "src"-based Python package layout.

agent-code/
│
├── src/
│   └── agent_code/
│       ├── __init__.py
│       ├── __main__.py
│       ├── agent.py
│       ├── loader.py
│       ├── addons.py
│       ├── advanced_features.py
│       ├── mcp_manager.py
│       ├── paths.py
│       ├── projects.py
│       ├── skill_manager.py
│       ├── doctor.py
│       ├── cli.py
│       ├── tui.py
│       │
│       └── data/
│           ├── icons/
│           └── skills/
│
├── server/
│
├── tests/
│
├── docs/
│   ├── index.html
│   ├── skills.html
│   └── addons.html
│
├── ADDON-DEVELOPMENT.md
├── RELEASE-NOTES-2.0.0.md
├── README.md
├── LICENSE
├── pyproject.toml
└── setup.cfg

The project may contain additional files and directories as development continues.

---

Creating Extensions

Agent Code is designed to be extensible.

Developers interested in contributing extensions should start with the documentation.

Skills Development

Read the Skills documentation:

"docs/skills.html"

Add-on Development

Read:

"ADDON-DEVELOPMENT.md"

And the Add-ons documentation:

"docs/addons.html"

MCP Development

Refer to the MCP integration architecture and the official MCP specification when developing external MCP-compatible servers.

---

Development

Clone the project:

git clone https://github.com/agent-code-dev/agent-code.git

cd agent-code

Install the project:

python -m pip install -e .

Run the test suite:

python -m pytest -q

Some tests may require optional dependencies or environment-specific components.

---

Troubleshooting

Python version

Check your Python version:

python --version

Agent Code requires Python 3.10 or newer.

Installation problems

Upgrade the packaging tools:

python -m pip install --upgrade pip setuptools wheel

Then reinstall:

python -m pip install --upgrade agent-code

AI provider errors

Check:

- Your API key.
- The configured endpoint.
- The selected model identifier.
- Provider availability.
- Your provider account's usage limits.

Errors from external providers do not necessarily indicate an Agent Code application failure.

Browser problems

Check that a supported browser is installed and that its executable can be detected or configured.

Execution environment problems

Verify that the selected local, sandbox, or SSH environment is installed, accessible, and correctly configured.

---

Roadmap

The project is intended to evolve around several areas:

- Improving the AI agent's reliability.
- Reducing unnecessary token consumption.
- Improving provider compatibility.
- Expanding the Skills ecosystem.
- Expanding Add-on development capabilities.
- Improving MCP integration.
- Improving sandbox and remote execution.
- Improving cross-platform compatibility.
- Improving the desktop experience.
- Strengthening extension security.

The roadmap is subject to change as the project develops.

---

Contributing

Contributions are welcome.

You can contribute by:

- Reporting bugs.
- Suggesting improvements.
- Submitting pull requests.
- Creating Skills.
- Developing Add-ons.
- Improving documentation.
- Testing compatibility.
- Reviewing the architecture.

Before submitting significant changes, please open an issue to discuss the proposed implementation.

---

Licensing

The Agent Code application is licensed under the MIT License.

The separate server component has its own license:

AGPL-3.0-only

See the relevant license files:

- "LICENSE"
- "server/LICENSE"

These licenses apply to their respective components.

---

Links

- GitHub Repository: https://github.com/agent-code-dev/agent-code
- PyPI Package: https://pypi.org/project/agent-code/
- Project Website: https://agent-code.page.gd

---

Agent Code 2.0

Build with AI. Extend without limits.

An open-source coding agent designed to give developers control over their AI tools, extensions, and development workflows.
