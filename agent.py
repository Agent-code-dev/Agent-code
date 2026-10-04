"""
agent.py — Local AI agent, Claude Code-inspired, polished UI.

Features:
  - File tools: read (line range), edit (string replace), write, glob, grep
  - Shell: sandboxed, allowlist, workspace jail
  - Browser: headless Chromium (DrissionPage)
  - Todo list: persistent task planning
  - Subagent: isolated research
  - Web fetch: URL → readable text
  - Permission modes: readonly | ask | auto
  - Markdown rendering in the log and Help
  - Clear / Copy last / Export chat buttons
  - Stop/Continue, save/resume, cloud sync, skills
"""

import os
import re
import sys
import json
import time
import shlex
import base64
import queue
import shutil
import threading
import itertools
import subprocess
import urllib.error
import urllib.request
import importlib.util
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

from DrissionPage import ChromiumPage, ChromiumOptions
from openai import OpenAI


# ===========================================================================
# Paths
# ===========================================================================

ROOT = Path(__file__).parent.resolve()
WORKSPACE = ROOT / "workspace"
SKILLS_DIR = ROOT / "skills"
CHATS_DIR = ROOT / "chats"
CONFIG_FILE = ROOT / "agent_config.json"
CHAT_FILE = CHATS_DIR / "current.json"
TODO_FILE = ROOT / ".agent_todo.json"

WORKSPACE.mkdir(parents=True, exist_ok=True)
SKILLS_DIR.mkdir(parents=True, exist_ok=True)
CHATS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["AGENT_WORKSPACE"] = str(WORKSPACE)


# ===========================================================================
# Markdown rendering
# ===========================================================================

def configure_md_tags(widget, mono_font="Consolas", size=10):
    widget.tag_configure("md_h1", foreground="#ffffff",
                         font=(mono_font, size + 4, "bold"),
                         spacing1=12, spacing3=6)
    widget.tag_configure("md_h2", foreground="#ffffff",
                         font=(mono_font, size + 2, "bold"),
                         spacing1=8, spacing3=4)
    widget.tag_configure("md_h3", foreground="#58a6ff",
                         font=(mono_font, size + 1, "bold"),
                         spacing1=6, spacing3=3)
    widget.tag_configure("md_bold", foreground="#ffffff",
                         font=(mono_font, size, "bold"))
    widget.tag_configure("md_italic", font=(mono_font, size, "italic"))
    widget.tag_configure("md_code_inline", foreground="#f0f6fc",
                         background="#1c2128", font=(mono_font, size - 1))
    widget.tag_configure("md_code_block", foreground="#f0f6fc",
                         background="#0d1117", font=(mono_font, size - 1),
                         lmargin1=24, lmargin2=24, rmargin=24,
                         spacing1=6, spacing3=6)
    widget.tag_configure("md_link", foreground="#58a6ff", underline=True)
    widget.tag_configure("md_link_url", foreground="#8b949e",
                         font=(mono_font, size - 1))
    widget.tag_configure("md_bullet", foreground="#58a6ff")
    widget.tag_configure("md_hr", foreground="#30363d")
    widget.tag_configure("md_quote", foreground="#8b949e")


_INLINE_PATTERN = re.compile(
    r"(\*\*[^*\n]+?\*\*)"
    r"|(`[^`\n]+?`)"
    r"|(\*[^*\n]+?\*)"
    r"|(\[[^\]\n]+?\]\([^)\n]+?\))"
)


def _render_inline(widget, text, base_tag):
    if not text:
        return
    pos = 0
    for m in _INLINE_PATTERN.finditer(text):
        if m.start() > pos:
            widget.insert("end", text[pos:m.start()], base_tag or ())
        token = m.group(0)
        if token.startswith("**") and token.endswith("**"):
            widget.insert("end", token[2:-2], "md_bold")
        elif token.startswith("`") and token.endswith("`"):
            widget.insert("end", token[1:-1], "md_code_inline")
        elif token.startswith("*") and token.endswith("*"):
            widget.insert("end", token[1:-1], "md_italic")
        elif token.startswith("[") and "](" in token:
            label, _, url = token[1:-1].partition("](")
            url = url.rstrip(")")
            widget.insert("end", label, "md_link")
            widget.insert("end", f" ({url})", "md_link_url")
        pos = m.end()
    if pos < len(text):
        widget.insert("end", text[pos:], base_tag or ())


def render_markdown(widget, text, base_tag=None):
    if not text:
        return
    lines = text.split("\n")
    i = 0
    in_code = False
    code_buf = []

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                widget.insert("end", "\n".join(code_buf), "md_code_block")
                widget.insert("end", "\n")
                code_buf = []
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = min(len(m.group(1)), 3)
            widget.insert("end", m.group(2).strip(), f"md_h{level}")
            widget.insert("end", "\n")
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", stripped):
            widget.insert("end", "─" * 60, "md_hr")
            widget.insert("end", "\n")
            i += 1
            continue

        if stripped.startswith("> "):
            widget.insert("end", "│ ", "md_quote")
            _render_inline(widget, stripped[2:], base_tag)
            widget.insert("end", "\n")
            i += 1
            continue

        m = re.match(r"^(\s*)([-*+])\s+(.*)$", line)
        if m:
            indent = "  " * (len(m.group(1)) // 2)
            widget.insert("end", indent + "• ", "md_bullet")
            _render_inline(widget, m.group(3), base_tag)
            widget.insert("end", "\n")
            i += 1
            continue

        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if m:
            indent = "  " * (len(m.group(1)) // 2)
            widget.insert("end", indent + m.group(2) + ". ", "md_bullet")
            _render_inline(widget, m.group(3), base_tag)
            widget.insert("end", "\n")
            i += 1
            continue

        _render_inline(widget, stripped, base_tag)
        widget.insert("end", "\n")
        i += 1

    if in_code and code_buf:
        widget.insert("end", "\n".join(code_buf), "md_code_block")
        widget.insert("end", "\n")


# ===========================================================================
# Config
# ===========================================================================

SKILL_SERVER_PRIMARY = "https://skills-manager.freesrv.com"
SKILL_SERVER_FALLBACK = "http://78.154.103.43:9074"
SKILL_SERVERS = [SKILL_SERVER_PRIMARY, SKILL_SERVER_FALLBACK]
DEFAULT_SKILL_SERVER = SKILL_SERVER_PRIMARY

SM_CFG_FILE = Path.home() / ".skill-manager.json"
SKILL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36")

MAX_TURNS = 40
SHELL_TIMEOUT = 60
MAX_READ_LINES = 2000
MAX_SUBAGENT_TURNS = 12

PERMISSION_READONLY = "readonly"
PERMISSION_ASK      = "ask"
PERMISSION_AUTO     = "auto"


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
        raw = [k.strip() for k in os.getenv("OPENAI_API_KEYS", "").split(",")
               if k.strip()]
    return [k.strip().strip('"').strip("'") for k in raw if k and k.strip()]


def _sm_cfg() -> dict:
    if SM_CFG_FILE.exists():
        try:
            return json.loads(SM_CFG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _sm_server_list():
    cfg = _sm_cfg()
    servers = []
    custom = cfg.get("server")
    if custom:
        servers.append(custom)
    for s in SKILL_SERVERS:
        if s not in servers:
            servers.append(s)
    return servers


def make_client(api_keys, base_url):
    if not api_keys:
        return None
    if len(api_keys) == 1:
        return OpenAI(api_key=api_keys[0], base_url=base_url)
    cycle = itertools.cycle(api_keys)
    return OpenAI(api_key=lambda: next(cycle), base_url=base_url)


# ===========================================================================
# Todo list
# ===========================================================================

class TodoList:
    def __init__(self, path: Path):
        self.path = path
        self.items = self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []

    def _save(self):
        try:
            self.path.write_text(json.dumps(self.items, indent=2),
                                 encoding="utf-8")
        except Exception:
            pass

    def write(self, items):
        clean = []
        for x in items or []:
            if not isinstance(x, dict):
                continue
            content = str(x.get("content", "")).strip()
            status = str(x.get("status", "pending")).lower()
            if status not in ("pending", "in_progress", "completed"):
                status = "pending"
            if content:
                clean.append({"content": content, "status": status})
        ip = [i for i, x in enumerate(clean) if x["status"] == "in_progress"]
        if len(ip) > 1:
            for i in ip[1:]:
                clean[i]["status"] = "pending"
        self.items = clean
        self._save()
        return self.render()

    def render(self):
        if not self.items:
            return "(todo list is empty)"
        icons = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
        return "\n".join(
            f"{icons.get(x['status'], '[ ]')} {x['content']}"
            for x in self.items
        )


# ===========================================================================
# Project context
# ===========================================================================

def load_project_context() -> str:
    for name in ("AGENT.md", "CLAUDE.md", "AGENTS.md", "README.md"):
        p = ROOT / name
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                return f"# Project context (from {name})\n\n{text[:8000]}"
            except Exception:
                continue
    return ""


# ===========================================================================
# File tools
# ===========================================================================

def _safe_path(path: str, allow_workspace_escape: bool = False) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("empty path")
    p = Path(path)
    if not p.is_absolute():
        p = (WORKSPACE / p)
    rp = p.resolve()
    if allow_workspace_escape:
        if not str(rp).startswith(str(ROOT)):
            raise ValueError(f"path escapes project: {path}")
    else:
        if not str(rp).startswith(str(WORKSPACE)):
            raise ValueError(f"path escapes workspace: {path}")
    return rp


def tool_read_file(path: str, offset: int = 0, limit: int = MAX_READ_LINES) -> str:
    try:
        p = _safe_path(path, allow_workspace_escape=True)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: not found: {path}"
    if p.is_dir():
        return f"ERROR: is a directory: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"

    lines = text.splitlines()
    total = len(lines)
    try:
        offset = max(0, int(offset))
    except Exception:
        offset = 0
    try:
        limit = max(1, min(MAX_READ_LINES, int(limit)))
    except Exception:
        limit = MAX_READ_LINES

    chunk = lines[offset:offset + limit]
    numbered = "\n".join(f"{i + offset + 1:>6}\t{ln}"
                         for i, ln in enumerate(chunk))
    header = f"# {path} (lines {offset + 1}-{offset + len(chunk)} of {total})\n"
    if offset + limit < total:
        header += f"# (truncated — {total - offset - limit} more lines)\n"
    return header + numbered


def tool_write_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"ERROR: {e}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_append_file(path: str, content: str) -> str:
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"ERROR: {e}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"OK appended {len(content)} chars; size now {p.stat().st_size}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_edit_file(path: str, old_string: str, new_string: str,
                   replace_all: bool = False) -> str:
    try:
        p = _safe_path(path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.exists():
        return f"ERROR: not found: {path}"
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR: {e}"

    if old_string == new_string:
        return "ERROR: old_string and new_string are identical"

    count = text.count(old_string)
    if count == 0:
        return (f"ERROR: old_string not found in {path}. "
                "Read the file first and match whitespace exactly.")
    if count > 1 and not replace_all:
        return (f"ERROR: old_string is not unique ({count} matches). "
                "Include more context, or pass replace_all=true.")

    if replace_all:
        new_text = text.replace(old_string, new_string)
        replaced = count
    else:
        new_text = text.replace(old_string, new_string, 1)
        replaced = 1

    try:
        p.write_text(new_text, encoding="utf-8")
        return f"OK replaced {replaced} occurrence(s) in {path}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_glob_files(pattern: str, path: str = ".") -> str:
    try:
        base = _safe_path(path, allow_workspace_escape=True)
    except ValueError as e:
        return f"ERROR: {e}"
    if not base.exists():
        return f"ERROR: not found: {path}"
    matches = []
    try:
        for m in base.rglob(pattern):
            if m.is_file():
                try:
                    rel = m.relative_to(ROOT)
                except ValueError:
                    rel = m
                matches.append(str(rel))
                if len(matches) >= 500:
                    break
    except Exception as e:
        return f"ERROR: {e}"
    if not matches:
        return f"(no files matched {pattern!r} under {path})"
    matches.sort()
    return f"{len(matches)} match(es):\n" + "\n".join(matches)


def tool_grep_files(pattern: str, path: str = ".", glob: str = "",
                    case_insensitive: bool = False,
                    max_results: int = 100) -> str:
    try:
        base = _safe_path(path, allow_workspace_escape=True)
    except ValueError as e:
        return f"ERROR: {e}"
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return f"ERROR: bad regex: {e}"

    hits = []
    try:
        files = base.rglob(glob) if glob else base.rglob("*")
        for f in files:
            if not f.is_file():
                continue
            if f.suffix.lower() in (".pyc", ".png", ".jpg", ".jpeg",
                                     ".gif", ".zip", ".exe", ".dll", ".so",
                                     ".pdf", ".woff", ".woff2"):
                continue
            try:
                for i, line in enumerate(
                        f.read_text(encoding="utf-8", errors="replace")
                        .splitlines(), 1):
                    if rx.search(line):
                        try:
                            rel = f.relative_to(ROOT)
                        except ValueError:
                            rel = f
                        hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                        if len(hits) >= max_results:
                            raise StopIteration
            except StopIteration:
                break
            except Exception:
                continue
    except Exception as e:
        return f"ERROR: {e}"
    if not hits:
        return f"(no matches for {pattern!r})"
    return f"{len(hits)} match(es):\n" + "\n".join(hits)


# ===========================================================================
# Shell
# ===========================================================================

ALLOWED_CMDS = {
    "ls", "pwd", "cd", "cat", "head", "tail", "grep", "find", "wc", "echo",
    "date", "whoami", "git", "python", "python3", "pip", "pip3", "node", "npm",
    "curl", "wget", "sed", "awk", "sort", "uniq", "diff", "tree", "dir",
    "type", "where", "mkdir", "copy", "move", "touch",
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


def tool_shell_run(command: str, cwd: str = ".") -> str:
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return f"BLOCKED: pattern {pat}"
    if re.search(r"[|&;<>`$]", command):
        return ("BLOCKED: shell metacharacters not allowed.")
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
        run_cwd = _safe_path(cwd) if cwd else WORKSPACE
    except ValueError as e:
        return f"BLOCKED: cwd: {e}"
    try:
        r = subprocess.run(
            parts, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=SHELL_TIMEOUT, cwd=str(run_cwd), shell=False)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return out[:8000] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout {SHELL_TIMEOUT}s"
    except FileNotFoundError:
        return f"ERROR: command not found: {base}"
    except Exception as e:
        return f"ERROR: {e}"


# ===========================================================================
# Web fetch
# ===========================================================================

def tool_web_fetch(url: str, max_chars: int = 6000) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": SKILL_UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"
    text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars] or "(empty)"


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
                .set_user_data_path(str(Path(os.environ.get("TEMP", "/tmp"))
                                        / "agent-profile")))
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
# Skills
# ===========================================================================

def load_skills(disabled: list):
    schemas, callables, metadata, commands = [], {}, [], {}
    if not SKILLS_DIR.exists():
        return schemas, callables, metadata, commands
    disabled = set(disabled or [])
    for skill_file in sorted(SKILLS_DIR.glob("*/skill.py")):
        name = skill_file.parent.name
        if name in disabled:
            print(f"[loader] skipped (disabled): {name}")
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{name}",
                                                          skill_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            schemas.extend(getattr(mod, "TOOL_SCHEMAS", []) or [])
            callables.update(getattr(mod, "TOOL_CALLABLES", {}) or {})
            cmds = getattr(mod, "COMMANDS", {}) or {}
            for cname, cdef in cmds.items():
                if isinstance(cdef, dict) and "handler" in cdef:
                    commands[cname] = cdef
            meta = getattr(mod, "SKILL", {"name": name})
            metadata.append(meta)
            print(f"[loader] loaded skill: {meta.get('name', name)}")
        except Exception as e:
            print(f"[loader] FAILED to load skill '{name}': {e}")
    return schemas, callables, metadata, commands


def discover_skills():
    out = []
    if not SKILLS_DIR.exists():
        return out
    for folder in sorted(SKILLS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if not (folder / "skill.py").exists():
            continue
        meta = {"name": folder.name, "description": "",
                "version": "?", "author": "?"}
        md = folder / "skill.md"
        if md.exists():
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
                m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if m:
                    for line in m.group(1).splitlines():
                        if ":" in line:
                            k, _, v = line.partition(":")
                            k = k.strip().lower()
                            v = v.strip().strip('"').strip("'")
                            if k in ("name", "description", "version", "author"):
                                meta[k] = v
            except Exception:
                pass
        out.append(meta)
    return out


# ===========================================================================
# Tool schemas
# ===========================================================================

CORE_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file with line numbers.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "offset": {"type": "integer"},
                                      "limit": {"type": "integer"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a file in the workspace.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "append_file",
        "description": "Append text to a file.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "Replace an exact unique string in a file.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "old_string": {"type": "string"},
                                      "new_string": {"type": "string"},
                                      "replace_all": {"type": "boolean"}},
                       "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {
        "name": "glob_files",
        "description": "Find files by glob pattern.",
        "parameters": {"type": "object",
                       "properties": {"pattern": {"type": "string"},
                                      "path": {"type": "string"}},
                       "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "grep_files",
        "description": "Search file contents with a regex.",
        "parameters": {"type": "object",
                       "properties": {"pattern": {"type": "string"},
                                      "path": {"type": "string"},
                                      "glob": {"type": "string"},
                                      "case_insensitive": {"type": "boolean"}},
                       "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "shell_run",
        "description": "Run an allowlisted shell command in the workspace.",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string"},
                                      "cwd": {"type": "string"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "browser_navigate",
        "description": "Open a URL in the headless browser.",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "browser_snapshot",
        "description": "Return visible text of the current page.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "browser_links",
        "description": "List clickable links.",
        "parameters": {"type": "object",
                       "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "browser_click",
        "description": "Click an element by CSS selector.",
        "parameters": {"type": "object",
                       "properties": {"selector": {"type": "string"}},
                       "required": ["selector"]}}},
    {"type": "function", "function": {
        "name": "browser_type",
        "description": "Type text into an input by CSS selector.",
        "parameters": {"type": "object",
                       "properties": {"selector": {"type": "string"},
                                      "text": {"type": "string"}},
                       "required": ["selector", "text"]}}},
    {"type": "function", "function": {
        "name": "browser_scroll",
        "description": "Scroll the page down by N pixels.",
        "parameters": {"type": "object",
                       "properties": {"pixels": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "Fetch a URL and return its readable text.",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"},
                                      "max_chars": {"type": "integer"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "todo_write",
        "description": "Replace the task list. status: pending|in_progress|completed.",
        "parameters": {"type": "object",
                       "properties": {"todos": {"type": "array",
                                                "items": {"type": "object"}}},
                       "required": ["todos"]}}},
    {"type": "function", "function": {
        "name": "todo_read",
        "description": "Return the current task list.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "task",
        "description": "Spawn an isolated subagent for one focused job.",
        "parameters": {"type": "object",
                       "properties": {"description": {"type": "string"},
                                      "prompt": {"type": "string"}},
                       "required": ["description", "prompt"]}}},
]


CORE_PROMPT = f"""You are a coding and research agent running on the user's machine.

Working directory: {ROOT}
Sandbox: {WORKSPACE}

# Tools
File: read_file, write_file, append_file, edit_file, glob_files, grep_files
Shell: shell_run (allowlisted, workspace-jailed)
Browser: browser_navigate, browser_snapshot, browser_links, browser_click,
         browser_type, browser_scroll
Web: web_fetch
Plan: todo_write, todo_read
Task: task (isolated subagent)

# How to work
1. PLAN when the task has 3+ steps: call todo_write.
2. READ before you EDIT.
3. PREFER edit_file over write_file.
4. VERIFY after edits.
5. Use SUBAGENTS for open-ended exploration.
6. Parallelize independent tool calls.
7. STOP and ask on login / CAPTCHA / ambiguity.

# Style
- Be concise.
- Your final answer is rendered as markdown. Use headers, bold, lists,
  fenced code blocks where they help.
- When finished, say what changed, where, and how to verify.

# Rules
- Never say "I'm working on it" as a final answer.
- If a tool returns BLOCKED or ERROR, adapt — don't repeat the call.
- Files outside the workspace are read-only.
"""


# ===========================================================================
# Theme — polished palette
# ===========================================================================

BG          = "#0a0d13"
BG_PANEL    = "#10141b"
BG_CARD     = "#161b22"
BG_INPUT    = "#0d1117"
BG_HOVER    = "#1f2630"
BG_TOOLBAR  = "#0d1117"
FG          = "#c9d1d9"
FG_BRIGHT   = "#f0f6fc"
FG_DIM      = "#8b949e"
FG_FAINT    = "#6e7681"
ACCENT      = "#58a6ff"
ACCENT_DARK = "#388bfd"
GREEN       = "#3fb950"
YELLOW      = "#d29922"
RED         = "#f85149"
PURPLE      = "#bc8cff"
BORDER      = "#21262d"
BORDER_SOFT = "#30363d"


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
    style.configure("Toolbar.TFrame", background=BG_TOOLBAR)

    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG)
    style.configure("Card.TLabel", background=BG_CARD, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
    style.configure("PanelDim.TLabel", background=BG_PANEL, foreground=FG_DIM)
    style.configure("Faint.TLabel", background=BG_PANEL, foreground=FG_FAINT)

    style.configure("Header.TLabel", background=BG_PANEL,
                    foreground=ACCENT, font=("Segoe UI", 13, "bold"))
    style.configure("Status.TLabel", background=BG_PANEL,
                    foreground=FG_DIM, font=("Segoe UI", 9))
    style.configure("StatusHi.TLabel", background=BG_PANEL,
                    foreground=FG_BRIGHT, font=("Segoe UI", 9, "bold"))

    style.configure("TEntry",
                    fieldbackground=BG_INPUT, foreground=FG_BRIGHT,
                    insertcolor=ACCENT, bordercolor=BORDER_SOFT,
                    lightcolor=BORDER_SOFT, darkcolor=BORDER_SOFT,
                    padding=10, relief="flat")

    style.configure("TButton",
                    background=BG_CARD, foreground=FG,
                    borderwidth=1, focusthickness=0, padding=(12, 6),
                    font=("Segoe UI", 9))
    style.map("TButton",
              background=[("active", BG_HOVER), ("disabled", BG_CARD)],
              foreground=[("disabled", FG_FAINT)],
              bordercolor=[("active", BORDER_SOFT)])

    style.configure("Send.TButton",
                    background=ACCENT, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(18, 9),
                    font=("Segoe UI", 10, "bold"))
    style.map("Send.TButton",
              background=[("active", "#79b8ff"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_FAINT)])

    style.configure("Stop.TButton",
                    background="#7d1d1d", foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(18, 9),
                    font=("Segoe UI", 10, "bold"))
    style.map("Stop.TButton",
              background=[("active", "#b02121"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_FAINT)])

    style.configure("Accent.TButton",
                    background=ACCENT, foreground="#ffffff",
                    borderwidth=0, focusthickness=0, padding=(14, 6),
                    font=("Segoe UI", 9, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#79b8ff"), ("disabled", "#30363d")],
              foreground=[("disabled", FG_FAINT)])

    style.configure("Icon.TButton",
                    background=BG_CARD, foreground=FG_DIM,
                    borderwidth=1, focusthickness=0, padding=(10, 5),
                    font=("Segoe UI", 9))
    style.map("Icon.TButton",
              background=[("active", BG_HOVER)],
              foreground=[("active", FG_BRIGHT)])

    style.configure("Vertical.TScrollbar",
                    background=BG_PANEL, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG_FAINT,
                    lightcolor=BG_PANEL, darkcolor=BG_PANEL)


# ===========================================================================
# Settings / Skills / Help dialogs (compact versions of the previous ones)
# ===========================================================================

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Settings")
        self.configure(bg=BG)
        self.geometry("560x660")
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

        ttk.Label(body, text="API keys (one per line)",
                  style="Panel.TLabel").pack(anchor="w")
        kf = tk.Frame(body, bg=BG_PANEL)
        kf.pack(fill="x", pady=(2, 10))
        self.keys_text = tk.Text(kf, height=3, bg=BG_INPUT, fg=FG_BRIGHT,
                                 insertbackground=FG, relief="flat",
                                 padx=8, pady=6, font=("Consolas", 10),
                                 wrap="none")
        self.keys_text.pack(side="left", fill="x", expand=True)
        ks = ttk.Scrollbar(kf, orient="vertical", command=self.keys_text.yview)
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
        self.model_entry.pack(fill="x", pady=(2, 14))

        ttk.Label(body, text="Permission mode",
                  style="Panel.TLabel").pack(anchor="w")
        self.perm_var = tk.StringVar(value=app.permission)
        pf = tk.Frame(body, bg=BG_PANEL)
        pf.pack(fill="x", pady=(2, 14))
        for val, label in [
            ("readonly", "Read-only — deny edits and writes"),
            ("ask", "Ask — prompt before edits and shell"),
            ("auto", "Auto — approve inside workspace"),
        ]:
            ttk.Radiobutton(pf, text=label, value=val,
                            variable=self.perm_var).pack(anchor="w")

        self.cloud_var = tk.BooleanVar(value=app.cloud_sync)
        ttk.Checkbutton(body, text="Sync chat to registry server",
                        variable=self.cloud_var).pack(anchor="w", pady=(0, 4))
        ttk.Label(body, text=f"account: {app.cloud_user or '(not signed in)'}",
                  style="PanelDim.TLabel").pack(anchor="w")

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=24, pady=(14, 20))
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="right", padx=(0, 8))

    def _save(self):
        keys = [l.strip() for l in
                self.keys_text.get("1.0", "end").splitlines() if l.strip()]
        base = self.base_entry.get().strip() or "https://api.openai.com/v1"
        model = self.model_entry.get().strip() or "gpt-4o"
        cloud = bool(self.cloud_var.get())
        perm = self.perm_var.get()
        if not keys:
            messagebox.showerror("Settings", "At least one API key required",
                                 parent=self)
            return
        cfg = load_agent_config()
        cfg.update({
            "openai_api_keys": keys,
            "openai_base_url": base,
            "openai_model": model,
            "cloud_sync": cloud,
            "permission_mode": perm,
        })
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
        self.app.permission = perm
        self.app.client = make_client(keys, base)
        self.app._update_header()
        self.destroy()
        self.app.log_line(
            f"[settings] saved — model={model}  perm={perm}  cloud={cloud}",
            "dim")


class SkillsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Skills")
        self.configure(bg=BG)
        self.geometry("640x520")
        self.transient(parent)
        self.grab_set()
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text="SKILLS", style="Header.TLabel").pack(
            anchor="w", padx=24, pady=(20, 4))
        ttk.Label(pad, text="Toggle skills on or off. Changes save immediately.",
                  style="PanelDim.TLabel").pack(anchor="w", padx=24, pady=(0, 14))

        lf = tk.Frame(pad, bg=BG_PANEL)
        lf.pack(fill="both", expand=True, padx=24)
        self.listbox = tk.Listbox(lf, bg=BG_CARD, fg=FG,
                                  selectbackground=ACCENT,
                                  selectforeground="#ffffff",
                                  relief="flat", font=("Consolas", 10),
                                  activestyle="none", borderwidth=0,
                                  highlightthickness=0, height=10)
        self.listbox.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(lf, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-1>", lambda e: self._toggle_selected())

        df = tk.Frame(pad, bg=BG_PANEL)
        df.pack(fill="x", padx=24, pady=(12, 6))
        ttk.Label(df, text="Description",
                  style="PanelDim.TLabel").pack(anchor="w")
        self.desc = tk.Text(df, height=4, bg=BG_CARD, fg=FG,
                            relief="flat", padx=8, pady=6,
                            font=("Segoe UI", 9), wrap="word")
        self.desc.pack(fill="x")
        self.desc.configure(state="disabled")

        row = tk.Frame(pad, bg=BG_PANEL)
        row.pack(fill="x", padx=24, pady=(12, 6))
        ttk.Button(row, text="Toggle", style="Accent.TButton",
                   command=self._toggle_selected).pack(side="left")
        ttk.Button(row, text="Enable all",
                   command=self._enable_all).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Disable all",
                   command=self._disable_all).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Close",
                   command=self.destroy).pack(side="right")

        self.status = ttk.Label(pad, text="", style="PanelDim.TLabel")
        self.status.pack(anchor="w", padx=24, pady=(0, 20))
        self.skills = []
        self._refresh()

    def _refresh(self):
        self.listbox.delete(0, "end")
        self.skills = discover_skills()
        for s in self.skills:
            name = s["name"]
            enabled = name not in self.app.disabled_skills
            mark = "[✓]" if enabled else "[ ]"
            self.listbox.insert(
                "end", f"  {mark}  {name:<24}  v{s.get('version','?')}")
            if not enabled:
                self.listbox.itemconfig("end", foreground=FG_DIM)
        self.status.configure(
            text=f"{len(self.skills)} skill(s) · "
                 f"{len(self.app.disabled_skills)} disabled")

    def _selected_name(self):
        sel = self.listbox.curselection()
        return self.skills[sel[0]]["name"] if sel else None

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


class HelpDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Help")
        self.configure(bg=BG)
        self.geometry("860x700")
        self.transient(parent)
        apply_theme(self)

        pad = ttk.Frame(self, style="Panel.TFrame")
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text="HELP", style="Header.TLabel").pack(
            anchor="w", padx=20, pady=(16, 6))

        body = tk.Frame(pad, bg=BG_PANEL)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        left = tk.Frame(body, bg=BG_CARD, width=200,
                        highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        self.sections = [
            ("Quick start", self._sec_quick),
            ("Commands", self._sec_commands),
            ("Tools", self._sec_tools),
            ("Permissions", self._sec_perms),
            ("Markdown", self._sec_markdown),
            ("Skills", self._sec_skills),
            ("Chat / cloud", self._sec_cloud),
            ("Troubleshooting", self._sec_trouble),
            ("System info", self._sec_system),
        ]
        self.listbox = tk.Listbox(left, bg=BG_CARD, fg=FG,
                                  selectbackground=ACCENT,
                                  selectforeground="#ffffff",
                                  relief="flat", font=("Segoe UI", 10),
                                  activestyle="none", borderwidth=0,
                                  highlightthickness=0)
        self.listbox.pack(fill="both", expand=True, padx=6, pady=6)
        for title, _ in self.sections:
            self.listbox.insert("end", title)
        self.listbox.bind("<<ListboxSelect>>", self._on_section)

        right = tk.Frame(body, bg=BG_CARD,
                         highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ff = "Cascadia Mono" if self._has_font("Cascadia Mono") else "Consolas"
        self.content = tk.Text(right, wrap="word", bg=BG_CARD, fg=FG,
                               relief="flat", padx=16, pady=14,
                               font=(ff, 10), borderwidth=0,
                               spacing1=2, spacing3=5)
        self.content.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(right, orient="vertical", command=self.content.yview)
        sb.pack(side="right", fill="y")
        self.content.configure(yscrollcommand=sb.set, state="disabled")
        configure_md_tags(self.content, mono_font=ff, size=10)

        ttk.Button(pad, text="Close", style="Accent.TButton",
                   command=self.destroy).pack(pady=(0, 12))
        self.listbox.selection_set(0)
        self._on_section(None)

    def _has_font(self, name):
        try:
            return name in tkfont.families()
        except Exception:
            return False

    def _on_section(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.sections):
            title, fn = self.sections[idx]
            self._show(f"# {title}\n\n" + fn())

    def _show(self, md_text):
        self.content.configure(state="normal")
        self.content.delete("1.0", "end")
        render_markdown(self.content, md_text)
        self.content.yview_moveto(0)
        self.content.configure(state="disabled")

    def _sec_quick(self):
        return (
            "Type a task, press **Enter**. The agent thinks, calls tools, "
            "and answers.\n\n"
            "**Buttons**\n\n"
            "- **Send** — start a task\n"
            "- **Stop** — halt mid-turn\n"
            "- **Continue** — resume from the last tool result\n"
            "- **Clear** — wipe the log and conversation\n"
            "- **Copy** — copy the last agent answer\n"
            "- **Export** — save the whole chat to a markdown file\n"
            "- **Todo** — show the task list\n"
            "- **Save** — local + cloud save\n"
            "- **Settings / Skills / Help** — the dialogs\n"
        )

    def _sec_commands(self):
        return (
            "| Command | Action |\n|---|---|\n"
            "| `/reset` | Clear conversation memory |\n"
            "| `/history` | Print recent messages |\n"
            "| `/skills` | List loaded skills and commands |\n"
            "| `/todo` | Show the task list |\n"
            "| `/todo clear` | Empty the task list |\n"
            "| `/save` | Force a chat save |\n"
            "| `/permission` | Show the permission mode |\n"
            "| `/open <file>` | Open a workspace file |\n"
        )

    def _sec_tools(self):
        return (
            "**Files** — `read_file`, `write_file`, `append_file`, "
            "`edit_file`, `glob_files`, `grep_files`\n\n"
            "**System** — `shell_run`, `web_fetch`, `browser_*`\n\n"
            "**Planning** — `todo_write`, `todo_read`, `task`"
        )

    def _sec_perms(self):
        return (f"Current: **{self.app.permission}**\n\n"
                "- **readonly** — writes and shell denied\n"
                "- **ask** — dialog before each write or shell\n"
                "- **auto** — free inside the workspace\n")

    def _sec_markdown(self):
        return (
            "Answers render as markdown:\n\n"
            "- **bold**, *italic*, `inline code`\n"
            "- headers, bullets, numbered lists\n"
            "- fenced code blocks\n"
            "- blockquotes, links, horizontal rules\n"
        )

    def _sec_skills(self):
        lines = ["Skills directory:", "",
                 "```text", str(SKILLS_DIR), "```", ""]
        if self.app.skill_meta:
            lines.append("**Loaded**")
            lines.append("")
            for m in self.app.skill_meta:
                lines.append(f"- **{m['name']}** — "
                             f"{m.get('description','')[:120]}")
        else:
            lines.append("(none loaded)")
        return "\n".join(lines)

    def _sec_cloud(self):
        return (f"**Local**\n\n```text\n{CHAT_FILE}\n```\n\n"
                "**Cloud**\n\n" +
                "\n".join(f"- {s}" for s in self.app.cloud_servers) +
                f"\n\naccount: `{self.app.cloud_user or 'not signed in'}`")

    def _sec_trouble(self):
        return ("| Symptom | Fix |\n|---|---|\n"
                "| browser: FAILED | install WebView2 / Chromium |\n"
                "| LLM ERROR: 401 | wrong key or stray quotes |\n"
                "| LLM ERROR: 404 | model not on provider |\n"
                "| BLOCKED: ... | sandbox rejected the command |\n"
                "| NOT_FOUND: ... | CSS selector mismatch |\n"
                "| edit not unique | add context or replace_all=true |")

    def _sec_system(self):
        import getpass
        import platform
        try:
            user = getpass.getuser()
        except Exception:
            user = os.environ.get("USERNAME") or os.environ.get("USER") or "?"
        py = f"{sys.version_info.major}.{sys.version_info.minor}." \
             f"{sys.version_info.micro}"
        return (f"**Environment**\n\n"
                f"- OS: {platform.system()} {platform.release()}\n"
                f"- Python: {py}\n"
                f"- User: {user}\n\n"
                f"**LLM**\n\n"
                f"- model: `{self.app.model}`\n"
                f"- base: `{self.app.base_url}`\n"
                f"- keys: {len(self.app.api_keys)}")


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
        self._last_agent_answer = ""

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
        self.permission = cfg.get("permission_mode", PERMISSION_ASK)
        if self.permission not in (PERMISSION_READONLY,
                                   PERMISSION_ASK,
                                   PERMISSION_AUTO):
            self.permission = PERMISSION_ASK

        if not self.api_keys:
            self.api_keys = normalize_keys(
                [k.strip() for k in
                 os.getenv("OPENAI_API_KEYS", "").split(",")])

        self.client = make_client(self.api_keys, self.base_url)

        sm = _sm_cfg()
        self.cloud_servers = _sm_server_list()
        self.cloud_server = self.cloud_servers[0]
        self.cloud_token = sm.get("token")
        self.cloud_user = sm.get("nickname")

        self.todo = TodoList(TODO_FILE)
        self.project_context = load_project_context()

        apply_theme(root)
        self._build_toolset()
        self.messages = [{"role": "system", "content": self.system_prompt}]

        root.title("AI Agent")
        root.geometry("1180x820")
        root.minsize(900, 580)

        # ---------- Header ----------
        header = tk.Frame(root, bg=BG_PANEL, height=56)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # left: brand
        brand = tk.Frame(header, bg=BG_PANEL)
        brand.pack(side="left", padx=18, pady=10)
        tk.Label(brand, text="●", bg=BG_PANEL, fg=ACCENT,
                 font=("Segoe UI", 12)).pack(side="left", padx=(0, 8))
        ttk.Label(brand, text="AI AGENT", style="Header.TLabel").pack(side="left")

        # right: status + actions
        actions = tk.Frame(header, bg=BG_PANEL)
        actions.pack(side="right", padx=14, pady=10)

        self.status_lbl = ttk.Label(actions, text="", style="Status.TLabel")
        self.status_lbl.pack(side="right", padx=(14, 0))
        self.browser_lbl = ttk.Label(actions, text="browser: …",
                                     style="Status.TLabel")
        self.browser_lbl.pack(side="right", padx=(14, 0))

        # action buttons row (grouped)
        ttk.Button(actions, text="Help", style="Icon.TButton",
                   command=self._open_help).pack(side="left", padx=2)
        ttk.Button(actions, text="Skills", style="Icon.TButton",
                   command=self._open_skills).pack(side="left", padx=2)
        ttk.Button(actions, text="Settings", style="Icon.TButton",
                   command=self._open_settings).pack(side="left", padx=2)

        # separator
        tk.Frame(actions, bg=BORDER, width=1).pack(side="left",
                                                   fill="y", padx=8, pady=6)

        ttk.Button(actions, text="Todo", style="Icon.TButton",
                   command=self._show_todo).pack(side="left", padx=2)
        ttk.Button(actions, text="Export", style="Icon.TButton",
                   command=self._export_chat).pack(side="left", padx=2)
        ttk.Button(actions, text="Copy last", style="Icon.TButton",
                   command=self._copy_last).pack(side="left", padx=2)
        ttk.Button(actions, text="Save", style="Icon.TButton",
                   command=self._save_chat_manual).pack(side="left", padx=2)

        # ---------- Log panel ----------
        log_outer = tk.Frame(root, bg=BG)
        log_outer.pack(fill="both", expand=True, padx=14, pady=(12, 8))

        log_frame = tk.Frame(log_outer, bg=BG_PANEL,
                             highlightbackground=BORDER,
                             highlightthickness=1)
        log_frame.pack(fill="both", expand=True)

        ff = "Cascadia Mono" if self._has_font("Cascadia Mono") else "Consolas"
        self.log = tk.Text(log_frame, wrap="word", bg=BG_PANEL, fg=FG,
                           insertbackground=ACCENT,
                           selectbackground="#1f3a5f",
                           relief="flat", borderwidth=0,
                           padx=18, pady=14,
                           font=(ff, 10), spacing1=2, spacing3=4)
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_frame, orient="vertical",
                           command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set, state="disabled")

        # log tags
        self.log.tag_configure("user",   foreground=YELLOW,
                               font=(ff, 10, "bold"))
        self.log.tag_configure("agent",  foreground=GREEN,
                               font=(ff, 10, "bold"))
        self.log.tag_configure("tool",   foreground=ACCENT)
        self.log.tag_configure("result", foreground=PURPLE)
        self.log.tag_configure("error",  foreground=RED)
        self.log.tag_configure("dim",    foreground=FG_DIM)
        self.log.tag_configure("turn",   foreground=FG_FAINT,
                               font=(ff, 9, "italic"))
        self.log.tag_configure("think",  foreground=FG_DIM,
                               font=(ff, 9, "italic"))
        configure_md_tags(self.log, mono_font=ff, size=10)

        # ---------- Input bar ----------
        bottom = tk.Frame(root, bg=BG_PANEL, height=64)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        inner = tk.Frame(bottom, bg=BG_PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        # left group: Stop / Continue / Clear
        self.stop_btn = ttk.Button(inner, text="Stop",
                                   style="Stop.TButton",
                                   command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 6))

        self.continue_btn = ttk.Button(inner, text="Continue",
                                       style="Icon.TButton",
                                       command=self._on_continue,
                                       state="disabled")
        self.continue_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = ttk.Button(inner, text="Clear",
                                    style="Icon.TButton",
                                    command=self._on_clear)
        self.clear_btn.pack(side="left", padx=(0, 10))

        # entry + send
        self.entry = ttk.Entry(inner, font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.entry.bind("<Return>", lambda e: self.on_send())

        self.send_btn = ttk.Button(inner, text="Send  ➤",
                                   style="Send.TButton",
                                   command=self.on_send)
        self.send_btn.pack(side="right", padx=(10, 0))

        # ---------- Boot log ----------
        self._load_local_chat()
        self._try_load_cloud_chat()

        self.log_line(f"Model    : {self.model}", "dim")
        self.log_line(f"Base     : {self.base_url}", "dim")
        self.log_line(f"Keys     : {len(self.api_keys)}", "dim")
        self.log_line(f"Root     : {ROOT}", "dim")
        self.log_line(f"Workspace: {WORKSPACE}", "dim")
        self.log_line(f"Permission: {self.permission}", "dim")
        if self.project_context:
            self.log_line("[context] loaded AGENT.md / README.md", "dim")
        cloud_status = "on" if (self.cloud_sync and self.cloud_token) else "off"
        self.log_line(f"Cloud    : {cloud_status} "
                      f"({' → '.join(self.cloud_servers)})", "dim")
        self.log_line(f"Skills   : {', '.join(self.skill_names) or '(none)'}",
                      "dim")
        if self.disabled_skills:
            self.log_line(f"Disabled : {', '.join(self.disabled_skills)}",
                          "dim")
        if self.skill_commands:
            self.log_line("Commands : " +
                          ", ".join(f"/{c}"
                                    for c in sorted(self.skill_commands)),
                          "dim")
        self.log_line("─" * 78, "dim")

        threading.Thread(target=self._browser_selftest, daemon=True).start()
        self._poll_log()
        self.entry.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- header ----

    def _update_header(self):
        enabled = len([s for s in discover_skills()
                       if s["name"] not in self.disabled_skills])
        cloud = "☁" if (self.cloud_sync and self.cloud_token) else ""
        self.status_lbl.configure(
            text=f"{self.model}   ·   {self.permission}   ·   "
                 f"{enabled} skill   {cloud}")

    # ---- toolset ----

    def _build_toolset(self):
        self.all_schemas = list(CORE_SCHEMAS)
        self.all_callables = {
            "read_file":     tool_read_file,
            "write_file":    self._guarded(tool_write_file),
            "append_file":   self._guarded(tool_append_file),
            "edit_file":     self._guarded_edit,
            "glob_files":    tool_glob_files,
            "grep_files":    tool_grep_files,
            "shell_run":     self._guarded_shell,
            "browser_navigate": self.browser.navigate,
            "browser_snapshot": self.browser.snapshot,
            "browser_links":    self.browser.links,
            "browser_click":    self.browser.click,
            "browser_type":     self.browser.type_text,
            "browser_scroll":   self.browser.scroll,
            "web_fetch":        tool_web_fetch,
            "todo_write":       self.todo.write,
            "todo_read":        self.todo.render,
            "task":             self._run_subagent,
        }

        skill_schemas, skill_callables, skill_meta, skill_commands = \
            load_skills(self.disabled_skills)
        self.all_schemas.extend(skill_schemas)
        self.all_callables.update(skill_callables)
        self.skill_names = [m.get("name", "?") for m in skill_meta]
        self.skill_meta = skill_meta
        self.skill_commands = skill_commands

        prompt = CORE_PROMPT
        if self.project_context:
            prompt += "\n\n" + self.project_context
        if skill_meta:
            lines = "\n".join(f"- {m['name']}: {m.get('description', '')}"
                              for m in skill_meta)
            prompt += "\n\n# Loaded skills\n" + lines
        self.system_prompt = prompt

    def _reload_tools(self):
        self._build_toolset()
        if getattr(self, "messages", None):
            self.messages[0] = {"role": "system",
                                "content": self.system_prompt}
        if hasattr(self, "status_lbl"):
            self._update_header()
        self.log_line(f"[skills] reloaded — active: "
                      f"{', '.join(self.skill_names) or '(none)'}", "dim")

    # ---- permissions ----

    def _ask_permission(self, what: str, detail: str) -> bool:
        if self.permission == PERMISSION_AUTO:
            return True
        if self.permission == PERMISSION_READONLY:
            return False
        result = {"ok": False}
        ev = threading.Event()

        def show():
            try:
                result["ok"] = messagebox.askyesno(
                    "Permission required",
                    f"{what}\n\n{detail[:600]}\n\nAllow this action?",
                    parent=self.root)
            finally:
                ev.set()

        self.root.after(0, show)
        ev.wait(timeout=300)
        return result["ok"]

    def _guarded(self, fn):
        def wrapper(*a, **kw):
            if self.permission == PERMISSION_READONLY:
                return "DENIED: read-only mode is on"
            path = a[0] if a else "?"
            if not self._ask_permission(
                    f"File write: {path}",
                    f"Tool: {fn.__name__}\nPath: {path}"):
                return "DENIED by user"
            return fn(*a, **kw)
        return wrapper

    def _guarded_edit(self, *a, **kw):
        if self.permission == PERMISSION_READONLY:
            return "DENIED: read-only mode is on"
        detail = f"Edit {a[0] if a else '?'}"
        if len(a) >= 3:
            detail += f"\n\nOLD:\n{str(a[1])[:200]}\n\nNEW:\n{str(a[2])[:200]}"
        if not self._ask_permission("File edit", detail):
            return "DENIED by user"
        return tool_edit_file(*a, **kw)

    def _guarded_shell(self, *a, **kw):
        if self.permission == PERMISSION_READONLY:
            return "DENIED: read-only mode is on"
        cmd = a[0] if a else ""
        first = cmd.split()[0] if cmd.split() else ""
        if first in ("ls", "pwd", "cat", "head", "tail", "grep", "find",
                     "wc", "echo", "date", "whoami", "git", "tree", "dir",
                     "type", "where"):
            return tool_shell_run(*a, **kw)
        if not self._ask_permission("Shell command", cmd):
            return "DENIED by user"
        return tool_shell_run(*a, **kw)

    # ---- subagent ----

    def _run_subagent(self, description: str, prompt: str) -> str:
        sub_messages = [
            {"role": "system", "content":
                f"You are a subagent. Job: {description}.\n"
                "Use tools to investigate, then return a concise final "
                "answer. The caller sees only your final message.\n"
                f"Workspace: {WORKSPACE}"},
            {"role": "user", "content": prompt},
        ]

        for turn in range(1, MAX_SUBAGENT_TURNS + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=sub_messages,
                    tools=self.all_schemas, tool_choice="auto",
                    temperature=0.2)
            except Exception as e:
                return f"SUBAGENT ERROR: {e}"

            msg = resp.choices[0].message
            assistant = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ]
            sub_messages.append(assistant)

            if not msg.tool_calls:
                return msg.content or "(subagent returned nothing)"

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                fn = self.all_callables.get(name)
                try:
                    result = fn(**args) if fn else f"unknown tool: {name}"
                except Exception as e:
                    result = f"ERROR: {e}"
                sub_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)[:4000],
                })

        return "(subagent hit turn limit)"

    # ---- save / load ----

    def _save_local_chat(self):
        try:
            data = {
                "messages": self.messages,
                "log": self._log_history[-500:],
                "model": self.model,
                "saved_at": time.time(),
            }
            tmp = CHAT_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
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
                return
            except Exception as e:
                print(f"[cloud] {server}: {e}")

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
                print(f"[cloud] {server}: {e}")
                continue
            blob = data.get("state")
            if not blob:
                return
            try:
                state = json.loads(blob)
            except Exception:
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
            return

    def _save_chat_manual(self):
        self._save_local_chat()
        self._save_cloud_chat()
        cloud = " + cloud" if (self.cloud_sync and self.cloud_token) else ""
        self.log_line(f"[save] chat saved{cloud} → {CHAT_FILE}", "dim")

    # ---- actions ----

    def _on_clear(self):
        if not messagebox.askyesno(
                "Clear chat",
                "Clear the log and the conversation memory?\n\n"
                "The saved chat file will be wiped too.",
                parent=self.root):
            return
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self._log_history = []
        self._last_agent_answer = ""
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.log_line("── cleared ──", "dim")
        self._save_local_chat()

    def _copy_last(self):
        if not self._last_agent_answer:
            self.log_line("[copy] no agent answer yet", "dim")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._last_agent_answer)
            self.log_line(f"[copy] copied {len(self._last_agent_answer)} chars "
                          "to clipboard", "dim")
        except Exception as e:
            self.log_line(f"[copy] failed: {e}", "error")

    def _export_chat(self):
        try:
            path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Export chat",
                defaultextension=".md",
                initialfile=f"chat-{time.strftime('%Y%m%d-%H%M%S')}.md",
                filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
            if not path:
                return
            Path(path).write_text(self._chat_as_markdown(), encoding="utf-8")
            self.log_line(f"[export] wrote {path}", "dim")
        except Exception as e:
            self.log_line(f"[export] failed: {e}", "error")

    def _chat_as_markdown(self) -> str:
        lines = [f"# Chat export",
                 "",
                 f"- model: `{self.model}`",
                 f"- exported: {time.strftime('%Y-%m-%d %H:%M')}",
                 "",
                 "---",
                 ""]
        for m in self.messages[1:]:
            role = m.get("role", "?")
            content = m.get("content") or ""
            if role == "user":
                lines.append("## User")
                lines.append("")
                lines.append(content)
                lines.append("")
            elif role == "assistant":
                lines.append("## Agent")
                lines.append("")
                if content:
                    lines.append(content)
                    lines.append("")
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    lines.append(f"- tool call: `{fn.get('name','?')}` "
                                 f"`{fn.get('arguments','')[:200]}`")
                lines.append("")
            elif role == "tool":
                lines.append("### Tool result")
                lines.append("")
                lines.append("```")
                lines.append(content[:2000])
                lines.append("```")
                lines.append("")
        return "\n".join(lines)

    # ---- run control ----

    def _set_running(self, running):
        if running:
            self.send_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.continue_btn.configure(state="disabled")
            self.clear_btn.configure(state="disabled")
            self.status_lbl.configure(text="running…")
        else:
            self.send_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.continue_btn.configure(
                state="normal" if self._stopped_last else "disabled")
            self.clear_btn.configure(state="normal")
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
        self._worker = threading.Thread(target=self._run_agent, args=(None,),
                                        daemon=True)
        self._worker.start()

    # ---- dialogs ----

    def _open_settings(self):
        SettingsDialog(self.root, self)

    def _open_skills(self):
        SkillsDialog(self.root, self)

    def _open_help(self):
        HelpDialog(self.root, self)

    def _show_todo(self):
        self.log_line("\n" + self.todo.render(), "dim")

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
        self.log_line(f"browser self-test: {result}",
                      "dim" if ok else "error")

    def log_line(self, text, tag=None):
        with self._log_lock:
            self._log_history.append((text, tag))
        self._log_q.put((text, tag))

    def _poll_log(self):
        try:
            while True:
                text, tag = self._log_q.get_nowait()
                self.log.configure(state="normal")
                if tag == "agent_md":
                    self.log.insert("end", "AGENT ▸ ", "agent")
                    render_markdown(self.log, text)
                    self.log.insert("end", "\n")
                elif tag:
                    self.log.insert("end", text + "\n", tag)
                else:
                    self.log.insert("end", text + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(60, self._poll_log)

    # ---- input ----

    def on_send(self):
        task = self.entry.get().strip()
        if not task:
            return
        self.entry.delete(0, "end")
        low = task.lower()

        if low in ("/reset", "/clear"):
            self._on_clear()
            return
        if low == "/history":
            for m in self.messages[1:]:
                role = m.get("role", "?")
                content = (m.get("content") or "")[:140].replace("\n", " ")
                self.log_line(f"  [{role}] {content}", "dim")
            return
        if low == "/skills":
            self.log_line(f"active: {', '.join(self.skill_names) or '(none)'}",
                          "dim")
            for m in self.skill_meta:
                self.log_line(f"  - {m['name']}: "
                              f"{m.get('description', '')[:100]}", "dim")
            if self.disabled_skills:
                self.log_line(f"disabled: {', '.join(self.disabled_skills)}",
                              "dim")
            if self.skill_commands:
                self.log_line("commands:", "dim")
                for cname, cdef in sorted(self.skill_commands.items()):
                    self.log_line(f"  /{cname:<14} "
                                  f"{cdef.get('description', '')}", "dim")
            return
        if low == "/todo":
            self.log_line("\n" + self.todo.render(), "dim")
            return
        if low == "/todo clear":
            self.todo.write([])
            self.log_line("[todo] cleared", "dim")
            return
        if low == "/save":
            self._save_chat_manual()
            return
        if low == "/permission":
            self.log_line(f"permission mode: {self.permission}", "dim")
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

        self.log_line(f"\n▸ {task}", "user")
        self._stopped_last = False
        self._stop_event.clear()
        self._set_running(True)
        self._worker = threading.Thread(target=self._run_agent, args=(task,),
                                        daemon=True)
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
            if len(self.messages) > 60:
                self.messages = [self.messages[0]] + self.messages[-50:]

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

            reasoning = getattr(msg, "reasoning", None) or \
                getattr(msg, "reasoning_content", None)
            if reasoning:
                self.log_line(f"  {str(reasoning)[:400]}", "think")

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
                self._last_agent_answer = msg.content or "(done)"
                self.log_line(self._last_agent_answer, "agent_md")
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
                self.log_line(f"→ {name}({preview[:220]})", "tool")

                fn = self.all_callables.get(name)
                try:
                    result = fn(**args) if fn else f"unknown tool: {name}"
                except Exception as e:
                    result = f"ERROR: {e}"

                tag = "error" if str(result).startswith(
                    ("ERROR", "BLOCKED", "NOT_FOUND", "DENIED")) else "result"
                self.log_line(
                    f"← {str(result)[:600].replace(chr(10), ' ⏎ ')}", tag)

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result)[:6000],
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