"""Interactive user questions and durable task-state primitives.

This module is UI-agnostic: the agent worker emits question events, while the
GUI/TUI renders them and calls ``answer_question``. It deliberately stores no
provider credentials, API keys, or private model reasoning.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Condition, RLock
from typing import Any, Callable
import json
import os
import tempfile
import time
import uuid


@dataclass(frozen=True)
class UserQuestion:
    question_id: str
    prompt: str
    options: tuple[str, ...] = ()
    allow_custom: bool = True
    allow_skip: bool = True
    title: str = "Agent Code needs your input"

    @classmethod
    def create(
        cls,
        prompt: str,
        options: list[str] | tuple[str, ...] | None = None,
        *,
        allow_custom: bool = True,
        allow_skip: bool = True,
        title: str = "Agent Code needs your input",
    ) -> "UserQuestion":
        prompt = str(prompt).strip()
        clean_options = tuple(dict.fromkeys(str(x).strip() for x in (options or ()) if str(x).strip()))
        if not prompt:
            raise ValueError("Question prompt cannot be empty")
        if len(prompt) > 4000:
            raise ValueError("Question prompt is too long")
        if len(clean_options) > 12:
            raise ValueError("A question can contain at most 12 options")
        return cls(uuid.uuid4().hex, prompt, clean_options, bool(allow_custom), bool(allow_skip), str(title))


@dataclass(frozen=True)
class UserAnswer:
    question_id: str
    choice: str | None = None
    custom_text: str | None = None
    skipped: bool = False


class AskUserBroker:
    """Bridges a background agent worker and a GUI/TUI without Tk calls off-thread.

    ``ask`` blocks only the agent worker, never the UI thread. ``on_question``
    should enqueue/display the event using the UI's normal thread-safe queue.
    """

    def __init__(self, on_question: Callable[[dict[str, Any]], None] | None = None):
        self._condition = Condition(RLock())
        self._pending: dict[str, UserQuestion] = {}
        self._answers: dict[str, UserAnswer] = {}
        self._on_question = on_question

    def ask(self, question: UserQuestion, timeout: float | None = None) -> UserAnswer:
        with self._condition:
            if question.question_id in self._pending:
                raise ValueError("Question is already pending")
            self._pending[question.question_id] = question
        event = {"type": "ask_user", "question": asdict(question)}
        if self._on_question:
            try:
                self._on_question(event)
            except Exception:
                with self._condition:
                    self._pending.pop(question.question_id, None)
                raise
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        with self._condition:
            while question.question_id not in self._answers:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self._pending.pop(question.question_id, None)
                    raise TimeoutError("Timed out waiting for the user's answer")
                self._condition.wait(remaining)
            answer = self._answers.pop(question.question_id)
            self._pending.pop(question.question_id, None)
            return answer

    def answer_question(
        self,
        question_id: str,
        *,
        choice: str | None = None,
        custom_text: str | None = None,
        skip: bool = False,
    ) -> UserAnswer:
        with self._condition:
            question = self._pending.get(str(question_id))
            if question is None:
                raise KeyError("Question is no longer pending")
            if skip:
                if not question.allow_skip:
                    raise ValueError("Skipping this question is disabled")
                answer = UserAnswer(question.question_id, skipped=True)
            elif custom_text is not None:
                value = str(custom_text).strip()
                if not question.allow_custom:
                    raise ValueError("Custom answers are disabled for this question")
                if not value:
                    raise ValueError("Custom answer cannot be empty")
                if len(value) > 4000:
                    raise ValueError("Custom answer is too long")
                answer = UserAnswer(question.question_id, custom_text=value)
            elif choice is not None:
                value = str(choice)
                if value not in question.options:
                    raise ValueError("Selected option is not part of this question")
                answer = UserAnswer(question.question_id, choice=value)
            else:
                raise ValueError("Provide a listed choice, custom answer, or skip")
            self._answers[question.question_id] = answer
            self._condition.notify_all()
            return answer

    def pending_questions(self) -> list[dict[str, Any]]:
        with self._condition:
            return [asdict(q) for q in self._pending.values()]

    def cancel_all(self) -> None:
        """Wake blocked workers with a cancellation answer (used on Stop)."""
        with self._condition:
            for question_id in tuple(self._pending):
                self._answers[question_id] = UserAnswer(question_id, skipped=True)
            self._condition.notify_all()


@dataclass
class TaskState:
    task_id: str
    objective: str
    status: str = "running"
    plan: list[dict[str, Any]] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    conversation: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskStateStore:
    """Atomic JSON persistence for plans and observable tool/task events."""

    VALID_STATUSES = {"queued", "running", "waiting_for_user", "completed", "failed", "stopped"}

    def __init__(self, path: str | Path, max_events: int = 500):
        self.path = Path(path).expanduser()
        self.max_events = max(20, int(max_events))
        self._lock = RLock()

    def save(self, state: TaskState) -> None:
        if state.status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid task status: {state.status}")
        payload = asdict(state)
        payload["trajectory"] = payload["trajectory"][-self.max_events:]
        payload["conversation"] = payload.get("conversation", [])[-120:]
        payload["updated_at"] = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, self.path)
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass
            finally:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def load(self) -> TaskState | None:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            if not isinstance(payload, dict):
                raise ValueError("Task state file must contain a JSON object")
            status = payload.get("status", "queued")
            if status not in self.VALID_STATUSES:
                raise ValueError("Task state contains an invalid status")
            return TaskState(
                task_id=str(payload["task_id"]),
                objective=str(payload.get("objective", "")),
                status=status,
                plan=list(payload.get("plan") or []),
                trajectory=list(payload.get("trajectory") or [])[-self.max_events:],
                conversation=list(payload.get("conversation") or [])[-120:],
                created_at=float(payload.get("created_at", time.time())),
                updated_at=float(payload.get("updated_at", time.time())),
            )

    def checkpoint(self, state: TaskState, conversation: list[dict[str, Any]], *, summary: str = "Safe execution checkpoint") -> None:
        """Persist a restartable conversation boundary after a complete tool result.

        Only JSON-compatible message data is stored. Binary image payloads are
        omitted; the original user objective remains available for recovery.
        Files are protected by the store's 0600 permissions.
        """
        clean: list[dict[str, Any]] = []
        for message in conversation[-120:]:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                continue
            item: dict[str, Any] = {"role": role}
            for key in ("content", "tool_call_id", "tool_calls", "name"):
                value = message.get(key)
                if key == "content" and isinstance(value, list):
                    # Image blocks may contain large base64/private payloads.
                    value = [part for part in value if isinstance(part, dict) and part.get("type") == "text"]
                    if not value:
                        value = "[image content omitted from recovery checkpoint]"
                try:
                    json.dumps(value, ensure_ascii=False)
                except (TypeError, ValueError):
                    continue
                if value is not None:
                    item[key] = value
            clean.append(item)
        state.conversation = clean
        state.trajectory.append({"time": time.time(), "kind": "checkpoint", "summary": summary[:240]})
        self.save(state)

    def delete(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


class TaskHistoryStore:
    """A bounded, per-user task archive with newest-first discovery.

    Each task is stored separately so starting a new task never overwrites the
    previous task's plan or trajectory. Legacy ``latest.json`` remains readable.
    """

    def __init__(self, directory: str | Path, *, max_tasks: int = 100):
        self.directory = Path(directory).expanduser()
        self.max_tasks = max(1, int(max_tasks))
        self._lock = RLock()

    def store_for(self, task_id: str) -> TaskStateStore:
        safe_id = str(task_id)
        if not safe_id or any(ch not in "0123456789abcdef-" for ch in safe_id.lower()):
            raise ValueError("Invalid task ID")
        return TaskStateStore(self.directory / f"{safe_id}.json")

    def save(self, state: TaskState) -> None:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.store_for(state.task_id).save(state)
            states = self.list_states()
            for old in states[self.max_tasks:]:
                if old.task_id != state.task_id:
                    self.store_for(old.task_id).delete()

    def get(self, task_id: str) -> TaskState | None:
        try:
            return self.store_for(task_id).load()
        except ValueError:
            return None

    def list_states(self, limit: int | None = None) -> list[TaskState]:
        with self._lock:
            if not self.directory.is_dir():
                return []
            states: list[TaskState] = []
            for path in self.directory.glob("*.json"):
                if path.name == "latest.json":
                    continue
                try:
                    state = TaskStateStore(path).load()
                    if state is not None:
                        states.append(state)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            states.sort(key=lambda item: (item.updated_at, item.created_at), reverse=True)
            if limit is not None:
                states = states[:max(0, int(limit))]
            return states

    def delete(self, task_id: str) -> None:
        self.store_for(task_id).delete()
