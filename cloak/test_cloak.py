"""
test_cloak.py — CHEYANNE Cloak Verification Script
22DIV / george wu

Tests concealment by checking visibility of processes, files,
and connections before and after cloak activation.

Usage:
    python cloak/test_cloak.py              # pre-cloak visibility check
    python cloak/test_cloak.py --after      # post-cloak verification
"""

import subprocess
import sys
import os

HIDDEN_PROCESSES = [
    "cheyanne_shell.exe",
    "dark_room.exe",
    "cheyanne_implant.exe",
    "cheyanne_inject.exe",
    "cheyanne_stager.exe",
    "cloak_loader.exe",
]

HIDDEN_FILES = [
    "cheyanne_shell.exe",
    "dark_room.exe",
    "cheyanne_implant.exe",
    "cheyanne_inject.exe",
    "cheyanne_inject_dll.dll",
    "cheyanne_stager.exe",
    "osppc.dll",
    "osppcext.dll",
    "cloak.dll",
    "cloak_loader.exe",
    "cheyanne_implant_canary.txt",
    "cheyanne_clean.exe",
]

C2_PORT = 4443


def check_processes():
    print("\n  [PROCESS CHECK]")
    result = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True, text=True
    )
    found = []
    for name in HIDDEN_PROCESSES:
        if name.lower() in result.stdout.lower():
            found.append(name)
            print(f"    VISIBLE: {name}")

    if not found:
        print("    No target processes running (start CHEYANNE components first)")
    return found


def check_files():
    print("\n  [FILE CHECK]")
    bin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
    found = []
    for name in HIDDEN_FILES:
        path = os.path.join(bin_dir, name)
        if os.path.exists(path):
            found.append(name)
            print(f"    VISIBLE: {name}")

    if not found:
        print("    No target files found in bin/")
    return found


def check_connections():
    print("\n  [CONNECTION CHECK]")
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True, text=True
    )
    found = []
    for line in result.stdout.split('\n'):
        if f":{C2_PORT}" in line:
            found.append(line.strip())
            print(f"    VISIBLE: {line.strip()}")

    if not found:
        print(f"    No connections on port {C2_PORT}")
    return found


def main():
    after = "--after" in sys.argv

    if after:
        print("\n  CHEYANNE CLOAK — Post-Activation Verification")
        print("  ==========================================")
        print("  (cloak should be active — items below should be GONE)")
    else:
        print("\n  CHEYANNE CLOAK — Pre-Activation Baseline")
        print("  ======================================")
        print("  (showing what's currently visible)")

    procs = check_processes()
    files = check_files()
    conns = check_connections()

    print("\n  ---------------------------------")
    if after:
        total = len(procs) + len(files) + len(conns)
        if total == 0:
            print("  [+] CONCEALMENT VERIFIED — nothing visible")
        else:
            print(f"  [!] {total} items still visible — cloak may not be active")
    else:
        total = len(procs) + len(files) + len(conns)
        print(f"  [*] {total} items visible (baseline before cloak)")

    print("")


if __name__ == "__main__":
    main()
