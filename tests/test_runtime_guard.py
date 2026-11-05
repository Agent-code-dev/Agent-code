from pathlib import Path

from agent_code.runtime import AgentLoopGuard, HookBus, PermissionEngine, ProgressTracker, SkillExecutionRouter


def test_identical_tool_calls_are_blocked_after_two_attempts():
    guard = AgentLoopGuard(max_identical_calls=2)
    assert guard.before_call("grep_files", {"pattern": "needle", "path": "."}) is None
    guard.after_call("grep_files", {"pattern": "needle", "path": "."}, "no matches")
    assert guard.before_call("grep_files", {"pattern": "needle", "path": "."}) is None
    assert "LOOP_GUARD" in guard.before_call("grep_files", {"pattern": "needle", "path": "."})


def test_similar_search_phrases_are_detected():
    guard = AgentLoopGuard(max_similar_searches=2)
    for phrase in ("authentication token validation", "validation token authentication"):
        assert guard.before_call("grep_files", {"pattern": phrase, "path": "src"}) is None
        guard.after_call("grep_files", {"pattern": phrase, "path": "src"}, "found")
    assert "LOOP_GUARD" in guard.before_call("grep_files", {"pattern": "token authentication validation", "path": "src"})


def test_unchanged_file_reads_are_cached_and_changed_files_invalidate_cache(tmp_path):
    file = tmp_path / "a.txt"
    file.write_text("one")
    guard = AgentLoopGuard(workspace=tmp_path)
    args = {"path": "a.txt", "offset": 0, "limit": 20}
    guard.record_read("read_file", args, "one")
    assert guard.cached_read("read_file", args) == "one"
    file.write_text("two and changed")
    assert guard.cached_read("read_file", args) is None


def test_progress_tracker_records_real_tool_results():
    tracker = ProgressTracker()
    tracker.reset("edit a file")
    tracker.record("write_file", {"path": "a.py"}, "OK")
    assert tracker.snapshot()["tool_calls"] == 1
    assert tracker.snapshot()["unique_tool_calls"] == 1
    assert tracker.completed[0]["success"] is True


def test_hook_bus_supports_veto_and_isolates_noncritical_errors():
    hooks = HookBus()
    hooks.register("before_tool_call", lambda **_: False)
    try:
        hooks.emit("before_tool_call", fail_closed=True)
    except PermissionError:
        pass
    else:
        raise AssertionError("a veto hook must block the operation")
    hooks.register("after_tool_call", lambda **_: (_ for _ in ()).throw(RuntimeError("bad hook")))
    assert hooks.emit("after_tool_call") == []


def test_permission_engine_maps_core_names_and_treats_extensions_as_untrusted():
    policy = PermissionEngine()
    assert policy.classify("core_read_file") == "read"
    assert policy.classify("core_write_file") == "stateful"
    assert policy.classify("browser_open_page") == "extension"


def test_skill_router_never_falls_back_from_unavailable_remote_target():
    router = SkillExecutionRouter()
    try:
        router.execute(target="sandbox", handler=lambda: "host", args={}, context={})
    except RuntimeError as exc:
        assert "No host fallback" in str(exc)
    else:
        raise AssertionError("sandbox execution must fail closed when no provider exists")


def test_reading_same_file_with_many_different_ranges_is_bounded(tmp_path):
    file = tmp_path / "large.txt"
    file.write_text("x" * 1000)
    guard = AgentLoopGuard(workspace=tmp_path)
    for offset in range(8):
        args = {"path": "large.txt", "offset": offset * 10, "limit": 10}
        assert guard.before_call("read_file", args) is None
        guard.after_call("read_file", args, "read")
    blocked = guard.before_call("read_file", {"path": "large.txt", "offset": 90, "limit": 10})
    assert blocked and "inspected" in blocked


def test_planning_engine_requires_plan_for_complex_work_and_delegation():
    from agent_code.runtime import PlanningEngine, VerificationEngine
    planner = PlanningEngine()
    decision = planner.analyze("Implement the frontend and backend and add tests across the whole project")
    assert decision["planning_required"] is True
    assert decision["parallelizable"] is True
    assert "todo_write" in planner.directive("Implement a whole project architecture", delegation_required=True)
    verifier = VerificationEngine(max_attempts=2)
    assert verifier.should_verify(changed_paths={"a.py"}, status="complete")
    verifier.record({"passed": False})
    assert verifier.attempts == 1
    assert verifier.should_verify(changed_paths={"a.py"}, status="complete")
