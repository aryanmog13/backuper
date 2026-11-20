"""curl transport for Telegram requests routed through an explicit proxy."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit


PROTOCOLS = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")

CURL_ERRORS = {
    5: "Could not resolve the proxy address. Check its host name.",
    6: "Could not resolve the server address. Check the internet connection.",
    7: "Could not connect to the proxy. Check its address and port.",
    28: "The connection timed out. The proxy or the server did not answer.",
    35: "The proxy closed the secure connection. The proxy link may have expired.",
    52: "The proxy closed the connection without a reply. The proxy link may be inactive.",
    56: "The proxy reset the connection. Try again or use another proxy.",
    60: "The certificate of the proxy or server could not be verified.",
    97: "This curl build does not support that proxy type.",
}


class ProxyRequestError(OSError):
    """A proxy or network failure with a message meant for the window."""


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


def _request(url, proxy, data, content_type, timeout):
    # Use curl's stdin config so neither the proxy password nor bot token is in argv.
    def quoted(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    curl = "/usr/bin/curl" if sys.platform == "darwin" else shutil.which("curl.exe" if os.name == "nt" else "curl")
    if not curl:
        raise ProxyRequestError("Install curl to use a proxy.")
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
            raise ProxyRequestError("The connection timed out. The proxy did not answer.") from None
    body, _, status = result.stdout.rpartition(b"\n")
    if result.returncode or not status.isdigit():
        raise ProxyRequestError(
            CURL_ERRORS.get(result.returncode, f"Proxy request failed (curl exit {result.returncode}).")
        )
    return int(status), body


def request_json(url, proxy, data, content_type, timeout):
    code, body = _request(url, proxy, data, content_type, timeout)
    try:
        return code, json.loads(body) if code == 200 and body.strip() else None
    except ValueError:
        return code, None


def request_status(url, proxy, timeout):
    code, _ = _request(url, proxy, b"", "application/json", timeout)
    return code
