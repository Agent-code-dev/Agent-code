import importlib.util
from pathlib import Path


def load_browser_skill():
    path = Path(__file__).parents[1] / "src" / "agent_code" / "data" / "skills" / "browser" / "skill.py"
    spec = importlib.util.spec_from_file_location("agent_code_browser_skill_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_firefox_is_selected_when_deb_or_snap_binary_is_found(monkeypatch):
    browser = load_browser_skill()
    monkeypatch.setenv("AGENT_CODE_BROWSER", "auto")
    monkeypatch.setattr(browser, "_firefox_binary", lambda: "/snap/bin/firefox")
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser.os.path, "isfile", lambda path: False)
    assert browser._requested_browser() == "firefox"


def test_explicit_firefox_selection_does_not_require_chromium(monkeypatch):
    browser = load_browser_skill()
    monkeypatch.setenv("AGENT_CODE_BROWSER", "firefox")
    monkeypatch.setattr(browser, "_firefox_binary", lambda: "/usr/bin/firefox-esr")
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    assert browser._requested_browser() == "firefox"


def test_firefox_snap_launcher_is_detected_before_chromium_fallback(monkeypatch):
    browser = load_browser_skill()
    monkeypatch.setenv("AGENT_CODE_BROWSER", "auto")
    monkeypatch.setattr(browser, "_firefox_binary", lambda: "/snap/bin/firefox")
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(browser, "ChromiumPage", object())
    assert browser._requested_browser() == "firefox"


def test_firefox_only_machine_does_not_fall_back_to_missing_chromium(monkeypatch):
    browser = load_browser_skill()
    monkeypatch.setenv("AGENT_CODE_BROWSER", "auto")
    monkeypatch.setattr(browser, "_firefox_binary", lambda: None)
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(browser, "ChromiumPage", object())
    assert browser._requested_browser() == "unavailable"


def test_manual_firefox_path_is_selected(monkeypatch, tmp_path):
    browser = load_browser_skill()
    executable = tmp_path / "firefox-custom"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.setattr(browser, "_browser_settings", lambda: (str(executable), "auto"))
    monkeypatch.setattr(browser, "_firefox_binary", lambda: str(executable))
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser.os.path, "isfile", lambda path: str(path) == str(executable))
    assert browser._requested_browser() == "firefox"


def test_manual_chromium_path_is_selected_without_path_lookup(monkeypatch, tmp_path):
    browser = load_browser_skill()
    executable = tmp_path / "browser-custom"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.setattr(browser, "_browser_settings", lambda: (str(executable), "auto"))
    monkeypatch.setattr(browser, "_firefox_binary", lambda: None)
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser.os.path, "isfile", lambda path: str(path) == str(executable))
    monkeypatch.setattr(browser, "ChromiumPage", object())
    assert browser._requested_browser() == "chromium"
