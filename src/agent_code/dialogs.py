"""Consistent dark, CustomTkinter-native modal dialogs for Agent Code."""
from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

BG = "#0a0d13"
PANEL = "#10141b"
CARD = "#161b22"
INPUT = "#0d1117"
FG = "#c9d1d9"
BRIGHT = "#f0f6fc"
DIM = "#8b949e"
ACCENT = "#388bfd"
BORDER = "#30363d"


class AgentDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, message, *, options=None, password=False):
        super().__init__(parent)
        self.result = None
        self.options = list(options or [])
        self.title(title or "Agent Code")
        self.configure(fg_color=BG)
        self.geometry("700x540" if self.options else "620x360")
        self.minsize(480, 300)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        shell = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=18, border_width=1, border_color=BORDER)
        shell.pack(fill="both", expand=True, padx=14, pady=14)
        header = ctk.CTkFrame(shell, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 8))
        ctk.CTkLabel(header, text="AGENT CODE", text_color=ACCENT,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text=title or "Your input", text_color=BRIGHT,
                     font=ctk.CTkFont(size=21, weight="bold")).pack(anchor="w", pady=(4, 0))

        body = ctk.CTkScrollableFrame(shell, fg_color=CARD, corner_radius=12,
                                      scrollbar_button_color=BORDER)
        body.pack(fill="both", expand=True, padx=20, pady=(8, 12))
        ctk.CTkLabel(body, text=message, text_color=FG, justify="left", anchor="w",
                     wraplength=620, font=ctk.CTkFont(size=13)).pack(fill="x", padx=16, pady=16)

        self.choice = tk.StringVar(value="")
        if self.options:
            ctk.CTkLabel(body, text="Choose an option", text_color=BRIGHT,
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(4, 8))
            for index, option in enumerate(self.options):
                ctk.CTkRadioButton(body, text=str(option), variable=self.choice, value=str(index),
                                   fg_color=ACCENT, hover_color=ACCENT,
                                   text_color=FG, border_color=BORDER).pack(anchor="w", padx=18, pady=5)

        ctk.CTkLabel(shell, text="Or write your own answer" if self.options else "Your answer",
                     text_color=DIM, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=22, pady=(0, 5))
        self.entry = ctk.CTkEntry(shell, height=42, fg_color=INPUT, border_color=BORDER,
                                  text_color=BRIGHT, placeholder_text="Type here…",
                                  show="*" if password else "")
        self.entry.pack(fill="x", padx=20, pady=(0, 14))
        self.entry.bind("<Return>", lambda _e: self._submit())

        footer = ctk.CTkFrame(shell, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 18))
        ctk.CTkButton(footer, text="Cancel", width=100, fg_color=CARD, hover_color=BORDER,
                      border_width=1, border_color=BORDER, text_color=FG,
                      command=self._cancel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(footer, text="Continue", width=120, fg_color=ACCENT,
                      hover_color="#1f6feb", text_color="white",
                      command=self._submit).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(80, self.entry.focus_set)
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")

    def _submit(self):
        typed = self.entry.get().strip()
        if typed:
            self.result = typed
        elif self.choice.get() != "":
            self.result = self.options[int(self.choice.get())]
        else:
            self.result = ""
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.result = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def ask_agent(parent, title, message, *, options=None, password=False):
    """Show a themed modal and return text/selected option, or None on cancel."""
    dialog = AgentDialog(parent, title, message, options=options, password=password)
    parent.wait_window(dialog)
    return dialog.result

class _ThemedMessageBox:
    """Drop-in themed replacements for the application's Tk message boxes."""
    @staticmethod
    def _show(title, message, parent, kind="info", choices=("OK",)):
        win = ctk.CTkToplevel(parent)
        win.title(title or "Agent Code")
        win.configure(fg_color=BG)
        win.geometry("480x250")
        win.resizable(False, False)
        win.transient(parent.winfo_toplevel())
        win.grab_set()
        frame = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        accent = {"error": "#f85149", "warning": "#d29922", "info": ACCENT}.get(kind, ACCENT)
        ctk.CTkLabel(frame, text="AGENT CODE", text_color=accent,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=20, pady=(18, 6))
        ctk.CTkLabel(frame, text=title or "Message", text_color=BRIGHT,
                     font=ctk.CTkFont(size=19, weight="bold")).pack(anchor="w", padx=20)
        ctk.CTkLabel(frame, text=str(message), text_color=FG, justify="left", anchor="w",
                     wraplength=420).pack(fill="both", expand=True, padx=20, pady=12)
        result = {"value": None}
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        def finish(value):
            result["value"] = value
            try: win.grab_release()
            except tk.TclError: pass
            win.destroy()
        for label, value in reversed(list(choices)):
            ctk.CTkButton(buttons, text=label, width=100,
                          fg_color=accent if label in ("OK", "Yes") else CARD,
                          hover_color="#1f6feb" if label in ("OK", "Yes") else BORDER,
                          text_color="white" if label in ("OK", "Yes") else FG,
                          command=lambda v=value: finish(v)).pack(side="right", padx=(8, 0))
        win.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        parent.wait_window(win)
        return result["value"]

    @classmethod
    def showinfo(cls, title, message, **kw):
        cls._show(title, message, kw.get("parent") or tk._default_root, "info")
        return "ok"

    @classmethod
    def showwarning(cls, title, message, **kw):
        cls._show(title, message, kw.get("parent") or tk._default_root, "warning")
        return "ok"

    @classmethod
    def showerror(cls, title, message, **kw):
        cls._show(title, message, kw.get("parent") or tk._default_root, "error")
        return "ok"

    @classmethod
    def askyesno(cls, title, message, **kw):
        return bool(cls._show(title, message, kw.get("parent") or tk._default_root,
                              "info", (("No", False), ("Yes", True))))

    @classmethod
    def askyesnocancel(cls, title, message, **kw):
        return cls._show(title, message, kw.get("parent") or tk._default_root,
                         "info", (("Cancel", None), ("No", False), ("Yes", True)))


themed_messagebox = _ThemedMessageBox()
