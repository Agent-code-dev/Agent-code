"""Security primitives for the agent.

- Command risk classifier (critical / high / medium / low)
- Secret redaction for any text passing through logs or context
- Path validation against a workspace root
- Append-only audit log
"""
import os
import re
import json
import time
import hashlib
from pathlib import Path

RISK_PATTERNS = [
    (r"\brm\s+-rf\s+/", "critical"),
    (r":\(\)\s*\{", "critical"),
    (r"mkfs\.", "critical"),
    (r"dd\s+if=", "critical"),
    (r"format\s+[a-z]:", "critical"),
    (r"del\s+/[sq]", "critical"),
    (r"rd\s+/s", "critical"),
    (r"shutdown", "critical"),
    (r"reboot", "critical"),
    (r"reg\s+delete", "critical"),
    (r"rm\s+-rf\s+~", "critical"),
    (r"diskpart", "critical"),
    (r"bcdedit", "critical"),
    (r"git\s+push[^\n]*--force", "high"),
    (r"git\s+reset\s+--hard", "high"),
    (r"drop\s+table", "high"),
    (r"truncate\s+table", "high"),
    (r"sudo\s+rm", "high"),
    (r"chmod\s+-R\s+777", "high"),
    (r"ssh-keygen", "medium"),
    (r"scp\s+", "medium"),
    (r"chmod\s+777", "medium"),
    (r"sudo\s+", "medium"),
    (r"eval\s*\(", "medium"),
    (r"exec\s*\(", "medium"),
    (r"__import__\s*\(", "medium"),
    (r"base64\s+-d", "medium"),
    (r"curl\s+[^\n]*\|\s*sh", "critical"),
]

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_\-]{20,}", "openai_key"),
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "anthropic_key"),
    (r"ghp_[A-Za-z0-9]{36}", "github_pat"),
    (r"gho_[A-Za-z0-9]{36}", "github_oauth"),
    (r"ghs_[A-Za-z0-9]{36}", "github_server"),
    (r"AIza[A-Za-z0-9_\-]{35}", "google_api"),
    (r"xox[baprs]-[A-Za-z0-9\-]{10,}", "slack_token"),
    (r"AKIA[A-Z0-9]{16}", "aws_access"),
    (r"ASIA[A-Z0-9]{16}", "aws_session"),
    (r"re_[A-Za-z0-9_]{20,}", "resend_key"),
    (r"xkeysib-[A-Za-z0-9]{40,}", "brevo_key"),
    (r"cc_[A-Za-z0-9]{20,}", "codecraft_key"),
    (r"-----BEGIN[^-]{0,40}PRIVATE KEY-----", "private_key"),
    (r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", "jwt"),
]

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def classify_risk(cmd: str) -> str:
    """Return highest risk level found in a shell command."""
    worst = "low"
    for pat, level in RISK_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            if RISK_ORDER[level] > RISK_ORDER[worst]:
                worst = level
    return worst


def redact_secrets(text: str) -> str:
    """Replace API keys and tokens with [REDACTED:label]."""
    if not isinstance(text, str):
        return text
    out = text
    for pat, label in SECRET_PATTERNS:
        out = re.sub(pat, f"[REDACTED:{label}]", out)
    return out


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_path(path: str, root) -> Path:
    """Resolve `path` and ensure it lives under `root`. Raises on escape."""
    p = Path(path).resolve()
    r = Path(root).resolve()
    try:
        p.relative_to(r)
    except ValueError:
        raise ValueError(f"path escapes root: {path}")
    return p


class AuditLog:
    """Append-only JSONL audit log. Thread-safe via OS append semantics."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields):
        rec = {"ts": time.time(), "event": event}
        rec.update(fields)
        line = json.dumps(rec, default=str)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass