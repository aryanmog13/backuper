# Backuper

<img src="backuper_app/assets/backuper-icon.png" alt="Backuper icon" width="96">

Send a folder from macOS, Windows, or Linux to your private Telegram bot chat as a ZIP archive. Backuper can send a backup immediately, repeat it on a schedule, or respond to `/backup` in Telegram. Any regular folder works.

[Download source ZIP](https://github.com/aryanmog13/backuper/archive/refs/heads/main.zip) · [راهنمای فارسی](README.fa.md) · [Desktop test runs](https://github.com/aryanmog13/backuper/actions/workflows/desktop.yml)

## Requirements

| Dependency | When you need it | Official download or package |
| --- | --- | --- |
| Python 3.11+ with Tcl/Tk | Running the desktop app | [macOS installer](https://www.python.org/downloads/macos/), [Windows installer](https://www.python.org/downloads/windows/) |
| Tkinter on Linux | If your Python 3.11+ installation lacks Tkinter | [Debian `python3-tk`](https://packages.debian.org/trixie/python3-tk), [Ubuntu `python3-tk`](https://packages.ubuntu.com/search?keywords=python3-tk), [Fedora `python3-tkinter`](https://packages.fedoraproject.org/pkgs/python3.14/python3-tkinter/) |
| Telegram bot token | Pairing Backuper and receiving backups | [BotFather](https://t.me/BotFather) |
| curl | Using a proxy in the desktop app | [curl downloads](https://curl.se/download.html) |
| Xray-core | Importing VLESS, VMess, or Trojan links directly | [Xray-core releases](https://github.com/XTLS/Xray-core/releases) |

## One-line install

Install Python 3.11+ with Tkinter from the links above. The command downloads Backuper from GitHub and installs it in your user folder. The macOS and Linux command also uses curl.

**macOS or Linux**

```sh
(t=$(mktemp) && trap 'rm -f "$t"' 0 && curl -fsSL https://raw.githubusercontent.com/aryanmog13/backuper/refs/heads/main/install.py -o "$t" && python3 "$t")
```

**Windows PowerShell**

```powershell
& { $t = [IO.Path]::GetTempFileName(); try { Invoke-WebRequest -UseBasicParsing https://raw.githubusercontent.com/aryanmog13/backuper/refs/heads/main/install.py -OutFile $t -ErrorAction Stop; py -3 $t } finally { Remove-Item -LiteralPath $t } }
```

The installer prints the launcher path. On macOS it installs into `~/Applications/Backuper`, on Windows into `%LOCALAPPDATA%\BackuperApp`, and on Linux into `${XDG_DATA_HOME:-$HOME/.local/share}/Backuper`.

## Quick start

Open the launcher in the installed folder. For a manual install, extract the source ZIP or clone the repository and open the launcher from that folder.

| Platform | Open the desktop app |
| --- | --- |
| macOS | Double-click `Backuper.app` in Finder. |
| Windows | Double-click `Backuper-Windows.cmd`. Install Python with Tcl/Tk and the Windows Python launcher or add Python to PATH. |
| Linux | Run `sh Backuper-Linux.sh` from a desktop session. Install `python3-tk` on Debian or Ubuntu, or `python3-tkinter` on Fedora, if Tkinter is missing. |

1. Open [BotFather](https://t.me/BotFather) in Telegram, send `/newbot`, and copy your new bot's token.
2. Paste the token into Backuper, click **Connect Bot**, then **Open Telegram**. Press **Start** in the private chat to pair it.
3. Click **Choose Folder**, then **Send ZIP**. The archive appears in your private bot chat.

If the Telegram Bot API is reachable only through a proxy on your network, configure the proxy before connecting the bot.

## Backup modes

| Mode | How it works |
| --- | --- |
| **Send ZIP** | Creates and sends a fresh archive of the selected folder. |
| **Listen for /backup** | Waits for `/backup` in the paired private chat and backs up the folder selected in the app. |
| **Start Schedule** | Sends a backup every number of hours you enter. The default is six hours, and the first run happens after one interval. Enable **Also listen for /backup** to combine a schedule with Telegram commands. |

Keep Backuper open while listening or running a schedule. If the computer sleeps through a scheduled run, Backuper runs one backup after wake. The app remembers the selected folder and interval when you start a schedule. Click **Start Schedule** again after reopening Backuper.

## Proxies

Set a proxy in **Proxy** and click **Save Proxy**. The desktop app uses it for pairing, polling commands, and uploading files. Clear the field and save to remove it. Proxy support uses `curl`, which must be available on the computer.

| Input | Example |
| --- | --- |
| Host and port | `127.0.0.1:1080` |
| Host, port, and credentials | `proxy.example:1080:alice:password` |
| Credentials before the host | `alice:password@proxy.example:1080` |
| HTTP or HTTPS URL | `https://alice:password@proxy.example:443` |
| SOCKS URL | `socks5h://127.0.0.1:10808` |
| V2Ray-compatible share link | `vless://…`, `vmess://…`, or `trojan://…` |

For inputs without a URL scheme, choose the protocol in the dropdown. The app accepts HTTP, HTTPS, SOCKS4, SOCKS4a, SOCKS5, and SOCKS5h. Percent-encode special characters in credentials when pasting a full URL.

For VLESS, VMess, or Trojan links, install [Xray-core](https://github.com/XTLS/Xray-core/releases) and put `xray` or `xray.exe` on PATH. Backuper starts a local Xray SOCKS listener for its Telegram traffic and stops it when the operation ends. Supported link transports include TCP, WebSocket, gRPC, HTTPUpgrade, and XHTTP, with common TLS and REALITY options. You can also use the local SOCKS address from a client that already manages your proxy configuration.

## Restore a backup

Download and open the ZIP from Telegram. Backuper preserves the folder structure, including hidden files and empty directories. It skips symbolic links and special files. On Windows it also skips junctions and other reparse points. ZIP archives are unencrypted.

For a large archive, Backuper sends numbered parts and posts the reassembly command when the upload finishes. Download all parts to the same folder and run the command there. For an archive named `example.zip`, the commands look like this.

**macOS or Linux**

```sh
cat example.zip.part* > example.zip
```

**Windows Command Prompt**

```cmd
copy /b example.zip.part* example.zip
```

Open the resulting ZIP after the command finishes.

## Command line

From the project folder, run the commands below. On Windows, use `py -3` in place of `python3`.

```sh
python3 backuper.py setup
python3 backuper.py send "/path/to/folder"
python3 backuper.py listen "/path/to/folder"
```

The desktop app and CLI share the bot pairing. Schedule and proxy settings are managed in the desktop app. Local settings are stored in `~/.config/backuper/` on macOS and Linux and in `%LOCALAPPDATA%\Backuper\` on Windows.

## Development

- [`backuper.py`](backuper.py) opens the command-line interface, and [`backuper_gui.py`](backuper_gui.py) launches the desktop window.
- [`backuper_app/`](backuper_app/) contains the backup service, desktop UI, and proxy integrations.
- [`tests/`](tests/) contains the desktop smoke tests.

Run the ZIP, schedule, and desktop tests with Python's standard test runner. The window test needs a desktop session. On headless Linux, run the command under `xvfb-run -a`.

```sh
python -B -m unittest discover -s tests -v
```
