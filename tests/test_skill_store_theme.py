"""Regression tests for Skills Store theme constants (without importing GUI deps)."""
import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "src" / "agent_code" / "skill_manager.py"
REQUIRED_THEME_NAMES = {
    "BG", "BG_PANEL", "BG_CARD", "BG_HOVER", "BG_INPUT",
    "FG", "FG_BRIGHT", "FG_DIM", "ACCENT", "ACCENT_DARK",
    "GREEN", "YELLOW", "RED", "BORDER",
}


def test_all_required_theme_constants_are_defined():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    defined = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert REQUIRED_THEME_NAMES <= defined


def test_theme_color_constants_are_valid_hex_colors():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    for name in REQUIRED_THEME_NAMES:
        value = values[name]
        assert isinstance(value, str), name
        assert len(value) == 7 and value.startswith("#"), (name, value)
        int(value[1:], 16)
