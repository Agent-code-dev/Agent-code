from pathlib import Path


def test_gui_exposes_task_workspace_navigation_and_actions():
    source = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
    text = source.read_text(encoding="utf-8")
    assert '"☷   Task Workspace", self._open_task_workspace' in text
    assert "def _open_task_workspace(self):" in text
    assert "def _refresh_task_workspace(self):" in text
    assert "def _show_task_workspace_detail(self, task_id):" in text
    assert "def _rerun_selected_task(self):" in text


def test_gui_task_workspace_displays_plan_and_trajectory():
    source = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
    text = source.read_text(encoding="utf-8")
    assert '"PLAN"' in text
    assert '"TRAJECTORY"' in text
    assert "state.plan" in text
    assert "state.trajectory" in text
