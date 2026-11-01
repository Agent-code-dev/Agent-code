import json
from pathlib import Path

from agent_code.addons import AddonAPI, AddonManager, create_addon_template


def test_addon_template_loads_and_registers_hook(tmp_path):
    folder = create_addon_template(tmp_path, "sample-addon", "Sample")
    manager = AddonManager(tmp_path)
    schemas, callables, commands = manager.load()
    assert folder.exists()
    assert schemas == []
    assert callables == {}
    assert commands == {}
    assert [x.name for x in manager.infos] == ["sample-addon"]
    assert manager.emit("tools_loaded", app=None) == [None]


def test_addon_registers_tool_command_and_action(tmp_path):
    folder = tmp_path / "demo"
    folder.mkdir()
    (folder / "addon.json").write_text(json.dumps({"name": "demo", "version": "1"}))
    (folder / "addon.py").write_text('''
def register(api):
    api.register_tool({"type":"function","function":{"name":"demo_ping","description":"Ping","parameters":{"type":"object","properties":{}}}}, lambda: "pong")
    api.register_command("hello", lambda args, log: "hello", "Say hello")
    api.register_action("open", lambda: None)
''')
    manager = AddonManager(tmp_path)
    schemas, callables, commands = manager.load()
    assert schemas[0]["function"]["name"] == "demo_ping"
    assert callables["demo_ping"]() == "pong"
    assert commands["demo:hello"]["handler"]([], None) == "hello"
    assert manager.actions[0]["name"] == "open"


def test_disabled_addon_is_not_imported(tmp_path):
    folder = tmp_path / "disabled"
    folder.mkdir()
    (folder / "addon.json").write_text(json.dumps({"name": "disabled"}))
    (folder / "addon.py").write_text('raise RuntimeError("should not execute")')
    manager = AddonManager(tmp_path, ["disabled"])
    assert manager.load() == ([], {}, {})
    assert manager.infos[0].enabled is False


def test_duplicate_tool_name_is_reported_without_crashing(tmp_path):
    for name in ("one", "two"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "addon.json").write_text(json.dumps({"name": name}))
        (folder / "addon.py").write_text('''
def register(api):
    api.register_tool({"type":"function","function":{"name":"shared","parameters":{"type":"object","properties":{}}}}, lambda: 1)
''')
    manager = AddonManager(tmp_path)
    manager.load()
    assert len(manager.callables) == 1
    assert any("duplicate add-on tool name" in info.error for info in manager.infos)


def test_addon_can_register_live_ui_contribution(tmp_path):
    folder = tmp_path / "ui-addon"
    folder.mkdir()
    (folder / "addon.json").write_text(json.dumps({"name": "ui-addon"}))
    (folder / "addon.py").write_text('''
def build(parent, app):
    return {"parent": parent, "app": app}
def register(api):
    api.register_ui("extra-page", build, location="sidebar", label="Extra page")
''')
    manager = AddonManager(tmp_path)
    manager.load()
    parent, app = object(), object()
    built = manager.build_ui("sidebar", parent, app)
    assert built == [{"parent": parent, "app": app}]


def test_addon_can_replace_named_application_service(tmp_path):
    folder = tmp_path / "store-addon"
    folder.mkdir()
    (folder / "addon.json").write_text(json.dumps({"name": "store-addon"}))
    (folder / "addon.py").write_text('''
class CustomStore:
    endpoint = "https://example.invalid/api"
def register(api):
    api.register_service("skill_store", CustomStore(), replaces=True, priority=20)
''')
    manager = AddonManager(tmp_path)
    manager.load()
    default = object()
    service = manager.resolve_service("skill_store", default)
    assert service is not default
    assert service.endpoint == "https://example.invalid/api"


def test_addon_service_default_is_preserved_when_no_override(tmp_path):
    manager = AddonManager(tmp_path)
    default = object()
    assert manager.resolve_service("skill_store", default) is default


def test_service_priority_prefers_replacement_and_higher_priority(tmp_path):
    for name, priority, value in (("low", 1, "low"), ("high", 10, "high")):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "addon.json").write_text(json.dumps({"name": name}))
        (folder / "addon.py").write_text(f'''\nclass Service:\n    value = {value!r}\ndef register(api):\n    api.register_service("skill_store", Service(), replaces=True, priority={priority})\n''')
    manager = AddonManager(tmp_path)
    manager.load()
    assert manager.resolve_service("skill_store").value == "high"
