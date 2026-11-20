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
from tkinter import filedialog, ttk
import webbrowser

from .backup_service import BackupError, CONFIG, listen, load_config, pair_bot, run_schedule, send_backup, validate_folder
from .curl_proxy_transport import PROTOCOLS, normalize_proxy
from .xray_proxy import is_xray_link, outbound_from_link, proxy_session


PREFERENCES = CONFIG.with_name("preferences.json")
ASSETS = Path(__file__).with_name("assets")
SURFACE = "#f1f5fb"
CARD = "#ffffff"
INK = "#14243d"
SECONDARY = "#455873"
EDGE = "#dbe4f0"
BLUE = "#1558bf"


def configure_theme(root):
    root.configure(background=SURFACE)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=SURFACE)
    style.configure("TLabel", background=SURFACE, foreground=INK)
    style.configure("Heading.TLabel", font=("TkDefaultFont", 26, "bold"))
    style.configure("Subtitle.TLabel", foreground=SECONDARY)
    style.configure("TLabelframe", background=CARD, bordercolor=EDGE, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=SURFACE, foreground=INK,
                    font=("TkDefaultFont", 10, "bold"))
    style.configure("Card.TLabel", background=CARD, foreground=SECONDARY)
    style.configure("TCheckbutton", background=CARD, foreground=INK, padding=(0, 4))
    style.map("TCheckbutton", background=[("active", CARD)])
    style.configure("TEntry", fieldbackground="#f7faff", bordercolor=EDGE, padding=6)
    style.map("TEntry", bordercolor=[("focus", BLUE)])
    style.configure("TCombobox", fieldbackground="#f7faff", bordercolor=EDGE, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", "#f7faff")])
    style.configure("TButton", padding=(12, 7), background=CARD, bordercolor=EDGE, foreground=INK)
    style.map("TButton", background=[("active", "#e7effb")])
    style.configure("Accent.TButton", background=BLUE, lightcolor=BLUE, darkcolor=BLUE,
                    bordercolor=BLUE, foreground="#ffffff", font=("TkDefaultFont", 10, "bold"))
    style.map("Accent.TButton", background=[("disabled", "#e4ebf7"), ("active", "#104590")],
              foreground=[("disabled", "#496389")], bordercolor=[("disabled", "#cddaf0")])
    style.configure("Status.TLabel", background="#e4edf9", foreground=INK, padding=(12, 9))
    style.configure("Horizontal.TProgressbar", background=BLUE, troughcolor="#e4edf9",
                    lightcolor=BLUE, darkcolor=BLUE, bordercolor=EDGE)


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
        hours = float(value)
    except ValueError:
        hours = 0
    if not math.isfinite(hours) or not 1 / 60 <= hours <= 24 * 30:
        raise ValueError("Set an interval from 1 minute to 720 hours.")
    return hours


class BackuperWindow:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.operation = None
        self.stop = Event()
        self.run_now = Event()
        self.link = None
        self.closing = False
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
        artwork = files(__package__).joinpath("assets", "backuper-icon.png").read_bytes()
        icon = tk.PhotoImage(master=root, data=base64.b64encode(artwork))
        self.brand_image = icon.subsample(5)
        windowing_system = root.tk.call("tk", "windowingsystem")
        if windowing_system == "win32":
            root.iconbitmap(default=str(ASSETS / "backuper-icon.ico"))
        elif windowing_system == "x11":
            root.iconphoto(True, icon)
        root.minsize(640, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=(28, 24))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame)
        header.grid(sticky="ew", pady=(0, 22))
        ttk.Label(header, image=self.brand_image).grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="w")
        ttk.Label(header, text="Backuper", style="Heading.TLabel").grid(row=0, column=1, sticky="sw")
        ttk.Label(header, text="Send a folder as a ZIP to your private Telegram chat.", style="Subtitle.TLabel").grid(
            row=1, column=1, sticky="nw",
        )

        folder_section = ttk.LabelFrame(frame, text="Backup folder", padding=12)
        folder_section.grid(sticky="ew", pady=(0, 14))
        folder_section.columnconfigure(0, weight=1)
        self.path_entry = ttk.Entry(folder_section, textvariable=self.folder, width=46)
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.choose_button = ttk.Button(folder_section, text="Choose Folder…", command=self.choose_folder)
        self.choose_button.grid(row=0, column=1)

        self.telegram_section = ttk.LabelFrame(frame, text="Telegram", padding=12)
        self.telegram_section.grid(sticky="ew")
        self.telegram_section.columnconfigure(0, weight=1)
        self.connection = ttk.Label(self.telegram_section, style="Card.TLabel")
        self.connection.grid(row=0, column=0, columnspan=2, sticky="w")
        self.token_entry = ttk.Entry(self.telegram_section, textvariable=self.token, show="•")
        self.token_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(8, 0))
        self.pair_button = ttk.Button(self.telegram_section, text="Connect Bot", command=self.connect)
        self.pair_button.grid(row=1, column=1, sticky="e", pady=(8, 0))
        self.link_button = ttk.Button(self.telegram_section, text="Open Telegram", command=self.open_link)
        self.link_button.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.link_button.grid_remove()

        proxy_section = ttk.LabelFrame(frame, text="Proxy", padding=12)
        proxy_section.grid(sticky="ew", pady=(14, 0))
        proxy_section.columnconfigure(1, weight=1)
        self.proxy_protocol = ttk.Combobox(proxy_section, textvariable=self.proxy_type,
                                          values=PROTOCOLS, state="readonly", width=8)
        self.proxy_protocol.grid(row=0, column=0, padx=(0, 8))
        self.proxy_entry = ttk.Entry(proxy_section, textvariable=self.proxy, show="•")
        self.proxy_entry.grid(row=0, column=1, sticky="ew")
        self.save_proxy_button = ttk.Button(proxy_section, text="Save Proxy", command=self.save_proxy)
        self.save_proxy_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(proxy_section, text="Optional. Enter a proxy address or a VLESS, VMess, or Trojan link.",
                  style="Card.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 0),
        )

        schedule = ttk.LabelFrame(frame, text="Automatic backups", padding=12)
        schedule.grid(sticky="ew", pady=(14, 0))
        ttk.Label(schedule, text="Every", style="Card.TLabel").grid(row=0, column=0)
        self.interval_entry = ttk.Entry(schedule, textvariable=self.hours, width=6)
        self.interval_entry.grid(row=0, column=1, padx=6)
        ttk.Label(schedule, text="hours", style="Card.TLabel").grid(row=0, column=2, padx=(0, 10))
        self.schedule_button = ttk.Button(schedule, text="Start Schedule", command=self.start_schedule)
        self.schedule_button.grid(row=0, column=3, sticky="w")
        self.listen_option = ttk.Checkbutton(schedule, text="Also listen for /backup", variable=self.schedule_listens)
        self.listen_option.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        actions = ttk.Frame(frame)
        actions.grid(sticky="ew", pady=(20, 8))
        self.send_button = ttk.Button(actions, text="Send ZIP", command=self.send, style="Accent.TButton")
        self.send_button.pack(side="left")
        self.listen_button = ttk.Button(actions, text="Listen for /backup", command=self.start_listener)
        self.listen_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(actions, text="Stop", command=self.request_stop)
        self.stop_button.pack(side="left")
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=160)
        self.progress.grid(sticky="ew", pady=(4, 8))
        self.progress.grid_remove()
        ttk.Label(frame, textvariable=self.status, style="Status.TLabel", wraplength=530, justify="left").grid(sticky="ew")
        self.folder.trace_add("write", self.refresh)
        self.token.trace_add("write", self.refresh)
        self.refresh()
        self.root.after(75, self.drain_events)

    def refresh(self, *_):
        busy = self.operation is not None
        paired = CONFIG.is_file()
        can_send = paired and bool(self.folder.get().strip()) and not busy
        self.connection.configure(text=(
            "Connected to your private chat" if paired else "Enter the bot token from Telegram’s @BotFather."
        ))
        for control in (self.token_entry, self.pair_button):
            if paired:
                control.grid_remove()
            else:
                control.grid()
        self.path_entry.configure(state="disabled" if busy else "normal")
        self.choose_button.configure(state="disabled" if busy else "normal")
        self.token_entry.configure(state="disabled" if busy else "normal")
        self.pair_button.configure(state="normal" if self.token.get().strip() and not busy else "disabled")
        active_schedule = self.operation == "schedule" and not self.stop.is_set()
        self.send_button.configure(state="normal" if can_send or active_schedule else "disabled")
        self.listen_button.configure(state="normal" if can_send else "disabled")
        self.schedule_button.configure(state="normal" if can_send else "disabled")
        self.proxy_protocol.configure(state="disabled" if busy else "readonly")
        for control in (self.proxy_entry, self.save_proxy_button, self.interval_entry, self.listen_option):
            control.configure(state="disabled" if busy else "normal")
        self.stop_button.configure(state=(
            "normal" if self.operation in ("pair", "listen", "schedule") and not self.stop.is_set() else "disabled"
        ))

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose a folder to back up", mustexist=True)
        if folder:
            self.folder.set(folder)
            self.status.set("Ready to send." if CONFIG.is_file() else "Connect your Telegram bot to send this folder.")

    def start(self, operation, action, success_text):
        self.operation = operation
        self.stop = Event()
        self.run_now = Event()
        self.progress.grid()
        self.progress.start(15)
        self.refresh()

        def work():
            try:
                result = action()
                self.events.put(("done", success_text(result)))
            except (BackupError, OSError, ValueError) as error:
                self.events.put(("done", str(error)))

        Thread(target=work, daemon=True).start()

    def report(self, status):
        self.events.put(("status", status))

    def drain_events(self):
        while True:
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "done":
                self.operation = None
                self.link = None
                self.link_button.grid_remove()
                self.progress.stop()
                self.progress.grid_remove()
                self.status.set(value)
                self.refresh()
                if self.closing:
                    self.root.destroy()
                    return
            elif not self.stop.is_set():
                if event == "link":
                    self.link = value
                    self.link_button.grid()
                    self.status.set("Open Telegram and press Start to finish connecting.")
                else:
                    self.status.set(value)
        self.root.after(75, self.drain_events)

    def connect(self):
        proxy = self.get_proxy()
        if proxy is None:
            return
        token = self.token.get().strip()
        self.token.set("")
        self.status.set("Checking bot token…")
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
            self.status.set(str(error))
            return None

    def save_proxy(self):
        proxy = self.get_proxy()
        if proxy is None:
            return
        if self.save_preferences(proxy=self.proxy.get().strip(), proxy_type=self.proxy_type.get()):
            self.status.set("Proxy saved." if proxy else "Proxy cleared.")

    def save_preferences(self, **options):
        updated = {**self.preferences, **options}
        try:
            write_preferences(updated)
        except OSError as error:
            self.status.set(f"Could not save settings. {error}")
            return False
        self.preferences = updated
        return True

    def open_link(self):
        if self.link:
            webbrowser.open(self.link)

    def send(self):
        if self.operation == "schedule":
            self.run_now.set()
            self.status.set("Backup requested…")
            return
        proxy = self.get_proxy()
        if proxy is not None:
            path = self.folder.get()
            self.start("send", lambda: self.send_folder(path, proxy), lambda parts: f"Backup sent ({parts} file(s)).")

    def send_folder(self, path, proxy=""):
        folder = validate_folder(path)
        with proxy_session(proxy) as endpoint:
            bot, chat_id = load_config(endpoint)
            return send_backup(bot, chat_id, folder, progress=self.report)

    def start_listener(self):
        proxy = self.get_proxy()
        if proxy is not None:
            path = self.folder.get()
            self.status.set("Starting Telegram listener…")
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
            self.status.set(str(error))
            return
        accept_commands = self.schedule_listens.get()
        if self.save_preferences(folder=str(path), hours=self.hours.get(), schedule_listens=accept_commands,
                                 proxy=self.proxy.get().strip(), proxy_type=self.proxy_type.get()):
            self.status.set("Starting backup schedule…")
            self.start("schedule", lambda: self.listen_for_backup(path, proxy, hours, accept_commands),
                       lambda _: "Schedule stopped.")

    def request_stop(self):
        self.stop.set()
        self.link_button.grid_remove()
        self.status.set("Stopping after the current operation…")
        self.refresh()

    def close(self):
        if self.operation == "send":
            self.status.set("The backup is still sending. Close the app when it finishes.")
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
