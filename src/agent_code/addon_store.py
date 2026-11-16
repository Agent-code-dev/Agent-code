"""Client for the optional add-on catalogue hosted alongside the Skills Store.

The client deliberately uses a small documented HTTP contract. Older Skills Store
servers that expose only /skills return a clear unsupported-endpoint error rather
than silently treating native skills as executable add-ons.
"""
from __future__ import annotations
import json
import re
import hashlib
import base64
import io
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class AddonStoreError(RuntimeError):
    pass


class AddonStoreClient:
    def __init__(self, base_url: str, token: str = "", timeout: int = 25):
        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url.startswith("https://"):
            raise ValueError("Store server must use HTTPS")
        self.base_url, self.token, self.timeout = base_url, str(token or ""), int(timeout)

    def _request(self, path: str, *, binary=False):
        headers = {"Accept": "application/octet-stream" if binary else "application/json",
                   "User-Agent": "Agent-Code/2.3.0"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(self.base_url + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                payload = response.read()
            if binary:
                return payload
            data = json.loads(payload.decode("utf-8"))
            if isinstance(data, dict):
                return data
            raise AddonStoreError("Store returned an invalid catalogue response")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise AddonStoreError("This Skills Store server does not expose the add-on catalogue API yet.") from exc
            raise AddonStoreError(f"Store request failed (HTTP {exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AddonStoreError(f"Could not reach the configured Skills Store: {exc}") from exc

    def list_addons(self, search: str = "") -> list[dict]:
        query = ("?search=" + urllib.parse.quote(search.strip())) if search.strip() else ""
        data = self._request("/addons" + query)
        items = data.get("addons", [])
        if not isinstance(items, list):
            raise AddonStoreError("Store catalogue has an invalid addons list")
        return [item for item in items if isinstance(item, dict) and _NAME.fullmatch(str(item.get("name", "")))]

    def download_addon(self, name: str) -> bytes:
        if not _NAME.fullmatch(str(name)):
            raise ValueError("Invalid add-on name")
        return self._request("/addons/" + urllib.parse.quote(name, safe="") + "/download", binary=True)

    def publish_addon(self, folder: Path, admin_token: str, *, author="Agent Code Admin") -> dict:
        """Publish a local add-on to an admin-managed Skills Store catalogue."""
        folder = Path(folder)
        from .addons import _validate_addon_folder
        meta = _validate_addon_folder(folder)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if path.is_symlink():
                    raise AddonStoreError(f"Add-on packages cannot contain symlinks: {path.name}")
                if not path.is_file() or any(part in {".git", "__pycache__", ".venv", "venv"} for part in path.parts) or path.name == ".env":
                    continue
                if path.stat().st_size > 8 * 1024 * 1024:
                    raise AddonStoreError(f"File is too large to publish: {path.name}")
                archive.write(path, path.relative_to(folder).as_posix())
        blob = buffer.getvalue()
        if len(blob) > 32 * 1024 * 1024:
            raise AddonStoreError("Add-on archive exceeds the 32 MB upload limit")
        payload = {"name": meta["name"], "version": str(meta.get("version", "1.0.0")),
                   "description": str(meta.get("description", "")), "author": str(author),
                   "zip_b64": base64.b64encode(blob).decode("ascii")}
        request = urllib.request.Request(self.base_url + "/addons",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json",
                     "X-Admin-Token": str(admin_token), "User-Agent": "Agent-Code/2.3.0"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            return result if isinstance(result, dict) else {}
        except urllib.error.HTTPError as exc:
            try: detail = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception: detail = ""
            raise AddonStoreError(f"Add-on publish failed (HTTP {exc.code}): {detail or 'request rejected'}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AddonStoreError(f"Could not reach the configured Skills Store: {exc}") from exc

    def install_addon(self, name: str, addons_dir: Path, *, replace=False, expected_sha256=None) -> Path:
        import tempfile
        from .addons import install_addon_archive
        blob = self.download_addon(name)
        if len(blob) > 32 * 1024 * 1024:
            raise AddonStoreError("Add-on archive exceeds the 32 MB limit")
        if expected_sha256:
            actual = hashlib.sha256(blob).hexdigest()
            if not re.fullmatch(r"[a-fA-F0-9]{64}", str(expected_sha256)) or actual.lower() != str(expected_sha256).lower():
                raise AddonStoreError("Add-on archive SHA-256 verification failed")
        with tempfile.NamedTemporaryFile(prefix="agent-code-addon-", suffix=".zip", delete=False) as handle:
            handle.write(blob)
            path = Path(handle.name)
        try:
            return install_addon_archive(path, addons_dir, replace=replace)
        finally:
            path.unlink(missing_ok=True)
