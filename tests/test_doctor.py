import json
from pathlib import Path

from agent_code import doctor


def test_diagnostics_never_include_api_key(tmp_path, monkeypatch):
    config = tmp_path / "agent_config.json"
    secret = "never-print-this-api-key"
    config.write_text(json.dumps({"openai_api_keys": [secret], "openai_base_url": "https://user:pass@api.example.test/v1?api_key=hidden"}), encoding="utf-8")
    monkeypatch.setattr("agent_code.paths.user_config_file", lambda: config)
    workspace = tmp_path / "workspace"
    monkeypatch.setattr("agent_code.paths.project_workspace_dir", lambda: workspace)
    report = doctor.collect_diagnostics()
    assert secret not in json.dumps(report)
    assert "pass" not in json.dumps(report)
    assert "hidden" not in json.dumps(report)
    assert "API key configured" in next(c["detail"] for c in report["checks"] if c["name"] == "User configuration")
    assert report["version"] == "2.2.0"


def test_diagnostics_handles_corrupt_config(tmp_path, monkeypatch):
    config = tmp_path / "agent_config.json"
    config.write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr("agent_code.paths.user_config_file", lambda: config)
    workspace = tmp_path / "workspace"
    monkeypatch.setattr("agent_code.paths.project_workspace_dir", lambda: workspace)
    report = doctor.collect_diagnostics()
    check = next(c for c in report["checks"] if c["name"] == "User configuration")
    assert check["status"] == "error"
    assert "JSONDecodeError" in check["detail"]


def test_browser_detection_checks_common_install_locations(tmp_path, monkeypatch):
    from agent_code import doctor as doctor_module

    browser = tmp_path / "chrome"
    browser.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(doctor_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor_module.sys, "platform", "linux")
    monkeypatch.setattr(doctor_module.Path, "home", classmethod(lambda cls: tmp_path))
    # Simulate a common path without needing an installed browser.
    original_is_file = Path.is_file
    def fake_is_file(path):
        if path == Path("/usr/bin/google-chrome"):
            return True
        return original_is_file(path)
    monkeypatch.setattr(doctor_module.Path, "is_file", fake_is_file)
    assert doctor_module._detect_browser_executable() == "/usr/bin/google-chrome"
