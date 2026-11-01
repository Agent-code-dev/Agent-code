"""Remote MCP client manager using the official MCP Python SDK.

Only Streamable HTTP remote servers are supported. No local server processes are
started. Sessions live on a dedicated asyncio loop thread; synchronous agent tools
bridge to that loop without blocking the CustomTkinter event thread.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import threading
from datetime import timedelta
from contextlib import AsyncExitStack
from urllib.parse import urlparse

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:  # clear error on feature use, keep the base app importable
    ClientSession = None
    streamablehttp_client = None


class MCPError(RuntimeError):
    pass


def validate_server_url(url: str) -> str:
    url = str(url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("https", "http") or not p.hostname:
        raise ValueError("MCP URL must be an absolute http:// or https:// URL")
    if p.username or p.password:
        raise ValueError("Do not put credentials in the URL; configure authentication separately")
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Remote MCP servers must use HTTPS; plain HTTP is allowed only for localhost")
    return url.rstrip("/")


def safe_tool_name(server_id: str, tool_name: str, used: set[str]) -> str:
    base = "mcp_" + re.sub(r"[^a-zA-Z0-9_-]", "_", server_id) + "_" + re.sub(
        r"[^a-zA-Z0-9_-]", "_", tool_name)
    base = base[:64].rstrip("_") or "mcp_tool"
    name, n = base, 2
    while name in used:
        suffix = f"_{n}"
        name = base[:64-len(suffix)] + suffix
        n += 1
    used.add(name)
    return name


def _json_schema(value):
    """Sanitize common JSON Schema values for OpenAI-compatible function tools."""
    if not isinstance(value, dict):
        return {"type": "object", "properties": {}, "additionalProperties": True}
    # MCP tools normally use JSON Schema. Copy recursively to avoid mutating SDK data.
    try:
        cleaned = json.loads(json.dumps(value))
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}, "additionalProperties": True}
    if cleaned.get("type") != "object":
        return {"type": "object", "properties": {}, "additionalProperties": True}
    cleaned.setdefault("properties", {})
    if not isinstance(cleaned.get("properties"), dict):
        cleaned["properties"] = {}
    if not isinstance(cleaned.get("required", []), list):
        cleaned.pop("required", None)
    return cleaned


def validate_tool_arguments(schema, arguments):
    """Validate the common JSON Schema constraints used by MCP tool inputs."""
    if not isinstance(arguments, dict):
        raise ValueError("MCP tool arguments must be a JSON object")
    schema = _json_schema(schema)
    required = schema.get("required", [])
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ValueError("Missing required MCP argument(s): " + ", ".join(map(str, missing)))
    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = set(arguments) - set(props)
        if extra: raise ValueError("Unknown MCP argument(s): " + ", ".join(sorted(extra)))
    types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
    for key, value in arguments.items():
        spec = props.get(key, {})
        expected = types.get(spec.get("type"))
        if expected and (not isinstance(value, expected) or (spec.get("type") == "integer" and isinstance(value, bool))):
            raise ValueError(f"MCP argument '{key}' must be {spec.get('type')}")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"MCP argument '{key}' is not an allowed value")
    return arguments


class RemoteMCPManager:
    def __init__(self, timeout: float = 20.0, call_timeout: float = 60.0):
        self.timeout = timeout
        self.call_timeout = call_timeout
        self._lock = threading.RLock()
        self._loop = None
        self._thread = threading.Thread(target=self._loop_thread, name="agent-code-mcp", daemon=True)
        self._ready = threading.Event()
        self._sessions = {}  # id -> {stack, session, tools, config}
        self._thread.start()
        self._ready.wait(timeout=5)

    def _loop_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def _run(self, coro, timeout=None):
        if self._loop is None or not self._ready.is_set():
            raise MCPError("MCP event loop is not available")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout or self.call_timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise MCPError("Remote MCP operation timed out") from None

    async def _connect(self, config):
        if ClientSession is None or streamablehttp_client is None:
            raise MCPError("Remote MCP requires the 'mcp' package. Install with: pip install 'mcp>=1.9,<2'")
        sid = str(config.get("id") or "").strip()
        if not sid:
            raise ValueError("Server configuration is missing its id")
        url = validate_server_url(config.get("url", ""))
        headers = config.get("headers") or {}
        if not isinstance(headers, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
            raise ValueError("Authentication headers must be a mapping of strings")
        # Prevent common credential leakage / malformed header injection.
        if any("\r" in k or "\n" in k or "\r" in v or "\n" in v for k, v in headers.items()):
            raise ValueError("Authentication headers contain invalid newline characters")
        with self._lock:
            old = self._sessions.pop(sid, None)
        if old:
            await old["stack"].aclose()
        stack = AsyncExitStack()
        try:
            read_stream, write_stream, *_ = await asyncio.wait_for(
                stack.enter_async_context(streamablehttp_client(url, headers=headers, timeout=timedelta(seconds=self.timeout),
                                     sse_read_timeout=timedelta(seconds=max(self.timeout, 60)))),
                timeout=self.timeout + 2)
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await asyncio.wait_for(session.initialize(), timeout=self.timeout)
            result = await asyncio.wait_for(session.list_tools(), timeout=self.timeout)
            tools = []
            for tool in (getattr(result, "tools", None) or []):
                name = getattr(tool, "name", None)
                if not isinstance(name, str) or not name.strip():
                    continue
                tools.append({"name": name, "description": str(getattr(tool, "description", "") or "")[:2000],
                              "inputSchema": _json_schema(getattr(tool, "inputSchema", None))})
            with self._lock:
                self._sessions[sid] = {"stack": stack, "session": session, "tools": tools,
                                       "config": {k: v for k, v in config.items() if k != "headers"}}
            return tools
        except Exception:
            await stack.aclose()
            raise

    def connect(self, config):
        return self._run(self._connect(dict(config)), timeout=self.timeout * 2 + 10)

    async def _disconnect(self, sid):
        with self._lock:
            entry = self._sessions.pop(str(sid), None)
        if entry:
            await entry["stack"].aclose()
        return bool(entry)

    def disconnect(self, server_id):
        return self._run(self._disconnect(server_id), timeout=self.timeout + 5)

    def is_connected(self, server_id):
        with self._lock:
            return str(server_id) in self._sessions

    def connected_tools(self, server_id=None):
        with self._lock:
            entries = list(self._sessions.items())
        result = []
        for sid, entry in entries:
            if server_id is None or sid == server_id:
                result.extend((sid, dict(tool)) for tool in entry["tools"])
        return result

    async def _call(self, sid, tool_name, arguments):
        with self._lock:
            entry = self._sessions.get(str(sid))
        if not entry:
            raise MCPError("Remote MCP server is disconnected; reconnect it and retry")
        tool_schema = next((t.get("inputSchema") for t in entry["tools"] if t.get("name") == tool_name), None)
        if tool_schema is None:
            raise MCPError(f"MCP tool '{tool_name}' is not in the current discovery list")
        try:
            validate_tool_arguments(tool_schema, arguments)
        except ValueError as exc:
            raise MCPError(f"Invalid arguments for MCP tool '{tool_name}': {exc}") from exc
        result = await asyncio.wait_for(entry["session"].call_tool(tool_name, arguments), timeout=self.call_timeout)
        parts = []
        for item in (getattr(result, "content", None) or []):
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
            else:
                parts.append(str(item))
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            parts.append(json.dumps(structured, ensure_ascii=False, default=str))
        output = "\n".join(parts) or "(remote tool returned no text content)"
        if getattr(result, "isError", False):
            return "REMOTE MCP TOOL ERROR: " + output[:12000]
        return output[:12000]

    def call_tool(self, server_id, original_name, arguments):
        return self._run(self._call(server_id, original_name, arguments), timeout=self.call_timeout + 5)

    async def _close_all(self):
        for sid in list(self._sessions):
            await self._disconnect(sid)

    def close(self):
        if self._loop and self._loop.is_running():
            try:
                self._run(self._close_all(), timeout=5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
