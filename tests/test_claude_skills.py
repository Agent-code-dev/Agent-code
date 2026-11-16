from pathlib import Path
from agent_code.claude_skills import discover_claude_skills, build_claude_skill_context


def test_discovers_claude_skill_md_without_python_module(tmp_path):
    folder = tmp_path / "skills" / "review"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: code-review\ndescription: Review changes\n---\nInspect tests and edge cases.\n", encoding="utf-8")
    found = discover_claude_skills([tmp_path / "skills"])
    assert len(found) == 1
    assert found[0]["name"] == "code-review"
    context = build_claude_skill_context([tmp_path / "skills"])
    assert "Inspect tests and edge cases" in context
    assert "not executable tools" in context


def test_ignores_oversized_and_empty_skill_files(tmp_path):
    root = tmp_path / "skills"; root.mkdir()
    (root / "empty").mkdir(); (root / "empty" / "SKILL.md").write_text("---\nname: empty\n---\n")
    (root / "huge").mkdir(); (root / "huge" / "SKILL.md").write_text("x" * 50000)
    assert discover_claude_skills([root]) == []
