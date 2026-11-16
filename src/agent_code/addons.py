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
from .tool_namespace import make_tool_name
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
    permissions: list[str] = field(default_factory=list)
    api_version: int = 1


class AddonAPI:
    """Registration API exposed to one add-on during its register(api) call."""
    def __init__(self, addon_name: str):
        self.addon_name = addon_name
        self.tools: list[tuple[dict, Callable]] = []
        self.commands: dict[str, dict] = {}
        self.hooks: dict[str, list[Callable]] = {}
        self.actions: list[dict] = []
        self.ui_contributions: list[dict] = []
        self.web_components: list[dict] = []
        self.services: list[dict] = []
        self.capabilities: list[str] = []
        self.web_components: list[dict] = []

    def register_tool(self, schema: dict, handler: Callable):
        if not isinstance(schema, dict) or not callable(handler):
            raise TypeError("register_tool expects a tool schema and callable handler")
        fn = schema.get("function", {})
        if schema.get("type") != "function" or not isinstance(fn, dict):
            raise ValueError("tool schema must be an OpenAI function tool schema")
        params = fn.get("parameters", {})
        if not isinstance(params, dict) or params.get("type") not in (None, "object"):
            raise ValueError("tool parameters must be a JSON Schema object")
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
                    label: str | None = None, description: str = "", backend: str = "tk"):
        """Register a live UI contribution.

        Supported locations: sidebar, addons, settings, toolbar, workspace.
        builder(parent, app) must create and return a CustomTkinter widget.
        The authenticated WebUI uses register_web_component instead.
        """
        allowed = {"sidebar", "addons", "settings", "toolbar", "workspace"}
        if location not in allowed or not callable(builder):
            raise ValueError(f"UI location must be one of {sorted(allowed)} and builder must be callable")
        backend = str(backend).lower()
        if backend != "tk":
            raise ValueError("register_ui supports backend='tk'; use register_web_component for WebUI")
        self.ui_contributions.append({"addon": self.addon_name, "name": str(name),
            "label": str(label or name), "description": str(description),
            "location": location, "backend": backend, "builder": builder})

    def register_web_component(self, name: str, *, html: str = "", css: str = "",
                               javascript: str = "", location: str = "addons",
                               label: str | None = None, description: str = ""):
        """Register a trusted authenticated WebUI contribution.

        Add-on authors should keep components self-contained and must not put
        credentials or untrusted user data into executable markup/scripts.
        Web components are mounted by the authenticated server WebUI; the same
        add-on's tools, hooks and commands remain available to every interface.
        """
        allowed = {"sidebar", "addons", "settings", "toolbar", "workspace"}
        if location not in allowed or not _NAME_RE.fullmatch(str(name)):
            raise ValueError("web component requires a valid name and supported location")
        if any(len(str(value)) > 128_000 for value in (html, css, javascript)):
            raise ValueError("web component assets are limited to 128 KB each")
        self.web_components.append({"addon": self.addon_name, "name": str(name),
            "label": str(label or name), "description": str(description),
            "location": location, "html": str(html), "css": str(css),
            "javascript": str(javascript)})

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
        self.tool_identities: dict[str, dict] = {}
        self.commands: dict[str, dict] = {}
        self.actions: list[dict] = []
        self.ui_contributions: list[dict] = []
        self.web_components: list[dict] = []
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
                api_version = int(meta.get("api_version", 1))
                if api_version != 1:
                    raise ValueError(f"unsupported add-on API version {api_version}; this build supports version 1")
                permissions = meta.get("permissions", [])
                if not isinstance(permissions, list) or any(not isinstance(x, str) for x in permissions):
                    raise ValueError("permissions must be a list of strings")
                found.append(AddonInfo(name=name, version=str(meta.get("version", "0.0.0")),
                    description=str(meta.get("description", "")),
                    author=str(meta.get("author", "Unknown")), path=str(folder),
                    enabled=name not in self.disabled, permissions=permissions, api_version=api_version))
            except Exception as exc:
                found.append(AddonInfo(name=folder.name, path=str(folder), enabled=False,
                                       error=f"Invalid addon.json: {exc}"))
        self.infos = found
        return found

    def load(self):
        self.apis.clear(); self.schemas.clear(); self.callables.clear(); self.tool_identities.clear()
        self.commands.clear(); self.actions.clear(); self.ui_contributions.clear(); self.web_components.clear()
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
                used_names = set(self.callables)
                for schema, handler in api.tools:
                    original = schema["function"]["name"]
                    name = make_tool_name(info.name, original, used_names)
                    normalized = dict(schema)
                    normalized["function"] = {**schema["function"], "name": name}
                    self.schemas.append(normalized)
                    self.callables[name] = handler
                    self.tool_identities[name] = {"namespace": info.name,
                                                  "original_name": original,
                                                  "source_type": "addon"}
                for name, definition in api.commands.items():
                    if name in self.commands:
                        raise ValueError(f"duplicate add-on command: {name}")
                    self.commands[name] = definition
                self.actions.extend(api.actions)
                self.ui_contributions.extend(api.ui_contributions)
                self.web_components.extend(api.web_components)
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

    def build_ui(self, location: str, parent: Any, app: Any = None, *, backend: str = "tk") -> list[Any]:
        """Build UI contributions for a placement and frontend; failures are isolated."""
        built = []
        for item in list(self.ui_contributions):
            if item["location"] != location or item.get("backend", "tk") != backend:
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
        "api_version": 1, "description": description, "author": "", "permissions": []}, indent=2) + "\n", encoding="utf-8")
    (folder / "addon.py").write_text('''"""Example Agent Code add-on."""\n\ndef register(api):\n    # Add tools, slash commands, lifecycle hooks, or UI actions here.\n    api.on("tools_loaded", on_tools_loaded)\n\n\ndef on_tools_loaded(**context):\n    # Keep hooks fast; do not block the UI thread.\n    return None\n''', encoding="utf-8")
    (folder / "README.md").write_text(f"# {name}\n\n{description}\n\nThis is a trusted Python extension. Review its code before enabling it.\n", encoding="utf-8")
    return folder


# ---------------------------------------------------------------------------
# Safe local add-on package management
# ---------------------------------------------------------------------------

import shutil
import zipfile

MAX_ADDON_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_ADDON_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_ADDON_FILES = 1500


def _validate_addon_folder(folder: Path) -> dict:
    folder = Path(folder)
    manifest = folder / "addon.json"
    entry = folder / "addon.py"
    if not manifest.is_file() or not entry.is_file():
        raise ValueError("Add-on package must contain addon.json and addon.py")
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise ValueError("addon.json must contain a JSON object")
    name = str(meta.get("name") or folder.name)
    if not _NAME_RE.fullmatch(name):
        raise ValueError("Invalid add-on name in addon.json")
    files = 0; total = 0
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Add-on packages cannot contain symlinks: {path.name}")
        if path.is_file():
            files += 1; total += path.stat().st_size
            if files > MAX_ADDON_FILES or total > MAX_ADDON_UNPACKED_BYTES:
                raise ValueError("Add-on folder exceeds file-count or expanded-size limits")
    meta["name"] = name
    return meta


def install_addon_archive(archive: Path, addons_dir: Path, *, replace: bool = False) -> Path:
    """Install a zip add-on after validating paths, size, and its manifest."""
    archive, addons_dir = Path(archive), Path(addons_dir)
    if archive.stat().st_size > MAX_ADDON_ARCHIVE_BYTES:
        raise ValueError("Add-on archive exceeds the 32 MB download limit")
    addons_dir.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="agent-code-addon-") as tmp:
        staging = Path(tmp) / "unpacked"
        staging.mkdir()
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if len(members) > MAX_ADDON_FILES:
                raise ValueError("Add-on archive contains too many files")
            total = 0
            for info in members:
                name = info.filename.replace("\\", "/")
                target = (staging / name).resolve()
                if name.startswith("/") or ".." in Path(name).parts or staging.resolve() not in target.parents and target != staging.resolve():
                    raise ValueError("Unsafe path in add-on archive")
                total += int(info.file_size)
                if total > MAX_ADDON_UNPACKED_BYTES:
                    raise ValueError("Add-on archive expands beyond the 64 MB limit")
            zf.extractall(staging)
        # Accept either a package root or one enclosing directory.
        roots = [staging] if (staging / "addon.json").exists() else [p for p in staging.iterdir() if p.is_dir()]
        source = next((p for p in roots if (p / "addon.json").is_file() and (p / "addon.py").is_file()), None)
        if source is None:
            raise ValueError("Could not find addon.json and addon.py in the archive")
        meta = _validate_addon_folder(source)
        destination = addons_dir / meta["name"]
        if destination.exists() and not replace:
            raise FileExistsError(f"Add-on '{meta['name']}' is already installed")
        backup = None
        if destination.exists():
            backup = addons_dir / (meta["name"] + ".backup")
            if backup.exists(): shutil.rmtree(backup)
            destination.rename(backup)
        try:
            shutil.copytree(source, destination)
            _validate_addon_folder(destination)
        except Exception:
            if destination.exists(): shutil.rmtree(destination)
            if backup and backup.exists(): backup.rename(destination)
            raise
        if backup and backup.exists(): shutil.rmtree(backup)
        return destination


def import_addon_directory(source: Path, addons_dir: Path, *, replace: bool = False) -> Path:
    source, addons_dir = Path(source), Path(addons_dir)
    meta = _validate_addon_folder(source)
    destination = addons_dir / meta["name"]
    if destination.exists() and not replace:
        raise FileExistsError(f"Add-on '{meta['name']}' is already installed")
    if destination.exists(): shutil.rmtree(destination)
    addons_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination


def remove_addon(name: str, addons_dir: Path) -> bool:
    if not _NAME_RE.fullmatch(str(name)):
        raise ValueError("Invalid add-on name")
    root = Path(addons_dir).resolve()
    target = (root / name).resolve()
    if target.parent != root or not target.is_dir():
        return False
    shutil.rmtree(target)
    return True
