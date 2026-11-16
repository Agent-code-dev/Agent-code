# WebUI settings and Skills Store

The WebUI and authenticated `agent-code server` use the same frontend and `AgentWebAPI`.

## Settings

Settings are split into fixed-height category panels: Provider & models, Permissions, Accounts & sync, Link to SSH, Sandbox, Core mode, Browser, and Interface. Switching categories replaces the visible panel; the desktop Settings page does not use a page-level vertical scrollbar.

The settings bridge persists values through the existing Agent Code configuration. API keys can be entered one per line or comma-separated; leaving the field empty preserves existing credentials. Provider profiles continue to use the existing local profile store.

SSH passwords are only passed to the live connection attempt and are not saved. SSH host keys must already be present in the operating-system `known_hosts` file; unknown hosts are rejected rather than automatically trusted.

## Native Skills Store

The **Skills Store** is separate from the Add-on Store. It uses the existing Skills Store account configuration and HTTPS API. The WebUI supports sign-in, account registration, search, installed/mine/flagged filters, skill detail inspection, safety warnings, and installation.

Downloaded archives are staged and validated with the existing safe ZIP extraction helper before replacing an installed skill. A skill must contain `skill.py`; unsafe paths, symbolic links, oversized archives, and malformed packages are rejected. The agent tool registry is reloaded after installation.
