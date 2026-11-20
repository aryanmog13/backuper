"""curl transport for Telegram requests routed through an explicit proxy."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, urlsplit


PROTOCOLS = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")


def normalize_proxy(value, default="http"):
    value = value.strip()
    if not value:
        return ""
    try:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError
        if default not in PROTOCOLS:
            raise ValueError
        if "://" not in value:
            shorthand = re.fullmatch(
                r"(\[[^\]]+\]|[^:\s]+):([0-9]+):([^:]+):(.*)", value,
            )
            if shorthand:
                host, port, username, password = shorthand.groups()
                value = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
            value = f"{default}://{value}"
        parsed = urlsplit(value)
        if (parsed.scheme not in PROTOCOLS or not parsed.hostname or not parsed.port
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or any(char.isspace() for char in parsed.netloc)
                or parsed.netloc.count("@") > 1 or "\\" in parsed.netloc):
            raise ValueError
        return f"{parsed.scheme}://{parsed.netloc}"
    except ValueError:
        raise ValueError(
            "Enter an HTTP, HTTPS or SOCKS proxy as host:port, host:port:user:pass, "
            "or a URL such as socks5h://user:pass@host:port."
        ) from None


def request_json(url, proxy, data, content_type, timeout):
    # Use curl's stdin config so neither the proxy password nor bot token is in argv.
    def quoted(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    curl = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if not curl:
        raise OSError("Install curl to use a proxy.")
    with tempfile.TemporaryDirectory(prefix="backuper-request-") as temporary:
        payload = Path(temporary) / "body"
        payload.write_bytes(data)
        options = {
            "url": url,
            "proxy": proxy,
            "noproxy": "",
            "header": f"Content-Type: {content_type}",
            "data-binary": f"@{payload}",
            "max-time": str(timeout),
            "connect-timeout": str(min(10, timeout)),
            "write-out": "\\n%{http_code}",
        }
        config = "\n".join(f"{key} = {quoted(value)}" for key, value in options.items())
        try:
            result = subprocess.run(
                [curl, "--disable", "--silent", "--config", "-"],
                input=config.encode(), capture_output=True, timeout=timeout + 5, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise OSError("Proxy request timed out.") from None
    body, _, status = result.stdout.rpartition(b"\n")
    if result.returncode or not status.isdigit():
        status = result.returncode
        raise OSError(f"Proxy request failed (curl exit {status}).")
    code = int(status)
    return code, json.loads(body) if code == 200 else None
