"""Runtime coordination primitives used by Agent Code's execution loop."""
from __future__ import annotations

import hashlib
import json
import os
import re
import difflib
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable


_VOLATILE_TOOLS = {"task_status", "todo_read", "todo_write", "finish_plan"}
_READ_TOOLS = {"read_file", "glob_files", "grep_files", "web_search", "web_fetch", "project_context"}


def _stable(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        return repr(value)


class ProgressTracker:
    """Tracks observable work, not model-private reasoning."""
    def __init__(self):
        self.reset()

    def reset(self, objective: str = "") -> None:
        self.objective = str(objective)
        self.started_at = time.monotonic()
        self.completed: list[dict] = []
        self.pending: list[str] = []
        self.last_change = self.started_at
        self.tool_calls = 0
        self.unique_calls: set[str] = set()

    def record(self, name: str, args: dict, result: Any) -> None:
        fingerprint = hashlib.sha256((name + "\0" + _stable(args)).encode()).hexdigest()[:16]
        result_text = str(result or "")
        self.tool_calls += 1
        self.unique_calls.add(fingerprint)
        self.completed.append({"tool": name, "fingerprint": fingerprint,
                               "success": not result_text.lstrip().startswith(("ERROR", "DENIED", "BLOCKED")),
                               "summary": result_text[:180]})
        self.completed = self.completed[-100:]
        self.last_change = time.monotonic()

    @property
    def unique_ratio(self) -> float:
        return len(self.unique_calls) / max(1, self.tool_calls)

    @property
    def idle_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.last_change)

    def snapshot(self) -> dict:
        return {"objective": self.objective, "tool_calls": self.tool_calls,
                "unique_tool_calls": len(self.unique_calls),
                "recent_actions": self.completed[-12:],
                "idle_seconds": round(self.idle_seconds, 2)}


class AgentLoopGuard:
    """Detects duplicate calls and reuses safe, unchanged file-read results."""
    def __init__(self, max_identical_calls: int = 2, max_similar_searches: int = 3,
                 cache_reads: bool = True, workspace: str | Path | None = None):
        self.max_identical_calls = max(1, int(max_identical_calls))
        self.max_similar_searches = max(1, int(max_similar_searches))
        self.cache_reads = bool(cache_reads)
        self.workspace = Path(workspace).expanduser().resolve() if workspace else None
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.RLock()):
            self.calls: dict[str, int] = {}
            self.searches: deque[str] = deque(maxlen=30)
            self.read_cache: dict[tuple, str] = {}
            self.file_read_counts: dict[str, int] = {}
            self.last_results: dict[str, str] = {}

    @staticmethod
    def _search_key(name: str, args: dict) -> str:
        query = str(args.get("pattern") or args.get("query") or args.get("q") or "")
        query = re.sub(r"\W+", " ", query.casefold()).strip()
        path = str(args.get("path") or ".")
        glob = str(args.get("glob") or "")
        return f"{name}:{path}:{glob}:{query}"

    def _read_signature(self, args: dict) -> tuple | None:
        raw = args.get("path")
        if not raw:
            return None
        try:
            path = Path(raw).expanduser()
            if not path.is_absolute() and self.workspace is not None:
                path = self.workspace / path
            path = path.resolve()
            stat = path.stat()
            if not path.is_file():
                return None
            return (str(path), stat.st_ino, stat.st_mtime_ns, stat.st_size,
                    args.get("offset", 0), args.get("limit"))
        except (OSError, ValueError):
            return None

    def cached_read(self, name: str, args: dict) -> str | None:
        if not self.cache_reads or name not in {"read_file", "core_read_file"}:
            return None
        signature = self._read_signature(args)
        if signature is None:
            return None
        with self._lock:
            return self.read_cache.get(signature)

    def record_read(self, name: str, args: dict, result: Any) -> None:
        if not self.cache_reads or name not in {"read_file", "core_read_file"}:
            return
        signature = self._read_signature(args)
        if signature is not None and not str(result).startswith("ERROR"):
            with self._lock:
                self.read_cache[signature] = str(result)
                while len(self.read_cache) > 64:
                    self.read_cache.pop(next(iter(self.read_cache)))

    def before_call(self, name: str, args: dict) -> str | None:
        if name in _VOLATILE_TOOLS:
            return None
        fingerprint_payload = {"args": args}
        if name in {"read_file", "core_read_file"}:
            fingerprint_payload["file_signature"] = self._read_signature(args)
        fingerprint = hashlib.sha256((name + "\0" + _stable(fingerprint_payload)).encode()).hexdigest()
        with self._lock:
            count = self.calls.get(fingerprint, 0) + 1
            self.calls[fingerprint] = count
            if count > self.max_identical_calls:
                previous = self.last_results.get(fingerprint, "")
                return (f"LOOP_GUARD: blocked repeated identical call to {name}; "
                        f"the same arguments were already tried {count - 1} times. "
                        "Use the previous result, change the arguments, or choose a different strategy. "
                        f"Previous result summary: {previous[:240]}")
            if name in {"read_file", "core_read_file"}:
                signature = self._read_signature(args)
                if signature is not None:
                    path_key = signature[0]
                    file_count = self.file_read_counts.get(path_key, 0) + 1
                    self.file_read_counts[path_key] = file_count
                    max_reads = 16 if signature[3] > 1024 * 1024 else 8
                    if file_count > max_reads:
                        return (f"LOOP_GUARD: read_file has inspected {path_key} {file_count} times. "
                                "Stop rereading the same file; use targeted search, inspect a narrower "
                                "range, or make the change based on the information already collected.")
            if name in {"web_search", "grep_files", "glob_files"}:
                key = self._search_key(name, args)
                self.searches.append(key)
                key_parts = key.split(":", 3)
                query_tokens = set(key_parts[3].split()) if len(key_parts) == 4 else set()
                similar = 0
                for old in self.searches:
                    old_parts = old.split(":", 3)
                    if len(old_parts) != 4 or old_parts[:3] != key_parts[:3]:
                        continue
                    old_tokens = set(old_parts[3].split())
                    if old == key or (query_tokens and old_tokens and
                                      len(query_tokens & old_tokens) / max(1, len(query_tokens | old_tokens)) >= 0.72):
                        similar += 1
                if similar > self.max_similar_searches:
                    return (f"LOOP_GUARD: repeated search for the same target ({name}). "
                            "Use the existing results or inspect a different source/path.")
        return None

    def after_call(self, name: str, args: dict, result: Any) -> None:
        fingerprint_payload = {"args": args}
        if name in {"read_file", "core_read_file"}:
            fingerprint_payload["file_signature"] = self._read_signature(args)
        fingerprint = hashlib.sha256((name + "\0" + _stable(fingerprint_payload)).encode()).hexdigest()
        with self._lock:
            self.last_results[fingerprint] = str(result or "")[:500]
        self.record_read(name, args, result)


class HookBus:
    """Ordered lifecycle hooks with isolated failures and optional veto hooks."""
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}
        self._lock = threading.RLock()

    def register(self, event: str, callback: Callable) -> None:
        if not str(event).strip() or not callable(callback):
            raise ValueError("hook requires a non-empty event and callable")
        with self._lock:
            self._hooks.setdefault(str(event).strip(), []).append(callback)

    def emit(self, event: str, *, fail_closed: bool = False, **context) -> list[Any]:
        with self._lock:
            callbacks = tuple(self._hooks.get(event, ()))
        results = []
        for callback in callbacks:
            try:
                value = callback(**context)
                results.append(value)
                if fail_closed and value is False:
                    raise PermissionError(f"Execution vetoed by hook: {event}")
            except Exception:
                if fail_closed:
                    raise
        return results


class PermissionEngine:
    """Central policy for tool permissions, independent of provider naming."""
    READ_ONLY = {"read_file", "glob_files", "grep_files", "todo_read", "web_search",
                 "web_fetch", "project_context", "review_changes", "finish_plan", "task_status"}
    STATEFUL = {"write_file", "append_file", "edit_file", "shell_run", "background_shell",
                "remote_shell", "todo_write", "task", "validate_project", "create_project"}

    @staticmethod
    def original_name(name: str, identity=None) -> str:
        if identity is not None:
            return identity.original_name
        value = str(name)
        if value.startswith("core_"):
            return value[5:]
        return value

    def classify(self, name: str, identity=None) -> str:
        original = self.original_name(name, identity)
        if original in self.READ_ONLY:
            return "read"
        if original in self.STATEFUL:
            return "stateful"
        if str(name).startswith("mcp_") or (identity and identity.source_type in {"mcp", "addon", "skill"}):
            return "extension"
        return "extension"


class PlanningEngine:
    """Small deterministic planning policy; the model creates the actual plan."""
    COMPLEXITY_MARKERS = (
        "implement", "build", "refactor", "redesign", "architecture", "integrate",
        "migrate", "multiple", "entire", "whole project", "end-to-end", "system",
    )

    def analyze(self, task: str) -> dict:
        value = str(task or "").strip().casefold()
        markers = [marker for marker in self.COMPLEXITY_MARKERS if marker in value]
        complex_task = len(value) >= 220 or len(markers) >= 2 or any(
            phrase in value for phrase in ("whole project", "end-to-end", "from scratch", "all modules"))
        return {"planning_required": bool(complex_task),
                "parallelizable": bool(complex_task and any(
                    word in value for word in ("frontend", "backend", "tests", "documentation", "independent", "parallel"))),
                "signals": markers[:8]}

    def directive(self, task: str, *, delegation_required: bool = False) -> str:
        decision = self.analyze(task)
        if not decision["planning_required"] and not delegation_required:
            return "For a small, local change, inspect the relevant code and proceed directly."
        parts = [
            "TASK PLANNING: Before changing files, identify the affected components, dependencies, risks, and acceptance checks. "
            "For multi-step work, create/update the task checklist with todo_write and keep it synchronized with actual progress. "
            "Revise the plan when evidence changes; do not repeat exploration that has already produced the needed facts."
        ]
        if decision["parallelizable"] or delegation_required:
            parts.append("Identify independent work packages and delegate suitable packages to subagents; keep conflicting file ownership separate.")
        if delegation_required:
            parts.append("The user explicitly requested subagents: at least one real task-tool delegation and result integration is mandatory before finalizing.")
        return " ".join(parts)


class VerificationEngine:
    """Tracks verification attempts and gates task completion on observable checks."""
    def __init__(self, max_attempts: int = 4):
        self.max_attempts = max(1, int(max_attempts))
        self.reset()

    def reset(self):
        self.attempted = False
        self.attempts = 0
        self.last_result = None

    def should_verify(self, *, changed_paths, status: str, already_verified: bool = False) -> bool:
        return bool(changed_paths and status not in {"error", "stopped"}
                    and not already_verified and self.attempts < self.max_attempts)

    def record(self, result: Any):
        self.attempted = True
        self.attempts += 1
        self.last_result = result

    def summary(self) -> dict:
        return {"attempted": self.attempted, "attempts": self.attempts,
                "last_result": self.last_result}


class SkillExecutionRouter:
    """Routes a Skill callable to an explicitly declared execution provider.

    Host execution is built in. Sandbox/SSH providers are injected by the
    application. Missing providers fail closed; there is never an implicit
    fallback to the host for a Skill that requested a remote environment.
    """
    def __init__(self, providers: dict[str, Callable] | None = None):
        self.providers = {"host": lambda handler, args, context: handler(**args)}
        self.providers.update(providers or {})

    def execute(self, *, target: str, handler: Callable, args: dict, context: dict | None = None):
        target = str(target or "host").strip().lower()
        if target == "auto":
            target = str((context or {}).get("default_target") or "host").lower()
        allowed = (context or {}).get("allowed_targets")
        if isinstance(allowed, (list, tuple, set)) and allowed:
            allowed = {str(item).strip().lower() for item in allowed}
            if target not in allowed:
                raise RuntimeError(f"Skill execution target '{target}' is not allowed by this Skill; permitted: {', '.join(sorted(allowed))}")
        provider = self.providers.get(target)
        if provider is None:
            raise RuntimeError(f"Skill requires '{target}' execution, but that execution provider is not available. No host fallback was attempted.")
        return provider(handler, dict(args), dict(context or {}))


def skill_execution_target(metadata: dict, tool_name: str) -> str:
    """Resolve per-Skill execution target; tool overrides take precedence."""
    execution = metadata.get("execution", {}) if isinstance(metadata, dict) else {}
    if not isinstance(execution, dict):
        return "host"
    per_tool = execution.get("tools", {})
    if isinstance(per_tool, dict) and isinstance(per_tool.get(tool_name), dict):
        target = str(per_tool[tool_name].get("target") or execution.get("target") or "host")
    else:
        target = str(execution.get("target") or "host")
    target = target.strip().lower()
    if target not in {"host", "sandbox", "ssh", "auto"}:
        raise ValueError(f"Unsupported Skill execution target: {target}")
    allowed = execution.get("allowed")
    if isinstance(allowed, (list, tuple, set)) and allowed:
        allowed = {str(item).strip().lower() for item in allowed}
        if target != "auto" and target not in allowed:
            raise ValueError(f"Skill execution target '{target}' is not in its allowed environments")
    return target
