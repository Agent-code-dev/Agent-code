from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_installation_docs_use_simple_pip_command_and_no_custom_installer():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
    cli = (ROOT / "src" / "agent_code" / "cli.py").read_text(encoding="utf-8")
    assert "pip install agent-code" in readme
    assert "pip install agent-code" in docs
    assert "install-linux.sh" not in readme
    assert "install-system-deps" not in readme
    assert "install-system-deps" not in cli
    assert not (ROOT / "scripts" / "install-linux.sh").exists()
    assert not (ROOT / "src" / "agent_code" / "system_deps.py").exists()


def test_full_install_keeps_customtkinter_without_pywebview():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "pywebview" not in pyproject
    assert "customtkinter>=5.2.2; extra != 'lite'" in pyproject


def test_textual_settings_scroll_viewports_are_explicitly_sized():
    source = (ROOT / "src" / "agent_code" / "textual_tui.py").read_text(encoding="utf-8")
    assert "#settings-tabs VerticalScroll { height: 1fr; min-height: 0; overflow-y: scroll;" in source
    assert "def _ensure_settings_scroll_layout" in source
    assert "scroll.styles.overflow_y = \"scroll\"" in source


def test_server_webui_initializes_over_authenticated_http_only():
    source = (ROOT / "src" / "agent_code" / "web_ui" / "app.js").read_text(encoding="utf-8")
    assert "pywebview" not in source
    assert "fetch('/api/'" in source
    assert "async function poll()" in source
    assert "initializeAgentCodeUI" in source


def test_web_ui_contains_accessible_focus_and_responsive_ai_workspace_polish():
    css = (ROOT / "src" / "agent_code" / "web_ui" / "style.css").read_text(encoding="utf-8")
    assert "button:focus-visible" in css
    assert "@media(max-width:820px)" in css
    assert ".send-button,.primary-button{background:#465159!important" in css
    assert "--bg:#141618" in css and "--blue:#84939e" in css
    assert "prefers-reduced-motion" in css
