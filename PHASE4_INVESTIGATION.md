# PHASE 4 INVESTIGATION REPORT — PROCESS INJECTION

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Operator: VADER (george wu / 22DIV)
## Authorisation: Own hardware only. CSEC academic research.
## Date: 2026-06-17

---

## Executive Summary

Phase 4 extends the VADER dark room (AMSI+ETW hardware breakpoint bypass) from a single-process capability to a process-wide injection system. Two components were built, compiled, tested, and verified against a live Windows Defender installation with zero detections across the entire kill chain.

**Components:**
| Component | File | Size | XOR Key | Callsign |
|-----------|------|------|---------|----------|
| Injection DLL | `injection/vader_inject_dll_annotated.c` | 105,472 bytes | 0x77 | HOTEL |
| Injector EXE | `injection/vader_inject_annotated.c` | 148,992 bytes | 0x77 | HOTEL |

**Result:** Full kill chain — standard user to AMSI-blind injected process — confirmed operational. Defender did not detect, quarantine, or alert on any component at any stage.

---

## 1. Architecture

### Problem Statement

The dark room (`dark_room_annotated.c`) sets hardware breakpoints on AmsiScanBuffer and EtwEventWrite using CPU debug registers (DR0, DR1) plus a Vectored Exception Handler. This blinds AMSI and ETW in the dark room's own process. But hardware breakpoints are per-thread. Child processes spawned via CreateProcess do NOT inherit debug register state. A PowerShell launched from the dark room has a clean DR0-DR3 — AMSI sees everything.

Phase 4 solves this: inject the bypass into any running process or spawn a new process pre-blinded.

### Design Decisions

**DLL injection over shellcode injection.** The VEH handler, DR register setup, and thread enumeration logic are standard C code. Compiling as a DLL and injecting via LoadLibrary is cleaner than writing position-independent shellcode. The DLL's DllMain runs under the target's process context, registers the VEH, sets breakpoints on all threads, and returns. One function call does the entire job.

**Two-mode injector.** The EXE operates in two modes:
- `vader_inject.exe <PID>` — Inject into a running process (e.g., an already-open PowerShell)
- `vader_inject.exe --spawn` — CreateProcessA with CREATE_SUSPENDED, inject before first instruction, resume

The `--spawn` mode is the more interesting case: the target process is born blind. AMSI never gets a chance to scan anything because the bypass is active before the first PowerShell statement executes.

**Loader lock safety.** DllMain runs under the Windows loader lock (LdrpLoaderLock). This restricts what APIs are safe to call. The design was validated against known safe/unsafe patterns:

| Operation | Safe Under Loader Lock | Used In DllMain |
|-----------|----------------------|-----------------|
| GetModuleHandle | YES (no DLL loading) | YES |
| GetProcAddress | YES (reads PE headers) | YES |
| LoadLibraryA("amsi.dll") | YES (CRITICAL_SECTION allows same-thread re-entry) | YES (tryLoad=1) |
| CreateToolhelp32Snapshot | YES (kernel call) | YES |
| OpenThread / SuspendThread | YES (kernel calls) | YES |
| SetThreadContext | YES (kernel call) | YES |
| ResumeThread | YES (kernel call) | YES |
| AddVectoredExceptionHandler | YES (ntdll internal) | YES |
| CreateThread | **NO** (deadlock risk) | NO |

**VdrWatch export.** The DLL exports a `VdrWatch` function that runs as a persistent monitoring thread. After the initial DllMain setup blinds all existing threads, VdrWatch loops every 2 seconds to:
1. Retry AMSI resolution if amsi.dll wasn't loaded at injection time
2. Re-blind all threads if AMSI becomes newly available
3. Write periodic canary heartbeats

This handles the case where amsi.dll loads AFTER injection (e.g., when PowerShell's CLR initialises and pulls in AMSI). Without VdrWatch, a delayed AMSI load would create a window where scripts are scanned.

**Thread enumeration for process-wide coverage.** DllMain blinds only the current thread (the one running LoadLibrary). VdrWatch and the thread enumeration function (`blind_all_threads`) iterate ALL threads in the target process via CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD), suspending each, setting DR0/DR1/DR7 via SetThreadContext, and resuming. VdrWatch skips its own TID to avoid self-suspension.

### XOR Encoding

All strings use XOR key 0x77 (callsign HOTEL), maintaining signature isolation from other VADER components:

| Component | Key | Callsign |
|-----------|-----|----------|
| Dark Room | 0x41 | (base) |
| V4 DELTA | 0x52 | DELTA |
| V5 ECHO | 0x37 | ECHO |
| V6 FOXTROT | 0x63 | FOXTROT |
| V7 GOLF | 0x19 | GOLF |
| **Phase 4 Inject** | **0x77** | **HOTEL** |

Encoded strings in the DLL:
- `amsi.dll` (8 bytes)
- `AmsiScanBuffer` (14 bytes)
- `ntdll.dll` (9 bytes)
- `EtwEventWrite` (13 bytes)
- Canary path (33 bytes)

Encoded strings in the EXE:
- `powershell.exe` (14 bytes)
- DLL filename (16 bytes)
- `VdrWatch` (8 bytes)

### 64-bit Module Address Resolution

A design problem was identified and solved during development: `GetExitCodeThread` returns a DWORD (32 bits), but on x64, HMODULE addresses can exceed 4GB. Using the LoadLibrary remote thread's exit code to get the DLL base address truncates high addresses.

**Solution:** After the LoadLibrary thread completes, `get_remote_module` uses `CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)` to enumerate all modules in the target process, matches by name via `_stricmp`, and retrieves the full 64-bit `modBaseAddr`. This is then used to calculate VdrWatch's remote address via RVA offset.

### VdrWatch Remote Address Calculation

The injector needs the address of VdrWatch inside the target process to spawn it via CreateRemoteThread. Since ASLR applies to the DLL, the injector:
1. Loads the DLL locally with `LoadLibraryExA(path, NULL, DONT_RESOLVE_DLL_REFERENCES)` — no DllMain execution
2. Gets `VdrWatch` address locally via `GetProcAddress`
3. Calculates offset: `local_VdrWatch - local_base`
4. Applies offset to remote base: `remote_base + offset`

This works because the DLL's internal layout (RVA) is identical regardless of where ASLR maps the base.

---

## 2. Build Process

### Compilation

Both components compile with MSVC (`cl.exe`) from a Developer Command Prompt:

```cmd
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

:: DLL
cl.exe injection\vader_inject_dll_annotated.c /Fe:injection\vader_inject.dll /LD /O1 /GS- /utf-8

:: EXE
cl.exe injection\vader_inject_annotated.c /Fe:injection\vader_inject.exe /O1 /GS- /utf-8
```

**Flags:**
- `/O1` — Optimise for size (smaller binary = less signature surface)
- `/GS-` — Disable stack cookies (not needed, reduces detection surface)
- `/LD` — Build as DLL (for the injection payload)
- `/utf-8` — Source encoding

**Result:** Zero errors, zero warnings. All dependencies resolve from default `kernel32.lib`.

### Defender Scan

Both binaries were scanned immediately after compilation using `deploy.py --status`:

```
vader_inject.dll    CLEAN
vader_inject.exe    CLEAN
```

No static detection. No cloud/ML retroactive detection after extended on-disk time.

---

## 3. Test Evidence

Six discrete tests were executed. All passed.

### Test 1: PID Injection — DLL Load

**Objective:** Inject into a running PowerShell process.
**Method:** `vader_inject.exe <PID>` targeting an open PowerShell window.

**Evidence:**
```
[*] VADER Phase 4 — Process Injection
[*] Target PID: 31244
[*] DLL path: C:\Users\gwu07\Desktop\vader-rootkit\injection\vader_inject.dll
[+] Remote memory allocated
[+] DLL path written to target
[+] LoadLibrary thread created — waiting...
[+] DLL loaded at remote base: 0x00007FF858390000
```

DLL successfully loaded into the target process. `vader_inject.dll` is now resident in the target's address space with VEH handler registered and breakpoints active on the LoadLibrary thread.

### Test 2: PID Injection — VdrWatch Thread

**Objective:** Verify VdrWatch export is callable in the remote process.
**Method:** Injector calculates VdrWatch RVA and spawns a second remote thread.

**Evidence:**
```
[+] VdrWatch resolved locally at offset 0x1154
[+] VdrWatch remote address: 0x00007FF858391154
[+] VdrWatch thread started in target (TID: 45012)
[*] Injection complete — target is blind
```

VdrWatch is now running as a persistent thread in the target, re-blinding any new threads every 2 seconds.

### Test 3: PID Injection — Canary Verification

**Objective:** Confirm the DLL is executing code inside the target process.
**Method:** Check canary file written by DllMain and VdrWatch.

**Evidence (canary content):**
```
[HOTEL] DllMain AMSI blind | pid=31244
[HOTEL] DllMain ETW  blind | pid=31244
[HOTEL] VdrWatch alive | pid=31244 | tick=1
```

Both AMSI and ETW bypasses confirmed active. VdrWatch heartbeat confirms persistent monitoring.

### Test 4: CREATE_SUSPENDED Spawn

**Objective:** Spawn a new PowerShell process pre-blinded.
**Method:** `vader_inject.exe --spawn`

**Evidence:**
```
[*] VADER Phase 4 — Process Injection (SPAWN mode)
[+] Process created SUSPENDED: PID 43808
[+] DLL injected into suspended process
[+] VdrWatch started
[+] Main thread resumed — process is now running BLIND
```

The target PowerShell process was born with CREATE_SUSPENDED flag. Its main thread was frozen before executing any user-mode code. The DLL was injected, breakpoints set, VEH registered — all before the process ran a single instruction. On resume, the process operates normally but AMSI and ETW are already bypassed.

**ASLR shared mapping confirmed:** The DLL loaded at `0x00007FF858390000` in both the PID injection test (Test 1, PID 31244) and the CREATE_SUSPENDED test (Test 4, PID 43808). Same file maps to the same ASLR base on the same boot.

### Test 5: AMSI Blind Verification

**Objective:** Prove AMSI cannot scan scripts in the injected process.
**Method:** Execute the official AMSI test string inside the injected PowerShell.

The AMSI test string (`AMSI Test Sample: 7e72c3ce-861b-4339-8671-d21b2a0abb23`) is a Microsoft-documented trigger that AMSI is contractually required to flag. If this string passes through `Invoke-Expression` without detection, AMSI is provably non-functional.

**Procedure:**
1. Base64-encode the test string (to avoid Defender scanning the test script itself)
2. In the injected PowerShell: decode → `Invoke-Expression`
3. If AMSI is active: Defender kills the process or blocks execution
4. If AMSI is blind: the string evaluates as a harmless string literal, no detection

**Result: AMSI_BLIND**

The test string passed through `Invoke-Expression` without triggering any Defender response. No process termination. No alert. No quarantine. AmsiScanBuffer was intercepted by the VEH handler before it could evaluate the content, returned `E_INVALIDARG (0x80070057)`, and the AMSI infrastructure accepted the "scan failed" result without escalating.

### Test 6: Full Kill Chain

**Objective:** Execute the complete attack chain from standard user to AMSI-blind injected shell.
**Method:** Sequential execution of all phases.

```
Phase 0: C2 listener started (port 4444)                    ✓
Phase 1+2: Dark room activated (AMSI + ETW blind)           ✓
Phase 4: vader_inject.exe --spawn (PowerShell born blind)   ✓
         Canary: DllMain AMSI+ETW blind confirmed           ✓
         VdrWatch: heartbeat active                         ✓
Phase 3: Privesc vector deployable from blind shell         ✓
```

**Defender response across all phases: ZERO detections.**

No binary quarantined. No behavioral alert. No cloud/ML retroactive flagging. All components remain on disk and operational.

---

## 4. Defender Evasion Analysis

### Why Phase 4 Is Invisible

**Layer 1 — Static analysis defeated by XOR encoding.**
All strings that would match Defender signatures (function names, DLL names, paths) are XOR-encoded with key 0x77. They exist in the binary as meaningless byte arrays. Decoded at runtime, used, then discarded. Defender's static engine pattern-matches against known malware strings — these don't exist in the file.

**Layer 2 — No VirtualProtect on protected regions.**
Defender's `Behavior:Win32/AMSI_Patch_T.B12` rule monitors for VirtualProtect calls targeting amsi.dll's code section, followed by writes to AmsiScanBuffer. The HWBP approach never calls VirtualProtect. Debug registers are set via SetThreadContext — a standard API for debuggers, profilers, and runtime instrumentation. amsi.dll's memory pages are never touched.

**Layer 3 — Debug registers are architecturally invisible to memory integrity checks.**
Defender monitors memory modifications. CPU debug registers exist in a completely separate domain: the thread context structure, maintained by the kernel, not visible in the process's virtual address space. There is no `Behavior:Win32/HWBP_Tamper_T` equivalent. SetThreadContext on your own process's threads is unrestricted for standard users.

**Layer 4 — Classic injection technique, not novel.**
DLL injection via VirtualAllocEx → WriteProcessMemory → CreateRemoteThread(LoadLibraryA) is the most documented injection method. It's monitored by WdFilter.sys and visible in ETW. But the injection itself is not malicious — it's what the DLL DOES that matters. And what the DLL does (set debug registers, register exception handler) are all legitimate OS operations that don't trigger behavioral rules.

### The Open Question: EtwTiLogSetContextThread

The kernel ETW-Ti (Threat Intelligence) provider includes `EtwTiLogSetContextThread`, which should fire when SetThreadContext modifies debug registers. Two possibilities:

1. **It fires, Defender ignores it.** The consumer (WdFilter.sys) doesn't have a rule correlating SetThreadContext + DR0 targeting amsi.dll regions. This is a consumer gap — the telemetry exists but isn't acted on.

2. **It doesn't fire for same-process SetThreadContext.** The provider may only instrument cross-process context manipulation. This is a provider gap — the telemetry doesn't exist for the self-modification case.

Either way, the bypass works. The distinction matters for MSRC submission quality: a consumer gap is more likely to be patched (just add a rule) than a provider gap (requires kernel changes).

---

## 5. Capability Comparison

### Dark Room (Single Process) vs Phase 4 Inject (Process-Wide)

| Capability | Dark Room | Phase 4 Inject |
|-----------|-----------|----------------|
| AMSI bypass | Own process only | Any target process |
| ETW bypass | Own process only | Any target process |
| Thread coverage | Current thread only | All threads (enumerated) |
| New thread handling | None | VdrWatch re-blinds every 2s |
| Deployment | Self-contained EXE | DLL + EXE pair |
| CREATE_SUSPENDED | No | Yes (process born blind) |
| Persistent monitoring | No | VdrWatch heartbeat loop |
| Canary evidence | Single write | Tagged `[HOTEL]` with PID + tick |
| Memory modification | Zero bytes | Zero bytes (in target's code) |
| Defender detection | NONE | NONE |

### Key Advancement

Dark Room proves the bypass works. Phase 4 proves it's deployable. The gap between "I can blind my own process" and "I can blind any process on the system" is the difference between a proof of concept and a weapon. Phase 4 crosses that line.

---

## 6. MITRE ATT&CK Mapping

| Technique | ID | Phase 4 Implementation |
|-----------|-----|----------------------|
| Process Injection: DLL Injection | T1055.001 | VirtualAllocEx + WriteProcessMemory + CreateRemoteThread(LoadLibraryA) |
| Impair Defenses: Disable or Modify Tools | T1562.001 | HWBP on AmsiScanBuffer returns E_INVALIDARG |
| Impair Defenses: Indicator Blocking | T1562.006 | HWBP on EtwEventWrite returns STATUS_SUCCESS |
| Create or Modify System Process | T1543 | CREATE_SUSPENDED + pre-execution injection |
| Execution Guardrails | T1480 | XOR-encoded strings, runtime-only decode |

---

## 7. Responsible Disclosure

This research was conducted on personally owned hardware under CSEC academic authorisation. No third-party systems were targeted.

**MSRC relevance of the HWBP blind spot (Finding #36):** Defender's tamper protection monitors memory-level modifications but not CPU debug register manipulation. This architectural gap allows both AMSI and ETW to be bypassed simultaneously with zero memory modification. The pattern is systemic — it applies to any function that can be intercepted via hardware breakpoints, not just AmsiScanBuffer and EtwEventWrite.

Phase 4's injection capability extends this from a per-process novelty to a deployable technique. If MSRC determines the debug register blind spot warrants remediation, the mitigation path would likely involve:
1. WdFilter.sys consuming EtwTiLogSetContextThread events
2. Correlating SetThreadContext(DR0-DR3) with addresses in protected DLLs (amsi.dll, ntdll.dll)
3. Triggering behavioral detection when debug registers point to known security functions

Until then, the technique remains viable against current Defender signatures and behavioral rules.

---

## 8. Conclusions

Phase 4 is operational. The VADER toolkit now has a complete injection pipeline:

1. **Locate** — Resolve AMSI and ETW function addresses (shared ASLR mapping)
2. **Inject** — Classic DLL injection into any target process
3. **Blind** — HWBP + VEH intercepts AmsiScanBuffer and EtwEventWrite
4. **Persist** — VdrWatch monitors for new threads and delayed AMSI loads
5. **Verify** — Canary files with `[HOTEL]` tags confirm execution

The full kill chain from standard user to AMSI-blind injected process runs end-to-end with zero Defender detections. All six tests passed. Both binaries remain clean on disk after extended exposure.

What was a single-process proof of concept (dark room) is now a deployable injection system. The "NOT BUILT" placeholder in the execution manual can be replaced with tested, documented procedures.

---

*VADER ROOTKIT — 22DIV / george wu*
*CSEC Tactical Cyber Operations*
