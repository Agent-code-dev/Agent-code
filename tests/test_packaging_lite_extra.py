from pathlib import Path
import tomllib


def test_default_install_uses_customtkinter_without_pywebview():
    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert not any(dep.startswith("pywebview") for dep in deps)
    assert any(dep.startswith("customtkinter") for dep in deps)
    assert "lite" in data["project"]["optional-dependencies"]
    assert not any(dep.lower().startswith("pyside6") for dep in deps)


def test_pywebview_is_not_a_project_dependency():
    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert not any("pywebview" in dep.lower() for dep in data["project"]["dependencies"])
