"""Safe creation helpers for isolated projects inside an Agent Code workspace."""
from __future__ import annotations

import re
from pathlib import Path


def create_project_directory(workspace: Path, name: str, description: str = "") -> str:
    """Create a fresh, uniquely named project directory below *workspace*."""
    workspace = Path(workspace).expanduser().resolve()
    raw_name = str(name or "").strip()
    if not raw_name:
        return "ERROR: project name is required"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_name).strip(".-_")[:64]
    if not slug or slug in {".", ".."}:
        return "ERROR: project name must contain letters or numbers"
    candidate = (workspace / slug).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError:
        return "ERROR: project name escapes the workspace"
    suffix = 2
    while candidate.exists():
        candidate = (workspace / f"{slug}-{suffix}").resolve()
        suffix += 1
        if suffix > 10000:
            return "ERROR: could not find an unused project directory name"
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        candidate.mkdir(parents=True, exist_ok=False)
        rel = candidate.relative_to(workspace).as_posix()
        note = f" Description: {str(description).strip()[:240]}" if description else ""
        return (f"OK: created a NEW empty project directory at {rel}/.{note} "
                f"Create all new-project files under {rel}/; do not modify sibling projects or workspace-root files.")
    except Exception as exc:
        return f"ERROR creating project directory: {type(exc).__name__}: {exc}"
