# Agent Code Skill Registry Server

Standalone HTTP service for the Agent Code skill registry. This directory is licensed under GNU AGPL v3.0; the main Agent Code application remains MIT-licensed.

## Run

Set configuration through environment variables or a `.env` file next to `skill-server.py`, then run:

```bash
python skill-server.py --host 127.0.0.1 --port 8000
```

For a public deployment, use a TLS reverse proxy, set a strong `ADMIN_TOKEN`, configure the AI review provider, and apply rate limiting at the proxy. The AI review is advisory and must not be treated as a guarantee that a skill is safe.
