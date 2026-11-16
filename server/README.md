# Agent Code Skill Registry Server

Standalone HTTP service for the Agent Code skill registry. This directory is licensed under GNU AGPL v3.0; the main Agent Code application remains MIT-licensed.

## Run

Set configuration through environment variables or a `.env` file next to `skill-server.py`, then run:

```bash
python skill-server.py --host 127.0.0.1 --port 8000
```

For a public deployment, use a TLS reverse proxy, set a strong `ADMIN_TOKEN`, configure the AI review provider, and apply rate limiting at the proxy. The AI review is advisory and must not be treated as a guarantee that a skill is safe.

## Application Add-on catalogue

The same service can host trusted Agent Code application add-ons separately from executable Skills. Add-ons are **admin-published only**; the admin is responsible for reviewing the Python source before publishing. Public clients can browse and download the packages:

- `GET /addons?search=...` — catalogue metadata, including SHA-256.
- `GET /addons/{name}` — one add-on's metadata.
- `GET /addons/{name}/download` — ZIP archive with `addon.json` and `addon.py`.
- `POST /addons` — admin-only publish; requires `X-Admin-Token` and JSON fields `name`, `version`, `description`, `author`, and base64 `zip_b64`.
- `DELETE /addons/{name}` — admin-only removal.

The upload endpoint validates ZIP paths, symlinks, entry count, expanded size, and the add-on manifest. It does not execute or AI-review add-on Python. Do not publish code unless it has been manually reviewed. Configure `MAX_ADDON_UPLOAD_BYTES` to change the compressed upload limit (default 32 MiB).
