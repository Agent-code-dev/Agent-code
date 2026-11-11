import json
from pathlib import Path
import pytest


def test_shared_settings_roundtrip_and_atomic_private_file(tmp_path, monkeypatch):
    from agent_code import settings_store
    target = tmp_path / 'agent_config.json'
    monkeypatch.setattr(settings_store, 'user_config_file', lambda: target)
    monkeypatch.setattr(settings_store, '_store', lambda account, secret: account)
    monkeypatch.setattr(settings_store, '_load', lambda account: 'vault-secret')
    source = {
        'provider_name': 'OpenRouter',
        'openai_base_url': 'https://openrouter.ai/api/v1',
        'openai_api_keys': ['secret-value'],
        'saved_providers': {'Work': {'openai_api_keys': ['profile-secret'], 'openai_model': 'x'}},
        'permission_mode': 'ask',
    }
    settings_store.save_config(source)
    raw = json.loads(target.read_text())
    assert 'secret-value' not in target.read_text()
    assert 'profile-secret' not in target.read_text()
    assert raw['openai_api_key_refs'] == ['provider/default/0']
    assert target.stat().st_mode & 0o777 == 0o600
    restored = settings_store.load_config()
    assert restored['provider_name'] == 'OpenRouter'
    assert restored['openai_api_keys'] == ['vault-secret']
    assert restored['saved_providers']['Work']['openai_api_keys'] == ['vault-secret']


def test_settings_reject_non_dictionary(tmp_path, monkeypatch):
    from agent_code import settings_store
    monkeypatch.setattr(settings_store, 'user_config_file', lambda: tmp_path / 'config.json')
    with pytest.raises(TypeError):
        settings_store.save_config([])
