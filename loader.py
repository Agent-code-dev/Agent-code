"""Hardened skill loader.

- Scans every skill with skill_security before importing
- Blocks critical-risk skills by default
- Warns on high/medium
- Caches discovery metadata
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from skill_security import scan_skill, verdict


def _meta_from_md(folder: Path) -> dict:
    import re
    md = folder / "skill.md"
    meta = {"name": folder.name, "description": "", "version": "?", "author": "?"}
    if not md.exists():
        return meta
    try:
        text = md.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    k = k.strip().lower()
                    v = v.strip().strip('"').strip("'")
                    if k in ("name", "description", "version", "author"):
                        meta[k] = v
    except Exception:
        pass
    return meta


def discover_skills(skills_dir) -> list:
    skills_dir = Path(skills_dir)
    out = []
    if not skills_dir.exists():
        return out
    for folder in sorted(skills_dir.iterdir()):
        if not folder.is_dir():
            continue
        if not (folder / "skill.py").exists():
            continue
        out.append(_meta_from_md(folder))
    return out


def load_skills(skills_dir, disabled=None, block_at=6) -> tuple:
    """Return (schemas, callables, metadata, commands).

    block_at: risk score at which a skill is refused.
    """
    skills_dir = Path(skills_dir)
    disabled = set(disabled or [])
    schemas, callables, metadata, commands = [], {}, [], {}

    if not skills_dir.exists():
        return schemas, callables, metadata, commands

    for skill_file in sorted(skills_dir.glob("*/skill.py")):
        name = skill_file.parent.name
        if name in disabled:
            print(f"[loader] skipped (disabled): {name}")
            continue

        # Security scan first
        scan = scan_skill(skill_file.parent)
        v = verdict(scan["score"])
        if scan["score"] >= block_at:
            print(f"[loader] BLOCKED {name}: risk={scan['score']} verdict={v} "
                  f"findings={scan['total']}")
            metadata.append({
                "name": name,
                "description": f"(blocked: {v} risk score {scan['score']})",
                "version": "?", "author": "?", "_blocked": True,
                "_scan": scan,
            })
            continue
        if scan["total"]:
            print(f"[loader] {name}: risk={scan['score']} verdict={v} "
                  f"findings={scan['total']}")

        try:
            spec = importlib.util.spec_from_file_location(f"skill_{name}", skill_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            schemas.extend(getattr(mod, "TOOL_SCHEMAS", []) or [])
            callables.update(getattr(mod, "TOOL_CALLABLES", {}) or {})

            cmds = getattr(mod, "COMMANDS", {}) or {}
            for cn, cd in cmds.items():
                if isinstance(cd, dict) and "handler" in cd:
                    commands[cn] = cd

            meta = getattr(mod, "SKILL", {"name": name})
            meta["_scan"] = scan
            metadata.append(meta)
            print(f"[loader] loaded: {meta.get('name', name)}")
        except Exception as e:
            print(f"[loader] FAILED {name}: {e}")

    return schemas, callables, metadata, commands