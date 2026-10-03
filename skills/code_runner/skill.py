"""code_runner skill — write and run a script in the workspace, capture output."""
import subprocess
import sys
import tempfile
import os
from pathlib import Path

SKILL = {
    "name": "code_runner",
    "description": "Write a script into the workspace and run it, returning stdout.",
}

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", "workspace")).resolve()
WORKSPACE.mkdir(parents=True, exist_ok=True)


def run_script(code: str, language: str = "python", timeout: int = 20) -> str:
    lang = language.lower().strip()
    suffix, cmd_builder = {
        "python": (".py", lambda p: [sys.executable, "-I", "-S", str(p)]),
        "javascript": (".js", lambda p: ["node", str(p)]),
        "shell": (".cmd", lambda p: ["cmd", "/c", str(p)]),
    }.get(lang, (".py", lambda p: [sys.executable, "-I", "-S", str(p)]))

    fd, name = tempfile.mkstemp(dir=str(WORKSPACE), suffix=suffix)
    os.close(fd)
    p = Path(name)
    try:
        p.write_text(code, encoding="utf-8")
        r = subprocess.run(
            cmd_builder(p), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(WORKSPACE),
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out[:6000] or f"(exit {r.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout after {timeout}s"
    except FileNotFoundError as e:
        return f"ERROR: {e}"
    finally:
        try:
            p.unlink()
        except Exception:
            pass


TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "run_script",
        "description": "Run code in the workspace. language: python|javascript|shell.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["code"],
        },
    },
}]

TOOL_CALLABLES = {"run_script": run_script}