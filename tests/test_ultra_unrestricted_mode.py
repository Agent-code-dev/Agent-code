from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
TEXTUAL = ROOT / "src" / "agent_code" / "textual_tui.py"


def test_ultra_mode_is_opt_in_and_explicitly_warned_in_desktop_settings():
    source = AGENT.read_text(encoding="utf-8")
    assert 'ultra_unrestricted_enabled' in source
    assert 'Enable Ultra Unrestricted Agent Code' in source
    assert 'Mistakes may modify or delete personal files' in source
    assert 'self.app.permission = PERMISSION_AUTO if ultra_enabled else perm' in source


def test_ultra_mode_enables_host_execution_but_blacklist_check_remains_before_it():
    source = AGENT.read_text(encoding="utf-8")
    shell_start = source.index('def tool_shell_run(')
    shell_end = source.index('\ndef ', shell_start + 5)
    shell = source[shell_start:shell_end]
    assert shell.index('command_touches_blacklist') < shell.index('ultra_unrestricted_enabled')
    assert 'shell=True, executable=' in shell
    assert 'Path(cwd or WORKSPACE).expanduser().resolve()' in shell


def test_ultra_mode_bypasses_per_tool_prompts_only_after_plan_and_blacklist_guards():
    source = AGENT.read_text(encoding="utf-8")
    gate = source[source.index('def _central_tool_permission'):source.index('def _show_model_browser')]
    assert gate.index('command_touches_blacklist') < gate.index('ultra_unrestricted_enabled')
    assert gate.index('execution_mode == "plan"') < gate.index('ultra_unrestricted_enabled')


def test_textual_tui_exposes_ultra_toggle_and_confirmation():
    source = TEXTUAL.read_text(encoding="utf-8")
    assert 'id="ultra_unrestricted"' in source
    assert 'push_screen_wait(Confirm(' in source
    assert 'self.cfg["permission_mode"] = "auto" if ultra' in source


def test_ultra_mode_path_boundary_is_enabled_only_by_saved_setting():
    source = AGENT.read_text(encoding="utf-8")
    path_fn = source[source.index("def _safe_path("):source.index("def tool_read_file(")]
    assert 'load_agent_config().get("ultra_unrestricted_enabled", False)' in path_fn
    assert "boundary = Path(rp.anchor)" in path_fn
    assert "boundary = ROOT if allow_workspace_escape else WORKSPACE" in path_fn
