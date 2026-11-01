import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
TREE = ast.parse(AGENT.read_text(encoding="utf-8"))
NAMES = {"filter_core_tools", "tool_curl_fetch"}
NODES = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in NAMES]
NS = {"re": __import__("re"), "subprocess": __import__("subprocess"), "SKILL_UA": "test-agent",
      "CORE_TOOL_NAMES": {"create_project", "read_file", "write_file", "append_file",
                          "edit_file", "glob_files", "grep_files", "shell_run", "curl_fetch"}}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(AGENT), "exec"), NS)


def test_core_filter_keeps_only_shell_files_and_curl():
    names = ["read_file", "shell_run", "curl_fetch", "web_search", "task", "skill_magic", "write_file"]
    schemas = [{"type": "function", "function": {"name": n}} for n in names]
    callables = {n: (lambda: n) for n in names}
    filtered_schemas, filtered_callables = NS["filter_core_tools"](schemas, callables)
    kept = {x["function"]["name"] for x in filtered_schemas}
    assert kept == {"read_file", "shell_run", "curl_fetch", "write_file"}
    assert "background_shell" not in kept
    assert kept <= {"create_project", "read_file", "write_file", "append_file",
                    "edit_file", "glob_files", "grep_files", "shell_run", "curl_fetch"}
    assert set(filtered_callables) == kept


def test_curl_fetch_rejects_non_http_url():
    assert NS["tool_curl_fetch"]("file:///etc/passwd").startswith("ERROR: URL must start")


def test_core_mode_ui_and_minimal_prompt_are_wired():
    src = AGENT.read_text(encoding="utf-8")
    assert 'tabs.add("Core")' in src
    assert 'cfg.get("core_mode", False)' in src
    assert '"core_mode": bool(self.core_mode_var.get())' in src
    assert "CORE_MINI_PROMPT" in src
    assert "if not getattr(self, \"core_mode\", False):" in src


def test_core_prompt_explicitly_limits_tool_families():
    src = AGENT.read_text(encoding="utf-8")
    assert "Do not use browser, search, skills, MCP, subagents, background processes" in src
    assert '"background_shell"' not in src[src.index("CORE_TOOL_NAMES"):src.index("def filter_core_tools")]

def test_regular_agent_mode_keeps_its_extended_toolset():
    src = AGENT.read_text(encoding="utf-8")
    assert '"background_shell": self._guarded_background_shell' in src
    assert 'self._build_mcp_tools(self.all_schemas, self.all_callables)' in src
    assert 'load_skills(SKILLS_DIR, self.disabled_skills)' in src
