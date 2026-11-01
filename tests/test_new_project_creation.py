from agent_code.projects import create_project_directory


def test_create_project_makes_isolated_new_directory(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    existing = workspace / "existing-app"
    existing.mkdir()
    (existing / "app.py").write_text("old", encoding="utf-8")

    result = create_project_directory(workspace, "Weather App", "A fresh weather application")

    created = workspace / "Weather-App"
    assert "OK: created a NEW empty project directory" in result
    assert "Weather-App/" in result
    assert created.is_dir()
    assert list(created.iterdir()) == []
    assert (existing / "app.py").read_text(encoding="utf-8") == "old"


def test_create_project_avoids_existing_name(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "demo").mkdir()

    result = create_project_directory(workspace, "demo")

    assert (workspace / "demo-2").is_dir()
    assert "demo-2/" in result


def test_create_project_rejects_empty_name(tmp_path):
    assert create_project_directory(tmp_path, "  ").startswith("ERROR:")


def test_create_project_does_not_accept_path_traversal(tmp_path):
    workspace = tmp_path / "workspace"
    result = create_project_directory(workspace, "../../outside")
    assert "outside" not in result or result.startswith("OK:")
    assert not (tmp_path / "outside").exists()
