import ast
import re
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NAMES = {"_render_inline", "_render_markdown_legacy"}
NODES = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
NS = {"re": re, "_INLINE_PATTERN": re.compile(
    r"(\*\*[^*\n]+?\*\*)|(`[^`\n]+?`)|(~~[^~\n]+?~~)|(\*[^*\n]+?\*)|(\[[^\]\n]+?\]\([^\)\n]+?\))"
)}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), "exec"), NS)


class TextBuffer:
    def __init__(self):
        self.value = ""

    def insert(self, _where, value, _tags=()):
        self.value += value


def test_fallback_renders_pipe_tables_as_rows_not_raw_markdown():
    widget = TextBuffer()
    NS["_render_markdown_legacy"](
        widget, "| Name | Details |\n|---|---|\n| Python | [Official docs](https://python.org) |"
    )
    assert "Name" in widget.value and "Details" in widget.value
    assert "Official docs" in widget.value
    assert "|---|---|" not in widget.value


def test_fallback_renders_bold_strike_and_links():
    widget = TextBuffer()
    NS["_render_inline"](widget, "**bold** ~~removed~~ [docs](https://example.com)", None)
    assert widget.value == "bold removed docs (https://example.com)"
