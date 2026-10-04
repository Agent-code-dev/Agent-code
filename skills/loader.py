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
import importlib.util
from pathlib import Path


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

def load_skills(skills_dir: Path, disabled: list) -> tuple:
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

    for skill_file in sorted(skills_dir.glob("*/skill.py")):
        name = skill_file.parent.name

        if name in disabled:
            print(f"[loader] skipped (disabled): {name}")
            continue

        try:
            spec = importlib.util.spec_from_file_location(f"skill_{name}", skill_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"[loader] FAILED to import '{name}': {e}")
            continue

        try:
            schemas.extend(getattr(mod, "TOOL_SCHEMAS", []) or [])
            callables.update(getattr(mod, "TOOL_CALLABLES", {}) or {})

            cmds = getattr(mod, "COMMANDS", {}) or {}
            for cname, cdef in cmds.items():
                if not isinstance(cdef, dict) or "handler" not in cdef:
                    print(f"[loader] skipping malformed command '{cname}' in {name}")
                    continue
                commands[cname] = cdef

            meta = getattr(mod, "SKILL", {"name": name})
            metadata.append(meta)
            print(f"[loader] loaded skill: {meta.get('name', name)}")
        except Exception as e:
            print(f"[loader] FAILED to read contract of '{name}': {e}")

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