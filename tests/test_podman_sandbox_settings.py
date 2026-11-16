from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = (ROOT / "src/agent_code/agent.py").read_text(encoding="utf-8")
WEB = (ROOT / "src/agent_code/web_desktop.py").read_text(encoding="utf-8")
TEXTUAL = (ROOT / "src/agent_code/textual_tui.py").read_text(encoding="utf-8")
DESKTOP = (ROOT / "src/agent_code/agent.py").read_text(encoding="utf-8")
WEB_JS = (ROOT / "src/agent_code/web_ui/app.js").read_text(encoding="utf-8")


def test_network_can_be_disabled_for_managed_container():
    assert 'network_mode = "bridge" if network_enabled else "none"' in AGENT
    assert '"podman_network_enabled"' in WEB
    assert 'id="podman_network"' in TEXTUAL
    assert "podmanNetwork" in WEB_JS


def test_sandbox_resource_limits_are_configurable_and_bounded():
    assert '"--memory", f"{memory_mb}m", "--cpus", str(cpu_limit)' in AGENT
    assert '"--pids-limit", str(pids_limit)' in AGENT
    assert "podman_memory_mb" in WEB and "podman_cpu_limit" in WEB and "podman_pids_limit" in WEB
    assert 'id="podman_memory"' in TEXTUAL and 'id="podman_cpu"' in TEXTUAL and 'id="podman_pids"' in TEXTUAL


def test_workspace_can_be_mounted_read_only():
    assert "'rw' if workspace_mode == 'read-write' else 'ro'" in AGENT
    assert 'id="podman_workspace_access"' in TEXTUAL
    assert "podmanWorkspaceAccess" in WEB_JS


def test_customtkinter_exposes_sandbox_settings():
    assert "self.podman_network_var" in DESKTOP
    assert "self.podman_workspace_var" in DESKTOP
    assert "self.podman_memory_var" in DESKTOP
