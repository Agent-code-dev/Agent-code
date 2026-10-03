"""Isolated subprocess runner for skill tool calls.

Each call runs in a fresh Python process with:
  - isolated mode (-I, no user site, no env leakage)
  - no site packages (-S)
  - hard timeout
  - stdout captured as JSON

This prevents a skill crash or hang from taking down the agent.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER_SRC = r'''
import sys, json, traceback, importlib.util
path, tool, args_json = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    spec = importlib.util.spec_from_file_location("skill", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fns = getattr(mod, "TOOL_CALLABLES", {}) or {}
    fn = fns.get(tool)
    if fn is None:
        print(json.dumps({"error": "tool not found: " + tool}))
        sys.exit(0)
    args = json.loads(args_json)
    result = fn(**args)
    print(json.dumps({"result": str(result)}))
except Exception as e:
    print(json.dumps({
        "error": type(e).__name__ + ": " + str(e),
        "traceback": traceback.format_exc()[:2000],
    }))
'''

_RUNNER = None


def _runner_path() -> Path:
    global _RUNNER
    if _RUNNER is None:
        p = Path(tempfile.gettempdir()) / "_agent_skill_runner.py"
        p.write_text(RUNNER_SRC, encoding="utf-8")
        _RUNNER = p
    return _RUNNER


def run_tool(skill_py: str, tool: str, args: dict,
             timeout: int = 30) -> dict:
    """Run one tool call in isolation. Returns {result} or {error, ...}."""
    try:
        r = subprocess.run(
            [sys.executable, "-I", "-S", str(_runner_path()),
             str(skill_py), tool, json.dumps(args or {})],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}

    out = (r.stdout or "").strip().splitlines()
    if not out:
        return {
            "error": "no output",
            "stderr": (r.stderr or "")[:500],
            "returncode": r.returncode,
        }
    try:
        return json.loads(out[-1])
    except json.JSONDecodeError:
        return {"error": "invalid JSON from runner", "raw": out[-1][:500]}