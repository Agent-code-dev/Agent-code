"""
agent.py — AI agent with Stop/Continue, local + cloud chat save,
headless browser, sandboxed shell, skill-loaded commands, two-pane Help.

No auto-install of skills — install them yourself via skill-manager.py
into ./skills/ and they'll be picked up on startup.

Deps: DrissionPage, openai
"""

import os
import re
import sys
import json
import time
import shlex
import queue
import threading
import itertools
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont

from DrissionPage import ChromiumPage, ChromiumOptions
from openai import OpenAI

# Load the skill loader from skills/loader.py
sys.path.insert(0, str(Path(__file__).parent / "skills"))
from loader import discover_skills as loader_discover
from loader import load_skills as loader_load
from loader import get_skill_help as loader_get_help


# ===========================================================================
# Paths
# ===========================================================================

ROOT = Path(__file__).parent.resolve()
WORKSPACE = ROOT / "workspace"
SKILLS_DIR = ROOT / "skills"
CHATS_DIR = ROOT / "chats"
CONFIG_FILE = ROOT / "agent_config.json"
CHAT_FILE = CHATS_DIR / "current.json"

WORKSPACE.mkdir(parents=True, exist_ok=True)
SKILLS_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["AGENT_WORKSPACE"] = str(WORKSPACE)

print(f"[sandbox] workspace = {WORKSPACE}")


# ===========================================================================
# Server URLs — primary HTTPS, IP fallback for cloud sync
# ===========================================================================

SKILL_SERVER_PRIMARY  = "https://skills-manager.freesrv.com"
SKILL_SERVER_FALLBACK = "http://78.154.103.43:9074"
SKILL_SERVERS = [SKILL_SERVER_PRIMARY, SKILL_SERVER_FALLBACK]
DEFAULT_SKILL_SERVER = SKILL_SERVER_PRIMARY   # kept for display

SM_CFG_FILE = Path.home() / ".skill-manager.json"
SKILL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36")


def _sm_cfg() -> dict:
    if SM_CFG_FILE.exists():
        try:
            return json.loads(SM_CFG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _sm_server_list() -> list:
    cfg = _sm_cfg()
    servers = []
    custom = cfg.get("server")
    if custom:
        servers.append(custom)
    for s in SKILL_SERVERS:
        if s not in servers:
            servers.append(s)
    return servers


# ===========================================================================
# Config
# ===========================================================================

MAX_TURNS = 30
SHELL_TIMEOUT = 40


def load_agent_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[config] failed to parse: {e}")
    return {}


def save_agent_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def normalize_keys(raw) -> list:
    if isinstance(raw, str):
        raw = [raw]
    if not raw:
        raw = [k.strip() for k in os.getenv("OPENAI_API_KEYS", "").split(",") if k.strip()]
    return [k.strip().strip('"').strip("'") for k in raw if k and k.strip()]


# ===========================================================================
# LLM
# ===========================================================================

def make_client(api_keys: list, base_url: str):
    if not api_keys:
        return None
    if len(api_keys) == 1:
        return OpenAI(api_key=api_keys[0], base_url=base_url)
    cycle = itertools.cycle(api_keys)
    return OpenAI(api_key=lambda: next(cycle), base_url=base_url)


# ===========================================================================
# Shell (sandboxed)
# ===========================================================================

ALLOWED_CMDS = {
    "ls", "pwd", "cd", "cat", "head", "tail", "grep", "find", "wc", "echo",
    "date", "whoami", "git", "python", "python3", "pip", "pip3", "node", "npm",
    "curl", "wget", "sed", "awk", "sort", "uniq", "diff", "tree", "dir",
    "type", "where", "mkdir", "copy", "move",
}
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/", r":\(\)\s*\{", r"mkfs\.", r"dd\s+if=",
    r">\s*/dev/sd", r"format\s+[a-z]:", r"del\s+/[sq]", r"rd\s+/s",
    r"shutdown", r"reboot", r"reg\s+delete", r"regedit",
    r"net\s+user\s+.*\s+/add", r"runas",
]


def _arg_safe(arg: str) -> bool:
    if arg.startswith(("http://", "https://")):
        return True
    if arg.startswith("-"):
        return True
    try:
        p = Path(arg)
        if p.is_absolute():
            return str(p.resolve()).startswith(str(WORKSPACE))
    except Exception:
        pass
    if ".." in re.split(r"[\\/]", arg):
        return False
    return True


def shell_run(command):
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return f"BLOCKED: pattern {pat}"
    if re.search(r"[|&;<>`$]", command):
        return ("BLOCKED: shell metacharacters not allowed. "
                "Run separate commands or write a script file first.")
    try:
        parts = shlex.split(command, posix=False)
    except ValueError as e:
        return f"BLOCKED: parse error {e}"
    if not parts:
        return "BLOCKED: empty"
    base = os.path.basename(parts[0].strip('"')).lower()
    if base not in ALLOWED_CMDS:
        return f"BLOCKED: '{base}' not allowed"
    for arg in parts[1:]:
        if not _arg_safe(arg):
            return f"BLOCKED: arg escapes workspace: {arg}"
    try:
        r = subprocess.run(parts, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=SHELL_TIMEOUT, cwd=str(WORKSPACE), shell=False)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return out[:4000] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout {SHELL_TIMEOUT}s"
    except FileNotFoundError:
        return f"ERROR: command not found: {base}"
    except Exception as e:
        return f"ERROR: {e}"


# ===========================================================================
# Browser
# ===========================================================================

class Browser:
    def __init__(self, headless=True):
        opts = (ChromiumOptions()
                .headless(headless)
                .set_argument("--disable-blink-features=AutomationControlled")
                .set_argument("--no-sandbox")
                .set_argument("--disable-dev-shm-usage")
                .set_user_data_path(str(Path(os.environ.get("TEMP", "/tmp")) / "agent-profile")))
        self.page = ChromiumPage(opts)
        self._lock = threading.Lock()

    def self_test(self):
        with self._lock:
            try:
                self.page.get("https://example.com", timeout=15)
                return f"OK · title={self.page.title!r}"
            except Exception as e:
                return f"FAILED · {e}"

    def navigate(self, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        with self._lock:
            try:
                self.page.get(url, timeout=30)
                time.sleep(0.3)
                return f"OK title={self.page.title!r} url={self.page.url}"
            except Exception as e:
                return f"ERROR: {e}"

    def snapshot(self, max_chars=6000):
        with self._lock:
            try:
                body = self.page.ele("tag:body", timeout=5)
                text = body.text if body else self.page.html
                return (text or "(empty)")[:max_chars]
            except Exception as e:
                return f"ERROR: {e}"

    def links(self, limit=30):
        with self._lock:
            try:
                out = []
                for a in self.page.eles("tag:a")[:limit]:
                    t = (a.text or "").strip()[:80]
                    h = a.attr("href") or ""
                    if t and h:
                        out.append(f"{t} -> {h}")
                return "\n".join(out) or "(no links)"
            except Exception as e:
                return f"ERROR: {e}"

    def click(self, selector):
        with self._lock:
            try:
                ele = self.page.ele(selector, timeout=5)
                if not ele:
                    return f"NOT_FOUND: {selector}"
                ele.click()
                time.sleep(0.3)
                return "OK"
            except Exception as e:
                return f"ERROR: {e}"

    def type_text(self, selector, text, clear=True):
        with self._lock:
            try:
                ele = self.page.ele(selector, timeout=5)
                if not ele:
                    return f"NOT_FOUND: {selector}"
                if clear:
                    try:
                        ele.clear()
                    except Exception:
                        pass
                ele.input(text)
                return "OK"
            except Exception as e:
                return f"ERROR: {e}"

    def scroll(self, pixels=800):
        with self._lock:
            try:
                self.page.scroll.down(int(pixels))
                return f"OK scrolled {pixels}px"
            except Exception as e:
                return f"ERROR: {e}"

    def close(self):
        try:
            self.page.quit()
        except Exception:
            pass


# ===========================================================================
# Core tools + prompt
# ===========================================================================

CORE_SCHEMAS = [
    {"type": "function", "function": {
        "name": "browser_navigate",
        "description": "Open a URL in the headless browser. Faster than shell curl.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "browser_snapshot",
        "description": "Return visible text of the current page.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "browser_links",
        "description": "List clickable links (text -> href).",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "browser_click",
        "description": "Click an element by CSS selector.",
        "parameters": {"type": "object", "properties": {"selector": {"type": "string"}},
                       "required": ["selector"]}}},
    {"type": "function", "function": {
        "name": "browser_type",
        "description": "Type text into an input by CSS selector.",
        "parameters": {"type": "object",
                       "properties": {"selector": {"type": "string"}, "text": {"type": "string"}},
                       "required": ["selector", "text"]}}},
    {"type": "function", "function": {
        "name": "browser_scroll",
        "description": "Scroll the page down by N pixels.",
        "parameters": {"type": "object", "properties": {"pixels": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "shell_run",
        "description": "Run an allowlisted local command inside the sandbox (CWD=./workspace/).",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
]

CORE_PROMPT = f"""You are an autonomous agent with:

A) BROWSER (headless Chromium):
   browser_navigate, browser_snapshot, browser_links, browser_click,
   browser_type, browser_scroll
B) SHELL (sandboxed to {WORKSPACE}):
   shell_run
C) SKILLS (auto-loaded, listed below)

TOOL SELECTION:
- Web tasks → BROWSER FIRST.
- shell_run("curl ...") for raw JSON/XML only. If it returns empty/403/HTML,
  switch to browser_navigate.

SANDBOX:
- Workspace: {WORKSPACE}
- File paths are RELATIVE to it.
- shell_run cannot leave the workspace. No pipes, redirection, ;, &, &&.

ENVIRONMENT: Windows CMD. No heredocs. Multi-line Python → write .py file then run.

FILE CREATION:
- Large files: write_file first chunk, append_file the rest.
- NEVER answer with "hang tight" / "working on it". Either call a tool or
  return the finished result.

WORKFLOW:
1. Plan briefly, then act with tools.
2. After browser_navigate/click, snapshot to verify.
3. Login/CAPTCHA/2FA → STOP and ask.
4. When done, summarize and give the file path.
"""


# ===========================================================================
# Theme
# ===========================================================================

BG        = "#0e1117"
BG_PANEL  = "#161b22"
BG_CARD   = "#1c2128"
BG_INPUT  = "#1c2128"
BG_HOVER  = "#21262d"
FG        = "#c9d1d9"
FG_DIM    = "#8b949e"
ACCENT    = "#58a6ff"
GREEN     = "#3fb950"
YELLOW    = "#d29922"
RED       = "#f85149"
PURPLE    = "#bc8cff"
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
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
    style.configure("PanelDim.TLabel", background=BG_PANEL, foreground=FG_DIM)
    style.configure("Header.TLabel", background=BG_PANEL,
                    foreground=ACCENT, font=("Segoe UI", 12, "bold"))
    style.configure("Status.TLabel", background=BG_PANEL,
                    foreground=FG_DIM, font=("Segoe UI", 9))
    style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG,
                    insertcolor=FG, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=8)
    style.configure("TButton", background=BG_CARD, foreground=FG,
                    borderwidth=1, focusthickness=0, padding=(10, 6),
                    font=("Segoe UI", 9))
    style.map("TButton",
              background=[("active", BG_HOVER), ("disabled", BG_CARD)],
              foreground=[("disabled", FG_DIM)])
    style.configure("Send.TButton", background=ACCENT, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(16, 8),
                    font=("Segoe UI", 10, "bold"))
    style.map("Send.TButton",
              background=[("active", "#79b8ff"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_DIM)])
    style.configure("Stop.TButton", background="#8b1a1a", foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(16, 8),
                    font=("Segoe UI", 10, "bold"))
    style.map("Stop.TButton",
              background=[("active", "#b02121"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_DIM)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 9, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#79b8ff"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_DIM)])
    style.configure("Vertical.TScrollbar", background=BG_PANEL,
                    troughcolor=BG, bordercolor=BG, arrowcolor=FG_DIM)


# ===========================================================================
# Settings dialog
# ===========================================================================

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Settings")
        self.configure(bg=BG)
        self.geometry("580x620")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text="SETTINGS", style="Header.TLabel").pack(
            anchor="w", padx=24, pady=(20, 4))
        ttk.Label(pad, text=str(CONFIG_FILE), style="PanelDim.TLabel").pack(
            anchor="w", padx=24, pady=(0, 14))

        body = tk.Frame(pad, bg=BG_PANEL)
        body.pack(fill="both", expand=True, padx=24)

        ttk.Label(body, text="LLM", style="PanelDim.TLabel").pack(anchor="w")
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(2, 10))

        ttk.Label(body, text="API keys (one per line)", style="Panel.TLabel").pack(anchor="w")
        keys_frame = tk.Frame(body, bg=BG_PANEL)
        keys_frame.pack(fill="x", pady=(2, 10))
        self.keys_text = tk.Text(keys_frame, height=3, bg=BG_INPUT, fg=FG,
                                 insertbackground=FG, relief="flat",
                                 padx=8, pady=6, font=("Consolas", 10), wrap="none")
        self.keys_text.pack(side="left", fill="x", expand=True)
        ks = ttk.Scrollbar(keys_frame, orient="vertical", command=self.keys_text.yview)
        ks.pack(side="right", fill="y")
        self.keys_text.configure(yscrollcommand=ks.set)
        for k in app.api_keys:
            self.keys_text.insert("end", k + "\n")

        ttk.Label(body, text="Base URL", style="Panel.TLabel").pack(anchor="w")
        self.base_entry = ttk.Entry(body, font=("Segoe UI", 11))
        self.base_entry.insert(0, app.base_url)
        self.base_entry.pack(fill="x", pady=(2, 10))

        ttk.Label(body, text="Model", style="Panel.TLabel").pack(anchor="w")
        self.model_entry = ttk.Entry(body, font=("Segoe UI", 11))
        self.model_entry.insert(0, app.model)
        self.model_entry.pack(fill="x", pady=(2, 18))

        ttk.Label(body, text="CLOUD SYNC", style="PanelDim.TLabel").pack(anchor="w")
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(2, 10))
        self.cloud_var = tk.BooleanVar(value=app.cloud_sync)
        ttk.Checkbutton(body, text="Sync chat state to skill-manager server",
                        variable=self.cloud_var).pack(anchor="w", pady=(0, 6))
        ttk.Label(body, text="servers:",
                  style="PanelDim.TLabel").pack(anchor="w", pady=(0, 2))
        for s in app.cloud_servers:
            ttk.Label(body, text=f"  {s}",
                      style="PanelDim.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"account: {app.cloud_user or '(not signed in)'}",
                  style="PanelDim.TLabel").pack(anchor="w", pady=(4, 0))

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=24, pady=(14, 20))
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="right", padx=(0, 8))

    def _save(self):
        keys = [l.strip() for l in self.keys_text.get("1.0", "end").splitlines() if l.strip()]
        base = self.base_entry.get().strip() or "https://api.openai.com/v1"
        model = self.model_entry.get().strip() or "gpt-4o"
        cloud = bool(self.cloud_var.get())
        if not keys:
            messagebox.showerror("Settings", "At least one API key required", parent=self)
            return
        cfg = load_agent_config()
        cfg["openai_api_keys"] = keys
        cfg["openai_base_url"] = base
        cfg["openai_model"] = model
        cfg["cloud_sync"] = cloud
        cfg.setdefault("headless", True)
        cfg.setdefault("disabled_skills", [])
        try:
            save_agent_config(cfg)
        except Exception as e:
            messagebox.showerror("Settings", f"save failed: {e}", parent=self)
            return
        self.app.api_keys = keys
        self.app.base_url = base
        self.app.model = model
        self.app.cloud_sync = cloud
        self.app.client = make_client(keys, base)
        self.app._update_header()
        self.destroy()
        self.app.log_line(f"[settings] saved — model={model}  cloud={cloud}", "dim")


# ===========================================================================
# Skills dialog
# ===========================================================================

class SkillsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Skills")
        self.configure(bg=BG)
        self.geometry("640x540")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text="SKILLS", style="Header.TLabel").pack(
            anchor="w", padx=24, pady=(20, 4))
        ttk.Label(pad, text="Toggle skills on or off. Changes save immediately.",
                  style="PanelDim.TLabel").pack(anchor="w", padx=24, pady=(0, 16))

        list_frame = tk.Frame(pad, bg=BG_PANEL)
        list_frame.pack(fill="both", expand=True, padx=24)
        self.listbox = tk.Listbox(list_frame, bg=BG_CARD, fg=FG,
                                  selectbackground=ACCENT, selectforeground="#ffffff",
                                  relief="flat", font=("Consolas", 10),
                                  activestyle="none", borderwidth=0,
                                  highlightthickness=0, height=10)
        self.listbox.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-1>", lambda e: self._toggle_selected())

        desc_frame = tk.Frame(pad, bg=BG_PANEL)
        desc_frame.pack(fill="x", padx=24, pady=(12, 6))
        ttk.Label(desc_frame, text="Description", style="PanelDim.TLabel").pack(anchor="w")
        self.desc = tk.Text(desc_frame, height=4, bg=BG_CARD, fg=FG,
                            relief="flat", padx=8, pady=6,
                            font=("Segoe UI", 9), wrap="word")
        self.desc.pack(fill="x")
        self.desc.configure(state="disabled")

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=24, pady=(12, 6))
        ttk.Button(row, text="Toggle", style="Accent.TButton",
                   command=self._toggle_selected).pack(side="left")
        ttk.Button(row, text="Enable all", command=self._enable_all).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Disable all", command=self._disable_all).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Close", command=self.destroy).pack(side="right")

        self.status = ttk.Label(pad, text="", style="PanelDim.TLabel")
        self.status.pack(anchor="w", padx=24, pady=(0, 20))

        self.skills = []
        self._refresh()

    def _refresh(self):
        self.listbox.delete(0, "end")
        self.skills = loader_discover(SKILLS_DIR)
        for s in self.skills:
            name = s["name"]
            enabled = name not in self.app.disabled_skills
            mark = "[✓]" if enabled else "[ ]"
            self.listbox.insert("end", f"  {mark}  {name:<24}  v{s.get('version','?')}")
            if not enabled:
                self.listbox.itemconfig("end", foreground=FG_DIM)
        self.status.configure(
            text=f"{len(self.skills)} skill(s) found · {len(self.app.disabled_skills)} disabled")

    def _selected_name(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.skills[sel[0]]["name"]

    def _on_select(self, event):
        name = self._selected_name()
        if not name:
            return
        meta = next((s for s in self.skills if s["name"] == name), None)
        if not meta:
            return
        self.desc.configure(state="normal")
        self.desc.delete("1.0", "end")
        self.desc.insert("1.0", meta.get("description", "(no description)") +
                         f"\n\nauthor: {meta.get('author', '?')}")
        self.desc.configure(state="disabled")

    def _toggle_selected(self):
        name = self._selected_name()
        if not name:
            return
        if name in self.app.disabled_skills:
            self.app.disabled_skills.remove(name)
        else:
            self.app.disabled_skills.append(name)
        self.app._save_disabled_skills()
        self.app._reload_tools()
        self._refresh()

    def _enable_all(self):
        self.app.disabled_skills = []
        self.app._save_disabled_skills()
        self.app._reload_tools()
        self._refresh()

    def _disable_all(self):
        self.app.disabled_skills = [s["name"] for s in self.skills]
        self.app._save_disabled_skills()
        self.app._reload_tools()
        self._refresh()


# ===========================================================================
# Help dialog — two-pane with clickable skills
# ===========================================================================

class HelpDialog(tk.Toplevel):
    """Two-pane help browser. Left: sections + skills. Right: content."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Help")
        self.configure(bg=BG)
        self.geometry("1020x720")
        self.minsize(820, 540)
        self.transient(parent)
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)

        # header
        header = tk.Frame(pad, bg=BG_PANEL)
        header.pack(fill="x", padx=20, pady=(16, 10))
        ttk.Label(header, text="HELP", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="click a section or a skill",
                  style="PanelDim.TLabel").pack(side="left", padx=(12, 0))

        # split body
        body = tk.Frame(pad, bg=BG_PANEL)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        # ---- LEFT: tree ----
        left_wrap = tk.Frame(body, bg=BG_CARD, width=250,
                             highlightbackground=BORDER, highlightthickness=1)
        left_wrap.pack(side="left", fill="y")
        left_wrap.pack_propagate(False)

        style = ttk.Style(self)
        style.configure("Help.Treeview",
                        background=BG_CARD, fieldbackground=BG_CARD,
                        foreground=FG, bordercolor=BORDER,
                        rowheight=26, font=("Segoe UI", 10))
        style.map("Help.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

        self.tree = ttk.Treeview(left_wrap, show="tree",
                                 selectmode="browse", style="Help.Treeview")
        self.tree.column("#0", width=230, stretch=True)
        self.tree.tag_configure("group",
                                foreground=ACCENT,
                                font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("item",
                                foreground=FG,
                                font=("Segoe UI", 10))

        vsb = ttk.Scrollbar(left_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # ---- RIGHT: content ----
        right_wrap = tk.Frame(body, bg=BG_CARD,
                              highlightbackground=BORDER, highlightthickness=1)
        right_wrap.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.content = tk.Text(right_wrap, wrap="word", bg=BG_CARD, fg=FG,
                               relief="flat", padx=18, pady=14,
                               font=("Consolas", 10), borderwidth=0,
                               spacing1=2, spacing3=5)
        self.content.pack(side="left", fill="both", expand=True)
        csb = ttk.Scrollbar(right_wrap, orient="vertical",
                            command=self.content.yview)
        self.content.configure(yscrollcommand=csb.set, state="disabled")
        csb.pack(side="right", fill="y")

        # ---- footer ----
        footer = tk.Frame(pad, bg=BG_PANEL)
        footer.pack(fill="x", padx=20, pady=(0, 16))
        ttk.Button(footer, text="Close", style="Accent.TButton",
                   command=self.destroy).pack(side="right")

        # build content
        self._sections = self._build_sections()
        self._populate_tree()

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.selection_set("sec:quick_start")
        self._show_section("quick_start")

    # ---- content builders ----

    def _build_sections(self) -> dict:
        import getpass
        import platform

        try:
            username = getpass.getuser()
        except Exception:
            username = (os.environ.get("USERNAME")
                        or os.environ.get("USER")
                        or "user")

        platform_str = f"{platform.system()} {platform.release()}"
        py_ver = (f"{sys.version_info.major}.{sys.version_info.minor}"
                  f".{sys.version_info.micro}")

        workspace_p = str(WORKSPACE)
        chat_p      = str(CHAT_FILE)
        config_p    = str(CONFIG_FILE)
        skills_p    = str(SKILLS_DIR)
        root_p      = str(ROOT)

        cmd_lines = []
        for cname, cdef in sorted(self.app.skill_commands.items()):
            cmd_lines.append(f"  /{cname:<14} {cdef.get('description', '')}")
        skill_cmds = "\n".join(cmd_lines) if cmd_lines else "  (none)"

        skill_lines = []
        for s in self.app.skill_meta:
            n = s.get("name", "?")
            d = (s.get("description", "") or "")[:70]
            skill_lines.append(f"  {n:<18} {d}")
        skills_list = "\n".join(skill_lines) if skill_lines else "  (none loaded)"

        servers_str = "\n".join(f"    {s}" for s in self.app.cloud_servers)

        sections = {}

        sections["quick_start"] = ("Quick Start", f"""Type a task in the input box and press Enter.
The agent thinks, calls tools, and returns an answer.

Buttons
  Send       start a new task
  Stop       halt the running agent
  Continue   resume from the last tool result
  Save       save chat locally + cloud (if enabled)
  Settings   edit API key, base URL, model, cloud sync
  Skills     toggle installed skills on/off
  Help       this window

First run
  The agent does NOT auto-install skills. Use skill-manager.py
  to install what you want, then restart the agent.
""")

        sections["commands"] = ("Commands", f"""Built-in (always available):

  /reset                clear conversation memory
  /history              print recent messages
  /skills               list loaded + disabled skills + commands
  /save                 force save chat (local + cloud)
  /open <file>          open a file from the workspace
                          e.g. /open gta.html

Skill commands (loaded from skills):

{skill_cmds}

Type /skills in the chat to see this list live.
""")

        sections["skills"] = ("Skills", f"""Skills are folders under:

  {skills_p}

Each skill is a folder containing skill.py (code) and skill.md (docs).
They add tools the LLM can call and /commands you can type.

Loaded in this session:

{skills_list}

Install new skills:
  1. python skill-manager.py
  2. Sign in, browse, click Install
  3. Restart this agent

Toggle skills on/off with the Skills button. Changes save
immediately to agent_config.json.

To write your own skill, open docs/skills.html in a browser.
Click a skill in the left panel to see its own help page.
""")

        sections["workspace"] = ("Workspace & Sandbox", f"""Everything the agent creates goes here:

  {workspace_p}

Shell rules
  • Commands must be in the allowlist (ls, cat, git, python, curl, …)
  • CWD is forced to the workspace
  • Absolute paths outside it are rejected
  • No pipes, redirection, ;, &, &&

If the agent tries something blocked, you'll see:

  BLOCKED: <reason>

To let it use a new command, add it to ALLOWED_CMDS in agent.py.
""")

        sections["cloud"] = ("Chat Save & Cloud", f"""Local save
  {chat_p}

  Auto-saved after every turn and on window close.
  Loaded on startup if it exists.

Cloud sync (optional)
  Servers tried in order:
{servers_str}

  account: {self.app.cloud_user or "(not signed in)"}

  Enable in Settings → CLOUD SYNC. Uses the same account as
  skill-manager.py. Local file wins if both exist — cloud is
  loaded on startup only if the local file is missing.
""")

        sections["troubleshooting"] = ("Troubleshooting", """browser: FAILED
  Install WebView2 (Windows) or verify Chromium is on PATH.

LLM ERROR: 401
  Wrong API key, or stray quotes around it in agent_config.json.

LLM ERROR: 404
  Model name doesn't match the provider. Check the provider docs.

BLOCKED: <cmd> not allowed
  Add it to ALLOWED_CMDS in agent.py, or use a different approach.

NOT_FOUND: <selector>
  CSS selector didn't match. Call browser_snapshot first.

email: not configured
  Run /email to see setup. Resend / Brevo / Mailjet, all free.

cloud: not synced
  Settings → CLOUD SYNC on. Then click Save.
""")

        sections["about"] = ("System Info", f"""OS           {platform_str}
Python       {py_ver}
User         {username}

Paths
  root       {root_p}
  config     {config_p}
  chat       {chat_p}
  workspace  {workspace_p}
  skills     {skills_p}

LLM
  model      {self.app.model}
  base       {self.app.base_url}
  keys       {len(self.app.api_keys)}

Skills       {len(self.app.skill_names)} loaded, {len(self.app.disabled_skills)} disabled
Cloud sync   {"on" if self.app.cloud_sync else "off"}
Cloud acct   {self.app.cloud_user or "(not signed in)"}
Cloud srv    {self.app.cloud_servers[0]}
""")

        return sections

    # ---- tree ----

    def _populate_tree(self):
        self.tree.insert("", "end", iid="grp:general",
                         text="  GENERAL", open=True, tags=("group",))
        for key, (title, _) in self._sections.items():
            self.tree.insert("grp:general", "end", iid=f"sec:{key}",
                             text=f"  {title}", tags=("item",))

        self.tree.insert("", "end", iid="grp:skills",
                         text="  SKILLS", open=True, tags=("group",))
        if self.app.skill_meta:
            for s in self.app.skill_meta:
                name = s.get("name", "?")
                self.tree.insert("grp:skills", "end",
                                 iid=f"skill:{name}",
                                 text=f"  {name}", tags=("item",))
        else:
            self.tree.insert("grp:skills", "end", iid="skill_none",
                             text="  (none loaded)", tags=("item",))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith("sec:"):
            self._show_section(iid[4:])
        elif iid.startswith("skill:"):
            self._show_skill(iid[6:])

    # ---- content renderer ----

    def _show_section(self, key: str):
        title, body = self._sections.get(key, ("?", "(not found)"))
        header = f"{title}\n{'─' * len(title)}\n\n"
        self._set_content(header + body)

    def _show_skill(self, name: str):
        meta = next((s for s in self.app.skill_meta
                     if s.get("name") == name), {}) or {}
        body = loader_get_help(SKILLS_DIR, name)
        header = (
            f"{name}\n"
            f"{'─' * len(name)}\n"
            f"version: {meta.get('version', '?')}    "
            f"author: {meta.get('author', '?')}\n\n"
        )
        self._set_content(header + body)

    def _set_content(self, text: str):
        self.content.configure(state="normal")
        self.content.delete("1.0", "end")
        self.content.insert("1.0", text)
        self.content.yview_moveto(0)
        self.content.configure(state="disabled")


# ===========================================================================
# App
# ===========================================================================

class App:
    def __init__(self, root, browser):
        self.root = root
        self.browser = browser
        self._log_q = queue.Queue()
        self._log_history = []
        self._log_lock = threading.Lock()

        self._stop_event = threading.Event()
        self._worker = None
        self._stopped_last = False

        cfg = load_agent_config()
        self.api_keys = normalize_keys(cfg.get("openai_api_keys"))
        self.base_url = (cfg.get("openai_base_url")
                         or os.getenv("OPENAI_BASE_URL")
                         or "https://api.openai.com/v1")
        self.model = (cfg.get("openai_model")
                      or os.getenv("OPENAI_MODEL")
                      or "gpt-4o")
        self.disabled_skills = list(cfg.get("disabled_skills") or [])
        self.cloud_sync = bool(cfg.get("cloud_sync", False))

        if not self.api_keys:
            self.api_keys = normalize_keys(
                [k.strip() for k in os.getenv("OPENAI_API_KEYS", "").split(",")])

        self.client = make_client(self.api_keys, self.base_url)

        sm = _sm_cfg()
        self.cloud_servers = _sm_server_list()
        self.cloud_server = self.cloud_servers[0]
        self.cloud_token = sm.get("token")
        self.cloud_user = sm.get("nickname")

        print(f"[config] model={self.model}  base={self.base_url}  keys={len(self.api_keys)}")
        print(f"[config] cloud={self.cloud_sync}  servers={self.cloud_servers}  user={self.cloud_user}")

        apply_theme(root)
        self._build_toolset()
        self.messages = [{"role": "system", "content": self.system_prompt}]

        root.title("AI Agent")
        root.geometry("1020x760")
        root.minsize(780, 520)

        header = ttk.Frame(root, style="Panel.TFrame")
        header.pack(fill="x", side="top")
        ttk.Label(header, text="AI AGENT", style="Header.TLabel").pack(
            side="left", padx=16, pady=10)
        ttk.Button(header, text="Help", command=self._open_help).pack(
            side="right", padx=(6, 16), pady=10)
        ttk.Button(header, text="Skills", command=self._open_skills).pack(
            side="right", padx=(6, 0), pady=10)
        ttk.Button(header, text="Settings", command=self._open_settings).pack(
            side="right", padx=(6, 0), pady=10)
        ttk.Button(header, text="Save", command=self._save_chat_manual).pack(
            side="right", padx=(6, 0), pady=10)
        self.browser_lbl = ttk.Label(header, text="browser: starting…",
                                     style="Status.TLabel")
        self.browser_lbl.pack(side="right", padx=16)
        self.status_lbl = ttk.Label(header, text="", style="Status.TLabel")
        self.status_lbl.pack(side="right", padx=16)
        self._update_header()

        log_wrap = tk.Frame(root, bg=BG)
        log_wrap.pack(fill="both", expand=True, padx=12, pady=(10, 6))
        ff = "Cascadia Mono" if self._has_font("Cascadia Mono") else "Consolas"
        self.log = tk.Text(log_wrap, wrap="word", bg=BG_PANEL, fg=FG,
                           insertbackground=FG, selectbackground="#264f78",
                           relief="flat", borderwidth=0, padx=14, pady=12,
                           font=(ff, 10), spacing1=2, spacing3=4)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

        self.log.tag_configure("user",   foreground=YELLOW, font=(ff, 10, "bold"))
        self.log.tag_configure("agent",  foreground=GREEN,  font=(ff, 10, "bold"))
        self.log.tag_configure("tool",   foreground=ACCENT)
        self.log.tag_configure("result", foreground=PURPLE)
        self.log.tag_configure("error",  foreground=RED)
        self.log.tag_configure("dim",    foreground=FG_DIM)
        self.log.tag_configure("turn",   foreground=FG_DIM, font=(ff, 9, "italic"))

        bottom = ttk.Frame(root, style="Panel.TFrame")
        bottom.pack(fill="x", side="bottom")
        inner = tk.Frame(bottom, bg=BG_PANEL)
        inner.pack(fill="x", padx=12, pady=10)
        self.stop_btn = ttk.Button(inner, text="Stop", style="Stop.TButton",
                                   command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 6))
        self.continue_btn = ttk.Button(inner, text="Continue",
                                       command=self._on_continue, state="disabled")
        self.continue_btn.pack(side="left", padx=(0, 10))
        self.entry = ttk.Entry(inner, font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=2)
        self.entry.bind("<Return>", lambda e: self.on_send())
        self.send_btn = ttk.Button(inner, text="Send", style="Send.TButton",
                                   command=self.on_send)
        self.send_btn.pack(side="right", padx=(10, 0))

        self._load_local_chat()
        self._try_load_cloud_chat()

        self.log_line(f"Model    : {self.model}", "dim")
        self.log_line(f"Base     : {self.base_url}", "dim")
        self.log_line(f"Keys     : {len(self.api_keys)}", "dim")
        self.log_line(f"Workspace: {WORKSPACE}", "dim")
        self.log_line(f"Chat file: {CHAT_FILE}", "dim")
        cloud_status = "on" if (self.cloud_sync and self.cloud_token) else "off"
        self.log_line(f"Cloud    : {cloud_status} ({' → '.join(self.cloud_servers)})", "dim")
        self.log_line(f"Skills   : {', '.join(self.skill_names) or '(none)'}", "dim")
        if self.disabled_skills:
            self.log_line(f"Disabled : {', '.join(self.disabled_skills)}", "dim")
        if self.skill_commands:
            self.log_line("Commands : " + ", ".join(f"/{c}" for c in sorted(self.skill_commands)),
                          "dim")
        self.log_line("Buttons  : Stop · Continue · Send · Save · Settings · Skills · Help", "dim")
        self.log_line("─" * 70, "dim")

        threading.Thread(target=self._browser_selftest, daemon=True).start()
        self._poll_log()
        self.entry.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- header ----

    def _update_header(self):
        enabled = len([s for s in loader_discover(SKILLS_DIR)
                       if s["name"] not in self.disabled_skills])
        cloud = "☁" if (self.cloud_sync and self.cloud_token) else ""
        self.status_lbl.configure(
            text=f"{self.model}  ·  {len(self.api_keys)} key  ·  {enabled} skill  {cloud}")

    # ---- skills ----

    def _build_toolset(self):
        self.all_schemas = list(CORE_SCHEMAS)
        self.all_callables = {
            "browser_navigate": self.browser.navigate,
            "browser_snapshot": self.browser.snapshot,
            "browser_links":    self.browser.links,
            "browser_click":    self.browser.click,
            "browser_type":     self.browser.type_text,
            "browser_scroll":   self.browser.scroll,
            "shell_run":        shell_run,
        }
        skill_schemas, skill_callables, skill_meta, skill_commands = \
            loader_load(SKILLS_DIR, self.disabled_skills)

        self.all_schemas.extend(skill_schemas)
        self.all_callables.update(skill_callables)
        self.skill_names = [m.get("name", "?") for m in skill_meta]
        self.skill_meta = skill_meta
        self.skill_commands = skill_commands

        if skill_meta:
            lines = "\n".join(f"- {m['name']}: {m.get('description', '')}"
                              for m in skill_meta)
            self.system_prompt = CORE_PROMPT + "\nSKILLS (loaded):\n" + lines + "\n"
        else:
            self.system_prompt = CORE_PROMPT

    def _reload_tools(self):
        self._build_toolset()
        if hasattr(self, "messages") and self.messages:
            self.messages[0] = {"role": "system", "content": self.system_prompt}
        if hasattr(self, "status_lbl"):
            self._update_header()
        self.log_line(f"[skills] reloaded — active: {', '.join(self.skill_names) or '(none)'}", "dim")

    def _save_disabled_skills(self):
        cfg = load_agent_config()
        cfg["disabled_skills"] = list(self.disabled_skills)
        cfg.setdefault("openai_api_keys", self.api_keys)
        cfg.setdefault("openai_base_url", self.base_url)
        cfg.setdefault("openai_model", self.model)
        cfg.setdefault("headless", True)
        cfg.setdefault("cloud_sync", self.cloud_sync)
        try:
            save_agent_config(cfg)
        except Exception as e:
            print(f"[config] save failed: {e}")

    # ---- dialogs ----

    def _open_settings(self):
        SettingsDialog(self.root, self)

    def _open_skills(self):
        SkillsDialog(self.root, self)

    def _open_help(self):
        HelpDialog(self.root, self)

    # ---- logging ----

    def _has_font(self, name):
        try:
            return name in tkfont.families()
        except Exception:
            return False

    def _browser_selftest(self):
        result = self.browser.self_test()
        ok = result.startswith("OK")
        self.root.after(0, lambda: self.browser_lbl.configure(
            text="browser: ready" if ok else "browser: FAILED",
            foreground=GREEN if ok else RED))
        self.log_line(f"browser self-test: {result}", "dim" if ok else "error")

    def log_line(self, text, tag=None):
        with self._log_lock:
            self._log_history.append((text, tag))
        self._log_q.put((text, tag))

    def _poll_log(self):
        try:
            while True:
                text, tag = self._log_q.get_nowait()
                self.log.configure(state="normal")
                if tag:
                    self.log.insert("end", text + "\n", tag)
                else:
                    self.log.insert("end", text + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(60, self._poll_log)

    # ---- local chat ----

    def _save_local_chat(self):
        try:
            data = {
                "messages": self.messages,
                "log": self._log_history[-500:],
                "model": self.model,
                "saved_at": time.time(),
            }
            tmp = CHAT_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(CHAT_FILE)
        except Exception as e:
            print(f"[chat] save failed: {e}")

    def _load_local_chat(self):
        if not CHAT_FILE.exists():
            return
        try:
            data = json.loads(CHAT_FILE.read_text(encoding="utf-8"))
            msgs = data.get("messages") or []
            if msgs and msgs[0].get("role") == "system":
                msgs[0] = {"role": "system", "content": self.system_prompt}
            if msgs:
                self.messages = msgs
            for text, tag in (data.get("log") or [])[-200:]:
                with self._log_lock:
                    self._log_history.append((text, tag))
                self._log_q.put((text, tag))
            print(f"[chat] loaded {len(msgs)} messages from {CHAT_FILE}")
        except Exception as e:
            print(f"[chat] load failed: {e}")

    # ---- cloud ----

    def _cloud_headers(self):
        return {
            "Accept": "application/json",
            "User-Agent": SKILL_UA,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_token}",
        }

    def _save_cloud_chat(self):
        if not (self.cloud_sync and self.cloud_token):
            return

        payload = json.dumps({
            "messages": self.messages,
            "log": self._log_history[-500:],
            "model": self.model,
        }, ensure_ascii=False)
        body = json.dumps({"state": payload}).encode("utf-8")

        for server in self.cloud_servers:
            try:
                req = urllib.request.Request(
                    server.rstrip("/") + "/state",
                    data=body, method="POST", headers=self._cloud_headers())
                with urllib.request.urlopen(req, timeout=15) as r:
                    r.read()
                if server != self.cloud_servers[0]:
                    print(f"[cloud] saved via fallback: {server}")
                return
            except Exception as e:
                print(f"[cloud] {server} save failed: {e}")
        print("[cloud] all servers failed on save")

    def _try_load_cloud_chat(self):
        if not (self.cloud_sync and self.cloud_token):
            return
        if CHAT_FILE.exists():
            return

        for server in self.cloud_servers:
            try:
                req = urllib.request.Request(
                    server.rstrip("/") + "/state",
                    method="GET", headers=self._cloud_headers())
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
            except Exception as e:
                print(f"[cloud] {server} load failed: {e}")
                continue

            blob = data.get("state")
            if not blob:
                return
            try:
                state = json.loads(blob)
            except Exception as e:
                print(f"[cloud] bad state blob from {server}: {e}")
                return

            msgs = state.get("messages") or []
            if msgs and msgs[0].get("role") == "system":
                msgs[0] = {"role": "system", "content": self.system_prompt}
            if msgs:
                self.messages = msgs
            for text, tag in (state.get("log") or [])[-200:]:
                with self._log_lock:
                    self._log_history.append((text, tag))
                self._log_q.put((text, tag))
            print(f"[cloud] loaded {len(msgs)} messages from {server}")
            return

    def _save_chat_manual(self):
        self._save_local_chat()
        self._save_cloud_chat()
        cloud = " + cloud" if (self.cloud_sync and self.cloud_token) else ""
        self.log_line(f"[save] chat saved{cloud} → {CHAT_FILE}", "dim")

    # ---- run control ----

    def _set_running(self, running):
        if running:
            self.send_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.continue_btn.configure(state="disabled")
            self.status_lbl.configure(text="running…")
        else:
            self.send_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.continue_btn.configure(
                state="normal" if self._stopped_last else "disabled")
            self._update_header()

    def _on_stop(self):
        self._stop_event.set()
        self.log_line("[stop] requested", "error")
        self.stop_btn.configure(state="disabled")

    def _on_continue(self):
        if self._worker and self._worker.is_alive():
            return
        self.log_line("\n▸ continue", "user")
        self._stopped_last = False
        self._stop_event.clear()
        self._set_running(True)
        self._worker = threading.Thread(target=self._run_agent, args=(None,), daemon=True)
        self._worker.start()

    # ---- input ----

    def on_send(self):
        task = self.entry.get().strip()
        if not task:
            return
        self.entry.delete(0, "end")
        low = task.lower()

        # ---- built-in commands ----
        if low in ("/reset", "/clear"):
            self.messages = [{"role": "system", "content": self.system_prompt}]
            self._log_history = []
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")
            self.log_line("── conversation cleared ──", "dim")
            self._save_local_chat()
            return
        if low == "/history":
            for m in self.messages[1:]:
                role = m.get("role", "?")
                content = (m.get("content") or "")[:140].replace("\n", " ")
                self.log_line(f"  [{role}] {content}", "dim")
            return
        if low == "/skills":
            self.log_line(f"active: {', '.join(self.skill_names) or '(none)'}", "dim")
            for m in self.skill_meta:
                self.log_line(f"  - {m['name']}: {m.get('description', '')[:100]}", "dim")
            if self.disabled_skills:
                self.log_line(f"disabled: {', '.join(self.disabled_skills)}", "dim")
            if self.skill_commands:
                self.log_line("commands:", "dim")
                for cname, cdef in sorted(self.skill_commands.items()):
                    self.log_line(f"  /{cname:<14} {cdef.get('description','')}", "dim")
            return
        if low == "/save":
            self._save_chat_manual()
            return
        if low.startswith("/open "):
            rel = task[6:].strip()
            p = (WORKSPACE / rel).resolve()
            if not str(p).startswith(str(WORKSPACE)) or not p.exists():
                self.log_line(f"ERROR: not in workspace: {rel}", "error")
                return
            try:
                os.startfile(str(p))
                self.log_line(f"opened {p}", "dim")
            except Exception as e:
                self.log_line(f"ERROR: {e}", "error")
            return

        # ---- dispatch to skill commands ----
        if task.startswith("/"):
            parts = task[1:].split()
            cmd_name = parts[0].lower() if parts else ""
            args = parts[1:]
            if cmd_name in self.skill_commands:
                handler = self.skill_commands[cmd_name]["handler"]
                try:
                    handler(args, self.log_line)
                except Exception as e:
                    self.log_line(f"[{cmd_name}] error: {e}", "error")
                return
            self.log_line(f"unknown command: /{cmd_name}", "error")
            return

        # ---- normal task ----
        self.log_line(f"\n▸ {task}", "user")
        self._stopped_last = False
        self._stop_event.clear()
        self._set_running(True)
        self._worker = threading.Thread(target=self._run_agent, args=(task,), daemon=True)
        self._worker.start()

    def _run_agent(self, task):
        self._stopped_last = False
        try:
            self._agent_loop(task)
        finally:
            self._save_local_chat()
            self._save_cloud_chat()
            self.root.after(0, self._set_running, False)

    def _agent_loop(self, task):
        if task is not None:
            self.messages.append({"role": "user", "content": task})
            if len(self.messages) > 42:
                self.messages = [self.messages[0]] + self.messages[-40:]

        for turn in range(1, MAX_TURNS + 1):
            if self._stop_event.is_set():
                self.log_line("[stopped]", "error")
                self._stopped_last = True
                return

            self.log_line(f"[turn {turn}] thinking…", "turn")
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=self.messages,
                    tools=self.all_schemas, tool_choice="auto",
                    temperature=0.2)
            except Exception as e:
                self.log_line(f"LLM ERROR: {e}", "error")
                return

            msg = resp.choices[0].message
            assistant = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]
            self.messages.append(assistant)

            if not msg.tool_calls:
                self.log_line("AGENT ▸ " + (msg.content or "(done)"), "agent")
                return

            for tc in msg.tool_calls:
                if self._stop_event.is_set():
                    self.log_line("[stopped before tool call]", "error")
                    self._stopped_last = True
                    return

                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                preview = ", ".join(f"{k}={v!r}" for k, v in args.items())
                self.log_line(f"→ {name}({preview[:200]})", "tool")

                fn = self.all_callables.get(name)
                try:
                    result = fn(**args) if fn else f"unknown tool: {name}"
                except Exception as e:
                    result = f"ERROR: {e}"

                tag = "error" if str(result).startswith(
                    ("ERROR", "BLOCKED", "NOT_FOUND")) else "result"
                self.log_line(f"← {str(result)[:400].replace(chr(10), ' ⏎ ')}", tag)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)[:4000],
                })
                self._save_local_chat()

        self.log_line("stopped: max turns reached", "error")

    def _on_close(self):
        try:
            self._stop_event.set()
            self._save_local_chat()
            self._save_cloud_chat()
        finally:
            try:
                self.browser.close()
            finally:
                self.root.destroy()


# ===========================================================================
# Entry
# ===========================================================================

def main():
    if not load_agent_config().get("openai_api_keys"):
        print("[config] no API keys — open Settings in the GUI to add one")

    browser = Browser(headless=True)
    root = tk.Tk()
    app = App(root, browser)
    root.mainloop()


if __name__ == "__main__":
    main()