"""CLI entry point. Subcommands: run, manage, skills, doctor."""
import os
import sys
import argparse
from . import __version__

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agent-code",
        description="Local AI agent with headless browser and skills.")
    ap.add_argument("--version", action="version",
                    version=f"agent-code {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("run", help="run the agent (default)")
    p.add_argument("--global", dest="global_paths", action="store_true",
                   help="use ~/.agent-code for skills, workspace and chats")
    p.set_defaults(func=_run)

    p = sub.add_parser("tui", help="full terminal UI for headless PCs and SSH sessions")
    p.add_argument("--global", dest="global_paths", action="store_true",
                   help="use ~/.agent-code for skills, workspace and chats")
    p.set_defaults(func=_tui)

    p = sub.add_parser("manage", help="skill manager GUI")
    p.add_argument("--global", dest="global_paths", action="store_true",
                   help="install skills into ~/.agent-code/skills")
    p.set_defaults(func=_manage)

    p = sub.add_parser("gui", help="launch the desktop GUI explicitly")
    p.set_defaults(func=_gui)

    p = sub.add_parser("doctor", help="diagnose installation and configuration issues")
    p.add_argument("--json", action="store_true", help="print machine-readable JSON")
    p.add_argument("--output", metavar="FILE", help="write a privacy-conscious JSON report")
    p.set_defaults(func=_doctor)

    p = sub.add_parser("skills", help="list or install bundled skills")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "install"])
    p.set_defaults(func=_skills)

    args = ap.parse_args(argv)
    if args.cmd is None:
        return _run(args)
    return args.func(args)

def _run(args):
    if getattr(args, "global_paths", False):
        os.environ["AGENT_CODE_GLOBAL"] = "1"
    # A monitor-free Linux machine has no graphical display: use the terminal UI.
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No graphical display detected; starting Agent Code TUI. Use `agent-code gui` on a desktop.")
        return _tui(args)
    _ensure_linux_tkinter()
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        print("CustomTkinter is missing. Install Agent Code dependencies with: python -m pip install -e .")
        print("For a monitor-free PC, run `agent-code tui` instead.")
        return 1
    from .agent import main as m
    m(); return 0

def _ensure_linux_tkinter():
    """Offer an opt-in system package install for Tkinter on common Linux distros."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import tkinter  # noqa: F401
        return
    except ImportError:
        pass
    if not sys.stdin.isatty():
        print("Tkinter is missing. Install the distro package (python3-tk/python3-tkinter/tk) to use the GUI.")
        return
    print("Tkinter is missing; the GUI needs your Linux distribution's Tk package.")
    try:
        answer = input("Install it now using the system package manager? [y/N] ").strip().lower()
    except EOFError:
        return
    if answer not in ("y", "yes"):
        print("Skipped Tkinter installation. You can still use `agent-code tui` without a monitor.")
        return
    import shutil, subprocess
    commands = []
    if shutil.which("apt-get"):
        commands = [["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", "python3-tk"]]
    elif shutil.which("dnf"):
        commands = [["sudo", "dnf", "install", "-y", "python3-tkinter"]]
    elif shutil.which("pacman"):
        commands = [["sudo", "pacman", "-Sy", "--needed", "tk"]]
    elif shutil.which("zypper"):
        commands = [["sudo", "zypper", "install", "python3-tk"]]
    elif shutil.which("apk"):
        commands = [["sudo", "apk", "add", "python3-tkinter", "tk"]]
    else:
        print("Unsupported package manager. Install Tkinter manually; TUI mode needs no Tkinter.")
        return
    try:
        for command in commands:
            subprocess.run(command, check=True)
        print("Tkinter package installation completed. If Python still cannot import tkinter, check that your active Python matches the distro package.")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Could not install Tkinter automatically: {exc}")
        print("Use `agent-code tui` or install the matching Tk package manually.")

def _tui(args):
    if getattr(args, "global_paths", False):
        os.environ["AGENT_CODE_GLOBAL"] = "1"
    from .tui import main as run_tui
    return run_tui()

def _gui(args):
    _ensure_linux_tkinter()
    try:
        import tkinter  # noqa: F401
        import customtkinter  # noqa: F401
    except ImportError as exc:
        print(f"Desktop GUI dependencies unavailable: {exc}. Try `agent-code tui`.")
        return 1
    from .agent import main as m
    m(); return 0

def _manage(args):
    if getattr(args, "global_paths", False):
        os.environ["AGENT_CODE_GLOBAL"] = "1"
    from .skill_manager import main as m
    m(); return 0

def _doctor(args):
    from .doctor import main as run_doctor
    return run_doctor(as_json=args.json, output=args.output)

def _skills(args):
    from .paths import (install_bundled_skills, list_bundled_skills,
                        project_skills_dir)
    if args.action == "list":
        print("Bundled skills:")
        for n in list_bundled_skills():
            print(f"  - {n}")
        print()
        print(f"Install location: {project_skills_dir()}")
        return 0
    copied = install_bundled_skills(overwrite=False)
    if not copied:
        print("All bundled skills are already installed.")
    else:
        for name in copied:
            print(f"  installed: {name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
