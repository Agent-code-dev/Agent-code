"""Extensible Agent Code add-on runtime.

Add-ons are trusted Python extensions installed in the per-user add-ons directory.
They can contribute tools, slash commands, lifecycle hooks, UI actions, and
capability metadata without modifying the core application or changing its AI model.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")


@dataclass
class AddonInfo:
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = "Unknown"
    path: str = ""
    enabled: bool = True
    error: str = ""


class AddonAPI:
    """Registration API exposed to one add-on during its register(api) call."""
    def __init__(self, addon_name: str):
        self.addon_name = addon_name
        self.tools: list[tuple[dict, Callable]] = []
        self.commands: dict[str, dict] = {}
        self.hooks: dict[str, list[Callable]] = {}
        self.actions: list[dict] = []
        self.ui_contributions: list[dict] = []
        self.services: list[dict] = []
        self.capabilities: list[str] = []

    def register_tool(self, schema: dict, handler: Callable):
        if not isinstance(schema, dict) or not callable(handler):
            raise TypeError("register_tool expects a tool schema and callable handler")
        fn = schema.get("function", {})
        name = fn.get("name") if isinstance(fn, dict) else None
        if not name or not _NAME_RE.fullmatch(name):
            raise ValueError("tool schema must contain a valid function.name")
        self.tools.append((schema, handler))

    def register_command(self, name: str, handler: Callable, description: str = ""):
        name = str(name).strip().lstrip("/")
        if not _NAME_RE.fullmatch(name) or not callable(handler):
            raise ValueError("command requires a valid name and callable handler")
        # Namespaced commands prevent collisions with built-in and skill commands.
        key = f"{self.addon_name}:{name}"
        self.commands[key] = {"handler": handler, "description": description,
                              "addon": self.addon_name}

    def on(self, event: str, callback: Callable):
        if not isinstance(event, str) or not event.strip() or not callable(callback):
            raise ValueError("on requires an event name and callable callback")
        self.hooks.setdefault(event.strip(), []).append(callback)

    def register_action(self, name: str, callback: Callable, description: str = ""):
        if not name or not callable(callback):
            raise ValueError("action requires a name and callable callback")
        self.actions.append({"name": str(name), "callback": callback,
                             "description": str(description)})

    def register_ui(self, name: str, builder: Callable, *, location: str = "addons",
                    label: str | None = None, description: str = ""):
        """Register a live UI contribution.

        Supported locations: sidebar, addons, settings, toolbar, workspace.
        builder(parent, app) must create and return a Tk/CustomTkinter widget.
        """
        allowed = {"sidebar", "addons", "settings", "toolbar", "workspace"}
        if location not in allowed or not callable(builder):
            raise ValueError(f"UI location must be one of {sorted(allowed)} and builder must be callable")
        self.ui_contributions.append({"addon": self.addon_name, "name": str(name),
            "label": str(label or name), "description": str(description),
            "location": location, "builder": builder})

    def register_service(self, name: str, implementation: Any, *, replaces: bool = False,
                         priority: int = 0, description: str = ""):
        """Register/replace a named application service (e.g. skill_store, skills_forge).

        The implementation may be an object or a factory(app). Core code opts into
        resolution via AddonManager.resolve_service; add-ons never silently rewrite
        arbitrary URLs or configuration values.
        """
        if not _NAME_RE.fullmatch(str(name)):
            raise ValueError("service name must be a valid identifier")
        if implementation is None or not (callable(implementation) or hasattr(implementation, "__dict__")):
            raise ValueError("service implementation must be an object or factory")
        self.services.append({"addon": self.addon_name, "name": str(name),
            "implementation": implementation, "replaces": bool(replaces),
            "priority": int(priority), "description": str(description)})

    def declare_capability(self, capability: str):
        if capability:
            self.capabilities.append(str(capability))


class AddonManager:
    def __init__(self, directory: Path, disabled: list[str] | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.disabled = set(disabled or [])
        self.infos: list[AddonInfo] = []
        self.apis: list[AddonAPI] = []
        self.schemas: list[dict] = []
        self.callables: dict[str, Callable] = {}
        self.commands: dict[str, dict] = {}
        self.actions: list[dict] = []
        self.ui_contributions: list[dict] = []
        self.services: dict[str, list[dict]] = {}
        self._loaded_modules = []

    def discover(self) -> list[AddonInfo]:
        found = []
        for folder in sorted(self.directory.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            manifest_path = folder / "addon.json"
            entry = folder / "addon.py"
            if not manifest_path.is_file() or not entry.is_file():
                continue
            try:
                meta = json.loads(manifest_path.read_text(encoding="utf-8"))
                name = str(meta.get("name") or folder.name)
                if not _NAME_RE.fullmatch(name):
                    raise ValueError("invalid add-on name")
                found.append(AddonInfo(name=name, version=str(meta.get("version", "0.0.0")),
                    description=str(meta.get("description", "")),
                    author=str(meta.get("author", "Unknown")), path=str(folder),
                    enabled=name not in self.disabled))
            except Exception as exc:
                found.append(AddonInfo(name=folder.name, path=str(folder), enabled=False,
                                       error=f"Invalid addon.json: {exc}"))
        self.infos = found
        return found

    def load(self):
        self.apis.clear(); self.schemas.clear(); self.callables.clear()
        self.commands.clear(); self.actions.clear(); self.ui_contributions.clear()
        self.services.clear(); self._loaded_modules.clear()
        for info in self.discover():
            if not info.enabled or info.error:
                continue
            entry = Path(info.path) / "addon.py"
            try:
                module_name = "agent_code_addon_" + re.sub(r"\W+", "_", info.name)
                spec = importlib.util.spec_from_file_location(module_name, entry)
                if spec is None or spec.loader is None:
                    raise ImportError("could not create add-on module loader")
                module = importlib.util.module_from_spec(spec)
                # Keep the add-on root importable so larger add-ons can ship
                # helper modules and packages beside addon.py.
                addon_root = str(Path(info.path))
                if addon_root not in sys.path:
                    sys.path.insert(0, addon_root)
                spec.loader.exec_module(module)
                api = AddonAPI(info.name)
                register = getattr(module, "register", None)
                if not callable(register):
                    raise TypeError("addon.py must export register(api)")
                register(api)
                for schema, handler in api.tools:
                    name = schema["function"]["name"]
                    if name in self.callables:
                        raise ValueError(f"duplicate add-on tool name: {name}")
                    self.schemas.append(schema); self.callables[name] = handler
                for name, definition in api.commands.items():
                    if name in self.commands:
                        raise ValueError(f"duplicate add-on command: {name}")
                    self.commands[name] = definition
                self.actions.extend(api.actions)
                self.ui_contributions.extend(api.ui_contributions)
                for service in api.services:
                    self.services.setdefault(service["name"], []).append(service)
                self.apis.append(api); self._loaded_modules.append(module)
            except Exception as exc:
                info.error = f"{type(exc).__name__}: {exc}"
                print(f"[addons] failed to load {info.name}: {info.error}")
        for entries in self.services.values():
            entries.sort(key=lambda item: (item["replaces"], item["priority"]), reverse=True)
        return self.schemas, self.callables, self.commands

    def resolve_service(self, name: str, default: Any = None, *, app: Any = None):
        """Return the highest-priority registered implementation, else default.

        Factories can declare ``addon_service_factory = True`` and receive app.
        """
        entries = self.services.get(name, [])
        if not entries:
            return default
        implementation = entries[0]["implementation"]
        if getattr(implementation, "addon_service_factory", False):
            return implementation(app)
        return implementation

    def build_ui(self, location: str, parent: Any, app: Any = None) -> list[Any]:
        """Build all UI contributions for a placement; failures are isolated."""
        built = []
        for item in list(self.ui_contributions):
            if item["location"] != location:
                continue
            try:
                widget = item["builder"](parent, app)
                if widget is not None:
                    built.append(widget)
            except Exception:
                print(f"[addons] UI contribution {item['addon']}:{item['name']} failed:\n{traceback.format_exc()}")
        return built

    def emit(self, event: str, **context: Any) -> list[Any]:
        results = []
        for api in list(self.apis):
            for callback in api.hooks.get(event, []):
                try:
                    results.append(callback(**context))
                except Exception:
                    print(f"[addons] hook {event!r} failed in {api.addon_name}:\n{traceback.format_exc()}")
        return results


def create_addon_template(directory: Path, name: str, description: str = "") -> Path:
    if not _NAME_RE.fullmatch(name):
        raise ValueError("Use 1-64 letters, numbers, dots, underscores or hyphens")
    folder = Path(directory) / name
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "addon.json").write_text(json.dumps({"name": name, "version": "1.0.0",
        "description": description, "author": ""}, indent=2) + "\n", encoding="utf-8")
    (folder / "addon.py").write_text('''"""Example Agent Code add-on."""\n\ndef register(api):\n    # Add tools, slash commands, lifecycle hooks, or UI actions here.\n    api.on("tools_loaded", on_tools_loaded)\n\n\ndef on_tools_loaded(**context):\n    # Keep hooks fast; do not block the UI thread.\n    return None\n''', encoding="utf-8")
    (folder / "README.md").write_text(f"# {name}\n\n{description}\n\nThis is a trusted Python extension. Review its code before enabling it.\n", encoding="utf-8")
    return folder
