"""Shared WebUI API and scheduler used only by the authenticated server.

The desktop application is CustomTkinter; this module provides the independent
HTTP WebUI backend and static assets for `agent-code server`.
"""
from __future__ import annotations

import html
import json
import base64
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .settings_store import load_config, save_config

UI_DIR = Path(__file__).with_name("web_ui")


def render_markdown(source: str) -> str:
    """Render untrusted Markdown safely (raw HTML disabled) with Pygments."""
    text = str(source or "")
    try:
        from markdown_it import MarkdownIt
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name, TextLexer

        formatter = HtmlFormatter(style="monokai", nowrap=True)

        def code_renderer(code: str, language: str, _attrs: str) -> str:
            try:
                lexer = get_lexer_by_name(language or "text", stripall=False)
            except Exception:
                lexer = TextLexer()
            return highlight(code, lexer, formatter)

        parser = MarkdownIt("default", {"html": False, "typographer": True,
                                         "linkify": False, "highlight": code_renderer})
        body = parser.render(text)
        pygments_css = formatter.get_style_defs(".highlight")
        default_link_open = parser.renderer.rules.get("link_open")
        if default_link_open:
            def safe_link_open(tokens, idx, options, env):
                tokens[idx].attrSet("target", "_blank")
                tokens[idx].attrSet("rel", "noopener noreferrer")
                return default_link_open(tokens, idx, options, env)
            parser.renderer.rules["link_open"] = safe_link_open
            body = parser.render(text)
        return f"<style>{pygments_css}</style>" + body
    except Exception:
        return "<pre>" + html.escape(text) + "</pre>"


class WebviewRoot:
    """Minimal Tk-shaped scheduler used by the UI-independent Agent engine."""
    def __init__(self):
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.RLock()
        self._confirmations: dict[str, dict[str, Any]] = {}
        self._closed = threading.Event()

    def after(self, milliseconds: int, callback, *args):
        ident = uuid.uuid4().hex
        def invoke():
            with self._lock:
                self._timers.pop(ident, None)
            if not self._closed.is_set():
                try:
                    callback(*args)
                except Exception as exc:
                    print(f"[server scheduler] callback failed: {type(exc).__name__}: {exc}")
        timer = threading.Timer(max(0, int(milliseconds)) / 1000, invoke)
        timer.daemon = True
        with self._lock:
            self._timers[ident] = timer
        timer.start()
        return ident

    def after_idle(self, callback, *args):
        return self.after(0, callback, *args)

    def after_cancel(self, ident):
        with self._lock:
            timer = self._timers.pop(str(ident), None)
        if timer:
            timer.cancel()

    def askyesno(self, title, prompt):
        ident = uuid.uuid4().hex
        event = threading.Event()
        record = {"id": ident, "title": str(title), "prompt": str(prompt),
                  "event": event, "answer": False, "created": time.time()}
        with self._lock:
            self._confirmations[ident] = record
        # Agent worker blocks; the authenticated WebUI polls and resolves this request.
        if not event.wait(timeout=300):
            with self._lock:
                self._confirmations.pop(ident, None)
            return False
        with self._lock:
            self._confirmations.pop(ident, None)
        return bool(record["answer"])

    def pending_confirmations(self):
        with self._lock:
            return [{"id": x["id"], "title": x["title"], "prompt": x["prompt"]}
                    for x in self._confirmations.values()]

    def answer_confirmation(self, ident: str, answer: bool):
        with self._lock:
            record = self._confirmations.get(str(ident))
            if not record:
                return False
            record["answer"] = bool(answer)
            record["event"].set()
            return True

    def protocol(self, *_args, **_kwargs):
        return None

    def update_idletasks(self):
        return None

    def focus_get(self):
        return None

    def destroy(self):
        self._closed.set()
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
            confirmations = list(self._confirmations.values())
            self._confirmations.clear()
        for timer in timers:
            timer.cancel()
        for item in confirmations:
            item["answer"] = False
            item["event"].set()


class AgentWebAPI:
    """Narrow JS bridge. Methods validate inputs and delegate to core services."""
    def __init__(self, engine, root: WebviewRoot, window=None):
        self.engine = engine
        self.root = root
        self.window = window
        self._lock = threading.RLock()
        self._activity_cursor = 0

    def ready(self):
        return {"ok": True, "version": self._version(), "workspace": str(self._workspace())}

    @staticmethod
    def _version():
        from . import __version__
        return __version__

    @staticmethod
    def _workspace():
        from .paths import project_workspace_dir
        return project_workspace_dir()

    def get_state(self):
        engine = self.engine
        with self._lock:
            with getattr(engine, "_log_lock", threading.RLock()):
                history = list(getattr(engine, "_log_history", []))
            messages = []
            for item in list(getattr(engine, "messages", []))[-100:]:
                if not isinstance(item, dict) or item.get("role") == "system":
                    continue
                content = item.get("content", "")
                if isinstance(content, list):
                    # Preserve readable text while avoiding serializing binary image payloads.
                    content = "\n".join(str(part.get("text", "[image attachment]"))
                                        for part in content if isinstance(part, dict))
                if isinstance(content, str) and content:
                    messages.append({"role": str(item.get("role", "assistant")),
                                     "content": content[:100000],
                                     "html": render_markdown(content[:100000])})
            activity = []
            start = max(0, len(history) - 100)
            for text, tag in history[start:]:
                activity.append({"text": str(text)[:4000], "tag": str(tag or "")})
            cfg = load_config()
            return {
                "version": self._version(), "workspace": str(self._workspace()),
                "messages": messages, "activity": activity,
                "running": bool(getattr(engine, "_worker", None) and engine._worker.is_alive()),
                "status": str(getattr(engine, "_last_run_status", "idle")),
                "can_continue": bool(getattr(engine, "_can_continue", False)),
                "mode": str(getattr(engine, "execution_mode", "build")),
                "provider": str(getattr(engine, "provider_name", "OpenAI")),
                "model": str(getattr(engine, "model", "")),
                "permission": str(getattr(engine, "permission", "ask")),
                "questions": engine._ask_user_broker.pending_questions(),
                "confirmations": self.root.pending_confirmations(),
                "settings": {"skill_store_server": cfg.get("skill_store_server", "https://skills-manager.freesrv.com"),
                    "core_mode": bool(cfg.get("core_mode", False)),
                    "cloud_sync": bool(cfg.get("cloud_sync", False)),
                    "max_repair_attempts": int(cfg.get("max_repair_attempts", 3) or 0),
                    "provider_name": cfg.get("provider_name", "OpenAI"),
                    "openai_model": cfg.get("openai_model", ""),
                    "thinking_effort": cfg.get("thinking_effort", "off"),
                    "openai_base_url": cfg.get("openai_base_url", "https://api.openai.com/v1"),
                    "show_activity_details": bool(cfg.get("show_activity_details", True)),
                    "podman_sandbox_enabled": bool(cfg.get("podman_sandbox_enabled", False)),
                    "podman_container_name": str(cfg.get("podman_container_name", "") or ""),
                    "ultra_unrestricted_enabled": bool(cfg.get("ultra_unrestricted_enabled", False)),
                    "allow_unrestricted_host_shell": bool(cfg.get("allow_unrestricted_host_shell", False)),
                    "browser_executable_path": str(cfg.get("browser_executable_path", "")),
                    "browser_type": str(cfg.get("browser_type", "auto")),
                    "ssh_connection": cfg.get("ssh_connection", {}) if isinstance(cfg.get("ssh_connection", {}), dict) else {},
                    "cloud_user": str(getattr(engine, "cloud_user", "") or ""),
                    "provider_profiles": list((cfg.get("saved_providers", {}) or {}).keys()) if isinstance(cfg.get("saved_providers", {}), dict) else []},
            }

    def send_task(self, task: str, image_parts=None):
        task = str(task or "").strip()
        if not task:
            return {"ok": False, "error": "Write a task first."}
        if len(task) > 100000:
            return {"ok": False, "error": "Task is too long."}
        if self.engine._worker and self.engine._worker.is_alive():
            return {"ok": False, "error": "Agent Code is already working."}
        clean_images = []
        total_image_bytes = 0
        for item in (image_parts or [])[:8]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", ""))
            if not url.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,", "data:image/gif;base64,")):
                continue
            try:
                raw = base64.b64decode(url.split(",", 1)[1], validate=True)
            except Exception:
                continue
            if len(raw) > 12 * 1024 * 1024 or total_image_bytes + len(raw) > 24 * 1024 * 1024:
                continue
            total_image_bytes += len(raw)
            clean_images.append({"type": "image_url", "image_url": {"url": url}})
        if clean_images:
            self.engine._queued_image_parts = clean_images
        self.engine.log_line("\nYou\n" + task, "user")
        self.engine._stopped_last = False
        self.engine._can_continue = False
        self.engine._last_run_status = "running"
        self.engine._stop_event.clear()
        self.engine._set_running(True)
        worker = threading.Thread(target=self.engine._run_agent, args=(task,),
                                  daemon=True, name="agent-code-web-task")
        self.engine._worker = worker
        worker.start()
        return {"ok": True}

    def continue_task(self):
        """Continue the last interrupted turn using the existing agent continuation path."""
        if self.engine._worker and self.engine._worker.is_alive():
            return {"ok": False, "error": "Agent Code is already working."}
        if not bool(getattr(self.engine, "_can_continue", False)):
            return {"ok": False, "error": "There is no interrupted task to continue."}
        self.engine._can_continue = False
        self.engine._stopped_last = False
        self.engine._stop_event.clear()
        self.engine.log_line("\nYou\nContinue previous task", "user")
        self.engine._set_running(True)
        worker = threading.Thread(target=self.engine._run_agent, args=(None,), daemon=True,
                                  name="agent-code-web-continue")
        self.engine._worker = worker
        worker.start()
        return {"ok": True}

    def stop_task(self):
        self.engine._stop_event.set()
        self.engine._ask_user_broker.cancel_all()
        self.engine.log_line("[task] stop requested", "activity")
        return {"ok": True}

    def clear_chat(self):
        if self.engine._worker and self.engine._worker.is_alive():
            return {"ok": False, "error": "Stop the current task before clearing the chat."}
        self.engine.messages = [m for m in self.engine.messages if m.get("role") == "system"]
        self.engine._save_local_chat()
        self.engine.log_line("Started a new conversation.", "dim")
        return {"ok": True}

    def clear_activity(self):
        """Clear the visible activity history without interrupting a running task."""
        lock = getattr(self.engine, "_log_lock", threading.RLock())
        with lock:
            history = getattr(self.engine, "_log_history", None)
            if isinstance(history, list):
                history.clear()
        return {"ok": True}

    def set_mode(self, mode: str, approved: bool = False):
        mode = str(mode).lower()
        if mode not in {"plan", "build", "max"}:
            return {"ok": False, "error": "Unknown execution mode."}
        previous = str(getattr(self.engine, "execution_mode", "build"))
        if mode in {"build", "max"} and previous == "plan" and not approved:
            return {"ok": False, "requires_approval": True,
                    "message": "Build and Max allow file changes, subject to the configured permission policy."}
        self.engine.execution_mode = mode
        cfg = load_config(); cfg["execution_mode"] = mode; save_config(cfg)
        return {"ok": True, "mode": mode}

    def answer_question(self, question_id: str, choice=None, custom_text=None, skip=False):
        try:
            self.engine._ask_user_broker.answer_question(str(question_id), choice=choice,
                custom_text=custom_text, skip=bool(skip))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def answer_confirmation(self, confirmation_id: str, yes: bool):
        return {"ok": self.root.answer_confirmation(str(confirmation_id), bool(yes))}

    def get_workspace_entries(self, relative=""):
        """Return a bounded, secret-aware workspace tree for the WebUI."""
        root = self._workspace().resolve()
        raw = str(relative or "").strip().replace("\\", "/")
        try:
            candidate = root
            for part in Path(raw).parts:
                if part in {"", "."}:
                    continue
                candidate = candidate / part
                if candidate.is_symlink():
                    return {"entries": [], "error": "Symbolic links cannot be browsed."}
            base = candidate.resolve()
            base.relative_to(root)
        except (OSError, ValueError):
            return {"entries": [], "error": "Invalid workspace path."}
        if not base.is_dir():
            return {"entries": [], "error": "Workspace folder is unavailable."}
        skip = {".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules", "dist", "build", ".agent-code"}
        sensitive = {".ssh", ".aws", "credentials", "secrets", ".config"}
        entries = []
        try:
            for item in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.casefold())):
                if item.is_symlink() or item.name in skip or item.name.lower() in sensitive or item.name.lower().startswith(".env"):
                    continue
                if item.name.startswith("."):
                    continue
                rel = item.relative_to(root).as_posix()
                entries.append({"name": item.name, "path": rel, "is_dir": item.is_dir(),
                                "depth": min(2, len(Path(rel).parts)-1)})
                if len(entries) >= 300:
                    break
        except OSError as exc:
            return {"entries": [], "error": str(exc)}
        return {"entries": entries, "root": str(root)}

    def read_workspace_file(self, relative):
        """Read a small, non-sensitive regular file inside the active workspace."""
        root = self._workspace().resolve()
        rel = str(relative or "").strip().replace("\\", "/")
        try:
            candidate = root
            for part in Path(rel).parts:
                if part in {"", "."}:
                    continue
                candidate = candidate / part
                if candidate.is_symlink():
                    return {"ok": False, "error": "Symbolic links cannot be previewed."}
            target = candidate.resolve()
            target.relative_to(root)
            low = rel.lower()
            if any(part in low for part in (".env", ".ssh", ".aws", "credential", "secret", "id_rsa", "id_ed25519")):
                return {"ok": False, "error": "This file is not available in the workspace preview."}
            if not target.is_file():
                return {"ok": False, "error": "File not found."}
            if target.stat().st_size > 200_000:
                return {"ok": False, "error": "File is too large to preview (200 KB limit)."}
            data = target.read_bytes()
            if b"\x00" in data[:8192]:
                return {"ok": False, "error": "Binary files cannot be previewed."}
            return {"ok": True, "content": data.decode("utf-8", errors="replace")}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": f"Could not read file: {exc}"}

    def write_workspace_file(self, relative, content, create=False):
        """Save a UTF-8 text file strictly inside the active workspace."""
        root = self._workspace().resolve()
        rel = str(relative or "").strip().replace("\\", "/")
        text = str(content if content is not None else "")
        if not rel or len(rel) > 500 or len(text.encode("utf-8")) > 500_000:
            return {"ok": False, "error": "A file path is required and file content must be at most 500 KB."}
        low = rel.lower()
        blocked = (".env", ".ssh", ".aws", "credential", "secret", "id_rsa", "id_ed25519")
        if any(part in low for part in blocked):
            return {"ok": False, "error": "Editing sensitive files through the workspace IDE is disabled."}
        try:
            rel_path = Path(rel)
            parts = rel_path.parts
            if rel_path.is_absolute() or (parts and parts[0].endswith(":")) or any(part in {"", ".", "..", "/", "\\"} for part in parts):
                return {"ok": False, "error": "Invalid workspace path."}
            target = root.joinpath(*parts)
            parent = target.parent
            cursor = root
            for part in parts[:-1]:
                cursor = cursor / part
                if cursor.is_symlink():
                    return {"ok": False, "error": "Symbolic links cannot be edited."}
            parent_resolved = parent.resolve()
            parent_resolved.relative_to(root)
            if create and not parent_resolved.exists():
                parent.mkdir(parents=True, exist_ok=True)
                parent_resolved = parent.resolve()
                parent_resolved.relative_to(root)
            if not parent_resolved.is_dir() or target.is_symlink():
                return {"ok": False, "error": "Workspace folder or file is unavailable."}
            if target.exists() and not target.is_file():
                return {"ok": False, "error": "Only regular text files can be edited."}
            if not target.exists() and not create:
                return {"ok": False, "error": "File no longer exists. Use New file to create it."}
            if target.exists() and target.stat().st_size > 500_000:
                return {"ok": False, "error": "File is too large to edit (500 KB limit)."}
            # Recheck after directory creation to reduce symlink/path race exposure.
            target.resolve(strict=False).relative_to(root)
            temp = target.with_name(target.name + ".agent-code-tmp")
            temp.write_text(text, encoding="utf-8", newline="")
            temp.replace(target)
            return {"ok": True, "path": target.relative_to(root).as_posix(), "bytes": len(text.encode("utf-8"))}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": f"Could not save file: {exc}"}

    def get_todo(self):
        items = getattr(self.engine.todo, "items", [])
        return {"items": [{"content": str(x.get("content", "")), "status": str(x.get("status", "pending"))}
                           for x in items if isinstance(x, dict)]}

    def get_task_history(self):
        try:
            from .interactive import TaskHistoryStore
            from .paths import global_data_dir
            states = TaskHistoryStore(global_data_dir() / "tasks").list_states(20)
            return {"tasks": [{"task_id": x.task_id, "objective": x.objective, "status": x.status,
                               "created_at": x.created_at, "updated_at": x.updated_at,
                               "plan_count": len(x.plan), "event_count": len(x.trajectory),
                               "resumable": bool(x.conversation) and x.status in {"running", "stopped", "failed", "waiting_for_user"}}
                              for x in states]}
        except Exception as exc:
            return {"tasks": [], "error": str(exc)}

    def resume_task(self, task_id):
        """Resume a saved task from its last persisted safe conversation boundary."""
        try:
            from .interactive import TaskHistoryStore
            from .paths import global_data_dir
            task_id = str(task_id or "")
            state = TaskHistoryStore(global_data_dir() / "tasks").get(task_id)
            if state is None or not state.conversation:
                return {"ok": False, "error": "No recoverable conversation checkpoint is available for this task."}
            if self.engine._worker and self.engine._worker.is_alive():
                return {"ok": False, "error": "Stop the active task before resuming another task."}
            self.engine._resume_task_history_id = task_id
            self.engine._can_continue = False
            self.engine._stopped_last = False
            self.engine._stop_event.clear()
            self.engine._last_run_status = "running"
            self.engine.log_line(f"[task] resuming {task_id[:8]} from its latest safe checkpoint", "activity")
            self.engine._set_running(True)
            worker = threading.Thread(target=self.engine._run_agent, args=(None,), daemon=True,
                                      name="agent-code-web-resume")
            self.engine._worker = worker
            worker.start()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": f"Could not resume task: {type(exc).__name__}: {exc}"}

    def rerun_task(self, task_id):
        try:
            from .interactive import TaskHistoryStore
            from .paths import global_data_dir
            state = TaskHistoryStore(global_data_dir() / "tasks").get(str(task_id or ""))
            if state is None:
                return {"ok": False, "error": "Task history entry not found."}
            return self.send_task(state.objective)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_task_detail(self, task_id):
        try:
            from .interactive import TaskHistoryStore
            from .paths import global_data_dir
            state = TaskHistoryStore(global_data_dir() / "tasks").get(str(task_id or ""))
            if state is None:
                return {"ok": False, "error": "Task history entry not found."}
            return {"ok": True, "task": {"task_id": state.task_id, "objective": state.objective,
                    "status": state.status, "plan": state.plan[:100], "trajectory": state.trajectory[-100:],
                    "created_at": state.created_at, "updated_at": state.updated_at}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_checkpoints(self):
        try:
            rows = self.engine.checkpoints.history(30)
            return [{"id": str(x.get("id", "")), "label": str(x.get("label", "Task checkpoint")),
                     "created": x.get("created", 0), "status": "saved",
                     "files_changed": len(x.get("files", {}))} for x in rows]
        except Exception:
            return []

    def get_checkpoint_diff(self, checkpoint_id, relative):
        try:
            checkpoint_id = str(checkpoint_id or "")
            relative = str(relative or "")
            if not checkpoint_id or Path(checkpoint_id).name != checkpoint_id or any(x in checkpoint_id for x in ("/", "\\")):
                return {"ok": False, "error": "Invalid checkpoint ID."}
            if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
                return {"ok": False, "error": "Invalid checkpoint file path."}
            diff = self.engine.checkpoints.unified_diff(checkpoint_id, relative)
            return {"ok": True, "diff": diff}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def preview_checkpoint(self, checkpoint_id):
        try:
            checkpoint_id = str(checkpoint_id or "")
            if not checkpoint_id or Path(checkpoint_id).name != checkpoint_id or any(x in checkpoint_id for x in ("/", "\\")):
                return {"ok": False, "error": "Invalid checkpoint ID."}
            result = self.engine.checkpoints.preview_restore(checkpoint_id)
            actions = result.get("actions", [])
            return {"ok": True, "summary": f"{len(actions)} file(s) in this checkpoint. This is a preview; no files were changed.",
                    "actions": [{"path": str(x.get("path", "")), "action": str(x.get("action", "review"))} for x in actions],
                    "files": [f"{x.get('path', '')} — {x.get('action', x.get('status', 'review'))}" for x in actions]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_blueprint(self):
        try:
            data = self.engine.blueprint_store.load()
            return {"ok": True, "blueprint": data or {"title": "", "goal": "", "requirements": [],
                    "architecture": [], "milestones": [], "acceptance_criteria": []}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_blueprint(self, payload):
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Blueprint must be an object."}
        clean = {}
        clean["title"] = str(payload.get("title", "Untitled project")).strip()[:160]
        clean["goal"] = str(payload.get("goal", "")).strip()[:5000]
        for key in ("requirements", "architecture", "milestones", "acceptance_criteria"):
            raw = payload.get(key, [])
            if not isinstance(raw, list):
                return {"ok": False, "error": f"{key} must be a list."}
            clean[key] = [str(item).strip()[:1000] for item in raw[:100] if str(item).strip()]
        try:
            path = self.engine.blueprint_store.save(clean)
            return {"ok": True, "path": str(path)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_provider_profiles(self):
        cfg = load_config()
        profiles = cfg.get("saved_providers", {})
        if not isinstance(profiles, dict):
            profiles = {}
        return [{"name": str(name), "provider_name": str(item.get("provider_name", "OpenAI")),
                 "model": str(item.get("openai_model", "")),
                 "base_url": str(item.get("openai_base_url", "")),
                 "key_count": len(item.get("openai_api_keys", [])) if isinstance(item.get("openai_api_keys", []), list) else 0}
                for name, item in sorted(profiles.items()) if isinstance(item, dict)]

    def save_provider_profile(self, name, payload):
        name = str(name or "").strip()[:80]
        if not name or not isinstance(payload, dict):
            return {"ok": False, "error": "Enter a profile name and valid provider settings."}
        base = str(payload.get("openai_base_url", "")).strip().rstrip("/")
        if not base.startswith(("https://", "http://")):
            return {"ok": False, "error": "Provider URL must start with HTTPS or HTTP."}
        keys = payload.get("openai_api_keys", [])
        if isinstance(keys, str):
            keys = [x.strip() for x in keys.replace("\n", ",").split(",") if x.strip()]
        if not isinstance(keys, list):
            return {"ok": False, "error": "API keys must be a list."}
        clean_keys = list(dict.fromkeys(str(x).strip() for x in keys if str(x).strip()))[:20]
        cfg = load_config()
        profiles = cfg.get("saved_providers", {})
        if not isinstance(profiles, dict): profiles = {}
        # Reuse an existing profile for the same normalized endpoint and merge keys.
        def endpoint(value):
            from urllib.parse import urlsplit, urlunsplit
            u = urlsplit(str(value or "").strip())
            host = (u.hostname or "").lower()
            port = u.port
            if port and not ((u.scheme == "https" and port == 443) or (u.scheme == "http" and port == 80)):
                host += f":{port}"
            return urlunsplit((u.scheme.lower(), host, (u.path or "").rstrip("/"), "", "")).lower()
        existing = next((n for n, v in profiles.items() if isinstance(v, dict) and endpoint(v.get("openai_base_url")) == endpoint(base)), None)
        if existing and existing != name:
            prior = profiles.get(existing, {})
            merged = list(dict.fromkeys([*(prior.get("openai_api_keys", []) if isinstance(prior.get("openai_api_keys", []), list) else []), *clean_keys]))
            prior["openai_api_keys"] = merged[:20]
            profiles[existing] = prior
            save_config({**cfg, "saved_providers": profiles})
            return {"ok": True, "name": existing, "merged": True}
        previous = profiles.get(name, {}) if isinstance(profiles.get(name), dict) else {}
        if not clean_keys and endpoint(previous.get("openai_base_url")) == endpoint(base):
            clean_keys = list(previous.get("openai_api_keys", []))
        profiles[name] = {"provider_name": str(payload.get("provider_name", "OpenAI"))[:80],
                          "openai_api_keys": clean_keys,
                          "openai_base_url": base,
                          "openai_model": str(payload.get("openai_model", "")).strip()[:200]}
        save_config({**cfg, "saved_providers": profiles})
        return {"ok": True, "name": name, "merged": False}

    def apply_provider_profile(self, name):
        cfg = load_config()
        profile = (cfg.get("saved_providers", {}) or {}).get(str(name or ""))
        if not isinstance(profile, dict):
            return {"ok": False, "error": "Provider profile not found."}
        cfg.update({"provider_name": profile.get("provider_name", "OpenAI"),
                    "openai_api_keys": profile.get("openai_api_keys", []),
                    "openai_base_url": profile.get("openai_base_url", "https://api.openai.com/v1"),
                    "openai_model": profile.get("openai_model", "")})
        save_config(cfg)
        try:
            from .agent import make_client, normalize_keys
            self.engine.provider_name = str(cfg["provider_name"])
            self.engine.api_keys = normalize_keys(cfg["openai_api_keys"])
            self.engine.base_url = str(cfg["openai_base_url"])
            self.engine.model = str(cfg["openai_model"])
            self.engine.client = make_client(self.engine.api_keys, self.engine.base_url, self.engine.provider_name)
            return {"ok": True, "name": str(name)}
        except Exception as exc:
            return {"ok": False, "error": f"Profile saved but provider reload failed: {exc}"}

    def delete_provider_profile(self, name):
        cfg = load_config()
        profiles = cfg.get("saved_providers", {})
        if not isinstance(profiles, dict) or str(name or "") not in profiles:
            return {"ok": False, "error": "Provider profile not found."}
        profiles.pop(str(name), None)
        cfg["saved_providers"] = profiles
        save_config(cfg)
        return {"ok": True}

    def get_skills(self):
        from .agent import SKILLS_DIR
        from .loader import discover_skills
        from .claude_skills import discover_claude_skills
        engine = self.engine
        native = discover_skills(SKILLS_DIR)
        roots = [self._workspace() / ".claude" / "skills", Path.home() / ".claude" / "skills", Path(SKILLS_DIR)]
        claude = discover_claude_skills(roots)
        result = []
        for skill in native:
            result.append({"name": skill["name"], "description": skill.get("description", ""),
                           "kind": "python", "enabled": skill["name"] not in engine.disabled_skills,
                           "path": skill.get("path", "")})
        for skill in claude:
            key = "claude:" + skill["name"]
            result.append({"name": skill["name"], "description": skill.get("description", ""),
                           "kind": "claude", "enabled": skill["name"] not in engine.disabled_skills and key not in engine.disabled_skills,
                           "path": skill.get("path", "")})
        return result

    def toggle_skill(self, name: str, enabled: bool, kind: str = "python"):
        name = str(name).strip()
        if not name or len(name) > 120:
            return {"ok": False, "error": "Invalid skill name."}
        key = ("claude:" + name) if str(kind) == "claude" else name
        disabled = set(self.engine.disabled_skills)
        if enabled: disabled.discard(name); disabled.discard(key)
        else: disabled.add(key)
        self.engine.disabled_skills = sorted(disabled)
        self.engine._save_disabled_skills()
        self.engine._reload_tools()
        return {"ok": True}

    def get_addons(self):
        manager = self.engine.addon_manager
        infos = manager.discover()
        return [{"name": x.name, "version": x.version, "description": x.description,
                 "author": x.author, "enabled": x.enabled, "error": x.error,
                 "permissions": x.permissions, "api_version": x.api_version}
                for x in infos]

    def toggle_addon(self, name: str, enabled: bool):
        name = str(name).strip()
        if not name or len(name) > 64:
            return {"ok": False, "error": "Invalid add-on name."}
        disabled = set(self.engine.disabled_addons)
        if enabled: disabled.discard(name)
        else: disabled.add(name)
        self.engine.disabled_addons = sorted(disabled)
        cfg = load_config(); cfg["disabled_addons"] = self.engine.disabled_addons; save_config(cfg)
        self.engine._reload_tools()
        return {"ok": True}

    def get_web_addon_components(self, location: str = "addons"):
        allowed = {"sidebar", "addons", "settings", "toolbar", "workspace"}
        if location not in allowed:
            return []
        manager = self.engine.addon_manager
        return [dict(item) for item in manager.web_components if item.get("location") == location]

    def get_mcp_servers(self):
        connected = set()
        if self.engine.mcp_manager:
            connected = {sid for sid, _tool in self.engine.mcp_manager.connected_tools()}
        return [{"id": x["id"], "name": x["name"], "url": x["url"],
                 "enabled": bool(x.get("enabled", True)), "connected": x["id"] in connected,
                 "tool_count": len(self.engine.mcp_manager.connected_tools(x["id"])) if self.engine.mcp_manager else 0}
                for x in self.engine.mcp_servers]

    def add_mcp_server(self, name: str, url: str):
        name, url = str(name).strip(), str(url).strip()
        if not name or len(name) > 80:
            return {"ok": False, "error": "Enter a server name (maximum 80 characters)."}
        try:
            from .mcp_manager import validate_server_url
            validate_server_url(url)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if any(x["url"] == url for x in self.engine.mcp_servers):
            return {"ok": False, "error": "That MCP server URL is already configured."}
        server = {"id": uuid.uuid4().hex, "name": name, "url": url,
                  "enabled": True, "headers": {}, "auth_in_keyring": False, "last_tools": []}
        self.engine.mcp_servers.append(server)
        self.engine._save_mcp_servers()
        return {"ok": True}

    def connect_mcp(self, server_id: str):
        server = next((x for x in self.engine.mcp_servers if x["id"] == str(server_id)), None)
        if not server or not self.engine.mcp_manager:
            return {"ok": False, "error": "MCP server not found or MCP support is unavailable."}
        def connect():
            try:
                self.engine.mcp_manager.connect(server)
                self.engine._mcp_registry_changed()
                self.engine.log_line(f"[MCP] connected: {server['name']}", "activity")
            except Exception as exc:
                self.engine.log_line(f"[MCP] connection failed for {server['name']}: {exc}", "error")
        threading.Thread(target=connect, daemon=True, name="agent-code-mcp-connect").start()
        return {"ok": True, "started": True}

    def disconnect_mcp(self, server_id: str):
        try:
            self.engine.mcp_manager.disconnect(str(server_id))
            self.engine._mcp_registry_changed()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_store_addons(self, search: str = ""):
        from .addon_store import AddonStoreClient
        cfg = load_config()
        client = AddonStoreClient(cfg.get("skill_store_server", "https://skills-manager.freesrv.com"))
        return client.list_addons(str(search or "")[:100])

    def install_store_addon(self, name: str, expected_sha256: str = ""):
        from .addon_store import AddonStoreClient
        from .agent import ADDONS_DIR
        cfg = load_config()
        client = AddonStoreClient(cfg.get("skill_store_server", "https://skills-manager.freesrv.com"))
        try:
            expected = str(expected_sha256 or "").strip()
            if not expected:
                item = next((x for x in client.list_addons() if x.get("name") == str(name)), {})
                expected = str(item.get("sha256") or "")
            path = client.install_addon(str(name), ADDONS_DIR,
                                        expected_sha256=expected or None)
            self.engine._reload_tools()
            return {"ok": True, "path": str(path)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # Native Skills Store: separate from the add-on catalogue.
    @staticmethod
    def _skill_store_module():
        from . import skill_manager
        return skill_manager

    def get_skill_store_state(self):
        sm = self._skill_store_module()
        cfg = sm.load_config()
        return {"signed_in": bool(cfg.get("token")), "nickname": cfg.get("nickname") or "",
                "server": cfg.get("server") or sm.DEFAULT_SERVER,
                "published_count": len(cfg.get("my_skills", []) or [])}

    def skill_store_auth(self, mode: str, nickname: str, password: str):
        import re
        sm = self._skill_store_module()
        mode = str(mode or "login").lower()
        nickname, password = str(nickname or "").strip(), str(password or "")
        if mode not in {"login", "register"}:
            return {"ok": False, "error": "Invalid sign-in mode."}
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", nickname):
            return {"ok": False, "error": "Nickname must start with a letter and contain only letters, numbers, _ or - (maximum 64 characters)."}
        if len(password) < 4 or len(password) > 512:
            return {"ok": False, "error": "Password must contain between 4 and 512 characters."}
        cfg = sm.load_config()
        try:
            result = sm.api("POST", "/register" if mode == "register" else "/login", cfg,
                            {"nickname": nickname, "password": password})
            if not isinstance(result, dict) or not all(k in result for k in ("token", "nickname", "user_id")):
                raise sm.ApiError("The Skills Store returned an incomplete authentication response.")
            cfg.update({"token": result["token"], "nickname": result["nickname"],
                        "user_id": result["user_id"], "last_login": time.time()})
            sm.save_config(cfg)
            return {"ok": True, "nickname": cfg["nickname"]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500]}

    def skill_store_logout(self):
        sm = self._skill_store_module()
        cfg = sm.load_config()
        if cfg.get("token"):
            try: sm.api("POST", "/logout", cfg, {}, auth=True)
            except Exception: pass
        sm.clear_auth(cfg)
        return {"ok": True}

    def skill_store_list(self, search: str = ""):
        import urllib.parse
        sm = self._skill_store_module()
        cfg = sm.load_config()
        query = str(search or "").strip()[:100]
        path = "/skills" + ("?search=" + urllib.parse.quote(query) if query else "")
        try:
            result = sm.api("GET", path, cfg)
            skills = result.get("skills", []) if isinstance(result, dict) else []
            if not isinstance(skills, list): skills = []
            installed = {p.name for p in sm.SKILLS_DIR.iterdir() if p.is_dir()} if sm.SKILLS_DIR.exists() else set()
            mine = {x.get("name") for x in cfg.get("my_skills", []) if isinstance(x, dict)}
            safe = []
            for item in skills[:250]:
                if not isinstance(item, dict): continue
                row = {k: item.get(k) for k in ("name", "version", "author", "description", "downloads", "ai_verdict", "ai_summary", "ai_reasons", "report_count", "flagged")}
                row["installed"] = row.get("name") in installed
                row["mine"] = row.get("name") in mine
                safe.append(row)
            return {"ok": True, "skills": safe, "signed_in": bool(cfg.get("token"))}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500], "skills": []}

    def skill_store_detail(self, name: str):
        import re
        sm = self._skill_store_module()
        name = str(name or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name):
            return {"ok": False, "error": "Invalid skill name."}
        try:
            result = sm.api("GET", "/skills/" + name, sm.load_config())
            skill = result.get("skill") if isinstance(result, dict) else None
            if not isinstance(skill, dict): raise sm.ApiError("Invalid Skills Store response.")
            return {"ok": True, "skill": {k: skill.get(k) for k in ("name", "version", "author", "description", "downloads", "ai_verdict", "ai_summary", "ai_reasons", "report_count", "flagged")}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500]}

    def skill_store_install(self, name: str, allow_flagged: bool = False):
        import re, base64, shutil
        from pathlib import Path
        sm = self._skill_store_module()
        name = str(name or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name):
            return {"ok": False, "error": "Invalid skill name."}
        cfg = sm.load_config()
        if not cfg.get("token"):
            return {"ok": False, "error": "Sign in to the Skills Store before installing a skill."}
        try:
            meta = sm.api("GET", "/skills/" + name, cfg).get("skill", {})
            verdict = str(meta.get("ai_verdict") or "safe").lower()
            flagged = bool(meta.get("flagged")) or verdict in {"suspicious", "malicious"} or int(meta.get("report_count") or 0) > 0
            if flagged and not allow_flagged:
                return {"ok": False, "requires_confirmation": True, "verdict": verdict,
                        "warning": str(meta.get("ai_summary") or "This skill has safety reports. Review its details before installing.")}
            download = sm.api("GET", "/skills/" + name + "/download", cfg, auth=True)
            blob = base64.b64decode(download["zip_b64"], validate=True)
            root = Path(sm.SKILLS_DIR).expanduser()
            root.mkdir(parents=True, exist_ok=True)
            target, staging, backup = root / name, root / ("." + name + ".installing"), root / ("." + name + ".previous")
            for old in (staging, backup):
                if old.exists(): shutil.rmtree(old, ignore_errors=True)
            sm.extract_zip_safe(blob, staging)
            if not (staging / "skill.py").is_file():
                children = [x for x in staging.iterdir() if x.is_dir()]
                if len(children) == 1 and (children[0] / "skill.py").is_file():
                    nested = children[0]
                    for child in list(nested.iterdir()): shutil.move(str(child), str(staging / child.name))
                    nested.rmdir()
            if not (staging / "skill.py").is_file():
                shutil.rmtree(staging, ignore_errors=True)
                raise sm.ApiError("The downloaded archive does not contain skill.py.")
            if target.exists(): target.rename(backup)
            try: staging.rename(target)
            except Exception:
                if backup.exists() and not target.exists(): backup.rename(target)
                raise
            if backup.exists(): shutil.rmtree(backup, ignore_errors=True)
            self.engine._reload_tools()
            return {"ok": True, "path": str(target), "version": download.get("version", "")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500]}

    def connect_ssh(self, command: str = "", host: str = "", username: str = "", port: int = 22,
                    key_filename: str = "", password: str = ""):
        """Connect to a pre-trusted SSH host; unknown host keys are rejected, never auto-trusted."""
        try:
            import shlex
            import paramiko
            command = str(command or "").strip()
            host = str(host or "").strip()
            username = str(username or "").strip()
            key_filename = str(key_filename or "").strip()
            if command:
                parts = shlex.split(command)
                if not parts or Path(parts[0]).name != "ssh":
                    return {"ok": False, "error": "Enter a normal ssh command, such as ssh user@host."}
                positional = []
                index = 1
                while index < len(parts):
                    token = parts[index]
                    if token in {"-p", "-i", "-l", "-o", "-F", "-J", "-S", "-b", "-c", "-D", "-E", "-e", "-L", "-m", "-O", "-R", "-W", "-w"}:
                        if index + 1 >= len(parts):
                            return {"ok": False, "error": f"SSH option {token} needs a value."}
                        value = parts[index + 1]
                        if token == "-p": port = int(value)
                        elif token == "-i": key_filename = value
                        elif token == "-l": username = value
                        index += 2
                        continue
                    if token.startswith("-"):
                        index += 1
                        continue
                    positional.append(token)
                    index += 1
                target = positional[-1] if positional else ""
                if "@" in target:
                    username, host = target.split("@", 1)
                elif target:
                    host = target
            if not host or len(host) > 253:
                return {"ok": False, "error": "Enter a valid SSH hostname or alias."}
            port = int(port or 22)
            if not 1 <= port <= 65535:
                return {"ok": False, "error": "SSH port must be between 1 and 65535."}
            client = paramiko.SSHClient()
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            kwargs = {"hostname": host, "port": port, "username": username or None,
                      "timeout": 15, "banner_timeout": 15, "auth_timeout": 20,
                      "allow_agent": True, "look_for_keys": True}
            if key_filename: kwargs["key_filename"] = str(Path(key_filename).expanduser())
            if password: kwargs["password"] = str(password)
            client.connect(**kwargs)
            old = getattr(self.engine, "ssh_client", None)
            self.engine.ssh_client = client
            if old:
                try: old.close()
                except Exception: pass
            cfg = load_config()
            cfg["ssh_connection"] = {"command": command, "host": host, "username": username,
                                     "port": str(port), "key_filename": key_filename}
            save_config(cfg)
            self.engine.log_line(f"[SSH] connected to {username + '@' if username else ''}{host}:{port}", "activity")
            return {"ok": True, "host": host, "username": username}
        except ImportError:
            return {"ok": False, "error": "SSH support requires Paramiko. Install it with: pip install paramiko"}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:350]}"}

    def disconnect_ssh(self):
        client = getattr(self.engine, "ssh_client", None)
        self.engine.ssh_client = None
        if client:
            try: client.close()
            except Exception as exc: return {"ok": False, "error": str(exc)[:300]}
        self.engine.log_line("[SSH] disconnected", "activity")
        return {"ok": True}

    def list_provider_models(self, provider_name: str = "", base_url: str = "", raw_keys: str = ""):
        try:
            from .agent import make_client, normalize_keys
            provider_name = str(provider_name or self.engine.provider_name or "OpenAI")
            base_url = str(base_url or self.engine.base_url or "https://api.openai.com/v1").strip()
            keys = normalize_keys(raw_keys if raw_keys else load_config().get("openai_api_keys"))
            if not keys and provider_name != "Vireonix Free" and "vireonix.ai/v1" not in base_url.lower():
                return {"ok": False, "error": "Enter an API key before listing models." , "models": []}
            if not base_url.startswith(("https://", "http://")):
                return {"ok": False, "error": "Base URL must start with http:// or https://.", "models": []}
            client = make_client(keys, base_url, provider_name)
            client.timeout = 20.0
            response = client.models.list()
            data = getattr(response, "data", []) or []
            models = sorted({str(getattr(x, "id", "")).strip() for x in data if getattr(x, "id", None)}, key=str.casefold)
            return {"ok": True, "models": models[:500]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:400], "models": []}

    def podman_status(self):
        try:
            from .agent import (_podman_cli, _podman_state, _podman_container_name,
                                _podman_managed_container_name, _podman_list_workspace_containers)
            cli = _podman_cli()
            if not cli:
                return {"ok": True, "cli": "not installed", "state": "not installed", "containers": [],
                        "selected": _podman_container_name(), "managed": _podman_managed_container_name()}
            containers = _podman_list_workspace_containers()
            selected = _podman_container_name()
            # Keep the managed option visible even before its first creation.
            if not any(x["name"] == _podman_managed_container_name() for x in containers):
                containers.insert(0, {"id": "managed", "name": _podman_managed_container_name(), "status": "managed · not created"})
            return {"ok": True, "cli": cli, "state": _podman_state(selected), "containers": containers,
                    "selected": selected, "managed": _podman_managed_container_name()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300], "containers": []}

    def select_podman_container(self, name: str):
        """Persist a selected compatible container; never accept arbitrary container IDs."""
        try:
            from .agent import (_podman_managed_container_name, _podman_list_workspace_containers)
            name = str(name or "").strip()
            managed = _podman_managed_container_name()
            if name in {"", "__managed__", managed}:
                selected = ""
            else:
                allowed = {item["name"] for item in _podman_list_workspace_containers()}
                if name not in allowed:
                    return {"ok": False, "error": "That container is not available for this workspace. It must mount this project read-write at /workspace."}
                selected = name
            cfg = load_config()
            cfg["podman_container_name"] = selected
            save_config(cfg)
            actual = selected or managed
            self.engine.log_line(f"[Sandbox] Selected Podman container: {actual}", "activity")
            return {"ok": True, "selected": actual}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}

    def podman_action(self, action: str):
        action = str(action or "")
        if action not in {"start", "stop", "remove"}:
            return {"ok": False, "error": "Unsupported sandbox action."}
        def worker():
            try:
                from .agent import _podman_start, _podman_stop
                result = _podman_start() if action == "start" else _podman_stop(remove=(action == "remove"))
                self.engine.log_line(f"[Sandbox] {result}", "activity")
            except Exception as exc:
                self.engine.log_line(f"[Sandbox] {action} failed: {exc}", "error")
        threading.Thread(target=worker, daemon=True, name="agent-code-web-podman").start()
        return {"ok": True, "started": True}

    def save_settings(self, payload: dict):
        if not isinstance(payload, dict):
            return {"ok": False, "error": "Invalid settings payload."}
        cfg = load_config()
        allowed = {"provider_name", "openai_model", "openai_base_url", "skill_store_server",
                   "permission_mode", "execution_mode", "core_mode", "cloud_sync", "max_repair_attempts",
                   "show_activity_details", "podman_sandbox_enabled", "podman_os", "podman_network_enabled",
                   "podman_memory_mb", "podman_cpu_limit", "podman_pids_limit", "podman_workspace_access", "ultra_unrestricted_enabled",
                   "allow_unrestricted_host_shell", "browser_executable_path", "browser_type",
                   "ssh_connection", "thinking_effort"}
        for key in allowed:
            if key in payload:
                cfg[key] = payload[key]
        cfg["podman_os"] = str(cfg.get("podman_os", "alpine")).lower()
        if cfg["podman_os"] not in {"alpine", "ubuntu", "debian", "fedora"}:
            return {"ok": False, "error": "Unsupported Podman operating system."}
        cfg["podman_network_enabled"] = bool(cfg.get("podman_network_enabled", True))
        try:
            cfg["podman_memory_mb"] = max(256, min(16384, int(cfg.get("podman_memory_mb", 2048))))
            cfg["podman_cpu_limit"] = max(0.25, min(16.0, float(cfg.get("podman_cpu_limit", 2.0))))
            cfg["podman_pids_limit"] = max(64, min(4096, int(cfg.get("podman_pids_limit", 256))))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Invalid Podman resource limit."}
        cfg["podman_workspace_access"] = str(cfg.get("podman_workspace_access", "read-write")).lower()
        if cfg["podman_workspace_access"] not in {"read-write", "read-only"}:
            return {"ok": False, "error": "Invalid Podman workspace access mode."}
        cfg["thinking_effort"] = str(cfg.get("thinking_effort", "off")).lower()
        if cfg["thinking_effort"] not in {"off", "low", "medium", "high"}:
            return {"ok": False, "error": "Invalid thinking effort."}
        cfg["execution_mode"] = str(cfg.get("execution_mode", "build"))
        if cfg["execution_mode"] not in {"plan", "build", "max"}:
            return {"ok": False, "error": "Invalid execution mode."}
        if cfg.get("permission_mode") not in {"ask", "readonly", "auto"}:
            return {"ok": False, "error": "Invalid permission policy."}
        store_url = str(cfg.get("skill_store_server", "")).strip().rstrip("/")
        if not store_url.startswith("https://"):
            return {"ok": False, "error": "Skills Store URL must use HTTPS."}
        cfg["skill_store_server"] = store_url
        cfg["max_repair_attempts"] = max(0, min(3, int(cfg.get("max_repair_attempts", 3))))
        raw_keys = payload.get("api_keys", payload.get("api_key", ""))
        if isinstance(raw_keys, list):
            keys = [str(x).strip() for x in raw_keys if str(x).strip()]
        else:
            keys = [x.strip() for x in str(raw_keys or "").replace(",", "\n").splitlines() if x.strip()]
        if bool(payload.get("clear_api_keys", False)):
            cfg["openai_api_keys"] = []
        elif keys:
            cfg["openai_api_keys"] = keys
        browser_type = str(cfg.get("browser_type", "auto")).lower()
        if browser_type not in {"auto", "chromium", "firefox"}:
            return {"ok": False, "error": "Browser type must be auto, chromium, or firefox."}
        cfg["browser_type"] = browser_type
        cfg["browser_executable_path"] = str(cfg.get("browser_executable_path", "") or "").strip()
        ssh = cfg.get("ssh_connection", {})
        if not isinstance(ssh, dict):
            return {"ok": False, "error": "SSH connection settings must be an object."}
        cfg["ssh_connection"] = {k: str(ssh.get(k, ""))[:500] for k in ("command", "host", "username", "port", "key_filename")}
        cfg["allow_unrestricted_host_shell"] = bool(cfg.get("allow_unrestricted_host_shell", False))
        cfg["ultra_unrestricted_enabled"] = bool(cfg.get("ultra_unrestricted_enabled", False))
        if cfg["ultra_unrestricted_enabled"]:
            cfg["permission_mode"] = "auto"
        save_config(cfg)
        engine = self.engine
        engine.execution_mode = cfg["execution_mode"]
        engine.permission = "auto" if bool(cfg.get("ultra_unrestricted_enabled", False)) else cfg["permission_mode"]
        engine.security_config["permission_mode"] = engine.permission
        engine.ultra_unrestricted_enabled = bool(cfg.get("ultra_unrestricted_enabled", False))
        engine.allow_unrestricted_host_shell = bool(cfg.get("allow_unrestricted_host_shell", False) or engine.ultra_unrestricted_enabled)
        engine.core_mode = bool(cfg.get("core_mode", False))
        engine.cloud_sync = bool(cfg.get("cloud_sync", False))
        engine.max_repair_attempts = cfg["max_repair_attempts"]
        engine.provider_name = str(cfg.get("provider_name", "OpenAI"))
        engine.model = str(cfg.get("openai_model", ""))
        engine.thinking_effort = str(cfg.get("thinking_effort", "off"))
        engine.base_url = str(cfg.get("openai_base_url", "https://api.openai.com/v1"))
        try:
            from .agent import make_client, normalize_keys
            engine.api_keys = normalize_keys(cfg.get("openai_api_keys"))
            engine.client = make_client(engine.api_keys, engine.base_url, engine.provider_name)
        except Exception as exc:
            return {"ok": False, "error": f"Settings saved, but provider reload failed: {exc}"}
        engine._reload_tools()
        return {"ok": True, "restart_required": False}

    def open_workspace(self):
        from .agent import open_with_system_app
        try:
            open_with_system_app(self._workspace())
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def pick_files(self):
        """Native file dialogs are unavailable in a remote browser session."""
        return {"ok": False, "error": "Use the browser file-upload control. The server cannot open a file dialog on the connected device."}
