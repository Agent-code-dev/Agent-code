from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = (ROOT / "src/agent_code/agent.py").read_text(encoding="utf-8")
TUI = (ROOT / "src/agent_code/tui.py").read_text(encoding="utf-8")
TEXTUAL = (ROOT / "src/agent_code/textual_tui.py").read_text(encoding="utf-8")


def test_max_mode_is_write_capable_but_not_a_permission_bypass():
    assert '("plan", "build", "max")' in AGENT
    assert 'self.execution_mode in ("build", "max")' in AGENT
    assert "safety, permissions, workspace boundaries" in AGENT
    assert '"Max Mode"' in AGENT


def test_tui_supports_max_mode_and_blueprint_context():
    assert '"max": "Max"' in TUI
    assert "BlueprintStore(WORKSPACE).prompt_context()" in TUI
    assert '("Build", "Max")' in TUI
    assert '"max": "Max"' in TEXTUAL


def test_textual_logs_do_not_force_scroll_or_clear_activity_each_poll():
    assert "auto_scroll=False" in TEXTUAL
    assert "activity.clear()" in TEXTUAL  # only used for a non-prefix reset
    assert "activity_was_at_bottom" in TEXTUAL
    assert "activity.call_after_refresh(activity.scroll_end" in TEXTUAL
