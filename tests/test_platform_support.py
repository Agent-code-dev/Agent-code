from agent_code import platform_support


def test_detects_xbps_without_distro_allowlist(monkeypatch):
    monkeypatch.setattr(platform_support.shutil, "which", lambda name: "/usr/bin/xbps-install" if name == "xbps-install" else None)
    prefix, command = platform_support.podman_install_command()
    assert prefix == ["sudo"]
    assert command == ["xbps-install", "-Sy", "podman"]


def test_detects_nix_profile_install(monkeypatch):
    monkeypatch.setattr(platform_support.shutil, "which", lambda name: "/nix/var/nix/profiles/default/bin/nix" if name == "nix" else None)
    prefix, command = platform_support.podman_install_command()
    assert prefix == []
    assert command == ["nix", "profile", "install", "nixpkgs#podman"]
