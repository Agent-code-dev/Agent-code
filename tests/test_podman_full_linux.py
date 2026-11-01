from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "src" / "agent_code" / "agent.py"
SOURCE = AGENT.read_text(encoding="utf-8")


def test_podman_uses_lightweight_alpine_and_bash():
    assert 'image = "docker.io/library/alpine:3.22"' in SOURCE
    assert '"bash", "-lc", command' in SOURCE
    assert "https://dl-cdn.alpinelinux.org/alpine/v3.22/main" in SOURCE
    assert "https://dl-cdn.alpinelinux.org/alpine/v3.22/community" in SOURCE
    assert '"--network", "bridge"' in SOURCE
    assert "apk update" in SOURCE and "apk add --no-cache bash git curl build-base" in SOURCE
    assert "for attempt in 1 2 3" in SOURCE
    # Alpine's build-base meta-package includes gcc, g++, make and libc headers.
    assert "build-base" in SOURCE
    assert "agent-code-alpine-sandbox-" in SOURCE


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
    assert "Alpine Linux 3.22 (not Ubuntu)" in SOURCE
    assert "Podman bridge networking" in SOURCE
    assert "CORE_MINI_PROMPT" in SOURCE
