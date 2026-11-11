"""Tests for the local model-protocol catalog and native tool-call parsing."""
import json

from agent_code.model_protocols import (
    initialize_database,
    resolve_model_profile,
    parse_minimax_text_tool_calls,
    MiniMaxStreamTextFilter,
    upsert_profile,
)


def test_database_is_created_and_seeds_model_protocols(tmp_path):
    db = tmp_path / "protocols.sqlite3"
    assert initialize_database(db) == db
    qwen = resolve_model_profile("Custom OpenAI-compatible", "qwen3-max", "https://dashscope.example/v1", db)
    assert qwen["provider"] == "qwen"
    assert qwen["tool_format"] == "structured_tool_calls"
    assert qwen["preserve_reasoning"] is True

    minimax = resolve_model_profile("Custom OpenAI-compatible", "MiniMax-M2", "https://api.example/v1", db)
    assert minimax["provider"] == "minimax"
    assert minimax["tool_format"] == "structured_tool_calls"
    assert "native M2" in minimax["notes"]
    assert resolve_model_profile("Custom", "deepseek-v3", "https://api.deepseek.com/v1", db)["provider"] == "deepseek"
    assert resolve_model_profile("Custom", "kimi-k2.5", "https://api.moonshot.ai/v1", db)["provider"] == "kimi"
    assert resolve_model_profile("Custom", "glm-4.5", "https://open.bigmodel.cn/api/paas/v4", db)["provider"] == "glm"


def test_minimax_xml_tool_call_converts_to_internal_call(tmp_path):
    db = tmp_path / "protocols.sqlite3"
    initialize_database(db)
    profile = resolve_model_profile("MiniMax", "MiniMax-M2", path=db)
    assert profile["tool_format"] == "structured_tool_calls"
    # The explicit native marker is recognized as a fallback, not inferred
    # solely from the model name (hosted MiniMax APIs use structured calls).

    raw = (
        "I will inspect the file.\n"
        "<minimax:tool_call>"
        '<invoke name="read_file">'
        '<parameter name="path">src/main.py</parameter>'
        '<parameter name="offset">12</parameter>'
        "</invoke></minimax:tool_call>"
        "Done planning."
    )
    calls, visible = parse_minimax_text_tool_calls(raw, {"read_file"})
    assert len(calls) == 1
    assert calls[0].function.name == "read_file"
    assert json.loads(calls[0].function.arguments) == {"path": "src/main.py", "offset": 12}
    assert visible == "I will inspect the file.\nDone planning."


def test_unknown_or_incomplete_minimax_calls_are_never_dispatched():
    unknown, visible = parse_minimax_text_tool_calls(
        '<minimax:tool_call><invoke name="rm_everything"></invoke></minimax:tool_call>',
        {"read_file"},
    )
    assert unknown == []
    assert "rm_everything" in visible

    incomplete, visible = parse_minimax_text_tool_calls(
        '<minimax:tool_call><invoke name="read_file">', {"read_file"}
    )
    assert incomplete == []
    assert "<minimax:tool_call>" in visible


def test_stream_filter_handles_markers_split_across_chunks():
    filt = MiniMaxStreamTextFilter()
    visible = [filt.feed("Visible before <mini"),
               filt.feed("max:tool_call><invoke name='x'>"),
               filt.feed("<parameter name='a'>b</parameter></invoke></minimax:tool_call>Visible after"),
               filt.finish()]
    assert "".join(visible) == "Visible before Visible after"


def test_custom_profile_can_be_added_without_credentials(tmp_path):
    db = tmp_path / "protocols.sqlite3"
    initialize_database(db)
    upsert_profile({
        "provider": "custom-provider",
        "model_pattern": "my-model",
        "protocol": "custom-chat",
        "tool_format": "structured_tool_calls",
        "thinking_format": "none",
        "priority": 20,
        "notes": "test profile",
    }, db)
    profile = resolve_model_profile("custom-provider", "my-model-v2", path=db)
    assert profile["protocol"] == "custom-chat"


def test_profile_rejects_secret_fields(tmp_path):
    db = tmp_path / "protocols.sqlite3"
    initialize_database(db)
    try:
        upsert_profile({
            "provider": "x", "model_pattern": "*", "protocol": "x",
            "tool_format": "x", "thinking_format": "x", "api_key": "secret",
        }, db)
    except ValueError as exc:
        assert "credentials" in str(exc)
    else:
        raise AssertionError("secret-bearing protocol profiles must be rejected")


def test_protocol_request_options_only_send_known_capabilities():
    from agent_code.model_protocols import protocol_request_options
    profile = {"tool_choice_modes": ["auto", "none"], "parallel_tool_calls": None}
    assert protocol_request_options(profile, has_tools=True) == {"tool_choice": "auto"}
    assert protocol_request_options(profile, has_tools=False) == {"tool_choice": "none"}
    assert protocol_request_options({"tool_choice_modes": [], "parallel_tool_calls": None}, has_tools=True) == {}


def test_protocol_database_initialization_is_cached(tmp_path, monkeypatch):
    import agent_code.model_protocols as protocols
    db = tmp_path / "protocols.sqlite3"
    protocols.initialize_database(db)
    original = protocols._connect
    calls = []
    def counted(path=None):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(protocols, "_connect", counted)
    protocols.resolve_model_profile("qwen", "qwen3", path=db)
    assert calls == [db]
    calls.clear()
    protocols.resolve_model_profile("qwen", "qwen3", path=db)
    assert calls == [db]
