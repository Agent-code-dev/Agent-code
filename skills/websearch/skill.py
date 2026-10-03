"""websearch skill — DuckDuckGo search without an API key."""
import html
import json
import re
import urllib.parse
import urllib.request

SKILL = {
    "name": "websearch",
    "description": "Search the web via DuckDuckGo and return top results.",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentCode/1.0"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def search(query: str, limit: int = 8) -> str:
    q = urllib.parse.quote_plus(query)
    html_body = _fetch(f"https://html.duckduckgo.com/html/?q={q}")
    results = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html_body, re.DOTALL,
    )
    lines = []
    for i, (href, title) in enumerate(results[:limit], 1):
        url = urllib.parse.unquote(href)
        if "uddg=" in url:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = qs.get("uddg", [url])[0]
        title = re.sub(r"<[^>]+>", "", title)
        title = html.unescape(title).strip()
        lines.append(f"{i}. {title}\n   {url}")
    if not lines:
        return "No results."
    return "\n".join(lines)


TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web via DuckDuckGo. Returns title + URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}]

TOOL_CALLABLES = {"web_search": search}