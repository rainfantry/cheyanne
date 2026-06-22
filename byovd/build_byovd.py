"""
build_byovd.py — CHEYANNE BYOVD Build Script
22DIV / george wu

Compiles byovd.exe using MSVC (cl.exe).
Runs Defender scan on the binary.

Usage:
    python byovd/build_byovd.py
    python byovd/build_byovd.py --scan    (build + Defender scan)
    python byovd/build_byovd.py --noscan  (build only, skip scan)
"""

import subprocess
import sys
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
OUT_DIR = os.path.join(SCRIPT_DIR, "bin")

VCVARS = r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

SOURCES = [
    "byovd_loader.c",
    "kernel_ops.c",
    "byovd_main.c",
]

PERSIST_SOURCES = [
    "byovd_loader.c",
    "kernel_ops.c",
    "cheyanne_persist.c",
]


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
            for line in result.stderr.strip().split('\n')[:15]:
                print(f"      {line}")
        if result.stdout:
            for line in result.stdout.strip().split('\n')[:15]:
                print(f"      {line}")
        return False
    print(f"  [+] OK")
    return True


def build():
    os.makedirs(OUT_DIR, exist_ok=True)

    src_files = " ".join(os.path.join(SCRIPT_DIR, s) for s in SOURCES)
    exe_out = os.path.join(OUT_DIR, "byovd.exe")

    cmd = (
        f'cmd /c ""{VCVARS}" >nul 2>&1 && '
        f'cl.exe /nologo /O2 /W3 '
        f'{src_files} '
        f'/Fe:"{exe_out}" '
        f'/link psapi.lib kernel32.lib advapi32.lib"'
    )

    persist_files = " ".join(os.path.join(SCRIPT_DIR, s) for s in PERSIST_SOURCES)
    persist_out = os.path.join(OUT_DIR, "cheyanne_persist.exe")

    persist_cmd = (
        f'cmd /c ""{VCVARS}" >nul 2>&1 && '
        f'cl.exe /nologo /O2 /W3 '
        f'{persist_files} '
        f'/Fe:"{persist_out}" '
        f'/link psapi.lib kernel32.lib advapi32.lib shlwapi.lib"'
    )

    print("\n  CHEYANNE BYOVD — Build")
    print("  ====================\n")

    ok = run_cmd(cmd, "Compiling byovd.exe")
    ok2 = run_cmd(persist_cmd, "Compiling cheyanne_persist.exe")

    for junk in glob.glob(os.path.join(SCRIPT_DIR, "*.obj")):
        os.remove(junk)
    for junk in glob.glob(os.path.join(OUT_DIR, "*.obj")):
        os.remove(junk)

    if ok and os.path.exists(exe_out):
        size = os.path.getsize(exe_out)
        print(f"\n  [+] byovd.exe:         {size // 1024} KB")
    if ok2 and os.path.exists(persist_out):
        size = os.path.getsize(persist_out)
        print(f"  [+] cheyanne_persist.exe: {size // 1024} KB")

    return ok and ok2


def scan():
    mp = find_mpcmdrun()
    if not mp:
        print("  [!] MpCmdRun.exe not found — skipping scan")
        return

    print(f"\n  [*] Defender scan ({os.path.basename(os.path.dirname(mp))})")

    for binary in ["byovd.exe", "cheyanne_persist.exe"]:
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

    if "--noscan" not in sys.argv:
        scan()

    print("\n  [*] Build complete\n")


if __name__ == "__main__":
    main()
