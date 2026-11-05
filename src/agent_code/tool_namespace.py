"""Global tool-name normalization for every Agent Code tool provider.

The provider-facing name is always ``<source>_<original_name>``.  The
callable and source identity remain private registry metadata so execution is
never inferred from a model-supplied name.
"""
from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Iterable

MAX_TOOL_NAME = 64


def _identifier(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_-")
    value = re.sub(r"_+", "_", value)
    return value.lower() or "tool"


def make_tool_name(namespace: str, original_name: str, used: set[str] | None = None,
                   max_length: int = MAX_TOOL_NAME) -> str:
    """Create a deterministic, provider-safe, collision-free tool name."""
    used = used if used is not None else set()
    prefix = _identifier(namespace)
    original = _identifier(original_name)
    raw = f"{prefix}_{original}"
    if len(raw) > max_length:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
        raw = f"{raw[:max_length - 9].rstrip('_-')}_{digest}"
    candidate = raw
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = f"{raw[:max_length - len(suffix)].rstrip('_-')}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


@dataclass(frozen=True)
class ToolIdentity:
    provider_name: str
    original_name: str
    namespace: str
    source_type: str


class UnifiedToolNamespace:
    """Builds one globally unique schema/callable registry.

    Register every source (Core, Skill, MCP, Add-on, Plugin, or future source)
    through this object.  The model only sees provider names; execution resolves
    through the private callable map.
    """
    def __init__(self, max_length: int = MAX_TOOL_NAME):
        self.max_length = max(16, min(int(max_length), MAX_TOOL_NAME))
        self.schemas: list[dict] = []
        self.callables: dict[str, Callable] = {}
        self.identities: dict[str, ToolIdentity] = {}
        self._used: set[str] = set()

    def register(self, namespace: str, source_type: str, schema: dict,
                 handler: Callable, *, original_name: str | None = None) -> str:
        if not isinstance(schema, dict) or not callable(handler):
            raise TypeError("tool registration requires a schema and callable handler")
        function = schema.get("function")
        if not isinstance(function, dict) or not function.get("name"):
            raise ValueError("tool schema is missing function.name")
        original = str(original_name or function["name"])
        provider_name = make_tool_name(namespace, original, self._used, self.max_length)
        cloned = deepcopy(schema)
        cloned["function"]["name"] = provider_name
        self.schemas.append(cloned)
        self.callables[provider_name] = handler
        self.identities[provider_name] = ToolIdentity(
            provider_name=provider_name,
            original_name=original,
            namespace=_identifier(namespace),
            source_type=str(source_type),
        )
        return provider_name

    def register_named(self, provider_name: str, namespace: str, source_type: str,
                       original_name: str, schema: dict, handler: Callable) -> str:
        """Register an already namespaced source name without double-prefixing."""
        if not isinstance(schema, dict) or not callable(handler):
            raise TypeError("tool registration requires a schema and callable handler")
        base = _identifier(provider_name)[:self.max_length].rstrip("_-") or "tool"
        candidate = base
        if candidate in self._used:
            digest = hashlib.sha256(
                f"{namespace}:{source_type}:{original_name}".encode("utf-8")
            ).hexdigest()[:8]
            suffix = "_" + digest
            candidate = base[:self.max_length-len(suffix)].rstrip("_-") + suffix
            counter = 2
            while candidate in self._used:
                tail = f"_{counter}"
                candidate = base[:self.max_length-len(tail)].rstrip("_-") + tail
                counter += 1
        self._used.add(candidate)
        cloned = deepcopy(schema)
        cloned.setdefault("function", {})["name"] = candidate
        self.schemas.append(cloned)
        self.callables[candidate] = handler
        self.identities[candidate] = ToolIdentity(
            provider_name=candidate, original_name=str(original_name),
            namespace=_identifier(namespace), source_type=str(source_type))
        return candidate

    def register_many(self, namespace: str, source_type: str,
                      schemas: Iterable[dict], callables: dict[str, Callable]) -> None:
        for schema in schemas:
            function = schema.get("function", {}) if isinstance(schema, dict) else {}
            original = function.get("name") if isinstance(function, dict) else None
            if not original:
                continue
            handler = callables.get(original)
            if handler is None:
                continue
            self.register(namespace, source_type, schema, handler, original_name=original)

    def resolve(self, provider_name: str) -> Callable | None:
        return self.callables.get(str(provider_name))

    def identity(self, provider_name: str) -> ToolIdentity | None:
        return self.identities.get(str(provider_name))

    def describe(self) -> list[dict]:
        return [identity.__dict__.copy() for identity in self.identities.values()]


def namespace_toolset(sources: Iterable[tuple[str, str, Iterable[dict], dict[str, Callable]]],
                      max_length: int = MAX_TOOL_NAME) -> UnifiedToolNamespace:
    registry = UnifiedToolNamespace(max_length=max_length)
    for namespace, source_type, schemas, callables in sources:
        registry.register_many(namespace, source_type, schemas, callables)
    return registry
