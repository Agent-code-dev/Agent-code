from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
SOURCE = AGENT.read_text(encoding="utf-8")


def test_podman_uses_lightweight_alpine_and_bash():
    assert '"alpine": {"label": "Alpine Linux (lightweight)", "image": "docker.io/library/alpine:3.22"' in SOURCE
    assert '"bash", "-lc", command' in SOURCE
    assert '"ubuntu": {"label": "Ubuntu 24.04 LTS", "image": "docker.io/library/ubuntu:24.04"' in SOURCE
    assert '"debian": {"label": "Debian 13", "image": "docker.io/library/debian:trixie-slim"' in SOURCE
    assert '"fedora": {"label": "Fedora", "image": "docker.io/library/fedora:latest"' in SOURCE
    assert '"--network", "bridge"' in SOURCE
    assert "apk update && apk add --no-cache bash git curl build-base" in SOURCE
    assert "apt-get install -y --no-install-recommends" in SOURCE
    assert "dnf -y install" in SOURCE
    # Alpine's build-base meta-package includes gcc, g++, make and libc headers.
    assert "build-base" in SOURCE
    assert 'return f"agent-code-{os_id}-sandbox-{digest}"' in SOURCE
    assert "host.containers.internal" in SOURCE


def test_podman_commands_are_dispatched_before_host_restrictions():
    start = SOURCE.index("def tool_shell_run(")
    end = SOURCE.index("def tool_background_shell(", start)
    shell_source = SOURCE[start:end]
    assert shell_source.index('get("podman_sandbox_enabled", False)') < shell_source.index("for pat in HIGH_RISK_PATTERNS")
    assert "shell operators are disabled" in shell_source


def test_background_commands_use_full_bash_in_container():
    start = SOURCE.index("def tool_background_shell(")
    end = SOURCE.index("# Web research search", start)
    bg_source = SOURCE[start:end]
    assert 'get("podman_sandbox_enabled", False)' in bg_source
    assert '"bash", "-lc", command' in bg_source


def test_agent_prompt_identifies_alpine_sandbox_and_network():
    assert "SANDBOX ENVIRONMENT:" in SOURCE
    assert "PODMAN_OS_IMAGES" in SOURCE
    assert "Podman bridge networking" in SOURCE
    assert "CORE_MINI_PROMPT" in SOURCE


def test_podman_host_loopback_urls_are_routed_to_host_gateway():
    assert "host.containers.internal" in SOURCE
    assert "def _podman_host_url_command" in SOURCE
    assert "https?://" in SOURCE
    assert "127\\.0\\.0\\.1" in SOURCE


def test_podman_takes_precedence_even_when_unrestricted_mode_is_enabled():
    start = SOURCE.index("def tool_shell_run(")
    end = SOURCE.index("def tool_background_shell(", start)
    shell_source = SOURCE[start:end]
    assert shell_source.index('get("podman_sandbox_enabled", False)') < shell_source.index('get("allow_unrestricted_host_shell", False)')
