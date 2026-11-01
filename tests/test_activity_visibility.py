import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NODE = next(node for node in TREE.body if isinstance(node, ast.FunctionDef)
            and node.name == "_is_internal_activity_log")
NS = {}
exec(compile(ast.Module(body=[NODE], type_ignores=[]), str(SOURCE), "exec"), NS)


def test_settings_and_model_status_are_activity_only():
    check = NS["_is_internal_activity_log"]
    assert check("[settings] saved — model=x")
    assert check("[models] Loaded 416 live models")


def test_checkpoint_and_recovery_messages_are_activity_only():
    check = NS["_is_internal_activity_log"]
    assert check("[checkpoint] started abc123")
    assert check("Recovery point: abc123")


def test_task_completion_and_failure_reports_are_activity_only():
    check = NS["_is_internal_activity_log"]
    assert check("Task Completed\nFiles changed: 2\nValidation passed")
    assert check("Task Failed\nFiles changed: 0\nValidation not run")


def test_internal_details_tag_is_always_activity_only():
    assert NS["_is_internal_activity_log"]("arbitrary diagnostic", "detail")


def test_normal_conversation_and_final_answers_remain_visible():
    check = NS["_is_internal_activity_log"]
    assert not check("Hello! How can I help?")
    assert not check("I finished implementing the requested feature.")
    assert not check("The tests passed.", "agent_md")
