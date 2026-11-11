from pathlib import Path

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "agent_code"


def test_textual_terminal_workspace_has_navigation_tabs_search_and_palette():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    for marker in ("TabbedContent", "TabPane", "#search", "settings_search", "ctrl+p", "command_palette"):
        assert marker in source
    for page in ("Chat", "Workspace", "Activity", "Skills", "MCP", "Settings", "Add-ons", "Help"):
        assert page in source


def test_textual_tui_reuses_existing_agent_execution_engine():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    assert "self.engine = TUI.__new__(TUI)" in source
    assert "self.engine.answer(prompt)" in source
    assert "@work(thread=True" in source
    assert "self.engine.cancel_event.set()" in source


def test_textual_settings_use_existing_secure_config_writer():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    assert "from .tui import PROVIDERS, TUI, read_config, write_config, api_keys" in source
    assert "write_config(self.cfg)" in source
    assert "password=True, id=\"api_key\"" in source


def test_cli_routes_tui_to_textual_and_keeps_legacy_curses_option():
    source = (SRC / "cli.py").read_text(encoding="utf-8")
    assert 'from .textual_tui import main as run_tui' in source
    assert 'sub.add_parser("tui-legacy"' in source
    assert 'sub.add_parser("configure"' in source


def test_textual_is_a_runtime_dependency():
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"textual>=1.0.0"' in source


def test_textual_ui_does_not_scan_filesystem_on_its_poll_timer():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    poll = source.split("def _poll_engine", 1)[1].split("def _refresh_live_panels", 1)[0]
    assert "_refresh_live_panels()" in poll
    assert "_workspace_summary()" not in poll
    assert "_skills_summary()" not in poll
    assert "_addons_summary()" not in poll
