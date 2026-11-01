import json

import pytest
pytest.importorskip("customtkinter")
from agent_code import agent


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def set_password(self, service, account, secret):
        self.values[(service, account)] = secret

    def get_password(self, service, account):
        return self.values.get((service, account))


def test_provider_keys_are_stored_outside_config_json(tmp_path, monkeypatch):
    fake = FakeKeyring()
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(agent, "keyring", fake)
    monkeypatch.setattr(agent, "CONFIG_FILE", config_path)

    agent.save_agent_config({
        "openai_api_keys": ["sk-test-primary", "sk-test-secondary"],
        "openai_base_url": "https://example.invalid/v1",
        "saved_providers": {
            "Example": {
                "provider_name": "Example",
                "openai_api_keys": ["sk-profile-secret"],
            }
        },
    })

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    serialized = config_path.read_text(encoding="utf-8")
    assert "sk-test-primary" not in serialized
    assert "sk-test-secondary" not in serialized
    assert "sk-profile-secret" not in serialized
    assert "openai_api_key_refs" in raw

    loaded = agent.load_agent_config()
    assert loaded["openai_api_keys"] == ["sk-test-primary", "sk-test-secondary"]
    assert loaded["saved_providers"]["Example"]["openai_api_keys"] == ["sk-profile-secret"]


def test_saving_secrets_fails_closed_without_keyring(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "keyring", None)
    monkeypatch.setattr(agent, "CONFIG_FILE", tmp_path / "config.json")
    try:
        agent.save_agent_config({"openai_api_keys": ["sk-do-not-write"]})
    except RuntimeError as exc:
        assert "credential storage" in str(exc).lower() or "secure vault" in str(exc).lower()
    else:
        raise AssertionError("Secret save should fail when OS credential vault is unavailable")
    assert not (tmp_path / "config.json").exists()
