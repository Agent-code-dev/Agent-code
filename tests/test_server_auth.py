import json

import pytest
from fastapi.testclient import TestClient

from agent_code import server


def test_password_hash_is_salted_and_verifies():
    first = server._password_record("a-very-strong-password")
    second = server._password_record("a-very-strong-password")
    assert first["salt"] != second["salt"]
    assert server._verify_password("a-very-strong-password", first)
    assert not server._verify_password("wrong-password", first)


def test_password_minimum_length():
    with pytest.raises(ValueError):
        server._password_record("short")


def test_configure_credentials_persists_only_hash(monkeypatch):
    saved = {}
    monkeypatch.setattr(server, "load_config", lambda: dict(saved))
    def save(value):
        saved.clear(); saved.update(value)
    monkeypatch.setattr(server, "save_config", save)
    user, generated = server.configure_credentials(username="tester")
    assert user == "tester"
    assert generated and len(generated) >= 20
    record = saved["server_auth"]["password"]
    assert "hash" in record and "salt" in record
    assert generated not in json.dumps(saved)
    assert server._verify_password(generated, record)


def test_web_server_requires_login(monkeypatch):
    cfg = {"server_auth": {"username": "tester",
        "password": server._password_record("a-very-strong-password")}}
    monkeypatch.setattr(server, "load_config", lambda: cfg)
    app = server.create_app(engine=object(), root=server.WebviewRoot())
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    denied = client.post("/api/ready", json={"args": []})
    assert denied.status_code == 401
    login = client.post("/login", json={"username": "tester", "password": "a-very-strong-password"})
    assert login.status_code == 200
    assert server.SESSION_COOKIE in client.cookies
    ready = client.post("/api/ready", json={"args": []})
    assert ready.status_code == 200
    assert ready.json()["ok"] is True
    assert client.post("/api/not_a_method", json={"args": []}).status_code == 404
    app.state.agent_code_runtime.root.destroy()


def test_authenticated_browser_gets_web_ui_and_assets(monkeypatch):
    cfg = {"server_auth": {"username": "tester",
        "password": server._password_record("a-very-strong-password")}}
    monkeypatch.setattr(server, "load_config", lambda: cfg)
    root = server.WebviewRoot()
    app = server.create_app(engine=object(), root=root)
    client = TestClient(app, base_url="http://127.0.0.1")
    client.post("/login", json={"username": "tester", "password": "a-very-strong-password"})
    page = client.get("/")
    assert page.status_code == 200
    assert '/assets/app.js' in page.text
    assert '/assets/style.css' in page.text
    script = client.get('/assets/app.js')
    assert script.status_code == 200
    assert "credentials:'same-origin'" in script.text
    assert page.headers["x-frame-options"] == "DENY"
    root.destroy()


def test_server_rejects_unrecognized_host(monkeypatch):
    cfg = {"server_auth": {"username": "tester",
        "password": server._password_record("a-very-strong-password")}}
    monkeypatch.setattr(server, "load_config", lambda: cfg)
    root = server.WebviewRoot()
    app = server.create_app(engine=object(), root=root)
    client = TestClient(app, base_url="http://attacker.example")
    response = client.get("/login")
    assert response.status_code == 400
    root.destroy()
