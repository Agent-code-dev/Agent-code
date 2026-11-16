import json
import urllib.error
import pytest
from agent_code.addon_store import AddonStoreClient, AddonStoreError


def test_addon_store_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        AddonStoreClient("http://example.test")


def test_addon_catalogue_endpoint_and_validation(monkeypatch):
    client = AddonStoreClient("https://skills-manager.example")
    monkeypatch.setattr(client, "_request", lambda path: {"addons": [{"name": "editor", "version": "1", "description": "Editor"}, {"name": "../bad"}]})
    result = client.list_addons()
    assert [item["name"] for item in result] == ["editor"]


def test_missing_addon_endpoint_is_clear(monkeypatch):
    client = AddonStoreClient("https://skills-manager.example")
    def missing(path, binary=False):
        raise AddonStoreError("This Skills Store server does not expose the add-on catalogue API yet.")
    monkeypatch.setattr(client, "_request", missing)
    with pytest.raises(AddonStoreError, match="does not expose"):
        client.list_addons()
