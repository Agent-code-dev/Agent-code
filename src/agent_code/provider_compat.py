"""Preserve provider-specific metadata in OpenAI-compatible tool conversations."""


def _provider_metadata(value):
    """Return provider-specific response metadata without inventing fields.

    Gemini 3 sends an opaque thought signature in the OpenAI-compatible
    ``extra_content.google.thought_signature`` field. The OpenAI SDK keeps
    unknown response fields in ``model_extra``; rebuilding a message from its
    standard fields alone silently discards that signature.
    """
    if value is None:
        return {}
    candidates = []
    if isinstance(value, dict):
        candidates.append(value)
    else:
        for attr in ("model_extra", "__pydantic_extra__"):
            extra = getattr(value, attr, None)
            if isinstance(extra, dict):
                candidates.append(extra)
        try:
            dumped = value.model_dump(exclude_unset=True)
            if isinstance(dumped, dict):
                candidates.append(dumped)
        except Exception:
            pass
        extra_content = getattr(value, "extra_content", None)
        if extra_content is not None:
            candidates.append({"extra_content": extra_content})
        signature = getattr(value, "thought_signature", None)
        if signature:
            candidates.append({"thought_signature": signature})

    result = {}
    for candidate in candidates:
        extra_content = candidate.get("extra_content")
        if isinstance(extra_content, dict) and extra_content:
            result["extra_content"] = dict(extra_content)
        signature = candidate.get("thought_signature")
        if signature and "extra_content" not in result:
            result["extra_content"] = {"google": {"thought_signature": signature}}
    return result


def _tool_call_history_item(tool_call):
    """Serialize a tool call while retaining provider-required metadata."""
    function = getattr(tool_call, "function", None)
    if isinstance(tool_call, dict):
        function = tool_call.get("function") or {}
        item = {
            "id": tool_call.get("id", ""),
            "type": tool_call.get("type", "function"),
            "function": {
                "name": function.get("name", "") if isinstance(function, dict) else "",
                "arguments": function.get("arguments", "{}") if isinstance(function, dict) else "{}",
            },
        }
    else:
        item = {
            "id": getattr(tool_call, "id", ""),
            "type": getattr(tool_call, "type", "function") or "function",
            "function": {
                "name": getattr(function, "name", "") or "",
                "arguments": getattr(function, "arguments", "{}") or "{}",
            },
        }
    item.update(_provider_metadata(tool_call))
    return item


def _stream_tool_call_index(call, slots):
    """Handle providers (notably Google) that omit the streaming call index."""
    index = getattr(call, "index", None)
    if isinstance(index, int) and index >= 0:
        return index
    call_id = getattr(call, "id", None)
    if call_id:
        for existing_index, slot in slots.items():
            if slot.get("id") == call_id:
                return existing_index
    # Reuse the only unfinished slot for a fragmented call without an index.
    if not call_id and len(slots) == 1:
        only_index, only_slot = next(iter(slots.items()))
        function = getattr(call, "function", None)
        incoming_name = getattr(function, "name", None) if function is not None else None
        incoming_args = getattr(function, "arguments", None) if function is not None else None
        if (not only_slot.get("name") or not only_slot.get("arguments")
                or (not incoming_name and not incoming_args)):
            return only_index
    index = 0
    while index in slots:
        index += 1
    return index


def _has_missing_gemini_tool_signature(messages):
    """Detect legacy tool-call history that cannot be replayed to Gemini 3."""
    for message in messages or []:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            extra = call.get("extra_content") or {}
            google = extra.get("google") if isinstance(extra, dict) else None
            if not (isinstance(google, dict) and google.get("thought_signature")):
                return True
    return False
