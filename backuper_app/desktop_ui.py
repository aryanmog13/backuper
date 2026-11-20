"""Desktop window for configuring, sending, and scheduling backups."""

import base64
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import platform
import queue
import sys
import tempfile
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk
import webbrowser

from .backup_service import (
    BackupError, CONFIG, listen, load_config, pair_bot, run_schedule, send_backup,
    test_telegram, validate_folder,
)
from .curl_proxy_transport import PROTOCOLS, normalize_proxy
from .xray_proxy import is_xray_link, outbound_from_link, proxy_session


PREFERENCES = CONFIG.with_name("preferences.json")
ASSETS = Path(__file__).with_name("assets")

BG = "#0b1119"
CARD = "#131c2a"
FIELD = "#0e1621"
BUTTON = "#1a2534"
BUTTON_HOVER = "#223046"
BORDER = "#233045"
INK = "#eef4fc"
MUTED = "#8fa1b8"
ACCENT = "#5ce1e6"
ACCENT_HOVER = "#7cecf0"
ACCENT_INK = "#04141a"
GOOD = "#4ade80"
WARN = "#fbbf24"
BAD = "#f87171"
DISABLED = "#7d8ea6"

FONTS = {}


def configure_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=BG)
    family = tkfont.nametofont("TkDefaultFont").actual("family")
    FONTS.clear()
    FONTS.update(
        display=tkfont.Font(root=root, family=family, size=20, weight="bold"),
        title=tkfont.Font(root=root, family=family, size=13, weight="bold"),
        body=tkfont.Font(root=root, family=family, size=12),
        small=tkfont.Font(root=root, family=family, size=11),
        button=tkfont.Font(root=root, family=family, size=12, weight="bold"),
    )
    style.configure(".", background=BG, foreground=INK, font=FONTS["body"],
                    bordercolor=BORDER, focuscolor=ACCENT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("TEntry", fieldbackground=FIELD, foreground=INK, insertcolor=INK,
                    bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=(9, 7))
    style.map("TEntry",
              bordercolor=[("focus", ACCENT)],
              fieldbackground=[("disabled", CARD)],
              foreground=[("disabled", DISABLED)])
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=INK,
                    arrowcolor=MUTED, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD,
                    padding=(8, 6))
    style.map("TCombobox",
              fieldbackground=[("readonly", FIELD), ("disabled", CARD)],
              foreground=[("readonly", INK), ("disabled", DISABLED)],
              background=[("active", BUTTON_HOVER)],
              arrowcolor=[("active", INK), ("disabled", DISABLED)])
    style.configure("TButton", background=BUTTON, foreground=INK, bordercolor=BORDER,
                    lightcolor=BUTTON, darkcolor=BUTTON, padding=(14, 8), width=0,
                    relief="flat", font=FONTS["body"])
    style.map("TButton",
              background=[("active", BUTTON_HOVER), ("pressed", FIELD), ("disabled", CARD)],
              lightcolor=[("active", BUTTON_HOVER), ("pressed", FIELD)],
              darkcolor=[("active", BUTTON_HOVER), ("pressed", FIELD)],
              foreground=[("disabled", DISABLED)],
              bordercolor=[("disabled", BORDER)])
    style.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_INK,
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                    padding=(18, 9), width=0, relief="flat", font=FONTS["button"])
    style.map("Accent.TButton",
              background=[("active", ACCENT_HOVER), ("pressed", "#43cbd0"), ("disabled", CARD)],
              lightcolor=[("active", ACCENT_HOVER), ("pressed", "#43cbd0"), ("disabled", CARD)],
              darkcolor=[("active", ACCENT_HOVER), ("pressed", "#43cbd0"), ("disabled", CARD)],
              foreground=[("disabled", DISABLED)],
              bordercolor=[("disabled", BORDER)])
    style.configure("Danger.TButton", background=CARD, foreground=BAD, bordercolor=BORDER,
                    lightcolor=CARD, darkcolor=CARD, padding=(12, 8), width=0,
                    relief="flat", font=FONTS["body"])
    style.map("Danger.TButton",
              background=[("active", "#2a1a22"), ("disabled", CARD)],
              lightcolor=[("active", "#2a1a22")],
              darkcolor=[("active", "#2a1a22")],
              foreground=[("disabled", DISABLED)])
    style.configure("TCheckbutton", background=CARD, foreground=INK, focuscolor=CARD,
                    indicatorbackground=FIELD, indicatorforeground=ACCENT,
                    indicatormargin=(0, 0, 8, 0), padding=(0, 4))
    style.map("TCheckbutton",
              background=[("active", CARD)],
              indicatorbackground=[("selected", ACCENT), ("active", BUTTON_HOVER)],
              indicatorforeground=[("selected", ACCENT_INK)],
              foreground=[("disabled", DISABLED)])
    style.configure("Vertical.TScrollbar", background=BUTTON, troughcolor=BG, bordercolor=BG,
                    arrowcolor=MUTED, lightcolor=BUTTON, darkcolor=BUTTON, gripcount=0,
                    relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BUTTON_HOVER)])
    style.configure("Accent.Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD,
                    bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT, arrowsize=6)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_INK)


def read_preferences():
    try:
        data = json.loads(PREFERENCES.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_preferences(data):
    PREFERENCES.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=PREFERENCES.parent, delete=False) as destination:
        path = destination.name
        try:
            json.dump(data, destination)
            destination.close()
            os.replace(path, PREFERENCES)
        finally:
            if os.path.exists(path):
                os.unlink(path)


def backup_interval(value):
    try:
        hours = float(value.replace("٫", "."))
    except ValueError:
        hours = 0
    if not math.isfinite(hours) or not 1 / 60 <= hours <= 24 * 30:
        raise ValueError("Set an interval from 1 minute to 720 hours.")
    return hours


def read_connection():
    """Return the paired bot settings, or None when the file is missing or damaged."""
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    chat_id = data.get("chat_id")
    token = data.get("token")
    if type(chat_id) is not int or chat_id <= 0 or not isinstance(token, str) or not token:
        return None
    return data


class ScrollArea(ttk.Frame):
    """A vertically scrolling body that keeps the footer in place."""

    def __init__(self, master):
        super().__init__(master)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=BG, highlightthickness=0, borderwidth=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._sync)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.bar.grid(row=0, column=1, sticky="ns")
        self.body = tk.Frame(self.canvas, background=BG)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body)
        self.canvas.bind("<Configure>", self._on_canvas)

    def _sync(self, first, last):
        self.bar.set(first, last)
        fits = float(first) <= 0.0 and float(last) >= 1.0
        if fits and self.bar.winfo_ismapped():
            self.bar.grid_remove()
        elif not fits and not self.bar.winfo_ismapped():
            self.bar.grid()

    def _on_body(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)

    def scroll(self, event):
        node = self.winfo_toplevel().winfo_containing(event.x_root, event.y_root)
        while node is not None:
            if node is self:
                if sys.platform == "darwin":
                    step = -event.delta
                else:
                    step = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
                self.canvas.yview_scroll(int(step) or -1, "units")
                return "break"
            node = node.master
        return None

    def scroll_linux(self, event):
        node = self.winfo_toplevel().winfo_containing(event.x_root, event.y_root)
        while node is not None:
            if node is self:
                self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
                return "break"
            node = node.master
        return None


class BackuperWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.operation = None
        self.stop = Event()
        self.run_now = Event()
        self.link = None
        self.closing = False
        self.bot_details = None
        self.preferences = read_preferences()
        self.folder = tk.StringVar(value=self.preferences.get("folder", ""))
        self.token = tk.StringVar()
        self.proxy = tk.StringVar(value=self.preferences.get("proxy", ""))
        self.proxy_type = tk.StringVar(value=self.preferences.get("proxy_type", "http"))
        self.hours = tk.StringVar(value=self.preferences.get("hours", "6"))
        self.schedule_listens = tk.BooleanVar(value=self.preferences.get("schedule_listens", False))
        self.status = tk.StringVar(value="Choose a folder to get started.")

        root.title("Backuper")
        configure_theme(root)
        windowing_system = root.tk.call("tk", "windowingsystem")
        try:
            artwork = files(__package__).joinpath("assets", "backuper-icon.png").read_bytes()
            icon = tk.PhotoImage(master=root, data=base64.b64encode(artwork))
            self.brand_image = icon.subsample(max(1, icon.width() // 42))
        except (OSError, tk.TclError):
            self.brand_image = None
        if windowing_system == "win32":
            try:
                root.iconbitmap(default=str(ASSETS / "backuper-icon.ico"))
            except tk.TclError:
                pass
        elif windowing_system == "x11" and self.brand_image is not None:
            root.iconphoto(True, icon)
        self.place_window(root)
        root.minsize(640, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)

        shell = tk.Frame(root, background=BG)
        shell.pack(fill="both", expand=True)
        self.build_header(shell)
        self.area = ScrollArea(shell)
        self.area.pack(fill="both", expand=True)
        self.area.body.columnconfigure(0, weight=1)
        self.build_folder_card()
        self.build_telegram_card()
        self.build_proxy_card()
        self.build_schedule_card()
        self.build_footer(shell)
        root.bind_all("<MouseWheel>", self.area.scroll)
        root.bind_all("<Button-4>", self.area.scroll_linux)
        root.bind_all("<Button-5>", self.area.scroll_linux)

        for entry in (self.path_entry, self.token_entry, self.proxy_entry, self.interval_entry):
            entry.bind("<<Paste>>", lambda event: self.paste_entry(event.widget))
            if windowing_system == "aqua":
                # The V key produces ر on the standard Persian layout.
                entry.bind("<Command-Key-Arabic_ra>", lambda event: self.paste_entry(event.widget))
        self.folder.trace_add("write", self.refresh_actions)
        self.token.trace_add("write", self.refresh_actions)
        self.proxy.trace_add("write", self.refresh_proxy_hint)
        self.refresh_proxy_hint()
        self.refresh()
        self.path_entry.focus_set()
        self.root.after(75, self.drain_events)

    def place_window(self, root):
        width = min(760, root.winfo_screenwidth() - 80)
        height = min(820, root.winfo_screenheight() - 120)
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height) // 3)
        root.geometry(f"{width}x{height}+{x}+{y}")

    def build_header(self, parent):
        header = tk.Frame(parent, background=BG)
        header.pack(fill="x", padx=24, pady=(18, 14))
        if self.brand_image is not None:
            tk.Label(header, image=self.brand_image, background=BG).pack(side="left", padx=(0, 14))
        text = tk.Frame(header, background=BG)
        text.pack(side="left")
        tk.Label(text, text="Backuper", background=BG, foreground=INK,
                 font=FONTS["display"]).pack(anchor="w")
        tk.Label(text, text="Folder → ZIP → your private Telegram chat", background=BG,
                 foreground=MUTED, font=FONTS["small"]).pack(anchor="w")
        self.connection_pill = tk.Label(header, text="●  Not connected", background=BG,
                                        foreground=MUTED, font=FONTS["small"])
        self.connection_pill.pack(side="right", pady=(6, 0))

    def make_card(self, row):
        card = tk.Frame(self.area.body, background=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER, borderwidth=0)
        card.grid(row=row, column=0, sticky="ew", padx=24, pady=(0, 12))
        inner = tk.Frame(card, background=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        return inner

    def card_title(self, parent, title, hint=None):
        head = tk.Frame(parent, background=CARD)
        head.pack(fill="x", pady=(0, 10))
        tk.Label(head, text=title, background=CARD, foreground=INK,
                 font=FONTS["title"]).pack(side="left")
        if hint:
            tk.Label(head, text=hint, background=CARD, foreground=MUTED,
                     font=FONTS["small"]).pack(side="right")
        return head

    def hint(self, parent, text, pady=(8, 0)):
        label = tk.Label(parent, text=text, background=CARD, foreground=MUTED,
                         font=FONTS["small"], anchor="w", justify="left")
        label.pack(fill="x", pady=pady)
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(220, event.width - 4)))
        return label

    def build_folder_card(self):
        inner = self.make_card(0)
        self.card_title(inner, "Backup folder", "ZIP")
        row = tk.Frame(inner, background=CARD)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        self.path_entry = ttk.Entry(row, textvariable=self.folder)
        self.path_entry.grid(row=0, column=0, sticky="ew")
        self.choose_button = ttk.Button(row, text="Browse…", command=self.choose_folder)
        self.choose_button.grid(row=0, column=1, padx=(8, 0))
        self.hint(inner, "Subfolders, hidden files and empty folders are kept. "
                         "Symbolic links and special files are skipped.")

    def build_telegram_card(self):
        inner = self.make_card(1)
        self.card_title(inner, "Telegram", "private chat only")
        self.account_box = tk.Frame(inner, background=CARD)
        self.account_box.pack(fill="x")
        self.token_row = tk.Frame(self.account_box, background=CARD)
        self.token_row.columnconfigure(0, weight=1)
        self.token_entry = ttk.Entry(self.token_row, textvariable=self.token, show="•")
        self.token_entry.grid(row=0, column=0, sticky="ew")
        self.paste_token_button = ttk.Button(
            self.token_row, text="Paste", command=lambda: self.paste_entry(self.token_entry, replace=True),
        )
        self.paste_token_button.grid(row=0, column=1, padx=(8, 0))
        self.pair_button = ttk.Button(self.token_row, text="Connect bot", style="Accent.TButton",
                                      command=self.connect)
        self.pair_button.grid(row=0, column=2, padx=(8, 0))
        self.paired_row = tk.Frame(self.account_box, background=CARD)
        self.account_label = tk.Label(self.paired_row, text="Connected to your private chat",
                                      background=CARD, foreground=GOOD, font=FONTS["body"],
                                      anchor="w", justify="left")
        self.account_label.pack(side="left", fill="x", expand=True)
        self.open_chat_button = ttk.Button(self.paired_row, text="Open chat", command=self.open_chat)
        self.open_chat_button.pack(side="left", padx=(8, 0))
        self.disconnect_button = ttk.Button(self.paired_row, text="Disconnect", style="Danger.TButton",
                                            command=self.disconnect)
        self.disconnect_button.pack(side="left", padx=(8, 0))
        self.link_button = ttk.Button(self.account_box, text="Open Telegram and press Start",
                                      command=self.open_link)
        self.hint(inner, "Create a bot with @BotFather, paste its token, then press Start in the chat.")

    def build_proxy_card(self):
        inner = self.make_card(2)
        self.card_title(inner, "Connection", "optional")
        row = tk.Frame(inner, background=CARD)
        row.pack(fill="x")
        row.columnconfigure(1, weight=1)
        self.proxy_protocol = ttk.Combobox(row, textvariable=self.proxy_type, values=PROTOCOLS,
                                           state="readonly", width=9)
        self.proxy_protocol.grid(row=0, column=0, padx=(0, 8))
        self.proxy_entry = ttk.Entry(row, textvariable=self.proxy, show="•")
        self.proxy_entry.grid(row=0, column=1, sticky="ew")
        self.paste_proxy_button = ttk.Button(row, text="Paste",
                                             command=lambda: self.paste_entry(self.proxy_entry, replace=True))
        self.paste_proxy_button.grid(row=0, column=2, padx=(8, 0))
        actions = tk.Frame(inner, background=CARD)
        actions.pack(fill="x", pady=(8, 0))
        self.proxy_hint = tk.Label(
            actions, text="Proxy address, or a VLESS, VMess or Trojan link.",
            background=CARD, foreground=MUTED, font=FONTS["small"], anchor="w", justify="left",
        )
        self.proxy_hint.pack(side="left", fill="x", expand=True)
        self.proxy_hint.bind("<Configure>", lambda event: self.proxy_hint.configure(
            wraplength=max(200, event.width - 4)))
        self.test_proxy_button = ttk.Button(actions, text="Test", command=self.test_connection)
        self.test_proxy_button.pack(side="left", padx=(8, 0))
        self.save_proxy_button = ttk.Button(actions, text="Save", command=self.save_proxy)
        self.save_proxy_button.pack(side="left", padx=(8, 0))

    def build_schedule_card(self):
        inner = self.make_card(3)
        self.card_title(inner, "Automatic backups")
        row = tk.Frame(inner, background=CARD)
        row.pack(fill="x")
        tk.Label(row, text="Every", background=CARD, foreground=INK,
                 font=FONTS["body"]).pack(side="left")
        self.interval_entry = ttk.Entry(row, textvariable=self.hours, width=6, justify="center")
        self.interval_entry.pack(side="left", padx=8)
        tk.Label(row, text="hours", background=CARD, foreground=INK,
                 font=FONTS["body"]).pack(side="left")
        self.schedule_button = ttk.Button(row, text="Start schedule", command=self.start_schedule)
        self.schedule_button.pack(side="right")
        self.listen_option = ttk.Checkbutton(row, text="Also answer /backup",
                                             variable=self.schedule_listens)
        self.listen_option.pack(side="right", padx=(0, 12))
        self.hint(inner, "The first backup runs after one full interval. Keep Backuper open.")

    def build_footer(self, parent):
        footer = tk.Frame(parent, background=BG)
        footer.pack(fill="x", padx=24, pady=(4, 18))
        actions = tk.Frame(footer, background=BG)
        actions.pack(fill="x", pady=(0, 10))
        self.send_button = ttk.Button(actions, text="Send ZIP", style="Accent.TButton", command=self.send)
        self.send_button.pack(side="left")
        self.listen_button = ttk.Button(actions, text="Listen for /backup", command=self.start_listener)
        self.listen_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(actions, text="Stop", command=self.request_stop)
        self.stop_button.pack(side="left", padx=(8, 0))
        status_row = tk.Frame(footer, background=BG)
        status_row.pack(fill="x")
        self.status_dot = tk.Label(status_row, text="●", background=BG, foreground=MUTED,
                                   font=FONTS["small"])
        self.status_dot.pack(side="left", anchor="n", padx=(2, 8), pady=(1, 0))
        self.status_label = tk.Label(status_row, textvariable=self.status, background=BG,
                                     foreground=MUTED, font=FONTS["small"], anchor="w", justify="left")
        self.status_label.pack(side="left", fill="x", expand=True)
        status_row.bind("<Configure>", lambda event: self.status_label.configure(
            wraplength=max(240, event.width - 40)))
        self.progress = ttk.Progressbar(footer, mode="indeterminate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(8, 0))
        self.progress.configure(value=0)

    def set_status(self, text, level="info"):
        self.status.set(text)
        colour = {"good": GOOD, "error": BAD, "warn": WARN}.get(level, MUTED)
        self.status_dot.configure(foreground=colour)
        self.status_label.configure(foreground=colour if level != "info" else MUTED)

    def refresh(self):
        busy = self.operation is not None
        self.bot_details = read_connection()
        paired = self.bot_details is not None
        if busy:
            pill, colour = "●  Working", WARN
        elif paired:
            pill, colour = "●  Connected", GOOD
        else:
            pill, colour = "●  Not connected", MUTED
        self.connection_pill.configure(text=pill, foreground=colour)
        if paired:
            self.token_row.pack_forget()
            self.paired_row.pack(fill="x")
            username = self.bot_details.get("username")
            self.account_label.configure(
                text=f"Connected as @{username}" if isinstance(username, str) and username
                else "Connected to your private chat",
            )
        else:
            self.paired_row.pack_forget()
            self.token_row.pack(fill="x")
            self.link_button.pack_forget()
        self.path_entry.configure(state="disabled" if busy else "normal")
        self.choose_button.configure(state="disabled" if busy else "normal")
        self.token_entry.configure(state="disabled" if busy else "normal")
        self.paste_token_button.configure(state="disabled" if busy else "normal")
        self.proxy_protocol.configure(state="disabled" if busy else "readonly")
        for control in (self.proxy_entry, self.paste_proxy_button, self.save_proxy_button,
                        self.test_proxy_button, self.interval_entry, self.listen_option,
                        self.open_chat_button, self.disconnect_button):
            control.configure(state="disabled" if busy else "normal")
        self.refresh_actions()

    def refresh_proxy_hint(self, *_):
        if is_xray_link(self.proxy.get().strip()):
            self.proxy_hint.configure(text="VLESS/VMess/Trojan link detected. The protocol list is ignored.")
        else:
            self.proxy_hint.configure(text="Proxy address, or a VLESS, VMess or Trojan link.")

    def refresh_actions(self, *_):
        busy = self.operation is not None
        paired = self.bot_details is not None
        can_send = paired and bool(self.folder.get().strip()) and not busy
        self.pair_button.configure(state="normal" if self.token.get().strip() and not busy else "disabled")
        active_schedule = self.operation == "schedule" and not self.stop.is_set()
        self.send_button.configure(
            text="Run backup now" if active_schedule else "Send ZIP",
            state="normal" if can_send or active_schedule else "disabled",
        )
        self.listen_button.configure(state="normal" if can_send else "disabled")
        self.schedule_button.configure(state="normal" if can_send else "disabled")
        self.stop_button.configure(state=(
            "normal" if self.operation in ("pair", "listen", "schedule") and not self.stop.is_set()
            else "disabled"
        ))

    def paste_entry(self, entry, *, replace=False):
        if not entry.instate(("!disabled", "!readonly")):
            return "break"
        try:
            value = self.root.clipboard_get().rstrip("\r\n")
        except tk.TclError:
            self.set_status("There is no text on the clipboard.", "warn")
            return "break"
        if entry in (self.token_entry, self.proxy_entry):
            value = value.strip().strip("\ufeff\u200e\u200f").strip()
        if not value or any(char in value for char in "\r\n\x00"):
            self.set_status("Copy one line of text, then try Paste again.", "warn")
            return "break"
        if replace:
            entry.delete(0, tk.END)
        elif entry.selection_present():
            entry.delete("sel.first", "sel.last")
        entry.insert(tk.INSERT, value)
        entry.focus_set()
        if replace:
            self.set_status("Text pasted.")
        return "break"

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose a folder to back up", mustexist=True)
        if folder:
            self.folder.set(folder)
            self.save_preferences(folder=folder)
            if self.bot_details is None:
                self.set_status("Connect your Telegram bot to send this folder.", "warn")
            else:
                self.set_status("Ready to send.", "good")

    def start(self, operation, action, success_text):
        self.operation = operation
        self.stop = Event()
        self.run_now = Event()
        self.progress.start(15)
        self.refresh()

        def work():
            try:
                result = action()
                self.events.put(("done", (success_text(result), "good")))
            except (BackupError, OSError, ValueError) as error:
                self.events.put(("done", (str(error), "error")))

        Thread(target=work, daemon=True).start()

    def report(self, status):
        self.events.put(("status", (status, "info")))

    def drain_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "done":
                text, level = payload
                if self.operation == "pair" and read_connection() is not None:
                    self.token.set("")
                self.operation = None
                self.link = None
                self.link_button.pack_forget()
                self.progress.stop()
                self.progress.configure(value=0)
                self.set_status(text, level)
                self.refresh()
                if self.closing:
                    self.root.destroy()
                    return
            elif event == "link":
                if not self.stop.is_set():
                    self.link = payload
                    self.link_button.pack(fill="x", pady=(10, 0))
                    self.set_status("Open Telegram and press Start to finish connecting.", "warn")
            elif not self.stop.is_set():
                text, level = payload
                self.set_status(text, level)
        self.root.after(75, self.drain_events)

    def connect(self):
        proxy = self.get_proxy()
        if proxy is None:
            return
        token = self.token.get().strip()
        self.set_status("Checking the bot token…")
        self.start(
            "pair",
            lambda: self.pair(token, proxy),
            lambda paired: "Telegram is connected." if paired else "Connection cancelled.",
        )

    def pair(self, token, proxy):
        with proxy_session(proxy) as endpoint:
            return pair_bot(token, lambda link: self.events.put(("link", link)), self.stop, proxy=endpoint)

    def get_proxy(self):
        value = self.proxy.get().strip()
        try:
            if is_xray_link(value):
                outbound_from_link(value)
                return value
            return normalize_proxy(value, self.proxy_type.get())
        except ValueError as error:
            self.set_status(str(error), "error")
            return None

    def probe(self, proxy):
        with proxy_session(proxy) as endpoint:
            return test_telegram(endpoint)

    def test_connection(self):
        proxy = self.get_proxy()
        if proxy is None:
            return
        self.set_status("Testing the connection to Telegram…")
        self.start(
            "probe",
            lambda: self.probe(proxy),
            lambda code: f"Connection works. Telegram answered with HTTP {code}.",
        )

    def save_proxy(self):
        proxy = self.get_proxy()
        if proxy is None:
            return
        if self.save_preferences(proxy=self.proxy.get().strip(), proxy_type=self.proxy_type.get()):
            self.set_status("Proxy saved." if proxy else "Proxy cleared.", "good")

    def save_preferences(self, **options):
        updated = {**self.preferences, **options}
        try:
            write_preferences(updated)
        except OSError as error:
            self.set_status(f"Could not save settings. {error}", "error")
            return False
        self.preferences = updated
        return True

    def open_link(self):
        if self.link:
            webbrowser.open(self.link)

    def open_chat(self):
        username = (self.bot_details or {}).get("username")
        webbrowser.open(f"https://t.me/{username}" if isinstance(username, str) and username else "https://t.me")

    def disconnect(self):
        if not messagebox.askyesno(
            "Disconnect Telegram",
            "Remove the saved bot token and chat from this computer?",
            parent=self.root,
        ):
            return
        try:
            CONFIG.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            self.set_status(f"Could not remove the saved settings. {error}", "error")
            return
        self.token.set("")
        self.link = None
        self.link_button.pack_forget()
        self.refresh()
        self.set_status("Disconnected. Paste a bot token to connect again.", "good")

    def send(self):
        if self.operation == "schedule":
            self.run_now.set()
            self.set_status("Backup requested. It starts after the current run.")
            return
        proxy = self.get_proxy()
        if proxy is not None:
            path = self.folder.get()
            self.set_status("Preparing the backup…")
            self.start("send", lambda: self.send_folder(path, proxy),
                       lambda parts: f"Backup sent ({parts} file(s)).")

    def send_folder(self, path, proxy=""):
        folder = validate_folder(path)
        with proxy_session(proxy) as endpoint:
            bot, chat_id = load_config(endpoint)
            return send_backup(bot, chat_id, folder, progress=self.report)

    def start_listener(self):
        proxy = self.get_proxy()
        if proxy is not None:
            path = self.folder.get()
            self.set_status("Starting the Telegram listener…")
            self.start("listen", lambda: self.listen_for_backup(path, proxy), lambda _: "Listener stopped.")

    def listen_for_backup(self, path, proxy="", hours=None, accept_commands=False):
        folder = validate_folder(path)
        with proxy_session(proxy) as endpoint:
            bot, chat_id = load_config(endpoint)
            if hours is None:
                listen(bot, chat_id, folder, stop=self.stop, progress=self.report)
            else:
                run_schedule(bot, chat_id, folder, hours, stop=self.stop, run_now=self.run_now,
                             progress=self.report, accept_commands=accept_commands)

    def start_schedule(self):
        proxy = self.get_proxy()
        if proxy is None:
            return
        try:
            path = validate_folder(self.folder.get())
            hours = backup_interval(self.hours.get())
        except (ValueError, OSError, BackupError) as error:
            self.set_status(str(error), "error")
            return
        accept_commands = self.schedule_listens.get()
        if self.save_preferences(folder=str(path), hours=self.hours.get(), schedule_listens=accept_commands,
                                 proxy=self.proxy.get().strip(), proxy_type=self.proxy_type.get()):
            self.set_status("Starting the backup schedule…")
            self.start("schedule", lambda: self.listen_for_backup(path, proxy, hours, accept_commands),
                       lambda _: "Schedule stopped.")

    def request_stop(self):
        self.stop.set()
        self.link_button.pack_forget()
        self.set_status("Stopping after the current operation…", "warn")
        self.refresh()

    def close(self):
        if self.operation == "send":
            self.set_status("The backup is still sending. Close the app when it finishes.", "warn")
        elif self.operation:
            self.closing = True
            self.request_stop()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    if sys.argv[1:2] == ["--check"] and len(sys.argv) <= 3:
        try:
            root.withdraw()
            BackuperWindow(root)
            root.update_idletasks()
            windowing = root.tk.call("tk", "windowingsystem")
            report = [f"Backuper startup OK ({platform.machine()}, Tk {tk.TkVersion}, {windowing})"]
            if getattr(sys, "frozen", False):
                sample = "vless://00000000-0000-4000-a000-000000000001@example.invalid:443?security=tls&type=tcp"
                with proxy_session(sample):
                    report.append("Bundled Xray started with a test VLESS profile")
            result = "\n".join(report)
            if len(sys.argv) == 3:
                Path(sys.argv[2]).write_text(result + "\n", encoding="utf-8")
            else:
                print(result)
        finally:
            root.destroy()
        return
    BackuperWindow(root)
    root.mainloop()
