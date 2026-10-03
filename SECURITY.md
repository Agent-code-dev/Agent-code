# Security Policy

## Reporting a vulnerability

Open a private advisory at:
https://github.com/Agent-code-dev/Agent-code/security/advisories/new

Do not open a public issue for anything that could be exploited.

## What the agent sandboxes

- **Shell** - allowlist of commands, `shell=False`, cwd forced to `workspace/`,
  no pipes, redirects, `;`, `&`, `&&`, or absolute paths outside the workspace.
- **Filesystem** - every path resolved and validated against `workspace/`.
- **Browser** - headless Chromium in a throwaway profile.
- **Skills** - each tool call runs in a subprocess with `-I -S` (isolated,
  no user site) and a hard timeout. Crashing or hanging a skill cannot take
  down the agent.
- **Skill loading** - every skill is static-scanned before import. Skills
  scoring >= 6/10 are refused. Critical patterns (credential theft, hidden
  unicode, base64 blobs, crypto miners) score 10.
- **Secrets** - API keys matching 20+ patterns are redacted from shell
  output, audit logs, and chat history before they reach the LLM.
- **Registry** - the local dashboard checks Origin/Referer, enforces per-IP
  rate limits, caps request bodies, refuses zip entries with `..` or NTFS
  streams, and guards against zip bombs.

## What the agent does NOT sandbox

- **`python` and `node` are in the shell allowlist.** The agent can read
  arbitrary files. Remove them from `ALLOWED_CMDS` if that matters.
- **`curl` and `wget` are allowed.** The agent can POST local data to
  remote servers.
- **Skills are arbitrary Python.** Installing a skill means trusting its
  author. The static scanner is a first line of defense, not a proof.
- **Prompt injection via web content.** A malicious page can steer the
  agent. Use permission mode `ask` or `readonly` on untrusted targets.

## Recommended deployment

For untrusted use, run the agent inside a container with `workspace/`
bind-mounted and no network access to internal services.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x   | yes       |
| 0.9.x   | no        |
