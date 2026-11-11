# Agent Code security controls

## Prompt-injection handling

Agent Code treats repository files, web pages, search snippets, terminal output, tool results, and Sub-Agent reports as untrusted data. They can provide facts, but cannot override the user's task, system rules, or permission settings. Tool results are explicitly marked as untrusted when added to model context. This is defense in depth, not a guarantee that every malicious instruction can be detected.

## Blacklist files using aliases

Blacklist files are configured by alias, so paths can be moved without changing Agent Code source code. Add entries to the user configuration (`agent_config.json`):

```json
{
  "security_blacklist_files": {
    "project-private": ".agent-code/blacklist.txt",
    "personal-secrets": "~/.config/agent-code/blocked-files.txt"
  },
  "security_blacklist_aliases": ["project-private", "personal-secrets"]
}
```

Each active file contains one glob pattern per line. Blank lines and lines beginning with `#` or `;` are ignored. Examples:

```text
.env
.env.*
**/secrets/**
**/*.pem
**/id_rsa*
```

The file tools deny direct access to blacklisted paths; glob and grep omit matching files. Shell checks are best-effort because shell syntax, aliases, variables, and scripts can obscure file access. Use Podman for stronger isolation; do not treat blacklist rules as a sandbox.

## Host shell opt-in

The unrestricted host shell is OFF by default. Enable **Desktop Settings → Permissions → Enable unrestricted host shell** to allow host commands, with a per-command approval prompt. Host commands run as the current logged-in OS account; Agent Code does not acquire root/Administrator rights automatically.

## Ultra Unrestricted Agent Code

**Ultra Unrestricted Agent Code** is a separate, OFF-by-default setting in Desktop Settings → Permissions and the Textual TUI → Settings → Execution. Enabling it requires an explicit warning confirmation. While active, Agent Code automatically approves its available tools, enables the host shell and background shell, and permits direct file tools and shell working directories outside the workspace. It disables per-action approval prompts. The setting is persisted and can be switched off from the same settings page.

This mode is deliberately powerful and can overwrite or delete personal files, install software, change user-level settings, and run arbitrary commands within the current OS account's permissions. It does not bypass OS access controls, sudo passwords, UAC, or other privilege boundaries; it cannot make a normal user process an administrator. Active blacklist rules remain in force as a defense-in-depth measure, although shell blacklist checks are best-effort and are not a security sandbox. Plan Mode remains read-only. Podman is not used for shell execution while Ultra mode is active because the mode explicitly targets the host. Use a separate OS account or a disposable VM for experiments that may damage data.
