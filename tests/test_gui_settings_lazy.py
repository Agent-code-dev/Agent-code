"""Regression checks for lazy, non-blocking desktop settings construction."""
import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"


def _settings_class():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SettingsDialog"
    )


def _method(cls, name):
    return next(
        node for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _nested_methods(method):
    return {
        node.name: node for node in ast.walk(method)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node is not method
    }


def test_settings_tabs_are_built_on_first_visit():
    cls = _settings_class()
    init = _method(cls, "__init__")
    nested = _nested_methods(init)
    assert "_build_mcp" in nested
    assert "_build_sandbox" in nested
    assert "_build_ssh" in nested
    assert "_build_provider" in nested

    # Heavy MCP widgets must only be created inside the MCP tab builder.
    eager_calls = [
        node for node in init.body
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MCPManagerDialog"
    ]
    assert not eager_calls
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MCPManagerDialog"
        for node in ast.walk(nested["_build_mcp"])
    )


def test_unvisited_tabs_keep_persisted_settings_on_save():
    cls = _settings_class()
    save = _method(cls, "_save")
    source = ast.unparse(save)
    assert "hasattr(self, 'podman_sandbox_var')" in source
    assert "hasattr(self, 'core_mode_var')" in source
    assert "hasattr(self, 'browser_path_entry')" in source
    assert "cfg.get('max_repair_attempts', 3)" in source


def test_podman_status_probe_runs_in_worker_thread():
    cls = _settings_class()
    method = _method(cls, "_refresh_podman_status")
    source = ast.unparse(method)
    assert "threading.Thread" in source
    assert "self.after(0" in source


def test_settings_tab_callback_supports_ctktabview_no_argument_contract():
    cls = _settings_class()
    init = _method(cls, "__init__")
    nested = _nested_methods(init)
    callback = nested["_on_settings_tab_change"]
    # CTkTabview calls command() without passing the selected tab name.
    assert len(callback.args.args) == 1  # self is not present for nested functions
    source = ast.unparse(callback)
    assert "tabs.get()" in source
    assert "tab_name=None" in source
