"""Path resolution for pip-installed use."""
import os
import json
import shutil
from pathlib import Path

PACKAGE_ROOT   = Path(__file__).parent.resolve()
DATA_DIR       = PACKAGE_ROOT / "data"
BUNDLED_SITE   = DATA_DIR / "site"
BUNDLED_SKILLS = DATA_DIR / "skills"

def user_config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        p = Path(base) / "agent-code"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else (Path.home() / ".config")
        p = base / "agent-code"
    p.mkdir(parents=True, exist_ok=True)
    return p

def user_config_file() -> Path:
    return user_config_dir() / "agent_config.json"

def global_data_dir() -> Path:
    """Per-user local data directory, independent of the current project."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        p = Path(base) / "AgentCode"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        p = (Path(base) if base else Path.home() / ".local" / "share") / "agent-code"
    p.mkdir(parents=True, exist_ok=True)
    return p


def global_skills_dir() -> Path:
    p = global_data_dir() / "skills"
    p.mkdir(parents=True, exist_ok=True)
    return p



def global_addons_dir() -> Path:
    """Per-user add-on directory, separate from skills and project files."""
    p = global_data_dir() / "addons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def migrate_project_skills_to_global() -> list:
    """Copy legacy project skills into the global user skill directory once, without overwriting."""
    source = Path.cwd() / "skills"
    target = global_skills_dir()
    copied = []
    if source.resolve() == target.resolve() or not source.is_dir():
        return copied
    for folder in source.iterdir():
        if not folder.is_dir() or not (folder / "skill.py").is_file():
            continue
        destination = target / folder.name
        if destination.exists():
            continue
        try:
            shutil.copytree(folder, destination)
            copied.append(folder.name)
        except OSError:
            # A single inaccessible skill must not prevent the app from starting.
            continue
    return copied


def _cfg() -> dict:
    p = user_config_file()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def use_global_paths() -> bool:
    env = os.environ.get("AGENT_CODE_GLOBAL")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return bool(_cfg().get("use_global_paths"))


def project_dir() -> Path:
    if use_global_paths():
        return global_data_dir()
    return Path.cwd()
def project_workspace_dir() -> Path:
    p = project_dir() / "workspace"; p.mkdir(parents=True, exist_ok=True); return p
def project_skills_dir() -> Path:
    """Compatibility name: skills are global per-user, not project-local."""
    migrate_project_skills_to_global()
    return global_skills_dir()
def project_chats_dir() -> Path:
    p = project_dir() / "chats";     p.mkdir(parents=True, exist_ok=True); return p

def project_config_file() -> Path:
    """Compatibility name: API keys and settings are always stored per-user."""
    return user_config_file()

def list_bundled_skills() -> list:
    if not BUNDLED_SKILLS.exists(): return []
    return sorted(d.name for d in BUNDLED_SKILLS.iterdir()
                  if d.is_dir() and (d / "skill.py").exists())

def install_bundled_skills(overwrite: bool = False) -> list:
    target = project_skills_dir(); written = []
    if not BUNDLED_SKILLS.exists(): return written
    for folder in sorted(BUNDLED_SKILLS.iterdir()):
        if not folder.is_dir(): continue
        if not (folder / "skill.py").exists(): continue
        dst = target / folder.name
        if dst.exists() and not overwrite: continue
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(folder, dst); written.append(folder.name)
    return written

def bundled_site_dir() -> Path:
    return BUNDLED_SITE
