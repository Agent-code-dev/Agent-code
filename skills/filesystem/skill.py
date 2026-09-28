"""filesystem skill — read/write files, confined to the workspace sandbox."""

import os
from pathlib import Path

SKILL = {
    "name": "filesystem",
    "description": (
        "Create, read, and list files INSIDE the sandbox workspace. "
        "write_file creates a file, append_file adds chunks, read_file "
        "inspects, list_dir explores. Paths are relative to the workspace."
    ),
}

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", "workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)

MAX_READ = 20_000
MAX_WRITE_CHUNK = 200_000   # ~200 KB per call


def _safe(path: str) -> Path:
    """Resolve `path` under WORKSPACE; reject anything that escapes."""
    if not isinstance(path, str):
        raise ValueError("path must be a string")
    if os.path.isabs(path):
        p = Path(path).resolve()
        if not str(p).startswith(str(WORKSPACE)):
            raise ValueError(f"absolute path outside workspace: {path}")
        return p
    p = (WORKSPACE / path).resolve()
    if not str(p).startswith(str(WORKSPACE)):
        raise ValueError(f"path escapes workspace: {path}")
    return p


def write_file(path: str, content: str) -> str:
    """Create or overwrite a file. Content capped at MAX_WRITE_CHUNK."""
    try:
        if not isinstance(content, str):
            return "ERROR: content must be a string"
        if len(content) > MAX_WRITE_CHUNK:
            return (f"ERROR: content too large ({len(content)} chars, "
                    f"max {MAX_WRITE_CHUNK}). Write in chunks with write_file "
                    f"then append_file.")
        p = _safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK wrote {len(content)} chars to {path} (total {p.stat().st_size} bytes)"
    except Exception as e:
        return f"ERROR: {e}"


def append_file(path: str, content: str) -> str:
    """Append text to a file (creates it if missing)."""
    try:
        if not isinstance(content, str):
            return "ERROR: content must be a string"
        if len(content) > MAX_WRITE_CHUNK:
            return f"ERROR: chunk too large ({len(content)} chars)"
        p = _safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"OK appended {len(content)} chars; file is now {p.stat().st_size} bytes"
    except Exception as e:
        return f"ERROR: {e}"


def read_file(path: str) -> str:
    try:
        p = _safe(path)
        if not p.exists():
            return f"ERROR: not found: {path}"
        return p.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
    except Exception as e:
        return f"ERROR: {e}"


def list_dir(path: str = ".") -> str:
    try:
        p = _safe(path)
        if not p.is_dir():
            return f"ERROR: not a directory: {path}"
        rows = []
        for child in sorted(p.iterdir()):
            kind = "DIR " if child.is_dir() else "FILE"
            size = child.stat().st_size if child.is_file() else 0
            rows.append(f"{kind} {size:>9}  {child.name}")
        return "\n".join(rows) or "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": (
            "Create or overwrite a file in the workspace. "
            "For large files, write the first chunk then use append_file."
        ),
        "parameters": {"type": "object",
                       "properties": {
                           "path": {"type": "string",
                                    "description": "Relative path, e.g. 'gta.html'"},
                           "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "append_file",
        "description": "Append text to a file in the workspace (creates if missing).",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file's text content from the workspace.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List files and folders in a workspace directory.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}}}}},
]

TOOL_CALLABLES = {
    "write_file": write_file,
    "append_file": append_file,
    "read_file": read_file,
    "list_dir": list_dir,
}