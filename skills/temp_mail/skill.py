"""temp_mail skill — multi-provider temp email: send AND receive.

RECEIVE (auto-fallback chain):
  mail.tm     — REST/JSON, no signup, no captcha (primary)
  Guerrilla   — AJAX, receive-only
  PhoboMail   — MCP-based, send+receive

SEND (configure one via /email):
  Resend   100/day  https://resend.com
  Brevo    300/day  https://brevo.com
  Mailjet  200/day  https://mailjet.com

The temp inbox is attached as Reply-To on every send.
"""

import os
import re
import sys
import json
import time
import random
import string
import threading
import subprocess
from pathlib import Path


SKILL = {
    "name": "temp_mail",
    "description": (
        "Temporary email with multi-provider send and receive. "
        "get_temp_email() creates an inbox, check_temp_inbox() lists messages, "
        "read_temp_email(id) reads one, send_email(to,subject,body) sends, "
        "reset_temp_email() rotates, list_providers() shows providers."
    ),
}


# ===========================================================================
# Paths
# ===========================================================================

WORKSPACE = Path(os.environ.get("AGENT_WORKSPACE", "workspace")).resolve()
STATE_FILE = WORKSPACE / ".temp_mail.json"
ROOT = WORKSPACE.parent
AGENT_CFG = ROOT / "agent_config.json"


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ===========================================================================
# Lazy pip install
# ===========================================================================

_import_lock = threading.Lock()
_import_cache = {}


def _try_import(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _pip_install(pip_name, timeout=120):
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return False, str(e)


def _ensure_import(name):
    with _import_lock:
        if name in _import_cache:
            return _import_cache[name]
        if _try_import(name):
            _import_cache[name] = (True, "")
            return True, ""
        ok, out = _pip_install(name)
        if not ok:
            msg = f"pip install {name} failed: {out[:300]}"
            _import_cache[name] = (False, msg)
            return False, msg
        try:
            import importlib
            importlib.invalidate_caches()
        except Exception:
            pass
        if _try_import(name):
            _import_cache[name] = (True, "")
            return True, ""
        msg = f"{name} installed but import fails"
        _import_cache[name] = (False, msg)
        return False, msg


# ===========================================================================
# Email API config
# ===========================================================================

def _load_email_api():
    if not AGENT_CFG.exists():
        return None
    try:
        cfg = json.loads(AGENT_CFG.read_text(encoding="utf-8"))
    except Exception:
        return None
    api = cfg.get("email_api")
    if not api or not api.get("api_key"):
        return None
    return api


# ===========================================================================
# Receive: mail.tm
# ===========================================================================

MAILTM = "https://api.mail.tm"


def _mailtm_create():
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests

    r = requests.get(f"{MAILTM}/domains", timeout=20)
    r.raise_for_status()
    members = r.json().get("hydra:member", [])
    domains = [d["domain"] for d in members if d.get("isActive")]
    if not domains:
        raise RuntimeError("mail.tm has no active domains")

    local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    email = f"{local}@{domains[0]}"
    pw = "".join(random.choices(string.ascii_letters + string.digits, k=18))

    r = requests.post(f"{MAILTM}/accounts",
                      json={"address": email, "password": pw}, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"mail.tm create: {r.status_code} {r.text[:200]}")

    r = requests.post(f"{MAILTM}/token",
                      json={"address": email, "password": pw}, timeout=20)
    r.raise_for_status()
    token = r.json()["token"]

    return {"provider": "mail.tm", "email": email, "password": pw,
            "token": token, "created": time.time()}


def _mailtm_list(state):
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    r = requests.get(f"{MAILTM}/messages",
                     headers={"Authorization": f"Bearer {state['token']}"},
                     timeout=20)
    if r.status_code == 401:
        raise RuntimeError("mail.tm token expired")
    r.raise_for_status()
    return r.json().get("hydra:member", [])


def _mailtm_read(state, msg_id):
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    r = requests.get(f"{MAILTM}/messages/{msg_id}",
                     headers={"Authorization": f"Bearer {state['token']}"},
                     timeout=20)
    r.raise_for_status()
    return r.json()


# ===========================================================================
# Receive: Guerrilla
# ===========================================================================

GUERRILLA = "https://api.guerrillamail.com/ajax.php"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0.0.0 Safari/537.36")


def _g_create():
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.get(GUERRILLA, params={"f": "get_email_address", "ip": "127.0.0.1",
                                 "agent": UA}, timeout=20)
    r.raise_for_status()
    data = r.json()
    email = data.get("email_addr")
    sid = data.get("sid_token")
    if not email or not sid:
        raise RuntimeError(f"guerrilla: unexpected response {data}")
    return {"provider": "guerrilla", "email": email, "sid_token": sid,
            "cookie": s.cookies.get_dict(), "created": time.time()}


def _g_session(state):
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for k, v in (state.get("cookie") or {}).items():
        s.cookies.set(k, v)
    return s


def _g_list(state):
    s = _g_session(state)
    r = s.get(GUERRILLA, params={"f": "check_email", "seq": 0,
                                 "sid_token": state["sid_token"]}, timeout=20)
    r.raise_for_status()
    return r.json().get("list", [])


def _g_read(state, msg_id):
    s = _g_session(state)
    r = s.get(GUERRILLA, params={"f": "fetch_email", "email_id": msg_id,
                                 "sid_token": state["sid_token"]}, timeout=20)
    r.raise_for_status()
    return r.json()


# ===========================================================================
# Receive: PhoboMail
# ===========================================================================

PHOBO_API = "https://phobomail.com/api"


def _phobo_create():
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    r = requests.post(f"{PHOBO_API}/register", json={}, timeout=20)
    r.raise_for_status()
    data = r.json()
    email = data.get("email") or data.get("address")
    api_key = data.get("api_key") or data.get("token")
    if not email:
        raise RuntimeError(f"phobo: unexpected response {data}")
    return {"provider": "phobomail", "email": email,
            "api_key": api_key, "created": time.time()}


def _phobo_list(state):
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    r = requests.get(f"{PHOBO_API}/inbox",
                     headers={"Authorization": f"Bearer {state['api_key']}"},
                     timeout=20)
    r.raise_for_status()
    return r.json().get("messages", [])


def _phobo_read(state, msg_id):
    ok, err = _ensure_import("requests")
    if not ok:
        raise RuntimeError(err)
    import requests
    r = requests.get(f"{PHOBO_API}/inbox/{msg_id}",
                     headers={"Authorization": f"Bearer {state['api_key']}"},
                     timeout=20)
    r.raise_for_status()
    return r.json()


# ===========================================================================
# Provider registry
# ===========================================================================

RECEIVE_PROVIDERS = ["mail.tm", "guerrilla", "phobomail"]

RECEIVE_HANDLERS = {
    "mail.tm":   {"create": _mailtm_create, "list": _mailtm_list, "read": _mailtm_read},
    "guerrilla": {"create": _g_create,     "list": _g_list,     "read": _g_read},
    "phobomail": {"create": _phobo_create, "list": _phobo_list, "read": _phobo_read},
}

SEND_PROVIDERS = {
    "resend":  {"name": "Resend",  "free_limit": "100/day, 3000/mo", "signup": "https://resend.com"},
    "brevo":   {"name": "Brevo",   "free_limit": "300/day, 9000/mo", "signup": "https://brevo.com"},
    "mailjet": {"name": "Mailjet", "free_limit": "200/day, 6000/mo", "signup": "https://mailjet.com"},
}


def _create_inbox():
    errors = []
    for name in RECEIVE_PROVIDERS:
        try:
            state = RECEIVE_HANDLERS[name]["create"]()
            print(f"[temp_mail] inbox via {name}: {state['email']}")
            return state
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"[temp_mail] {name} failed: {e}")
    raise RuntimeError("all receive providers failed:\n  " + "\n  ".join(errors))


def _ensure_inbox():
    state = _load_state()
    if state.get("email") and state.get("provider"):
        return state, None
    try:
        state = _create_inbox()
        _save_state(state)
        return state, None
    except Exception as e:
        return None, f"ERROR creating temp inbox: {e}"


# ===========================================================================
# Send handlers
# ===========================================================================

def _send_resend(api, to, subject, body, reply_to, html=""):
    ok, err = _ensure_import("requests")
    if not ok:
        return f"ERROR: {err}"
    import requests
    from_name = api.get("from_name", "Agent")
    from_addr = api.get("from_addr", "onboarding@resend.dev")
    payload = {
        "from": f"{from_name} <{from_addr}>",
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html
    if reply_to:
        payload["reply_to"] = [reply_to]
    r = requests.post("https://api.resend.com/emails",
                      headers={"Authorization": f"Bearer {api['api_key']}",
                               "Content-Type": "application/json"},
                      json=payload, timeout=30)
    if r.status_code in (200, 201, 202):
        return f"OK sent via Resend from {from_addr} → {to}"
    return f"ERROR: Resend {r.status_code}: {r.text[:300]}"


def _send_brevo(api, to, subject, body, reply_to, html=""):
    ok, err = _ensure_import("requests")
    if not ok:
        return f"ERROR: {err}"
    import requests
    payload = {
        "sender": {"email": api.get("from_addr", ""),
                   "name": api.get("from_name", "Agent")},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    if html:
        payload["htmlContent"] = html
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    r = requests.post("https://api.brevo.com/v3/smtp/email",
                      headers={"api-key": api["api_key"],
                               "Content-Type": "application/json"},
                      json=payload, timeout=30)
    if r.status_code in (200, 201, 202):
        return f"OK sent via Brevo from {api.get('from_addr','?')} → {to}"
    return f"ERROR: Brevo {r.status_code}: {r.text[:300]}"


def _send_mailjet(api, to, subject, body, reply_to, html=""):
    ok, err = _ensure_import("requests")
    if not ok:
        return f"ERROR: {err}"
    import requests
    payload = {
        "From": {"Email": api.get("from_addr", ""),
                 "Name": api.get("from_name", "Agent")},
        "To": [{"email": to}],
        "Subject": subject,
        "TextPart": body,
    }
    if html:
        payload["HTMLPart"] = html
    if reply_to:
        payload["ReplyTo"] = {"email": reply_to}
    r = requests.post("https://api.mailjet.com/v3.1/send",
                      auth=(api.get("username", ""), api["api_key"]),
                      json=payload, timeout=30)
    if r.status_code in (200, 201):
        return f"OK sent via Mailjet from {api.get('from_addr','?')} → {to}"
    return f"ERROR: Mailjet {r.status_code}: {r.text[:300]}"


SEND_HANDLERS = {
    "resend":  _send_resend,
    "brevo":   _send_brevo,
    "mailjet": _send_mailjet,
}


# ===========================================================================
# Tools
# ===========================================================================

def get_temp_email():
    state, err = _ensure_inbox()
    if err:
        return err
    api = _load_email_api()
    send_info = (f"{api.get('provider')} (from {api.get('from_addr')})"
                 if api else "NOT configured — run /email")
    return (f"Your temporary email: {state['email']}\n"
            f"receive provider: {state['provider']}\n"
            f"send provider:    {send_info}\n"
            f"Replies land in this inbox.")


def reset_temp_email():
    _save_state({})
    return get_temp_email()


def list_providers():
    lines = ["RECEIVE (auto chain):"]
    for name in RECEIVE_PROVIDERS:
        lines.append(f"  {name}")
    lines.append("")
    lines.append("SEND (configure via /email):")
    for key, p in SEND_PROVIDERS.items():
        lines.append(f"  {key:<10} {p['name']:<10} {p['free_limit']:<20} {p['signup']}")
    api = _load_email_api()
    lines.append("")
    lines.append(f"Active send provider: {api.get('provider') if api else '(none)'}")
    return "\n".join(lines)


COMMON_TYPOS = {
    "gmaill.com": "gmail.com", "gmial.com": "gmail.com",
    "gamil.com": "gmail.com", "gmail.co": "gmail.com", "gmail.cm": "gmail.com",
    "hotmial.com": "hotmail.com", "hotmai.com": "hotmail.com",
    "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com",
    "outlok.com": "outlook.com", "outllook.com": "outlook.com",
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def send_email(to: str, subject: str, body: str, html: str = ""):
    to = (to or "").strip().lower()
    if not EMAIL_RE.match(to):
        return f"ERROR: invalid email address: {to!r}"
    domain = to.split("@", 1)[1]
    if domain in COMMON_TYPOS:
        return (f"ERROR: '{domain}' looks like a typo. "
                f"Did you mean '{COMMON_TYPOS[domain]}'? "
                f"Fix and retry — do NOT resend to the typo.")

    api = _load_email_api()
    if not api:
        return (
            "ERROR: email sending not configured.\n\n"
            "Pick one free provider (no captcha):\n"
            "  Resend  — https://resend.com  (100/day)\n"
            "  Brevo   — https://brevo.com   (300/day)\n"
            "  Mailjet — https://mailjet.com (200/day)\n\n"
            "Then run one of:\n"
            "  /email resend  re_YOUR_KEY\n"
            "  /email brevo   xkeysib-YOUR_KEY you@yourdomain.com\n"
            "  /email mailjet USERNAME SECRET you@yourdomain.com\n"
            "Do NOT retry send_email until /email is configured."
        )

    provider = (api.get("provider") or "resend").lower()
    fn = SEND_HANDLERS.get(provider)
    if not fn:
        return f"ERROR: unknown send provider: {provider}"

    state = _load_state()
    reply_to = state.get("email") if state else None
    return fn(api, to, subject, body, reply_to, html)


def check_temp_inbox():
    state, err = _ensure_inbox()
    if err:
        return err
    provider = state.get("provider")
    handler = RECEIVE_HANDLERS.get(provider)
    if not handler:
        return f"ERROR: unknown provider {provider}"
    try:
        msgs = handler["list"](state)
        if not msgs:
            return f"Inbox {state['email']} is empty."
        lines = [f"Inbox {state['email']} ({provider}) — {len(msgs)} message(s):"]
        for m in msgs[:15]:
            if provider == "mail.tm":
                mid = m.get("id", "?")
                frm = (m.get("from") or {}).get("address", "?")
                subj = m.get("subject", "?")
            elif provider == "guerrilla":
                mid = m.get("mail_id", "?")
                frm = m.get("mail_from", "?")
                subj = m.get("mail_subject", "?")
            else:
                mid = m.get("id", "?")
                frm = m.get("from", "?")
                subj = m.get("subject", "?")
            lines.append(f"  id={mid} | from={frm} | subject={subj}")
        return "\n".join(lines)
    except Exception as e:
        _save_state({})
        return f"ERROR: {provider} failed ({e}). State cleared — call get_temp_email."


def read_temp_email(email_id: str):
    state = _load_state()
    provider = state.get("provider")
    handler = RECEIVE_HANDLERS.get(provider)
    if not handler:
        return "ERROR: no inbox — call get_temp_email first"
    try:
        m = handler["read"](state, email_id)
        if provider == "mail.tm":
            text = m.get("text") or ""
            if not text and m.get("html"):
                text = re.sub(r"<[^>]+>", " ", m["html"])
                text = re.sub(r"\s+", " ", text).strip()
            frm = (m.get("from") or {}).get("address", "?")
            return f"From: {frm}\nSubject: {m.get('subject','?')}\n---\n{text[:3000]}"
        if provider == "guerrilla":
            text = m.get("mail_body") or ""
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return (f"From: {m.get('mail_from','?')}\n"
                    f"Subject: {m.get('mail_subject','?')}\n---\n{text[:3000]}")
        text = m.get("text") or m.get("body") or ""
        if not text and m.get("html"):
            text = re.sub(r"<[^>]+>", " ", m["html"])
            text = re.sub(r"\s+", " ", text).strip()
        return (f"From: {m.get('from','?')}\n"
                f"Subject: {m.get('subject','?')}\n---\n{text[:3000]}")
    except Exception as e:
        return f"ERROR reading email: {e}"


# ===========================================================================
# OpenAI schemas
# ===========================================================================

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_temp_email",
        "description": "Get (or create) a temporary email address for receiving.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "send_email",
        "description": (
            "Send an email via the configured provider (Resend/Brevo/Mailjet). "
            "The temp inbox is set as Reply-To. If not configured, returns "
            "setup instructions — do NOT retry."
        ),
        "parameters": {"type": "object",
                       "properties": {"to": {"type": "string"},
                                      "subject": {"type": "string"},
                                      "body": {"type": "string"},
                                      "html": {"type": "string"}},
                       "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {
        "name": "check_temp_inbox",
        "description": "List messages in the temp inbox.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_temp_email",
        "description": "Read a specific email by ID.",
        "parameters": {"type": "object",
                       "properties": {"email_id": {"type": "string"}},
                       "required": ["email_id"]}}},
    {"type": "function", "function": {
        "name": "reset_temp_email",
        "description": "Delete the current inbox and create a fresh one.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "list_providers",
        "description": "Show available send and receive email providers.",
        "parameters": {"type": "object", "properties": {}}}},
]

TOOL_CALLABLES = {
    "get_temp_email": get_temp_email,
    "send_email": send_email,
    "check_temp_inbox": check_temp_inbox,
    "read_temp_email": read_temp_email,
    "reset_temp_email": reset_temp_email,
    "list_providers": list_providers,
}


# ===========================================================================
# Chat commands
# ===========================================================================

def _handle_email_command(args: list, log) -> None:
    """Handle /email. args = tokens after '/email'. log(text, tag=None)."""
    def load_cfg() -> dict:
        if AGENT_CFG.exists():
            try:
                return json.loads(AGENT_CFG.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_cfg(c: dict):
        AGENT_CFG.write_text(json.dumps(c, indent=2), encoding="utf-8")

    if not args:
        cfg = load_cfg()
        api = cfg.get("email_api")
        if api:
            log(f"send provider: {api.get('provider')} from {api.get('from_addr')}", "dim")
        else:
            log("send provider: NOT configured", "dim")
            log("setup examples:", "dim")
            log("  /email resend  re_YOUR_KEY", "dim")
            log("  /email brevo   xkeysib-KEY you@domain.com", "dim")
            log("  /email mailjet USER SECRET you@domain.com", "dim")
            log("signup links:", "dim")
            log("  Resend  100/day  https://resend.com", "dim")
            log("  Brevo   300/day  https://brevo.com", "dim")
            log("  Mailjet 200/day  https://mailjet.com", "dim")
        return

    provider = args[0].lower()
    cfg = load_cfg()

    if provider == "resend" and len(args) >= 2:
        cfg["email_api"] = {
            "provider": "resend",
            "api_key": args[1],
            "from_addr": args[2] if len(args) >= 3 else "onboarding@resend.dev",
            "from_name": "Agent",
        }
    elif provider == "brevo" and len(args) >= 3:
        cfg["email_api"] = {
            "provider": "brevo",
            "api_key": args[1],
            "from_addr": args[2],
            "from_name": "Agent",
        }
    elif provider == "mailjet" and len(args) >= 4:
        cfg["email_api"] = {
            "provider": "mailjet",
            "api_key": args[3],
            "username": args[1],
            "from_addr": args[3],
            "from_name": "Agent",
        }
    else:
        log("usage:", "error")
        log("  /email resend  <key> [from@addr]", "error")
        log("  /email brevo   <key> <from@addr>", "error")
        log("  /email mailjet <username> <secret> <from@addr>", "error")
        return

    try:
        save_cfg(cfg)
        log(f"[email] saved — {provider} / {cfg['email_api']['from_addr']}", "dim")
    except Exception as e:
        log(f"[email] error: {e}", "error")


def _handle_providers_command(args: list, log) -> None:
    for line in list_providers().splitlines():
        log(line, "dim")


COMMANDS = {
    "email": {
        "handler": _handle_email_command,
        "description": "Configure email sending (Resend/Brevo/Mailjet)",
    },
    "providers": {
        "handler": _handle_providers_command,
        "description": "List email send + receive providers",
    },
}