"""agent-code terminal — interactive CLI agent.

Run:  python terminal.py
Or:   .\agent-code.cmd
"""
import hashlib
import importlib.util
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

os.system("")

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from agent_security import AuditLog, classify_risk, redact_secrets, safe_path
from skill_security import scan_skill, verdict, hash_skill
from skill_runner import run_tool
from loader import load_skills, discover_skills

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: pip install openai")
    sys.exit(1)

# ---------- ANSI ----------
R = "\x1b[0m"; D = "\x1b[2m"; B = "\x1b[1m"
RED = "\x1b[31m"; GRN = "\x1b[32m"; YEL = "\x1b[33m"
BLU = "\x1b[34m"; CYA = "\x1b[36m"; MAG = "\x1b[35m"

def c(s, color=""):
    return f"{color}{s}{R}"

# ---------- Config ----------
WORKSPACE = ROOT / "workspace"
SKILLS_DIR = ROOT / "skills"
CONFIG = ROOT / "agent_config.json"
AUDIT = AuditLog(ROOT / "logs" / "audit.jsonl")
WORKSPACE.mkdir(parents=True, exist_ok=True)

def load_cfg():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

CFG = load_cfg()
KEYS = CFG.get("openai_api_keys") or []
KEYS = [k.strip() for k in KEYS if k and k.strip()]
BASE = CFG.get("openai_base_url") or "https://api.openai.com/v1"
MODEL = CFG.get("openai_model") or "gpt-4o"
PERMISSION = CFG.get("permission_mode") or "ask"

if not KEYS:
    print(c("ERROR:", RED), "no API keys in", CONFIG)
    print("Create", CONFIG, "with:")
    print(json.dumps({
        "openai_api_keys": ["sk-..."],
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o",
    }, indent=2))
    sys.exit(1)

_key_cycle = itertools.cycle(KEYS)

def make_client():
    """Fresh OpenAI client bound to the next key in rotation."""
    return OpenAI(api_key=next(_key_cycle), base_url=BASE)

# ---------- Load skills ----------
SCHEMAS, CALLABLES, METADATA, COMMANDS = load_skills(SKILLS_DIR)
SKILL_TOOL_OWNER = {}
for skill_file in sorted(SKILLS_DIR.glob("*/skill.py")):
    try:
        spec = importlib.util.spec_from_file_location(
            "_scan_" + skill_file.parent.name, skill_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for s in getattr(mod, "TOOL_SCHEMAS", []) or []:
            n = s.get("function", {}).get("name")
            if n:
                SKILL_TOOL_OWNER[n] = str(skill_file)
    except Exception:
        pass

# ---------- Core tools ----------
def read_file(path, offset=0, limit=500):
    try:
        base = ROOT if Path(path).is_absolute() else WORKSPACE
        p = safe_path(path if Path(path).is_absolute() else (WORKSPACE / path),
                      base if Path(path).is_absolute() else WORKSPACE)
    except ValueError as e:
        return "ERROR: " + str(e)
    if not p.exists():
        return "ERROR: not found: " + path
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    chunk = lines[offset:offset + limit]
    return "\n".join(f"{i+offset+1:>6}\t{ln}" for i, ln in enumerate(chunk)) or "(empty)"

def write_file(path, content):
    try:
        p = safe_path(WORKSPACE / path if not Path(path).is_absolute() else path,
                      WORKSPACE)
    except ValueError as e:
        return "ERROR: " + str(e)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return "OK wrote {} chars to {}".format(len(content), path)

def edit_file(path, old_string, new_string, replace_all=False):
    try:
        p = safe_path(WORKSPACE / path, WORKSPACE)
    except ValueError as e:
        return "ERROR: " + str(e)
    if not p.exists():
        return "ERROR: not found: " + path
    text = p.read_text(encoding="utf-8")
    n = text.count(old_string)
    if n == 0:
        return "ERROR: old_string not found"
    if n > 1 and not replace_all:
        return "ERROR: not unique ({} matches)".format(n)
    p.write_text(text.replace(old_string, new_string, -1 if replace_all else 1),
                 encoding="utf-8")
    return "OK replaced {}".format(n if replace_all else 1)

def shell_run(command):
    if PERMISSION == "readonly":
        return "DENIED: readonly mode"
    risk = classify_risk(command)
    if risk == "critical":
        AUDIT.write("shell_block", cmd=command, risk=risk)
        return "BLOCKED: critical risk command"
    if risk == "high" and PERMISSION != "auto":
        print(c("\n  [risk] {}: {}".format(risk, command[:100]), YEL))
        try:
            ans = input(c("  allow? [y/N] ", YEL)).strip().lower()
        except EOFError:
            ans = "n"
        if ans != "y":
            AUDIT.write("shell_deny", cmd=command, risk=risk)
            return "DENIED by user"
    if PERMISSION == "readonly":
        return "DENIED: readonly mode"
    if re.search(r"[|&;<>`$]", command) and PERMISSION != "auto":
        return "BLOCKED: shell metacharacters"
    try:
        parts = shlex.split(command, posix=False)
    except ValueError as e:
        return "ERROR: parse " + str(e)
    try:
        r = subprocess.run(parts, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=30, cwd=str(WORKSPACE), shell=False)
        out = ((r.stdout or "") + (r.stderr or "")).strip() or "(no output)"
        AUDIT.write("shell_run", cmd=command, risk=risk)
        return redact_secrets(out[:4000])
    except Exception as e:
        return "ERROR: " + str(e)

CORE = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "shell_run": shell_run,
}

CORE_SCHEMAS = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "offset": {"type": "integer"},
                                      "limit": {"type": "integer"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Write a file",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "edit_file", "description": "Replace exact string in file",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "old_string": {"type": "string"},
                                      "new_string": {"type": "string"},
                                      "replace_all": {"type": "boolean"}},
                       "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {
        "name": "shell_run", "description": "Run allowlisted shell command",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
]

ALL_SCHEMAS = CORE_SCHEMAS + SCHEMAS
ALL_CALLABLES = dict(CORE)
ALL_CALLABLES.update(CALLABLES)

skill_lines = "\n".join(
    "- {}: {}".format(m.get("name"), m.get("description", ""))
    for m in METADATA if not m.get("_blocked")
)

SYSTEM = (
    "You are Agent Code - a local coding agent with a headless browser, "
    "sandboxed shell, and skills.\n\n"
    "Workspace: {}\n\n"
    "Tools:\n"
    "- read_file, write_file, edit_file, shell_run\n"
    "- Plus any skills listed below\n\n"
    "Rules:\n"
    "- Read before editing.\n"
    "- Prefer edit_file over write_file.\n"
    "- Critical-risk shell commands are blocked. High-risk prompt for approval.\n"
    "- Be concise.\n\n"
    "Loaded skills:\n{}"
).format(WORKSPACE, skill_lines)

# ---------- Agent loop ----------
MESSAGES = [{"role": "system", "content": SYSTEM}]

def stream_agent(task):
    MESSAGES.append({"role": "user", "content": task})
    if len(MESSAGES) > 40:
        MESSAGES[:] = [MESSAGES[0]] + MESSAGES[-30:]
    AUDIT.write("task", task=task[:300], model=MODEL)
    for turn in range(1, 25):
        print(c("\n  turn {}".format(turn), D))
        try:
            resp = make_client().chat.completions.create(
                model=MODEL, messages=MESSAGES,
                tools=ALL_SCHEMAS, tool_choice="auto",
                temperature=0.2)
        except Exception as e:
            print(c("  LLM ERROR: {}".format(e), RED))
            return
        msg = resp.choices[0].message
        asst = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            asst["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in msg.tool_calls]
        MESSAGES.append(asst)
        if not msg.tool_calls:
            print(c("\nAGENT > ", GRN) + (msg.content or "(done)"))
            return
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            preview = ", ".join("{}={!r}".format(k, v) for k, v in args.items())[:120]
            print(c("  -> {}".format(name), CYA) + c("({})".format(preview), D))
            if name in SKILL_TOOL_OWNER:
                res = run_tool(SKILL_TOOL_OWNER[name], name, args, timeout=30)
                result = res.get("result") or res.get("error", "(no result)")
            else:
                fn = ALL_CALLABLES.get(name)
                try:
                    result = fn(**args) if fn else "unknown tool " + name
                except Exception as e:
                    result = "ERROR: " + str(e)
            snippet = str(result)[:200].replace("\n", " / ")
            print(c("  <- {}".format(snippet), MAG))
            MESSAGES.append({"role": "tool", "tool_call_id": tc.id,
                             "content": str(result)[:5000]})

# ---------- Commands ----------
def cmd_help():
    print("\n" + c("Commands", B) + """
  /help           this help
  /reset          clear conversation memory
  /skills         list loaded skills + security scores
  /scan           rescan skill folders
  /perm <mode>    readonly | ask | auto
  /keys           show API key fingerprints (masked)
  /quit           exit

""" + c("Anything else is a task for the agent.", D) + "\n")

def cmd_skills():
    print("\n" + c("Skills", B))
    for s in discover_skills(SKILLS_DIR):
        folder = SKILLS_DIR / s["name"]
        sc = scan_skill(folder)
        v = verdict(sc["score"])
        color = GRN if v == "safe" else (YEL if v in ("warn", "suspicious") else RED)
        print("  {:<16} v{:<8} risk={} ({})  {}".format(
            c(s["name"], B), s.get("version", "?"),
            c(str(sc["score"]), color), v,
            s.get("description", "")[:60]))
    print()

def cmd_scan():
    print("\n" + c("Security scan", B))
    for s in discover_skills(SKILLS_DIR):
        folder = SKILLS_DIR / s["name"]
        sc = scan_skill(folder)
        v = verdict(sc["score"])
        color = GRN if v == "safe" else (YEL if v in ("warn", "suspicious") else RED)
        print("  {:<16} score={} verdict={} findings={}".format(
            c(s["name"], B), c(str(sc["score"]), color), v, sc["total"]))
        for fname, findings in sc["findings"].items():
            for f in findings[:3]:
                print("    {}{}:{} [{}] {}{}".format(
                    D, fname, f["line"], f["level"], f["pattern"], R))
        h = hash_skill(folder)
        print("    {}sha256: {}...{}".format(D, h[:16], R))
    print()

def cmd_perm(mode):
    global PERMISSION
    if mode not in ("readonly", "ask", "auto"):
        print(c("  use: readonly | ask | auto", YEL))
        return
    PERMISSION = mode
    CFG["permission_mode"] = mode
    CONFIG.write_text(json.dumps(CFG, indent=2), encoding="utf-8")
    print(c("  permission -> {}".format(mode), GRN))

def cmd_keys():
    for i, k in enumerate(KEYS, 1):
        h = hashlib.sha256(k.encode()).hexdigest()[:12]
        print("  key {}: {}...  sha256:{}{}".format(i, c(k[:6], D), c(h, D), R))

# ---------- Main ----------
def main():
    print(c("\n" + "=" * 68, BLU))
    print(c("  AGENT-CODE", B) + c("  |  terminal v1.0.2", D))
    print(c("=" * 68, BLU))
    print("  model     " + c(MODEL, CYA))
    print("  base      " + c(BASE, D))
    print("  workspace " + c(str(WORKSPACE), D))
    loaded = len([m for m in METADATA if not m.get("_blocked")])
    blocked = len([m for m in METADATA if m.get("_blocked")])
    print("  skills    {} loaded ({} blocked)".format(loaded, blocked))
    print("  perm      " + c(PERMISSION, YEL))
    print(c("  /help for commands\n", D))

    while True:
        try:
            line = input(c("agent-code", GRN) + c(" > ", D)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.startswith("/"):
            parts = line[1:].split()
            cmd = parts[0].lower() if parts else ""
            args = parts[1:]
            if cmd in ("quit", "exit", "q"):
                break
            elif cmd in ("help", "h", "?"):
                cmd_help()
            elif cmd == "skills":
                cmd_skills()
            elif cmd == "scan":
                cmd_scan()
            elif cmd == "perm":
                cmd_perm(args[0] if args else "")
            elif cmd == "keys":
                cmd_keys()
            elif cmd == "reset":
                MESSAGES[:] = [MESSAGES[0]]
                print(c("  memory cleared", D))
            else:
                print(c("  unknown command: /" + cmd, YEL))
            continue
        try:
            stream_agent(line)
        except Exception as e:
            print(c("ERROR: " + str(e), RED))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")