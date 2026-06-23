"""
VADER ROOTKIT — Detection Status Scanner
Copies each binary to temp, scans with MpCmdRun, reports results.
Does NOT touch originals — scans copies only.
"""

import os
import sys
import shutil
import subprocess
import tempfile
import glob

MPCMDRUN = None
for p in glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"):
    MPCMDRUN = p
    break
if not MPCMDRUN:
    MPCMDRUN = r"C:\Program Files\Windows Defender\MpCmdRun.exe"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BINARIES = []
for dirpath, _, filenames in os.walk(ROOT):
    if ".git" in dirpath:
        continue
    for f in filenames:
        if f.endswith((".exe", ".dll", ".obj")):
            BINARIES.append(os.path.join(dirpath, f))


def scan_file(src_path):
    tmp_dir = tempfile.mkdtemp(prefix="vader_scan_")
    fname = os.path.basename(src_path)
    tmp_path = os.path.join(tmp_dir, fname)

    try:
        shutil.copy2(src_path, tmp_path)
    except (OSError, PermissionError) as e:
        return {"file": fname, "status": "COPY_FAIL", "detail": str(e)}

    try:
        result = subprocess.run(
            [MPCMDRUN, "-Scan", "-ScanType", "3", "-File", tmp_path,
             "-DisableRemediation"],
            capture_output=True, text=True, timeout=30
        )
        rc = result.returncode
        if rc == 0:
            status = "CLEAN"
        elif rc == 2:
            status = "DETECTED"
        else:
            status = f"RC={rc}"

        return {
            "file": fname,
            "path": os.path.relpath(src_path, ROOT),
            "status": status,
            "size": os.path.getsize(src_path),
        }
    except subprocess.TimeoutExpired:
        return {"file": fname, "path": os.path.relpath(src_path, ROOT),
                "status": "TIMEOUT", "size": os.path.getsize(src_path)}
    finally:
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass


def main():
    print("=" * 65)
    print("  VADER ROOTKIT — Detection Status Scanner")
    print(f"  MpCmdRun: {MPCMDRUN}")
    print(f"  Binaries: {len(BINARIES)}")
    print("=" * 65)

    results = {"CLEAN": [], "DETECTED": [], "OTHER": []}

    for i, bpath in enumerate(sorted(BINARIES)):
        rel = os.path.relpath(bpath, ROOT)
        print(f"  [{i+1}/{len(BINARIES)}] Scanning {rel}...", end=" ", flush=True)
        r = scan_file(bpath)
        print(r["status"])

        if r["status"] == "CLEAN":
            results["CLEAN"].append(r)
        elif r["status"] == "DETECTED":
            results["DETECTED"].append(r)
        else:
            results["OTHER"].append(r)

    print("\n" + "=" * 65)
    print("  RESULTS")
    print("=" * 65)
    print(f"  CLEAN:    {len(results['CLEAN'])}")
    print(f"  DETECTED: {len(results['DETECTED'])}")
    print(f"  OTHER:    {len(results['OTHER'])}")

    if results["DETECTED"]:
        print("\n  --- DETECTED (needs mutation) ---")
        for r in results["DETECTED"]:
            print(f"    {r['path']} ({r['size']} bytes)")

    if results["CLEAN"]:
        print("\n  --- CLEAN (operational) ---")
        for r in results["CLEAN"]:
            print(f"    {r['path']} ({r['size']} bytes)")

    if results["OTHER"]:
        print("\n  --- OTHER ---")
        for r in results["OTHER"]:
            print(f"    {r.get('path', r['file'])} — {r['status']}")


if __name__ == "__main__":
    main()
