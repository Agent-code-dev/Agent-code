"""Monitor-free terminal interface for Agent Code. Uses only terminal UI APIs."""
from __future__ import annotations
import curses, json, os, platform, queue, shutil, subprocess, textwrap, threading, time, uuid, re, unicodedata
from pathlib import Path
from . import __version__
from . import paths

CONFIG = paths.user_config_file()
WORKSPACE = paths.project_workspace_dir()

_SUBAGENT_JOBS = {}
_SUBAGENT_JOBS_LOCK = threading.RLock()

PROVIDERS = {
    "OpenAI": "https://api.openai.com/v1",
    "Google AI Studio": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Vireonix Free": "https://vireonix.ai/v1",
    "Custom OpenAI-compatible": "",
}


def read_config():
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}
    # Desktop GUI stores provider secrets in the OS keyring. Restore them here
    # too, so GUI and TUI share one configuration without exposing plaintext.
    refs = cfg.get("openai_api_key_refs", [])
    if not cfg.get("openai_api_keys") and refs:
        try:
            import keyring
            cfg["openai_api_keys"] = [value for ref in refs
                                      if (value := keyring.get_password("agent-code", ref))]
        except Exception:
            cfg["openai_api_keys"] = []
    return cfg

def write_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    disk = dict(cfg)
    keys = api_keys(disk)
    if keys:
        try:
            import keyring
            refs = []
            for index, secret in enumerate(keys):
                account = f"provider/default/{index}"
                keyring.set_password("agent-code", account, secret)
                if keyring.get_password("agent-code", account) != secret:
                    raise RuntimeError("credential vault did not verify the saved key")
                refs.append(account)
            disk["openai_api_key_refs"] = refs
            disk.pop("openai_api_keys", None)
        except Exception as exc:
            raise RuntimeError(f"Could not save API key to the OS credential vault: {exc}") from exc
    CONFIG.write_text(json.dumps(disk, indent=2), encoding="utf-8")
    try: CONFIG.chmod(0o600)
    except OSError: pass

def api_keys(cfg):
    keys = cfg.get("openai_api_keys", [])
    if isinstance(keys, str): keys = [x.strip() for x in keys.replace('\n', ',').split(',') if x.strip()]
    if not keys and os.getenv("OPENAI_API_KEY"): keys = [os.environ["OPENAI_API_KEY"]]
    return keys

class TUI:
    def __init__(self, screen):
        self.s=screen; self.cfg=read_config(); self.messages=[]; self.notice="Welcome. Press ? for help."; self.mode="Build"
        self.input=""; self.input_cursor=0; self.scroll=0; self.cwd="."; self.page="Chat"; self.running=True; self.busy=False; self.cancel_event=threading.Event(); self.events=queue.Queue(); self.activity=["Ready — send a task to watch agent progress."]; self.tool_details=[]; self.activity_scroll=0; self.stream_text=""; self.selected_index=0
        try:
            curses.curs_set(1); curses.start_color(); curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1); curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(3, curses.COLOR_GREEN, -1); curses.init_pair(4, curses.COLOR_YELLOW, -1)
            curses.init_pair(5, curses.COLOR_MAGENTA, -1); curses.init_pair(6, curses.COLOR_RED, -1)
        except curses.error:
            pass
        self.s.keypad(True); self.s.timeout(150); self.draw()
    def safe_add(self,y,x,text,attr=0,width=None):
        h,w=self.s.getmaxyx()
        if y<0 or y>=h or x<0 or x>=w: return
        columns = max(0, min(w - x - 1, width if width is not None else w - x - 1))
        text = self._clip_columns(str(text), columns)
        try: self.s.addstr(y,x,text,attr)
        except curses.error: pass

    @staticmethod
    def _char_width(char):
        if char in "\n\r":
            return 0
        if unicodedata.combining(char):
            return 0
        return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1

    @classmethod
    def _display_width(cls, value):
        return sum(cls._char_width(ch) for ch in str(value))

    @classmethod
    def _clip_columns(cls, value, columns):
        """Clip by terminal cells, not Python characters (CJK/emoji safe)."""
        if columns <= 0:
            return ""
        output, used = [], 0
        for char in str(value):
            if char in "\r\n":
                char = " "
            cells = cls._char_width(char)
            if used + cells > columns:
                break
            output.append(char)
            used += cells
        return "".join(output)

    @classmethod
    def _wrap_terminal_line(cls, value, columns):
        """Wrap one logical line without splitting a wide terminal glyph."""
        columns = max(1, int(columns))
        value = str(value).expandtabs(4)
        if not value:
            return [""]
        rows, current, used = [], [], 0
        for char in value:
            cells = cls._char_width(char)
            if used and used + cells > columns:
                rows.append("".join(current))
                current, used = [], 0
            if cells > columns:
                char, cells = "?", 1
            current.append(char)
            used += cells
        if current or not rows:
            rows.append("".join(current))
        return rows

    @classmethod
    def render_chat_lines(cls, messages, width):
        """Create a stable, fully wrapped transcript for the visible viewport."""
        width = max(1, int(width))
        rendered = []
        for role, body in list(messages or []):
            label = {"assistant": "ASSISTANT", "user": "YOU", "tool": "TOOL RESULT"}.get(role, str(role).upper())
            rendered.append((f"{label}  ─────────────────────────", role))
            body_text = cls._chat_text(body)
            if role == "tool":
                body_text = body_text.splitlines()[0] if body_text.splitlines() else "Tool completed. See Activity for details."
            previous_blank = False
            for raw_line in (body_text.splitlines() or [""]):
                if not raw_line.strip():
                    if not previous_blank:
                        rendered.append(("", role))
                    previous_blank = True
                    continue
                previous_blank = False
                rendered.extend((line, role) for line in cls._wrap_terminal_line(raw_line, width))
            rendered.append(("", role))
        return rendered

    @staticmethod
    def visible_chat_lines(rendered, viewport, scroll=0):
        """Return the bottom-anchored transcript window; scroll=0 means newest."""
        viewport = max(1, int(viewport))
        total = len(rendered)
        max_scroll = max(0, total - viewport)
        scroll = max(0, min(int(scroll), max_scroll))
        end = total - scroll
        start = max(0, end - viewport)
        return rendered[start:end], max_scroll, scroll
    @staticmethod
    def _chat_text(body):
        """Normalize provider content into readable terminal text."""
        if body is None:
            return "(empty response)"
        if isinstance(body, str):
            value = body
        elif isinstance(body, (list, tuple)):
            chunks = []
            for part in body:
                if isinstance(part, dict):
                    value_part = part.get("text") or part.get("content")
                    if value_part is not None:
                        chunks.append(str(value_part))
                else:
                    value_part = getattr(part, "text", None)
                    if value_part is not None:
                        chunks.append(str(value_part))
            value = "\n".join(chunks) if chunks else str(body)
        else:
            value = str(body)
        # Remove terminal control sequences while retaining ordinary newlines/tabs.
        value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", value)
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        value = "".join(ch if ch in "\n\t" or ord(ch) >= 32 else " " for ch in value)
        return value.strip() or "(The provider returned no displayable text.)"

    PAGES = ["Chat", "Workspace", "Activity", "Skills", "MCP", "Settings", "Add-ons", "Help"]

    def _page_title(self):
        return {
            "Chat": "Conversation", "Workspace": "Project workspace",
            "Activity": "Live activity", "Skills": "Native skills",
            "MCP": "Remote MCP servers", "Settings": "Provider settings",
            "Add-ons": "Application add-ons", "Help": "Keyboard shortcuts",
        }.get(self.page, self.page)

    def _draw_sidebar(self, height, width, sidebar_width):
        self.safe_add(1, 2, "AGENT CODE", curses.color_pair(1) | curses.A_BOLD)
        self.safe_add(2, 2, "v" + __version__ + "  TERMINAL", curses.A_DIM)
        self.safe_add(4, 2, "NAVIGATION", curses.A_DIM | curses.A_BOLD)
        for index, page in enumerate(self.PAGES):
            y = 5 + index
            if y >= height - 7:
                break
            active = page == self.page
            marker = "● " if active else "  "
            attr = curses.color_pair(2) | curses.A_BOLD if active else curses.A_NORMAL
            self.safe_add(y, 2, marker + f"{index + 1}  {page}", attr, sidebar_width - 4)
        info_y = max(14, height - 8)
        self.safe_add(info_y, 2, "SESSION", curses.A_DIM | curses.A_BOLD)
        self.safe_add(info_y + 1, 2, "MODE  " + self.mode.upper(), curses.color_pair(4), sidebar_width - 4)
        self.safe_add(info_y + 2, 2, "STATE " + ("WORKING" if self.busy else "READY"),
                      curses.color_pair(4 if self.busy else 3), sidebar_width - 4)
        provider = str(self.cfg.get("provider_name", "OpenAI"))
        self.safe_add(info_y + 3, 2, "AI    " + provider, curses.A_DIM, sidebar_width - 4)
        self.safe_add(info_y + 4, 2, "F2 mode · F5 stop", curses.A_DIM, sidebar_width - 4)
        for y in range(0, height - 1):
            self.safe_add(y, sidebar_width, "│", curses.A_DIM)

    def _draw_chat(self, top, left, width, height):
        self.safe_add(top, left, "CHAT", curses.color_pair(1) | curses.A_BOLD)
        self.safe_add(top, left + 7, "Build instructions, ask questions, or delegate project work", curses.A_DIM,
                      max(0, width - 8))
        body_top = top + 2
        composer_height = 4
        body_height = max(1, height - body_top - composer_height)
        rendered = self.render_chat_lines(self.messages, max(1, width - 3))
        visible, max_scroll, self.scroll = self.visible_chat_lines(rendered, body_height, self.scroll)
        if not visible:
            welcome = [
                ("AGENT CODE", "assistant"),
                ("Your workspace is ready.", "assistant"),
                ("Describe what you want to build, inspect, or fix.", "assistant"),
                ("Use !command to run an explicit shell command.", "assistant"),
            ]
            visible = welcome
        for row, (line, role) in enumerate(visible):
            if row >= body_height:
                break
            is_heading = line.endswith("─────────────────────────")
            if role == "assistant":
                attr = curses.color_pair(3) | (curses.A_BOLD if is_heading else 0)
            elif role == "user":
                attr = curses.color_pair(4) | (curses.A_BOLD if is_heading else 0)
            elif role == "tool":
                attr = curses.color_pair(5) | (curses.A_BOLD if is_heading else 0)
            else:
                attr = curses.A_DIM
            self.safe_add(body_top + row, left, line, attr, width - 2)
        if max_scroll:
            self.safe_add(body_top - 1, left, f"{self.scroll} lines above · PgUp/PgDn to scroll", curses.A_DIM)

        divider_y = height - composer_height
        self.safe_add(divider_y, left, "─" * max(1, width - 2), curses.color_pair(1))
        state = "Agent is working…" if self.busy else "Message"
        self.safe_add(divider_y + 1, left, state, curses.A_BOLD | (curses.color_pair(4) if self.busy else 0))
        prompt_x = left
        prompt_text = "> " + self.input
        available = max(1, width - 3)
        cursor_index = getattr(self, "input_cursor", len(self.input))
        cursor_cell = self._display_width(self.input[:cursor_index])
        prefix_cells = 2
        offset = max(0, cursor_cell + prefix_cells - available + 1)
        visible_input = self._clip_columns(prompt_text, available)
        if offset:
            visible_input = self._clip_columns(prompt_text[prefix_cells:], available)
            # Keep the cursor visible for long prompts without slicing wide glyphs incorrectly.
            chars = self.input
            start_index = 0
            used = 0
            while start_index < len(chars) and used < offset:
                used += self._char_width(chars[start_index]); start_index += 1
            visible_input = "> " + chars[start_index:]
            visible_input = self._clip_columns(visible_input, available)
        self.safe_add(divider_y + 2, prompt_x, visible_input, curses.A_BOLD, available)
        hint = "Enter send · ! shell · F5 stop · Ctrl+L clear · Tab pages · F10 quit"
        self.safe_add(height - 1, left, hint, curses.A_DIM, width - 2)
        try:
            cursor_x = left + min(width - 2, prefix_cells + max(0, cursor_cell - offset))
            self.s.move(min(height - 2, divider_y + 2), max(left, cursor_x))
        except Exception:
            pass

    def _draw_workspace(self, top, left, width, height):
        self.safe_add(top, left, "PROJECT FILES", curses.color_pair(1) | curses.A_BOLD)
        self.safe_add(top + 1, left, str(WORKSPACE), curses.A_DIM, width - 2)
        try:
            entries = sorted(WORKSPACE.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            entries = []
            self.notice = f"Workspace unavailable: {exc}"
        if not entries:
            self.safe_add(top + 3, left, "This workspace is empty. Ask the agent to create a project.")
            return
        for index, item in enumerate(entries[:max(1, height - top - 4)]):
            marker = "▸ " if index == self.selected_index else "  "
            kind = "DIR " if item.is_dir() else "FILE"
            try:
                size = "" if item.is_dir() else f"  {item.stat().st_size:,} B"
            except OSError:
                size = ""
            attr = curses.A_REVERSE if index == self.selected_index else 0
            self.safe_add(top + 3 + index, left, f"{marker}{kind}  {item.name}{size}", attr, width - 2)
        self.safe_add(height - 2, left, "↑/↓ select · Enter inspect path · 1 return to chat", curses.A_DIM, width - 2)

    def _draw_activity(self, top, left, width, height):
        self.safe_add(top, left, "EXECUTION LOG", curses.color_pair(1) | curses.A_BOLD)
        self.safe_add(top + 1, left, "Tool activity and results are shown here; private model reasoning is never displayed.", curses.A_DIM, width - 2)
        lines = []
        for item in self.activity:
            lines.extend(self._wrap_terminal_line("· " + str(item), max(10, width - 3)))
        for item in self.tool_details:
            lines.append("─ TOOL DETAIL ─")
            for raw in str(item).splitlines():
                lines.extend(self._wrap_terminal_line(raw, max(10, width - 3)))
        viewport = max(1, height - top - 5)
        max_back = max(0, len(lines) - viewport)
        self.activity_scroll = max(0, min(self.activity_scroll, max_back))
        end = len(lines) - self.activity_scroll
        start = max(0, end - viewport)
        for row, line in enumerate(lines[start:end]):
            self.safe_add(top + 3 + row, left, line, curses.A_DIM if line.startswith("─") else 0, width - 2)
        self.safe_add(height - 2, left, f"{len(lines)} lines · {self.activity_scroll} lines back · PgUp/PgDn scroll", curses.A_DIM, width - 2)

    def _draw_management(self, top, left, width, height):
        page = self.page
        if page == "Skills":
            from .loader import discover_skills
            items = discover_skills(paths.global_skills_dir())
            disabled = set(self.cfg.get("disabled_skills", []))
            self.safe_add(top, left, f"INSTALLED SKILLS  ·  {len(items)} total  ·  {sum(x['name'] not in disabled for x in items)} enabled", curses.color_pair(1) | curses.A_BOLD)
            rows = [(f"{'●' if x['name'] not in disabled else '○'}  {x['name']}  —  {x.get('description', '')}", x['name'] not in disabled) for x in items]
            footer = "T toggle · I install bundled skills · changes apply to the next task"
        elif page == "Add-ons":
            from .addons import AddonManager
            items = AddonManager(paths.global_addons_dir(), self.cfg.get("disabled_addons", [])).discover()
            self.safe_add(top, left, f"APPLICATION ADD-ONS  ·  {len(items)} installed", curses.color_pair(1) | curses.A_BOLD)
            rows = [(f"{'●' if x.enabled else '○'}  {x.name} v{x.version}  —  {x.error or x.description}", x.enabled) for x in items]
            footer = "T toggle · N create starter add-on · O show add-on directory"
        elif page == "MCP":
            items = self.cfg.get("mcp_servers", [])
            if not isinstance(items, list):
                items = []
            self.safe_add(top, left, f"REMOTE MCP SERVERS  ·  {len(items)} configured", curses.color_pair(1) | curses.A_BOLD)
            rows = [(f"{'●' if x.get('enabled', True) else '○'}  {x.get('name', x.get('id', 'unnamed'))}  —  {x.get('url', '')}", x.get('enabled', True)) for x in items]
            footer = "A add · E edit · T enable/disable · D delete · C connect/test"
        else:
            key_state = "configured" if api_keys(self.cfg) else "not configured"
            values = [
                ("Provider", self.cfg.get("provider_name", "OpenAI")),
                ("Base URL", self.cfg.get("openai_base_url") or PROVIDERS.get(self.cfg.get("provider_name", "OpenAI"), "(not set)")),
                ("Model", self.cfg.get("openai_model") or "(not selected)"),
                ("API key", key_state),
                ("Workspace", str(WORKSPACE)),
                ("Config file", str(CONFIG)),
            ]
            for i, (label, value) in enumerate(values):
                self.safe_add(top + i * 2, left, label.upper(), curses.A_DIM | curses.A_BOLD)
                self.safe_add(top + i * 2 + 1, left, str(value), curses.A_BOLD, width - 2)
            self.safe_add(height - 2, left, "P provider · K API key · M fetch models · I install Podman", curses.A_DIM, width - 2)
            return
        if not rows:
            self.safe_add(top + 2, left, "Nothing here yet. Use the action keys shown below.", curses.A_DIM)
        for index, (label, enabled) in enumerate(rows[:max(1, height - top - 5)]):
            attr = curses.A_REVERSE if index == self.selected_index else (curses.color_pair(3) if enabled else curses.color_pair(4))
            self.safe_add(top + 2 + index, left, label, attr, width - 2)
        self.safe_add(height - 2, left, footer, curses.A_DIM, width - 2)

    def draw(self):
        self.s.erase()
        height, width = self.s.getmaxyx()
        if height < 12 or width < 48:
            self.safe_add(0, 0, "AGENT CODE — terminal too small", curses.A_BOLD)
            self.safe_add(2, 0, f"Current size: {width}×{height}. Resize to at least 48×12.")
            self.safe_add(4, 0, "F10 or Ctrl+C to quit.", curses.A_DIM)
            self.s.refresh()
            return
        self.safe_add(0, 0, " AGENT CODE  " + __version__ + "  ◆  " + self._page_title().upper(), curses.color_pair(2) | curses.A_BOLD, width - 1)
        sidebar = max(21, min(27, width // 4)) if width >= 76 else 0
        left = sidebar + 2 if sidebar else 2
        content_width = max(1, width - left - 2)
        if sidebar:
            self._draw_sidebar(height, width, sidebar)
        else:
            nav = "  ".join(f"{i + 1}:{name}" for i, name in enumerate(self.PAGES))
            self.safe_add(1, 1, nav, curses.A_DIM, width - 2)
        self.safe_add(2, left, self._page_title(), curses.color_pair(1) | curses.A_BOLD, content_width)
        top = 4
        if self.page == "Chat":
            self._draw_chat(top, left, content_width, height)
        elif self.page == "Workspace":
            self._draw_workspace(top, left, content_width, height)
        elif self.page == "Activity":
            self._draw_activity(top, left, content_width, height)
        elif self.page in ("Skills", "MCP", "Settings", "Add-ons"):
            self._draw_management(top, left, content_width, height)
        else:
            help_lines = [
                "CHAT", "Enter send · !<command> execute shell · Ctrl+L clear conversation",
                "F5 stop task · F2 toggle Build/Plan · PgUp/PgDn scroll transcript",
                "", "NAVIGATION", "1–8 open pages · Tab next page · Shift+Tab previous page",
                "", "MANAGEMENT", "Skills: T toggle · I install bundled skills",
                "Add-ons: T toggle · N create · O show directory",
                "MCP: A add · E edit · T toggle · D delete · C connect/test",
                "Settings: P provider · K API key · M fetch models · I install Podman",
                "", "TERMINAL", "Ctrl+C or F10 quit · Esc clear the current chat input",
                "The TUI is designed for SSH and headless Linux environments.",
            ]
            for row, line in enumerate(help_lines):
                attr = curses.color_pair(1) | curses.A_BOLD if line and line.isupper() else 0
                self.safe_add(top + row, left, line, attr, content_width)
        # Persistent status strip.
        status = f" {'RUNNING' if self.busy else 'READY'}  │  {self.cfg.get('provider_name', 'OpenAI')}  │  {self.cfg.get('openai_model') or 'no model selected'}  │  {self.notice}"
        self.safe_add(height - 1, 0, status, curses.A_DIM, width - 1)
        self.s.refresh()

    def prompt(self,title,initial=""):
        """Read a one-line value without allowing the main polling timeout to interrupt it."""
        curses.echo()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        height, width = self.s.getmaxyx()
        try:
            old_timeout = self.s.getdelay()
        except Exception:
            old_timeout = 150
        self.s.timeout(-1)
        label = (str(title) + " ")[:max(1, width - 2)]
        self.safe_add(height - 2, 1, label, curses.color_pair(2), width - 2)
        self.s.clrtoeol()
        self.s.refresh()
        try:
            start_x = min(width - 2, len(label) + 1)
            value = self.s.getstr(height - 2, start_x, max(1, width - start_x - 1)).decode("utf-8", "replace")
        except (curses.error, UnicodeError, OSError):
            value = initial
        finally:
            try:
                curses.noecho()
                self.s.timeout(old_timeout)
            except curses.error:
                pass
        return value.strip() or initial

    def choose(self,title,options,current=None):
        """Scrollable keyboard selector used by provider, MCP, skill and add-on dialogs."""
        options = list(options)
        if not options:
            return None
        index = options.index(current) if current in options else 0
        offset = 0
        while True:
            self.s.erase()
            height, width = self.s.getmaxyx()
            self.safe_add(1, 2, str(title), curses.color_pair(1) | curses.A_BOLD, width - 4)
            self.safe_add(2, 2, f"{len(options)} options · type ↑/↓ or j/k to move", curses.A_DIM, width - 4)
            viewport = max(1, height - 6)
            offset = max(0, min(offset, max(0, len(options) - viewport)))
            if index < offset:
                offset = index
            elif index >= offset + viewport:
                offset = index - viewport + 1
            for row, option_index in enumerate(range(offset, min(len(options), offset + viewport))):
                active = option_index == index
                self.safe_add(4 + row, 3, ("❯ " if active else "  ") + str(options[option_index]),
                              curses.A_REVERSE if active else 0, width - 6)
            self.safe_add(height - 1, 2, "↑/↓ move · Enter select · Esc cancel", curses.A_DIM, width - 4)
            self.s.refresh()
            try:
                key = self.s.get_wch()
            except curses.error:
                continue
            if key in (curses.KEY_UP, "k"):
                index = (index - 1) % len(options)
            elif key in (curses.KEY_DOWN, "j"):
                index = (index + 1) % len(options)
            elif key == curses.KEY_PPAGE:
                index = max(0, index - viewport)
            elif key == curses.KEY_NPAGE:
                index = min(len(options) - 1, index + viewport)
            elif key in ("\n", curses.KEY_ENTER, 10, 13):
                return options[index]
            elif key == 27:
                return None

    def configure(self,which):
        if which=="provider":
            current=self.cfg.get("provider_name","OpenAI")
            choice=self.choose("Select AI provider",PROVIDERS.keys(),current)
            if not choice: return
            self.cfg["provider_name"]=choice
            self.cfg["openai_base_url"]=self.prompt("Provider Base URL",self.cfg.get("openai_base_url") or PROVIDERS[choice])
            self.cfg["openai_model"]=""
            self.notice="Provider selected. Fetch models (m) or enter a model ID."
        elif which=="model":
            self.fetch_models()
            return
        else:
            curses.noecho(); h,w=self.s.getmaxyx(); old_timeout=150
            try: old_timeout=self.s.getdelay()
            except Exception: pass
            self.s.timeout(-1)
            self.safe_add(h-1,0,"API key (hidden; Enter to save): ",curses.color_pair(2)); self.s.clrtoeol(); self.s.refresh()
            try: key=self.s.getstr(h-1,min(34,max(0,w-2)),max(1,w-36)).decode("utf-8","replace").strip()
            except (curses.error, OSError, UnicodeError): key=""
            finally:
                try: self.s.timeout(old_timeout)
                except curses.error: pass
            if not key:
                self.notice="API key unchanged (no key entered)."
                return
            self.cfg["openai_api_keys"]=[key]
        try:
            write_config(self.cfg)
            self.notice="Settings saved securely to "+str(CONFIG)
        except Exception as exc:
            self.notice=f"Settings not saved: {type(exc).__name__}: {exc}"
    def fetch_models(self):
        """Fetch model IDs on a worker thread so network latency never freezes curses."""
        if getattr(self, "model_fetching", False):
            self.notice = "Model search is already running…"
            return
        self.model_fetching = True
        self.notice = "Searching provider for available models…"
        def worker():
            try:
                from .agent import make_client
                provider = self.cfg.get("provider_name", "OpenAI")
                base = self.cfg.get("openai_base_url") or PROVIDERS.get(provider, "")
                keys = api_keys(self.cfg)
                if not base:
                    raise ValueError("Set a provider Base URL first.")
                if not keys and provider != "Vireonix Free":
                    raise ValueError("Set an API key first (Settings → k).")
                client = make_client(keys, base, provider)
                if client is None:
                    raise ValueError("Set at least one API key first.")
                client.timeout = 8
                models = sorted({str(item.id) for item in client.models.list().data if getattr(item, "id", None)})
                self.events.put(("models", models if models else "Provider returned no models."))
            except Exception as exc:
                self.events.put(("models", f"Model search failed: {type(exc).__name__}: {exc}"))
        threading.Thread(target=worker, daemon=True, name="agent-code-model-search").start()

    def select_searched_model(self, models):
        if isinstance(models, str):
            self.notice = models + " You can enter an exact model ID in Settings."
            return
        query = self.prompt("Filter model names (blank = all)", "")
        filtered = [m for m in models if query.lower() in m.lower()] if query else models
        if not filtered:
            self.notice = f"No models match {query!r}; press m to search again."
            return
        chosen = self.choose("Select model (provider results)", filtered, self.cfg.get("openai_model"))
        if chosen:
            self.cfg["openai_model"] = chosen
            write_config(self.cfg)
            self.notice = "Selected model: " + chosen

    def mcp_configure(self,action):
        servers=self.cfg.get("mcp_servers",[])
        if not isinstance(servers,list): servers=[]
        if action=="add":
            name=self.prompt("MCP server name")
            if not name: return
            url=self.prompt("MCP Streamable HTTP URL (https://…)")
            if not url: return
            headers_text=self.prompt('Headers JSON (optional, e.g. {"Authorization":"Bearer …"})','{}')
            try: headers=json.loads(headers_text or "{}")
            except Exception: self.notice="Headers must be valid JSON."; return
            if not isinstance(headers,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in headers.items()):
                self.notice="Headers must be a JSON object of string values."; return
            import re
            sid=re.sub(r"[^a-zA-Z0-9_-]","_",name.strip().lower()).strip("_") or "mcp_server"
            used={str(x.get("id")) for x in servers}; base=sid; n=2
            while sid in used: sid=f"{base}_{n}"; n+=1
            servers.append({"id":sid,"name":name.strip()[:80],"url":url.strip(),"enabled":True,"headers":headers,"auth_in_keyring":False,"last_tools":[]})
        else:
            if not servers: self.notice="No MCP servers configured."; return
            labels=[f"{i+1}. {x.get('name',x.get('id'))} — {x.get('url','')}" for i,x in enumerate(servers)]
            selected=self.choose("Select MCP server",labels)
            if selected is None: return
            idx=labels.index(selected); server=servers[idx]
            if action=="delete":
                if self.prompt("Type delete to remove this MCP server","no").lower()=="delete": servers.pop(idx)
            elif action=="toggle": server["enabled"]=not server.get("enabled",True)
            elif action=="edit":
                server["name"]=self.prompt("Name",server.get("name",""))[:80]
                server["url"]=self.prompt("Streamable HTTP URL",server.get("url",""))
                raw=self.prompt("Headers JSON",json.dumps(server.get("headers",{})))
                try:
                    hdr=json.loads(raw or "{}")
                    if not isinstance(hdr,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in hdr.items()): raise ValueError()
                    server["headers"]=hdr
                except Exception: self.notice="Invalid headers JSON; MCP settings not saved."; return
            elif action=="connect":
                try:
                    from .mcp_manager import RemoteMCPManager
                    manager=RemoteMCPManager(); tools=manager.connect(server)
                    self.notice=f"Connected to {server.get('name')}: {len(tools)} tool(s) discovered."
                    manager.close()
                except Exception as exc: self.notice=f"MCP connection failed: {exc}"; return
        self.cfg["mcp_servers"]=servers; write_config(self.cfg)
        if action!="connect": self.notice="MCP configuration saved."

    def manage_skill(self, action):
        from .loader import discover_skills
        skills_dir = paths.global_skills_dir()
        if action == "install":
            installed = paths.install_bundled_skills(overwrite=False)
            self.notice = ("Installed bundled skills: " + ", ".join(installed)) if installed else "All bundled skills are already installed."
            return
        skills = discover_skills(skills_dir)
        if not skills:
            self.notice = "No skills installed. Press i to install bundled skills."
            return
        labels = [f"{item['name']} — {item.get('description', '')}" for item in skills]
        selected = self.choose("Select skill", labels)
        if selected is None:
            return
        name = skills[labels.index(selected)]["name"]
        disabled = set(self.cfg.get("disabled_skills", []))
        if name in disabled:
            disabled.remove(name)
            state = "enabled"
        else:
            disabled.add(name)
            state = "disabled"
        self.cfg["disabled_skills"] = sorted(disabled)
        try:
            write_config(self.cfg)
            self.notice = f"Skill {name} {state}. Restart the current task to apply tool changes."
        except Exception as exc:
            self.notice = f"Could not save skill settings: {exc}"

    def manage_addon(self, action):
        from .addons import AddonManager, create_addon_template
        directory = paths.global_addons_dir()
        if action == "create":
            name = self.prompt("New add-on ID (letters, numbers, . _ -)")
            if not name:
                return
            description = self.prompt("Short description", "A custom Agent Code extension")
            try:
                folder = create_addon_template(directory, name, description)
                self.notice = f"Starter add-on created: {folder} — review addon.py before enabling."
            except Exception as exc:
                self.notice = f"Could not create add-on: {type(exc).__name__}: {exc}"
            return
        manager = AddonManager(directory, self.cfg.get("disabled_addons", []))
        infos = manager.discover()
        if action == "open":
            self.notice = f"Add-on directory: {directory}"
            return
        if not infos:
            self.notice = "No add-ons installed. Press n to create a starter add-on."
            return
        labels = [f"{item.name} — {item.description or item.error or 'No description'}" for item in infos]
        selected = self.choose("Select add-on", labels)
        if selected is None:
            return
        name = infos[labels.index(selected)].name
        disabled = set(self.cfg.get("disabled_addons", []))
        if name in disabled:
            disabled.remove(name)
            state = "enabled"
        else:
            disabled.add(name)
            state = "disabled"
        self.cfg["disabled_addons"] = sorted(disabled)
        try:
            write_config(self.cfg)
            self.notice = f"Add-on {name} {state}. Restart the current task to apply changes."
        except Exception as exc:
            self.notice = f"Could not save add-on settings: {type(exc).__name__}: {exc}"
    def answer(self,user):
        from .agent import make_client
        from . import agent as engine
        from .tool_namespace import UnifiedToolNamespace
        from .runtime import AgentLoopGuard, ProgressTracker
        keys=api_keys(self.cfg); provider=self.cfg.get("provider_name","OpenAI")
        base=self.cfg.get("openai_base_url") or PROVIDERS.get(provider,PROVIDERS["OpenAI"])
        model=str(self.cfg.get("openai_model") or "").strip()
        if not model:
            self.messages.append(("assistant","No model selected. Open Settings and press m to fetch models, or set a model ID.")); return
        if not keys and provider!="Vireonix Free":
            self.messages.append(("assistant","No API key configured. Open Settings and press k to add one.")); return
        client=make_client(keys,base,provider)
        if client is None:
            self.messages.append(("assistant","No API key configured. Add one or more keys in Settings.")); return
        client.timeout=600
        # Use the same core workspace tools as the desktop agent, not a chat-only stub.
        names={"read_file","write_file","append_file","edit_file","glob_files","grep_files","shell_run","background_shell","web_search","web_fetch","task","task_status"}
        raw_schemas=[x for x in engine.CORE_SCHEMAS if x.get("function",{}).get("name") in names]
        handlers={"read_file":engine.tool_read_file,"write_file":engine.tool_write_file,
            "append_file":engine.tool_append_file,"edit_file":engine.tool_edit_file,
            "glob_files":engine.tool_glob_files,"grep_files":engine.tool_grep_files,
            "shell_run":engine.tool_shell_run,"background_shell":engine.tool_background_shell,
            "web_search":engine.tool_web_search,"web_fetch":engine.tool_web_fetch}
        def task_status(job_id):
            with _SUBAGENT_JOBS_LOCK:
                job = _SUBAGENT_JOBS.get(str(job_id))
                if not job: return f"Unknown subagent job_id: {job_id}"
                if job["status"] == "running": return f"{job_id}: running; continue your own work, this check did not wait."
                return f"{job_id}: {job['status']}\n{job.get('result', '')[:10000]}"
        def start_subagent(description, prompt):
            if self.mode != "Build": return "DENIED: subagents that can modify files are available only in Build mode."
            with _SUBAGENT_JOBS_LOCK:
                active = sum(1 for item in _SUBAGENT_JOBS.values() if item.get("status") == "running")
                if active >= 4: return "SUBAGENT_LIMIT: four subagents are already running."
            job_id = "subagent-" + uuid.uuid4().hex[:8]
            with _SUBAGENT_JOBS_LOCK:
                _SUBAGENT_JOBS[job_id] = {"status":"running", "result":"", "description":str(description)[:200]}
            delegation_started.add(job_id)
            def run_job():
                allowed = {"read_file","write_file","append_file","edit_file","glob_files","grep_files","web_search","web_fetch"}
                sub_registry=UnifiedToolNamespace()
                for schema in engine.CORE_SCHEMAS:
                    original=schema.get("function",{}).get("name")
                    if original in allowed and original in raw_handlers:
                        sub_registry.register("core","core",schema,raw_handlers[original],original_name=original)
                sub_schemas=sub_registry.schemas
                sub_handlers=sub_registry.callables
                sub_original={name:identity.original_name for name,identity in sub_registry.identities.items()}
                sub_guard=AgentLoopGuard(max_identical_calls=2,max_similar_searches=3,workspace=WORKSPACE)
                history_sub = [{"role":"system","content":f"You are an independent coding subagent. Job: {description}. Work only inside workspace {WORKSPACE}. You may read and edit files, but avoid unrelated files and report exactly what changed. The main agent is working concurrently; avoid overwriting files it may be editing."}, {"role":"user","content":str(prompt)}]
                try:
                    while True:
                        response_sub = client.chat.completions.create(model=model,messages=history_sub,tools=sub_schemas,tool_choice="auto")
                        msg_sub = response_sub.choices[0].message
                        if not msg_sub.tool_calls:
                            result_sub = msg_sub.content or "(subagent returned no text)"
                            status_sub = "completed"
                            break
                        assistant_sub={"role":"assistant","content":msg_sub.content or "","tool_calls":[engine._tool_call_history_item(tc) for tc in msg_sub.tool_calls]}
                        assistant_sub.update(engine._provider_metadata(msg_sub))
                        history_sub.append(assistant_sub)
                        for tc in msg_sub.tool_calls:
                            try: args_sub=json.loads(tc.function.arguments or "{}")
                            except Exception: args_sub={}
                            original_sub=sub_original.get(tc.function.name,tc.function.name)
                            fn_sub=sub_handlers.get(tc.function.name)
                            try:
                                blocked=sub_guard.before_call(original_sub,args_sub)
                                cached=sub_guard.cached_read(original_sub,args_sub) if not blocked else None
                                out_sub=blocked if blocked else cached if cached is not None else (fn_sub(**args_sub) if fn_sub else "DENIED: tool unavailable to subagent")
                            except Exception as exc: out_sub=f"ERROR: {type(exc).__name__}: {exc}"
                            finally: sub_guard.after_call(original_sub,args_sub,locals().get("out_sub",""))
                            history_sub.append({"role":"tool","tool_call_id":tc.id,"content":str(out_sub)[:12000]})
                    with _SUBAGENT_JOBS_LOCK: _SUBAGENT_JOBS[job_id].update(status=status_sub,result=result_sub)
                except Exception as exc:
                    with _SUBAGENT_JOBS_LOCK: _SUBAGENT_JOBS[job_id].update(status="failed",result=f"{type(exc).__name__}: {exc}")
            threading.Thread(target=run_job,name=f"TUI-{job_id}",daemon=True).start()
            return f"Subagent started asynchronously. job_id={job_id}; continue your own work and check task_status later."
        handlers["task"] = start_subagent
        handlers["task_status"] = task_status
        # TUI and desktop must expose the same native Skills and Add-on tools.
        # The loader keeps remote-only Skills as safe placeholders; they fail
        # clearly here until a TUI execution router is configured.
        skill_schemas, skill_handlers, skill_meta, skill_commands = engine.load_skills(
            paths.global_skills_dir(), self.cfg.get("disabled_skills", []),
            default_target=self.cfg.get("skill_execution_default_target", "host"))
        raw_schemas.extend(skill_schemas)
        handlers.update(skill_handlers)
        addon_manager = engine.AddonManager(paths.global_addons_dir(), self.cfg.get("disabled_addons", []))
        addon_schemas, addon_handlers, addon_commands = addon_manager.load()
        for addon_schema in addon_schemas:
            addon_name = addon_schema.get("function", {}).get("name")
            if not addon_name or addon_name in handlers:
                self.activity.append(f"Skipped add-on tool with a conflicting name: {addon_name or '(unnamed)'}")
                continue
            raw_schemas.append(addon_schema)
            handlers[addon_name] = addon_handlers[addon_name]
        raw_handlers = dict(handlers)
        registry=UnifiedToolNamespace()
        for schema in raw_schemas:
            original=schema.get("function",{}).get("name")
            if original and callable(handlers.get(original)):
                # Skill and add-on schemas are already namespaced by their loaders.
                if original in skill_handlers:
                    meta = next((m for m in skill_meta if original in m.get("_tool_names", {})), {})
                    folder = meta.get("_folder_name") or meta.get("name") or "skill"
                    raw_name = meta.get("_tool_names", {}).get(original, original)
                    registry.register_named(original, folder, "skill", raw_name, schema, handlers[original])
                elif original in addon_handlers:
                    identity = addon_manager.tool_identities.get(original, {})
                    registry.register_named(original, identity.get("namespace", "addon"), "addon",
                                            identity.get("original_name", original), schema, handlers[original])
                else:
                    registry.register("core", "core", schema, handlers[original], original_name=original)
        schemas=registry.schemas
        handlers=registry.callables
        original_names={name:identity.original_name for name,identity in registry.identities.items()}
        loop_guard=AgentLoopGuard(max_identical_calls=2,max_similar_searches=3,workspace=WORKSPACE)
        progress=ProgressTracker()
        progress.reset(user)
        readonly_names={"read_file","glob_files","grep_files","web_search","web_fetch","task_status"}
        active_schemas = schemas if self.mode == "Build" else [x for x in schemas if original_names.get(x.get("function",{}).get("name")) in readonly_names]
        delegation_requested=self.mode == "Build" and bool(re.search(r"\b(use|with|via|through|delegate to)\b.{0,30}\b(sub.?agents?|parallel agents?)\b|\b(sub.?agents?)\b.{0,30}\b(required|must|please use)\b",user,re.I))
        delegation_started=set()
        delegation_prompted=False
        loaded_skill_names = ", ".join(str(m.get("name", "skill")) for m in skill_meta) or "none"
        loaded_addon_names = ", ".join(x.name for x in addon_manager.infos if x.enabled and not x.error) or "none"
        history=[{"role":"system","content":f"You are Agent Code, a general research and coding agent, not just a code generator. Work only inside this workspace: {WORKSPACE}. Current mode: {self.mode}. Native Skills available: {loaded_skill_names}. Application Add-ons available: {loaded_addon_names}. For current facts, comparisons, unfamiliar technology, APIs, troubleshooting, or research questions, use web_search and follow relevant results with web_fetch; prefer primary/authoritative sources, cite source titles and URLs, separate evidence from inference, and never invent sources. For coding tasks, research docs when details are unfamiliar or likely to have changed, but do not browse unnecessarily for simple edits. In Plan mode you MUST only inspect and explain a concrete plan; do not call write, edit, append, shell, or any state-changing tool. No implementation until the user explicitly switches to Build mode and submits/approves the task. In Build mode you may use available tools subject to their restrictions. Ask before destructive actions. Tools use their registered namespaces; never invent tool names. Avoid repeating identical tool calls; reuse unchanged file reads and change strategy when searches stop producing new information. {('The user explicitly requested subagents: launch at least one focused task, then collect and integrate its result.' if delegation_requested else '')}"}]
        prior_messages = self.messages[:-1] if self.messages and self.messages[-1] == ("user", user) else self.messages
        for role,content in prior_messages[-16:]:
            if role in ("user","assistant"):
                history.append({"role":role,"content":self._chat_text(content)})
        history.append({"role":"user","content":user})
        self.notice="Working…"; self.activity.append("Task started: "+user[:160])
        try:
            while True:
                if self.cancel_event.is_set():
                    answer = "Task stopped by user."
                    self.activity.append("Task stopped by user.")
                    break
                self.activity.append("Requesting model response…")
                # Stream every response so slow/large generations remain visible.
                # Assemble tool-call deltas before dispatch; partial JSON is never run.
                self.stream_text = ""
                self.messages.append(("assistant", ""))
                stream = client.chat.completions.create(
                    model=model, messages=history, tools=active_schemas or None,
                    tool_choice=("auto" if active_schemas else "none"), stream=True,
                    timeout=600,
                )
                content_parts=[]
                tool_parts={}
                try:
                    for chunk in stream:
                        if self.cancel_event.is_set():
                            close=getattr(stream,"close",None)
                            if callable(close): close()
                            break
                        choices=getattr(chunk,"choices",[]) or []
                        if not choices: continue
                        delta=getattr(choices[0],"delta",None)
                        if delta is None: continue
                        piece=getattr(delta,"content",None)
                        if isinstance(piece,str) and piece:
                            content_parts.append(piece)
                            self.stream_text += piece
                            self.messages[-1] = ("assistant", self.stream_text)
                        for call in (getattr(delta,"tool_calls",None) or []):
                            idx=engine._stream_tool_call_index(call,tool_parts)
                            slot=tool_parts.setdefault(idx,{"id":"","name":"","arguments":"","metadata":{}})
                            if getattr(call,"id",None): slot["id"]=call.id
                            slot["metadata"].update(engine._provider_metadata(call))
                            fn=getattr(call,"function",None)
                            if fn:
                                if getattr(fn,"name",None): slot["name"] += fn.name
                                if getattr(fn,"arguments",None): slot["arguments"] += fn.arguments
                finally:
                    close=getattr(stream,"close",None)
                    if callable(close):
                        try: close()
                        except Exception: pass
                if self.cancel_event.is_set():
                    answer="Task stopped by user."
                    self.activity.append("Task stopped by user during streaming.")
                    break
                from types import SimpleNamespace
                assembled_calls=[]
                for idx,slot in sorted(tool_parts.items()):
                    if not slot["id"]: slot["id"]="call_"+uuid.uuid4().hex
                    assembled_calls.append(SimpleNamespace(id=slot["id"],type="function",extra_content=slot["metadata"].get("extra_content"),function=SimpleNamespace(name=slot["name"],arguments=slot["arguments"])))
                msg=SimpleNamespace(content="".join(content_parts),tool_calls=assembled_calls)
                # The streamed assistant placeholder becomes commentary when tools
                # follow, or the final answer when no tools were requested.
                self.messages.pop()
                if self.cancel_event.is_set():
                    answer = "Task stopped by user."
                    self.activity.append("Task stopped by user.")
                    break
                if not msg.tool_calls:
                    answer=self._chat_text(msg.content) if msg.content else "The model returned an empty response. Try again or choose another model."
                    self.activity.append("Agent response ready.")
                    if delegation_requested:
                        if not delegation_started and not delegation_prompted:
                            delegation_prompted=True
                            history.append({"role":"system","content":"You have not fulfilled the user's explicit subagent requirement. Launch at least one focused task using core_task, then call core_task_status to retrieve and integrate its result before responding."})
                            continue
                        if delegation_started:
                            deadline=time.monotonic()+90
                            while time.monotonic()<deadline and not self.cancel_event.is_set():
                                with _SUBAGENT_JOBS_LOCK:
                                    pending=[jid for jid in delegation_started if _SUBAGENT_JOBS.get(jid,{}).get("status")=="running"]
                                if not pending: break
                                time.sleep(0.4)
                            with _SUBAGENT_JOBS_LOCK:
                                summaries=[f"{jid} [{_SUBAGENT_JOBS.get(jid,{}).get('status','unknown')}]: {_SUBAGENT_JOBS.get(jid,{}).get('result','Still running.')[:4000]}" for jid in delegation_started]
                            history.append({"role":"system","content":"Subagent results; integrate completed work and do not claim unfinished work succeeded:\n"+"\n\n".join(summaries)})
                            delegation_requested=False
                            continue
                    break
                # Some providers include useful user-facing commentary in the same
                # assistant turn as tool calls. Preserve it in the visible transcript.
                if msg.content and str(msg.content).strip():
                    self.messages.append(("assistant", str(msg.content).strip()))
                assistant_history={"role":"assistant","content":msg.content or "","tool_calls":[engine._tool_call_history_item(tc) for tc in msg.tool_calls]}
                assistant_history.update(engine._provider_metadata(msg))
                history.append(assistant_history)
                for tc in msg.tool_calls:
                    if self.cancel_event.is_set():
                        answer = "Task stopped by user."
                        self.activity.append("Task stopped by user.")
                        break
                    name=tc.function.name
                    original_name=original_names.get(name,name)
                    try:
                        args=json.loads(tc.function.arguments or "{}")
                        from .agent import describe_activity, describe_tool_result
                        action_label = describe_activity(original_name, args)
                    except Exception:
                        args = {}
                        action_label = "Working with project files" if original_name in ("read_file", "write_file", "edit_file", "append_file") else "Running a tool"
                    self.activity.append(action_label + "…")
                    self.notice=action_label + "…"
                    try:
                        loop_block=loop_guard.before_call(original_name,args)
                        cached=loop_guard.cached_read(original_name,args) if not loop_block else None
                        delegation_block = (delegation_requested and not delegation_started
                                            and original_name in {"write_file","append_file","edit_file","shell_run","background_shell"})
                        if delegation_block:
                            result="DELEGATION_REQUIRED: launch a focused subagent with core_task before implementing, as the user requested."
                        elif loop_block:
                            result=loop_block
                        elif cached is not None:
                            result=cached
                            self.activity.append("Reused unchanged file-read result.")
                        elif name not in handlers: result="ERROR: tool is not available in TUI"
                        elif self.mode == "Plan" and original_name not in readonly_names:
                            result="BLOCKED: Plan mode is strictly read-only. Present the plan without attempting implementation. The user must switch to Build mode explicitly."
                        else:
                            if original_name == "read_file":
                            # Keep previews bounded; the model can request a different offset/limit.
                                args["limit"] = max(1, min(400, int(args.get("limit", 120))))
                            result=handlers[name](**args)
                    except Exception as exc: result=f"ERROR: {exc}"
                    result_text = str(result)
                    loop_guard.after_call(original_name,args,result_text)
                    progress.record(original_name,args,result_text)
                    if original_name in ("shell_run", "background_shell") and result_text.strip() == "(no output)":
                        result_text = "Command completed successfully (no stdout or stderr)."
                    try:
                        user_result = describe_tool_result(original_name, args, result_text)
                        if original_name == "shell_run" and result_text.startswith("Command completed successfully"):
                            user_result = "Command completed successfully (no output)"
                    except Exception:
                        user_result = "Tool finished" if not result_text.startswith("ERROR") else "Tool failed"
                    if original_name == "read_file" and not result_text.startswith("ERROR"):
                        header = result_text.splitlines()[0] if result_text else ""
                        match = re.search(r"lines (\d+)-(\d+) of (\d+)", header)
                        if match:
                            count = int(match.group(2)) - int(match.group(1)) + 1
                            user_result = f"Read {count} lines from {args.get('path', 'file')} (of {match.group(3)} total; preview limit {args.get('limit', 120)})"
                    self.activity.append(user_result)
                    # Keep full tool data for the model, but show only a compact
                    # outcome in Chat so the final answer remains visible.
                    self.messages.append(("tool", user_result))
                    self.tool_details.append(
                        f"TOOL: {name}\nARGUMENTS: {json.dumps(args, ensure_ascii=False, default=str)}\nRESULT: {result_text[:12000]}"
                    )
                    self.tool_details = self.tool_details[-100:]
                    history.append({"role":"tool","tool_call_id":tc.id,"content":result_text[:12000]})
        except Exception as e:
            answer=f"Request failed: {type(e).__name__}: {e}"
            if "thought_signature" in str(e).lower():
                answer += "\nGemini tool-call metadata was rejected. Agent Code preserves the signature now; verify that any custom proxy forwards extra_content.google.thought_signature unchanged. Older chats created before this fix may need a new chat."
            if self.messages and self.messages[-1][0] == "assistant" and not self.messages[-1][1]:
                self.messages.pop()
            self.activity.append("Provider request failed: " + answer[:500])
        self.messages.append(("assistant",answer)); self.activity.append("Task finished."); self.activity=self.activity[-200:]; self.notice="Ready"; self.busy=False

    def install_podman(self):
        if shutil.which("podman"):
            self.notice="Podman is already installed."; return
        if not os.path.exists("/etc/os-release"):
            self.notice="Automatic Podman installation is supported on common Linux distributions."; return
        if shutil.which("apt-get"): cmd=["sudo","apt-get","install","-y","podman"]
        elif shutil.which("dnf"): cmd=["sudo","dnf","install","-y","podman"]
        elif shutil.which("pacman"): cmd=["sudo","pacman","-S","--needed","--noconfirm","podman"]
        elif shutil.which("zypper"): cmd=["sudo","zypper","--non-interactive","install","podman"]
        elif shutil.which("apk"): cmd=["sudo","apk","add","podman"]
        else: self.notice="Unsupported package manager; install Podman manually."; return
        answer=self.prompt("Install Podman using system package manager? type yes", "no")
        if answer.lower()!="yes": self.notice="Podman install cancelled."; return
        try:
            r=subprocess.run(cmd,timeout=600,capture_output=True,text=True)
            self.notice="Podman installed; initialize/start its engine if needed." if r.returncode==0 else (r.stderr or "Podman install failed")[-150:]
        except Exception as exc: self.notice=f"Podman install failed: {exc}"

    def _answer_worker(self, user):
        try:
            self.answer(user)
        except Exception as exc:
            self.messages.append(("assistant", f"Request failed: {type(exc).__name__}: {exc}"))
            self.activity.append(f"Task failed: {type(exc).__name__}: {exc}")
        finally:
            self.busy = False
            self.notice = "Ready"

    def _clear_chat(self):
        if self.busy:
            self.notice = "Stop the current task before clearing the chat."
            return
        self.messages.clear()
        self.scroll = 0
        self.tool_details.clear()
        self.activity_scroll = 0
        self.activity = ["Chat cleared."]
        self.notice = "Chat cleared."

    def _stop_answer(self):
        if not self.busy:
            self.notice = "No agent task is running."
            return
        self.cancel_event.set()
        self.notice = "Stop requested — waiting for the current network/tool operation to return…"
        self.activity.append("Stop requested by user.")

    def _run_direct_command(self, command):
        """Run an explicit terminal command without sending it to the model."""
        from . import agent as engine
        command = command.strip()
        if not command:
            return
        self.messages.append(("user", "$ " + command))
        self.notice = "Running terminal command…"
        self.activity.append("Terminal [" + self.cwd + "]: " + command[:140])
        try:
            import shlex
            parts = shlex.split(command, posix=(os.name != "nt"))
            if parts and parts[0] == "cd":
                target = parts[1] if len(parts) > 1 else "."
                if len(parts) > 2:
                    raise ValueError("cd accepts one directory at a time")
                root = WORKSPACE.resolve()
                candidate = (root / self.cwd / target).resolve()
                candidate.relative_to(root)
                if not candidate.is_dir():
                    raise NotADirectoryError(target)
                self.cwd = candidate.relative_to(root).as_posix() or "."
                result = f"Working directory: /workspace/{'' if self.cwd == '.' else self.cwd}"
            else:
                result = engine.tool_shell_run(command, cwd=self.cwd)
            result = str(result or "")
            if not result.strip() or result.strip() == "(no output)":
                result = "Command completed successfully (no stdout or stderr)."
            self.messages.append(("tool", "$ " + command + "\n" + result[:12000]))
            self.activity.append("Terminal command finished.")
            self.notice = "Terminal command finished."
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.messages.append(("tool", "$ " + command + "\nERROR: " + message))
            self.activity.append("Terminal command failed: " + message)
            self.notice = "Terminal command failed."

    def _dispatch_input(self, user):
        low = user.strip().lower()
        if low in ("/clear", "/reset", "clear"):
            self._clear_chat()
            return
        if low in ("/stop", "stop"):
            self._stop_answer()
            return
        if low in ("/help", "help"):
            self.page = "Help"
            self.notice = "Help opened."
            return
        if user.startswith("!"):
            self._run_direct_command(user[1:])
            return
        # Familiar executable commands are run directly. Natural-language prompts
        # remain model requests; use ! to force any shell command unambiguously.
        try:
            import shlex
            parts = shlex.split(user, posix=(os.name != "nt"))
            executable = parts[0] if parts else ""
            known_shell_builtins = {"cd", "pwd", "echo", "printf"}
            if executable in known_shell_builtins or shutil.which(executable):
                self._run_direct_command(user)
                return
        except (ValueError, OSError):
            pass
        self._start_answer(user)

    def _start_answer(self, user):
        if self.busy:
            self.notice = "Agent is already working; wait for the current task to finish."
            return
        self.busy = True
        self.cancel_event.clear()
        self.messages.append(("user", user))
        self.activity.append("Task queued: " + user[:160])
        threading.Thread(target=self._answer_worker, args=(user,), daemon=True, name="agent-code-tui-agent").start()

    def run(self):
        pages = self.PAGES
        while self.running:
            # All curses drawing and event handling stay on this thread.
            try:
                while True:
                    event, payload = self.events.get_nowait()
                    if event == "models":
                        self.model_fetching = False
                        self.select_searched_model(payload)
            except queue.Empty:
                pass
            self.draw()
            try:
                key = self.s.get_wch()
            except curses.error:
                continue
            if key is None:
                continue
            if key in (curses.KEY_F10, "\x03"):
                if key == "\x03" and self.busy:
                    self._stop_answer()
                else:
                    self.running = False
                continue
            if key == curses.KEY_F2:
                self.mode = "Plan" if self.mode == "Build" else "Build"
                self.notice = "Mode changed to " + self.mode
                continue
            if key == curses.KEY_F5:
                self._stop_answer()
                continue
            if key == "\x0c":
                self._clear_chat()
                continue
            if key == "\t":
                self.page = pages[(pages.index(self.page) + 1) % len(pages)]
                self.selected_index = 0
                continue
            if key == "\x1b":
                if self.page == "Chat":
                    self.input = ""
                    self.input_cursor = 0
                continue
            if key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                amount = max(3, self.s.getmaxyx()[0] // 2)
                delta = amount if key == curses.KEY_PPAGE else -amount
                if self.page == "Activity":
                    self.activity_scroll = max(0, self.activity_scroll + delta)
                elif self.page == "Chat":
                    self.scroll = max(0, self.scroll + delta)
                else:
                    self.selected_index = max(0, self.selected_index + (1 if delta < 0 else -1))
                continue
            if self.page == "Chat":
                if key in ("\n", curses.KEY_ENTER, 10, 13):
                    if self.input.strip():
                        user = self.input.strip()
                        self.input = ""
                        self.input_cursor = 0
                        self._dispatch_input(user)
                    continue
                if key in (curses.KEY_LEFT,):
                    self.input_cursor = max(0, self.input_cursor - 1)
                    continue
                if key in (curses.KEY_RIGHT,):
                    self.input_cursor = min(len(self.input), self.input_cursor + 1)
                    continue
                if key in (curses.KEY_HOME, "\x01"):
                    self.input_cursor = 0
                    continue
                if key in (curses.KEY_END, "\x05"):
                    self.input_cursor = len(self.input)
                    continue
                if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                    if self.input_cursor:
                        self.input = self.input[:self.input_cursor - 1] + self.input[self.input_cursor:]
                        self.input_cursor -= 1
                    continue
                if key == curses.KEY_DC:
                    if self.input_cursor < len(self.input):
                        self.input = self.input[:self.input_cursor] + self.input[self.input_cursor + 1:]
                    continue
                if key == "\x15":  # Ctrl+U
                    self.input = ""
                    self.input_cursor = 0
                    continue
                if key == "\x17":  # Ctrl+W
                    before = self.input[:self.input_cursor]
                    trimmed = before.rstrip()
                    cut = len(trimmed)
                    while cut and not trimmed[cut - 1].isspace():
                        cut -= 1
                    self.input = before[:cut] + self.input[self.input_cursor:]
                    self.input_cursor = cut
                    continue
                if isinstance(key, str) and len(key) == 1 and key.isprintable():
                    self.input = self.input[:self.input_cursor] + key + self.input[self.input_cursor:]
                    self.input_cursor += 1
                    continue
            # Global page selection is available whenever the composer is not active.
            if isinstance(key, str) and key in tuple(str(i) for i in range(1, len(pages) + 1)):
                self.page = pages[int(key) - 1]
                self.selected_index = 0
                continue
            if key in ("q", "Q") and self.page != "Chat":
                self.running = False
                continue
            if key in ("p", "P") and self.page in ("Settings", "Help"):
                self.page = "Settings"; self.configure("provider"); continue
            if key in ("m", "M") and self.page in ("Settings", "Help"):
                self.page = "Settings"; self.fetch_models(); continue
            if key in ("i", "I") and self.page in ("Settings", "Help"):
                if self.page == "Settings": self.install_podman()
                else: self.page = "Skills"; self.manage_skill("install")
                continue
            if key in ("k", "K") and self.page in ("Settings", "Help"):
                self.page = "Settings"; self.configure("key"); continue
            if self.page == "Skills" and key in ("t", "T"):
                self.manage_skill("toggle")
            elif self.page == "Skills" and key in ("i", "I"):
                self.manage_skill("install")
            elif self.page == "Add-ons" and key in ("t", "T"):
                self.manage_addon("toggle")
            elif self.page == "Add-ons" and key in ("n", "N"):
                self.manage_addon("create")
            elif self.page == "Add-ons" and key in ("o", "O"):
                self.manage_addon("open")
            elif self.page == "MCP" and key in ("a", "A"):
                self.mcp_configure("add")
            elif self.page == "MCP" and key in ("e", "E"):
                self.mcp_configure("edit")
            elif self.page == "MCP" and key in ("t", "T"):
                self.mcp_configure("toggle")
            elif self.page == "MCP" and key in ("d", "D"):
                self.mcp_configure("delete")
            elif self.page == "MCP" and key in ("c", "C"):
                self.mcp_configure("connect")
            elif key in (curses.KEY_UP, "k") and self.page != "Chat":
                self.selected_index = max(0, self.selected_index - 1)
            elif key in (curses.KEY_DOWN, "j") and self.page != "Chat":
                self.selected_index += 1


def main():
    if not (os.isatty(0) and os.isatty(1)):
        print("Agent Code TUI requires an interactive terminal. Run: agent-code tui"); return 2
    try: curses.wrapper(lambda scr:TUI(scr).run())
    except KeyboardInterrupt: pass
    return 0

if __name__=="__main__": raise SystemExit(main())
