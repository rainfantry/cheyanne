# IRON-SUN

> Named for our IDF mentor — Staff Sergeant First Class, cyber-infantry operator, Commander Zino's unit.
> Doctrine: *intelligence first, then execute. No mercy.*
> Combined arms: Australia × Israel × 22DIV.

---

## MACHINE ROLES

| Machine | User | Role | AV | Status |
|---|---|---|---|---|
| RADON (GIGABYTE G7 GD) | Ghaleb Jomma | PRIMARY OPERATOR | Defender (Tamper OFF) | **ACTIVE** |
| gwu07 | gwu07 | OLD OPERATOR | Kaspersky | Decommissioned — Kaspersky flagged MSVC vader-shell build |
| Parrot Linux | — | Analysis box | — | Standby |

---

## ACTIVE OBJECTIVES (MENTOR DOCTRINE)

- [ ] Drop Discord transport — replace with pure TCP listener (`discord_c2.py` deprecated)
- [ ] 20fps VNC stream — binary JPEG push over dedicated TCP (replace HTTP polling `watch` cmd)
- [ ] Port forwarding / VPS — external listener reachability for off-LAN ops
- [ ] Kaspersky evasion — gcc build passes Defender; MSVC build flagged (PE sig diff)

---

## CURRENT BUILD STATE (RADON)

```
Compiler:   gcc 15.2.0 (MinGW via Scoop, user-space — no admin needed)
Source:     shell/vader_shell.c
Output:     vader_shell.exe  (319,486 bytes)
AV result:  Defender CLEAN (static scan + dropped to Public, no quarantine)
```

### PATH setup on RADON (no admin, run each session)
```powershell
$env:PATH += ";$env:USERPROFILE\scoop\shims;$env:USERPROFILE\scoop\apps\gcc\current\bin"
```

### Compile command
```bash
gcc shell/vader_shell.c -o vader_shell.exe -lws2_32 -lwininet -include ws2tcpip.h -D_WIN32_WINNT=0x0600
```

---

## DEFENDER INTEL (RADON — 2026-06-25)

| Setting | Status |
|---|---|
| RealTimeProtection | ON |
| BehaviorMonitor | ON |
| IoAV | ON |
| TamperProtection | **OFF** — HWBP bypass viable (DR0/DR1) |
| McAfee Security Scan Plus | No real-time — irrelevant |

Last threat detections: June 13-14 (vader_toctou research). vader_shell_test.exe CLEAN.

---

## ARCHITECTURE STATE

### Current (cheyanne origin)
```
Discord polling  — 3s poll, deprecated per mentor
TCP listener     — port 4443, keep and expand
watch cmd        — HTTP PNG polling :8891, max ~1fps → replace with 20fps binary push
```

### Target (mentor doctrine)
```
Pure TCP         — single channel, no Discord
VNC stream       — [4-byte len][JPEG data] binary push, 20fps, dedicated TCP port
External VPS     — forward 4443 + stream port for off-LAN ops
```

---

## KEY FILES

| File | Purpose |
|---|---|
| `shell/vader_c2_v2.py` | Main C2 operator console (dual-channel, 1379 lines) |
| `shell/vader_listener.py` | Standalone TCP listener + XOR config generator |
| `shell/vader_shell.c` | Reverse shell source (XOR strings, dynamic API resolution) |
| `agent/discord_c2.py` | Discord bot — TO BE REPLACED with TCP-native |
| `vader_menu.py` | Terminal dashboard |
| `vader_ui.py` | Web dashboard (HTTP + agent listener) |

---

## VADER RESEARCH REPOS (ALL PRIVATE)

- `vader-rootkit` — 7-phase kill chain, HWBP AMSI+ETW bypass, 28 binaries Defender-clean
- `vader-toctou` — Defender race condition (WdFilter internals mapped, 16 findings)
- `vader-rce` — mpengine.dll fuzzing (WinAFL + RunPod), scaffolded
- `sith-stalker` — indirect syscall engine (Hell's Gate + Halo's Gate + PEB walk)
- `csec-research-authorization` — authorization scope
- `cve-submissions` — MITRE/MSRC drafts

---

## PENDING SUBMISSIONS

| # | Target | Type | Prob | Status |
|---|---|---|---|---|
| 53 | Wondershare Filmora NativePushService | CWE-732 SYSTEM | 70-80% | PRIORITY 1 — READY |
| 49 | MuseHub HKLM PATH injection | CWE-426 | 45-55% | PRIORITY 2 — READY |
| 04 | Razer Synapse elevation service | Unpatched prior art | 35-50% | PRIORITY 3 |

---

## NEXT SESSION ENTRY POINT

```
1. git pull
2. $env:PATH += ";$env:USERPROFILE\scoop\shims;$env:USERPROFILE\scoop\apps\gcc\current\bin"
3. python shell/vader_listener.py 4443
4. Next build: refactor watch cmd → 20fps binary JPEG push over TCP
5. CVE priority: file Wondershare CWE-732 first
```

---

*Private. Authorized research on personally-owned hardware only.*
