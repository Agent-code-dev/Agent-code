from pathlib import Path
import ast
import sys

ROOT = Path(__file__).parents[1]


def _load_resolver():
    source = (ROOT / "src" / "agent_code" / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "resolve_skill_command")
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"shlex": __import__("shlex"), "os": __import__("os")}
    exec(compile(module, "agent.py", "exec"), namespace)
    return namespace["resolve_skill_command"]


def test_natural_skill_alias_resolves_to_native_handler_not_shell():
    resolve = _load_resolver()
    handler = lambda args, log: None
    commands = {"email": {"handler": handler, "aliases": ["temp mail configure"]}}
    assert resolve("temp mail configure", commands) == ("email", [])
    assert resolve("temp mail configure resend KEY", commands) == ("email", ["resend", "KEY"])


def test_longest_alias_wins_and_ordinary_sentence_is_not_intercepted():
    resolve = _load_resolver()
    handler = lambda args, log: None
    commands = {
        "temp": {"handler": handler, "aliases": ["temp mail"]},
        "providers": {"handler": handler, "aliases": ["temp mail providers"]},
    }
    assert resolve("temp mail providers", commands) == ("providers", [])
    assert resolve("I need temp mail configure", commands) is None
    assert resolve("email my friend", commands) is None
    assert resolve("/email resend KEY", commands) is None


def test_temp_mail_registers_natural_phrase_aliases():
    source = (ROOT / "src" / "agent_code" / "data" / "skills" / "temp_mail" / "skill.py").read_text(encoding="utf-8")
    assert '"temp mail configure"' in source
    assert '"temp mail providers"' in source
