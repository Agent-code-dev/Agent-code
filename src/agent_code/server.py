"""Authenticated, cross-platform Agent Code web server.

The server exposes the standalone WebUI and AgentWebAPI. It is intended for
 trusted LAN/VPN access; put a TLS reverse
proxy in front of it before exposing it to the public internet.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
import os
import json
import secrets
import socket
import threading
import time
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from .settings_store import load_config, save_config
from .web_desktop import AgentWebAPI, UI_DIR, WebviewRoot

SESSION_COOKIE = "agent_code_session"
SESSION_TTL = 12 * 60 * 60
PBKDF2_ITERATIONS = 310_000
ALLOWED_METHODS = {
    "ready", "get_state", "send_task", "stop_task", "clear_chat", "set_mode",
    "answer_question", "answer_confirmation", "get_skills", "toggle_skill",
    "get_addons", "toggle_addon", "get_web_addon_components", "get_mcp_servers",
    "add_mcp_server", "connect_mcp", "disconnect_mcp", "get_store_addons",
    "install_store_addon", "save_settings", "clear_activity", "open_workspace", "pick_files",
    "get_workspace_entries", "read_workspace_file", "write_workspace_file", "get_todo", "get_task_history",
    "get_checkpoints", "preview_checkpoint", "get_checkpoint_diff", "get_task_detail",
    "resume_task", "rerun_task", "continue_task",
    "get_blueprint", "save_blueprint", "get_provider_profiles", "save_provider_profile",
    "apply_provider_profile", "delete_provider_profile",
    "get_skill_store_state", "skill_store_auth", "skill_store_logout",
    "skill_store_list", "skill_store_detail", "skill_store_install",
    "list_provider_models", "podman_status", "podman_action", "connect_ssh", "disconnect_ssh",
}


def _password_record(password: str) -> dict[str, str]:
    if len(password) < 12:
        raise ValueError("Server passwords must contain at least 12 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                 PBKDF2_ITERATIONS)
    return {"salt": salt.hex(), "hash": digest.hex(), "algorithm": "pbkdf2_sha256",
            "iterations": PBKDF2_ITERATIONS}


def _verify_password(password: str, record: dict) -> bool:
    try:
        if record.get("algorithm", "pbkdf2_sha256") != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(str(record["salt"]))
        expected = bytes.fromhex(str(record["hash"]))
        iterations = int(record.get("iterations", PBKDF2_ITERATIONS))
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError):
        return False


def configure_credentials(username: str | None = None,
                           password: str | None = None) -> tuple[str, str | None]:
    """Ensure credentials exist; returns (username, one-time generated password)."""
    cfg = load_config()
    # Keep existing OS-vault references intact without re-saving hydrated secrets.
    cfg.pop("openai_api_keys", None)
    for profile in (cfg.get("saved_providers", {}) or {}).values():
        if isinstance(profile, dict):
            profile.pop("openai_api_keys", None)
    auth = cfg.get("server_auth") if isinstance(cfg.get("server_auth"), dict) else {}
    current_user = str(auth.get("username") or "").strip()
    generated = None
    if password is not None:
        auth["password"] = _password_record(password)
    elif not isinstance(auth.get("password"), dict):
        generated = secrets.token_urlsafe(20)
        auth["password"] = _password_record(generated)
    chosen_user = str(username or current_user or "admin").strip()
    if not chosen_user or len(chosen_user) > 64 or any(c.isspace() for c in chosen_user):
        raise ValueError("Username must be 1–64 characters and contain no whitespace.")
    auth["username"] = chosen_user
    cfg["server_auth"] = auth
    save_config(cfg)
    return chosen_user, generated


def _login_html(error: str = "") -> str:
    message = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark">
<title>Sign in · Agent Code</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0e14;color:#edf0f8;font:15px system-ui,-apple-system,sans-serif}}
.card{{width:min(420px,calc(100vw - 32px));padding:34px;border:1px solid #272d3a;border-radius:22px;background:#111722;box-shadow:0 24px 90px #0008}}
.mark{{width:44px;height:44px;display:grid;place-items:center;border-radius:14px;background:#8b7cff;color:white;font-weight:800;font-size:23px}}
h1{{font-size:25px;margin:20px 0 6px}}p{{color:#a5aec0;line-height:1.55}}label{{display:block;margin:18px 0 7px;color:#cbd2e1;font-size:13px}}
input{{width:100%;padding:13px 14px;border:1px solid #30394a;border-radius:11px;background:#0c111a;color:#fff;font:inherit;outline:none}}
input:focus{{border-color:#8b7cff}}button{{width:100%;margin-top:22px;padding:13px;border:0;border-radius:11px;background:#8172f4;color:white;font-weight:700;font:inherit;cursor:pointer}}
.error{{color:#ff9ca7}}.hint{{font-size:12px;color:#7e899d;margin-top:18px}}
</style></head><body><main class="card"><div class="mark">A</div><h1>Welcome back</h1><p>Sign in to your Agent Code workspace.</p>{message}
<form id="login"><label for="username">Username</label><input id="username" autocomplete="username" required maxlength="64">
<label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form><p class="hint">Your credentials are checked by the Agent Code server.</p></main>
<script>document.getElementById('login').addEventListener('submit',async e=>{{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;b.textContent='Signing in…';try{{const r=await fetch('/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username:document.getElementById('username').value,password:document.getElementById('password').value}})}});const d=await r.json();if(!r.ok)throw Error(d.detail||'Sign-in failed');location.replace('/')}}catch(err){{let p=document.querySelector('.error');if(!p){{p=document.createElement('p');p.className='error';e.target.before(p)}}p.textContent=err.message}}finally{{b.disabled=false;b.textContent='Sign in'}}}});</script></body></html>'''


def _lan_addresses() -> list[str]:
    found = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, type=socket.SOCK_STREAM):
            ip = item[4][0]
            if not ip.lower().startswith(("127.", "::1", "169.254.", "fe80:")):
                found.add(ip)
    except OSError:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("192.0.2.1", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            found.add(ip)
        sock.close()
    except OSError:
        pass
    return sorted(found)


class ServerRuntime:
    def __init__(self, engine, root: WebviewRoot, api: AgentWebAPI):
        self.engine, self.root, self.api = engine, root, api
        self.sessions: dict[str, float] = {}
        self.login_attempts: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.RLock()

    def authenticated(self, request: Request) -> bool:
        token = request.cookies.get(SESSION_COOKIE, "")
        if not token:
            return False
        with self.lock:
            expiry = self.sessions.get(token)
            if not expiry:
                return False
            if expiry <= time.time():
                self.sessions.pop(token, None)
                return False
            self.sessions[token] = time.time() + SESSION_TTL
            return True

    def allow_login(self, ip: str) -> bool:
        now = time.time()
        with self.lock:
            attempts = self.login_attempts[ip]
            while attempts and attempts[0] < now - 300:
                attempts.popleft()
            return len(attempts) < 8

    def record_login_failure(self, ip: str):
        with self.lock:
            self.login_attempts[ip].append(time.time())


def create_app(engine=None, root=None) -> FastAPI:
    """Build the authenticated web server. Optional engine/root support tests."""
    owned_engine = engine is None
    if root is None:
        root = WebviewRoot()
    if engine is None:
        from .agent import App as AgentEngine, Browser
        engine = AgentEngine(root, Browser(headless=True), headless=True)
    api = AgentWebAPI(engine, root)
    runtime = ServerRuntime(engine, root, api)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        root.destroy()
        try:
            engine._ask_user_broker.cancel_all()
            engine._save_local_chat()
            engine.browser.close()
            if engine.mcp_manager:
                threading.Thread(target=engine.mcp_manager.close, daemon=True).start()
        except Exception:
            pass

    app = FastAPI(title="Agent Code Server", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.agent_code_runtime = runtime
    app.state.owned_engine = owned_engine

    @app.middleware("http")
    async def secure_request_defaults(request: Request, call_next):
        host = request.url.hostname or ""
        allowed_hosts = {"localhost", socket.gethostname().lower(), socket.getfqdn().lower()}
        allowed_hosts.update(x.strip().lower() for x in os.getenv("AGENT_CODE_SERVER_ALLOWED_HOSTS", "").split(",") if x.strip())
        host_ok = host.lower() in allowed_hosts
        if not host_ok:
            try:
                ipaddress.ip_address(host)
                host_ok = True
            except ValueError:
                host_ok = False
        if not host_ok:
            return JSONResponse({"detail": "Unrecognized Host header. Add this hostname to AGENT_CODE_SERVER_ALLOWED_HOSTS if it is your trusted reverse-proxy domain."}, status_code=400)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        return HTMLResponse(_login_html())

    @app.post("/login")
    async def login(request: Request):
        try:
            if int(request.headers.get("content-length", "0") or 0) > 8192:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
        ip = request.client.host if request.client else "unknown"
        if not runtime.allow_login(ip):
            return JSONResponse({"detail": "Too many sign-in attempts. Wait five minutes and try again."}, status_code=429)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        cfg = load_config()
        auth = cfg.get("server_auth") if isinstance(cfg.get("server_auth"), dict) else {}
        user_ok = hmac.compare_digest(str(payload.get("username", "")), str(auth.get("username", "")))
        pass_ok = _verify_password(str(payload.get("password", "")), auth.get("password", {}))
        if not (user_ok and pass_ok):
            runtime.record_login_failure(ip)
            return JSONResponse({"detail": "Incorrect username or password."}, status_code=401)
        token = secrets.token_urlsafe(32)
        with runtime.lock:
            runtime.sessions[token] = time.time() + SESSION_TTL
            runtime.login_attempts.pop(ip, None)
        response = JSONResponse({"ok": True})
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL, httponly=True,
                            secure=request.url.scheme == "https", samesite="strict", path="/")
        return response

    @app.post("/logout")
    async def logout(request: Request):
        token = request.cookies.get(SESSION_COOKIE, "")
        with runtime.lock:
            runtime.sessions.pop(token, None)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/")
    async def home(request: Request):
        if not runtime.authenticated(request):
            return RedirectResponse("/login", status_code=303)
        index = UI_DIR / "index.html"
        if not index.is_file():
            return HTMLResponse("Agent Code web UI assets are missing.", status_code=500)
        page = index.read_text(encoding="utf-8")
        page = page.replace('href="style.css"', 'href="/assets/style.css"')
        page = page.replace('src="app.js"', 'src="/assets/app.js"')
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/assets/{asset_name}")
    async def assets(asset_name: str, request: Request):
        if not runtime.authenticated(request):
            return RedirectResponse("/login", status_code=303)
        if asset_name not in {"style.css", "app.js"}:
            return Response(status_code=404)
        path = UI_DIR / asset_name
        if not path.is_file():
            return Response(status_code=404)
        return Response(path.read_bytes(), media_type="text/css" if asset_name.endswith(".css") else "text/javascript",
                        headers={"Cache-Control": "no-cache"})

    @app.post("/api/{method_name}")
    async def api_call(method_name: str, request: Request):
        try:
            if int(request.headers.get("content-length", "0") or 0) > 32 * 1024 * 1024:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
        if not runtime.authenticated(request):
            return JSONResponse({"detail": "Authentication required."}, status_code=401)
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.netloc.lower() != request.url.netloc.lower():
                return JSONResponse({"detail": "Cross-origin request rejected."}, status_code=403)
        if method_name not in ALLOWED_METHODS:
            return JSONResponse({"detail": "Unknown API operation."}, status_code=404)
        try:
            payload = await request.json()
            args = payload.get("args", []) if isinstance(payload, dict) else []
            if not isinstance(args, list) or len(args) > 5:
                return JSONResponse({"detail": "Invalid API arguments."}, status_code=400)
            method = getattr(api, method_name)
            result = await run_in_threadpool(method, *args)
            return JSONResponse(result)
        except Exception as exc:
            return JSONResponse({"detail": f"{type(exc).__name__}: {str(exc)[:500]}"}, status_code=400)


    return app


def main(host: str = "0.0.0.0", port: int = 8765, username: str | None = None,
         password: str | None = None) -> int:
    import uvicorn
    if not str(host).strip() or not 1 <= int(port) <= 65535:
        print("Server host must be non-empty and port must be between 1 and 65535.")
        return 2
    try:
        user, generated = configure_credentials(username=username, password=password)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Invalid Agent Code server credentials: {exc}")
        return 2
    from .agent import App as AgentEngine, Browser
    root = WebviewRoot()
    try:
        engine = AgentEngine(root, Browser(headless=True), headless=True)
    except Exception as exc:
        print(f"Agent Code server startup failed: {type(exc).__name__}: {exc}")
        root.destroy()
        return 1
    app = create_app(engine=engine, root=root)
    print("\nAgent Code Server is starting")
    print(f"  Local:      http://127.0.0.1:{port}")
    for address in _lan_addresses():
        family = "IPv6" if ":" in address else "IPv4"
        url_host = f"[{address}]" if family == "IPv6" else address
        print(f"  Network:    http://{url_host}:{port}")
    print(f"  Username:   {user}")
    if generated:
        print(f"  Password:   {generated}")
        print("  Save this password now. It is shown once and is not written to chat history or logs.")
    elif password:
        print("  Password:   updated (not displayed)")
    print("  Security:   use a trusted LAN/VPN; use HTTPS reverse proxy before public exposure.")
    print("  Stop:       Ctrl+C\n")
    try:
        uvicorn.run(app, host=host, port=int(port), log_level="info", access_log=False,
                    proxy_headers=True, forwarded_allow_ips="127.0.0.1,::1")
    except (OSError, ValueError) as exc:
        print(f"Could not start Agent Code server: {exc}")
        root.destroy()
        return 1
    return 0
