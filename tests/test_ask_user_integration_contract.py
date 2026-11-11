from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_agent_exposes_and_handles_ask_user():
    source = (ROOT / "src/agent_code/agent.py").read_text(encoding="utf-8")
    assert '"name": "ask_user"' in source
    assert "self._ask_user_broker.ask(question, timeout=900)" in source
    assert '"ask_user"' in source.split("def _central_tool_permission", 1)[1].split("def ", 1)[0]
    assert "self._ask_user_broker.cancel_all()" in source


def test_tui_exposes_and_handles_ask_user_on_ui_queue():
    source = (ROOT / "src/agent_code/tui.py").read_text(encoding="utf-8")
    assert '"name": "ask_user"' in source
    assert 'self.events.put(("ask_user", event))' in source
    assert "self.ask_user_broker.answer_question" in source
    assert "self.ask_user_broker.cancel_all()" in source
