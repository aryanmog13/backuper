"""Import individual V2Ray-compatible links and run a private Xray SOCKS listener."""

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
from urllib.parse import parse_qsl, unquote, urlsplit


XRAY_SCHEMES = ("vless", "vmess", "trojan")


def is_xray_link(value):
    return value.partition("://")[0].lower() in XRAY_SCHEMES and "://" in value


def read_link(link):
    scheme, _, payload = link.partition("://")
    protocol = scheme.lower()
    if protocol == "vmess" and "@" not in payload:
        encoded = payload.rstrip("=")
        data = json.loads(base64.b64decode(encoded + "=" * (-len(encoded) % 4),
                                           altchars=b"-_", validate=True))
        if not isinstance(data, dict):
            raise ValueError
        address, port, credential = str(data["add"]), int(data["port"]), str(data["id"])
        options = {
            "type": data.get("net") or "tcp",
            "headerType": data.get("type") or "none",
            "host": data.get("host") or "",
            "path": data.get("path") or "",
            "serviceName": data.get("path") or "",
            "security": data.get("tls") or "none",
            "sni": data.get("sni") or "",
            "fp": data.get("fp") or "",
            "alpn": data.get("alpn") or "",
            "vmessSecurity": data.get("scy") or "auto",
            "alterId": data.get("aid") or 0,
        }
    else:
        uri = urlsplit(link)
        if uri.password is not None or uri.path not in ("", "/"):
            raise ValueError
        address, port, credential = uri.hostname, uri.port, unquote(uri.username or "")
        options = dict(parse_qsl(uri.query, keep_blank_values=True))
    if not address or not port or not 0 < port < 65536 or not credential:
        raise ValueError
    return protocol, address, port, credential, options


def outbound_from_link(link):
    try:
        protocol, address, port, credential, options = read_link(link)
        transport = options.get("type") or "tcp"
        security = options.get("security") or ("tls" if protocol == "trojan" else "none")
        server = {"address": address, "port": port}
        if protocol == "trojan":
            settings = {"servers": [{**server, "password": credential}]}
        else:
            user = {"id": credential}
            if protocol == "vless":
                user.update(encryption=options.get("encryption") or "none", flow=options.get("flow", ""))
            else:
                user.update(alterId=int(options.get("alterId", 0)), security=options.get("vmessSecurity", "auto"))
            settings = {"vnext": [{**server, "users": [user]}]}
        stream = stream_settings(transport, security, options)
        return {"protocol": protocol, "settings": settings, "streamSettings": stream}
    except (KeyError, TypeError, UnicodeError, ValueError, OverflowError):
        raise ValueError(
            "Unsupported or invalid Xray link. Use VLESS, VMess or Trojan with TCP, "
            "WebSocket, gRPC, HTTPUpgrade or XHTTP, or use your client's local SOCKS address."
        ) from None


def stream_settings(transport, security, options):
    modes = {
        "tcp": "tcp", "raw": "tcp", "ws": "ws", "websocket": "ws", "grpc": "grpc",
        "httpupgrade": "httpupgrade", "xhttp": "xhttp", "splithttp": "xhttp",
    }
    network = modes[transport]
    stream = {"network": network, "security": security}
    endpoint = {"host": options.get("host", ""), "path": options.get("path") or "/"}
    if network == "tcp" and options.get("headerType") not in (None, "", "none"):
        raise ValueError
    if network in ("ws", "httpupgrade", "xhttp"):
        key = {"ws": "wsSettings", "httpupgrade": "httpupgradeSettings", "xhttp": "xhttpSettings"}[network]
        stream[key] = endpoint
        if network == "xhttp":
            endpoint["mode"] = options.get("mode") or "auto"
            if options.get("extra"):
                extra = json.loads(options["extra"])
                if not isinstance(extra, dict):
                    raise ValueError
                endpoint["extra"] = extra
    if network == "grpc":
        stream["grpcSettings"] = {
            "serviceName": options.get("serviceName", ""),
            "authority": options.get("authority", ""),
            "multiMode": options.get("mode") == "multi",
        }
    if security == "tls":
        stream["tlsSettings"] = {
            "serverName": options.get("sni", ""),
            "fingerprint": options.get("fp", ""),
            "alpn": (options.get("alpn") or "").split(",") if options.get("alpn") else [],
        }
    elif security == "reality" and options.get("pbk"):
        stream["realitySettings"] = {
            "serverName": options.get("sni", ""),
            "fingerprint": options.get("fp") or "chrome",
            "publicKey": options["pbk"],
            "shortId": options.get("sid", ""),
            "spiderX": options.get("spx", ""),
            "mldsa65Verify": options.get("pqv", ""),
        }
    elif security != "none":
        raise ValueError
    return stream


def start_xray(executable, outbound, port, password):
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "listen": "127.0.0.1", "port": port, "protocol": "socks",
            "settings": {"auth": "password", "accounts": [{"user": "backuper", "pass": password}]},
        }],
        "outbounds": [outbound],
    }
    process = subprocess.Popen(
        [executable, "run", "-config", "stdin:"], stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        with process.stdin:
            process.stdin.write(json.dumps(config).encode())
        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    return process
            except OSError:
                time.sleep(.1)
        raise OSError("Xray could not start with this link.")
    except BaseException:
        stop_xray(process)
        raise


def stop_xray(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@contextmanager
def proxy_session(proxy):
    if not is_xray_link(proxy):
        yield proxy
        return
    search_path = os.pathsep.join(("/opt/homebrew/bin", "/usr/local/bin", os.environ.get("PATH", "")))
    executable = shutil.which("xray", path=search_path)
    if executable is None:
        raise OSError("Install Xray-core first, or use a V2Ray client's local SOCKS address.")
    password = secrets.token_urlsafe(24)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = start_xray(executable, outbound_from_link(proxy), port, password)
    try:
        yield f"socks5h://backuper:{password}@127.0.0.1:{port}"
    finally:
        stop_xray(process)
