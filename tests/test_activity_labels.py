"""Unit tests for human-readable, tool-grounded progress labels."""
import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NODES = [node for node in TREE.body if isinstance(node, ast.FunctionDef)
         and node.name in {"describe_activity", "describe_tool_result"}]
NS = {"Path": Path}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), "exec"), NS)


def test_file_write_activity_names_actual_file():
    assert NS["describe_activity"]("write_file", {"path": "src/app.py"}) == "Writing app.py"
    assert NS["describe_activity"]("write_file", {"path": "README.md"}) == "Writing README.md"


def test_shell_activity_uses_human_friendly_action_label():
    label = NS["describe_activity"]("shell_run", {"command": "pytest -q"})
    assert label == "Running tests"
    assert "pytest" not in label


def test_shell_activity_names_file_when_relevant():
    label = NS["describe_activity"]("shell_run", {"command": "python -m py_compile src/app.py"})
    assert label == "Checking code in app.py"


def test_web_activity_hides_internal_url():
    label = NS["describe_activity"]("web_fetch", {"url": "https://example.com/private/path"})
    assert label == "Opening a web page"
    assert "example.com" not in label


def test_failed_result_is_not_reported_as_success():
    result = NS["describe_tool_result"]("write_file", {"path": "app.py"}, "ERROR: permission denied")
    assert result.startswith("Permission denied")
    assert "details in activity" in result


def test_successful_file_write_is_reported():
    assert NS["describe_tool_result"]("write_file", {"path": "app.py"}, "OK wrote 42 chars") == "Wrote app.py"
