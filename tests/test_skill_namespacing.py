from agent_code.loader import load_skills


def _skill(folder, tool_name, result):
    folder.mkdir()
    (folder / "skill.py").write_text(
        "SKILL = {'name': %r}\n"
        "TOOL_SCHEMAS = [{'type':'function','function':{'name':%r,'description':'x','parameters':{'type':'object','properties':{}}}}]\n"
        "TOOL_CALLABLES = {%r: lambda: %r}\n" % (folder.name, tool_name, tool_name, result),
        encoding="utf-8")


def test_same_tool_name_in_different_skills_is_preserved_and_namespaced(tmp_path):
    _skill(tmp_path / "filesystem", "write_file", "fs")
    _skill(tmp_path / "cloud", "write_file", "cloud")
    schemas, callables, metadata, commands = load_skills(tmp_path, [])
    assert {s["function"]["name"] for s in schemas} == {
        "filesystem_write_file", "cloud_write_file"}
    assert callables["filesystem_write_file"]() == "fs"
    assert callables["cloud_write_file"]() == "cloud"
    assert len(metadata) == 2
    assert commands == {}


def test_remote_only_skill_is_not_imported_on_host(tmp_path):
    folder = tmp_path / "remote_skill"
    folder.mkdir()
    marker = tmp_path / "host_imported.txt"
    (folder / "skill.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('host import happened')\n"
        "SKILL = {'name':'remote_skill','execution':{'target':'sandbox'}}\n"
        "TOOL_SCHEMAS = [{'type':'function','function':{'name':'run','description':'run remotely','parameters':{'type':'object','properties':{}}}}]\n"
        "TOOL_CALLABLES = {'run': lambda: 'remote result'}\n",
        encoding="utf-8")
    schemas, callables, metadata, _ = load_skills(tmp_path, [])
    assert not marker.exists()
    assert schemas[0]["function"]["name"] == "remote_skill_run"
    assert metadata[0]["_remote_only"] is True
    assert "remote Skill callable was invoked on Host" in callables["remote_skill_run"]()


def test_mixed_host_and_remote_tools_are_rejected_to_prevent_host_import(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "skill.py").write_text(
        "SKILL = {'name':'mixed','execution':{'target':'host','tools':{'remote':{'target':'ssh'}}}}\n"
        "TOOL_SCHEMAS = ["
        "{'type':'function','function':{'name':'local','parameters':{'type':'object','properties':{}}}},"
        "{'type':'function','function':{'name':'remote','parameters':{'type':'object','properties':{}}}}]\n"
        "TOOL_CALLABLES = {'local': lambda: 1, 'remote': lambda: 2}\n",
        encoding="utf-8")
    schemas, callables, metadata, _ = load_skills(tmp_path, [])
    assert schemas == [] and callables == {} and metadata == []
