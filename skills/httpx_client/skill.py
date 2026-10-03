"""httpx_client skill — HTTP client with JSON, retries, and headers."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SKILL = {
    "name": "httpx_client",
    "description": "HTTP client: GET/POST JSON with retries and custom headers.",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentCode/1.0"


def _do(method, url, body=None, headers=None, timeout=20, retries=2):
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, str)) else (body.encode() if isinstance(body, str) else body)
        hdrs["Content-Type"] = hdrs.get("Content-Type", "application/json")

    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, method=method.upper(), headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body_bytes = r.read()
                ctype = r.headers.get("Content-Type", "")
                text = body_bytes.decode("utf-8", errors="replace")
                if "json" in ctype.lower():
                    try:
                        return f"HTTP {r.status}\n" + json.dumps(json.loads(text), indent=2)[:6000]
                    except Exception:
                        pass
                return f"HTTP {r.status}\n{text[:6000]}"
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            return f"HTTP {e.code}\n{text[:4000]}"
        except Exception as e:
            last = e
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
    return f"ERROR: {type(last).__name__}: {last}"


def http_get(url, headers=None, timeout=20):
    return _do("GET", url, None, headers, timeout)


def http_post_json(url, body, headers=None, timeout=20):
    return _do("POST", url, body, headers, timeout)


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "http_get",
        "description": "HTTP GET. Returns status line plus body (JSON pretty-printed).",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"},
                                      "headers": {"type": "object"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "http_post_json",
        "description": "HTTP POST with a JSON body.",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"},
                                      "body": {"type": "object"},
                                      "headers": {"type": "object"}},
                       "required": ["url", "body"]}}},
]

TOOL_CALLABLES = {
    "http_get": http_get,
    "http_post_json": http_post_json,
}