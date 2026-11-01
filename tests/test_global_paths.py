import importlib.util
import os
from pathlib import Path


def load_paths_module():
    module_path = Path(__file__).parents[1] / "src" / "agent_code" / "paths.py"
    spec = importlib.util.spec_from_file_location("agent_code_paths_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skills_dir_is_in_global_user_data_not_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    paths = load_paths_module()
    skills = paths.project_skills_dir()
    assert skills == (tmp_path / "home" / ".local" / "share" / "agent-code" / "skills")
    assert skills != tmp_path / "skills"


def test_config_is_always_user_config_not_project_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    paths = load_paths_module()
    (tmp_path / "agent_config.json").write_text('{"api_key":"project-secret"}', encoding="utf-8")
    assert paths.project_config_file() == tmp_path / "home" / ".config" / "agent-code" / "agent_config.json"


def test_migrates_project_skills_without_overwriting_global(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    paths = load_paths_module()
    legacy = tmp_path / "skills" / "legacy_skill"
    legacy.mkdir(parents=True)
    (legacy / "skill.py").write_text("# old", encoding="utf-8")
    target = paths.global_skills_dir() / "legacy_skill"
    target.mkdir(parents=True)
    (target / "skill.py").write_text("# global", encoding="utf-8")
    paths.migrate_project_skills_to_global()
    assert (target / "skill.py").read_text(encoding="utf-8") == "# global"
    fresh = tmp_path / "skills" / "fresh_skill"
    fresh.mkdir()
    (fresh / "skill.py").write_text("# fresh", encoding="utf-8")
    paths.migrate_project_skills_to_global()
    assert (paths.global_skills_dir() / "fresh_skill" / "skill.py").exists()
