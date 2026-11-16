"""Persistent, versioned project blueprints for Agent Code."""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BLUEPRINT_VERSION = 1

class BlueprintStore:
    """Stores a project plan as structured, reviewable JSON in the workspace."""
    def __init__(self, workspace: str | Path):
        self.path = Path(workspace).expanduser().resolve() / ".agent-code" / "blueprint.json"

    def load(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("schema_version") == BLUEPRINT_VERSION:
                return data
        except (OSError, ValueError, TypeError):
            pass
        return None

    def save(self, blueprint: dict[str, Any]) -> Path:
        if not isinstance(blueprint, dict):
            raise TypeError("blueprint must be an object")
        clean = dict(blueprint)
        clean.setdefault("title", "Untitled project")
        clean.setdefault("goal", "")
        clean.setdefault("requirements", [])
        clean.setdefault("architecture", [])
        clean.setdefault("milestones", [])
        clean.setdefault("acceptance_criteria", [])
        clean["schema_version"] = BLUEPRINT_VERSION
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="blueprint-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(clean, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(tmp, self.path)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
        return self.path

    def prompt_context(self) -> str:
        data = self.load()
        if not data:
            return "No project blueprint exists yet. For substantial multi-step projects, create .agent-code/blueprint.json using the documented schema before implementation, then keep it updated as decisions change."
        return "ACTIVE PROJECT BLUEPRINT (authoritative project intent; reconcile conflicts with the user's latest request):\n" + json.dumps(data, ensure_ascii=False, indent=2)[:12000]
