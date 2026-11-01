import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent_code import mcp_manager as mm


def test_validate_remote_urls():
    assert mm.validate_server_url("https://example.com/mcp/") == "https://example.com/mcp"
    assert mm.validate_server_url("http://localhost:9000/mcp") == "http://localhost:9000/mcp"
    with pytest.raises(ValueError):
        mm.validate_server_url("ftp://example.com/mcp")
    with pytest.raises(ValueError):
        mm.validate_server_url("http://example.com/mcp")
    with pytest.raises(ValueError):
        mm.validate_server_url("https://user:password@example.com/mcp")


def test_internal_names_are_unique_and_stable():
    used = set()
    first = mm.safe_tool_name("github", "search/repos", used)
    second = mm.safe_tool_name("github", "search/repos", used)
    assert first == "mcp_github_search_repos"
    assert second != first
    assert len(first) <= 64


def test_schema_conversion_rejects_malformed_schema():
    assert mm._json_schema(None)["type"] == "object"
    assert mm._json_schema({"type": "array"})["properties"] == {}
    assert mm._json_schema({"type": "object", "properties": [], "required": "bad"}) == {
        "type": "object", "properties": {}}


class FakeSession:
    def __init__(self, read, write): self.calls = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def initialize(self): return None
    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name="echo", description="Echo text", inputSchema={"type":"object", "properties":{"text":{"type":"string"}}})])
    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(content=[SimpleNamespace(text=args["text"])], structuredContent=None, isError=False)


@pytest.fixture
def fake_sdk(monkeypatch):
    @asynccontextmanager
    async def fake_transport(url, headers=None, timeout=None, sse_read_timeout=None):
        yield object(), object(), None
    monkeypatch.setattr(mm, "streamablehttp_client", fake_transport)
    monkeypatch.setattr(mm, "ClientSession", FakeSession)


def test_remote_connect_discovery_call_and_disconnect(fake_sdk):
    manager = mm.RemoteMCPManager(timeout=2, call_timeout=2)
    config = {"id":"test", "name":"Test", "url":"https://example.com/mcp", "headers":{}}
    try:
        tools = manager.connect(config)
        assert tools[0]["name"] == "echo"
        assert manager.is_connected("test")
        assert manager.call_tool("test", "echo", {"text":"hello"}) == "hello"
        assert manager.disconnect("test") is True
        with pytest.raises(mm.MCPError, match="disconnected"):
            manager.call_tool("test", "echo", {"text":"hello"})
    finally:
        manager.close()


def test_remote_auth_header_newlines_rejected(fake_sdk):
    manager = mm.RemoteMCPManager(timeout=2, call_timeout=2)
    try:
        with pytest.raises(ValueError, match="newline"):
            manager.connect({"id":"bad", "url":"https://example.com/mcp", "headers":{"Authorization":"bad\nvalue"}})
    finally:
        manager.close()


def test_mcp_argument_schema_validation():
    from agent_code.mcp_manager import validate_tool_arguments
    schema = {"type": "object", "properties": {"name": {"type": "string"}, "count": {"type": "integer"}}, "required": ["name"], "additionalProperties": False}
    assert validate_tool_arguments(schema, {"name": "demo", "count": 2})["name"] == "demo"
    import pytest
    with pytest.raises(ValueError):
        validate_tool_arguments(schema, {})
    with pytest.raises(ValueError):
        validate_tool_arguments(schema, {"name": 4})
    with pytest.raises(ValueError):
        validate_tool_arguments(schema, {"name": "ok", "extra": True})
