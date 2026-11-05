from agent_code.tool_namespace import UnifiedToolNamespace, make_tool_name


def schema(name):
    return {"type": "function", "function": {
        "name": name, "description": "test",
        "parameters": {"type": "object", "properties": {}}}}


def test_namespace_uses_source_prefix_and_preserves_original_handler():
    registry = UnifiedToolNamespace()
    handler = lambda: "ok"
    provider_name = registry.register("filesystem", "skill", schema("write_file"),
                                      handler, original_name="write_file")
    assert provider_name == "filesystem_write_file"
    assert registry.resolve(provider_name) is handler
    assert registry.identity(provider_name).original_name == "write_file"


def test_global_registry_resolves_collisions_without_dropping_tools():
    registry = UnifiedToolNamespace()
    first = registry.register_named("core_write_file", "core", "core", "write_file",
                                    schema("write_file"), lambda: "core")
    second = registry.register_named("core_write_file", "my-addon", "addon", "write_file",
                                     schema("write_file"), lambda: "addon")
    assert first == "core_write_file"
    assert second != first
    assert registry.resolve(first)() == "core"
    assert registry.resolve(second)() == "addon"
    assert len(registry.schemas) == 2


def test_long_names_remain_within_provider_limit_and_are_deterministic():
    used = set()
    name = make_tool_name("x" * 80, "y" * 80, used)
    assert len(name) <= 64
    assert name.endswith(name[-8:])
