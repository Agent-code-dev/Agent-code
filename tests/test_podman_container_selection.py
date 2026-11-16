from pathlib import Path

ROOT = Path(__file__).parents[1]
AGENT = (ROOT / "src/agent_code/agent.py").read_text(encoding="utf-8")
WEB = (ROOT / "src/agent_code/web_desktop.py").read_text(encoding="utf-8")
HTML = (ROOT / "src/agent_code/web_ui/index.html").read_text(encoding="utf-8")
JS = (ROOT / "src/agent_code/web_ui/app.js").read_text(encoding="utf-8")


def test_selected_container_is_configurable_with_managed_fallback():
    assert 'get("podman_container_name", "")' in AGENT
    assert "_podman_managed_container_name" in AGENT
    assert "return selected" in AGENT


def test_only_workspace_bound_read_write_containers_are_eligible():
    assert 'destination == "/workspace"' in AGENT
    assert "and rw" in AGENT
    assert "_podman_container_has_workspace" in AGENT
    assert "must mount this Agent Code workspace at /workspace" in AGENT


def test_web_api_lists_and_validates_container_selection():
    assert "def podman_status(self)" in WEB
    assert "def select_podman_container(self, name: str)" in WEB
    assert "_podman_list_workspace_containers" in WEB
    assert "not available for this workspace" in WEB


def test_webui_has_container_picker_and_actions():
    assert 'id="podmanContainerSelect"' in HTML
    assert 'id="podmanSelectContainer"' in HTML
    assert "select_podman_container" in JS
    assert "podmanRefresh" in JS and "podmanStart" in JS
