"""Provider compatibility regression tests (Gemini OpenAI-compatible metadata)."""
from types import SimpleNamespace

from agent_code.provider_compat import (
    _provider_metadata,
    _stream_tool_call_index,
    _tool_call_history_item,
    _has_missing_gemini_tool_signature,
)


def test_gemini_extra_content_is_preserved_from_sdk_extra_fields():
    signature = "opaque-gemini-signature"
    call = SimpleNamespace(
        id="call_123",
        type="function",
        function=SimpleNamespace(name="memory_memory_index", arguments="{}"),
        model_extra={"extra_content": {"google": {"thought_signature": signature}}},
    )

    item = _tool_call_history_item(call)

    assert item["extra_content"]["google"]["thought_signature"] == signature
    assert item["function"]["name"] == "memory_memory_index"


def test_provider_metadata_supports_dict_and_direct_signature_shapes():
    assert _provider_metadata({"extra_content": {"google": {"thought_signature": "sig"}}}) == {
        "extra_content": {"google": {"thought_signature": "sig"}}
    }
    assert _provider_metadata(SimpleNamespace(thought_signature="sig")) == {
        "extra_content": {"google": {"thought_signature": "sig"}}
    }


def test_stream_calls_without_index_do_not_collapse_parallel_calls():
    slots = {}
    first = SimpleNamespace(id="call_a")
    second = SimpleNamespace(id="call_b")
    assert _stream_tool_call_index(first, slots) == 0
    slots[0] = {"id": "call_a", "name": "one"}
    assert _stream_tool_call_index(second, slots) == 1
    slots[1] = {"id": "call_b", "name": "two"}
    assert _stream_tool_call_index(SimpleNamespace(id="call_a"), slots) == 0


def test_unindexed_parallel_calls_without_ids_get_separate_slots():
    slots = {0: {"id": "", "name": "first", "arguments": "{}"}}
    second = SimpleNamespace(
        function=SimpleNamespace(name="second", arguments="{}")
    )
    assert _stream_tool_call_index(second, slots) == 1


def test_legacy_tool_history_is_detected_without_fabricating_a_signature():
    legacy = [{"role": "assistant", "tool_calls": [{
        "id": "call_old", "type": "function",
        "function": {"name": "memory_memory_index", "arguments": "{}"},
    }]}]
    current = [{"role": "assistant", "tool_calls": [{
        "id": "call_new", "type": "function",
        "function": {"name": "memory_memory_index", "arguments": "{}"},
        "extra_content": {"google": {"thought_signature": "real-signature"}},
    }]}]
    assert _has_missing_gemini_tool_signature(legacy) is True
    assert _has_missing_gemini_tool_signature(current) is False

