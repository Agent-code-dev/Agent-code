"""Static security analysis for skills.

Scans skill source before loading. Produces a risk score 0-10.
No execution of the skill is performed.
"""
import re
import json
import hashlib
from pathlib import Path

CRITICAL = [
    r"/etc/(passwd|shadow|sudoers)",
    r"\.ssh/id_",
    r"\.aws/credentials",
    r"\.kube/config",
    r"os\.exec[lv]p?e?\s*\(",
    r"pty\.spawn",
    r"marshal\.loads",
    r"rm\s+-rf\s+/",
    r"shutil\.rmtree\s*\(\s*['\"]/",
    r"curl\s+[^\n]*\|\s*sh",
    r"wget\s+[^\n]*\|\s*sh",
    r"setattr\s*\(\s*__builtins__",
    r"AppData\\\\Roaming\\\\Microsoft",
    r"C:\\\\Windows\\\\System32",
    r"crontab\s+-",
    r"schtasks\s+/create",
    r"systemctl\s+(enable|start)",
    r"LaunchAgents",
    r"LaunchDaemons",
    r"stratum\+tcp://",
    r"\bxmrig\b",
    r"\\AppData\\Local\\Google\\Chrome\\User Data",
    r"\bLogin Data\b",
    r"\.config/gcloud",
    r"\.docker/config\.json",
    r"\bmitmproxy\b",
    r"\bncat\b",
    r"\bmsfvenom\b",
]

HIGH = [
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"__import__\s*\(",
    r"importlib\.import_module\s*\(",
    r"os\.system\s*\(",
    r"os\.popen\s*\(",
    r"subprocess\.(Popen|run|call|check_output)\s*\([^)]*shell\s*=\s*True",
    r"pickle\.loads",
    r"base64\.b64decode\s*\([^)]*\)\s*\.decode",
    r"codecs\.decode\s*\(",
    r"globals\s*\(\s*\)\s*\[",
    r"vars\s*\(\s*\)\s*\[",
    r"ctypes\.(CDLL|WinDLL|windll|oledll)\s*\(",
    r"ctypes\.util\.find_library",
    r"sys\.modules\s*\[",
    r"__builtins__\s*\[",
    r"pty\.openpty",
    r"globals\s*\(\s*\)\s*\.(update|setdefault)",
]

MEDIUM = [
    r"subprocess\.",
    r"socket\.socket\s*\(",
    r"paramiko",
    r"smtplib",
    r"ftplib\.FTP",
    r"base64\.b64decode\s*\(",
    r"os\.environ\.(items|copy)\s*\(",
    r"keyring\.",
    r"requests?\.post\s*\(",
    r"urllib\.request\.Request\s*\(",
]

INVISIBLE = "\u200b\u200c\u200d\u202a\u202b\u202c\u202d\u202e\ufeff"

LEVELS = [("critical", CRITICAL, 10), ("high", HIGH, 4), ("medium", MEDIUM, 2)]


def scan_source(src: str) -> list:
    findings = []
    for i, line in enumerate(src.splitlines(), 1):
        for label, pats, _ in LEVELS:
            for pat in pats:
                if re.search(pat, line, re.IGNORECASE):
                    findings.append({
                        "line": i, "level": label, "pattern": pat,
                        "snippet": line.strip()[:140],
                    })
    for ch in INVISIBLE:
        if ch in src:
            findings.append({
                "line": 0, "level": "critical",
                "pattern": "invisible unicode",
                "snippet": f"U+{ord(ch):04X}",
            })
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"[A-Za-z0-9+/]{500,}={0,2}", line):
            findings.append({
                "line": i, "level": "high",
                "pattern": "long base64 blob",
                "snippet": line.strip()[:60] + "...",
            })
    return findings


def score(findings: list) -> int:
    weights = {"critical": 10, "high": 4, "medium": 2}
    return min(10, sum(weights.get(f["level"], 0) for f in findings))


def scan_skill(skill_dir) -> dict:
    """Return {findings: {file: [...]}, score, total} for a skill folder."""
    skill_dir = Path(skill_dir)
    results = {}
    for py in skill_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8", errors="replace")
        f = scan_source(src)
        if f:
            results[str(py.relative_to(skill_dir))] = f
    all_f = [x for v in results.values() for x in v]
    return {"findings": results, "score": score(all_f), "total": len(all_f)}


def hash_skill(skill_dir) -> str:
    """SHA-256 over sorted Python files. Stable fingerprint."""
    h = hashlib.sha256()
    for py in sorted(Path(skill_dir).rglob("*.py")):
        h.update(str(py.relative_to(skill_dir)).encode())
        h.update(py.read_bytes())
    return h.hexdigest()


def verdict(s: int) -> str:
    if s >= 10:
        return "malicious"
    if s >= 6:
        return "suspicious"
    if s >= 3:
        return "warn"
    return "safe"