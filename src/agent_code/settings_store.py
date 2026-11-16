"""Single shared settings store for GUI, Textual TUI and agent runtime.

Secrets are kept in the OS credential vault; JSON writes are atomic and private.
"""
from __future__ import annotations
import hashlib, json, os, tempfile
from pathlib import Path
from typing import Any
from .paths import user_config_file

SERVICE = "agent-code"
_DEFAULT_BACKEND = object()

def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None

def _store(account: str, secret: str, backend=_DEFAULT_BACKEND) -> str:
    kr = _keyring() if backend is _DEFAULT_BACKEND else backend
    if kr is None:
        raise RuntimeError("Secure credential storage is unavailable; API key was not saved")
    kr.set_password(SERVICE, account, secret)
    if kr.get_password(SERVICE, account) != secret:
        raise RuntimeError("Could not verify credential vault write")
    return account

def _load(account: str, backend=_DEFAULT_BACKEND) -> str:
    kr = _keyring() if backend is _DEFAULT_BACKEND else backend
    if kr is None:
        return ""
    try:
        return kr.get_password(SERVICE, account) or ""
    except Exception:
        return ""

def _keys(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace("\n", ",").split(",")
    return [str(x).strip().strip('"').strip("'") for x in (value or []) if str(x).strip()]

def load_config(*, keyring_backend=_DEFAULT_BACKEND, config_path=None) -> dict:
    path = Path(config_path) if config_path is not None else user_config_file()
    load_secret = _load if keyring_backend is _DEFAULT_BACKEND else lambda account: _load(account, keyring_backend)
    if not path.exists():
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            return {}
    except (OSError, ValueError):
        return {}
    if "openai_api_keys" not in cfg:
        cfg["openai_api_keys"] = [v for ref in cfg.get("openai_api_key_refs", []) if (v := load_secret(ref))]
    profiles = cfg.get("saved_providers", {})
    if isinstance(profiles, dict):
        for name, profile in profiles.items():
            if isinstance(profile, dict) and "openai_api_keys" not in profile:
                profile["openai_api_keys"] = [v for ref in profile.get("openai_api_key_refs", []) if (v := load_secret(ref))]
    return cfg

def save_config(config: dict, *, keyring_backend=_DEFAULT_BACKEND, config_path=None) -> None:
    if not isinstance(config, dict):
        raise TypeError("Settings must be a dictionary")
    disk = dict(config)
    store_secret = _store if keyring_backend is _DEFAULT_BACKEND else lambda account, secret: _store(account, secret, keyring_backend)
    secrets = _keys(disk.pop("openai_api_keys", []))
    refs = list(disk.get("openai_api_key_refs", [])) if not secrets else []
    for i, secret in enumerate(secrets):
        refs.append(store_secret(f"provider/default/{i}", secret))
    disk["openai_api_key_refs"] = refs
    profiles = disk.get("saved_providers", {})
    if isinstance(profiles, dict):
        safe_profiles = {}
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                safe_profiles[name] = profile
                continue
            item = dict(profile)
            pkeys = _keys(item.pop("openai_api_keys", []))
            prefs = list(item.get("openai_api_key_refs", [])) if not pkeys else []
            pid = hashlib.sha256(str(name).encode()).hexdigest()[:20]
            for i, secret in enumerate(pkeys):
                prefs.append(store_secret(f"provider/profile/{pid}/{i}", secret))
            item["openai_api_key_refs"] = prefs
            safe_profiles[name] = item
        disk["saved_providers"] = safe_profiles
    path = Path(config_path) if config_path is not None else user_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".agent-config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(disk, stream, indent=2, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        try: os.chmod(path, 0o600)
        except OSError: pass
    except Exception:
        try: os.unlink(tmp_name)
        except OSError: pass
        raise
