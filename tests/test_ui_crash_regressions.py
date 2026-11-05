"""Regression checks for scroll events, large model lists, and the chat menu."""
import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)


def _class_method(class_name, method_name):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)


def test_scroll_event_compatibility_resolves_tk_widget_paths_and_handles_stale_targets():
    assert "nametowidget(widget)" in TEXT
    assert "if not hasattr(widget, \"master\")" in TEXT
    assert "_check_if_valid_scroll = safe_check" in TEXT


def test_large_model_lists_are_rendered_in_bounded_pages():
    method = _class_method("App", "_show_model_browser")
    source = ast.get_source_segment(TEXT, method)
    assert "page_size = 60" in source
    assert "filtered[state[\"shown\"]:end]" in source
    assert "Load more" in source
    assert "query_var.trace_add" in source
    assert "self.app._show_model_browser" in TEXT


def test_chat_menu_uses_customtkinter_popup_not_native_menu():
    method = _class_method("App", "_show_chat_menu")
    source = ast.get_source_segment(TEXT, method)
    assert "ctk.CTkToplevel" in source
    assert "ctk.CTkButton" in source
    assert "tk_popup" not in source
    assert "self._chat_menu = tk.Menu" not in TEXT
    assert "self.chat_menu_button" in TEXT


def test_mcp_manager_refresh_computes_connection_state_per_server():
    method = _class_method("MCPManagerDialog", "_refresh")
    source = ast.get_source_segment(TEXT, method)
    assert "connected = bool(self.app.mcp_manager" in source
    assert 'server["id"] in connected' not in source


def test_tui_exposes_skills_and_addons_management_pages():
    tui_source = (Path(__file__).parents[1] / "src" / "agent_code" / "tui.py").read_text(encoding="utf-8")
    assert '"Add-ons"' in tui_source
    assert "def manage_skill(self, action):" in tui_source
    assert "def manage_addon(self, action):" in tui_source
    assert "self.cfg.get(\"disabled_skills\", [])" in tui_source
    assert "self.cfg.get(\"disabled_addons\", [])" in tui_source
    assert "skill_schemas, skill_handlers, skill_meta, skill_commands" in tui_source
    assert "addon_schemas, addon_handlers, addon_commands" in tui_source


def test_tui_answer_does_not_shadow_module_regex_import():
    tui_path = Path(__file__).parents[1] / "src" / "agent_code" / "tui.py"
    tui_tree = ast.parse(tui_path.read_text(encoding="utf-8"))
    tui_class = next(node for node in tui_tree.body if isinstance(node, ast.ClassDef) and node.name == "TUI")
    answer = next(node for node in tui_class.body if isinstance(node, ast.FunctionDef) and node.name == "answer")
    local_re_imports = [
        node for node in ast.walk(answer)
        if isinstance(node, ast.Import) and any(alias.name == "re" for alias in node.names)
    ]
    assert not local_re_imports, "answer() must use the module-level re import"
