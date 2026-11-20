from io import BytesIO
import json
from pathlib import Path
import tempfile
from threading import Event
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from backuper_app import backup_service as backuper
from backuper_app import desktop_ui as backuper_gui


class DesktopTests(unittest.TestCase):
    def test_zip_preserves_non_ascii_folders_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve() / "پروژه شخصی"
            folder.mkdir()
            (folder / "empty").mkdir()
            (folder / "notes.txt").write_text("ordinary folder", encoding="utf-8")
            bot = Mock()
            self.assertEqual(backuper.send_backup(bot, 42, folder), 1)
            chat_id, name, payload, _ = bot.document.call_args.args
            self.assertEqual(chat_id, 42)
            self.assertTrue(name.endswith(".zip"))
            with ZipFile(BytesIO(payload)) as archive:
                self.assertEqual(archive.read(f"{folder.name}/notes.txt"), b"ordinary folder")
                self.assertIn(f"{folder.name}/empty/", archive.namelist())

    def test_schedule_sends_at_first_deadline(self):
        stop = Event()
        report = Mock()
        bot = Mock()

        def stop_after_send(status):
            if status.startswith("Backup sent"):
                stop.set()

        report.side_effect = stop_after_send
        with patch.object(backuper.time, "time", side_effect=[1000, 1000, 22600, 22600]), \
             patch.object(stop, "wait"), patch.object(backuper, "send_backup", return_value=1) as send:
            backuper.run_schedule(bot, 42, Path("."), 6, stop=stop, run_now=Event(), progress=report)
        send.assert_called_once()
        self.assertTrue(report.call_args_list[0].args[0].startswith("Next backup"))

    def test_paste_replaces_secrets_without_merging_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch.object(backuper_gui, "CONFIG", folder / "telegram.json"), \
                 patch.object(backuper_gui, "PREFERENCES", folder / "preferences.json"):
                root = tk.Tk()
                try:
                    root.withdraw()
                    window = backuper_gui.BackuperWindow(root)
                    window.token.set("old")
                    with patch.object(root, "clipboard_get", return_value="\u200f123:dummy\r\n"):
                        window.paste_token_button.invoke()
                    self.assertEqual(window.token.get(), "123:dummy")
                    self.assertTrue(window.pair_button.instate(["!disabled"]))
                    with patch.object(window, "start"):
                        window.connect()
                    self.assertEqual(window.token.get(), "123:dummy")

                    window.proxy.set("http://old.example:8080")
                    with patch.object(root, "clipboard_get", return_value="http://one\nhttp://two"):
                        window.paste_proxy_button.invoke()
                    self.assertEqual(window.proxy.get(), "http://old.example:8080")
                    with patch.object(root, "clipboard_get", return_value="socks5h://localhost:1080\n"):
                        window.paste_proxy_button.invoke()
                    self.assertEqual(window.get_proxy(), "socks5h://localhost:1080")

                    window.path_entry.insert(0, "/tmp/old folder")
                    window.path_entry.selection_range(5, tk.END)
                    with patch.object(root, "clipboard_get", return_value="پوشه جدید\n"):
                        window.paste_entry(window.path_entry)
                    self.assertEqual(window.folder.get(), "/tmp/پوشه جدید")
                    self.assertEqual(backuper_gui.backup_interval("۶٫۵"), 6.5)
                finally:
                    root.destroy()

    def test_damaged_config_stays_disconnected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            config = folder / "telegram.json"
            config.write_text("{not json", encoding="utf-8")
            with patch.object(backuper_gui, "CONFIG", config), \
                 patch.object(backuper_gui, "PREFERENCES", folder / "preferences.json"):
                root = tk.Tk()
                try:
                    root.withdraw()
                    window = backuper_gui.BackuperWindow(root)
                    window.folder.set(temporary)
                    root.update_idletasks()
                    self.assertIsNone(window.bot_details)
                    self.assertTrue(window.send_button.instate(["disabled"]))
                    self.assertTrue(window.token_row.winfo_manager())
                finally:
                    root.destroy()

    def test_status_text_and_progress_bar_do_not_share_a_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(backuper_gui, "CONFIG", Path(temporary) / "telegram.json"), \
                 patch.object(backuper_gui, "PREFERENCES", Path(temporary) / "preferences.json"):
                root = tk.Tk()
                try:
                    root.withdraw()
                    window = backuper_gui.BackuperWindow(root)
                    self.assertIsNot(window.progress.master, window.status_label.master)
                finally:
                    root.destroy()

    def test_window_folder_selection_and_proxy_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary).resolve()
            config = folder / "telegram.json"
            config.write_text(json.dumps({"token": "123:dummy", "chat_id": 42, "username": "test_bot"}))
            preferences = folder / "preferences.json"
            with patch.object(backuper_gui, "CONFIG", config), \
                 patch.object(backuper_gui, "PREFERENCES", preferences), \
                 patch.object(backuper_gui.filedialog, "askdirectory", return_value=str(folder)):
                root = tk.Tk()
                try:
                    root.withdraw()
                    window = backuper_gui.BackuperWindow(root)
                    root.update_idletasks()
                    self.assertTrue(window.send_button.instate(["disabled"]))
                    window.choose_button.invoke()
                    self.assertEqual(window.folder.get(), str(folder))
                    self.assertTrue(window.send_button.instate(["!disabled"]))
                    self.assertTrue(window.schedule_button.instate(["!disabled"]))
                    window.proxy_type.set("socks5h")
                    window.proxy.set("127.0.0.1:1080")
                    window.save_proxy_button.invoke()
                    self.assertEqual(window.get_proxy(), "socks5h://127.0.0.1:1080")
                    self.assertEqual(backuper_gui.read_preferences()["proxy_type"], "socks5h")
                finally:
                    root.destroy()
