"""Token-efficiency regression tests for bounded history and browser snapshots."""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
BROWSER = ROOT / "src" / "agent_code" / "data" / "skills" / "browser" / "skill.py"

tree = ast.parse(AGENT.read_text(encoding="utf-8"))
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "compact_chat_history"]
NS = {}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(AGENT), "exec"), NS)

def test_compaction_keeps_system_and_recent_turns_only():
    messages = [{"role": "system", "content": "base"}]
    for i in range(9):
        messages.extend([{"role": "user", "content": f"q{i}"},
                         {"role": "assistant", "content": f"a{i}"}])
    result = NS["compact_chat_history"](messages, keep_turns=3)
    assert result[0] == {"role": "system", "content": "base"}
    assert [m["content"] for m in result if m["role"] == "user"] == ["q6", "q7", "q8"]
    assert any("Older conversation turns omitted" in m.get("content", "") for m in result if m["role"] == "system")

def test_compaction_keeps_tool_call_and_bounds_tool_result():
    messages = [{"role": "user", "content": "inspect"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
                {"role": "tool", "tool_call_id": "c1", "content": "x" * 5000}]
    result = NS["compact_chat_history"](messages, keep_turns=3, max_tool_chars=250)
    assert result[1].get("tool_calls") == [{"id": "c1"}]
    assert len(result[2]["content"]) == 250

def test_browser_snapshot_uses_offset_and_limit_not_whole_page_chars():
    source = BROWSER.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    snapshot = next(n for n in ast.walk(parsed) if isinstance(n, ast.FunctionDef) and n.name == "snapshot")
    args = [a.arg for a in snapshot.args.args]
    assert args == ["offset", "limit"]
    assert "More lines available" in source

def test_shell_command_output_is_bounded_and_keeps_end():
    source = AGENT.read_text(encoding='utf-8')
    parsed = ast.parse(source)
    helper = next(n for n in ast.walk(parsed) if isinstance(n, ast.FunctionDef) and n.name == '_compact_command_output')
    ns = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(AGENT), 'exec'), ns)
    result = ns['_compact_command_output']('START' + ('x' * 5000) + 'IMPORTANT_END', 500)
    assert len(result) <= 500
    assert result.startswith('START')
    assert result.endswith('IMPORTANT_END')
    assert 'characters omitted' in result

def test_tool_schema_compaction_bounds_descriptions_without_mutating_source():
    helper = next(n for n in ast.walk(ast.parse(AGENT.read_text(encoding='utf-8')))
                  if isinstance(n, ast.FunctionDef) and n.name == 'compact_tool_schemas')
    ns = {'json': __import__('json')}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(AGENT), 'exec'), ns)
    original = [{"type": "function", "function": {"name": "x", "description": "d" * 1000,
                "parameters": {"type": "object", "properties": {"x": {"type": "string", "description": "p" * 500}}}}}]
    result = ns['compact_tool_schemas'](original)
    assert len(result[0]['function']['description']) == 220
    assert len(result[0]['function']['parameters']['properties']['x']['description']) == 120
    assert len(original[0]['function']['description']) == 1000


def test_main_system_prompt_is_mission_focused_and_compact():
    source = AGENT.read_text(encoding='utf-8')
    prompt = source.split('CORE_PROMPT = f"""', 1)[1].split('"""', 1)[0]
    assert len(prompt) < 1500
    assert 'MISSION:' in prompt and 'TOOLS:' in prompt
    assert 'NEW PROJECT RULE' not in prompt


def test_provider_server_errors_are_sanitized_before_entering_agent_context():
    helper = next(n for n in ast.parse(AGENT.read_text(encoding='utf-8')).body
                  if isinstance(n, ast.FunctionDef) and n.name == 'sanitize_tool_result_for_context')
    ns = {'re': __import__('re')}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(AGENT), 'exec'), ns)
    sanitize = ns['sanitize_tool_result_for_context']
    for code, expected in (
        ('ERROR: HTTP 403: Forbidden - secret response body', 'denied access'),
        ('ERROR: HTTP 429: Too Many Requests', 'rate-limiting'),
        ('ERROR: HTTP 503: Service Unavailable', 'temporarily unavailable'),
    ):
        result = sanitize(code)
        assert code.split('HTTP ')[1][:3] not in result
        assert expected in result
    mixed = sanitize('Fetched 3 records\\nERROR: HTTP 503: backend offline')
    assert 'Fetched 3 records' in mixed
    assert '503' not in mixed


def test_main_tool_context_uses_sanitized_results():
    source = AGENT.read_text(encoding='utf-8')
    assert '"content": sanitize_tool_result_for_context(result, 2000)' in source
