from agent_code.tui import TUI


def test_legacy_settings_center_exposes_core_configuration():
    tui = TUI.__new__(TUI)
    tui.cfg = {
        "provider_name": "OpenAI",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-5",
        "openai_api_keys": ["secret-a", "secret-b"],
        "execution_mode": "max",
        "permission_mode": "ask",
        "thinking_effort": "high",
        "podman_sandbox_enabled": True,
        "podman_container_name": "project-box",
        "show_activity_details": False,
        "desktop_ui": "webview",
    }
    rows = tui._settings_rows()
    values = {key: value for key, _label, value, _hint in rows}
    assert values["provider"] == "OpenAI"
    assert values["model"] == "gpt-5"
    assert values["key"] == "2 key(s) configured"
    assert values["mode"] == "MAX"
    assert values["thinking"] == "HIGH"
    assert values["container"] == "project-box"
    assert values["activity"] == "Compact"


def test_legacy_settings_never_display_api_key_values():
    tui = TUI.__new__(TUI)
    tui.cfg = {"openai_api_keys": ["do-not-display-this"]}
    assert "do-not-display-this" not in repr(tui._settings_rows())


def test_legacy_settings_thinking_selection_is_available():
    tui = TUI.__new__(TUI)
    tui.cfg = {"thinking_effort": "off"}
    rows = {key: (label, value, hint) for key, label, value, hint in tui._settings_rows()}
    assert rows["thinking"][1] == "OFF"
    assert "Low, Medium, or High" in rows["thinking"][2]


def test_legacy_tui_has_separate_addon_store_navigation():
    from pathlib import Path
    source = Path(__file__).parents[1] / "src" / "agent_code" / "tui.py"
    text = source.read_text(encoding="utf-8")
    assert '"Add-on Store"' in text
    assert 'self.page=="Add-on Store"' in text
    assert 'self.manage_addon("store")' in text


def test_legacy_tui_initializes_event_queue_before_ask_user_broker():
    from pathlib import Path
    source = Path(__file__).parents[1] / "src" / "agent_code" / "tui.py"
    text = source.read_text(encoding="utf-8")
    init = text.split("def __init__(self, screen):", 1)[1].split("def safe_add", 1)[0]
    assert init.index("self.events=queue.Queue()") < init.index("AskUserBroker(")


def test_legacy_tui_reasoning_effort_is_forwarded_to_model_protocol():
    from pathlib import Path
    source = Path(__file__).parents[1] / "src" / "agent_code" / "tui.py"
    text = source.read_text(encoding="utf-8")
    assert text.count('thinking_effort=self.cfg.get("thinking_effort", "off")') >= 2


def test_legacy_tui_keyboard_interrupt_requests_worker_shutdown():
    import threading

    tui = TUI.__new__(TUI)
    tui.running = True
    tui.cancel_event = threading.Event()

    class Broker:
        cancelled = False
        def cancel_all(self):
            self.cancelled = True

    tui.ask_user_broker = Broker()
    def interrupted(_pages):
        raise KeyboardInterrupt
    tui._run_loop = interrupted
    tui.run()
    assert tui.running is False
    assert tui.cancel_event.is_set()
    assert tui.ask_user_broker.cancelled is True
