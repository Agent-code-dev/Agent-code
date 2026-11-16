# Agent Code Server

Agent Code Server runs the same Agent Code engine and a separate authenticated WebUI over HTTP, so another computer, tablet, or phone can connect using a browser. The local desktop application remains CustomTkinter. It works on Linux, Windows, and macOS wherever the supported Python runtime and dependencies are available.

## Start

```bash
agent-code server
```

The server binds to `0.0.0.0:8765` by default. Open the printed Local URL on the host computer, or a printed Network URL from another device on the same trusted LAN. To choose another address or port:

```bash
agent-code server --host 0.0.0.0 --port 9000
```

The first start generates a strong password and prints it once in the server startup output. The username defaults to `admin`. The password is stored only as a salted PBKDF2-HMAC-SHA256 verifier in the private Agent Code configuration; plaintext passwords are never written to chat transcripts or log files.

## Set your own credentials

Set a username and interactively choose a password (minimum 12 characters):

```bash
agent-code server --username myuser --set-password
```

You can also provide the password through `AGENT_CODE_SERVER_PASSWORD` for scripted deployments. Avoid putting passwords directly on command lines because they may be visible in process listings or shell history.

Credentials are shared across server starts on the same Agent Code profile. Use `--set-password` to rotate the password. Use `--global` if you want the server to use the global `~/.agent-code` workspace and data paths:

```bash
agent-code server --global
```

## Security notes

- Web UI routes and API calls require a login session. Session cookies are HttpOnly and SameSite=Strict, and expire after 12 hours.
- Login attempts are rate-limited per client address.
- Passwords are salted and hashed; session tokens are random and held in memory.
- The server gives authenticated browser clients access to the Agent Code engine, workspace, configured provider, installed Skills, Add-ons, and MCP servers. Treat it like remote access to your logged-in user account.
- The default HTTP listener is intended for a trusted LAN or VPN. **Do not expose the plain HTTP port directly to the public internet.** For remote internet access, use a VPN or put the server behind a properly configured HTTPS reverse proxy, firewall it, and restrict who can connect. If the reverse proxy uses a DNS hostname, add that exact hostname to `AGENT_CODE_SERVER_ALLOWED_HOSTS` (comma-separated) in the server environment; IP addresses and localhost are accepted by default.
- The server is single-workspace/single-agent: connected browser clients share the same conversation and running task. Do not run multiple independent agents against the same workspace at once.
- Stop the server with Ctrl+C.

## Lightweight installs

The server does not depend on a desktop GUI and can run on headless machines:

```bash
pip install "agent-code[lite]"
agent-code server
```

The full `pip install agent-code` also includes server support.
