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


def test_textual_tui_initializes_question_broker_and_routes_questions_to_ui():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    assert "self.engine.ask_user_broker = AskUserBroker" in source
    assert "def _drain_engine_events" in source
    assert "AgentQuestionScreen" in source
    assert "_answer_agent_question" in source


def test_textual_addons_navigation_uses_real_tab_id_and_worker_always_resets_busy():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    assert '"addons" if name == "Add-ons"' in source
    worker = source.split("def _run_agent", 1)[1].split("def action_stop_task", 1)[0]
    assert "finally:" in worker and "self.engine.busy = False" in worker


def test_textual_settings_search_is_compact_and_does_not_push_settings_tabs_out_of_view():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    assert 'with Horizontal(id="settings-search-row")' in source
    assert 'yield Input(placeholder="Filter settings…", id="settings_search")' in source
    assert 'yield Static("All settings", id="search-results")' in source
    assert "#settings-search-row { height: 3; min-height: 3;" in source
    assert "#search-results { width: 2fr; height: 3; min-height: 3;" in source
    assert "#settings-tabs { height: 1fr; min-height: 0; }" in source


def test_textual_ui_uses_restrained_modern_neutral_palette():
    source = (SRC / "textual_tui.py").read_text(encoding="utf-8")
    assert "Screen { background: #111315; color: #e5e7e9; }" in source
    assert "#176b91" not in source
    assert "#45b8e8" not in source
    assert "#8bd5ff" not in source
    assert 'color = "#c2cbd1" if role == "user"' in source
