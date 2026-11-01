import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "agent.py"


def test_platform_open_helper_has_windows_macos_linux_paths():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "open_with_system_app")
    source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), fn)
    assert 'os.startfile' in source
    assert '["open", target]' in source
    assert '"xdg-open"' in source and '"gio"' in source


def test_open_command_uses_relative_path_validation():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'p.relative_to(WORKSPACE.resolve())' in source
    assert 'open_with_system_app(p)' in source
