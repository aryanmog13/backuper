"""Install Backuper from the public GitHub source archive into the user profile."""

import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile


ARCHIVE_URL = "https://github.com/aryanmog13/backuper/archive/refs/heads/main.zip"
APP_FILES = (
    "backuper.py", "backuper_gui.py", "proxy_transport.py", "xray_proxy.py",
    "README.md", "README.fa.md",
)
LAUNCHERS = {
    "darwin": ("Backuper.app/Contents/Info.plist", "Backuper.app/Contents/MacOS/Backuper"),
    "win32": ("Backuper-Windows.cmd",),
    "linux": ("Backuper-Linux.sh",),
}
EXECUTABLES = {"Backuper.app/Contents/MacOS/Backuper", "Backuper-Linux.sh"}


def install_location(platform):
    home = Path.home()
    if platform == "darwin":
        return home / "Applications" / "Backuper"
    if platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "BackuperApp"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "Backuper"


def install(destination, platform):
    files = APP_FILES + LAUNCHERS[platform]
    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink() and all(
            (destination / name).is_file() for name in files
        ):
            return False
        raise FileExistsError(f"Choose a different path for the existing item at {destination}, then retry.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".backuper-install-", dir=destination.parent) as temporary:
        work = Path(temporary)
        download = work / "source.zip"
        staging = work / "app"
        with urlopen(ARCHIVE_URL, timeout=60) as response, download.open("wb") as output:
            shutil.copyfileobj(response, output)
        with ZipFile(download) as archive:
            for name in files:
                installed = staging / name
                installed.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(f"backuper-main/{name}") as source, installed.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if name in EXECUTABLES:
                    installed.chmod(0o755)
        staging.rename(destination)
    return True


def main():
    if sys.version_info < (3, 11):
        sys.exit("Backuper requires Python 3.11 or later.")
    if sys.platform not in LAUNCHERS:
        sys.exit("Backuper supports macOS, Windows, and Linux.")
    try:
        import tkinter
    except ImportError:
        sys.exit("Install Python with Tkinter before running the installer. See the Backuper README.")

    destination = install_location(sys.platform)
    try:
        installed = install(destination, sys.platform)
    except (OSError, KeyError, BadZipFile) as error:
        sys.exit(f"Installation failed: {error}")
    print(f"{'Installed' if installed else 'Already installed'}: {destination}")
    if sys.platform == "darwin":
        print(f"Open Backuper with: open {shlex.quote(str(destination / 'Backuper.app'))}")
    elif sys.platform == "win32":
        print(f"To open Backuper, double-click: {destination / 'Backuper-Windows.cmd'}")
    else:
        print(f"Open Backuper with: sh {shlex.quote(str(destination / 'Backuper-Linux.sh'))}")


if __name__ == "__main__":
    main()
