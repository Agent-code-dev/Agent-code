from pathlib import Path
import sys
import types


def test_desktop_always_launches_customtkinter(monkeypatch):
    from agent_code import cli
    monkeypatch.setattr(cli, "_ensure_linux_tkinter", lambda: None)
    monkeypatch.setitem(sys.modules, "tkinter", types.ModuleType("tkinter"))
    monkeypatch.setitem(sys.modules, "customtkinter", types.ModuleType("customtkinter"))
    classic = types.ModuleType("agent_code.agent")
    classic.main = lambda: None
    monkeypatch.setitem(sys.modules, "agent_code.agent", classic)
    assert cli._gui(types.SimpleNamespace()) == 0


def test_legacy_customtkinter_config_remains_compatible(monkeypatch):
    from agent_code import cli, settings_store
    monkeypatch.setattr(settings_store, "load_config", lambda: {"desktop_ui": "customtkinter"})
    monkeypatch.setattr(cli, "_ensure_linux_tkinter", lambda: None)
    monkeypatch.setitem(sys.modules, "tkinter", types.ModuleType("tkinter"))
    monkeypatch.setitem(sys.modules, "customtkinter", types.ModuleType("customtkinter"))
    legacy = types.ModuleType("agent_code.agent")
    legacy.main = lambda: None
    monkeypatch.setitem(sys.modules, "agent_code.agent", legacy)
    assert cli._gui(types.SimpleNamespace()) == 0


def test_server_webui_uses_local_html_markdown_and_http_api():
    root = Path(__file__).parents[1] / "src/agent_code"
    source = (root / "web_desktop.py").read_text()
    html = (root / "web_ui/index.html").read_text()
    css = (root / "web_ui/style.css").read_text()
    js = (root / "web_ui/app.js").read_text()
    assert "class AgentWebAPI" in source
    assert "raw HTML disabled" in source
    assert 'MarkdownIt("default"' in source
    assert "def main() -> int:" not in source
    assert "Add-on Store" in html and "MCP servers" in html
    assert "prefers-reduced-motion" in css
    assert "window.pywebview" not in js
    assert "fetch('/api/'" in js
    assert "Tasks & plans" in html and "Workspace" in html
    assert "settings-panel" in html and "read_workspace_file" in js


def test_agent_headless_mode_does_not_touch_tk_widgets():
    source = (Path(__file__).parents[1] / "src/agent_code/agent.py").read_text()
    assert "if self.headless:" in source
    assert "self._engine_running = bool(running)" in source


def test_web_ui_activity_controls_and_compact_settings_contract():
    root = Path(__file__).parents[1] / "src/agent_code/web_ui"
    html = (root / "index.html").read_text()
    js = (root / "app.js").read_text()
    css = (root / "style.css").read_text()
    backend = (root.parent / "web_desktop.py").read_text()
    assert 'id="clearActivity"' in html and 'id="clearChat"' in html
    assert "clear_activity" in js and "clear_chat" in js
    assert "STREAM_CHUNK_EVENT='stream_chunk'" in js and "STREAM_END_EVENT='stream_end'" in js
    assert "def clear_activity(self)" in backend
    assert "settings-layout" in css and "grid-template-columns:205px minmax(0,1fr)" in css
    assert "get_workspace_entries" in backend and "get_task_history" in backend


def test_agent_workspace_visual_refresh_is_shared_by_desktop_and_server():
    root = Path(__file__).parents[1] / "src/agent_code"
    html = (root / "web_ui/index.html").read_text()
    css = (root / "web_ui/style.css").read_text()
    server = (root / "server.py").read_text()
    assert "Make progress on" in html
    assert "Build a feature" in html
    assert "prompt-cards" in html
    assert "--blue2:#4f76ee" in css
    # The authenticated server serves the exact same packaged UI directory
    # as the authenticated WebUI server frontend.
    assert "from .web_desktop import AgentWebAPI, UI_DIR, WebviewRoot" in server
    assert 'index = UI_DIR / "index.html"' in server
    assert 'path = UI_DIR / asset_name' in server


def test_web_ui_exposes_blueprints_provider_profiles_and_task_recovery():
    root = Path(__file__).parents[1] / "src/agent_code"
    html = (root / "web_ui/index.html").read_text()
    js = (root / "web_ui/app.js").read_text()
    backend = (root / "web_desktop.py").read_text()
    server = (root / "server.py").read_text()
    assert 'data-page="blueprint"' in html and 'id="blueprintForm"' in html
    assert 'id="providerProfile"' in html and 'id="saveProviderProfile"' in html
    assert "resume_task" in js and "continue_task" in js and "rerun_task" in js
    assert "def save_blueprint" in backend and "def save_provider_profile" in backend
    assert '"save_blueprint"' in server and '"resume_task"' in server
