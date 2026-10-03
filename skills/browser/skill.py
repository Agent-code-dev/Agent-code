"""Headless Chromium browser skill via DrissionPage."""
from DrissionPage import ChromiumPage, ChromiumOptions

_page = None


def _get_page():
    global _page
    if _page is None:
        opts = (ChromiumOptions()
                .headless(True)
                .set_argument("--no-sandbox")
                .set_argument("--disable-dev-shm-usage")
                .set_argument("--disable-blink-features=AutomationControlled"))
        _page = ChromiumPage(opts)
    return _page


def navigate(url):
    if not isinstance(url, str) or not url.strip():
        return "ERROR: url required"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        page = _get_page()
        page.get(url, timeout=30)
        return "OK title={!r} url={}".format(page.title, page.url)
    except Exception as e:
        return "ERROR: " + str(e)


def snapshot(max_chars=6000):
    try:
        page = _get_page()
        body = page.ele("tag:body", timeout=5)
        text = body.text if body else page.html
        return (text or "(empty)")[:int(max_chars)]
    except Exception as e:
        return "ERROR: " + str(e)


def click(selector):
    try:
        page = _get_page()
        ele = page.ele(selector, timeout=5)
        if not ele:
            return "NOT_FOUND: " + str(selector)
        ele.click()
        return "OK"
    except Exception as e:
        return "ERROR: " + str(e)


def type_text(selector, text):
    try:
        page = _get_page()
        ele = page.ele(selector, timeout=5)
        if not ele:
            return "NOT_FOUND: " + str(selector)
        try:
            ele.clear()
        except Exception:
            pass
        ele.input(str(text))
        return "OK"
    except Exception as e:
        return "ERROR: " + str(e)


def links(limit=30):
    try:
        page = _get_page()
        out = []
        for a in page.eles("tag:a")[:int(limit)]:
            t = (a.text or "").strip()[:80]
            h = a.attr("href") or ""
            if t and h:
                out.append("{} -> {}".format(t, h))
        return "\n".join(out) or "(no links)"
    except Exception as e:
        return "ERROR: " + str(e)


def scroll(pixels=800):
    try:
        page = _get_page()
        page.scroll.down(int(pixels))
        return "OK scrolled {}px".format(pixels)
    except Exception as e:
        return "ERROR: " + str(e)


def close():
    global _page
    try:
        if _page is not None:
            _page.quit()
    except Exception:
        pass
    _page = None
    return "OK"


SKILL = {
    "name": "browser",
    "description": "Headless Chromium via DrissionPage: navigate, read, click, type, scroll.",
    "version": "1.0.0",
    "author": "agent-code",
}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "browser_navigate",
        "description": "Open a URL in the headless browser.",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "browser_snapshot",
        "description": "Return visible text of the current page.",
        "parameters": {"type": "object",
                       "properties": {"max_chars": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "browser_click",
        "description": "Click an element by CSS selector.",
        "parameters": {"type": "object",
                       "properties": {"selector": {"type": "string"}},
                       "required": ["selector"]}}},
    {"type": "function", "function": {
        "name": "browser_type",
        "description": "Type text into an input identified by CSS selector.",
        "parameters": {"type": "object",
                       "properties": {"selector": {"type": "string"},
                                      "text": {"type": "string"}},
                       "required": ["selector", "text"]}}},
    {"type": "function", "function": {
        "name": "browser_links",
        "description": "List clickable links on the current page.",
        "parameters": {"type": "object",
                       "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "browser_scroll",
        "description": "Scroll the page down by N pixels.",
        "parameters": {"type": "object",
                       "properties": {"pixels": {"type": "integer"}}}}},
]

TOOL_CALLABLES = {
    "browser_navigate": navigate,
    "browser_snapshot": snapshot,
    "browser_click":    click,
    "browser_type":     type_text,
    "browser_links":    links,
    "browser_scroll":   scroll,
}


def _cmd_close(args, log):
    log(close(), "dim")


COMMANDS = {
    "browser-close": {"handler": _cmd_close,
                      "description": "Close the headless browser."},
}
