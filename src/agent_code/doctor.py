"""Privacy-conscious environment diagnostics for Agent Code."""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any


def _check(name: str, ok: bool, detail: str, level: str | None = None) -> dict[str, str]:
    if level is None:
        level = "ok" if ok else "warning"
    return {"name": name, "status": level, "detail": detail}




def _detect_browser_executable() -> str | None:
    """Find common Chromium-family browser installs beyond PATH.

    DrissionPage commonly uses its own discovery paths, so a PATH miss alone
    should not be reported as though the browser is missing.
    """
    names = ("chrome", "chromium", "chromium-browser", "msedge", "google-chrome")
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    candidates: list[Path] = []
    home = Path.home()
    if sys.platform.startswith("win"):
        for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(env_name)
            if root:
                base = Path(root)
                candidates.extend([
                    base / "Google/Chrome/Application/chrome.exe",
                    base / "Microsoft/Edge/Application/msedge.exe",
                    base / "Chromium/Application/chrome.exe",
                ])
    elif sys.platform == "darwin":
        candidates.extend([
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ])
    else:
        candidates.extend([
            Path("/usr/bin/google-chrome"), Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"), Path("/usr/bin/microsoft-edge"),
            Path("/snap/bin/chromium"), home / ".cache/ms-playwright/chromium",
            home / ".local/share/applications/chrome",
        ])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue

    # Ask DrissionPage's own resolver if available; it may know custom install paths.
    try:
        from DrissionPage import ChromiumOptions
        options = ChromiumOptions()
        browser_path = getattr(options, "browser_path", None)
        if callable(browser_path):
            browser_path = browser_path()
        if browser_path:
            path = Path(str(browser_path)).expanduser()
            if path.is_file():
                return str(path)
    except Exception:
        pass
    return None



def _detect_firefox_executable() -> str | None:
    """Detect Firefox installations including Debian wrappers and Snap launchers."""
    for name in ("firefox", "firefox-esr", "mozilla-firefox"):
        found = shutil.which(name)
        if found:
            return found
    candidates = (
        "/snap/bin/firefox", "/snap/firefox/current/usr/lib/firefox/firefox",
        "/usr/bin/firefox", "/usr/bin/firefox-esr", "/usr/lib/firefox/firefox",
        "/usr/lib/firefox-esr/firefox-esr", "/usr/lib/firefox-esr/firefox",
        "/opt/firefox/firefox", "/var/lib/flatpak/exports/bin/org.mozilla.firefox",
        str(Path.home() / ".local/share/flatpak/exports/bin/org.mozilla.firefox"),
        "/Applications/Firefox.app/Contents/MacOS/firefox",
    )
    for candidate in candidates:
        try:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        except OSError:
            pass
    for command, args in (("snap", ["list", "firefox"]), ("flatpak", ["info", "org.mozilla.firefox"])):
        exe = shutil.which(command)
        if exe:
            try:
                result = __import__("subprocess").run([exe, *args], capture_output=True, text=True, timeout=4)
                if result.returncode == 0:
                    return f"{command}:{'firefox' if command == 'snap' else 'org.mozilla.firefox'} (installed; launcher not found)"
            except Exception:
                pass
    return None

def collect_diagnostics() -> dict[str, Any]:
    """Collect useful checks without exposing API keys, tokens, or config contents."""
    from . import __version__
    from .paths import user_config_file, project_workspace_dir

    checks: list[dict[str, str]] = []
    checks.append(_check("Python", sys.version_info >= (3, 10), platform.python_version(),
                         "ok" if sys.version_info >= (3, 10) else "error"))
    checks.append(_check("Operating system", True, f"{platform.system()} {platform.release()}"))

    for module, label in (("customtkinter", "CustomTkinter GUI"), ("DrissionPage", "Browser automation"),
                          ("openai", "OpenAI-compatible API client"), ("markdown_it", "Markdown rendering")):
        found = importlib.util.find_spec(module) is not None
        required = module in ("customtkinter", "DrissionPage", "openai")
        checks.append(_check(label, found, "installed" if found else "not installed",
                             "ok" if found else ("error" if required else "warning")))

    config_path = user_config_file()
    config_state = "not created yet"
    config_ok = True
    has_api_key = False
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict):
                raise ValueError("configuration root must be a JSON object")
            candidates = []
            for key_name in ("openai_api_keys", "api_keys"):
                value = cfg.get(key_name, [])
                if isinstance(value, list):
                    candidates.extend(value)
                elif isinstance(value, str):
                    candidates.append(value)
            candidates.append(cfg.get("api_key", ""))
            has_api_key = any(isinstance(k, str) and k.strip() for k in candidates)
            config_state = "valid JSON; API key configured" if has_api_key else "valid JSON; API key not configured"
        except Exception as exc:
            config_ok = False
            config_state = f"invalid configuration ({type(exc).__name__})"
    checks.append(_check("User configuration", config_ok, config_state,
                         "ok" if config_ok else "error"))

    try:
        workspace = project_workspace_dir()
        probe = workspace / ".agent-code-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(_check("Workspace", True, f"writable: {workspace}"))
    except Exception as exc:
        checks.append(_check("Workspace", False, f"not writable ({type(exc).__name__})", "error"))

    browser_path = _detect_browser_executable()
    firefox_path = _detect_firefox_executable()
    checks.append(_check("Chromium-family browser", bool(browser_path),
                         browser_path or "No Chrome/Chromium/Edge executable detected.",
                         "ok" if browser_path else "warning"))
    checks.append(_check("Firefox browser", bool(firefox_path),
                         firefox_path or "No Firefox DEB/Snap/Flatpak executable detected.",
                         "ok" if firefox_path else "warning"))

    base_url = "not inspected"
    if config_path.exists() and config_ok:
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            raw_url = str(cfg.get("openai_base_url") or cfg.get("base_url") or cfg.get("api_base_url") or "not configured")
            if raw_url == "not configured":
                base_url = raw_url
            else:
                parsed = urlsplit(raw_url)
                # Exclude userinfo, query strings, and fragments which may contain secrets.
                host = parsed.hostname or ""
                if parsed.port:
                    host = f"{host}:{parsed.port}"
                base_url = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except Exception:
            base_url = "unavailable"
    checks.append(_check("API endpoint", True, base_url))

    return {
        "application": "Agent Code",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "checks": checks,
        "summary": {
            "ok": sum(c["status"] == "ok" for c in checks),
            "warnings": sum(c["status"] == "warning" for c in checks),
            "errors": sum(c["status"] == "error" for c in checks),
        },
        "privacy": "API keys, tokens, and configuration values other than the endpoint are not included.",
    }


def main(as_json: bool = False, output: str | None = None) -> int:
    report = collect_diagnostics()
    rendered = json.dumps(report, indent=2, ensure_ascii=False) if as_json or output else None
    if output:
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered or json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            target.chmod(0o600)
        except OSError:
            pass
        print(f"Diagnostic report saved to: {target}")
    if as_json:
        print(rendered)
    else:
        print(f"Agent Code {report['version']} — environment diagnostics")
        print("-" * 58)
        for item in report["checks"]:
            marker = {"ok": "OK", "warning": "WARN", "error": "ERROR"}[item["status"]]
            print(f"[{marker:5}] {item['name']}: {item['detail']}")
        s = report["summary"]
        print(f"\nSummary: {s['ok']} OK · {s['warnings']} warning(s) · {s['errors']} error(s)")
        print("Privacy: API keys and tokens are not printed.")
    return 1 if report["summary"]["errors"] else 0
