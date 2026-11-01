from types import SimpleNamespace
import threading
import time

import pytest
pytest.importorskip("customtkinter")
pytest.importorskip("openai")
from agent_code import agent


class FakeFailure(Exception):
    def __init__(self, status_code, message="failure"):
        super().__init__(message)
        self.status_code = status_code
        self.response = SimpleNamespace(headers={})


class FakeEndpoint:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def router_with(*outcomes):
    router = agent._KeyRoutingClient.__new__(agent._KeyRoutingClient)
    router._lock = threading.RLock()
    router._keys = [f"key-{i}" for i in range(len(outcomes))]
    router._clients = []
    router._cooldowns = [0.0] * len(outcomes)
    router._disabled_until = [0.0] * len(outcomes)
    router._next_index = 0
    for outcome in outcomes:
        endpoint = FakeEndpoint(outcome)
        router._clients.append(SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=endpoint)),
            models=SimpleNamespace(list=endpoint)))
    return router


def test_router_round_robins_healthy_keys():
    router = router_with("first", "second")
    assert router._request("chat.completions.create") == "first"
    assert router._request("chat.completions.create") == "second"


def test_router_fails_over_after_rate_limit():
    router = router_with(FakeFailure(429, "rate limit"), "success")
    assert router._request("chat.completions.create") == "success"
    assert router._cooldowns[0] > time.monotonic()


def test_router_temporarily_disables_invalid_key():
    router = router_with(FakeFailure(401, "invalid api key"), "success")
    assert router._request("chat.completions.create") == "success"
    assert router._disabled_until[0] > time.monotonic()


def test_router_does_not_retry_bad_request_on_other_keys():
    router = router_with(FakeFailure(400, "invalid request"), "must-not-run")
    try:
        router._request("chat.completions.create")
    except FakeFailure as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("400 response should be raised immediately")
    assert router._clients[1].chat.completions.create.calls == 0


def test_router_fails_fast_when_all_keys_are_cooling_down():
    router = router_with("unused", "unused")
    router._cooldowns = [time.monotonic() + 30, time.monotonic() + 60]
    try:
        router._request("models.list")
    except RuntimeError as exc:
        assert "cooling down" in str(exc).lower()
    else:
        raise AssertionError("Expected a clear all-keys-cooling-down error")
