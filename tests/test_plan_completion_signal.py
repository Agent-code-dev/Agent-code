from pathlib import Path


def test_plan_completion_requires_explicit_signal():
    source = (Path(__file__).parents[1] / "src" / "agent_code" / "agent.py").read_text(encoding="utf-8")
    assert '\"name\": \"finish_plan\"' in source
    assert 'An assistant message ending is NOT a plan-completion signal.' in source
    assert 'if original_name == "finish_plan":' in source
    # A plain final assistant response must not automatically queue a plan.
    assert 'if task is not None and self.execution_mode == "plan":\n                    # Preserve the request and completed plan' not in source


def test_finish_plan_is_available_only_in_plan_mode_requests():
    source = (Path(__file__).parents[1] / "src" / "agent_code" / "agent.py").read_text(encoding="utf-8")
    assert '"name": "finish_plan"' in source
    assert 'if self.execution_mode == "build" else' in source
    assert '!= "finish_plan"' in source
