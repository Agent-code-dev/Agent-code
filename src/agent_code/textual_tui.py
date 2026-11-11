"""Modern Textual terminal workspace for Agent Code.

The existing agent execution engine is reused through a small state facade; this
module owns presentation, navigation, settings forms, and terminal interaction.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, RichLog, Select,
    Static, TabbedContent, TabPane,
)

from . import __version__, paths
from .tui import PROVIDERS, TUI, read_config, write_config, api_keys

PAGES = ("Chat", "Workspace", "Activity", "Skills", "MCP", "Settings", "Add-ons", "Help")
PAGE_IDS = {name: name.lower().replace("-", "_") for name in PAGES}

CSS = """
Screen { background: #0b1020; color: #e5eaf5; }
Header { background: #111a2e; color: #e5eaf5; }
Footer { background: #111a2e; color: #a8b4ca; }
#shell { height: 1fr; }
#sidebar { width: 23; min-width: 19; background: #111a2e; border-right: tall #273653; padding: 1; }
#brand { height: 3; color: #8bd5ff; text-style: bold; content-align: left middle; }
.nav-button { width: 100%; height: 3; margin: 0 0 1 0; background: #17233b; border: none; color: #c7d3e8; content-align: left middle; }
.nav-button:hover { background: #223455; color: #ffffff; }
.nav-button:focus { border-left: thick #58c7fa; background: #203653; }
#side-meta { color: #8292ad; height: auto; margin-top: 1; }
#main { width: 1fr; padding: 1 2; }
#topline { height: 3; }
#search { width: 1fr; border: round #344563; background: #111a2e; }
#status { width: 38; color: #91a3bf; content-align: right middle; }
TabbedContent { height: 1fr; }
TabPane { padding: 1 0; }
.section-title { color: #8bd5ff; text-style: bold; margin: 0 0 1 0; }
.muted { color: #91a3bf; }
.card { background: #111a2e; border: round #273653; padding: 1 2; margin: 0 0 1 0; height: auto; }
.field-label { color: #aebbd1; margin: 1 0 0 0; }
Input, Select { background: #0d1628; border: round #344563; }
Button { background: #1b2b48; border: round #3b5278; color: #e5eaf5; }
Button.primary { background: #176b91; border: round #45b8e8; color: white; text-style: bold; }
Button.danger { background: #612d3a; border: round #a34c60; }
#chat-log, #activity-log { height: 1fr; background: #0d1628; border: round #273653; padding: 1; }
#composer { height: auto; margin-top: 1; }
#message { width: 1fr; }
#settings-tabs { height: 1fr; }
#save-row { height: 3; margin-top: 1; }
#search-results { height: 5; color: #9db0cc; }
.hidden { display: none; }
"""


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
        self.engine.mode = "Plan" if str(self.cfg.get("execution_mode", "build")).lower() == "plan" else "Build"
        self.engine.cancel_event = threading.Event()
        self.engine.activity = ["Agent Code ready. Submit a task to begin."]
        self.engine.tool_details = []
        self.engine.stream_text = ""
        self.engine.notice = "Ready"
        self.engine.busy = False
        self._last_messages_snapshot = None
        self._last_activity_snapshot = None
        self._search_matches: list[str] = []

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
                        yield RichLog(id="chat-log", wrap=True, markup=True)
                        with Horizontal(id="composer"):
                            yield Input(placeholder="Describe a task…", id="message")
                            yield Button("Send", id="send", classes="primary")
                            yield Button("Stop", id="stop", classes="danger", disabled=True)
                    with TabPane("Workspace", id="workspace"):
                        yield Label("WORKSPACE EXPLORER", classes="section-title")
                        yield Static("", id="workspace-list", classes="card")
                    with TabPane("Activity", id="activity"):
                        yield Label("LIVE TRAJECTORY · TOOL ACTIVITY", classes="section-title")
                        yield RichLog(id="activity-log", wrap=True, markup=True)
                    with TabPane("Skills", id="skills"):
                        yield Label("NATIVE SKILLS", classes="section-title")
                        yield Static("", id="skills-list", classes="card")
                    with TabPane("MCP", id="mcp"):
                        yield Label("REMOTE MCP CONNECTIONS", classes="section-title")
                        yield Static("", id="mcp-list", classes="card")
                        yield Label("MCP server credentials remain in the existing protected configuration flow.", classes="muted")
                    with TabPane("Settings", id="settings"):
                        yield Label("SETTINGS CENTER", classes="section-title")
                        yield Input(placeholder="Filter settings…", id="settings_search")
                        yield Static("", id="search-results")
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
                                    yield Label("Permission mode", classes="field-label")
                                    yield Select([("Ask before changes", "ask"), ("Workspace auto-approve", "auto"), ("Read-only", "readonly")], id="permission", allow_blank=False)
                                    yield Checkbox("Show detailed tool activity", value=bool(self.cfg.get("show_activity_details", True)), id="activity_details")
                                    yield Checkbox("Enable Podman sandbox", value=bool(self.cfg.get("podman_sandbox_enabled", False)), id="podman_enabled")
                                    yield Checkbox("ULTRA UNRESTRICTED — automatic approval for all tools and host access", value=bool(self.cfg.get("ultra_unrestricted_enabled", False)), id="ultra_unrestricted")
                                    yield Static("DANGER: may modify or delete files outside the workspace. Uses current OS account rights only; cannot bypass sudo/UAC or active blacklist rules. Disable to restore normal approvals.", classes="muted")
                                    yield Button("Save execution settings", id="save_execution", classes="primary")
                            with TabPane("Connections", id="connections"):
                                with VerticalScroll(classes="card"):
                                    yield Label("Configured MCP servers", classes="field-label")
                                    yield Static("Manage server definitions from the desktop Settings → Remote MCP panel. This view is intentionally read-only to avoid corrupting nested authentication data.", classes="muted")
                                    yield Label("SSH connection", classes="field-label")
                                    ssh = self.cfg.get("ssh_connection", {})
                                    yield Static(str(ssh.get("command") or ssh.get("host") or "Not configured"), id="ssh_status")
                            with TabPane("Appearance", id="appearance"):
                                with VerticalScroll(classes="card"):
                                    yield Label("Terminal theme", classes="field-label")
                                    yield Select([(x.replace("-", " ").title(), x) for x in ("textual-dark", "nord", "gruvbox", "dracula", "tokyo-night", "catppuccin-mocha", "monokai", "solarized-dark")], value="nord", id="theme", allow_blank=False)
                                    yield Button("Apply theme", id="apply_theme", classes="primary")
                    with TabPane("Add-ons", id="addons"):
                        yield Label("APPLICATION ADD-ONS", classes="section-title")
                        yield Static("", id="addons-list", classes="card")
                    with TabPane("Help", id="help"):
                        yield Label("KEYBOARD SHORTCUTS & HELP", classes="section-title")
                        yield Static("Ctrl+P  Open command palette\nCtrl+Enter  Send task\nF5  Stop task\nCtrl+1/2/3  Chat / Workspace / Activity\nTab navigation is clickable; use arrow keys to move between tabs.\n\nPlan mode is read-only. Build mode can modify files within the configured workspace. Review permission settings before running tasks.", classes="card")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = str(self.cfg.get("tui_theme", "nord"))
        self._populate_settings()
        self._refresh_live_panels()
        self.set_interval(0.35, self._poll_engine)

    def _populate_settings(self) -> None:
        provider = str(self.cfg.get("provider_name", "OpenAI"))
        self.query_one("#provider_name", Select).value = provider if provider in PROVIDERS else "OpenAI"
        self.query_one("#base_url", Input).value = str(self.cfg.get("openai_base_url") or PROVIDERS.get(provider, ""))
        self.query_one("#model_id", Input).value = str(self.cfg.get("openai_model", ""))
        permission = str(self.cfg.get("permission_mode", self.cfg.get("permission", "ask")))
        self.query_one("#permission", Select).value = permission if permission in ("ask", "auto", "readonly") else "ask"
        self.query_one("#status", Static).update("● " + ("Configured" if api_keys(self.cfg) or provider == "Vireonix Free" else "API key needed"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("nav_"):
            page = bid[4:]
            self.query_one("#pages", TabbedContent).active = page
            self._refresh_static_page(page)
        elif bid == "send":
            self.action_send_message()
        elif bid == "stop":
            self.engine.cancel_event.set()
            self.engine.notice = "Stopping…"
        elif bid == "save_provider":
            self._save_provider()
        elif bid == "save_execution":
            self._save_execution()
        elif bid == "apply_theme":
            theme = str(self.query_one("#theme", Select).value)
            self.theme = theme
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
                "Connections": "mcp ssh remote servers authentication",
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

    def _save_execution(self) -> None:
        ultra = bool(self.query_one("#ultra_unrestricted", Checkbox).value)
        if ultra and not bool(self.cfg.get("ultra_unrestricted_enabled", False)):
            from textual.widgets import Confirm
            approved = self.push_screen_wait(Confirm("Enable Ultra Unrestricted Agent Code? It removes per-action approvals and allows host commands/tools to affect files outside the workspace using your current OS account rights. This may cause data loss. It cannot bypass sudo/UAC or blacklist rules."))
            if not approved:
                self.query_one("#ultra_unrestricted", Checkbox).value = False
                return
        self.cfg["ultra_unrestricted_enabled"] = ultra
        self.cfg["allow_unrestricted_host_shell"] = bool(self.cfg.get("allow_unrestricted_host_shell", False) or ultra)
        self.cfg["permission_mode"] = "auto" if ultra else str(self.query_one("#permission", Select).value)
        self.cfg["show_activity_details"] = self.query_one("#activity_details", Checkbox).value
        self.cfg["podman_sandbox_enabled"] = self.query_one("#podman_enabled", Checkbox).value
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
        self.engine.mode = "Plan" if str(self.cfg.get("execution_mode", "build")).lower() == "plan" else "Build"
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
            self.engine.busy = False

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
        if self.engine.busy:
            self.query_one("#status", Static).update("◌ Working…")
            self.query_one("#stop", Button).disabled = False
        else:
            self.query_one("#status", Static).update("● " + str(self.engine.notice or "Ready"))
            self.query_one("#stop", Button).disabled = True

    def _refresh_live_panels(self) -> None:
        """Refresh only live logs; never rescan the filesystem on the UI timer."""
        chat = self.query_one("#chat-log", RichLog)
        snapshot = tuple((role, TUI._chat_text(body)) for role, body in self.engine.messages)
        previous = self._last_messages_snapshot or ()
        if snapshot != previous:
            # Append only new messages or streamed suffixes. Rebuilding the whole
            # transcript for every token would make long sessions progressively slow.
            prefix_unchanged = len(snapshot) >= len(previous) and snapshot[:len(previous)] == previous
            if prefix_unchanged:
                for role, body in snapshot[len(previous):]:
                    label = "YOU" if role == "user" else "AGENT" if role == "assistant" else "TOOL"
                    color = "#8bd5ff" if role == "user" else "#a8e6a3" if role == "assistant" else "#f0c987"
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
                    color = "#8bd5ff" if role == "user" else "#a8e6a3" if role == "assistant" else "#f0c987"
                    chat.write(f"[{color}]{label}[/]  {body}")
            self._last_messages_snapshot = snapshot
        activity = self.query_one("#activity-log", RichLog)
        activity_snapshot = tuple(self.engine.activity[-300:])
        if activity_snapshot != self._last_activity_snapshot:
            activity.clear()
            for index, item in enumerate(activity_snapshot, 1):
                activity.write(f"[dim]{index:03d}[/]  {item}")
            self._last_activity_snapshot = activity_snapshot

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

    @staticmethod
    def _workspace_summary() -> str:
        root = paths.project_workspace_dir()
        try:
            items = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:100]
        except OSError as exc:
            return f"Workspace unavailable: {exc}"
        return f"{root}\n\n" + ("\n".join(("📁 " if p.is_dir() else "   ") + p.name for p in items) if items else "(empty workspace)")

    def _skills_summary(self) -> str:
        try:
            from .loader import discover_skills
            skills = discover_skills(paths.global_skills_dir())
            disabled = set(self.cfg.get("disabled_skills", []))
            return "\n".join(f"{'●' if s['name'] not in disabled else '○'}  {s['name']}  —  {s.get('description', '')}" for s in skills) or "No skills installed."
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
