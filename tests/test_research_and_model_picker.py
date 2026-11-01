from pathlib import Path
import ast

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
TUI = ROOT / "src" / "agent_code" / "tui.py"


def test_web_search_is_a_registered_core_tool_and_read_only_in_plan_mode():
    source = AGENT.read_text(encoding="utf-8")
    assert '"name": "web_search"' in source
    assert '"web_search":       tool_web_search' in source
    assert '"web_search", "web_fetch"' in source
    tui = TUI.read_text(encoding="utf-8")
    assert '"web_search":engine.tool_web_search' in tui
    assert '"web_search","web_fetch","task_status"' in tui


def test_research_guidance_requires_real_sources_not_invented_citations():
    source = AGENT.read_text(encoding="utf-8")
    assert "never invent sources" in source
    assert "prefer primary/authoritative sources" in TUI.read_text(encoding="utf-8")


def test_model_picker_is_explicit_click_not_hover_dropdown():
    source = AGENT.read_text(encoding="utf-8")
    assert "command=self._open_model_picker" in source
    assert "def _open_model_picker(self)" in source
    assert "Hovering never changes the selected model" in source
    assert "self.model_quick_menu = ctk.CTkOptionMenu" not in source


def test_search_function_uses_bounded_query_and_result_count():
    tree = ast.parse(AGENT.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "tool_web_search")
    assert fn.args.args[0].arg == "query"
    assert any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "min" for n in ast.walk(fn))


def test_search_result_parser_extracts_title_and_snippet():
    import ast
    from html.parser import HTMLParser
    tree = ast.parse(AGENT.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_SearchResultParser")
    namespace = {"HTMLParser": HTMLParser}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(AGENT), "exec"), namespace)
    parser = namespace["_SearchResultParser"]()
    parser.feed('<a class="result__a" href="https://example.com/docs">Official docs</a><a class="result__snippet">Useful official documentation</a>')
    assert parser.results
    assert parser.results[0]["title"] == "Official docs"
    assert parser.results[0]["url"] == "https://example.com/docs"
    assert "Useful official documentation" in parser.results[0]["snippet"]
