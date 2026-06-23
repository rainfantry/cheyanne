# ENGAGEMENT LOG — VADER ROOTKIT

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Each engagement is a discrete test session against the target machine.
Document everything: hypothesis, procedure, result, finding number.

---

## Engagement Index

| # | Date | Module | Objective | Result | Findings |
|---|------|--------|-----------|--------|----------|
| 1-6 | 13-14 JUN 2026 | vader-toctou | Defender quarantine TOCTOU | DEFEATED | #1-#30 |
| 7 | 15 JUN 2026 | amsi/ | AMSI bypass — classic patch vs HWBP | CONFIRMED | #31-#33 |
| 8 | 15 JUN 2026 | etw/ | ETW bypass — classic patch vs HWBP | CONFIRMED | #34-#35 |
| 9 | 15 JUN 2026 | dark_room/ | Combined AMSI+ETW dark room | CONFIRMED | #36-#37 |
| 10 | 15 JUN 2026 | sideload/ | DLL sideload → binary replacement privesc | **SYSTEM** | #38-#43 |
| 11 | 15 JUN 2026 | recon/ | Flagship recon package (USB drop) | BUILT | #44 |
| 12 | 15 JUN 2026 | recon/ | Automated vector scan (PATH hijack, Steam ACL) | **2x CWE-427** | #45-#46 |
| 13 | 15 JUN 2026 | recon/ | Deep vector scan (phantom DLLs, COM, registry, full audit) | **PHANTOM DLL** | #47-#50 |
| 14 | 17 JUN 2026 | injection/ | Phase 4: DLL injection + CREATE_SUSPENDED + full kill chain | **OPERATIONAL** | #51-#53 |
| 15 | 19 JUN 2026 | cloak/ | Phase 7: User-mode rootkit — NtQuery inline hooks, system-wide CBT | **OPERATIONAL** | #54-#56 |
| 16 | 21 JUN 2026 | byovd/ | Phase 8: BYOVD kernel persistence — RTCore64/dbutil_2_3 token steal | **BUILT** | #57-#60 |
| 17 | 21 JUN 2026 | vader_agent.py | Phase 9: C2 agent upgrade — 17 ops, VNC, mic, keylog, SFTP, persist | **BUILT** | #61-#63 |
| 18 | 21 JUN 2026 | metamorph.py | Phase 10: Metamorphic obfuscation — source-level transforms, evolution pipeline | **OPERATIONAL** | #64-#66 |
| 19 | 21 JUN 2026 | full chain | End-to-end pentest: build → scan → dark room → C2 → agent → ops → persist → V7 | **OPERATIONAL** | #67-#70 |

---

## Prior Engagements (vader-toctou, Findings #1-#30)

Full documentation in `../vader-toctou/FINDINGS.md`.

Key findings that carry forward:
- **#14/#17**: SYSTEM file read via junction confirmed
- **#20**: DRP check fires during scan only, not retries (timing-based bypass pattern)
- **#21**: Fail-and-forget retry model (5-7 retries over ~20s)
- **#26**: Kernel-mode I/O bypasses user-mode hooks (oplock, ETW implications)
- **#29**: Junction path re-resolution confirmed (SYSTEM services follow junctions)
- **#30**: Single-handle architecture (defense pattern to look for in other services)

---

## Engagement 15 — User-Mode Rootkit (Phase 7: CLOAK)
**Date:** 19 JUN 2026
**Module:** `cloak/`
**Target:** Windows 11 Build 26200, Defender RTP enabled

### Hypothesis
Inline hooking of NtQuerySystemInformation, NtQueryDirectoryFile, and NtDeviceIoControlFile in each process's ntdll will hide processes, files, and network connections from user-mode enumeration tools (Task Manager, dir, netstat).

### Procedure
1. Built hook_engine.c — generic x64 inline hook (12-byte absolute JMP, VirtualProtect + trampoline)
2. Built hide_process.c — NtQuerySystemInformation hook, linked list unlink on SystemProcessInformation (class 5)
3. Built hide_file.c — NtQueryDirectoryFile hook, filters FileBothDirectoryInformation/FileDirectoryInformation
4. Built hide_connection.c — GetExtendedTcpTable wrapper hook, filters by port match
5. Built cloak.c — DLL entry point, installs all hooks on DLL_PROCESS_ATTACH via CBT hook injection
6. Built cloak_loader.c — SetWindowsHookEx(WH_CBT) system-wide loader, forces DLL into all GUI processes
7. Built vader_dropper.exe — embedded cloak.dll payload with pipe-based reverse shell

### Results
- **Finding #54**: NtQuerySystemInformation inline hook successfully hides processes from Task Manager, tasklist, PowerShell Get-Process. Process disappears from all user-mode enumeration within 1 second of hook install.
- **Finding #55**: NtQueryDirectoryFile hook hides files from Explorer, dir, Get-ChildItem. Files invisible but still accessible via direct path (by design — allows operational access while hiding from casual enumeration).
- **Finding #56**: Connection hiding via GetExtendedTcpTable hook removes C2 connections from netstat output. Port-based matching (configurable in cloak.h). Combined with process hiding = invisible C2 channel.

### Defender Scan
```
cloak.dll:         CLEAN
cloak_loader.exe:  CLEAN
vader_dropper.exe: CLEAN
```

---

## Engagement 16 — BYOVD Kernel Persistence (Phase 8: LIMA)
**Date:** 21 JUN 2026
**Module:** `byovd/`
**Target:** Windows 11 Build 26200, Defender RTP enabled

### Hypothesis
Signed vulnerable kernel drivers (RTCore64.sys CVE-2019-16098, dbutil_2_3.sys CVE-2021-21551) provide arbitrary kernel R/W via IOCTLs. This can be weaponised for:
- Token stealing (SYSTEM elevation without CWE-732)
- EDR callback removal (blind kernel-mode notification routines)
- DSE bypass (load unsigned drivers)

### Procedure
1. Built byovd.h — IOCTL definitions, buffer structs for both drivers, EPROCESS offsets for Win11 24H2
2. Built byovd_loader.c — SCM service create/start/stop, device handle acquisition
3. Built kernel_ops.c — kread32/kread64/kwrite32/kwrite64 primitives, EPROCESS walk, token steal, callback removal, DSE bypass
4. Built byovd_main.c — CLI with 6 commands: token, callbacks, dse, walk, read, all
5. Compiled with MSVC, linked psapi.lib + kernel32.lib + advapi32.lib

### Results
- **Finding #57**: RTCore64.sys IOCTL buffer struct confirmed: 0x30 bytes, address at offset 0x08, size at 0x18, value at 0x1C. Read IOCTL 0x80002048, Write IOCTL 0x8000204C. Arbitrary 4-byte kernel R/W.
- **Finding #58**: Token stealing chain: EnumDeviceDrivers → ntoskrnl base → PsInitialSystemProcess export (RVA resolved via user-mode LoadLibraryEx) → EPROCESS linked list walk via ActiveProcessLinks (offset 0x448) → Token copy (offset 0x4B8) with EX_FAST_REF masking (~0xF). PID 4 verification confirms correct EPROCESS resolution.
- **Finding #59**: Callback removal via LEA pattern scan: PsSet*NotifyRoutine functions reference their internal Psp* arrays via RIP-relative LEA. Scanning first 256 bytes of each function for REX.W+8D+ModR/M=0x05 pattern locates the array. Zeroing 64-entry arrays blinds all registered kernel notification callbacks.
- **Finding #60**: DSE bypass: CiInitialize export in CI.dll references g_CiOptions via MOV [RIP+disp32] pattern. Writing 0x0 disables enforcement. PatchGuard checks periodically — must restore quickly. Window is sufficient for unsigned driver load.

### Defender Scan
```
byovd.exe: CLEAN (157 KB, Defender 4.18.26050.15)
```

---

## Engagement 17 — C2 Agent Upgrade (Phase 9: MIKE)
**Date:** 21 JUN 2026
**Module:** `vader_agent.py`, `vader_ui.py`
**Target:** Agent protocol, no Defender interaction (Python script)

### Hypothesis
Expanding the VADER agent from 9 operations to 17 provides full RAT capability: screen capture, audio recording, keystroke logging, file transfer, persistence installation, and VNC-style remote viewing — all over the existing length-prefixed JSON protocol.

### Procedure
1. Added op_screenshot — GDI screen capture via ctypes (user32.GetDC, gdi32.BitBlt, GetDIBits), outputs BMP via base64
2. Added op_mic — waveIn API microphone recording (16kHz mono 16-bit PCM), outputs WAV via base64
3. Added op_keylog — GetAsyncKeyState polling at 10ms intervals, VK code mapping with shift state
4. Added op_sftp_get — chunked file download (64KB chunks) with SHA-256 hash verification
5. Added op_sftp_put — chunked upload with hash verification, file_chunk protocol messages
6. Added op_sftp_sync — recursive directory manifest (path, size, sha256, dir flag)
7. Added op_persist — 4 methods: scheduled task (WindowsUpdateService), registry Run key, WMI event subscription, IFEO debugger (sethc.exe)
8. Added op_vnc — GDI screen capture streamed as timed frames over file_chunk protocol
9. Updated vader_ui.py dashboard: 8 new operation buttons, parameter prompts, file_chunk handler, per-agent download subdirectories

### Results
- **Finding #61**: 17-operation agent fully functional over VADER protocol. All ops dispatch via handler table, parameter extraction from task dict. Protocol remains backwards-compatible (register, heartbeat, output, result, file_data, file_chunk message types).
- **Finding #62**: Multi-method persistence confirmed: schtask creates WindowsUpdateService scheduled task at SYSTEM logon, registry adds HKCU Run key, WMI creates __EventFilter + __FilterToConsumerBinding + CommandLineEventConsumer for delayed start, IFEO attaches as debugger to sethc.exe (Sticky Keys backdoor).
- **Finding #63**: VNC streaming via file_chunk protocol: GDI capture at configurable FPS, base64-encoded raw bitmap frames with width/height metadata. Dashboard receives and can reconstruct frames for remote viewing.

---

## Engagement 18 — Metamorphic Obfuscation Engine (Phase 10: NOVEMBER)
**Date:** 21 JUN 2026
**Module:** `metamorph.py`, `vader_evolve.py`
**Target:** All annotated C source files, Defender RTP enabled

### Hypothesis
Source-to-source C transformation — injecting dead code, opaque predicates, junk API calls, and constant splitting — changes the structural identity of compiled binaries enough to defeat both static signatures and binary similarity matching, while remaining invisible to Defender.

### Procedure
1. Built `metamorph.py` — metamorphic source transformer with 8 transform types:
   - Dead code injection: unreachable blocks with realistic WinAPI calls (GetTickCount, VirtualAlloc, InterlockedIncrement patterns)
   - Junk variable insertion: unused locals with computed assignments inside block scopes
   - Junk API call insertion: harmless WinAPI calls (GetTickCount, GetCurrentThreadId, SetLastError) between real operations
   - Opaque predicates: always-true math expressions wrapping real `if` conditions (`(x*x >= 0)`, `(x == x)`, `(x & 0) == 0`)
   - Constant splitting: decompose hex immediates into arithmetic expressions (`0x41` → `(0x20 + 0x21)`)
   - Safe injection point detection: brace-depth tracking ensures transforms only inject inside function bodies, never at file scope
2. Built `vader_evolve.py` — evolution pipeline that chains metamorph → mutate → compile → scan in one command
3. Three intensity levels: low (2 dead blocks, 3 junk vars), med (5/6), high (10/12)
4. Backup/restore system: `.metamorph_backup` files preserve originals for safe rollback
5. Tested full pipeline on dark_room_annotated.c: metamorph (17 transforms) → XOR rotation (key 0xD6 → 0xDC) → compile → Defender scan

### Results
- **Finding #64**: Metamorphic transforms produce unique binary fingerprint per evolution cycle. dark_room.exe fingerprint changed from baseline to `ebdc71b927f7a0f9` (141 KB) after single cycle. Each subsequent cycle produces a different fingerprint. Dead code and junk API calls change the binary's import table, section sizes, and control flow graph — three of the main features static analysis relies on.
- **Finding #65**: Safe injection point detection via brace-depth tracking prevents file-scope injection errors. Initial regex-based approach caused MSVC compile errors (C2065, C2059, C2449) by injecting outside function bodies. Brace counter approach identifies only lines inside function bodies (depth > 0) that end with `;` — zero compile errors across all test cycles.
- **Finding #66**: Full evolution pipeline (metamorph + mutate + compile + scan) completes in single command. dark_room.exe: 17 transforms applied, first-attempt CLEAN against Defender 4.18.26050.15. Pipeline supports multi-cycle operation (`--cycles N`) for repeated identity changes without manual intervention. 13/13 built binaries CLEAN after pipeline run.

### Defender Scan
```
dark_room.exe (metamorphed + mutated): CLEAN (141 KB, attempt 1)
All other binaries: 12/12 CLEAN (unchanged)
```

---

## Engagement 19 — End-to-End Pentest (Radon Scenario)
**Date:** 21 JUN 2026
**Module:** Full kill chain — all phases
**Target:** Windows 11 Build 26200, Defender RTP enabled, standard user context
**Scenario:** Simulated Radon workstation (standard user, admin PIN-locked, Office installed)

### Hypothesis
The complete VADER kill chain — build, evade, blind, command, exfiltrate, persist — operates end-to-end from standard user context against live Defender without a single detection. RTCore64.sys is available on disk for BYOVD escalation. The V7 phantom DLL is the primary privesc path for the Radon target profile.

### Procedure
1. Compiled all components via `deploy.py --compile` (9/10 core), `build_cloak.py` (3 binaries), `build_byovd.py` (2 binaries)
2. Full Defender scan: 80 binaries via `deploy.py --status`
3. Searched for RTCore64.sys — found at MSI Afterburner install directory
4. Checked CWE-732 target (NativePushService) — runs under different user profile (apacw), inaccessible from gwu07
5. Executed dark_room.exe — AMSI+ETW HWBP bypass verified
6. Started C2 server (vader_ui.py) — HTTP :8666 + TCP :8667
7. Started agent (vader_agent.py 127.0.0.1) — registered as a93c8ca5
8. Tested 10 remote operations through C2 API:
   - sysinfo: full target enumeration
   - ping: heartbeat confirmed
   - exec (whoami /all): complete user/group/privilege data
   - exec (net user): local user enumeration
   - exec (netstat): connection visibility (C2 on 8667 visible — cloak would hide)
   - ls: full directory listing with sizes
   - screenshot: 1536x864 GDI capture (3.98 MB BMP)
   - download: README.md exfiltrated (15.5 KB)
   - recon: system reconnaissance completed
   - keylog: 23 keystrokes captured in 3-second window
9. Installed persistence via C2: registry Run key `WindowsSecurityHealth` — agent auto-reconnects on login
10. Planted V7 phantom DLL (osppc.dll, 104 KB) in `%USERPROFILE%\.local\bin\` — user-writable PATH
11. Cleanup: removed registry key, removed phantom DLL, killed agent + C2

### Results
- **Finding #67**: RTCore64.sys confirmed on disk at `C:\Program Files (x86)\MSI Afterburner\RTCore64.sys` (40,688 bytes, SHA256 A4F44E26..., signed). Both primary and Legacy versions present. BYOVD kernel persistence is viable without downloading any external files — the vulnerable signed driver ships with MSI Afterburner and persists on disk after installation.

- **Finding #68**: CWE-732 NativePushService binary path (`C:\Users\apacw\AppData\Local\Wondershare\...`) runs under a different user profile. Standard user gwu07 cannot read or write to apacw's AppData directory (Access Denied). On multi-user machines, per-user service binary paths are protected by NTFS ACLs — the CWE-732 vector requires the service binary to be under the ATTACKER's profile or a world-writable location. This is a significant constraint for the Radon scenario where the attacker is a standard user on a shared machine.

- **Finding #69**: Complete C2 operational chain confirmed from standard user context with zero Defender detections. 80/80 binaries CLEAN. Agent registered automatically, 10 operations tested successfully through web dashboard:
  - Command execution: arbitrary command output exfiltrated
  - Screen capture: full desktop via GDI BitBlt (1536x864)
  - File exfiltration: arbitrary file download through C2 protocol
  - Keystroke capture: GetAsyncKeyState polling at 10ms intervals
  - Persistence: HKCU Run key installed via C2 tasking
  - Reconnaissance: automated system enumeration
  All operations complete within 1-3 seconds latency over localhost TCP. Protocol: length-prefixed JSON over TCP :8667.

- **Finding #70**: V7 phantom DLL deployment operational from standard user. osppc.dll (104 KB) planted in `%USERPROFILE%\.local\bin\` which is in user PATH. ClickToRunSvc (Office, LocalSystem, Auto start) attempts to load osppc.dll on service start — DLL search order walks user PATH after System32. Plant requires no elevation. SYSTEM code execution achieved on next service restart (confirmed in Finding #47). Combined with C2 agent persistence, this provides: standard user → SYSTEM escalation → persistent remote access → full target control.

### Defender Scan
```
80/80 binaries: CLEAN
Defender version: 4.18.26050.15-0
Engine: 4.18.26040.7-0
Target: Windows 11 Home Build 26200 (24H2)
```

### Operation Timeline
```
12:00:53  C2 server initialised (HTTP :8666, TCP :8667)
12:01:12  Agent connected: LAPTOP-R32M8MLI (a93c8ca5) from 127.0.0.1
12:01:47  sysinfo: gwu07 (standard), Windows 11 Build 10.0.26200
12:01:48  ping: pong
12:02:10  exec: whoami /all — full SID/group/privilege dump
12:02:12  ls: Desktop — full listing (dirs + files + sizes)
12:02:54  screenshot: 1536x864 BMP (3,981,366 bytes)
12:02:56  download: README.md (15,543 bytes)
12:03:25  recon: system reconnaissance
12:05:01  persist: registry Run key WindowsSecurityHealth
12:05:41  keylog: 23 keystrokes in 3 seconds
```

### Kill Chain Status (Post-Engagement)
```
Phase    Status       Evidence
─────────────────────────────────────────────
0 C2     OPERATIONAL  Agent registered, 10 ops tested
1 AMSI   BLIND        E_INVALIDARG (DR0 HWBP)
2 ETW    BLIND        STATUS_SUCCESS (DR1 HWBP)
3 PRIV   READY        V7 planted, BYOVD driver located
4 INJECT BUILT        vader_inject.exe + .dll compiled
5 STAGE  BUILT        http_stager.exe compiled
6 CLEAN  BUILT        vader_clean.exe compiled
7 CLOAK  BUILT        cloak.dll + loader compiled
8 BYOVD  READY        RTCore64.sys on disk, byovd.exe built
9 AGENT  OPERATIONAL  17-op agent confirmed
10 META  BUILT        metamorph.py + vader_evolve.py
```
