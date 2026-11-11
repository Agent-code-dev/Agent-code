import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent_code.interactive import AskUserBroker, TaskState, TaskStateStore, UserQuestion


class AskUserTests(unittest.TestCase):
    def test_choice_round_trip(self):
        events = []
        broker = AskUserBroker(events.append)
        question = UserQuestion.create("Which database?", ["SQLite", "PostgreSQL"])
        result = []
        worker = threading.Thread(target=lambda: result.append(broker.ask(question, timeout=2)))
        worker.start()
        for _ in range(100):
            if events:
                break
            time.sleep(0.005)
        self.assertEqual(events[0]["type"], "ask_user")
        broker.answer_question(question.question_id, choice="SQLite")
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0].choice, "SQLite")

    def test_custom_and_skip_validation(self):
        broker = AskUserBroker()
        q = UserQuestion.create("Choose", ["A"], allow_custom=False, allow_skip=False)
        worker = threading.Thread(target=lambda: broker.ask(q, timeout=2))
        worker.start()
        for _ in range(100):
            if broker.pending_questions():
                break
            time.sleep(0.005)
        with self.assertRaises(ValueError):
            broker.answer_question(q.question_id, custom_text="B")
        with self.assertRaises(ValueError):
            broker.answer_question(q.question_id, skip=True)
        broker.answer_question(q.question_id, choice="A")
        worker.join(2)

    def test_timeout_cleans_pending_question(self):
        broker = AskUserBroker()
        q = UserQuestion.create("Continue?")
        with self.assertRaises(TimeoutError):
            broker.ask(q, timeout=0.01)
        self.assertEqual(broker.pending_questions(), [])


class TaskStateTests(unittest.TestCase):
    def test_atomic_round_trip_and_event_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "task.json"
            store = TaskStateStore(path, max_events=20)
            state = TaskState("task-1", "Build a demo", plan=[{"title": "Inspect"}],
                              trajectory=[{"type": "tool", "name": str(i)} for i in range(30)])
            store.save(state)
            loaded = store.load()
            self.assertEqual(loaded.task_id, "task-1")
            self.assertEqual(len(loaded.trajectory), 20)
            self.assertTrue(path.exists())

    def test_invalid_status_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStateStore(Path(directory) / "task.json")
            with self.assertRaises(ValueError):
                store.save(TaskState("x", "y", status="unknown"))


if __name__ == "__main__":
    unittest.main()
