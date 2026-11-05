import ast
from pathlib import Path


def test_agent_loop_uses_module_regex_import_without_local_shadowing():
    source = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    agent_loop = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_agent_loop"
    )
    local_re_imports = [
        node for node in ast.walk(agent_loop)
        if isinstance(node, ast.Import)
        and any(alias.name == "re" for alias in node.names)
    ]
    assert not local_re_imports, "_agent_loop must use the module-level `re` import"
