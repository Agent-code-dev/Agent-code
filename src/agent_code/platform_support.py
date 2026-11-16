"""Portable platform and package-manager helpers; no distro allow-list."""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path


def distribution_info() -> dict[str, str]:
    info = {}
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/etc/os-release").read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    info[key] = value.strip().strip('"')
        except OSError:
            pass
    return {"id": info.get("ID", "unknown"), "name": info.get("PRETTY_NAME", "").strip(),
            "version": info.get("VERSION_ID", "")}


def podman_install_command() -> tuple[list[str], list[str]] | None:
    """Return (privilege_prefix, package-manager command) when recognized."""
    candidates = [
        ("apt-get", ["apt-get", "install", "-y", "podman"], ["sudo"]),
        ("dnf", ["dnf", "install", "-y", "podman"], ["sudo"]),
        ("yum", ["yum", "install", "-y", "podman"], ["sudo"]),
        ("pacman", ["pacman", "-S", "--needed", "--noconfirm", "podman"], ["sudo"]),
        ("zypper", ["zypper", "--non-interactive", "install", "podman"], ["sudo"]),
        ("apk", ["apk", "add", "podman"], ["doas"] if shutil.which("doas") else ["sudo"]),
        ("xbps-install", ["xbps-install", "-Sy", "podman"], ["sudo"]),
        ("emerge", ["emerge", "--ask=n", "app-containers/podman"], ["sudo"]),
        ("nix", ["nix", "profile", "install", "nixpkgs#podman"], []),
        ("guix", ["guix", "install", "podman"], []),
        ("pkg", ["pkg", "install", "-y", "podman"], ["sudo"]),
        ("brew", ["brew", "install", "podman"], []),
    ]
    for executable, command, prefix in candidates:
        if shutil.which(executable):
            return prefix, command
    return None
