"""public_api skill — search free public APIs and call them."""

import os
import json
from pathlib import Path

SKILL = {
    "name": "public_api",
    "description": (
        "Search free public APIs (weather, crypto, news, animals, etc.) from "
        "the public-api-lists repo (730+ APIs, 48 categories) and call them."
    ),
}

_CATALOG = Path(os.environ.get("TEMP", "/tmp")) / "public_apis.json"
_CATALOG_URL = "https://public-api-lists.github.io/public-api-lists/api/all.json"


def _extract_entries(data):
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if isinstance(data, dict):
        for k in ("data", "apis", "entries", "items", "results"):
            if k in data and isinstance(data[k], list):
                return [e for e in data[k] if isinstance(e, dict)]
        collected = []
        for v in data.values():
            if isinstance(v, list):
                collected.extend(x for x in v if isinstance(x, dict))
        return collected
    return []


def _catalog():
    if not _CATALOG.exists() or _CATALOG.stat().st_size == 0:
        import urllib.request
        with urllib.request.urlopen(_CATALOG_URL, timeout=30) as r:
            _CATALOG.write_bytes(r.read())
    raw = json.loads(_CATALOG.read_text(encoding="utf-8"))
    return _extract_entries(raw)


def search_apis(query="", category="", no_auth_only=True, limit=10):
    try:
        entries = _catalog()
    except Exception as e:
        return f"ERROR: {e}"
    if not entries:
        return "ERROR: catalog empty or unexpected shape"

    q, c = (query or "").lower().strip(), (category or "").lower().strip()
    hits = []
    for e in entries:
        auth = str(e.get("auth", "")).lower()
        if no_auth_only and auth not in ("no", "", "none", "false"):
            continue
        if c and str(e.get("category", "")).lower() != c:
            continue
        if q and q not in str(e.get("name", "")).lower() \
             and q not in str(e.get("description", "")).lower():
            continue
        hits.append(e)
        if len(hits) >= limit:
            break
    if not hits:
        return "No matches."
    return "\n".join(
        f"{e.get('name','?')} | auth={e.get('auth','?')} | {e.get('link','?')}"
        for e in hits
    )


def call_api(url, max_chars=4000):
    if not url.startswith(("http://", "https://")):
        return "ERROR: bad url"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")[:max_chars] or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_apis",
        "description": "Search free public APIs.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "category": {"type": "string"},
            "no_auth_only": {"type": "boolean"},
            "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "call_api",
        "description": "GET a public API URL and return the body.",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
]

TOOL_CALLABLES = {
    "search_apis": search_apis,
    "call_api": call_api,
}