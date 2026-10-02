#!/usr/bin/env python3
"""
skill-manager.py — GUI skill store (tkinter) with server fallback and AI warnings.

Server fallback: HTTPS domain primary, raw IP on failure.
Config (~/.skill-manager.json): token, nickname, user_id, my_skills, cached_at
"""

import os
import re
import sys
import json
import time
import base64
import shutil
import zipfile
import threading
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
import tkinter as tk


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_FILE = Path.home() / ".skill-manager.json"

SKILL_SERVER_PRIMARY = "https://skills-manager.freesrv.com"
SKILL_SERVER_FALLBACK = "http://78.154.103.43:9074"
SKILL_SERVERS = [SKILL_SERVER_PRIMARY, SKILL_SERVER_FALLBACK]
DEFAULT_SERVER = SKILL_SERVER_PRIMARY

SKILLS_DIR = Path("skills").resolve()

DEFAULT_CONFIG = {
    "server": DEFAULT_SERVER,
    "token": None,
    "nickname": None,
    "user_id": None,
    "last_login": None,
    "my_skills": [],
    "cached_at": None,
}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/125.0.0.0 Safari/537.36")

CF_MARKERS = (
    "cloudflare", "error 1010", "error 1020", "error 1003",
    "access denied", "just a moment", "cf-ray", "attention required",
)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    cfg["server"] = DEFAULT_SERVER
    return cfg


def save_config(cfg: dict):
    out = {k: cfg.get(k) for k in DEFAULT_CONFIG.keys()}
    out["server"] = DEFAULT_SERVER
    CONFIG_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    try:
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass


def clear_auth(cfg: dict):
    cfg["token"] = None
    cfg["nickname"] = None
    cfg["user_id"] = None
    cfg["last_login"] = None
    cfg["my_skills"] = []
    cfg["cached_at"] = None
    save_config(cfg)


# ---------------------------------------------------------------------------
# skill.md parser
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_skill_md(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip().lower()] = val.strip().strip('"').strip("'")
    return meta


def read_skill_md(folder: Path) -> dict:
    md_path = folder / "skill.md"
    if not md_path.exists():
        return {}
    try:
        return parse_skill_md(md_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_skill_md(folder: Path, name: str, description: str,
                   version: str = "1.0.0", author: str = "", body: str = ""):
    md_path = folder / "skill.md"
    text = ("---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"version: {version}\n"
            f"author: {author}\n"
            "---\n\n"
            f"# {name}\n\n"
            f"{description}\n")
    if body:
        text += "\n" + body.strip() + "\n"
    md_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP with server fallback
# ---------------------------------------------------------------------------

class ApiError(Exception):
    pass


class _FallbackNeeded(Exception):
    pass


def _do_request(server, method, path, cfg, body, auth):
    url = server.rstrip("/") + path
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if auth:
        token = cfg.get("token")
        if not token:
            raise ApiError("not signed in")
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = e.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""

        lower = payload.lower()
        if any(m in lower for m in CF_MARKERS):
            raise _FallbackNeeded(f"Cloudflare block (HTTP {e.code})")

        try:
            err = json.loads(payload)
            if e.code == 202:
                return err
            msg = err.get("error", payload)
        except Exception:
            msg = payload or f"HTTP {e.code}"

        if e.code == 401:
            raise ApiError(f"AUTH_EXPIRED: {msg}")
        if e.code == 403:
            raise ApiError(f"Not allowed: {msg}")
        if e.code == 404:
            raise ApiError(f"not found: {msg}")
        if e.code == 400:
            raise ApiError(f"bad request: {msg}")
        if e.code >= 500:
            raise ApiError(f"server error ({e.code}): {msg}")
        raise ApiError(msg)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise _FallbackNeeded(str(e))


def api(method, path, cfg, body=None, auth=False):
    errors = []
    for server in SKILL_SERVERS:
        try:
            result = _do_request(server, method, path, cfg, body, auth)
            if server != SKILL_SERVERS[0]:
                print(f"  [fallback] responded via {server}")
            return result
        except _FallbackNeeded as e:
            errors.append(f"{server}: {e}")
            continue
    raise ApiError("all servers failed:\n  " + "\n  ".join(errors))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_zip_safe(blob: bytes, target: Path):
    import io
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for member in zf.namelist():
            if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                raise ApiError(f"unsafe zip entry: {member}")
            dest = (target / member).resolve()
            if not str(dest).startswith(str(target)):
                raise ApiError(f"zip entry escapes target: {member}")
        zf.extractall(target)


def is_installed(name: str) -> bool:
    return (SKILLS_DIR / name / "skill.py").exists()


def fmt_time(ts):
    if not ts:
        return "never"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return str(ts)


def _verdict_of(skill_meta):
    """Safely extract the AI verdict from a skill dict."""
    if not isinstance(skill_meta, dict):
        return "safe"
    v = skill_meta.get("ai_verdict") or "safe"
    return str(v).lower()


def _reasons_of(skill_meta):
    if not isinstance(skill_meta, dict):
        return []
    r = skill_meta.get("ai_reasons") or []
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except Exception:
            r = []
    return r if isinstance(r, list) else []


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG        = "#0e1117"
BG_PANEL  = "#161b22"
BG_CARD   = "#1c2128"
BG_HOVER  = "#21262d"
FG        = "#c9d1d9"
FG_DIM    = "#8b949e"
ACCENT    = "#58a6ff"
GREEN     = "#3fb950"
YELLOW    = "#d29922"
RED       = "#f85149"
BORDER    = "#30363d"


def apply_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=BG)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=BG_PANEL)
    style.configure("Card.TFrame", background=BG_CARD)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
    style.configure("PanelDim.TLabel", background=BG_PANEL, foreground=FG_DIM)
    style.configure("Header.TLabel", background=BG_PANEL,
                    foreground=ACCENT, font=("Segoe UI", 15, "bold"))
    style.configure("Sub.TLabel", background=BG_PANEL,
                    foreground=FG_DIM, font=("Segoe UI", 9))
    style.configure("User.TLabel", background=BG_PANEL,
                    foreground=GREEN, font=("Segoe UI", 9, "bold"))
    style.configure("TEntry",
                    fieldbackground=BG_CARD, foreground=FG,
                    insertcolor=FG, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=6)
    style.configure("TButton",
                    background=BG_CARD, foreground=FG,
                    borderwidth=1, focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 10))
    style.map("TButton",
              background=[("active", BG_HOVER), ("disabled", BG_CARD)],
              foreground=[("disabled", FG_DIM)])
    style.configure("Toggle.TButton",
                    background=BG_CARD, foreground=FG_DIM,
                    borderwidth=1, focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 9))
    style.map("Toggle.TButton", background=[("active", BG_HOVER)])
    style.configure("ToggleOn.TButton",
                    background=ACCENT, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 9, "bold"))
    style.map("ToggleOn.TButton", background=[("active", "#79b8ff")])
    style.configure("Accent.TButton",
                    background=ACCENT, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(16, 8),
                    font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#79b8ff"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_DIM)])
    style.configure("Green.TButton",
                    background=GREEN, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(16, 8),
                    font=("Segoe UI", 10, "bold"))
    style.map("Green.TButton",
              background=[("active", "#56d364"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_DIM)])
    style.configure("Danger.TButton",
                    background="#8b1a1a", foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 10, "bold"))
    style.map("Danger.TButton",
              background=[("active", "#b02121"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_DIM)])
    style.configure("Vertical.TScrollbar",
                    background=BG_PANEL, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG_DIM)


# ---------------------------------------------------------------------------
# Login dialog
# ---------------------------------------------------------------------------

class LoginDialog(tk.Toplevel):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.result = None
        self.title("Sign in")
        self.configure(bg=BG)
        self.geometry("400x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="SKILL STORE", style="Header.TLabel").pack(
            anchor="w", padx=24, pady=(20, 4))
        ttk.Label(pad, text=DEFAULT_SERVER, style="Sub.TLabel").pack(
            anchor="w", padx=24, pady=(0, 4))
        ttk.Label(pad, text=f"(fallback: {SKILL_SERVER_FALLBACK})",
                  style="Sub.TLabel").pack(anchor="w", padx=24, pady=(0, 14))

        body = tk.Frame(pad, bg=BG_PANEL)
        body.pack(fill="x", padx=24)

        ttk.Label(body, text="Nickname", style="Panel.TLabel").pack(anchor="w")
        self.nick_entry = ttk.Entry(body, width=32, font=("Segoe UI", 11))
        self.nick_entry.pack(fill="x", pady=(2, 12))
        self.nick_entry.focus_set()
        if cfg.get("nickname"):
            self.nick_entry.insert(0, cfg["nickname"])

        ttk.Label(body, text="Password", style="Panel.TLabel").pack(anchor="w")
        self.pw_entry = ttk.Entry(body, show="•", font=("Segoe UI", 11))
        self.pw_entry.pack(fill="x", pady=(2, 12))
        self.pw_entry.bind("<Return>", lambda ev: self._login())

        self.hint_lbl = ttk.Label(
            body,
            text="New here? Just pick a nickname — the account is created automatically.",
            style="PanelDim.TLabel", wraplength=340, justify="left")
        self.hint_lbl.pack(anchor="w", pady=(0, 12))

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=24, pady=(8, 20))
        ttk.Button(row, text="Cancel", command=self._cancel).pack(side="right")
        self.go_btn = ttk.Button(row, text="Sign in", style="Accent.TButton",
                                 command=self._login)
        self.go_btn.pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda ev: self._cancel())

    def _login(self):
        nick = self.nick_entry.get().strip()
        pw = self.pw_entry.get()
        if not nick or len(pw) < 4:
            messagebox.showerror("Sign in",
                                 "Nickname required, password ≥ 4 chars",
                                 parent=self)
            return

        self.go_btn.configure(state="disabled", text="…")
        self.hint_lbl.configure(text="Contacting server…")

        def work():
            try:
                try:
                    r = api("POST", "/login", self.cfg,
                            {"nickname": nick, "password": pw})
                    kind = "logged in"
                except ApiError as ex:
                    msg = str(ex).lower()
                    if "invalid" in msg or "not found" in msg or "401" in msg:
                        r = api("POST", "/register", self.cfg,
                                {"nickname": nick, "password": pw})
                        kind = "registered"
                    else:
                        raise
                self.result = (r["token"], r["nickname"], r["user_id"], kind)
                self.after(0, self.destroy)
            except ApiError as ex:
                err_msg = str(ex)
                self.after(0, lambda m=err_msg: messagebox.showerror(
                    "Sign in", m, parent=self))
                self.after(0, lambda: self.go_btn.configure(
                    state="normal", text="Sign in"))
                self.after(0, lambda: self.hint_lbl.configure(
                    text="New here? Just pick a nickname."))

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------
# Publish dialog
# ---------------------------------------------------------------------------

class PublishDialog(tk.Toplevel):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.cfg = cfg
        self.result = None
        self._loaded_folder = None

        self.title("Publish skill")
        self.configure(bg=BG)
        self.geometry("560x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="PUBLISH SKILL", style="Header.TLabel").pack(
            anchor="w", padx=24, pady=(20, 14))

        body = tk.Frame(pad, bg=BG_PANEL)
        body.pack(fill="x", padx=24)

        ttk.Label(body, text="Folder (must contain skill.py + skill.md)",
                  style="Panel.TLabel").pack(anchor="w")
        pfr = tk.Frame(body, bg=BG_PANEL)
        pfr.pack(fill="x", pady=(2, 10))
        self.path_entry = ttk.Entry(pfr, font=("Segoe UI", 10))
        self.path_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(pfr, text="Browse…", command=self._browse).pack(
            side="right", padx=(8, 0))

        self.banner = ttk.Label(body, text="", style="PanelDim.TLabel",
                                wraplength=480, justify="left")
        self.banner.pack(anchor="w", pady=(0, 12))

        ttk.Label(body, text="Name", style="Panel.TLabel").pack(anchor="w")
        self.name_entry = ttk.Entry(body, font=("Segoe UI", 11))
        self.name_entry.pack(fill="x", pady=(2, 12))

        ttk.Label(body, text="Description", style="Panel.TLabel").pack(anchor="w")
        self.desc_entry = ttk.Entry(body, font=("Segoe UI", 11))
        self.desc_entry.pack(fill="x", pady=(2, 12))

        ttk.Label(body, text="Version", style="Panel.TLabel").pack(anchor="w")
        self.ver_entry = ttk.Entry(body, font=("Segoe UI", 11))
        self.ver_entry.insert(0, "1.0.0")
        self.ver_entry.pack(fill="x", pady=(2, 12))

        self.writeback = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="Update skill.md on disk with these values",
                        variable=self.writeback).pack(anchor="w")

        self.status = ttk.Label(pad, text="", style="PanelDim.TLabel")
        self.status.pack(anchor="w", padx=24, pady=(10, 0))

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=24, pady=(16, 20))
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right")
        self.pub_btn = ttk.Button(row, text="Publish", style="Accent.TButton",
                                  command=self._publish)
        self.pub_btn.pack(side="right", padx=(0, 8))

    def _browse(self):
        folder = filedialog.askdirectory(
            title="Select skill folder (must contain skill.py)", parent=self)
        if not folder:
            return
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, folder)
        self._loaded_folder = Path(folder)
        self._load_skill_md()

    def _load_skill_md(self):
        folder = self._loaded_folder
        if not folder or not folder.is_dir():
            return
        has_py = (folder / "skill.py").exists()
        has_md = (folder / "skill.md").exists()
        if not has_py:
            self.banner.configure(
                text="⚠ folder has no skill.py — publishing will fail",
                foreground=RED)
            return
        if not has_md:
            self.banner.configure(
                text="⚠ folder has no skill.md — will be created on publish",
                foreground=YELLOW)
            if not self.name_entry.get():
                self.name_entry.insert(0, folder.name)
            return
        meta = read_skill_md(folder)
        if not meta:
            self.banner.configure(
                text="⚠ skill.md has no frontmatter — will be regenerated",
                foreground=YELLOW)
        else:
            self.banner.configure(
                text=f"✓ loaded from skill.md — author: "
                     f"{meta.get('author', 'unknown')}",
                foreground=GREEN)
        if meta.get("name"):
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, meta["name"])
        elif not self.name_entry.get():
            self.name_entry.insert(0, folder.name)
        if meta.get("description") and not self.desc_entry.get():
            self.desc_entry.delete(0, "end")
            self.desc_entry.insert(0, meta["description"])
        if meta.get("version"):
            self.ver_entry.delete(0, "end")
            self.ver_entry.insert(0, meta["version"])

    def _publish(self):
        path_str = self.path_entry.get().strip()
        name = self.name_entry.get().strip()
        desc = self.desc_entry.get().strip()
        ver = self.ver_entry.get().strip() or "1.0.0"

        if not path_str or not Path(path_str).is_dir():
            messagebox.showerror("Publish", "Folder does not exist", parent=self)
            return
        path = Path(path_str)

        if not (path / "skill.py").exists():
            messagebox.showerror("Publish", "Folder must contain skill.py",
                                 parent=self)
            return
        if not name or not desc:
            messagebox.showerror("Publish", "Name and description required",
                                 parent=self)
            return

        if self.writeback.get():
            try:
                existing = read_skill_md(path)
                body = ""
                md_path = path / "skill.md"
                if md_path.exists() and existing:
                    text = md_path.read_text(encoding="utf-8")
                    parts = text.split("---", 2)
                    if len(parts) >= 3:
                        body = parts[2].strip()
                write_skill_md(path, name, desc, ver,
                               author=self.cfg.get("nickname", ""),
                               body=body)
            except Exception as ex:
                if not messagebox.askyesno(
                        "Publish",
                        f"Could not update skill.md: {ex}\n\nContinue anyway?",
                        parent=self):
                    return

        self.pub_btn.configure(state="disabled")
        self.status.configure(text="packaging…")

        def work():
            try:
                import io
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in path.rglob("*"):
                        if f.is_file():
                            zf.write(f, str(f.relative_to(path)))
                blob = buf.getvalue()
                if len(blob) > 5 * 1024 * 1024:
                    raise ApiError(f"skill too large ({len(blob)} bytes, max 5 MB)")

                self.after(0, lambda: self.status.configure(
                    text=f"uploading {len(blob):,} bytes… AI is reviewing…"))

                r = api("POST", "/skills", self.cfg, auth=True, body={
                    "name": name,
                    "description": desc,
                    "version": ver,
                    "zip_b64": base64.b64encode(blob).decode("ascii"),
                })

                self.result = r or {}
                self.after(0, self.destroy)

                status = (r or {}).get("status", "")
                if status == "queued_for_review":
                    reasons = "\n".join(
                        f"  • {x}" for x in ((r or {}).get("ai_reasons") or [])[:5])
                    verdict = ((r or {}).get("ai_verdict") or "suspicious").upper()
                    summary = ((r or {}).get("ai_summary") or "").strip()
                    self.after(0, lambda v=verdict, s=summary, rs=reasons, n=name:
                               messagebox.showwarning(
                                   "Queued for review",
                                   f"AI flagged '{n}' as {v}.\n\n"
                                   f"{s}\n\n{rs}\n\n"
                                   "It has been queued for admin review. "
                                   "It will appear in the store once approved."))
                elif status == "published":
                    self.after(0, lambda n=name: messagebox.showinfo(
                        "Published",
                        f"'{n}' passed AI review and is now live."))
            except ApiError as ex:
                err_msg = str(ex)
                self.after(0, lambda m=err_msg: messagebox.showerror(
                    "Publish", m, parent=self))
                self.after(0, lambda: self.pub_btn.configure(state="normal"))
                self.after(0, lambda: self.status.configure(text=""))
            except Exception as ex:
                err_msg = f"{type(ex).__name__}: {ex}"
                self.after(0, lambda m=err_msg: messagebox.showerror(
                    "Publish", m, parent=self))
                self.after(0, lambda: self.pub_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class SkillStore(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()

        self.title("Skill Store")
        self.geometry("1160x740")
        self.minsize(1000, 600)
        apply_theme(self)

        # ---- state flags (must be initialized before _build_ui / refresh) ----
        self.installed_only = False
        self.mine_only = False
        self.flagged_only = False
        self.selected_skill = None
        self.selected_skill_meta = None
        self._my_skill_names = {s.get("name") for s in self.cfg.get("my_skills", [])}

        self._build_ui()
        self._restore_session()
        self.after(200, self.refresh_skills)

    # ---- UI ----

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG_PANEL)
        header.pack(fill="x", side="top")

        left = tk.Frame(header, bg=BG_PANEL)
        left.pack(side="left", padx=16, pady=10)
        ttk.Label(left, text="SKILL STORE", style="Header.TLabel").pack(anchor="w")
        ttk.Label(left, text=DEFAULT_SERVER, style="Sub.TLabel").pack(anchor="w")
        ttk.Label(left, text=f"fallback: {SKILL_SERVER_FALLBACK}",
                  style="Sub.TLabel").pack(anchor="w")

        right = tk.Frame(header, bg=BG_PANEL)
        right.pack(side="right", padx=16, pady=10)
        self.user_lbl = ttk.Label(right, text="", style="User.TLabel")
        self.user_lbl.pack(side="right", padx=(0, 12))
        self.login_btn = ttk.Button(right, text="Sign in", style="Accent.TButton",
                                    command=self._on_login_click)
        self.login_btn.pack(side="right")

        # Toolbar
        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill="x", padx=16, pady=(12, 6))

        ttk.Label(toolbar, text="Search:", style="Dim.TLabel").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var,
                                      width=36, font=("Segoe UI", 10))
        self.search_entry.pack(side="left", padx=(8, 8), ipady=2)
        self.search_entry.bind("<Return>", lambda ev: self.refresh_skills())

        ttk.Button(toolbar, text="Search", command=self.refresh_skills).pack(side="left")
        ttk.Button(toolbar, text="Refresh", command=self.refresh_skills).pack(
            side="left", padx=(6, 0))
        self.publish_btn = ttk.Button(toolbar, text="Publish…",
                                      command=self._on_publish_click)
        self.publish_btn.pack(side="left", padx=(6, 0))

        self.mine_btn = ttk.Button(toolbar, text="Mine only",
                                   style="Toggle.TButton",
                                   command=self._toggle_mine)
        self.mine_btn.pack(side="right", padx=(6, 0))
        self.installed_btn = ttk.Button(toolbar, text="Installed only",
                                        style="Toggle.TButton",
                                        command=self._toggle_installed)
        self.installed_btn.pack(side="right")
        self.flagged_btn = ttk.Button(toolbar, text="Flagged only",
                                      style="Toggle.TButton",
                                      command=self._toggle_flagged)
        self.flagged_btn.pack(side="right", padx=(6, 0))

        # Split
        split = tk.Frame(self, bg=BG)
        split.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Tree list
        left_frame = tk.Frame(split, bg=BG_PANEL,
                              highlightbackground=BORDER, highlightthickness=1)
        left_frame.pack(side="left", fill="both", expand=True)

        cols = ("!", "name", "version", "author", "downloads", "mine", "installed")
        self.tree = ttk.Treeview(left_frame, columns=cols, show="headings",
                                 selectmode="browse")
        for c, t, w, a in [
            ("!", "!", 26, "center"),
            ("name", "Name", 200, "w"),
            ("version", "Version", 78, "center"),
            ("author", "Author", 110, "w"),
            ("downloads", "DLs", 55, "e"),
            ("mine", "Yours", 55, "center"),
            ("installed", "Installed", 80, "center"),
        ]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a)

        style = ttk.Style(self)
        style.configure("Treeview",
                        background=BG_PANEL, fieldbackground=BG_PANEL,
                        foreground=FG, bordercolor=BORDER,
                        rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading",
                        background=BG_CARD, foreground=FG_DIM,
                        relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

        self.tree.tag_configure("suspicious", foreground=YELLOW)
        self.tree.tag_configure("malicious", foreground=RED)
        self.tree.tag_configure("reported", foreground=YELLOW)

        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Detail panel
        right_frame = tk.Frame(split, bg=BG_CARD, width=380,
                               highlightbackground=BORDER, highlightthickness=1)
        right_frame.pack(side="right", fill="y", padx=(12, 0))
        right_frame.pack_propagate(False)

        detail = tk.Frame(right_frame, bg=BG_CARD)
        detail.pack(fill="both", expand=True, padx=18, pady=18)
        self._detail_frame = detail

        self.d_name = tk.Label(detail, text="Select a skill",
                               bg=BG_CARD, fg=FG,
                               font=("Segoe UI", 14, "bold"),
                               anchor="w", justify="left", wraplength=340)
        self.d_name.pack(fill="x")

        self.d_meta = tk.Label(detail, text="", bg=BG_CARD, fg=FG_DIM,
                               font=("Segoe UI", 9), anchor="w", justify="left")
        self.d_meta.pack(fill="x", pady=(4, 12))

        self.d_desc = tk.Label(detail, text="", bg=BG_CARD, fg=FG,
                               font=("Segoe UI", 10), anchor="nw",
                               justify="left", wraplength=340)
        self.d_desc.pack(fill="x", pady=(0, 12))

        # warning banner (packed on demand in _show_detail)
        self.d_warn = tk.Label(detail, text="", bg=BG_CARD, fg=YELLOW,
                               font=("Segoe UI", 9),
                               anchor="w", justify="left", wraplength=340)

        self.d_status = tk.Label(detail, text="", bg=BG_CARD, fg=GREEN,
                                 font=("Segoe UI", 9, "bold"), anchor="w")
        self.d_status.pack(fill="x", pady=(0, 12))

        self.d_install_btn = ttk.Button(detail, text="Install",
                                        style="Green.TButton",
                                        command=self._on_install_click)
        self.d_install_btn.pack(fill="x", pady=(0, 6))

        self.d_uninstall_btn = ttk.Button(detail, text="Uninstall",
                                          style="Danger.TButton",
                                          command=self._on_uninstall_click)
        self.d_uninstall_btn.pack(fill="x", pady=(0, 6))

        self.d_report_btn = ttk.Button(detail, text="Report…",
                                       command=self._on_report_click)

        self.d_delete_btn = ttk.Button(detail, text="Delete from server",
                                       style="Danger.TButton",
                                       command=self._on_delete_click)

        # Status bar
        status_bar = tk.Frame(self, bg=BG_PANEL)
        status_bar.pack(fill="x", side="bottom")
        self.status_lbl = ttk.Label(status_bar, text="Ready.",
                                    style="PanelDim.TLabel")
        self.status_lbl.pack(side="left", padx=16, pady=6)
        self.cache_lbl = ttk.Label(status_bar, text="", style="PanelDim.TLabel")
        self.cache_lbl.pack(side="left", padx=16, pady=6)
        self.count_lbl = ttk.Label(status_bar, text="", style="PanelDim.TLabel")
        self.count_lbl.pack(side="right", padx=16, pady=6)

    # ---- session ----

    def _restore_session(self):
        if self.cfg.get("token") and self.cfg.get("nickname"):
            self.user_lbl.configure(
                text=f"● {self.cfg['nickname']}  (id {self.cfg.get('user_id','?')})")
            self.login_btn.configure(text="Sign out",
                                     command=self._on_logout_click)
            self.publish_btn.configure(state="normal")
            cached = self.cfg.get("my_skills", [])
            if cached:
                self.cache_lbl.configure(
                    text=f"cached: {len(cached)} published · "
                         f"last sync {fmt_time(self.cfg.get('cached_at'))}")
            self._refresh_me(silent=True)
        else:
            self.user_lbl.configure(text="not signed in")
            self.publish_btn.configure(state="disabled")

    def _refresh_me(self, silent=False):
        if not self.cfg.get("token"):
            return

        def work():
            try:
                r = api("GET", "/me", self.cfg, auth=True)
                user = r.get("user") or {}
                skills = r.get("skills") or []
                self.cfg["user_id"] = user.get("id")
                self.cfg["nickname"] = user.get("nickname")
                self.cfg["my_skills"] = skills
                self.cfg["cached_at"] = time.time()
                save_config(self.cfg)
                self._my_skill_names = {s.get("name") for s in skills if s.get("name")}

                def ui_update():
                    self.user_lbl.configure(
                        text=f"● {user.get('nickname','?')}  (id {user.get('id','?')})")
                    self.cache_lbl.configure(
                        text=f"cached: {len(skills)} published · "
                             f"last sync {fmt_time(self.cfg['cached_at'])}")
                    if not silent:
                        self.set_status(f"synced: {len(skills)} published")
                    self.refresh_skills()
                self.after(0, ui_update)
            except ApiError as ex:
                msg = str(ex)
                if "AUTH_EXPIRED" in msg:
                    self.after(0, self._handle_expired)
                elif not silent:
                    self.after(0, lambda m=msg: self.set_status(f"error: {m}"))

        threading.Thread(target=work, daemon=True).start()

    def _handle_expired(self):
        messagebox.showwarning(
            "Session expired",
            "Your saved session has expired. Please sign in again.",
            parent=self)
        clear_auth(self.cfg)
        self._my_skill_names = set()
        self.user_lbl.configure(text="not signed in")
        self.login_btn.configure(text="Sign in", command=self._on_login_click)
        self.publish_btn.configure(state="disabled")
        self.cache_lbl.configure(text="")
        self.refresh_skills()

    def _on_login_click(self):
        dlg = LoginDialog(self, self.cfg)
        self.wait_window(dlg)
        if dlg.result:
            token, nick, uid, kind = dlg.result
            self.cfg["token"] = token
            self.cfg["nickname"] = nick
            self.cfg["user_id"] = uid
            self.cfg["last_login"] = time.time()
            save_config(self.cfg)

            self.user_lbl.configure(text=f"● {nick}  (id {uid})")
            self.login_btn.configure(text="Sign out",
                                     command=self._on_logout_click)
            self.publish_btn.configure(state="normal")
            self.set_status(f"{kind} as {nick}")
            self._refresh_me()
            self.refresh_skills()

    def _on_logout_click(self):
        if not messagebox.askyesno("Sign out",
                                   "Sign out and forget saved session?",
                                   parent=self):
            return
        try:
            api("POST", "/logout", self.cfg, {}, auth=True)
        except ApiError:
            pass
        clear_auth(self.cfg)
        self._my_skill_names = set()
        self.user_lbl.configure(text="not signed in")
        self.login_btn.configure(text="Sign in", command=self._on_login_click)
        self.publish_btn.configure(state="disabled")
        self.cache_lbl.configure(text="")
        self.set_status("signed out")
        self.refresh_skills()

    # ---- list ----

    def refresh_skills(self):
        self.set_status("loading skills…")

        def work():
            try:
                path = "/skills"
                q = self.search_var.get().strip()
                if q:
                    path += f"?search={urllib.parse.quote(q)}"
                r = api("GET", path, self.cfg)
                skills = r.get("skills") if isinstance(r, dict) else []
                if not isinstance(skills, list):
                    skills = []
                self.after(0, lambda s=skills: self._populate(s))
            except ApiError as ex:
                msg = str(ex)
                self.after(0, lambda m=msg: self.set_status(f"error: {m}"))
            except Exception as ex:
                import traceback
                traceback.print_exc()
                msg = f"{type(ex).__name__}: {ex}"
                self.after(0, lambda m=msg: self.set_status(f"error: {m}"))

        threading.Thread(target=work, daemon=True).start()

    def _populate(self, skills):
        self.tree.delete(*self.tree.get_children())
        shown = 0
        for s in skills:
            if not isinstance(s, dict):
                continue
            name = s.get("name") or "?"
            installed = is_installed(name)
            is_mine = name in self._my_skill_names

            if self.installed_only and not installed:
                continue
            if self.mine_only and not is_mine:
                continue

            verdict = _verdict_of(s)
            report_count = int(s.get("report_count") or 0)
            flagged = bool(s.get("flagged")) or verdict != "safe" or report_count > 0

            if self.flagged_only and not flagged:
                continue

            if verdict == "malicious":
                warn = "☠"
                tag = "malicious"
            elif verdict == "suspicious":
                warn = "⚠"
                tag = "suspicious"
            elif report_count > 0:
                warn = "⚠"
                tag = "reported"
            else:
                warn = ""
                tag = ""

            self.tree.insert("", "end", iid=name, values=(
                warn,
                name,
                s.get("version", "?"),
                s.get("author", "?"),
                s.get("downloads", 0),
                "★" if is_mine else "",
                "✓" if installed else "",
            ), tags=(tag,) if tag else ())
            shown += 1
        self.count_lbl.configure(text=f"{shown} skill(s)")
        self.set_status("loaded.")

    def _toggle_installed(self):
        self.installed_only = not self.installed_only
        self.installed_btn.configure(
            style="ToggleOn.TButton" if self.installed_only else "Toggle.TButton")
        self.refresh_skills()

    def _toggle_mine(self):
        self.mine_only = not self.mine_only
        self.mine_btn.configure(
            style="ToggleOn.TButton" if self.mine_only else "Toggle.TButton")
        self.refresh_skills()

    def _toggle_flagged(self):
        self.flagged_only = not getattr(self, "flagged_only", False)
        self.flagged_btn.configure(
            style="ToggleOn.TButton" if self.flagged_only else "Toggle.TButton")
        self.refresh_skills()

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        name = sel[0]
        self.selected_skill = name
        self._load_detail(name)

    def _load_detail(self, name):
        self.d_name.configure(text=name)
        self.d_meta.configure(text="loading…")
        self.d_desc.configure(text="")
        self.d_status.configure(text="")
        self.d_install_btn.configure(state="disabled")
        self.d_uninstall_btn.configure(state="disabled")
        self.d_delete_btn.pack_forget()
        self.d_report_btn.pack_forget()
        self.d_warn.pack_forget()

        def work():
            try:
                r = api("GET", f"/skills/{name}", self.cfg)
                skill = r.get("skill") if isinstance(r, dict) else None
                if not isinstance(skill, dict):
                    raise ApiError("invalid response from server")
                self.after(0, lambda s=skill: self._show_detail(s))
            except ApiError as ex:
                msg = str(ex)
                self.after(0, lambda m=msg: self.d_meta.configure(text=f"error: {m}"))
            except Exception as ex:
                msg = f"{type(ex).__name__}: {ex}"
                self.after(0, lambda m=msg: self.d_meta.configure(text=f"error: {m}"))

        threading.Thread(target=work, daemon=True).start()

    def _show_detail(self, s):
        self.selected_skill_meta = s
        name = s.get("name", "?")
        is_mine = name in self._my_skill_names
        installed = is_installed(name)

        self.d_name.configure(text=name)
        parts = [
            f"v{s.get('version','?')}",
            s.get("author", "?"),
            f"{s.get('downloads',0)} downloads",
        ]
        if is_mine:
            parts.append("★ yours")
        self.d_meta.configure(text="  ·  ".join(parts))
        self.d_desc.configure(text=s.get("description", ""))

        # ---- warning banner ----
        verdict = _verdict_of(s)
        reasons = _reasons_of(s)
        reports = s.get("reports") or []
        if not isinstance(reports, list):
            reports = []
        report_count = int(s.get("report_count") or len(reports))

        lines = []
        color = FG_DIM
        title = ""

        if verdict == "malicious":
            title = "☠ SYSTEM FLAGGED: MALICIOUS"
            color = RED
        elif verdict == "suspicious":
            title = "⚠ SYSTEM FLAGGED: SUSPICIOUS"
            color = YELLOW

        if report_count > 0:
            if title:
                title += f"  ·  {report_count} user report(s)"
            else:
                title = f"⚠ {report_count} user report(s)"
                color = YELLOW

        if title:
            lines.append(title)
            summary = (s.get("ai_summary") or "").strip()
            if summary:
                lines.append(f"   {summary}")
            for r in reasons[:5]:
                lines.append(f"   • {r}")
            for r in reports[:3]:
                if not isinstance(r, dict):
                    continue
                detail = (r.get("reason") or "").strip()
                if r.get("details"):
                    detail += f" — {str(r['details'])[:80]}"
                lines.append(f"   • user report: {detail}")

        if lines:
            self.d_warn.configure(text="\n".join(lines), fg=color)
            try:
                self.d_warn.pack(fill="x", pady=(0, 12), before=self.d_status)
            except tk.TclError:
                self.d_warn.pack(fill="x", pady=(0, 12))
        else:
            self.d_warn.pack_forget()

        # ---- status + buttons ----
        if installed:
            self.d_status.configure(text="✓ installed", fg=GREEN)
            self.d_install_btn.configure(state="normal")
            self.d_uninstall_btn.configure(state="normal")
        else:
            self.d_status.configure(text="not installed", fg=FG_DIM)
            self.d_install_btn.configure(state="normal")
            self.d_uninstall_btn.configure(state="disabled")

        # label install button based on verdict
        if verdict in ("malicious", "suspicious") or report_count > 0:
            self.d_install_btn.configure(text="Install anyway…")
        else:
            self.d_install_btn.configure(text="Reinstall" if installed else "Install")

        # report button always available
        self.d_report_btn.pack(fill="x", pady=(0, 6))

        if is_mine:
            self.d_delete_btn.pack(fill="x", pady=(6, 0))
        else:
            self.d_delete_btn.pack_forget()

    # ---- install / uninstall / report / delete ----

    def _on_install_click(self):
        if not self.selected_skill:
            return
        if not self.cfg.get("token"):
            messagebox.showinfo("Install", "Sign in first.", parent=self)
            return

        s = self.selected_skill_meta or {}
        verdict = _verdict_of(s)
        report_count = int(s.get("report_count") or len(s.get("reports") or []))
        name = self.selected_skill

        if verdict == "malicious":
            reasons = "\n".join(f"  • {r}" for r in _reasons_of(s)[:4])
            if not messagebox.askyesno(
                    "⚠ MALICIOUS skill",
                    f"AI flagged '{name}' as MALICIOUS.\n\n"
                    f"{(s.get('ai_summary') or '').strip()}\n\n"
                    f"{reasons}\n\n"
                    "Installing this is dangerous. Continue anyway?",
                    icon="error", parent=self):
                return
        elif verdict == "suspicious" or report_count > 0:
            reasons = "\n".join(f"  • {r}" for r in _reasons_of(s)[:4])
            if not messagebox.askyesno(
                    "⚠ Flagged skill",
                    f"'{name}' was flagged by the system.\n\n"
                    f"AI verdict: {verdict.upper()}\n"
                    f"{(s.get('ai_summary') or '').strip()}\n"
                    f"{reasons}\n"
                    f"User reports: {report_count}\n\n"
                    "Install anyway?",
                    icon="warning", parent=self):
                return

        self.d_install_btn.configure(state="disabled")
        self.set_status(f"installing {name}…")

        def work():
            try:
                r = api("GET", f"/skills/{name}/download", self.cfg, auth=True)
                version = r.get("version", "?")
                blob = base64.b64decode(r["zip_b64"])
                target = SKILLS_DIR / name
                if target.exists():
                    shutil.rmtree(target)
                extract_zip_safe(blob, target)

                def ok():
                    self.set_status(f"✓ installed {name} v{version}")
                    self.refresh_skills()
                    self._load_detail(name)
                self.after(0, ok)
            except ApiError as ex:
                msg = str(ex)
                self.after(0, lambda m=msg: messagebox.showerror(
                    "Install", m, parent=self))
                self.after(0, lambda m=msg: self.set_status(f"error: {m}"))
                self.after(0, lambda: self.d_install_btn.configure(state="normal"))
            except Exception as ex:
                msg = f"{type(ex).__name__}: {ex}"
                self.after(0, lambda m=msg: messagebox.showerror(
                    "Install", m, parent=self))
                self.after(0, lambda: self.d_install_btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    def _on_uninstall_click(self):
        if not self.selected_skill:
            return
        name = self.selected_skill
        if not messagebox.askyesno("Uninstall",
                                   f"Remove '{name}' from ./skills/ ?",
                                   parent=self):
            return
        target = SKILLS_DIR / name
        try:
            if target.exists():
                shutil.rmtree(target)
            self.set_status(f"removed {name}")
            self.refresh_skills()
            self._load_detail(name)
        except Exception as ex:
            msg = f"{type(ex).__name__}: {ex}"
            messagebox.showerror("Uninstall", msg, parent=self)

    def _on_report_click(self):
        if not self.selected_skill:
            return
        name = self.selected_skill

        dlg = tk.Toplevel(self)
        dlg.title(f"Report '{name}'")
        dlg.configure(bg=BG)
        dlg.geometry("480x360")
        dlg.transient(self)
        dlg.grab_set()
        apply_theme(dlg)

        pad = ttk.Frame(dlg, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="REPORT SKILL", style="Header.TLabel").pack(
            anchor="w", padx=20, pady=(16, 4))
        ttk.Label(pad, text=f"Reporting: {name}",
                  style="Sub.TLabel").pack(anchor="w", padx=20, pady=(0, 14))

        body = tk.Frame(pad, bg=BG_PANEL)
        body.pack(fill="both", expand=True, padx=20)

        ttk.Label(body, text="Reason (short)", style="Panel.TLabel").pack(anchor="w")
        reason_entry = ttk.Entry(body, font=("Segoe UI", 11))
        reason_entry.pack(fill="x", pady=(2, 12))
        reason_entry.focus_set()

        ttk.Label(body, text="Details (optional)", style="Panel.TLabel").pack(anchor="w")
        details_text = tk.Text(body, height=6, bg=BG_CARD, fg=FG,
                               relief="flat", padx=8, pady=6,
                               font=("Segoe UI", 10), wrap="word")
        details_text.pack(fill="both", expand=True)

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=20, pady=(12, 16))
        ttk.Button(row, text="Cancel", command=dlg.destroy).pack(side="right")

        def submit():
            reason = reason_entry.get().strip()
            details = details_text.get("1.0", "end").strip()
            if not reason:
                messagebox.showerror("Report", "Reason required", parent=dlg)
                return

            def work():
                try:
                    api("POST", "/report", self.cfg, auth=False, body={
                        "skill": name,
                        "reason": reason,
                        "details": details,
                    })
                    dlg.after(0, lambda: (
                        messagebox.showinfo("Report",
                                            "Thanks — report submitted.",
                                            parent=self),
                        dlg.destroy(),
                        self.refresh_skills(),
                    ))
                except ApiError as ex:
                    msg = str(ex)
                    dlg.after(0, lambda m=msg: messagebox.showerror(
                        "Report", m, parent=dlg))

            threading.Thread(target=work, daemon=True).start()

        ttk.Button(row, text="Submit", style="Accent.TButton",
                   command=submit).pack(side="right", padx=(0, 8))

    def _on_delete_click(self):
        if not self.selected_skill:
            return
        name = self.selected_skill
        if name not in self._my_skill_names:
            return

        if not messagebox.askyesno(
                "Delete from server",
                f"Permanently delete '{name}' from the server?\n\n"
                "This cannot be undone. Other users will no longer be able "
                "to install it.",
                parent=self):
            return
        confirm = messagebox.askstring(
            "Confirm delete",
            f"Type the skill name to confirm:\n\n  {name}",
            parent=self)
        if confirm != name:
            self.set_status("delete cancelled")
            return

        self.set_status(f"deleting {name}…")

        def work():
            try:
                api("DELETE", f"/skills/{name}", self.cfg, auth=True)
                self.cfg["my_skills"] = [
                    s for s in self.cfg.get("my_skills", [])
                    if s.get("name") != name
                ]
                save_config(self.cfg)
                self._my_skill_names.discard(name)

                def ok():
                    self.set_status(f"✓ deleted {name}")
                    self.refresh_skills()
                    self.cache_lbl.configure(
                        text=f"cached: {len(self.cfg['my_skills'])} published · "
                             f"last sync {fmt_time(self.cfg.get('cached_at'))}")
                    self._load_detail(name)
                self.after(0, ok)
            except ApiError as ex:
                msg = str(ex)
                self.after(0, lambda m=msg: messagebox.showerror(
                    "Delete", m, parent=self))
                self.after(0, lambda m=msg: self.set_status(f"error: {m}"))
            except Exception as ex:
                msg = f"{type(ex).__name__}: {ex}"
                self.after(0, lambda m=msg: messagebox.showerror(
                    "Delete", m, parent=self))

        threading.Thread(target=work, daemon=True).start()

    # ---- publish ----

    def _on_publish_click(self):
        if not self.cfg.get("token"):
            messagebox.showinfo("Publish", "Sign in first.", parent=self)
            return
        dlg = PublishDialog(self, self.cfg)
        self.wait_window(dlg)
        if dlg.result:
            status = (dlg.result or {}).get("status", "")
            name = dlg.result.get("name", "?")
            version = dlg.result.get("version", "?")
            if status == "published":
                self.set_status(f"✓ published {name} v{version}")
            elif status == "queued_for_review":
                self.set_status(f"⏳ {name} v{version} queued for review")
            self._refresh_me(silent=True)
            self.refresh_skills()

    def set_status(self, text):
        self.status_lbl.configure(text=text)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main():
    app = SkillStore()
    app.mainloop()


if __name__ == "__main__":
    main()