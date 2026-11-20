"""Create ZIP backups and deliver them through the Telegram Bot API."""

from datetime import datetime
from getpass import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import tempfile
from threading import Event
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .curl_proxy_transport import request_json


CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Backuper" if os.name == "nt" else (
    Path.home() / ".config" / "backuper"
)
CONFIG = CONFIG_DIR / "telegram.json"
PART_SIZE = 49_000_000


class BackupError(Exception):
    pass


class Telegram:
    def __init__(self, token, proxy=""):
        if not isinstance(token, str) or not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise BackupError("The Telegram bot token has an invalid format.")
        self.url = f"https://api.telegram.org/bot{token}/"
        self.proxy = proxy

    def call(self, method, fields, *, body=None, content_type="application/json", timeout=40):
        url = self.url + method
        data = json.dumps(fields).encode() if body is None else body
        try:
            if self.proxy or (sys.platform == "darwin" and getattr(sys, "frozen", False)):
                status, result = request_json(url, self.proxy, data, content_type, timeout)
            else:
                request = Request(url, data=data, headers={"Content-Type": content_type})
                with urlopen(request, timeout=timeout) as response:
                    status, result = response.status, json.load(response)
        except HTTPError as exc:
            status, result = exc.code, None
        except (URLError, OSError, ValueError):
            message = "Could not reach Telegram through the configured proxy." if self.proxy else (
                "Could not complete the request to Telegram."
            )
            raise BackupError(message) from None
        if status != 200:
            detail = {
                401: "Check the bot token.",
                403: "Open the bot's Telegram chat and press Start.",
                409: "Stop other listeners for this bot and check for an active webhook.",
            }.get(status, "Check the connection and try again.")
            raise BackupError(f"Telegram returned HTTP {status}. {detail}")
        if not isinstance(result, dict) or not result.get("ok"):
            raise BackupError(f"Telegram rejected {method}.")
        return result["result"]

    def updates(self, offset, timeout=25):
        return self.call("getUpdates", {
            "offset": offset, "timeout": timeout, "allowed_updates": ["message"],
        }, timeout=timeout + 10)

    def message(self, chat_id, text):
        self.call("sendMessage", {"chat_id": chat_id, "text": text})

    def document(self, chat_id, filename, content, caption):
        boundary = secrets.token_hex(16)
        fields = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n'
        ).encode()
        self.call(
            "sendDocument", {}, body=fields + content + f"\r\n--{boundary}--\r\n".encode(),
            content_type=f"multipart/form-data; boundary={boundary}", timeout=180,
        )


def private_sender(message):
    chat = message.get("chat", {})
    sender = message.get("from", {})
    if chat.get("type") == "private" and chat.get("id") == sender.get("id"):
        return chat.get("id")
    return None


def setup():
    token = getpass("Paste the bot token from BotFather (hidden): ").strip()
    pair_bot(token, lambda url: print(f"Open {url} and tap Start.", flush=True))
    print("Paired with your private Telegram chat.")


def pair_bot(token, show_link, stop=None, *, proxy=""):
    if CONFIG.exists():
        raise BackupError(f"Bot settings already exist at {CONFIG}.")
    stop = stop if stop is not None else Event()
    bot = Telegram(token, proxy)
    username = bot.call("getMe", {})["username"]
    code = secrets.token_urlsafe(18)
    if stop.is_set():
        return False
    show_link(f"https://t.me/{username}?start={code}")
    offset = 0
    deadline = time.monotonic() + 180
    while not stop.is_set() and time.monotonic() < deadline:
        for update in bot.updates(offset, timeout=5):
            if stop.is_set():
                return False
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = private_sender(message)
            if chat_id is None or message.get("text") != f"/start {code}":
                continue
            bot.message(chat_id, "Backuper is paired. Start the listener on your computer to use /backup.")
            CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(CONFIG, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as config:
                json.dump({"token": token, "chat_id": chat_id}, config)
            return True
    if stop.is_set():
        return False
    raise BackupError("Pairing timed out. Run setup again.")


def load_config(proxy=""):
    try:
        settings = json.loads(CONFIG.read_text())
        chat_id = settings["chat_id"]
        if type(chat_id) is not int or chat_id <= 0:
            raise ValueError
        return Telegram(settings["token"], proxy), chat_id
    except FileNotFoundError:
        raise BackupError("Pair the bot first with: python3 backuper.py setup") from None
    except (KeyError, TypeError, ValueError):
        raise BackupError(f"Invalid configuration in {CONFIG}.") from None


def make_zip(folder, archive):
    def fail_on_walk_error(error):
        raise error

    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as output:
        if not hasattr(os, "fwalk"):
            zip_windows_folder(folder, archive, output, fail_on_walk_error)
            return
        for directory, subdirs, files, descriptor in os.fwalk(folder, onerror=fail_on_walk_error):
            directory = Path(directory)
            subdirs[:] = [name for name in subdirs if directory / name != archive.parent]
            relative = directory.relative_to(folder.parent)
            if relative.parts:
                output.mkdir(str(relative))
            for name in files:
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                with os.fdopen(fd, "rb") as source:
                    zip_file(output, relative / name, source)


def is_link_or_reparse_point(metadata):
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def zip_windows_folder(folder, archive, output, onerror):
    for directory, subdirs, files in os.walk(folder, onerror=onerror, followlinks=False):
        directory = Path(directory)
        subdirs[:] = [
            name for name in subdirs
            if directory / name != archive.parent and not is_link_or_reparse_point((directory / name).lstat())
        ]
        relative = directory.relative_to(folder.parent)
        if relative.parts:
            output.mkdir(relative.as_posix())
        for name in files:
            path = directory / name
            metadata = path.lstat()
            if is_link_or_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                continue
            with path.open("rb") as source:
                if not os.path.samestat(metadata, os.fstat(source.fileno())):
                    raise BackupError(f"File was replaced during backup: {name}")
                zip_file(output, relative / name, source)


def zip_file(output, path, source):
    metadata = os.fstat(source.fileno())
    if not stat.S_ISREG(metadata.st_mode):
        raise BackupError(f"File changed type during backup: {path.name}")
    item = ZipInfo(path.as_posix())
    modified = datetime.fromtimestamp(metadata.st_mtime)
    item.date_time = min(max(modified, datetime(1980, 1, 1)), datetime(2107, 12, 31)).timetuple()[:6]
    item.create_system = 3
    item.external_attr = metadata.st_mode << 16
    item.compress_type = ZIP_DEFLATED
    item.file_size = metadata.st_size
    with output.open(item, "w") as destination:
        shutil.copyfileobj(source, destination)


def send_backup(bot, chat_id, folder, *, progress=None):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", folder.name).strip("-")[:60] or "backup"
    filename = f"{label}-{stamp}.zip"
    with tempfile.TemporaryDirectory(prefix="backuper-") as temp:
        archive = Path(temp).resolve() / filename
        if progress is not None:
            progress("Creating ZIP…")
        make_zip(folder, archive)
        parts = (archive.stat().st_size + PART_SIZE - 1) // PART_SIZE
        digits = max(3, len(str(parts)))
        with archive.open("rb") as source:
            for index in range(1, parts + 1):
                if progress is not None:
                    progress(f"Sending file {index} of {parts}…")
                part_name = filename if parts == 1 else f"{filename}.part{index:0{digits}d}"
                caption = f"Backup of {folder.name}" if parts == 1 else f"{folder.name} — part {index}/{parts}"
                try:
                    bot.document(chat_id, part_name, source.read(PART_SIZE), caption)
                except BackupError as exc:
                    raise BackupError(f"Upload stopped at part {index}/{parts}. {exc}") from None
        if parts > 1:
            bot.message(chat_id, f"All {parts} parts sent. Join them in the download folder.\n"
                        f"macOS/Linux terminal: cat {filename}.part* > {filename}\n"
                        f"Windows Command Prompt: copy /b {filename}.part* {filename}")
    print(f"Sent {filename} ({parts} file(s)).", flush=True)
    return parts


def listen(bot, chat_id, folder, *, stop=None, progress=None, before_poll=None):
    stop = stop if stop is not None else Event()
    print(f"Listening for /backup for {folder}. Press Ctrl+C to stop.", flush=True)
    offset = 0
    started = int(time.time())
    reconnecting = True
    while not stop.is_set():
        if before_poll is not None:
            before_poll()
        if stop.is_set():
            return
        try:
            updates = bot.updates(offset, timeout=5 if progress is not None else 25)
        except BackupError as exc:
            print(exc, file=sys.stderr, flush=True)
            if progress is not None:
                progress(str(exc))
            reconnecting = True
            stop.wait(5)
            continue
        if reconnecting and progress is not None:
            progress("Waiting for /backup in Telegram…")
        reconnecting = False
        for update in updates:
            if stop.is_set():
                return
            offset = update["update_id"] + 1
            message = update.get("message", {})
            if private_sender(message) != chat_id or message.get("date", 0) < started:
                continue
            if message.get("text") != "/backup":
                continue
            try:
                bot.message(chat_id, f"Preparing backup of {folder.name}…")
                if progress is None:
                    send_backup(bot, chat_id, folder)
                else:
                    parts = send_backup(bot, chat_id, folder, progress=progress)
                    progress(f"Backup sent ({parts} files). Waiting for /backup…")
            except (OSError, BackupError) as exc:
                print(f"Backup failed: {exc}", file=sys.stderr, flush=True)
                if progress is not None:
                    progress(f"Backup failed. {exc}")
                try:
                    bot.message(chat_id, "Backup failed. Check Backuper on your computer for details.")
                except BackupError as notify_error:
                    print(notify_error, file=sys.stderr, flush=True)


def run_schedule(bot, chat_id, folder, hours, *, stop, run_now, progress, accept_commands=False):
    interval = hours * 3600
    deadline = time.time() + interval

    def show_next(prefix=""):
        next_run = datetime.fromtimestamp(deadline).strftime("%b %d at %H:%M")
        progress(f"{prefix}Next backup: {next_run}.")

    def check_schedule():
        nonlocal deadline
        scheduled = time.time() >= deadline
        if not scheduled and not run_now.is_set():
            return
        run_now.clear()
        if scheduled:
            deadline = time.time() + interval
        try:
            parts = send_backup(bot, chat_id, folder, progress=progress)
            show_next(f"Backup sent ({parts} file(s)). ")
        except (OSError, BackupError) as error:
            show_next(f"Backup failed. {error} ")

    show_next()
    if accept_commands:
        def listener_progress(status):
            if status != "Waiting for /backup in Telegram…":
                progress(status)

        listen(bot, chat_id, folder, stop=stop, progress=listener_progress, before_poll=check_schedule)
    else:
        while not stop.is_set():
            check_schedule()
            stop.wait(1)


def validate_folder(path):
    folder = Path(path).expanduser().resolve(strict=True)
    if not folder.is_dir() or folder == folder.parent:
        raise BackupError("Choose a specific folder to back up.")
    return folder
