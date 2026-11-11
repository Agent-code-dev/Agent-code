"""Monitor-free terminal interface for Agent Code. Uses only terminal UI APIs."""
from __future__ import annotations
import curses, json, os, platform, queue, shutil, subprocess, textwrap, threading, time, uuid, re, unicodedata
from pathlib import Path
from . import __version__
from . import paths
from .model_protocols import (resolve_model_profile, protocol_request_options,
                              parse_minimax_text_tool_calls, MiniMaxStreamTextFilter,
                              reasoning_payload)
from .security import security_prompt_directive, mark_untrusted_tool_output

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
    from .settings_store import load_config
    return load_config()

def write_config(cfg):
    from .settings_store import save_config
    return save_config(cfg)

def api_keys(cfg):
    keys = cfg.get("openai_api_keys", [])
    if isinstance(keys, str):
        keys = [x.strip() for x in keys.replace("\n", ",").split(",") if x.strip()]
    if not keys and os.getenv("OPENAI_API_KEY"):
        keys = [os.environ["OPENAI_API_KEY"]]
    return keys


class TUI:
    def __init__(self, screen):
        self.s=screen; self.cfg=read_config(); self.messages=[]; self.notice="Welcome. Press ? for help."; self.mode="Build"
        from .interactive import AskUserBroker
        self.ask_user_broker = AskUserBroker(on_question=lambda event: self.events.put(("ask_user", event)))
        self.input=""; self.scroll=0; self.cwd="."; self.page="Chat"; self.task_selection=0; self.task_detail_id=None; self.running=True; self.busy=False; self.cancel_event=threading.Event(); self.events=queue.Queue(); self.activity=["Ready — send a task to watch agent progress."]; self.tool_details=[]; self.activity_scroll=0; self.stream_text=""
        curses.curs_set(1); curses.start_color(); curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1); curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_GREEN, -1); curses.init_pair(4, curses.COLOR_YELLOW, -1)
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

    def draw(self):
        self.s.erase(); h,w=self.s.getmaxyx()
        self.safe_add(0,0," AGENT CODE  "+__version__+"  ◆  TERMINAL WORKSPACE ",curses.color_pair(2),w-1)
        sidebar=max(19,min(25,w//4)) if w >= 72 else 0
        content=sidebar+2 if sidebar else 1
        if sidebar:
            self.safe_add(2,1,"NAVIGATION",curses.color_pair(1)|curses.A_BOLD)
            for i,name in enumerate(["Chat","Workspace","Tasks","Activity","Skills","MCP","Settings","Add-ons","Help"]):
                self.safe_add(4+i,2,("▸ " if name==self.page else "  ")+name,curses.A_BOLD if name==self.page else 0)
            self.safe_add(12,1,"WORKSPACE",curses.color_pair(1)|curses.A_BOLD)
            self.safe_add(13,1,str(WORKSPACE)[-max(1,sidebar-2):])
            self.safe_add(15,1,"MODE",curses.color_pair(1)|curses.A_BOLD)
            self.safe_add(16,2,"["+self.mode+"]  (F2 to toggle)")
            for y in range(1,h-2): self.safe_add(y,sidebar,"│")
        else:
            self.safe_add(1,1,"1 Chat  2 Workspace  3 Tasks  4 Activity  5 Skills  6 MCP  7 Settings  8 Add-ons  9 Help",curses.A_DIM)
        title={"Chat":"Chat / Agent","Workspace":"Workspace Explorer","Tasks":"Task Workspace / History","Activity":"Live Agent Activity / Mini IDE","Skills":"Installed Skills","MCP":"Remote MCP","Settings":"Provider Settings","Add-ons":"Application Add-ons","Help":"Keyboard Shortcuts"}.get(self.page,self.page)
        self.safe_add(2,content,title,curses.color_pair(1)|curses.A_BOLD)
        self.safe_add(h-1,0, ("Provider: "+str(self.cfg.get("provider_name", "OpenAI"))+"  •  "+self.notice)[:max(1,w-1)], curses.A_DIM)
        if self.page=="Chat":
            available=max(1,h-9)
            rendered = self.render_chat_lines(self.messages, max(1,w-content-3))
            visible, max_scroll, self.scroll = self.visible_chat_lines(rendered, available, self.scroll)
            for y,(line,role) in enumerate(visible,start=4):
                color = curses.color_pair(3) if role == "assistant" else curses.color_pair(4)
                attr = color|curses.A_BOLD if line.endswith("─────────────────────────") else 0
                self.safe_add(y,content,line,attr)
            if max_scroll:
                self.safe_add(3,content, f"Transcript: {self.scroll} lines back  (PgUp/PgDn scroll)", curses.A_DIM)
            self.safe_add(h-4,content,"─"*max(1,w-content-2),curses.color_pair(1))
            if self.busy and not self.messages:
                self.safe_add(4,content,"Connecting to provider…",curses.A_DIM)
            elif self.busy and (not rendered or not any(role == "assistant" for role, _ in self.messages)):
                self.safe_add(4,content,"Agent is working. Progress appears here when the provider responds; see Activity for tool updates.",curses.A_DIM)
            self.safe_add(h-3,content,"> "+self.input,curses.A_BOLD)
            self.safe_add(h-2,content,"Enter send • !command shell • F5 stop • Ctrl+L clear • PgUp/PgDn scroll",curses.A_DIM)
        elif self.page=="Workspace":
            try: files=sorted(WORKSPACE.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower()))
            except OSError: files=[]
            if not files: self.safe_add(4,content,"Workspace is empty. Ask the agent to create a project.")
            for i,p in enumerate(files[:max(1,h-7)]): self.safe_add(4+i,content, ("📁 " if p.is_dir() else "   ")+p.name)
        elif self.page=="Tasks":
            from .interactive import TaskHistoryStore
            from .paths import global_data_dir
            history = TaskHistoryStore(global_data_dir() / "tasks")
            tasks = history.list_states(limit=100)
            if self.task_detail_id:
                selected = history.get(self.task_detail_id)
                if selected is None:
                    self.task_detail_id = None
                    self.safe_add(4,content,"Selected task is no longer available.")
                else:
                    self.safe_add(4,content,f"Task: {selected.objective[:max(1,w-content-10)]}",curses.A_BOLD)
                    self.safe_add(5,content,f"ID: {selected.task_id}  |  Status: {selected.status}  |  Events: {len(selected.trajectory)}",curses.A_DIM)
                    self.safe_add(7,content,"PLAN",curses.color_pair(1)|curses.A_BOLD)
                    row=8
                    for step in selected.plan[:max(0,(h-13)//2)]:
                        label = step.get("title") or step.get("step") or step.get("description") or str(step)
                        self.safe_add(row,content,"• "+str(label)); row += 1
                    self.safe_add(min(row+1,h-5),content,"TRAJECTORY",curses.color_pair(1)|curses.A_BOLD)
                    row=min(row+2,h-4)
                    for event in selected.trajectory[-max(0,h-row-2):]:
                        stamp=time.strftime("%H:%M:%S",time.localtime(event.get("time",0)))
                        self.safe_add(row,content,f"{stamp}  {event.get('kind','event')}: {event.get('summary','')}")
                        row += 1
                    self.safe_add(h-3,content,"Esc: task list  •  R: run objective again (new task)",curses.A_DIM)
            else:
                self.safe_add(4,content,"RECENT TASKS  ·  Enter: inspect  ·  R: run selected objective",curses.color_pair(1)|curses.A_BOLD)
                if not tasks:
                    self.safe_add(6,content,"No saved tasks yet. Start a task in Chat to populate history.")
                for i,task in enumerate(tasks[:max(1,h-8)]):
                    marker = "▸ " if i == self.task_selection else "  "
                    stamp=time.strftime("%Y-%m-%d %H:%M",time.localtime(task.updated_at))
                    label=f"{marker}{task.status.upper():16} {stamp}  {task.objective}"
                    self.safe_add(6+i,content,label,curses.A_REVERSE if i == self.task_selection else 0)
                self.safe_add(h-3,content,"↑/↓ select  •  Enter inspect  •  R rerun objective  •  Tab return",curses.A_DIM)
        elif self.page=="Activity":
            self.safe_add(4,content,"LIVE ACTIVITY — tool calls and results, not private model reasoning",curses.color_pair(1))
            self.safe_add(6,content,"Workspace: "+str(WORKSPACE))
            # Activity is a complete chronological event log. Tool arguments and
            # results are included here (never private model reasoning).
            lines = []
            for item in self.activity:
                lines.extend(textwrap.wrap(str(item), max(10,w-content-3), replace_whitespace=False) or [""])
            for item in self.tool_details:
                lines.append("─ TOOL DETAIL ─")
                lines.extend(textwrap.wrap(str(item), max(10,w-content-3), replace_whitespace=False) or [""])
            viewport=max(1,h-12)
            max_back=max(0,len(lines)-viewport)
            self.activity_scroll=max(0,min(self.activity_scroll,max_back))
            end=len(lines)-self.activity_scroll
            start=max(0,end-viewport)
            for i,line in enumerate(lines[start:end]):
                self.safe_add(8+i,content,line)
            if max_back:
                self.safe_add(6,content,f"Activity log · {len(lines)} lines · {self.activity_scroll} lines back (PgUp/PgDn)",curses.A_DIM)
            self.safe_add(h-3,content,"Full activity and tool details. Press 1 for Chat.",curses.A_DIM)
        elif self.page=="Skills":
            from .loader import discover_skills
            skills=discover_skills(paths.global_skills_dir())
            disabled=set(self.cfg.get("disabled_skills", []))
            self.safe_add(4,content,f"Installed skills: {len(skills)}  ·  Enabled: {sum(s['name'] not in disabled for s in skills)}")
            for i,item in enumerate(skills[:max(1,h-9)]):
                state="ON" if item["name"] not in disabled else "OFF"
                self.safe_add(5+i,content,f"[{state}] {item['name']} — {item.get('description','')}")
            self.safe_add(h-4,content,"t Toggle selected skill  ·  i Install bundled skills  ·  m Open Skill Store (GUI)",curses.A_DIM)
            self.safe_add(h-3,content,"Press t to choose a skill and toggle its enabled state.",curses.A_DIM)
        elif self.page=="MCP":
            servers=self.cfg.get("mcp_servers", [])
            if not isinstance(servers,list): servers=[]
            self.safe_add(4,content,"REMOTE MCP CONFIGURATION  (HTTP/SSE Streamable HTTP)",curses.color_pair(1))
            if not servers: self.safe_add(6,content,"No MCP servers configured yet.")
            for i,server in enumerate(servers[:max(1,h-12)]):
                status="ON" if server.get("enabled",True) else "OFF"
                self.safe_add(6+i,content,f"{i+1}. [{status}] {server.get('name','unnamed')}  {server.get('url','')}")
            self.safe_add(h-5,content,"a Add  e Edit  t Toggle enabled  d Delete  c Connect/test  (choose number first)",curses.A_DIM)
            self.safe_add(h-4,content,"MCP headers are stored in agent_config.json; avoid sharing that file.",curses.A_DIM)
        elif self.page=="Settings":
            for i,line in enumerate([f"Provider: {self.cfg.get('provider_name','OpenAI')}",f"Base URL: {self.cfg.get('openai_base_url') or PROVIDERS.get(self.cfg.get('provider_name','OpenAI'),'') or '(not set)'}",f"Model: {self.cfg.get('openai_model') or '(not selected)'}",f"API key: {'configured' if api_keys(self.cfg) else 'not configured'}","p: select provider + URL   m: fetch model list   k: set API key"]): self.safe_add(4+i,content,line)
        elif self.page=="Add-ons":
            from .addons import AddonManager
            manager=AddonManager(paths.global_addons_dir(), self.cfg.get("disabled_addons", []))
            infos=manager.discover()
            disabled=set(self.cfg.get("disabled_addons", []))
            self.safe_add(4,content,f"Installed add-ons: {len(infos)}  ·  Enabled: {sum(x.name not in disabled for x in infos)}")
            for i,item in enumerate(infos[:max(1,h-9)]):
                state="ON" if item.enabled else "OFF"
                self.safe_add(5+i,content,f"[{state}] {item.name} v{item.version} — {item.error or item.description}")
            self.safe_add(h-4,content,"t Toggle selected add-on  ·  n Create starter add-on  ·  o Open add-on folder",curses.A_DIM)
            self.safe_add(h-3,content,"Add-ons are trusted Python extensions; review addon.py before enabling.",curses.A_DIM)
        else:
            for i,line in enumerate(["Tab: cycle pages","1-9: Chat, Workspace, Tasks, Activity, Skills, MCP, Settings, Add-ons, Help","Enter: send message; !command: run a shell command directly", "F5 or Ctrl+C: stop current agent task", "Ctrl+L or /clear: clear chat", "i: install Podman sandbox runtime","F2: toggle Plan / Build mode","p: choose provider and model (Settings)","m: fetch available models (Settings)","k: configure API key","Skills: t toggle selected; i install bundled skills","Add-ons: t toggle selected; n create template","MCP page: a add, e edit, t toggle, d delete, c connect/test","F10: quit","The terminal UI works over SSH without a monitor or desktop session."]): self.safe_add(4+i,content,line)
        self.s.refresh()
    def prompt(self,title,initial=""):
        curses.echo(); curses.curs_set(1); h,w=self.s.getmaxyx(); old_timeout = 150
        try: old_timeout = self.s.getdelay()
        except Exception: pass
        self.s.timeout(-1)
        self.safe_add(h-1,0,(title+" ")[:w-1],curses.color_pair(2)); self.s.clrtoeol(); self.s.refresh()
        try:
            value=self.s.getstr(h-1,min(len(title)+1,max(0,w-2)),max(1,w-len(title)-3)).decode("utf-8","replace")
        except (curses.error, UnicodeError, OSError):
            value=initial
        finally:
            try: curses.noecho()
            except curses.error: pass
            try: self.s.timeout(old_timeout)
            except curses.error: pass
        return value.strip() or initial
    def choose(self,title,options,current=None):
        options=list(options)
        if not options: return None
        idx=options.index(current) if current in options else 0
        while True:
            self.s.erase(); h,w=self.s.getmaxyx()
            self.safe_add(1,2,title,curses.A_BOLD|curses.color_pair(1))
            for i,opt in enumerate(options[:max(1,h-5)]):
                self.safe_add(3+i,3,("❯ " if i==idx else "  ")+str(opt),curses.A_REVERSE if i==idx else 0)
            self.safe_add(h-1,2,"↑/↓ move • Enter select • Esc cancel",curses.A_DIM); self.s.refresh()
            # The main screen uses a finite curses timeout to stay responsive.
            # A timeout is reported as curses.error; it is not a fatal input error.
            try:
                key=self.s.get_wch()
            except curses.error:
                continue
            if key in (curses.KEY_UP,"k") : idx=(idx-1)%len(options)
            elif key in (curses.KEY_DOWN,"j"): idx=(idx+1)%len(options)
            elif key in ("\n",curses.KEY_ENTER,10,13): return options[idx]
            elif key==27: return None
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
        from .interactive import TaskState, TaskStateStore
        task_state = TaskState(uuid.uuid4().hex, str(user), status="running")
        try:
            from .paths import global_data_dir
            from .interactive import TaskHistoryStore
            task_history = TaskHistoryStore(global_data_dir() / "tasks")
            task_store = task_history.store_for(task_state.task_id)
            task_store.save(task_state)
        except Exception as state_exc:
            task_store = None
            self.activity.append(f"Task history unavailable: {type(state_exc).__name__}")

        def record_task_event(kind, summary, status=None):
            task_state.trajectory.append({"time": time.time(), "kind": str(kind)[:40],
                                          "summary": str(summary)[:240]})
            if status:
                task_state.status = status
            if task_store:
                try:
                    task_store.save(task_state)
                except Exception as state_exc:
                    self.activity.append(f"Could not save task history: {type(state_exc).__name__}")

        record_task_event("started", str(user)[:240])
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
        model_profile = resolve_model_profile(provider, model, base)
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
                history_sub = [{"role":"system","content":f"You are an independent coding subagent. Job: {description}. Work only inside workspace {WORKSPACE}. You may read and edit files, but avoid unrelated files and report exactly what changed. The main agent is working concurrently; avoid overwriting files it may be editing. {security_prompt_directive()}"}, {"role":"user","content":str(prompt)}]
                try:
                    while True:
                        response_sub = client.chat.completions.create(
                            model=model, messages=history_sub, tools=sub_schemas,
                            **protocol_request_options(model_profile, has_tools=bool(sub_schemas)))
                        msg_sub = response_sub.choices[0].message
                        sub_calls = list(getattr(msg_sub, "tool_calls", None) or [])
                        sub_content = msg_sub.content or ""
                        if not sub_calls and model_profile.get("provider") == "minimax":
                            sub_calls, sub_content = parse_minimax_text_tool_calls(
                                sub_content, known_tool_names=set(sub_handlers))
                        if not sub_calls:
                            result_sub = sub_content or "(subagent returned no text)"
                            status_sub = "completed"
                            break
                        assistant_sub = {"role":"assistant", "content":sub_content,
                            "tool_calls":[{"id":tc.id,"type":"function","function":{"name":tc.function.name,"arguments":tc.function.arguments}} for tc in sub_calls]}
                        preserved_sub_reasoning = reasoning_payload(msg_sub, model_profile)
                        if preserved_sub_reasoning:
                            assistant_sub["reasoning_content"] = preserved_sub_reasoning
                        history_sub.append(assistant_sub)
                        for tc in sub_calls:
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
                            history_sub.append({"role":"tool","tool_call_id":tc.id,
                                                "content":mark_untrusted_tool_output(str(out_sub), 12000)})
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
        active_schemas = list(active_schemas) + [{
            "type": "function", "function": {
                "name": "ask_user",
                "description": "Ask the user for missing information or a decision, then wait for their answer.",
                "parameters": {"type": "object", "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}}
                }, "required": ["question"], "additionalProperties": False}
            }
        }]
        delegation_requested=self.mode == "Build" and bool(re.search(r"\b(use|with|via|through|delegate to)\b.{0,30}\b(sub.?agents?|parallel agents?)\b|\b(sub.?agents?)\b.{0,30}\b(required|must|please use)\b",user,re.I))
        delegation_started=set()
        delegation_prompted=False
        loaded_skill_names = ", ".join(str(m.get("name", "skill")) for m in skill_meta) or "none"
        loaded_addon_names = ", ".join(x.name for x in addon_manager.infos if x.enabled and not x.error) or "none"
        history=[{"role":"system","content":f"You are Agent Code, a general research and coding agent, not just a code generator. Work only inside this workspace: {WORKSPACE}. Current mode: {self.mode}. Native Skills available: {loaded_skill_names}. Application Add-ons available: {loaded_addon_names}. For current facts, comparisons, unfamiliar technology, APIs, troubleshooting, or research questions, use web_search and follow relevant results with web_fetch; prefer primary/authoritative sources, cite source titles and URLs, separate evidence from inference, and never invent sources. For coding tasks, research docs when details are unfamiliar or likely to have changed, but do not browse unnecessarily for simple edits. In Plan mode you MUST only inspect and explain a concrete plan; do not call write, edit, append, shell, or any state-changing tool. No implementation until the user explicitly switches to Build mode and submits/approves the task. In Build mode you may use available tools subject to their restrictions. Ask before destructive actions. Tools use their registered namespaces; never invent tool names. {security_prompt_directive()} Avoid repeating identical tool calls; reuse unchanged file reads and change strategy when searches stop producing new information. {('The user explicitly requested subagents: launch at least one focused task, then collect and integrate its result.' if delegation_requested else '')}"}]
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
                stream_options = protocol_request_options(model_profile, has_tools=bool(active_schemas))
                stream = client.chat.completions.create(
                    model=model, messages=history, tools=active_schemas or None,
                    stream=True, timeout=600, **stream_options,
                )
                content_parts=[]
                reasoning_parts=[]
                tool_parts={}
                minimax_filter = MiniMaxStreamTextFilter() if model_profile.get("provider") == "minimax" else None
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
                            visible_piece = minimax_filter.feed(piece) if minimax_filter else piece
                            if visible_piece:
                                self.stream_text += visible_piece
                                self.messages[-1] = ("assistant", self.stream_text)
                        reasoning_piece = getattr(delta, "reasoning_content", None)
                        if isinstance(reasoning_piece, str) and reasoning_piece:
                            reasoning_parts.append(reasoning_piece)
                        for call in (getattr(delta,"tool_calls",None) or []):
                            idx=getattr(call,"index",0)
                            slot=tool_parts.setdefault(idx,{"id":"","name":"","arguments":""})
                            if getattr(call,"id",None): slot["id"]=call.id
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
                    assembled_calls.append(SimpleNamespace(id=slot["id"],function=SimpleNamespace(name=slot["name"],arguments=slot["arguments"])))
                raw_content = "".join(content_parts)
                if minimax_filter:
                    trailing_visible = minimax_filter.finish()
                    if trailing_visible:
                        self.stream_text += trailing_visible
                        self.messages[-1] = ("assistant", self.stream_text)
                if not assembled_calls and model_profile.get("provider") == "minimax":
                    parsed_calls, visible_content = parse_minimax_text_tool_calls(
                        raw_content, known_tool_names=set(handlers))
                    assembled_calls.extend(parsed_calls)
                    raw_content = visible_content
                msg=SimpleNamespace(content=raw_content,tool_calls=assembled_calls,
                                    reasoning_content="".join(reasoning_parts))
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
                assistant_history = {"role":"assistant","content":msg.content or "","tool_calls":[{"id":tc.id,"type":"function","function":{"name":tc.function.name,"arguments":tc.function.arguments}} for tc in msg.tool_calls]}
                if model_profile.get("preserve_reasoning") and getattr(msg, "reasoning_content", None):
                    assistant_history["reasoning_content"] = msg.reasoning_content
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
                        if name == "ask_user":
                            from .interactive import UserQuestion
                            question = UserQuestion.create(args.get("question", ""), args.get("options") or ())
                            self.notice = "Waiting for your answer…"
                            self.activity.append("Agent Code is waiting for your answer.")
                            user_answer = self.ask_user_broker.ask(question, timeout=900)
                            result = json.dumps({"choice": user_answer.choice, "custom_text": user_answer.custom_text, "skipped": user_answer.skipped}, ensure_ascii=False)
                            loop_block = None
                            cached = None
                        else:
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
                                stateful_names = {"write_file", "append_file", "edit_file", "shell_run", "background_shell"}
                                ultra_unrestricted = bool(self.cfg.get("ultra_unrestricted_enabled", False))
                                unrestricted_host = (original_name in {"shell_run", "background_shell"}
                                    and bool(self.cfg.get("allow_unrestricted_host_shell", False))
                                    and not bool(self.cfg.get("podman_sandbox_enabled", False))
                                    and not ultra_unrestricted)
                                permission_mode = "auto" if ultra_unrestricted else str(self.cfg.get("permission_mode", "ask")).lower()
                                if original_name in stateful_names and permission_mode == "readonly":
                                    result = "DENIED: read-only permission profile is active."
                                elif (original_name in stateful_names and permission_mode == "ask") or unrestricted_host:
                                    if not hasattr(self, "ask_user_broker"):
                                        result = "DENIED: this TUI has no interactive confirmation channel for this state-changing action. Use the desktop or legacy TUI to approve it."
                                    else:
                                        from .interactive import UserQuestion
                                        title = ("Run this command through the unrestricted host shell? It may affect the entire computer."
                                                 if unrestricted_host else f"Allow this state-changing operation ({original_name})?\n{str(args)[:1200]}")
                                        approval = self.ask_user_broker.ask(UserQuestion.create(
                                            title, ["Allow this action", "Deny this action"],
                                            allow_custom=False, allow_skip=True), timeout=300)
                                        if approval.skipped or approval.choice != "Allow this action":
                                            result = "DENIED: user did not approve this action."
                                        else:
                                            if original_name == "read_file":
                                                args["limit"] = max(1, min(400, int(args.get("limit", 120))))
                                            result = handlers[name](**args)
                                else:
                                    if original_name == "read_file":
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
                        import re
                        match = re.search(r"lines (\d+)-(\d+) of (\d+)", header)
                        if match:
                            count = int(match.group(2)) - int(match.group(1)) + 1
                            user_result = f"Read {count} lines from {args.get('path', 'file')} (of {match.group(3)} total; preview limit {args.get('limit', 120)})"
                    self.activity.append(user_result)
                    record_task_event("tool", user_result)
                    # Keep full tool data for the model, but show only a compact
                    # outcome in Chat so the final answer remains visible.
                    self.messages.append(("tool", user_result))
                    self.tool_details.append(
                        f"TOOL: {name}\nARGUMENTS: {json.dumps(args, ensure_ascii=False, default=str)}\nRESULT: {result_text[:12000]}"
                    )
                    self.tool_details = self.tool_details[-100:]
                    history.append({"role":"tool","tool_call_id":tc.id,
                                    "content":mark_untrusted_tool_output(result_text, 12000)})
        except Exception as e:
            answer=f"Request failed: {type(e).__name__}: {e}"
            if self.messages and self.messages[-1][0] == "assistant" and not self.messages[-1][1]:
                self.messages.pop()
            self.activity.append("Provider request failed: " + answer[:500])
            record_task_event("failed", f"{type(e).__name__}: {e}", "failed")
        final_status = "stopped" if self.cancel_event.is_set() else ("failed" if answer.startswith("Request failed:") else "completed")
        record_task_event("finished", answer[:240], final_status)
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
        self.ask_user_broker.cancel_all()
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
        pages=["Chat","Workspace","Tasks","Activity","Skills","MCP","Settings","Add-ons","Help"]
        while self.running:
            # Drain worker events on the curses/UI thread only.
            try:
                while True:
                    event, payload = self.events.get_nowait()
                    if event == "models":
                        self.model_fetching = False
                        self.select_searched_model(payload)
                    elif event == "ask_user":
                        question = payload.get("question", {})
                        options = question.get("options") or []
                        prompt = str(question.get("prompt", "Agent Code needs your input"))
                        lines = ["", "AGENT CODE — INPUT REQUIRED", prompt]
                        lines.extend(f"  {i + 1}. {choice}" for i, choice in enumerate(options))
                        lines.append("Enter option number or custom answer (blank = skip): ")
                        h, w = self.s.getmaxyx()
                        for row, line in enumerate(lines[-max(1, h - 3):], start=1):
                            self.safe_add(row, 1, line, curses.A_BOLD if row == 1 else 0, w - 2)
                        self.s.refresh()
                        curses.echo()
                        try:
                            raw = self.s.getstr(max(1, h - 2), 1, max(1, w - 3)).decode("utf-8", "replace").strip()
                        finally:
                            curses.noecho()
                        qid = question.get("question_id")
                        if not raw:
                            self.ask_user_broker.answer_question(qid, skip=True)
                        elif options and raw.isdigit() and 1 <= int(raw) <= len(options):
                            self.ask_user_broker.answer_question(qid, choice=options[int(raw) - 1])
                        elif options and raw in options:
                            self.ask_user_broker.answer_question(qid, choice=raw)
                        else:
                            self.ask_user_broker.answer_question(qid, custom_text=raw)
                        self.notice = "Answer submitted. Agent is continuing…"
            except queue.Empty:
                pass
            self.draw()
            try:
                ch=self.s.get_wch()
            except curses.error:
                continue
            if ch is None:
                continue
            if ch == curses.KEY_F10:
                self.running = False
                continue
            if ch == curses.KEY_F2:
                self.mode="Plan" if self.mode=="Build" else "Build"; self.notice="Mode changed to "+self.mode
                continue
            if self.page == "Chat" and isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
                self.input += ch
                continue
            if ch == curses.KEY_PPAGE:
                amount=max(3,self.s.getmaxyx()[0]//2)
                if self.page=="Activity": self.activity_scroll += amount
                else: self.scroll += amount
                continue
            if ch == curses.KEY_NPAGE:
                amount=max(3,self.s.getmaxyx()[0]//2)
                if self.page=="Activity": self.activity_scroll=max(0,self.activity_scroll-amount)
                else: self.scroll=max(0,self.scroll-amount)
                continue
            if ch == curses.KEY_HOME and self.page == "Chat":
                self.scroll = 10**9
                continue
            if ch == curses.KEY_END and self.page == "Chat":
                self.scroll = 0
                continue
            if ch == curses.KEY_F5 or ch == "\x03":
                if self.busy:
                    self._stop_answer()
                    continue
                if ch == "\x03":
                    self.running = False
                    continue
            if ch == "\x0c":  # Ctrl+L
                self._clear_chat()
                continue
            if self.page == "Chat" and ch in ("\n", curses.KEY_ENTER, 10, 13):
                if self.input.strip():
                    user=self.input.strip(); self.input=""; self._dispatch_input(user)
                continue
            if ch in ("q", "Q", "\x03") and (self.page != "Chat" or not self.input):
                self.running=False
            elif ch == "\t": self.page=pages[(pages.index(self.page)+1)%len(pages)]
            elif ch in tuple(str(i) for i in range(1, len(pages)+1)) and (self.page != "Chat" or not self.input): self.page=pages[int(ch)-1]
            elif ch in ("p","P") and self.page in ("Settings","Help"): self.page="Settings"; self.configure("provider")
            elif ch in ("m","M") and self.page in ("Settings","Help"): self.page="Settings"; self.fetch_models()
            elif ch in ("i","I") and self.page in ("Settings","Help"): self.install_podman()
            elif ch in ("k","K") and self.page in ("Settings","Help"): self.page="Settings"; self.configure("key")
            elif self.page == "Tasks" and ch in (curses.KEY_UP, "k") and not self.task_detail_id:
                self.task_selection = max(0, self.task_selection - 1)
            elif self.page == "Tasks" and ch in (curses.KEY_DOWN, "j") and not self.task_detail_id:
                self.task_selection += 1
            elif self.page == "Tasks" and ch in ("\n", curses.KEY_ENTER, 10, 13) and not self.task_detail_id:
                from .interactive import TaskHistoryStore
                from .paths import global_data_dir
                tasks = TaskHistoryStore(global_data_dir() / "tasks").list_states(limit=100)
                if tasks:
                    self.task_selection = min(self.task_selection, len(tasks)-1)
                    self.task_detail_id = tasks[self.task_selection].task_id
            elif self.page == "Tasks" and ch == 27 and self.task_detail_id:
                self.task_detail_id = None
            elif self.page == "Tasks" and ch in ("r", "R"):
                from .interactive import TaskHistoryStore
                from .paths import global_data_dir
                tasks = TaskHistoryStore(global_data_dir() / "tasks").list_states(limit=100)
                if self.task_detail_id:
                    selected = TaskHistoryStore(global_data_dir() / "tasks").get(self.task_detail_id)
                else:
                    selected = tasks[self.task_selection] if tasks and self.task_selection < len(tasks) else None
                if selected:
                    self.task_detail_id = None
                    self.page = "Chat"
                    self._dispatch_input(selected.objective)
            elif self.page=="Skills" and ch in ("t","T"): self.manage_skill("toggle")
            elif self.page=="Skills" and ch in ("i","I"): self.manage_skill("install")
            elif self.page=="Add-ons" and ch in ("t","T"): self.manage_addon("toggle")
            elif self.page=="Add-ons" and ch in ("n","N"): self.manage_addon("create")
            elif self.page=="Add-ons" and ch in ("o","O"): self.manage_addon("open")
            elif self.page=="MCP" and ch in ("a","A"): self.mcp_configure("add")
            elif self.page=="MCP" and ch in ("e","E"): self.mcp_configure("edit")
            elif self.page=="MCP" and ch in ("t","T"): self.mcp_configure("toggle")
            elif self.page=="MCP" and ch in ("d","D"): self.mcp_configure("delete")
            elif self.page=="MCP" and ch in ("c","C"): self.mcp_configure("connect")
            elif ch in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                if self.page == "Chat": self.input=self.input[:-1]
            elif ch == 27:
                if self.page == "Chat": self.input=""


def main():
    if not (os.isatty(0) and os.isatty(1)):
        print("Agent Code TUI requires an interactive terminal. Run: agent-code tui"); return 2
    try: curses.wrapper(lambda scr:TUI(scr).run())
    except KeyboardInterrupt: pass
    return 0

if __name__=="__main__": raise SystemExit(main())
