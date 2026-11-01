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
