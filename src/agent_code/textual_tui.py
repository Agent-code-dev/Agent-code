"""Modern Textual terminal workspace for Agent Code.

The existing agent execution engine is reused through a small state facade; this
module owns presentation, navigation, settings forms, and terminal interaction.
"""
from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, RichLog, Select,
    Static, TabbedContent, TabPane,
)
from .interactive import AskUserBroker

from . import __version__, paths
from .tui import PROVIDERS, TUI, read_config, write_config, api_keys

PAGES = ("Chat", "Workspace", "Activity", "Skills", "MCP", "Settings", "Add-ons", "Add-on Store", "Help")
PAGE_IDS = {name: ("addons" if name == "Add-ons" else "addon_store" if name == "Add-on Store" else name.lower().replace("-", "_")) for name in PAGES}

CSS = """
/* Restrained graphite interface: neutral surfaces, quiet borders, one muted accent. */
Screen { background: #111315; color: #e5e7e9; }
Header { background: #191c1f; color: #e5e7e9; }
Footer { background: #191c1f; color: #a4abb2; }
#shell { height: 1fr; }
#sidebar { width: 23; min-width: 19; background: #191c1f; border-right: tall #30353a; padding: 1; }
#brand { height: 3; color: #d7dde2; text-style: bold; content-align: left middle; }
.nav-button { width: 100%; height: 3; margin: 0 0 1 0; background: #202428; border: none; color: #c4cbd1; content-align: left middle; }
.nav-button:hover { background: #2a3035; color: #f1f3f4; }
.nav-button:focus { border-left: thick #8b9aa6; background: #2b333a; }
#side-meta { color: #929ba3; height: auto; margin-top: 1; }
#main { width: 1fr; padding: 1 2; }
#topline { height: 3; }
#search { width: 1fr; border: round #3a4249; background: #1b1f23; }
#status { width: 38; color: #a3adb5; content-align: right middle; }
TabbedContent { height: 1fr; min-height: 0; }
TabPane { padding: 1 0; height: 1fr; min-height: 0; }
#settings { height: 1fr; min-height: 0; }
#settings-tabs { height: 1fr; min-height: 0; }
#settings-tabs TabPane { height: 1fr; min-height: 0; }
#settings-tabs VerticalScroll { height: 1fr; min-height: 0; overflow-y: scroll; }
#settings-tabs VerticalScroll.card { height: 1fr; min-height: 0; }
.section-title { color: #cbd3d9; text-style: bold; margin: 0 0 1 0; }
.muted { color: #929ba3; }
.card { background: #1b1f23; border: round #30373d; padding: 1 2; margin: 0 0 1 0; height: auto; }
.field-label { color: #b9c1c7; margin: 1 0 0 0; }
Input, Select { background: #15191c; border: round #3a4249; }
Button { background: #292f34; border: round #414a51; color: #e1e5e8; }
Button:hover { background: #343c42; }
Button.primary { background: #46545e; border: round #687984; color: #ffffff; text-style: bold; }
Button.danger { background: #493638; border: round #76575a; }
#chat-log, #activity-log { height: 1fr; background: #15191c; border: round #30373d; padding: 1; }
#composer { height: auto; margin-top: 1; }
#message { width: 1fr; }
#settings-tabs { height: 1fr; }
#save-row { height: 3; margin-top: 1; }
#settings-search-row { height: 3; min-height: 3; margin-bottom: 1; align: left middle; }
#settings_search { width: 1fr; height: 3; }
#search-results { width: 2fr; height: 3; min-height: 3; color: #a4adb4; content-align: left middle; padding: 0 1; }
.hidden { display: none; }
"""


class AgentQuestionScreen(ModalScreen[dict | None]):
    """Small, keyboard-friendly modal for agent clarification requests."""
    CSS = """
    AgentQuestionScreen { align: center middle; background: #0008; }
    #question-dialog { width: 72; max-width: 90%; height: auto; max-height: 80%; padding: 1 2; border: round #687984; background: #1b1f23; }
    #question-title { color: #cbd3d9; text-style: bold; margin-bottom: 1; }
    #question-prompt { height: auto; margin-bottom: 1; }
    #question-choice { margin-bottom: 1; }
    #question-answer { margin-bottom: 1; }
    #question-buttons { height: 3; align-horizontal: right; }
    """
    def __init__(self, question: dict):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal, Vertical
        q = self.question
        with Vertical(id="question-dialog"):
            yield Label(str(q.get("title") or "Agent Code needs your input"), id="question-title")
            yield Static(str(q.get("prompt") or "Please clarify the task."), id="question-prompt")
            options = [(str(x), str(x)) for x in q.get("options", [])]
            if options:
                yield Select(options, prompt="Choose an option", allow_blank=True, id="question-choice")
            if q.get("allow_custom", True):
                yield Input(placeholder="Or type your own answer…", id="question-answer")
            with Horizontal(id="question-buttons"):
                if q.get("allow_skip", True):
                    yield Button("Skip", id="question-skip")
                yield Button("Submit", id="question-submit", classes="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "question-skip":
            self.dismiss({"skip": True})
        elif event.button.id == "question-submit":
            try:
                choice = self.query_one("#question-choice", Select).value
            except Exception:
                choice = None
            try:
                custom = self.query_one("#question-answer", Input).value.strip()
            except Exception:
                custom = ""
            self.dismiss({"choice": None if choice is Select.BLANK else choice,
                          "custom_text": custom or None, "skip": False})


class AgentCodeTUI(App[None]):
    TITLE = f"Agent Code {__version__}"
    SUB_TITLE = "Autonomous terminal workspace"
    CSS = CSS
    BINDINGS = [
        ("ctrl+p", "command_palette", "Commands"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+enter", "send_message", "Send task"),
        ("f5", "stop_task", "Stop"),
        (("ctrl+1"), "show_chat", "Chat"),
        ("ctrl+2", "show_workspace", "Workspace"),
        ("ctrl+3", "show_activity", "Activity"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg = read_config()
        self.engine = TUI.__new__(TUI)
        self.engine.cfg = self.cfg
        self.engine.messages = []
        self.engine.mode = {"plan": "Plan", "build": "Build", "max": "Max"}.get(str(self.cfg.get("execution_mode", "build")).lower(), "Build")
        self.engine.cancel_event = threading.Event()
        self.engine.events = queue.Queue()
        self.engine.ask_user_broker = AskUserBroker(on_question=lambda event: self.engine.events.put(("ask_user", event)))
        self.engine.activity = ["Agent Code ready. Submit a task to begin."]
        self.engine.tool_details = []
        self.engine.stream_text = ""
        self.engine.notice = "Ready"
        self.engine.busy = False
        self._last_messages_snapshot = None
        self._last_activity_snapshot = None
        self._search_matches: list[str] = []
        self._settings_scroll_ready = False
        self._question_active = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="shell"):
            with Vertical(id="sidebar"):
                yield Label("◆ AGENT CODE", id="brand")
                yield Label(f"v{__version__}  ·  WORKSPACE", classes="muted")
                for page in PAGES:
                    yield Button(page, id=f"nav_{PAGE_IDS[page]}", classes="nav-button")
                yield Static("\nMODE\nBuild\n\nCtrl+P  Command palette\nCtrl+Q  Quit", id="side-meta")
            with Vertical(id="main"):
                with Horizontal(id="topline"):
                    yield Input(placeholder="Search pages, settings, commands…  (Ctrl+P for actions)", id="search")
                    yield Static("● Ready", id="status")
                with TabbedContent(initial="chat", id="pages"):
                    with TabPane("Chat", id="chat"):
                        yield Label("CHAT / AUTONOMOUS AGENT", classes="section-title")
                        yield RichLog(id="chat-log", wrap=True, markup=True, auto_scroll=False)
                        with Horizontal(id="composer"):
                            yield Input(placeholder="Describe a task…", id="message")
                            yield Button("Send", id="send", classes="primary")
                            yield Button("Stop", id="stop", classes="danger", disabled=True)
                    with TabPane("Workspace", id="workspace"):
                        yield Label("WORKSPACE EXPLORER", classes="section-title")
                        yield Static("", id="workspace-list", classes="card")
                    with TabPane("Activity", id="activity"):
                        yield Label("LIVE TRAJECTORY · TOOL ACTIVITY", classes="section-title")
                        yield RichLog(id="activity-log", wrap=True, markup=True, auto_scroll=False)
                    with TabPane("Skills", id="skills"):
                        yield Label("NATIVE AND CLAUDE-COMPATIBLE SKILLS", classes="section-title")
                        yield Static("", id="skills-list", classes="card")
                        with Horizontal():
                            yield Input(placeholder="Exact skill name", id="skill_toggle_name")
                            yield Select([("Enable", "enable"), ("Disable", "disable")], value="disable", id="skill_toggle_action", allow_blank=False)
                            yield Button("Apply", id="toggle_skill")
                    with TabPane("MCP", id="mcp"):
                        yield Label("REMOTE MCP CONNECTIONS", classes="section-title")
                        yield Static("", id="mcp-list", classes="card")
                        yield Label("MCP server credentials remain in the existing protected configuration flow.", classes="muted")
                    with TabPane("Settings", id="settings"):
                        yield Label("SETTINGS CENTER", classes="section-title")
                        with Horizontal(id="settings-search-row"):
                            yield Input(placeholder="Filter settings…", id="settings_search")
                            yield Static("All settings", id="search-results")
                        with TabbedContent(initial="provider", id="settings-tabs"):
                            with TabPane("Provider & Models", id="provider"):
                                with VerticalScroll(classes="card"):
                                    yield Label("Provider", classes="field-label")
                                    yield Select([(x, x) for x in PROVIDERS], id="provider_name", allow_blank=False)
                                    yield Label("Base URL", classes="field-label")
                                    yield Input(placeholder="https://api.example.com/v1", id="base_url")
                                    yield Label("Model ID", classes="field-label")
                                    yield Input(placeholder="provider/model-name", id="model_id")
                                    yield Label("API key · stored in OS credential vault", classes="field-label")
                                    yield Input(placeholder="Leave empty to keep the current key", password=True, id="api_key")
                                    yield Button("Save provider settings", id="save_provider", classes="primary")
                            with TabPane("Execution", id="execution"):
                                with VerticalScroll(classes="card"):
                                    yield Label("Execution mode", classes="field-label")
                                    yield Select([("Plan Mode · read-only", "plan"), ("Build Mode", "build"), ("Max Mode · best-result focus", "max")], value=str(self.cfg.get("execution_mode", "build")), id="execution_mode", allow_blank=False)
                                    yield Label("Permission mode", classes="field-label")
                                    yield Select([("Ask before changes", "ask"), ("Workspace auto-approve", "auto"), ("Read-only", "readonly")], id="permission", allow_blank=False)
                                    yield Checkbox("Show detailed tool activity", value=bool(self.cfg.get("show_activity_details", True)), id="activity_details")
                                    yield Checkbox("Enable Podman sandbox", value=bool(self.cfg.get("podman_sandbox_enabled", False)), id="podman_enabled")
                                    yield Label("Container operating system", classes="field-label")
                                    yield Select([("Alpine Linux · lightweight", "alpine"), ("Ubuntu 24.04 LTS", "ubuntu"), ("Debian 13", "debian"), ("Fedora", "fedora")], value=str(self.cfg.get("podman_os", "alpine")), id="podman_os", allow_blank=False)
                                    yield Checkbox("Allow network access from sandbox", value=bool(self.cfg.get("podman_network_enabled", True)), id="podman_network")
                                    yield Label("Workspace mount permissions", classes="field-label")
                                    yield Select([("Read and write", "read-write"), ("Read only", "read-only")], value=str(self.cfg.get("podman_workspace_access", "read-write")), id="podman_workspace_access", allow_blank=False)
                                    yield Label("Memory limit (MB)", classes="field-label")
                                    yield Input(value=str(self.cfg.get("podman_memory_mb", 2048)), id="podman_memory", type="integer")
                                    yield Label("CPU limit", classes="field-label")
                                    yield Input(value=str(self.cfg.get("podman_cpu_limit", 2.0)), id="podman_cpu", type="number")
                                    yield Label("Maximum processes", classes="field-label")
                                    yield Input(value=str(self.cfg.get("podman_pids_limit", 256)), id="podman_pids", type="integer")
                                    yield Static("Host services are reachable from the container as http://host.containers.internal:<port>. Host-loopback URLs in shell commands are translated automatically.", classes="muted")
                                    yield Checkbox("ULTRA UNRESTRICTED — automatic approval for all tools and host access", value=bool(self.cfg.get("ultra_unrestricted_enabled", False)), id="ultra_unrestricted")
                                    yield Static("DANGER: may modify or delete files outside the workspace. Uses current OS account rights only; cannot bypass sudo/UAC or active blacklist rules. Disable to restore normal approvals.", classes="muted")
                                    yield Button("Save execution settings", id="save_execution", classes="primary")
                            with TabPane("Connections", id="connections"):
                                with VerticalScroll(classes="card"):
                                    yield Label("Skills & Add-on Store server (HTTPS)", classes="field-label")
                                    yield Input(placeholder="https://skills-manager.freesrv.com", id="store_server")
                                    yield Button("Save store server", id="save_store_server", classes="primary")
                                    yield Label("Configured MCP servers", classes="field-label")
                                    yield Static("Manage server definitions from the desktop Settings → Remote MCP panel. This view is intentionally read-only to avoid corrupting nested authentication data.", classes="muted")
                                    yield Label("SSH connection", classes="field-label")
                                    ssh = self.cfg.get("ssh_connection", {})
                                    yield Static(str(ssh.get("command") or ssh.get("host") or "Not configured"), id="ssh_status")
                            with TabPane("Appearance", id="appearance"):
                                with VerticalScroll(classes="card"):
                                    yield Label("Desktop interface: CustomTkinter. The authenticated WebUI is available through `agent-code server`.", classes="muted")
                                    yield Label("Terminal UI remains available independently with `agent-code tui`.", classes="muted")
                                    yield Label("Terminal theme", classes="field-label")
                                    yield Select([(x.replace("-", " ").title(), x) for x in ("textual-dark", "nord", "gruvbox", "dracula", "tokyo-night", "catppuccin-mocha", "monokai", "solarized-dark")], value="nord", id="theme", allow_blank=False)
                                    yield Button("Apply theme", id="apply_theme", classes="primary")
                    with TabPane("Add-ons", id="addons"):
                        yield Label("APPLICATION ADD-ONS", classes="section-title")
                        yield Static("", id="addons-list", classes="card")
                        yield Label("ADD-ON STORE", classes="section-title")
                        yield Input(placeholder="Search add-ons…", id="addon_store_search")
                        with Horizontal():
                            yield Button("Browse store", id="browse_addon_store", classes="primary")
                            yield Input(placeholder="Exact add-on name to install", id="addon_install_name")
                            yield Button("Install", id="install_addon_store")
                        yield Static("Store catalogue has not been loaded.", id="addon_store_results", classes="card")
                    with TabPane("Add-on Store", id="addon_store"):
                        yield Label("COMMUNITY ADD-ON CATALOGUE", classes="section-title")
                        yield Input(placeholder="Search add-ons…", id="addon_store_search_main")
                        with Horizontal():
                            yield Button("Search catalogue", id="browse_addon_store_main", classes="primary")
                            yield Button("Refresh", id="refresh_addon_store")
                        yield Static("Select Search catalogue to load available add-ons.", id="addon_store_results_main", classes="card")
                        yield Input(placeholder="Exact add-on name to install", id="addon_install_name_main")
                        yield Button("Install selected add-on", id="install_addon_store_main")
                    with TabPane("Help", id="help"):
                        yield Label("KEYBOARD SHORTCUTS & HELP", classes="section-title")
                        yield Static("Ctrl+P  Open command palette\nCtrl+Enter  Send task\nF5  Stop task\nCtrl+1/2/3  Chat / Workspace / Activity\nTab navigation is clickable; use arrow keys to move between tabs.\n\nPlan mode is read-only. Build mode can modify files within the configured workspace. Review permission settings before running tasks.", classes="card")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = str(self.cfg.get("tui_theme", "nord"))
        self._populate_settings()
        self._refresh_live_panels()
        self.set_interval(0.35, self._poll_engine)

    def _ensure_settings_scroll_layout(self) -> None:
        """Reassert scroll viewport sizing after Textual computes tab layouts."""
        if not self.is_mounted:
            return
        for pane_id in ("provider", "execution", "connections", "appearance"):
            try:
                pane = self.query_one(f"#{pane_id}", TabPane)
                pane.styles.height = "1fr"
                pane.styles.min_height = 0
                scroll = pane.query_one(VerticalScroll)
                scroll.styles.height = "1fr"
                scroll.styles.min_height = 0
                scroll.styles.overflow_y = "scroll"
            except Exception as exc:
                self.log.warning("Settings scroll layout unavailable for %s: %s", pane_id, exc)

    def _populate_settings(self) -> None:
        provider = str(self.cfg.get("provider_name", "OpenAI"))
        self.query_one("#provider_name", Select).value = provider if provider in PROVIDERS else "OpenAI"
        self.query_one("#base_url", Input).value = str(self.cfg.get("openai_base_url") or PROVIDERS.get(provider, ""))
        self.query_one("#model_id", Input).value = str(self.cfg.get("openai_model", ""))
        self.query_one("#store_server", Input).value = str(self.cfg.get("skill_store_server", "https://skills-manager.freesrv.com"))
        permission = str(self.cfg.get("permission_mode", self.cfg.get("permission", "ask")))
        self.query_one("#permission", Select).value = permission if permission in ("ask", "auto", "readonly") else "ask"
        mode = str(self.cfg.get("execution_mode", "build"))
        self.query_one("#execution_mode", Select).value = mode if mode in ("plan", "build", "max") else "build"
        self.query_one("#status", Static).update("● " + ("Configured" if api_keys(self.cfg) or provider == "Vireonix Free" else "API key needed"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("nav_"):
            page = bid[4:]
            self.query_one("#pages", TabbedContent).active = page
            self._refresh_static_page(page)
        elif bid == "toggle_skill":
            self._toggle_skill_setting(self.query_one("#skill_toggle_name", Input).value.strip(),
                                       str(self.query_one("#skill_toggle_action", Select).value))
        elif bid in ("browse_addon_store", "browse_addon_store_main", "refresh_addon_store"):
            search_id = "#addon_store_search_main" if bid != "browse_addon_store" else "#addon_store_search"
            self._browse_addon_store(self.query_one(search_id, Input).value.strip())
        elif bid in ("install_addon_store", "install_addon_store_main"):
            name_id = "#addon_install_name_main" if bid.endswith("_main") else "#addon_install_name"
            self._install_addon_from_store(self.query_one(name_id, Input).value.strip())
        elif bid == "send":
            self.action_send_message()
        elif bid == "stop":
            self.engine.cancel_event.set()
            self.engine.notice = "Stopping…"
        elif bid == "save_provider":
            self._save_provider()
        elif bid == "save_execution":
            self._save_execution()
        elif bid == "save_store_server":
            self._save_store_server()
        elif bid == "apply_theme":
            theme = str(self.query_one("#theme", Select).value)
            # Textual's built-in themes are a separate registry; custom labels
            # are stored as preferences without crashing the running UI.
            available = getattr(self, "available_themes", {})
            if theme in available:
                self.theme = theme
            else:
                self.notify(f"Theme '{theme}' is saved as a preference; this Textual version does not provide it as a built-in theme.", severity="warning")
            self.cfg["tui_theme"] = theme
            self._persist_config()
        elif bid == "settings_search":
            return

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "message":
            self.action_send_message()
        elif event.input.id == "search":
            query = event.value.strip().lower()
            if query:
                mapping = {"chat": "chat", "workspace": "workspace", "activity": "activity", "skills": "skills", "mcp": "mcp", "settings": "settings", "addons": "addons", "add-ons": "addons", "help": "help"}
                for key, page in mapping.items():
                    if key in query:
                        self.query_one("#pages", TabbedContent).active = page
                        break

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider_name" and event.value is not Select.BLANK:
            provider = str(event.value)
            self.query_one("#base_url", Input).value = PROVIDERS.get(provider, "")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "settings_search":
            q = event.value.strip().lower()
            entries = {
                "Provider & Models": "provider base url model id api key credentials",
                "Execution": "permission mode ask before changes read only podman sandbox activity",
                "Connections": "mcp ssh remote servers authentication skills store addon store server url",
                "Appearance": "theme nord gruvbox dracula tokyo night colors",
            }
            matches = [name for name, words in entries.items() if not q or q in name.lower() or q in words]
            self.query_one("#search-results", Static).update("Matches: " + (" · ".join(matches) if matches else "No matching settings"))

    def _persist_config(self) -> None:
        try:
            write_config(self.cfg)
            self.engine.cfg = self.cfg
            self.query_one("#status", Static).update("✓ Settings saved")
        except Exception as exc:
            self.notify(f"Could not save settings: {exc}", severity="error")

    def _save_provider(self) -> None:
        provider = str(self.query_one("#provider_name", Select).value)
        base = self.query_one("#base_url", Input).value.strip()
        model = self.query_one("#model_id", Input).value.strip()
        key = self.query_one("#api_key", Input).value.strip()
        if not base.startswith(("http://", "https://")):
            self.notify("Base URL must start with http:// or https://", severity="error")
            return
        if not model:
            self.notify("Enter a model ID before saving.", severity="warning")
            return
        if not key and not api_keys(self.cfg) and provider != "Vireonix Free":
            self.notify("Add an API key, or choose a provider that does not require one.", severity="warning")
            return
        self.cfg.update(provider_name=provider, openai_base_url=base, openai_model=model)
        if key:
            self.cfg["openai_api_keys"] = [key]
        try:
            self._persist_config()
            self.query_one("#api_key", Input).value = ""
            self.notify("Provider configuration saved.", severity="information")
        except Exception as exc:
            self.notify(f"Credential save failed: {exc}", severity="error")

    def _save_store_server(self) -> None:
        server = self.query_one("#store_server", Input).value.strip().rstrip("/")
        if not server.startswith("https://"):
            self.notify("Store server must use HTTPS.", severity="error")
            return
        self.cfg["skill_store_server"] = server
        self._persist_config()
        self.notify("Skills and Add-on Store server saved.")

    def _save_execution(self) -> None:
        ultra = bool(self.query_one("#ultra_unrestricted", Checkbox).value)
        if ultra and not bool(self.cfg.get("ultra_unrestricted_enabled", False)):
            from textual.widgets import Confirm
            approved = self.push_screen_wait(Confirm("Enable Ultra Unrestricted Agent Code? It removes per-action approvals and allows host commands/tools to affect files outside the workspace using your current OS account rights. This may cause data loss. It cannot bypass sudo/UAC or blacklist rules."))
            if not approved:
                self.query_one("#ultra_unrestricted", Checkbox).value = False
                return
        selected_mode = str(self.query_one("#execution_mode", Select).value)
        if selected_mode not in ("plan", "build", "max"):
            selected_mode = "build"
        self.cfg["execution_mode"] = selected_mode
        self.engine.mode = {"plan": "Plan", "build": "Build", "max": "Max"}[selected_mode]
        self.cfg["ultra_unrestricted_enabled"] = ultra
        self.cfg["allow_unrestricted_host_shell"] = bool(self.cfg.get("allow_unrestricted_host_shell", False) or ultra)
        self.cfg["permission_mode"] = "auto" if ultra else str(self.query_one("#permission", Select).value)
        self.cfg["show_activity_details"] = self.query_one("#activity_details", Checkbox).value
        self.cfg["podman_sandbox_enabled"] = self.query_one("#podman_enabled", Checkbox).value
        self.cfg["podman_os"] = str(self.query_one("#podman_os", Select).value or "alpine")
        self.cfg["podman_network_enabled"] = self.query_one("#podman_network", Checkbox).value
        self.cfg["podman_workspace_access"] = str(self.query_one("#podman_workspace_access", Select).value or "read-write")
        try:
            self.cfg["podman_memory_mb"] = max(256, min(16384, int(self.query_one("#podman_memory", Input).value or 2048)))
            self.cfg["podman_cpu_limit"] = max(0.25, min(16.0, float(self.query_one("#podman_cpu", Input).value or 2)))
            self.cfg["podman_pids_limit"] = max(64, min(4096, int(self.query_one("#podman_pids", Input).value or 256)))
        except ValueError:
            self.notify("Sandbox resource limits must be valid numbers.", severity="error")
            return
        self._persist_config()
        self.engine.permission = "auto" if ultra else self.cfg["permission_mode"]
        self.engine.allow_unrestricted_host_shell = bool(self.cfg.get("allow_unrestricted_host_shell", False))
        self.engine.ultra_unrestricted_enabled = ultra
        self.notify("Execution settings saved.")

    def action_send_message(self) -> None:
        box = self.query_one("#message", Input)
        prompt = box.value.strip()
        if not prompt:
            return
        if self.engine.busy:
            self.notify("An agent task is already running.", severity="warning")
            return
        box.value = ""
        self.engine.mode = {"plan": "Plan", "build": "Build", "max": "Max"}.get(str(self.cfg.get("execution_mode", "build")).lower(), "Build")
        self.engine.cancel_event.clear()
        self.engine.busy = True
        self.engine.messages.append(("user", prompt))
        self.engine.activity.append("Task started: " + prompt[:180])
        self.query_one("#stop", Button).disabled = False
        self.query_one("#status", Static).update("◌ Working…")
        self._refresh_live_panels()
        self._run_agent(prompt)

    @work(thread=True, exclusive=True)
    def _run_agent(self, prompt: str) -> None:
        try:
            self.engine.answer(prompt)
        except Exception as exc:
            self.engine.messages.append(("assistant", f"Request failed: {type(exc).__name__}: {exc}"))
            self.engine.activity.append(f"Task failed: {type(exc).__name__}: {exc}")
        finally:
            # Early exits (for example, missing provider credentials) must not
            # leave the terminal permanently stuck in its busy state.
            self.engine.busy = False
            self.engine.notice = "Ready"

    def action_stop_task(self) -> None:
        if self.engine.busy:
            self.engine.cancel_event.set()
            self.engine.notice = "Stopping…"

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane_id = getattr(event.tab, "id", "")
        if pane_id:
            self._refresh_static_page(str(pane_id))

    def _poll_engine(self) -> None:
        if not self.is_mounted:
            return
        self._refresh_live_panels()
        self._drain_engine_events()
        if self.engine.busy:
            self.query_one("#status", Static).update("◌ Working…")
            self.query_one("#stop", Button).disabled = False
        else:
            self.query_one("#status", Static).update("● " + str(self.engine.notice or "Ready"))
            self.query_one("#stop", Button).disabled = True

    def _drain_engine_events(self) -> None:
        """Move worker-thread questions onto the Textual event loop."""
        if self._question_active:
            return
        try:
            kind, payload = self.engine.events.get_nowait()
        except queue.Empty:
            return
        if kind != "ask_user":
            return
        question = payload.get("question", {}) if isinstance(payload, dict) else {}
        if not question:
            return
        self._question_active = True
        self.push_screen(AgentQuestionScreen(question),
                         callback=lambda answer, qid=question.get("question_id"): self._answer_agent_question(qid, answer))

    def _answer_agent_question(self, question_id: str, answer: dict | None) -> None:
        self._question_active = False
        answer = answer or {"skip": True}
        try:
            self.engine.ask_user_broker.answer_question(
                str(question_id), choice=answer.get("choice"),
                custom_text=answer.get("custom_text"), skip=bool(answer.get("skip")))
        except Exception as exc:
            self.notify(f"Could not submit answer: {exc}", severity="error")

    def _refresh_live_panels(self) -> None:
        """Refresh only live logs; never rescan the filesystem on the UI timer."""
        chat = self.query_one("#chat-log", RichLog)
        snapshot = tuple((role, TUI._chat_text(body)) for role, body in self.engine.messages)
        previous = self._last_messages_snapshot or ()
        if snapshot != previous:
            chat_was_at_bottom = chat.scroll_y >= max(0, chat.max_scroll_y - 1)
            # Append only new messages or streamed suffixes. Rebuilding the whole
            # transcript for every token would make long sessions progressively slow.
            prefix_unchanged = len(snapshot) >= len(previous) and snapshot[:len(previous)] == previous
            if prefix_unchanged:
                for role, body in snapshot[len(previous):]:
                    label = "YOU" if role == "user" else "AGENT" if role == "assistant" else "TOOL"
                    color = "#c2cbd1" if role == "user" else "#aebbb2" if role == "assistant" else "#a9a49a"
                    chat.write(f"[{color}]{label}[/]  {body}")
            elif (previous and snapshot and len(snapshot) == len(previous)
                  and snapshot[:-1] == previous[:-1]
                  and snapshot[-1][0] == previous[-1][0]
                  and snapshot[-1][1].startswith(previous[-1][1])):
                chat.write(snapshot[-1][1][len(previous[-1][1]):])
            else:
                chat.clear()
                for role, body in snapshot:
                    label = "YOU" if role == "user" else "AGENT" if role == "assistant" else "TOOL"
                    color = "#c2cbd1" if role == "user" else "#aebbb2" if role == "assistant" else "#a9a49a"
                    chat.write(f"[{color}]{label}[/]  {body}")
            self._last_messages_snapshot = snapshot
            if chat_was_at_bottom:
                chat.call_after_refresh(chat.scroll_end, animate=False)
        activity = self.query_one("#activity-log", RichLog)
        activity_snapshot = tuple(self.engine.activity[-300:])
        previous_activity = self._last_activity_snapshot or ()
        if activity_snapshot != previous_activity:
            activity_was_at_bottom = activity.scroll_y >= max(0, activity.max_scroll_y - 1)
            # Preserve the user's scroll position: clearing/rebuilding RichLog on
            # every poll forcibly jumps the viewport and makes wheel scrolling unusable.
            if (len(activity_snapshot) >= len(previous_activity)
                    and activity_snapshot[:len(previous_activity)] == previous_activity):
                start = len(previous_activity)
                for index, item in enumerate(activity_snapshot[start:], start + 1):
                    activity.write(f"[dim]{index:03d}[/]  {item}")
            else:
                activity.clear()
                for index, item in enumerate(activity_snapshot, 1):
                    activity.write(f"[dim]{index:03d}[/]  {item}")
            self._last_activity_snapshot = activity_snapshot
            if activity_was_at_bottom:
                activity.call_after_refresh(activity.scroll_end, animate=False)

    def _refresh_static_page(self, page: str) -> None:
        """Load a page's filesystem/config data only when the user opens it."""
        if page == "workspace":
            self.query_one("#workspace-list", Static).update(self._workspace_summary())
        elif page == "skills":
            self.query_one("#skills-list", Static).update(self._skills_summary())
        elif page == "mcp":
            self.query_one("#mcp-list", Static).update(self._mcp_summary())
        elif page == "addons":
            self.query_one("#addons-list", Static).update(self._addons_summary())
        elif page == "addon_store":
            self._browse_addon_store(self.query_one("#addon_store_search_main", Input).value.strip())

    @staticmethod
    def _workspace_summary() -> str:
        root = paths.project_workspace_dir()
        try:
            items = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:100]
        except OSError as exc:
            return f"Workspace unavailable: {exc}"
        return f"{root}\n\n" + ("\n".join(("📁 " if p.is_dir() else "   ") + p.name for p in items) if items else "(empty workspace)")

    def _toggle_skill_setting(self, name: str, action: str) -> None:
        if not name:
            self.notify("Enter an exact skill name.", severity="warning")
            return
        from .loader import discover_skills
        from .claude_skills import discover_claude_skills
        roots = [Path.cwd() / ".claude" / "skills", Path.home() / ".claude" / "skills", paths.global_skills_dir()]
        native_names = {x["name"] for x in discover_skills(paths.global_skills_dir())}
        claude_names = {x["name"] for x in discover_claude_skills(roots)}
        if name in native_names:
            key = name
        elif name in claude_names:
            key = "claude:" + name
        else:
            self.notify("Skill not found. Use the exact name shown above.", severity="error")
            return
        disabled = set(self.cfg.get("disabled_skills", []))
        if action == "enable":
            disabled.discard(key)
            disabled.discard(name)
        elif action == "disable":
            disabled.add(key)
        else:
            self.notify("Choose Enable or Disable.", severity="error")
            return
        self.cfg["disabled_skills"] = sorted(disabled)
        self._persist_config()
        self.query_one("#skills-list", Static).update(self._skills_summary())
        self.notify(f"Skill {name} {action}d; changes apply to the next task.")

    def _skills_summary(self) -> str:
        try:
            from .loader import discover_skills
            skills = discover_skills(paths.global_skills_dir())
            disabled = set(self.cfg.get("disabled_skills", []))
            lines = [f"{'●' if s['name'] not in disabled else '○'}  {s['name']}  —  {s.get('description', '')}" for s in skills]
            try:
                from .claude_skills import discover_claude_skills
                roots = [Path.cwd() / ".claude" / "skills", Path.home() / ".claude" / "skills", paths.global_skills_dir()]
                lines.extend(f"{'●' if 'claude:' + s['name'] not in disabled else '○'}  {s['name']}  —  Claude instruction skill" for s in discover_claude_skills(roots))
            except Exception:
                pass
            return "\n".join(lines) or "No skills installed."
        except Exception as exc:
            return f"Could not load skills: {exc}"

    def _mcp_summary(self) -> str:
        servers = self.cfg.get("mcp_servers", [])
        if not isinstance(servers, list) or not servers:
            return "No MCP servers configured. Add and authenticate servers from desktop Settings → Remote MCP."
        return "\n".join(f"{'●' if s.get('enabled', True) else '○'}  {s.get('name', s.get('id', 'unnamed'))}  {s.get('url', '')}" for s in servers)

    def _addons_summary(self) -> str:
        try:
            from .addons import AddonManager
            manager = AddonManager(paths.global_addons_dir(), self.cfg.get("disabled_addons", []))
            infos = manager.discover()
            return "\n".join(f"{'●' if item.enabled else '○'}  {item.name} v{item.version} — {item.error or item.description}" for item in infos) or "No add-ons installed."
        except Exception as exc:
            return f"Could not load add-ons: {exc}"

    @work(thread=True, exclusive=True)
    def _browse_addon_store(self, query: str = "") -> None:
        try:
            from .addon_store import AddonStoreClient
            server = str(self.cfg.get("skill_store_server", "https://skills-manager.freesrv.com"))
            items = AddonStoreClient(server).list_addons(query)
            self._addon_store_cache = {str(x.get("name")): x for x in items}
            lines = [f"{x.get('name')} v{x.get('version', '?')} — {x.get('description', '')}" for x in items]
            body = "\n".join(lines) if lines else "No add-ons found, or this server has no add-on catalogue."
        except Exception as exc:
            self._addon_store_cache = {}
            body = f"Store unavailable: {type(exc).__name__}: {exc}"
        self.call_from_thread(self._update_addon_store_results, body)

    def _update_addon_store_results(self, body: str) -> None:
        for selector in ("#addon_store_results", "#addon_store_results_main"):
            try:
                self.query_one(selector, Static).update(body)
            except Exception:
                pass

    @work(thread=True, exclusive=True)
    def _install_addon_from_store(self, name: str = "") -> None:
        if not name:
            self.notify("Enter an exact add-on name first.", severity="warning")
            return
        item = getattr(self, "_addon_store_cache", {}).get(name)
        if not item:
            self.notify("Browse the catalogue first and use an exact listed name.", severity="warning")
            return
        try:
            from .addon_store import AddonStoreClient
            addons_dir = paths.global_addons_dir()
            server = str(self.cfg.get("skill_store_server", "https://skills-manager.freesrv.com"))
            AddonStoreClient(server).install_addon(name, addons_dir,
                expected_sha256=str(item.get("sha256") or "") or None)
            self.call_from_thread(self._after_addon_installed, name)
        except Exception as exc:
            self.call_from_thread(self.notify, f"Add-on install failed: {exc}", severity="error")

    def _after_addon_installed(self, name: str) -> None:
        self.notify(f"Installed add-on: {name}")
        self.query_one("#addons-list", Static).update(self._addons_summary())

    def action_show_chat(self) -> None:
        self.query_one("#pages", TabbedContent).active = "chat"

    def action_show_workspace(self) -> None:
        self.query_one("#pages", TabbedContent).active = "workspace"

    def action_show_activity(self) -> None:
        self.query_one("#pages", TabbedContent).active = "activity"


def main() -> int:
    if not (os.isatty(0) and os.isatty(1)):
        print("Agent Code TUI requires an interactive terminal. Run: agent-code tui")
        return 2
    AgentCodeTUI().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
