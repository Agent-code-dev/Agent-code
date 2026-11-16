import base64
import hashlib
import http.server
import importlib.util
import io
import json
import threading
import urllib.request
import zipfile
from pathlib import Path

SERVER = Path(__file__).parents[1] / "server" / "skill-server.py"
spec = importlib.util.spec_from_file_location("agent_code_skill_server_addons", SERVER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def addon_zip(name="sample-addon"):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("addon.json", json.dumps({"name": name, "version": "1.2.0"}))
        z.writestr("addon.py", "def register(api): pass\n")
    return out.getvalue()


def test_admin_publish_public_list_and_download(tmp_path):
    old = (mod.DB_PATH, mod.STORAGE, mod.ADDON_STORAGE, mod.ADMIN_TOKEN)
    mod.DB_PATH = tmp_path / "db.sqlite"
    mod.STORAGE = tmp_path / "storage"
    mod.ADDON_STORAGE = mod.STORAGE / "addons"
    mod.ADDON_STORAGE.mkdir(parents=True)
    mod.ADMIN_TOKEN = "test-admin-token"
    mod.init_db()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    blob = addon_zip()
    try:
        body = json.dumps({"name": "sample-addon", "version": "1.2.0", "description": "Test", "zip_b64": base64.b64encode(blob).decode()}).encode()
        req = urllib.request.Request(base + "/addons", data=body, method="POST", headers={"Content-Type": "application/json", "X-Admin-Token": "test-admin-token"})
        with urllib.request.urlopen(req) as response:
            published = json.loads(response.read())
        assert published["ok"] is True
        assert published["sha256"] == hashlib.sha256(blob).hexdigest()
        with urllib.request.urlopen(base + "/addons") as response:
            catalogue = json.loads(response.read())["addons"]
        assert catalogue[0]["name"] == "sample-addon"
        assert catalogue[0]["sha256"] == published["sha256"]
        with urllib.request.urlopen(base + "/addons/sample-addon/download") as response:
            assert response.read() == blob
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
        mod.DB_PATH, mod.STORAGE, mod.ADDON_STORAGE, mod.ADMIN_TOKEN = old
