import json

from agent_code.interactive import TaskHistoryStore, TaskState


def test_history_keeps_multiple_tasks_and_orders_newest(tmp_path):
    history = TaskHistoryStore(tmp_path / "tasks")
    first = TaskState("a1", "first objective", status="completed")
    first.trajectory.append({"kind": "finished", "summary": "done", "time": 10})
    second = TaskState("b2", "second objective", status="running")
    second.created_at = 20
    second.updated_at = 20
    history.save(first)
    history.save(second)

    items = history.list_states()
    assert [item.task_id for item in items] == ["b2", "a1"]
    assert history.get("a1").trajectory[0]["summary"] == "done"


def test_history_ignores_corrupt_files_and_limits_results(tmp_path):
    history = TaskHistoryStore(tmp_path / "tasks")
    history.save(TaskState("a1", "one"))
    history.save(TaskState("b2", "two"))
    (tmp_path / "tasks" / "corrupt.json").write_text("{broken", encoding="utf-8")
    assert len(history.list_states(limit=1)) == 1
    assert len(history.list_states()) == 2


def test_history_rejects_unsafe_task_ids(tmp_path):
    history = TaskHistoryStore(tmp_path / "tasks")
    assert history.get("../outside") is None
    assert not (tmp_path / "outside.json").exists()


def test_history_prunes_oldest_items(tmp_path):
    history = TaskHistoryStore(tmp_path / "tasks", max_tasks=2)
    for task_id, timestamp in (("a1", 1), ("b2", 2), ("c3", 3)):
        state = TaskState(task_id, task_id)
        state.updated_at = timestamp
        history.save(state)
    assert {item.task_id for item in history.list_states()} == {"b2", "c3"}


def test_checkpoint_persists_restartable_conversation_and_omits_images(tmp_path):
    history = TaskHistoryStore(tmp_path / "tasks")
    state = TaskState("c3", "continue implementation", status="running")
    store = history.store_for(state.task_id)
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": [
            {"type": "text", "text": "inspect this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,SECRET"}},
        ]},
        {"role": "assistant", "content": "I will inspect the project."},
        {"role": "tool", "tool_call_id": "call-1", "content": "Files listed."},
    ]
    store.checkpoint(state, messages, summary="Completed file inspection")
    loaded = history.get("c3")
    assert loaded is not None
    assert loaded.conversation[-1]["content"] == "Files listed."
    assert "SECRET" not in json.dumps(loaded.conversation)
    assert loaded.trajectory[-1]["kind"] == "checkpoint"


def test_checkpoint_rejects_invalid_status_and_round_trips(tmp_path):
    history = TaskHistoryStore(tmp_path / "tasks")
    state = TaskState("d4", "resume me")
    history.store_for("d4").checkpoint(state, [{"role": "user", "content": "resume me"}])
    loaded = history.get("d4")
    assert loaded is not None
    assert loaded.conversation == [{"role": "user", "content": "resume me"}]
