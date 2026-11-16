import json
from agent_code.blueprint import BlueprintStore


def test_blueprint_store_round_trip_and_defaults(tmp_path):
    store = BlueprintStore(tmp_path)
    path = store.save({"title": "NovaOS", "goal": "Build a coherent OS", "milestones": ["boot"]})
    assert path == tmp_path / ".agent-code" / "blueprint.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 1
    assert saved["requirements"] == []
    assert saved["acceptance_criteria"] == []
    assert store.load()["milestones"] == ["boot"]
    assert "ACTIVE PROJECT BLUEPRINT" in store.prompt_context()


def test_invalid_blueprint_is_not_loaded(tmp_path):
    store = BlueprintStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text('{"schema_version": 999}', encoding="utf-8")
    assert store.load() is None
    assert "No project blueprint" in store.prompt_context()
