"""skills/loader.py — discover and load skill modules.

A skill is a folder under `skills/` containing:
    skill.py     — must export SKILL, TOOL_SCHEMAS, TOOL_CALLABLES
                   and optionally COMMANDS, HELP
    skill.md     — optional metadata (frontmatter: name, description,
                   version, author) + free-form help body

Contract:
    SKILL          : dict  {"name": str, "description": str}
    TOOL_SCHEMAS   : list[dict]     OpenAI function-calling schemas
    TOOL_CALLABLES : dict[str, fn]  name -> python callable
    COMMANDS       : dict           optional
                     {
                       "cmdname": {
                           "handler": fn(args_list, log_fn),
                           "description": str,
                       },
                       ...
                     }
    HELP           : str            optional fallback help text

The loader never crashes on a bad skill; it prints a warning and skips it.
"""

import re
import ast
import importlib.util
from pathlib import Path
from .tool_namespace import make_tool_name


# ---------------------------------------------------------------------------
# Metadata extraction (no code execution)
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _read_skill_md(folder: Path) -> dict:
    """Parse the optional skill.md frontmatter. Returns {} if missing/invalid."""
    md = folder / "skill.md"
    if not md.exists():
        return {}
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower()
        v = v.strip().strip('"').strip("'")
        if k in ("name", "description", "version", "author"):
            meta[k] = v
    return meta


def _read_skill_md_body(folder: Path) -> str:
    """Return the text after the closing frontmatter --- of skill.md."""
    md = folder / "skill.md"
    if not md.exists():
        return ""
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    m = _FRONTMATTER_RE.match(text)
    if m:
        return text[m.end():].strip()
    return text.strip()


# ---------------------------------------------------------------------------
# Discovery — list skills without importing them
# ---------------------------------------------------------------------------

def discover_skills(skills_dir: Path) -> list:
    """Return list of dicts for each folder containing skill.py.

    Each dict: {name, description, version, author, path}
    Metadata is taken from skill.md when present; otherwise from the folder name.
    """
    out = []
    skills_dir = Path(skills_dir)
    if not skills_dir.exists():
        return out

    for folder in sorted(skills_dir.iterdir()):
        if not folder.is_dir():
            continue
        if not (folder / "skill.py").exists():
            continue

        meta = {
            "name": folder.name,
            "description": "",
            "version": "?",
            "author": "?",
            "path": str(folder),
        }
        meta.update(_read_skill_md(folder))
        out.append(meta)

    return out


# ---------------------------------------------------------------------------
# Loading — import skill.py and extract the contract
# ---------------------------------------------------------------------------

def load_skills(skills_dir: Path, disabled: list, default_target: str = "host") -> tuple:
    """Import every enabled skill.py and collect its exports.

    Returns:
        schemas    : list[dict]        merged OpenAI tool schemas
        callables  : dict[str, fn]     merged tool callables
        metadata   : list[dict]        SKILL dicts of loaded skills
        commands   : dict              merged COMMANDS
    """
    schemas, callables, metadata, commands = [], {}, [], {}
    skills_dir = Path(skills_dir)
    if not skills_dir.exists():
        return schemas, callables, metadata, commands

    disabled = set(disabled or [])

    def literal_export(tree, export_name):
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == export_name
                    for target in node.targets):
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    return None
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == export_name:
                try:
                    return ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError):
                    return None
        return None

    for skill_file in sorted(skills_dir.glob("*/skill.py")):
        name = skill_file.parent.name
        if name in disabled:
            print(f"[loader] skipped (disabled): {name}")
            continue

        try:
            source = skill_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(skill_file))
            literal_meta = literal_export(tree, "SKILL")
            literal_schemas = literal_export(tree, "TOOL_SCHEMAS")
        except Exception as exc:
            print(f"[loader] FAILED to inspect '{name}': {exc}")
            continue

        # Decide the execution target before importing skill.py. A remote-only
        # Skill is never imported into the host process: only literal metadata
        # and schemas are inspected locally; the module is imported in its
        # declared Sandbox/SSH environment when a tool is actually called.
        meta_for_target = literal_meta if isinstance(literal_meta, dict) else {}
        execution = meta_for_target.get("execution", {})
        if not isinstance(execution, dict):
            execution = {}
        base_target = str(execution.get("target") or "host").strip().lower()
        if base_target == "auto":
            base_target = str(default_target or "host").strip().lower()
        tool_targets = []
        if isinstance(literal_schemas, list):
            overrides = execution.get("tools", {}) if isinstance(execution.get("tools", {}), dict) else {}
            for schema in literal_schemas:
                function = schema.get("function", {}) if isinstance(schema, dict) else {}
                original = function.get("name") if isinstance(function, dict) else None
                override = overrides.get(original, {}) if isinstance(overrides.get(original, {}), dict) else {}
                target = str(override.get("target") or execution.get("target") or "host").strip().lower()
                if target == "auto":
                    target = str(default_target or "host").strip().lower()
                tool_targets.append(target)
        else:
            tool_targets = [base_target]
        remote_targets = {target for target in tool_targets if target in {"sandbox", "ssh"}}
        host_targets = {target for target in tool_targets if target == "host"}
        if any(target not in {"host", "sandbox", "ssh"} for target in tool_targets):
            print(f"[loader] FAILED to load '{name}': unsupported execution target")
            continue
        if remote_targets and host_targets:
            print(f"[loader] FAILED to load '{name}': mixed Host and remote tool targets are not allowed; split them into separate Skills so remote code is never imported on Host")
            continue
        remote_only = bool(remote_targets)

        if remote_only:
            if not isinstance(literal_meta, dict) or not isinstance(literal_schemas, list):
                print(f"[loader] FAILED to load remote Skill '{name}': SKILL and TOOL_SCHEMAS must be literal Python data so the module can remain unimported on Host")
                continue
            raw_schemas = literal_schemas
            meta = dict(literal_meta)
            raw_callables = {}
            for schema in raw_schemas:
                function = schema.get("function", {}) if isinstance(schema, dict) else {}
                original = function.get("name") if isinstance(function, dict) else None
                if original:
                    def remote_placeholder(**_kwargs):
                        return "ERROR: remote Skill callable was invoked on Host; check Skill execution routing."
                    raw_callables[original] = remote_placeholder
            cmds = {}
        else:
            try:
                spec = importlib.util.spec_from_file_location(f"skill_{name}", skill_file)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception as exc:
                print(f"[loader] FAILED to import '{name}': {exc}")
                continue
            raw_schemas = getattr(mod, "TOOL_SCHEMAS", []) or []
            raw_callables = getattr(mod, "TOOL_CALLABLES", {}) or {}
            meta = getattr(mod, "SKILL", {"name": name})
            cmds = getattr(mod, "COMMANDS", {}) or {}

        try:
            # Tool names are namespaced at load time, before any provider sees
            # them. Skill authors keep short, natural local names in skill.py.
            skill_tool_names = {}
            used_names = {s.get("function", {}).get("name") for s in schemas
                          if isinstance(s, dict)}
            for raw_schema in raw_schemas:
                if not isinstance(raw_schema, dict):
                    continue
                function = raw_schema.get("function", {})
                original = function.get("name") if isinstance(function, dict) else None
                if not original:
                    print(f"[loader] skipping unnamed tool in {name}")
                    continue
                handler = raw_callables.get(original)
                if not callable(handler):
                    print(f"[loader] skipping tool without callable '{original}' in {name}")
                    continue
                provider_name = make_tool_name(name, original, used_names)
                schema = {**raw_schema, "function": {**function, "name": provider_name}}
                schemas.append(schema)
                callables[provider_name] = handler
                skill_tool_names[provider_name] = original

            if not isinstance(cmds, dict):
                cmds = {}
            for cname, cdef in cmds.items():
                if not isinstance(cdef, dict) or "handler" not in cdef:
                    print(f"[loader] skipping malformed command '{cname}' in {name}")
                    continue
                commands[cname] = cdef

            if not isinstance(meta, dict):
                meta = {"name": name, "description": str(meta)}
            else:
                meta = dict(meta)
                meta.setdefault("name", name)
            meta["_tool_names"] = skill_tool_names
            meta["_folder_name"] = name
            meta["_remote_only"] = remote_only
            metadata.append(meta)
            print(f"[loader] loaded skill: {meta.get('name', name)}" +
                  (" (remote; not imported on host)" if remote_only else ""))
        except Exception as exc:
            print(f"[loader] FAILED to read contract of '{name}': {exc}")

    return schemas, callables, metadata, commands


def list_commands(commands: dict) -> str:
    """Pretty-print a COMMANDS dict for logging."""
    if not commands:
        return "(no commands)"
    lines = []
    for name, d in sorted(commands.items()):
        desc = d.get("description", "")
        lines.append(f"  /{name:<14} {desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-skill help
# ---------------------------------------------------------------------------

def get_skill_help(skills_dir: Path, name: str) -> str:
    """Return the help text for a skill.

    Priority:
      1. skill.md body  (text after the closing --- of the frontmatter)
      2. HELP string exported from skill.py
      3. SKILL["description"]
      4. "(no help available)"
    """
    skills_dir = Path(skills_dir)
    folder = skills_dir / name
    if not folder.is_dir():
        return f"(skill '{name}' not found)"

    # 1. skill.md body
    body = _read_skill_md_body(folder)
    if body:
        return body

    # 2. HELP export from skill.py
    skill_py = folder / "skill.py"
    if skill_py.exists():
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{name}", skill_py)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            h = getattr(mod, "HELP", None)
            if isinstance(h, str) and h.strip():
                return h.strip()
            meta = getattr(mod, "SKILL", {}) or {}
            desc = meta.get("description", "")
            if desc:
                return f"# {meta.get('name', name)}\n\n{desc}"
        except Exception as e:
            return f"(failed to load skill help: {e})"

    return "(no help available)"