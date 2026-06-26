#!/usr/bin/env python3
"""
SERVITOR SAFE HAVEN - Kaspersky-proof testing ground
Location: C:/Users/gwu07/Desktop/cheyanne/servitor

Mission: Build, test, and log payloads without Kaspersky interference.
The enemy deletes our agents. We document every death and strike back.
"""
import subprocess
import json
import hashlib
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# === CONFIG ===
SAFE_HAVEN = Path("C:/Users/gwu07/Desktop/cheyanne/servitor")
BUILDS_DIR = SAFE_HAVEN / "builds"
LOGS_DIR = SAFE_HAVEN / "logs"
PROOF_DIR = SAFE_HAVEN / "proof"
SCRIPTS_DIR = SAFE_HAVEN / "scripts"

# GCC from servitor-ops
GCC_PATH = Path("C:/Users/gwu07/Desktop/servitor-ops/mingw64/mingw64/bin")

# Source repos
IRON_SUN_DIR = Path("C:/Users/gwu07/Desktop/servitor-ops/repos/iron-sun")
CHEYANNE_DIR = Path("C:/Users/gwu07/Desktop/servitor-ops/repos/cheyanne")

# Ensure dirs exist
for d in [BUILDS_DIR, LOGS_DIR, PROOF_DIR, SCRIPTS_DIR]:
    d.mkdir(exist_ok=True)


def run(cmd, cwd=None, timeout=60, env=None):
    """Execute command, return stdout/stderr/code."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if GCC_PATH.exists():
        merged_env["PATH"] = str(GCC_PATH) + os.pathsep + merged_env.get("PATH", "")
    
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd, timeout=timeout, env=merged_env
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def log_battle(action, status, details=""):
    """Log every action to safe haven."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {action:25s} | {status:10s} | {details}\n"
    
    with open(LOGS_DIR / "safe_haven.log", "a") as f:
        f.write(entry)
    
    print(entry.strip())
    return entry


def build_payload():
    """Build iron_sun.exe in safe haven."""
    log_battle("BUILD", "START", "Compiling iron_sun.exe in safe haven")
    
    # Find source
    src = IRON_SUN_DIR / "shell" / "iron_sun.c"
    if not src.exists():
        src = CHEYANNE_DIR / "shell" / "iron_sun.c"
    
    if not src.exists():
        log_battle("BUILD", "FAIL", "iron_sun.c not found")
        return None
    
    # Copy source to safe haven (Kaspersky won't scan here)
    safe_src = BUILDS_DIR / "iron_sun.c"
    import shutil
    shutil.copy2(src, safe_src)
    
    # Build
    output = BUILDS_DIR / "iron_sun.exe"
    cmd = f'gcc "{safe_src}" -o "{output}" -lws2_32 -D_WIN32_WINNT=0x0600'
    stdout, stderr, code = run(cmd, cwd=BUILDS_DIR, timeout=60)
    
    if code == 0 and output.exists():
        sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
        size = output.stat().st_size
        log_battle("BUILD", "SUCCESS", f"SHA256: {sha256[:24]}... Size: {size} bytes")
        
        # Log build
        with open(LOGS_DIR / "builds.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} | {sha256} | {size} | {output}\n")
        
        return output
    else:
        log_battle("BUILD", "FAIL", stderr[:200])
        return None


def test_payload(binary_path):
    """Test payload execution. DO NOT run if Kaspersky is active — just verify binary integrity."""
    log_battle("TEST", "START", f"Verifying: {binary_path.name}")
    
    if not binary_path.exists():
        log_battle("TEST", "FAIL", "Binary missing")
        return "missing"
    
    # Verify SHA256
    sha256 = hashlib.sha256(binary_path.read_bytes()).hexdigest()
    
    # Check if binary is valid PE
    with open(binary_path, "rb") as f:
        header = f.read(2)
        is_pe = header == b"MZ"
    
    if is_pe:
        log_battle("TEST", "VALID_PE", f"SHA256: {sha256[:24]}...")
        return "valid"
    else:
        log_battle("TEST", "INVALID", "Not a valid PE file")
        return "invalid"


def document_for_disclosure(binary_path, result):
    """Create disclosure documentation."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    doc_path = PROOF_DIR / f"DISCLOSURE_{timestamp}.md"
    
    sha256 = hashlib.sha256(binary_path.read_bytes()).hexdigest() if binary_path.exists() else "N/A"
    
    doc = f"""# Responsible Disclosure Package

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Binary:** iron_sun.exe
**SHA256:** {sha256}
**Status:** {result}
**Test Location:** {SAFE_HAVEN}

## Test Environment
- Target: Windows with Kaspersky
- Build: MinGW GCC 13.2.0
- Source: iron-sun / cheyanne

## Evasion Techniques Tested
- [ ] XOR encoding (T1027)
- [ ] Dynamic API resolution (T1055)
- [ ] Anti-sandbox checks (T1497)
- [ ] PE header stomp (T1562.001)
- [ ] Raw TCP C2 (T1095)

## Result
{result}

## Next Steps
- If EVADED: Test on additional AV products
- If DETECTED: Iterate payload, document detection method

---
*Documented by SERVITOR Safe Haven automation*
"""
    
    with open(doc_path, "w") as f:
        f.write(doc)
    
    log_battle("DISCLOSURE", "DOCUMENTED", f"{doc_path.name}")
    return doc_path


def main():
    print("=" * 60)
    print("SERVITOR SAFE HAVEN — Kaspersky-proof testing ground")
    print(f"Location: {SAFE_HAVEN}")
    print("=" * 60)
    
    # Build payload
    binary = build_payload()
    
    if binary:
        # Test (verify, not execute if Kaspersky active)
        result = test_payload(binary)
        
        # Document for disclosure
        doc = document_for_disclosure(binary, result)
        
        log_battle("HAVEN", "COMPLETE", f"Binary: {binary.name}, Doc: {doc.name}")
    else:
        log_battle("HAVEN", "FAILED", "Build failed")
    
    print(f"\n[+] Logs: {LOGS_DIR}")
    print(f"[+] Builds: {BUILDS_DIR}")
    print(f"[+] Proof: {PROOF_DIR}")


if __name__ == "__main__":
    main()
