"""Cross-platform browser skill with deterministic fallback priority.

Automatic priority: Chrome/Chromium (DrissionPage), Firefox (Selenium/WebDriver),
then an explicit WebDriver setup error with installation guidance. Set
AGENT_CODE_BROWSER=chrome or AGENT_CODE_BROWSER=firefox to override detection.
Selenium Manager may download a driver on first launch; obtain user approval first.
"""
import json
import os
import shutil
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    ChromiumPage = ChromiumOptions = None

_page = None
_browser_kind = None

def _browser_settings():
    """Read the shared Agent Code browser override without importing the GUI."""
    try:
        from agent_code.paths import user_config_file
        cfg_path = user_config_file()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        raw_path = str(cfg.get("browser_executable_path", "") or "").strip()
        path = os.path.abspath(os.path.expanduser(raw_path)) if raw_path else ""
        kind = str(cfg.get("browser_type", "auto") or "auto").strip().lower()
        if kind not in ("auto", "chromium", "firefox"):
            kind = "auto"
        return path, kind
    except Exception:
        return "", "auto"

def _firefox_binary():
    """Find Firefox in DEB, Snap, Flatpak, tarball, or PATH installations.

    Return the best launcher/binary hint; launchability is validated separately by Selenium.
    """
    import subprocess
    configured_path, configured_kind = _browser_settings()
    if configured_path and configured_kind in ("auto", "firefox") and "firefox" in os.path.basename(configured_path).lower():
        return configured_path if os.path.isfile(configured_path) and os.access(configured_path, os.X_OK) else None
    if configured_path and configured_kind == "firefox":
        return configured_path if os.path.isfile(configured_path) and os.access(configured_path, os.X_OK) else None
    # Prefer actual packaged binaries over wrapper scripts such as /usr/bin/firefox.
    candidates = (
        "/usr/lib/firefox/firefox", "/usr/lib/firefox/firefox-bin",
        "/usr/lib/firefox-esr/firefox-esr", "/usr/lib/firefox-esr/firefox",
        "/usr/lib64/firefox/firefox", "/opt/firefox/firefox",
        "/snap/firefox/current/usr/lib/firefox/firefox",
        "/snap/firefox/current/usr/lib/firefox/firefox-bin",
        "/snap/bin/firefox", "/usr/bin/firefox-esr", "/usr/bin/firefox",
        "/var/lib/flatpak/exports/bin/org.mozilla.firefox",
        os.path.expanduser("~/.local/share/flatpak/exports/bin/org.mozilla.firefox"),
        "/Applications/Firefox.app/Contents/MacOS/firefox",
    )
    for candidate in candidates:
        try:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        except OSError:
            continue
    for name in ("firefox-esr", "firefox", "mozilla-firefox"):
        found = shutil.which(name)
        if found:
            # Preserve Snap launchers; resolving /snap/bin/firefox can point at snap itself.
            if found.startswith("/snap/bin/"):
                return found
            try:
                resolved = os.path.realpath(found)
                return resolved if os.path.isfile(resolved) and os.access(resolved, os.X_OK) else found
            except OSError:
                return found
    # Package metadata can establish that Firefox is installed even if PATH is unusual.
    if shutil.which("snap"):
        try:
            result = subprocess.run([shutil.which("snap"), "list", "firefox"], capture_output=True, text=True, timeout=4)
            if result.returncode == 0:
                for candidate in candidates:
                    if candidate.startswith("/snap/") and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        return candidate
                if os.path.exists("/snap/bin/firefox"):
                    return "/snap/bin/firefox"
        except Exception:
            pass
    if shutil.which("flatpak"):
        try:
            result = subprocess.run([shutil.which("flatpak"), "info", "org.mozilla.firefox"], capture_output=True, text=True, timeout=4)
            if result.returncode == 0:
                for candidate in candidates:
                    if "flatpak" in candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        return candidate
                return "flatpak:org.mozilla.firefox"
        except Exception:
            pass
    return None


def _requested_browser():
    """Prefer Chrome/Chromium when actually launchable; otherwise detect Firefox broadly."""
    configured_path, configured_kind = _browser_settings()
    choice = configured_kind if configured_kind != "auto" else os.environ.get("AGENT_CODE_BROWSER", "auto").strip().lower()
    if configured_path and os.path.isfile(configured_path) and os.access(configured_path, os.X_OK) and choice == "auto":
        choice = "firefox" if "firefox" in os.path.basename(configured_path).lower() else "chromium"
    if choice in ("firefox", "mozilla"):
        return "firefox" if _firefox_binary() else "unavailable"
    if choice in ("chromium", "chrome", "edge"):
        return "chromium"
    chromium_names = ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser", "msedge")
    chromium_paths = ("/snap/bin/chromium", "/usr/bin/chromium", "/usr/bin/chromium-browser",
                      "/usr/bin/google-chrome", "/opt/google/chrome/chrome",
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    has_chromium = bool(configured_path and choice in ("chromium", "chrome", "edge")) or any(shutil.which(name) for name in chromium_names) or any(
        os.path.isfile(p) and os.access(p, os.X_OK) for p in chromium_paths)
    if ChromiumPage is not None and has_chromium:
        return "chromium"
    if _firefox_binary():
        return "firefox"
    # Do not choose Chromium merely because DrissionPage is installed: on Firefox-only
    # systems that made the agent try a browser that does not exist.
    if has_chromium and ChromiumPage is not None:
        return "chromium"
    return "unavailable"


def _is_firefox():
    return _browser_kind == "firefox"


def _get_page():
    global _page, _browser_kind
    if _page is None:
        _browser_kind = _requested_browser()
        if _browser_kind == "unavailable":
            return None
        if _browser_kind == "firefox":
            try:
                from selenium import webdriver
                from selenium.webdriver.firefox.options import Options
            except ImportError:
                return None
            options = Options()
            options.add_argument("-headless")
            # Use a discovered native launcher explicitly where PATH aliases are absent.
            configured_path, _configured_kind = _browser_settings()
            binary = configured_path if configured_path and "firefox" in os.path.basename(configured_path).lower() else _firefox_binary()
            if binary and not binary.startswith("flatpak:"):
                # Snap launchers are wrappers, but Selenium can still use them as a binary hint.
                options.binary_location = binary
            elif binary and binary.startswith("flatpak:"):
                # Selenium needs an executable path; use Flatpak's exported launcher when available.
                exported = "/var/lib/flatpak/exports/bin/org.mozilla.firefox"
                if os.path.isfile(exported): options.binary_location = exported
            try:
                _page = webdriver.Firefox(options=options)
            except Exception as exc:
                raise RuntimeError(
                    "Firefox was detected, but its WebDriver kit (Selenium/geckodriver) "
                    "is not ready. Install the package with `pip install agent-code`, "
                    "then approve Selenium Manager's geckodriver download when prompted by your system. "
                    f"Details: {exc}"
                ) from exc
        else:
            opts = (ChromiumOptions()
                    .headless(True)
                    .set_argument("--no-sandbox")
                    .set_argument("--disable-dev-shm-usage")
                    .set_argument("--disable-blink-features=AutomationControlled"))
            configured_path, _configured_kind = _browser_settings()
            if configured_path:
                opts.set_browser_path(configured_path)
            _page = ChromiumPage(opts)
    if _page is None and _browser_kind == "firefox":
        raise RuntimeError("Firefox is available, but Selenium is missing. Install dependencies with `pip install agent-code` to enable browser automation.")
    if _page is None and _browser_kind == "unavailable":
        raise RuntimeError("Browser automation is unavailable because optional browser dependencies are not installed. Agent Code can continue without browser tools; install dependencies with `pip install agent-code` to enable it.")
    return _page


def navigate(url):
    if not isinstance(url, str) or not url.strip():
        return "ERROR: url required"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    global _page
    try:
        page = _get_page()
        if _is_firefox():
            page.set_page_load_timeout(30)
            page.get(url)
        else:
            page.get(url, timeout=30)
        return "OK browser={} title={!r} url={}".format(_browser_kind, page.title, page.current_url if _is_firefox() else page.url)
    except Exception as first_error:
        # Recover once if Chromium disconnected or the page handle went stale.
        try:
            try:
                if _page is not None:
                    _page.quit()
            except Exception:
                pass
            _page = None
            page = _get_page()
            if _is_firefox():
                page.set_page_load_timeout(30)
                page.get(url)
            else:
                page.get(url, timeout=30)
            return "OK reconnected title={!r} url={}".format(page.title, page.current_url if _is_firefox() else page.url)
        except Exception as retry_error:
            return "ERROR browser connection: {}; reconnect failed: {}".format(first_error, retry_error)


def snapshot(offset=0, limit=120):
    """Return a bounded line window from the visible page text.

    Use offset/limit to inspect only the relevant section instead of repeatedly
    sending the entire page to the model. The result is capped defensively.
    """
    try:
        page = _get_page()
        if _is_firefox():
            from selenium.webdriver.common.by import By
            text = page.find_element(By.TAG_NAME, "body").text
        else:
            body = page.ele("tag:body", timeout=5)
            text = body.text if body else page.html
        lines = (text or "(empty)").splitlines()
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = max(1, min(300, int(limit)))
        except (TypeError, ValueError):
            limit = 120
        chunk = lines[offset:offset + limit]
        result = "\n".join(chunk)
        header = f"# Browser snapshot lines {offset + 1}-{offset + len(chunk)} of {len(lines)}\n"
        if offset + len(chunk) < len(lines):
            header += f"# More lines available; request offset={offset + len(chunk)} to continue.\n"
        return header + result[:12000]
    except Exception as e:
        return "ERROR: " + str(e)


def click(selector):
    try:
        page = _get_page()
        if _is_firefox():
            from selenium.webdriver.common.by import By
            ele = page.find_element(By.CSS_SELECTOR, selector)
        else:
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
        if _is_firefox():
            from selenium.webdriver.common.by import By
            ele = page.find_element(By.CSS_SELECTOR, selector)
        else:
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


def screenshot(path="browser-screenshot.png", full_page=False):
    """Capture the current browser viewport or full page to a PNG file."""
    try:
        page = _get_page()
        target = str(path or "browser-screenshot.png")
        if _is_firefox():
            if full_page:
                page.execute_script("document.documentElement.style.overflow='visible'")
            page.save_screenshot(target)
        else:
            page.get_screenshot(path=target, full_page=bool(full_page))
        return "OK screenshot saved: " + target
    except Exception as e:
        return "ERROR screenshot: {}: {}".format(type(e).__name__, e)


def devtools(action="inspect", selector="", max_chars=4000):
    """Inspect DOM/page state, query selectors, or report performance entries."""
    try:
        page = _get_page()
        if action == "inspect":
            if _is_firefox():
                result = {"url": page.current_url, "title": page.title,
                          "ready_state": page.execute_script("return document.readyState"),
                          "viewport": page.execute_script("return ({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})"),
                          "html": (page.page_source or "")[:int(max_chars)]}
            else:
                result = {"url": page.url, "title": page.title,
                          "ready_state": page.run_js("document.readyState"),
                          "viewport": page.run_js("({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})"),
                          "html": (page.html or "")[:int(max_chars)]}
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if action == "selector":
            if not selector:
                return "ERROR: selector required"
            script = "return Array.from(document.querySelectorAll(arguments[0])).slice(0,30).map(e=>({tag:e.tagName,text:(e.innerText||'').slice(0,200),id:e.id,classes:String(e.className||'').slice(0,200),href:e.href||null,placeholder:e.placeholder||null}))"
            result = page.execute_script(script, selector) if _is_firefox() else page.run_js(script, selector)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if action == "performance":
            script = "return JSON.stringify(performance.getEntriesByType('resource').map(x=>({name:x.name,duration:Math.round(x.duration),size:x.transferSize})).slice(-80))"
            result = page.execute_script(script) if _is_firefox() else page.run_js(script)
            return json.dumps(json.loads(result or "[]"), ensure_ascii=False, indent=2)
        if action == "console":
            return "Console history is not consistently exposed by DrissionPage. Use action=inspect or performance for supported diagnostics."
        return "ERROR: action must be inspect, selector, performance, or console"
    except Exception as e:
        return "ERROR devtools: {}: {}".format(type(e).__name__, e)


def links(limit=30):
    try:
        page = _get_page()
        out = []
        if _is_firefox():
            from selenium.webdriver.common.by import By
            anchors = page.find_elements(By.TAG_NAME, "a")[:int(limit)]
            for a in anchors:
                t = (a.text or "").strip()[:80]
                h = a.get_attribute("href") or ""
                if t and h:
                    out.append("{} -> {}".format(t, h))
            return "\n".join(out) or "(no links)"
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
        if _is_firefox():
            page.execute_script("window.scrollBy(0, arguments[0])", int(pixels))
        else:
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
    global _browser_kind
    _browser_kind = None
    return "OK"


SKILL = {
    "name": "browser",
    "description": "Browser automation priority: Chrome/Chromium via DrissionPage first, Firefox via Selenium/WebDriver second, then WebDriver setup guidance as fallback. Set AGENT_CODE_BROWSER=chrome or firefox to override auto-detection.",
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
        "description": "Return a bounded line window of visible page text. Use offset and limit to inspect only the relevant section; continue from the returned offset instead of repeatedly reading the whole page.",
        "parameters": {"type": "object",
                       "properties": {"offset": {"type": "integer", "description": "Zero-based starting line; default 0"},
                                      "limit": {"type": "integer", "description": "Number of lines, 1-300; default 120"}}}}},
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
        "name": "browser_screenshot",
        "description": "Capture a screenshot of the current page as a PNG file; text snapshot remains available separately.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "full_page": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "browser_devtools",
        "description": "Browser developer diagnostics: inspect current page, query CSS selectors, or inspect resource performance. Actions: inspect, selector, performance, console.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["inspect", "selector", "performance", "console"]},
            "selector": {"type": "string"}, "max_chars": {"type": "integer"}}}}},
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
    "browser_screenshot": screenshot,
    "browser_devtools": devtools,
    "browser_scroll":   scroll,
}


def _cmd_close(args, log):
    log(close(), "dim")


COMMANDS = {
    "browser-close": {"handler": _cmd_close,
                      "description": "Close the headless browser."},
}
