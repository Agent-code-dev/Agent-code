from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
TEXTUAL = ROOT / "src" / "agent_code" / "textual_tui.py"
LEGACY_TUI = ROOT / "src" / "agent_code" / "tui.py"


def test_unrestricted_host_shell_is_opt_in_and_confirmed_each_time():
    source = AGENT.read_text(encoding="utf-8")
    assert 'cfg.get("allow_unrestricted_host_shell", False)' in source
    assert '"shell=True"' not in source
    assert 'shell=True, executable=' in source
    assert '"Unrestricted host shell command"' in source
    assert 'if not self._ask_permission(' in source


def test_unrestricted_host_shell_setting_is_saved_in_both_tuis():
    legacy = LEGACY_TUI.read_text(encoding="utf-8")
    assert 'allow_unrestricted_host_shell' in legacy
    assert 'Deny this action' in legacy
    assert 'no interactive confirmation channel' in legacy


def test_security_documentation_explains_blacklist_aliases_and_limits():
    doc = (ROOT / "docs" / "security.md").read_text(encoding="utf-8")
    assert "security_blacklist_aliases" in doc
    assert "best-effort" in doc
    assert "OFF by default" in doc
