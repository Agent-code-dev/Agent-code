"""Local model-protocol intelligence registry.

The SQLite database stores provider/model wire-protocol capabilities, not user
content or credentials. It is created lazily in Agent Code's per-user data dir.
All built-in records are deterministic defaults and can be updated by app code.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .paths import global_data_dir

_DB_NAME = "model_protocols.sqlite3"
_DB_LOCK = threading.RLock()
_SCHEMA_VERSION = 1
_INITIALIZED_PATHS: set[str] = set()

_BUILTIN_PROFILES = (
    {
        "provider": "qwen",
        "model_pattern": "*",
        "protocol": "openai_chat_completions",
        "tool_format": "structured_tool_calls",
        "thinking_format": "reasoning_content",
        "preserve_reasoning": True,
        "parallel_tool_calls": True,
        "tool_choice_modes": ["auto", "none"],
        "notes": "Qwen API deployments commonly expose OpenAI-compatible tool_calls. Preserve reasoning_content in assistant history when returned; support varies by model and endpoint.",
        "source": "Alibaba Cloud Model Studio function-calling and streaming documentation",
        "priority": 10,
    },
    {
        "provider": "minimax",
        "model_pattern": "*",
        "protocol": "openai_chat_completions",
        "tool_format": "structured_tool_calls",
        "thinking_format": "provider_metadata",
        "preserve_reasoning": True,
        "parallel_tool_calls": None,
        "tool_choice_modes": ["auto", "none"],
        "notes": "MiniMax API documentation describes structured message.tool_calls. Some native M2 inference templates may instead emit <minimax:tool_call> text; detect that explicit marker as a fallback. Capabilities differ by model/version and deployment.",
        "source": "MiniMax Open Platform conversation API documentation",
        "priority": 10,
    },
    {
        "provider": "deepseek",
        "model_pattern": "*",
        "protocol": "openai_chat_completions",
        "tool_format": "structured_tool_calls",
        "thinking_format": "reasoning_content_or_provider_metadata",
        "preserve_reasoning": True,
        "parallel_tool_calls": None,
        "tool_choice_modes": ["auto", "none"],
        "notes": "DeepSeek-compatible deployments may expose reasoning_content and structured tool_calls; verify capabilities against the selected endpoint/model version.",
        "source": "DeepSeek API compatibility profile; endpoint capabilities may vary",
        "priority": 10,
    },
    {
        "provider": "kimi",
        "model_pattern": "*",
        "protocol": "openai_chat_completions",
        "tool_format": "structured_tool_calls",
        "thinking_format": "reasoning_content",
        "preserve_reasoning": True,
        "parallel_tool_calls": None,
        "tool_choice_modes": ["auto", "none"],
        "notes": "Kimi thinking-mode tool turns may require retaining reasoning_content and the complete assistant tool_calls message.",
        "source": "Alibaba Cloud Model Studio Kimi function-calling guidance",
        "priority": 10,
    },
    {
        "provider": "glm",
        "model_pattern": "*",
        "protocol": "openai_chat_completions",
        "tool_format": "structured_tool_calls",
        "thinking_format": "provider_metadata",
        "preserve_reasoning": False,
        "parallel_tool_calls": None,
        "tool_choice_modes": ["auto", "none"],
        "notes": "GLM tool-calling capabilities and parameters vary by model generation and deployment endpoint.",
        "source": "OpenAI-compatible GLM deployment profile; verify endpoint capabilities",
        "priority": 10,
    },
    {
        "provider": "openai",
        "model_pattern": "*",
        "protocol": "openai_chat_completions",
        "tool_format": "structured_tool_calls",
        "thinking_format": "provider_metadata",
        "preserve_reasoning": False,
        "parallel_tool_calls": True,
        "tool_choice_modes": ["auto", "none", "required"],
        "notes": "Default OpenAI-compatible Chat Completions behavior; endpoint-specific extensions may override this profile.",
        "source": "OpenAI-compatible API baseline",
        "priority": 1,
    },
)


def database_path() -> Path:
    """Return the per-user database path without creating the database."""
    return global_data_dir() / _DB_NAME


def _connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize_database(path: str | Path | None = None) -> Path:
    """Create/migrate the local protocol catalog and seed built-in profiles."""
    target = Path(path) if path is not None else database_path()
    cache_key = str(target.expanduser().resolve())
    with _DB_LOCK:
        if cache_key in _INITIALIZED_PATHS and target.is_file():
            return target
    with _DB_LOCK, _connect(target) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS model_protocol_profiles (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model_pattern TEXT NOT NULL,
            protocol TEXT NOT NULL,
            tool_format TEXT NOT NULL,
            thinking_format TEXT NOT NULL,
            preserve_reasoning INTEGER NOT NULL DEFAULT 0,
            parallel_tool_calls INTEGER,
            tool_choice_modes_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 0,
            is_builtin INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, model_pattern, protocol)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_protocol_provider ON model_protocol_profiles(provider, priority DESC)")
        for profile in _BUILTIN_PROFILES:
            conn.execute("""INSERT OR IGNORE INTO model_protocol_profiles
                (id, provider, model_pattern, protocol, tool_format, thinking_format,
                 preserve_reasoning, parallel_tool_calls, tool_choice_modes_json,
                 notes, source, priority, is_builtin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (f"builtin:{profile['provider']}:{profile['model_pattern']}:{profile['protocol']}",
                 profile["provider"], profile["model_pattern"], profile["protocol"],
                 profile["tool_format"], profile["thinking_format"],
                 int(profile["preserve_reasoning"]),
                 None if profile["parallel_tool_calls"] is None else int(profile["parallel_tool_calls"]),
                 json.dumps(profile["tool_choice_modes"]), profile["notes"],
                 profile["source"], profile["priority"]))
        conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                     (str(_SCHEMA_VERSION),))
    try:
        target.chmod(0o600)
    except OSError:
        pass
    with _DB_LOCK:
        _INITIALIZED_PATHS.add(cache_key)
    return target


def _provider_key(provider: str = "", base_url: str = "", model: str = "") -> str:
    value = f"{provider} {base_url} {model}".lower()
    if "minimax" in value:
        return "minimax"
    if "qwen" in value or "dashscope" in value or "aliyun" in value or "maas.aliyuncs" in value:
        return "qwen"
    if "deepseek" in value:
        return "deepseek"
    if "kimi" in value or "moonshot" in value:
        return "kimi"
    if "glm" in value or "zhipu" in value or "bigmodel.cn" in value:
        return "glm"
    if "openai" in value:
        return "openai"
    # Keep custom provider identities distinct so their own profiles can be
    # registered without modifying the built-in provider list.
    label = str(provider or "").strip().lower()
    label = re.sub(r"[^a-z0-9_.-]+", "-", label).strip("-.")
    return label or "openai"


def resolve_model_profile(provider: str = "", model: str = "", base_url: str = "",
                          path: str | Path | None = None) -> dict[str, Any]:
    """Resolve the most specific provider/model profile without network access."""
    target = initialize_database(path)
    provider_key = _provider_key(provider, base_url, model)
    model_key = str(model or "").lower()
    with _DB_LOCK, _connect(target) as conn:
        rows = conn.execute("SELECT * FROM model_protocol_profiles WHERE provider=?",
                            (provider_key,)).fetchall()
    matches = []
    for row in rows:
        pattern = row["model_pattern"].lower()
        matched = pattern == "*" or pattern in model_key
        if matched:
            data = dict(row)
            data["tool_choice_modes"] = json.loads(data.pop("tool_choice_modes_json") or "[]")
            data["preserve_reasoning"] = bool(data["preserve_reasoning"])
            data["parallel_tool_calls"] = (None if data["parallel_tool_calls"] is None
                                            else bool(data["parallel_tool_calls"]))
            matches.append(data)
    if not matches:
        return {"provider": provider_key, "model_pattern": "*",
                "protocol": "openai_chat_completions",
                "tool_format": "structured_tool_calls", "thinking_format": "provider_metadata",
                "preserve_reasoning": False, "parallel_tool_calls": None,
                "tool_choice_modes": ["auto", "none"], "priority": 0}
    return max(matches, key=lambda item: (len(item["model_pattern"].replace("*", "")), item["priority"]))



def protocol_request_options(profile: dict[str, Any], *, has_tools: bool) -> dict[str, Any]:
    """Return only request parameters known to be supported by this profile."""
    options: dict[str, Any] = {}
    choices = set(profile.get("tool_choice_modes") or ())
    if has_tools and "auto" in choices:
        options["tool_choice"] = "auto"
    elif not has_tools and "none" in choices:
        options["tool_choice"] = "none"
    parallel = profile.get("parallel_tool_calls")
    if has_tools and parallel is not None:
        options["parallel_tool_calls"] = bool(parallel)
    return options


def reasoning_payload(message: Any, profile: dict[str, Any]) -> str | None:
    """Return provider reasoning metadata only when the profile requires it."""
    if not profile.get("preserve_reasoning"):
        return None
    value = getattr(message, "reasoning_content", None)
    if value is None and isinstance(message, dict):
        value = message.get("reasoning_content")
    return str(value) if value else None

def upsert_profile(profile: dict[str, Any], path: str | Path | None = None) -> None:
    """Add/update a protocol profile. Never accepts credential fields."""
    required = ("provider", "model_pattern", "protocol", "tool_format", "thinking_format")
    if not isinstance(profile, dict) or any(not str(profile.get(k, "")).strip() for k in required):
        raise ValueError("Profile must define provider, model_pattern, protocol, tool_format and thinking_format")
    safe = {k: profile[k] for k in required}
    if any("key" in str(k).lower() or "secret" in str(k).lower() or "token" in str(k).lower()
           for k in profile):
        raise ValueError("Protocol profiles must not contain credentials or secrets")
    target = initialize_database(path)
    pid = str(profile.get("id") or uuid.uuid4().hex)
    parallel = profile.get("parallel_tool_calls")
    with _DB_LOCK, _connect(target) as conn:
        conn.execute("""INSERT INTO model_protocol_profiles
            (id, provider, model_pattern, protocol, tool_format, thinking_format,
             preserve_reasoning, parallel_tool_calls, tool_choice_modes_json,
             notes, source, priority, is_builtin)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(provider, model_pattern, protocol) DO UPDATE SET
             tool_format=excluded.tool_format, thinking_format=excluded.thinking_format,
             preserve_reasoning=excluded.preserve_reasoning,
             parallel_tool_calls=excluded.parallel_tool_calls,
             tool_choice_modes_json=excluded.tool_choice_modes_json,
             notes=excluded.notes, source=excluded.source, priority=excluded.priority,
             updated_at=CURRENT_TIMESTAMP""",
            (pid, safe["provider"].lower(), safe["model_pattern"].lower(), safe["protocol"],
             safe["tool_format"], safe["thinking_format"],
             int(bool(profile.get("preserve_reasoning"))),
             None if parallel is None else int(bool(parallel)),
             json.dumps(profile.get("tool_choice_modes", ["auto", "none"])),
             str(profile.get("notes", "")), str(profile.get("source", "")),
             int(profile.get("priority", 50))))


def parse_minimax_text_tool_calls(content: str, known_tool_names: set[str] | None = None):
    """Parse complete MiniMax native text-template calls into OpenAI-like calls.

    Returns (calls, visible_text). Incomplete/malformed blocks are never executed.
    The parser is deliberately limited to MiniMax's explicit wrapper markers.
    """
    text = str(content or "")
    marker = "<minimax:tool_call>"
    close = "</minimax:tool_call>"
    calls = []
    visible = []
    cursor = 0
    while True:
        start = text.find(marker, cursor)
        if start < 0:
            visible.append(text[cursor:])
            break
        visible.append(text[cursor:start])
        end = text.find(close, start + len(marker))
        if end < 0:
            # Do not silently treat a partial call as a valid operation.
            visible.append(text[start:])
            break
        raw = text[start + len(marker):end]
        invoke_match = re.search(r"<invoke\s+name\s*=\s*(['\"])(.*?)\1\s*>(.*?)</invoke\s*>",
                                 raw, flags=re.I | re.S)
        if invoke_match:
            name = invoke_match.group(2).strip()
            body = invoke_match.group(3)
            params = {}
            for match in re.finditer(
                r"<parameter\s+name\s*=\s*(['\"])(.*?)\1\s*>(.*?)</parameter\s*>",
                body, flags=re.I | re.S):
                key = match.group(2).strip()
                value = re.sub(r"<[^>]+>", "", match.group(3)).strip()
                if key:
                    try:
                        params[key] = json.loads(value)
                    except (ValueError, TypeError):
                        params[key] = value
            # Some templates emit a JSON object as the invoke body.
            if not params and body.strip():
                try:
                    parsed = json.loads(body.strip())
                    if isinstance(parsed, dict):
                        params = parsed
                except ValueError:
                    pass
            if name and (known_tool_names is None or name in known_tool_names):
                from types import SimpleNamespace
                calls.append(SimpleNamespace(
                    id="call_" + uuid.uuid4().hex,
                    function=SimpleNamespace(name=name, arguments=json.dumps(params, ensure_ascii=False))))
            else:
                visible.append(text[start:end + len(close)])
        else:
            visible.append(text[start:end + len(close)])
        cursor = end + len(close)
    return calls, "".join(visible).strip()


class MiniMaxStreamTextFilter:
    """Keep native tool-call XML out of the live transcript while preserving text streaming."""
    OPEN = "<minimax:tool_call>"
    CLOSE = "</minimax:tool_call>"

    def __init__(self):
        self.pending = ""
        self.inside_call = False

    def feed(self, chunk: str) -> str:
        self.pending += str(chunk or "")
        output = []
        while self.pending:
            if self.inside_call:
                end = self.pending.find(self.CLOSE)
                if end < 0:
                    keep = max(0, len(self.CLOSE) - 1)
                    if len(self.pending) > keep:
                        self.pending = self.pending[-keep:] if keep else ""
                    break
                self.pending = self.pending[end + len(self.CLOSE):]
                self.inside_call = False
                continue
            start = self.pending.find(self.OPEN)
            if start >= 0:
                output.append(self.pending[:start])
                self.pending = self.pending[start + len(self.OPEN):]
                self.inside_call = True
                continue
            keep = max(0, len(self.OPEN) - 1)
            if len(self.pending) > keep:
                output.append(self.pending[:-keep] if keep else self.pending)
                self.pending = self.pending[-keep:] if keep else ""
            break
        return "".join(output)

    def finish(self) -> str:
        if self.inside_call:
            # An unfinished call is not displayed as executable markup.
            self.pending = ""
            return ""
        output, self.pending = self.pending, ""
        return output
