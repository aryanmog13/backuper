#!/usr/bin/env python3
"""Command-line launcher for Backuper."""

import argparse
from pathlib import Path
import sys

from backuper_app.backup_service import BackupError, listen, load_config, send_backup, setup, validate_folder

def main():
    parser = argparse.ArgumentParser(description="Send a folder backup to your private Telegram chat.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="pair a bot with your Telegram chat")
    commands.add_parser("send", help="send a backup immediately").add_argument("folder", type=Path)
    commands.add_parser("listen", help="wait for /backup in Telegram").add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.command == "setup":
        setup()
        return
    folder = validate_folder(args.folder)
    bot, chat_id = load_config()
    if args.command == "send":
        send_backup(bot, chat_id, folder)
    else:
        listen(bot, chat_id, folder)


if __name__ == "__main__":
    try:
        main()
    except (OSError, BackupError, EOFError) as error:
        sys.exit(str(error))
    except KeyboardInterrupt:
        sys.exit(130)
