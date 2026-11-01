"""Monitor-free terminal interface for Agent Code. Uses only terminal UI APIs."""
from __future__ import annotations
import curses, json, os, platform, queue, shutil, subprocess, textwrap, threading, time, uuid, re
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
    try: return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception: return {}

def write_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
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
        self.input=""; self.scroll=0; self.cwd="."; self.page="Chat"; self.running=True; self.busy=False; self.cancel_event=threading.Event(); self.events=queue.Queue(); self.activity=["Ready — send a task to watch agent progress."]; self.tool_details=[]
        curses.curs_set(1); curses.start_color(); curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1); curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_GREEN, -1); curses.init_pair(4, curses.COLOR_YELLOW, -1)
        self.s.keypad(True); self.s.timeout(150); self.draw()
    def safe_add(self,y,x,text,attr=0,width=None):
        h,w=self.s.getmaxyx()
        if y<0 or y>=h or x<0 or x>=w: return
        if width is not None: text=text[:width]
        else: text=text[:max(0,w-x-1)]
        try: self.s.addstr(y,x,text,attr)
        except curses.error: pass
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
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        value = "".join(ch if ch in "\n\t" or ord(ch) >= 32 else " " for ch in value)
        return value.strip() or "(The provider returned no displayable text.)"

    def draw(self):
        self.s.erase(); h,w=self.s.getmaxyx()
        self.safe_add(0,0," AGENT CODE  "+__version__+"  ◆  TERMINAL WORKSPACE ",curses.color_pair(2),w-1)
        sidebar=max(19,min(25,w//4)); content=sidebar+2
        self.safe_add(2,1,"NAVIGATION",curses.color_pair(1)|curses.A_BOLD)
        for i,name in enumerate(["Chat","Workspace","Activity","Skills","MCP","Settings","Help"]):
            self.safe_add(4+i,2,("▸ " if name==self.page else "  ")+name,curses.A_BOLD if name==self.page else 0)
        self.safe_add(12,1,"WORKSPACE",curses.color_pair(1)|curses.A_BOLD)
        self.safe_add(13,1,str(WORKSPACE)[-max(1,sidebar-2):])
        self.safe_add(15,1,"MODE",curses.color_pair(1)|curses.A_BOLD)
        self.safe_add(16,2,"["+self.mode+"]  (F2 to toggle)")
        for y in range(1,h-2): self.safe_add(y,sidebar,"│")
        title={"Chat":"Chat / Agent","Workspace":"Workspace Explorer","Activity":"Live Agent Activity / Mini IDE","Skills":"Installed Skills","MCP":"Remote MCP","Settings":"Provider Settings","Help":"Keyboard Shortcuts"}.get(self.page,self.page)
        self.safe_add(2,content,title,curses.color_pair(1)|curses.A_BOLD)
        self.safe_add(h-1,0, ("Provider: "+str(self.cfg.get("provider_name", "OpenAI"))+"  •  "+self.notice)[:max(1,w-1)], curses.A_DIM)
        if self.page=="Chat":
            available=max(1,h-9)
            rendered=[]
            for role,body in list(self.messages):
                # Keep tool payloads out of the main transcript: large command/file
                # results used to push the final assistant answer off-screen.
                label = {"assistant":"ASSISTANT", "user":"YOU", "tool":"TOOL RESULT"}.get(role, str(role).upper())
                color = curses.color_pair(3) if role == "assistant" else curses.color_pair(4)
                rendered.append((f"{label}  ─────────────────────────", color|curses.A_BOLD))
                body_text = self._chat_text(body)
                if role == "tool":
                    body_text = body_text.splitlines()[0] if body_text.splitlines() else "Tool completed. See Activity for details."
                previous_blank=False
                for raw_line in (body_text.splitlines() or [""]):
                    if not raw_line.strip():
                        if not previous_blank: rendered.append(("",0))
                        previous_blank=True
                        continue
                    previous_blank=False
                    for line in (textwrap.wrap(raw_line, max(10,w-content-3), replace_whitespace=False, drop_whitespace=False) or [""]):
                        rendered.append((line,0))
                rendered.append(("",0))
            max_scroll = max(0, len(rendered) - available)
            self.scroll = max(0, min(self.scroll, max_scroll))
            end = max_scroll - self.scroll
            start = max(0, end - available)
            for y,(line,attr) in enumerate(rendered[start:end],start=4):
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
        elif self.page=="Activity":
            self.safe_add(4,content,"LIVE ACTIVITY — tool calls and results, not private model reasoning",curses.color_pair(1))
            self.safe_add(6,content,"Workspace: "+str(WORKSPACE))
            for i,line in enumerate(self.activity[-max(1,h-12):]):
                self.safe_add(8+i,content,line)
            if self.tool_details:
                self.safe_add(max(8,h-5),content,"LATEST TOOL OUTPUT",curses.color_pair(1)|curses.A_BOLD)
                detail = self.tool_details[-1]
                for j,line in enumerate(textwrap.wrap(detail, max(10,w-content-3))[:3]):
                    self.safe_add(max(9,h-4)+j,content,line)
            self.safe_add(h-3,content,"Updates and recent tool output. Press 1 for Chat.",curses.A_DIM)
        elif self.page=="Skills":
            d=paths.global_skills_dir(); names=sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []
            self.safe_add(4,content,f"Installed skills: {len(names)}")
            for i,n in enumerate(names[:max(1,h-7)]): self.safe_add(5+i,content,"• "+n)
            self.safe_add(h-3,content,"Skill management: agent-code skills list / install")
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
        else:
            for i,line in enumerate(["Tab: cycle pages","1-7: Chat, Workspace, Activity, Skills, MCP, Settings, Help","Enter: send message; !command: run a shell command directly", "F5 or Ctrl+C: stop current agent task", "Ctrl+L or /clear: clear chat", "i: install Podman sandbox runtime","F2: toggle Plan / Build mode","p: choose provider and model (Settings)","m: fetch available models (Settings)","k: configure API key","MCP page: a add, e edit, t toggle, d delete, c connect/test","F5 or Ctrl+C: stop task; Ctrl+L: clear chat", "F10: quit","The terminal UI works over SSH without a monitor or desktop session."]): self.safe_add(4+i,content,line)
        self.s.refresh()
    def prompt(self,title,initial=""):
        curses.echo(); curses.curs_set(1); h,w=self.s.getmaxyx(); self.safe_add(h-1,0,(title+" ")[:w-1],curses.color_pair(2)); self.s.clrtoeol(); self.s.refresh()
        try:
            value=self.s.getstr(h-1,min(len(title)+1,max(0,w-2)),max(1,w-len(title)-3)).decode("utf-8","replace")
        except (curses.error, UnicodeError, OSError):
            value=initial
        finally:
            try: curses.noecho()
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
            curses.noecho(); h,w=self.s.getmaxyx()
            self.safe_add(h-1,0,"API key (hidden): ",curses.color_pair(2)); self.s.clrtoeol(); self.s.refresh()
            try: key=self.s.getstr(h-1,18,max(1,w-20)).decode("utf-8","replace").strip()
            except Exception: key=""
            if key: self.cfg["openai_api_keys"]=[key]
        write_config(self.cfg); self.notice="Settings saved to "+str(CONFIG)
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
    def answer(self,user):
        from .agent import make_client
        from . import agent as engine
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
        client.timeout=30
        # Use the same core workspace tools as the desktop agent, not a chat-only stub.
        names={"read_file","write_file","append_file","edit_file","glob_files","grep_files","shell_run","background_shell","web_search","web_fetch","task","task_status"}
        schemas=[x for x in engine.CORE_SCHEMAS if x.get("function",{}).get("name") in names]
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
            job_id = "subagent-" + uuid.uuid4().hex[:8]
            with _SUBAGENT_JOBS_LOCK:
                _SUBAGENT_JOBS[job_id] = {"status":"running", "result":"", "description":str(description)[:200]}
            def run_job():
                allowed = {"read_file","write_file","append_file","edit_file","glob_files","grep_files","web_search","web_fetch"}
                sub_schemas = [x for x in engine.CORE_SCHEMAS if x.get("function",{}).get("name") in allowed]
                sub_handlers = {k:v for k,v in handlers.items() if k in allowed}
                history_sub = [{"role":"system","content":f"You are an independent coding subagent. Job: {description}. Work only inside workspace {WORKSPACE}. You may read and edit files, but avoid unrelated files and report exactly what changed. The main agent is working concurrently; avoid overwriting files it may be editing."}, {"role":"user","content":str(prompt)}]
                try:
                    while True:
                        response_sub = client.chat.completions.create(model=model,messages=history_sub,tools=sub_schemas,tool_choice="auto")
                        msg_sub = response_sub.choices[0].message
                        if not msg_sub.tool_calls:
                            result_sub = msg_sub.content or "(subagent returned no text)"
                            status_sub = "completed"
                            break
                        history_sub.append({"role":"assistant","content":msg_sub.content or "","tool_calls":[{"id":tc.id,"type":"function","function":{"name":tc.function.name,"arguments":tc.function.arguments}} for tc in msg_sub.tool_calls]})
                        for tc in msg_sub.tool_calls:
                            try: args_sub=json.loads(tc.function.arguments or "{}")
                            except Exception: args_sub={}
                            fn_sub=sub_handlers.get(tc.function.name)
                            try: out_sub=fn_sub(**args_sub) if fn_sub else "DENIED: tool unavailable to subagent"
                            except Exception as exc: out_sub=f"ERROR: {type(exc).__name__}: {exc}"
                            history_sub.append({"role":"tool","tool_call_id":tc.id,"content":str(out_sub)[:12000]})
                    with _SUBAGENT_JOBS_LOCK: _SUBAGENT_JOBS[job_id].update(status=status_sub,result=result_sub)
                except Exception as exc:
                    with _SUBAGENT_JOBS_LOCK: _SUBAGENT_JOBS[job_id].update(status="failed",result=f"{type(exc).__name__}: {exc}")
            threading.Thread(target=run_job,name=f"TUI-{job_id}",daemon=True).start()
            return f"Subagent started asynchronously. job_id={job_id}; continue your own work and check task_status later."
        handlers["task"] = start_subagent
        handlers["task_status"] = task_status
        readonly_names={"read_file","glob_files","grep_files","web_search","web_fetch","task_status"}
        active_schemas = schemas if self.mode == "Build" else [x for x in schemas if x.get("function", {}).get("name") in readonly_names]
        history=[{"role":"system","content":f"You are Agent Code, a general research and coding agent, not just a code generator. Work only inside this workspace: {WORKSPACE}. Current mode: {self.mode}. For current facts, comparisons, unfamiliar technology, APIs, troubleshooting, or research questions, use web_search and follow relevant results with web_fetch; prefer primary/authoritative sources, cite source titles and URLs, separate evidence from inference, and never invent sources. For coding tasks, research docs when details are unfamiliar or likely to have changed, but do not browse unnecessarily for simple edits. In Plan mode you MUST only inspect and explain a concrete plan; do not call write, edit, append, shell, or any state-changing tool. No implementation until the user explicitly switches to Build mode and submits/approves the task. In Build mode you may use available tools subject to their restrictions. Ask before destructive actions."}]
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
                response=client.chat.completions.create(model=model,messages=history,tools=active_schemas or None,tool_choice=("auto" if active_schemas else "none"))
                msg=response.choices[0].message
                if self.cancel_event.is_set():
                    answer = "Task stopped by user."
                    self.activity.append("Task stopped by user.")
                    break
                if not msg.tool_calls:
                    answer=self._chat_text(msg.content) if msg.content else "The model returned an empty response. Try again or choose another model."
                    self.activity.append("Agent response ready.")
                    break
                # Some providers include useful user-facing commentary in the same
                # assistant turn as tool calls. Preserve it in the visible transcript.
                if msg.content and str(msg.content).strip():
                    self.messages.append(("assistant", str(msg.content).strip()))
                history.append({"role":"assistant","content":msg.content or "","tool_calls":[{"id":tc.id,"type":"function","function":{"name":tc.function.name,"arguments":tc.function.arguments}} for tc in msg.tool_calls]})
                for tc in msg.tool_calls:
                    if self.cancel_event.is_set():
                        answer = "Task stopped by user."
                        self.activity.append("Task stopped by user.")
                        break
                    name=tc.function.name
                    try:
                        args=json.loads(tc.function.arguments or "{}")
                        from .agent import describe_activity, describe_tool_result
                        action_label = describe_activity(name, args)
                    except Exception:
                        args = {}
                        action_label = "Working with project files" if name in ("read_file", "write_file", "edit_file", "append_file") else "Running a tool"
                    self.activity.append(action_label + "…")
                    self.notice=action_label + "…"
                    try:
                        if name == "read_file":
                            # Keep previews bounded; the model can request a different offset/limit.
                            args["limit"] = max(1, min(400, int(args.get("limit", 120))))
                        if name not in handlers: result="ERROR: tool is not available in TUI"
                        elif self.mode == "Plan" and name not in readonly_names:
                            result="BLOCKED: Plan mode is strictly read-only. Present the plan without attempting implementation. The user must switch to Build mode explicitly."
                        elif name in ("write_file","append_file","edit_file","shell_run","background_shell"):
                            result=handlers[name](**args)
                        else: result=handlers[name](**args)
                    except Exception as exc: result=f"ERROR: {exc}"
                    result_text = str(result)
                    if name in ("shell_run", "background_shell") and result_text.strip() == "(no output)":
                        result_text = "Command completed successfully (no stdout or stderr)."
                    try:
                        user_result = describe_tool_result(name, args, result_text)
                        if name == "shell_run" and result_text.startswith("Command completed successfully"):
                            user_result = "Command completed successfully (no output)"
                    except Exception:
                        user_result = "Tool finished" if not result_text.startswith("ERROR") else "Tool failed"
                    if name == "read_file" and not result_text.startswith("ERROR"):
                        header = result_text.splitlines()[0] if result_text else ""
                        import re
                        match = re.search(r"lines (\d+)-(\d+) of (\d+)", header)
                        if match:
                            count = int(match.group(2)) - int(match.group(1)) + 1
                            user_result = f"Read {count} lines from {args.get('path', 'file')} (of {match.group(3)} total; preview limit {args.get('limit', 120)})"
                    self.activity.append(user_result)
                    # Keep full tool data for the model, but show only a compact
                    # outcome in Chat so the final answer remains visible.
                    self.messages.append(("tool", user_result))
                    self.tool_details.append(f"{name}: {result_text[:1800]}")
                    self.tool_details = self.tool_details[-30:]
                    history.append({"role":"tool","tool_call_id":tc.id,"content":result_text[:12000]})
        except Exception as e: answer=f"Request failed: {e}"
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
        pages=["Chat","Workspace","Activity","Skills","MCP","Settings","Help"]
        while self.running:
            # Drain worker events on the curses/UI thread only.
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
                self.scroll += max(3, self.s.getmaxyx()[0] // 2)
                continue
            if ch == curses.KEY_NPAGE:
                self.scroll = max(0, self.scroll - max(3, self.s.getmaxyx()[0] // 2))
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
            elif ch in ("1","2","3","4","5","6","7") and (self.page != "Chat" or not self.input): self.page=pages[int(ch)-1]
            elif ch in ("p","P") and self.page in ("Settings","Help"): self.page="Settings"; self.configure("provider")
            elif ch in ("m","M") and self.page in ("Settings","Help"): self.page="Settings"; self.fetch_models()
            elif ch in ("i","I") and self.page in ("Settings","Help"): self.install_podman()
            elif ch in ("k","K") and self.page in ("Settings","Help"): self.page="Settings"; self.configure("key")
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
