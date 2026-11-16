import threading
import time

from agent_code.web_desktop import WebviewRoot, render_markdown


def test_markdown_renderer_escapes_raw_html_and_renders_code():
    rendered = render_markdown("<script>alert(1)</script>\n\n```python\nprint('ok')\n```")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "print" in rendered


def test_server_root_confirmation_round_trip():
    root = WebviewRoot()
    result = {}
    worker = threading.Thread(target=lambda: result.setdefault("answer", root.askyesno("Confirm", "Allow?")))
    worker.start()
    deadline = time.time() + 2
    pending = []
    while time.time() < deadline and not pending:
        pending = root.pending_confirmations()
        time.sleep(0.01)
    assert pending and pending[0]["title"] == "Confirm"
    assert root.answer_confirmation(pending[0]["id"], True)
    worker.join(timeout=2)
    assert result["answer"] is True
    root.destroy()


def test_server_root_rejects_unknown_confirmation():
    root = WebviewRoot()
    assert root.answer_confirmation("missing", True) is False
    root.destroy()


def test_web_workspace_browser_is_bounded_and_rejects_traversal_and_symlinks(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from agent_code.web_desktop import AgentWebAPI

    root = tmp_path / "workspace"
    root.mkdir()
    (root / "README.md").write_text("hello", encoding="utf-8")
    (root / ".env").write_text("SECRET=hidden", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("not for preview", encoding="utf-8")
    try:
        (root / "linked.txt").symlink_to(outside)
    except OSError:
        pass
    engine = SimpleNamespace(todo=SimpleNamespace(items=[]))
    api = AgentWebAPI(engine, WebviewRoot())
    monkeypatch.setattr(AgentWebAPI, "_workspace", staticmethod(lambda: root))

    listing = api.get_workspace_entries("")
    names = {item["name"] for item in listing["entries"]}
    assert "README.md" in names and ".env" not in names
    assert api.read_workspace_file("README.md")["content"] == "hello"
    assert not api.read_workspace_file("../outside.txt")["ok"]
    if (root / "linked.txt").is_symlink():
        assert not api.read_workspace_file("linked.txt")["ok"]
    api.root.destroy()


def test_web_task_and_checkpoint_panels_return_safe_summaries(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from agent_code.web_desktop import AgentWebAPI, WebviewRoot

    class Checkpoints:
        def history(self, limit):
            return [{"id": "abc", "label": "test", "files": {"a.py": {}}}]
        def preview_restore(self, checkpoint_id):
            return {"actions": [{"path": "a.py", "action": "restore"}]}

    engine = SimpleNamespace(todo=SimpleNamespace(items=[{"content": "test", "status": "pending"}]), checkpoints=Checkpoints())
    api = AgentWebAPI(engine, WebviewRoot())
    assert api.get_todo()["items"][0]["content"] == "test"
    assert api.get_checkpoints()[0]["files_changed"] == 1
    preview = api.preview_checkpoint("abc")
    assert preview["ok"] and "a.py" in preview["files"][0]
    assert not api.preview_checkpoint("../bad")["ok"]
    api.root.destroy()


def test_blueprint_bridge_validates_and_saves_structured_project_plan():
    from types import SimpleNamespace
    from agent_code.web_desktop import AgentWebAPI, WebviewRoot

    class Store:
        def __init__(self): self.value = None
        def load(self): return self.value
        def save(self, value): self.value = value; return "/workspace/.agent-code/blueprint.json"

    store = Store()
    api = AgentWebAPI(SimpleNamespace(blueprint_store=store), WebviewRoot())
    result = api.save_blueprint({"title": "Nova", "goal": "Build an OS", "requirements": ["Kernel", "Drivers"]})
    assert result["ok"] and store.value["requirements"] == ["Kernel", "Drivers"]
    assert api.get_blueprint()["blueprint"]["goal"] == "Build an OS"
    assert not api.save_blueprint({"requirements": "not a list"})["ok"]
    api.root.destroy()


def test_provider_profiles_keep_api_keys_out_of_listing(monkeypatch):
    import copy
    import agent_code.web_desktop as web
    from types import SimpleNamespace

    config = {}
    monkeypatch.setattr(web, "load_config", lambda: copy.deepcopy(config))
    def save(value):
        config.clear(); config.update(copy.deepcopy(value))
    monkeypatch.setattr(web, "save_config", save)
    api = web.AgentWebAPI(SimpleNamespace(), web.WebviewRoot())
    saved = api.save_provider_profile("Local", {"provider_name": "OpenAI-compatible",
        "openai_base_url": "https://example.invalid/v1", "openai_model": "test-model",
        "openai_api_keys": ["secret-key-value"]})
    assert saved["ok"]
    profiles = api.get_provider_profiles()
    assert profiles[0]["key_count"] == 1
    assert "secret-key-value" not in repr(profiles)
    api.root.destroy()


def test_webui_exposes_full_settings_and_native_skills_store_without_page_scroll():
    from pathlib import Path
    ui = Path(__file__).parents[1] / "src" / "agent_code" / "web_ui"
    html = (ui / "index.html").read_text(encoding="utf-8")
    css = (ui / "style.css").read_text(encoding="utf-8")
    js = (ui / "app.js").read_text(encoding="utf-8")
    for page in ("provider", "permissions", "accounts", "ssh", "sandbox", "core", "browser", "interface"):
        assert f'data-settings-panel="{page}"' in html
        assert f'data-settings-tab="{page}"' in html
    for control in ("unrestrictedShell", "ultraUnrestricted", "browserPath", "browserType",
                    "sshCommand", "sshHost", "sshUsername", "sshPort", "sshKeyPath",
                    "podmanSandbox", "coreMode", "cloudSync", "storeServer",
                    "connectSsh", "disconnectSsh", "skillStoreInstalledOnly", "skillStoreMineOnly",
                    "skillStoreFlaggedOnly"):

        assert f'id="{control}"' in html
    assert 'id="page-skillstore"' in html
    assert 'id="skillStoreResults"' in html and 'id="skillStoreDetail"' in html
    assert "overflow:hidden" in css
    assert "skill_store_install" in js and "skill_store_auth" in js


def test_server_api_allowlist_includes_full_settings_and_skills_store():
    from agent_code.server import ALLOWED_METHODS
    expected = {
        "get_skill_store_state", "skill_store_auth", "skill_store_logout",
        "skill_store_list", "skill_store_detail", "skill_store_install",
        "list_provider_models", "podman_status", "podman_action", "connect_ssh", "disconnect_ssh",
    }
    assert expected <= ALLOWED_METHODS


def test_web_settings_save_preserves_multiple_keys_and_applies_desktop_options(monkeypatch):
    import copy
    from types import SimpleNamespace
    import sys, types
    import agent_code.web_desktop as web
    agent = types.ModuleType("agent_code.agent")
    agent.normalize_keys = lambda values: list(values or [])
    agent.make_client = lambda keys, base, provider: {"keys": keys, "base": base}
    monkeypatch.setitem(sys.modules, "agent_code.agent", agent)

    config = {"openai_api_keys": ["old-key"], "permission_mode": "ask",
              "execution_mode": "build", "skill_store_server": "https://skills-manager.freesrv.com"}
    monkeypatch.setattr(web, "load_config", lambda: copy.deepcopy(config))
    def save(value):
        config.clear(); config.update(copy.deepcopy(value))
    monkeypatch.setattr(web, "save_config", save)
    engine = SimpleNamespace(execution_mode="build", permission="ask", security_config={},
        ultra_unrestricted_enabled=False, allow_unrestricted_host_shell=False,
        core_mode=False, cloud_sync=False, max_repair_attempts=3,
        provider_name="OpenAI", model="", base_url="https://api.openai.com/v1",
        _reload_tools=lambda: None)
    api = web.AgentWebAPI(engine, web.WebviewRoot())
    result = api.save_settings({"provider_name": "Custom", "openai_model": "model-x",
        "openai_base_url": "https://example.invalid/v1", "api_keys": "key-a\nkey-b",
        "permission_mode": "ask", "execution_mode": "max", "browser_type": "firefox",
        "browser_executable_path": "/usr/bin/firefox", "core_mode": True,
        "ssh_connection": {"host": "example.invalid", "port": "2222"}})
    assert result["ok"]
    assert config["openai_api_keys"] == ["key-a", "key-b"]
    assert config["browser_type"] == "firefox"
    assert config["ssh_connection"]["port"] == "2222"
    assert engine.execution_mode == "max" and engine.core_mode is True
    api.root.destroy()


def test_web_workspace_ide_write_is_confined_and_rejects_sensitive_paths(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from agent_code.web_desktop import AgentWebAPI, WebviewRoot

    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    api = AgentWebAPI(SimpleNamespace(todo=SimpleNamespace(items=[])), WebviewRoot())
    monkeypatch.setattr(AgentWebAPI, "_workspace", staticmethod(lambda: root))

    created = api.write_workspace_file("src/main.py", "print('hello')", create=True)
    assert created["ok"]
    assert (root / "src/main.py").read_text(encoding="utf-8") == "print('hello')"
    saved = api.write_workspace_file("src/main.py", "print('updated')")
    assert saved["ok"] and (root / "src/main.py").read_text(encoding="utf-8") == "print('updated')"
    assert not api.write_workspace_file("../outside.txt", "bad", create=True)["ok"]
    assert not api.write_workspace_file(str(outside), "bad", create=True)["ok"]
    assert not api.write_workspace_file(".env", "SECRET=x", create=True)["ok"]
    assert outside.read_text(encoding="utf-8") == "keep"
    api.root.destroy()
