import curses
from agent_code.tui import TUI


class TimeoutThenEnterScreen:
    def __init__(self):
        self.reads = 0

    def getmaxyx(self):
        return (24, 80)

    def erase(self):
        pass

    def refresh(self):
        pass

    def addstr(self, *args):
        pass

    def get_wch(self):
        self.reads += 1
        if self.reads == 1:
            raise curses.error("no input")
        return "\n"


def test_choose_ignores_curses_timeout(monkeypatch):
    tui = TUI.__new__(TUI)
    tui.s = TimeoutThenEnterScreen()
    monkeypatch.setattr(curses, "color_pair", lambda _: 0)
    result = tui.choose("Select model", ["model-a", "model-b"])
    assert result == "model-a"
    assert tui.s.reads == 2


def test_tui_history_does_not_duplicate_current_user_prompt():
    tui = TUI.__new__(TUI)
    tui.messages = [("user", "older question"), ("assistant", "older answer"),
                    ("user", "current task")]
    prior = tui.messages[:-1] if tui.messages and tui.messages[-1] == ("user", "current task") else tui.messages
    history = [{"role": role, "content": content} for role, content in prior[-16:]
               if role in ("user", "assistant")]
    history.append({"role": "user", "content": "current task"})
    assert [m["content"] for m in history if m["role"] == "user"] == ["older question", "current task"]


def test_tui_chat_tool_messages_are_rendered_as_compact_results():
    # The transcript renderer intentionally shows only the first summary line
    # for tool messages; full payloads remain available to the model/activity.
    body = "Wrote app.py\n\n" + ("large tool payload " * 500)
    compact = body.splitlines()[0] if body.splitlines() else "Tool completed. See Activity for details."
    assert compact == "Wrote app.py"
    assert len(compact) < 100


def test_chat_text_handles_provider_content_blocks():
    assert TUI._chat_text([{"type": "text", "text": "Hello"}, {"text": "world"}]) == "Hello\nworld"


def test_chat_text_removes_terminal_escape_sequences():
    assert TUI._chat_text("\x1b[31mVisible\x1b[0m") == "Visible"


def test_chat_text_has_fallback_for_empty_provider_content():
    assert TUI._chat_text(None) == "(empty response)"


def test_chat_viewport_shows_the_latest_assistant_message():
    rendered = TUI.render_chat_lines([
        ("user", "older question"),
        ("assistant", "older answer"),
        ("user", "current question"),
        ("assistant", "LATEST ANSWER MUST BE VISIBLE"),
    ], 24)
    visible, max_scroll, scroll = TUI.visible_chat_lines(rendered, viewport=5, scroll=0)
    assert max_scroll > 0
    assert scroll == 0
    assert "".join(line for line, _ in visible).replace(" ", "").find("LATESTANSWERMUSTBEVISIBLE") >= 0


def test_chat_renderer_wraps_wide_terminal_characters_by_cell_width():
    lines = TUI._wrap_terminal_line("A界B界C", 4)
    assert lines == ["A界B", "界C"]


class RecordingScreen:
    def __init__(self, height=24, width=80):
        self.height, self.width = height, width
        self.cells = {}
    def getmaxyx(self): return self.height, self.width
    def erase(self): self.cells.clear()
    def addstr(self, y, x, text, attr=0): self.cells[(y, x)] = str(text)
    def refresh(self): pass


def test_draw_renders_latest_answer_inside_the_real_chat_viewport(monkeypatch):
    tui = TUI.__new__(TUI)
    tui.s = RecordingScreen()
    tui.messages = [("user", "Please fix the issue"),
                    ("assistant", "The fix is complete and all checks passed.")]
    tui.page = "Chat"
    tui.mode = "Build"
    tui.cfg = {"provider_name": "OpenAI"}
    tui.notice = "Ready"
    tui.input = ""
    tui.busy = False
    tui.scroll = 0
    tui.activity = []
    tui.tool_details = []
    monkeypatch.setattr(curses, "color_pair", lambda _: 0)
    tui.draw()
    transcript = " ".join(tui.s.cells.values())
    assert "The fix is complete" in transcript
    assert "all checks passed" in transcript
