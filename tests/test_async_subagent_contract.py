from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_task_and_status_tools_are_registered_in_core_schemas():
    source = (ROOT / "src" / "agent_code" / "agent.py").read_text(encoding="utf-8")
    assert '"name": "task"' in source
    assert '"name": "task_status"' in source
    assert '"task_status":      self._subagent_status' in source


def test_subagent_schema_describes_async_shared_workspace():
    source = (ROOT / "src" / "agent_code" / "agent.py").read_text(encoding="utf-8")
    assert "Start a concurrent subagent" in source
    assert "job_id" in source
    assert "may read and modify files inside the shared workspace" in source
    assert "def _subagent_status(self, job_id: str)" in source


def test_tui_does_not_have_fixed_eight_round_cap():
    content = (ROOT / "src" / "agent_code" / "tui.py").read_text(encoding="utf-8")
    assert "for _ in range(8)" not in content
    assert "Stopped after 8 tool rounds" not in content


def test_background_process_tool_returns_pid_only():
    source = (ROOT / "src" / "agent_code" / "agent.py").read_text(encoding="utf-8")
    assert 'return f"PID: {proc.pid}"' in source
