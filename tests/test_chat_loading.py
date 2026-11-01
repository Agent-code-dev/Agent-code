"""Regression tests for safely loading old Agent Code chat archives."""
import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NAMES = {"normalize_chat_data", "describe_activity", "describe_tool_result"}
NODES = [node for node in TREE.body if isinstance(node, ast.FunctionDef)
         and node.name in NAMES]
NS = {"Path": Path}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), "exec"), NS)


def test_load_replaces_old_system_prompt_with_current_prompt():
    messages, log = NS["normalize_chat_data"](
        {"messages": [{"role": "system", "content": "old prompt"},
                      {"role": "user", "content": "hello"}],
         "log": [["hello", "user"]]}, "current prompt")
    assert messages[0] == {"role": "system", "content": "current prompt"}
    assert messages[1]["content"] == "hello"
    assert log == [("hello", "user")]


def test_load_adds_system_prompt_when_archive_does_not_have_one():
    messages, _ = NS["normalize_chat_data"](
        {"messages": [{"role": "user", "content": "continue this"}]}, "system")
    assert messages[0] == {"role": "system", "content": "system"}
    assert messages[1]["role"] == "user"


def test_load_rejects_non_chat_payload():
    try:
        NS["normalize_chat_data"]({"log": []}, "system")
    except ValueError as exc:
        assert "chat history" in str(exc).lower()
    else:
        raise AssertionError("invalid chat payload should be rejected")


def test_skill_activity_does_not_leak_internal_tool_name():
    assert NS["describe_activity"]("moltgit_upload_repo", {}) == "Using a skill or tool"
    assert NS["describe_tool_result"]("moltgit_upload_repo", {}, "raw internal output") == "Step completed"
