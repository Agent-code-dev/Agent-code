import ast
from pathlib import Path

from markdown_it import MarkdownIt

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


def _load_renderer():
    wanted = {"_insert_inline_tokens", "_render_markdown_tokens"}
    nodes = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace = {"_MD_PARSER": MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_render_markdown_tokens"]


render = _load_renderer()


class _TextBuffer:
    def __init__(self):
        self.value = ""

    def insert(self, _where, value, _tags=()):
        self.value += value

    def get(self, _start, _end):
        return self.value[-4:]


def test_bullet_items_do_not_get_blank_lines_between_them():
    widget = _TextBuffer()
    render(widget, "- Research information\n- Work with APIs\n- Browser automation")
    assert widget.value.rstrip("\n").splitlines() == [
        "• Research information",
        "• Work with APIs",
        "• Browser automation",
    ]


def test_paragraphs_keep_one_readable_blank_line_between_them():
    widget = _TextBuffer()
    render(widget, "First paragraph.\n\nSecond paragraph.")
    assert widget.value.rstrip("\n").splitlines() == ["First paragraph.", "", "Second paragraph."]
