from pathlib import Path

from agent_code.model_protocols import protocol_request_options
from agent_code.web_desktop import AgentWebAPI, WebviewRoot


def test_thinking_effort_is_sent_only_to_supported_models():
    profile = {"provider": "openai", "tool_choice_modes": ["auto"], "parallel_tool_calls": True}
    assert protocol_request_options(
        profile, has_tools=True, thinking_effort="high", model="gpt-5.1"
    )["reasoning_effort"] == "high"
    assert "reasoning_effort" not in protocol_request_options(
        profile, has_tools=True, thinking_effort="high", model="gpt-4.1"
    )


def test_openrouter_thinking_effort_uses_reasoning_object():
    profile = {"provider": "openai", "tool_choice_modes": ["auto"]}
    options = protocol_request_options(
        profile, has_tools=True, thinking_effort="medium", model="vendor/model",
        base_url="https://openrouter.ai/api/v1",
    )
    assert options["reasoning"] == {"effort": "medium"}


def test_unknown_endpoint_does_not_receive_thinking_parameters():
    profile = {"provider": "custom", "tool_choice_modes": ["auto"]}
    options = protocol_request_options(
        profile, has_tools=True, thinking_effort="high", model="unknown-model",
        base_url="https://example.invalid/v1",
    )
    assert "reasoning_effort" not in options
    assert "reasoning" not in options


def test_task_history_endpoint_returns_empty_list_without_history():
    class Engine:
        messages = []
        todo = type("Todo", (), {"items": []})()

    api = AgentWebAPI(Engine(), WebviewRoot())
    assert isinstance(api.get_task_history().get("tasks"), list)


def test_addon_store_is_a_main_navigation_destination():
    html = (Path(__file__).parents[1] / "src/agent_code/web_ui/index.html").read_text()
    assert 'data-page="store"' in html
    assert "Add-on Store" in html


def test_user_supplied_stylesheet_is_installed():
    css = (Path(__file__).parents[1] / "src/agent_code/web_ui/style.css").read_text()
    assert "--bg:#0b0d12" in css
    assert "--blue:#6c91ff" in css
