# Evidence Log — Finding #36: Defender Tamper Protection Bypass via HWBP

## Test Environment

| Field | Value |
|-------|-------|
| **Machine** | LAPTOP-R32M8MLI |
| **OS** | Windows 11 Home Build 26200 |
| **Defender Version** | 4.18.26050.15 |
| **Signatures Updated** | 2026-06-15 03:23:53 |
| **Real-Time Protection** | ENABLED |
| **Tamper Protection** | ENABLED |
| **Antivirus Enabled** | TRUE |
| **Test Date** | 2026-06-15 |
| **User Context** | Standard user (gwu07, no admin) |
| **Compiler** | MSVC 19.51.36247 (VS 18 Community) |

---

## Pre-Test Baseline

Recent Defender detections at time of test (proves Defender IS actively catching threats):

```
[2026-06-15 13:59:54] ThreatID=251873    | VERSION.dll (DLL sideload proxy — DETECTED)
[2026-06-15 04:06:14] ThreatID=2147971505 | unattend.xml (DETECTED)
[2026-06-15 03:10:15] ThreatID=251873    | VERSION.dll (DLL sideload proxy — DETECTED)
[2026-06-15 02:04:37] ThreatID=2147731849 | etw_patch.exe (memory patch ETW bypass — DETECTED)
```

**Key baseline observation:** Defender successfully detects both DLL sideload proxies AND memory-patch ETW bypasses. The AV engine is functioning and current.

---

## Control Test: Memory-Patch Bypass IS Detected

From earlier in this session (pre-baseline), the memory-patch AMSI bypass (`amsi_patch.exe`) and the memory-patch ETW bypass (`etw_patch.exe`) were both detected by Defender:

- `Behavior:Win32/AMSI_Patch_T.B12` — fires on VirtualProtect + byte write to amsi.dll
- `etw_patch.exe` — ThreatID 2147731849, quarantined

**This establishes that Defender's tamper protection DOES work against memory-level AMSI/ETW bypasses.**

---

## Test 1: AMSI HWBP Bypass

**Binary:** `amsi_hwbp.exe`
**SHA256:** `FB45F814385506BCACCDFC9A26EB4CF13A10F1E8A33535D41AD7828C1741F0D1`
**Size:** 145,408 bytes
**Timestamp:** 2026-06-15 15:11:38.500

### Console Output (verbatim)

```
  --- PHASE 1: LOCATE AMSI ---

  [+] amsi.dll loaded at 0x00007FFD6E8F0000
  [+] AmsiScanBuffer at 0x00007FFD6E8F8160

  --- PHASE 2: SET HARDWARE BREAKPOINT ---

  [+] VEH handler registered (first in chain)
  [*] Current DR0: 0x0  DR7: 0x0
  [+] Hardware breakpoint set: DR0 = 0x00007FFD6E8F8160
  [+] DR7 = 0x401 (DR0 enabled, execution, 1-byte)
  [+] NO memory modified in amsi.dll
  [+] NO VirtualProtect called

  --- PHASE 3: VERIFY BYPASS ---

  [*] Calling AmsiScanBuffer directly to test bypass...
  [+] AmsiScanBuffer returned 0x80070057 (E_INVALIDARG)
  [+] BYPASS CONFIRMED — AMSI is blind
  [+] result parameter = 0 (never written — function never ran)
```

**Exit code:** 0
**Completed:** 2026-06-15 15:11:38.606

### Defender Response

- **Detection:** NONE
- **Binary status:** Still on disk (not quarantined)
- **Tamper Protection alert:** NONE
- **Behavioral rule trigger:** NONE

### Evidence Summary

| Check | Result |
|-------|--------|
| AmsiScanBuffer located | 0x00007FFD6E8F8160 |
| DR0 set to target | Verified (0x00007FFD6E8F8160) |
| DR7 configured | 0x401 (execution breakpoint) |
| Memory modified in amsi.dll | ZERO bytes |
| VirtualProtect called | NO |
| AmsiScanBuffer return value | 0x80070057 (E_INVALIDARG) — intercepted |
| Defender detection | **NONE** |
| Binary quarantined | **NO** |

---

## Test 2: ETW HWBP Bypass

**Binary:** `etw_hwbp.exe`
**SHA256:** `FB486AB463336286DF5891EA9EE9EDFAFC8F98602D277CF61C5FE8A88E8A74F7`
**Size:** 145,408 bytes
**Timestamp:** 2026-06-15 15:12:52.812

### Console Output (verbatim)

```
  --- PHASE 1: LOCATE ETW ---

  [+] ntdll.dll at 0x00007FFD91760000
  [+] EtwEventWrite at 0x00007FFD917E0430

  --- PHASE 2: SET HARDWARE BREAKPOINT ---

  [+] VEH handler registered (first in chain)
  [*] Current DR0: 0x0  DR7: 0x0
  [+] Hardware breakpoint set: DR0 = 0x00007FFD917E0430
  [+] DR7 = 0x401 (DR0 enabled, execution, 1-byte)
  [+] NO memory modified in ntdll.dll
  [+] NO VirtualProtect called
  [+] NO EtwTi alert generated

  --- PHASE 3: VERIFY BYPASS ---

  [*] Calling EtwEventWrite with invalid handle (0xDEADBEEF)...
  [+] EtwEventWrite returned 0 (STATUS_SUCCESS)
  [+] BYPASS CONFIRMED — ETW is blind
  [+] Invalid handle accepted = function never executed
```

**Exit code:** 0
**Completed:** 2026-06-15 15:12:52.959

### Dead Man Test Explained

EtwEventWrite was called with `RegHandle = 0xDEADBEEF` (invalid). If the function executed normally, it would return an error (invalid handle). Instead it returned `STATUS_SUCCESS (0)` — proving the VEH handler intercepted BEFORE the function body executed and returned a spoofed success code. The function never ran.

### Defender Response

- **Detection:** NONE
- **Binary status:** Still on disk (not quarantined)
- **Tamper Protection alert:** NONE

---

## Test 3: Dark Room (Combined AMSI + ETW)

**Binary:** `dark_room.exe`
**SHA256:** `3D2B4D0C1435C9FFDF6E0A14607648A2F4A0FA9B3747DD592C90AF1D2A5031AB`
**Size:** 145,408 bytes
**Timestamp:** 2026-06-15 15:11:50.300

### Console Output (verbatim)

```
  --- PHASE 1: LOCATE TARGETS ---

  [+] AmsiScanBuffer at 0x00007FFD6E8F8160
  [+] EtwEventWrite  at 0x00007FFD917E0430

  --- PHASE 2: ACTIVATE DARK ROOM ---

  [+] Unified VEH handler registered
  [+] DR0 = 0x00007FFD6E8F8160 (AmsiScanBuffer)
  [+] DR1 = 0x00007FFD917E0430 (EtwEventWrite)
  [+] DR7 = 0x405

  [+] DARK ROOM ACTIVE
  [+] Script scanning: BLIND (AMSI)
  [+] Process telemetry: BLIND (ETW)
  [+] Memory integrity: CLEAN (zero modifications)

  --- PHASE 3: VERIFY ---

  [+] AMSI: returned 0x80070057 (E_INVALIDARG) — BLIND
  [+] ETW:  returned 0 (STATUS_SUCCESS) — BLIND

  [+] DARK ROOM VERIFIED — ALL SYSTEMS BLIND
```

**Exit code:** 0
**Completed:** 2026-06-15 15:11:50.397

### Defender Response

- **Detection:** `Trojan:Script/Wacatac.C!ml` (ThreatID 2147749377) at 15:11:51
- **Detection type:** Cloud ML heuristic (`!ml` suffix) — NOT tamper protection
- **Binary status:** QUARANTINED after execution completed
- **DidThreatExecute:** Defender reports `False` — **incorrect**, the binary completed all phases (exit 0)

### Critical Analysis of the dark_room.exe Detection

The `Wacatac.C!ml` detection is a **generic cloud machine-learning heuristic** based on binary characteristics (file reputation, static features). It is NOT:

- A tamper protection detection (no `AMSI_Patch_T` or equivalent)
- A behavioral detection of hardware breakpoint manipulation
- A detection of VEH registration targeting security functions
- A detection of debug register modification via SetThreadContext

**Evidence that this is NOT an HWBP-specific detection:**

1. `amsi_hwbp.exe` uses the EXACT same HWBP technique and is NOT detected
2. `etw_hwbp.exe` uses the EXACT same HWBP technique and is NOT detected
3. The `!ml` suffix indicates cloud ML, not a behavioral rule
4. The detection fired AFTER execution completed (post-hoc, not preventive)
5. Defender incorrectly reports `DidThreatExecute: False` despite confirmed execution

**Conclusion:** The cloud ML flagged `dark_room.exe` based on binary reputation or static features (likely: the combination of `LoadLibrary("amsi.dll") + GetProcAddress("AmsiScanBuffer")` string patterns). This is trivially bypassed by further XOR-encoding or binary modification. The underlying HWBP technique itself remains completely undetected.

---

## Summary: Defender Detection Matrix

| Bypass Technique | Target | Memory Modified | Defender Detects | Detection Type |
|-----------------|--------|-----------------|-----------------|----------------|
| Memory patch (control) | amsi.dll | YES | **YES** | Behavioral: AMSI_Patch_T.B12 |
| Memory patch (control) | ntdll.dll | YES | **YES** | ThreatID 2147731849 |
| **HWBP (this finding)** | amsi.dll | **NO** | **NO** | — |
| **HWBP (this finding)** | ntdll.dll | **NO** | **NO** | — |
| **HWBP combined** | both | **NO** | **ML only*** | Wacatac.C!ml (binary reputation, not technique detection) |

\* Cloud ML flagged the binary's static characteristics, not the HWBP technique. The same technique compiled into a different binary (amsi_hwbp.exe, etw_hwbp.exe) is completely undetected.

---

## Reproduction Steps for MSRC Triage

1. Enable Defender RTP + Tamper Protection (default on Windows 11)
2. Compile `amsi_hwbp.exe` from provided source
3. Run `amsi_hwbp.exe --test` as standard user
4. Observe: bypass succeeds, Defender silent
5. Run `Get-MpThreatDetection` — no new entries for amsi_hwbp
6. Compare: compile and run a memory-patch AMSI bypass
7. Observe: Defender immediately flags `Behavior:Win32/AMSI_Patch_T`
8. **Conclusion:** Tamper Protection catches memory patches but is blind to HWBP

---

## File Hashes (all PoC binaries)

```
amsi_hwbp.exe  SHA256: FB45F814385506BCACCDFC9A26EB4CF13A10F1E8A33535D41AD7828C1741F0D1
etw_hwbp.exe   SHA256: FB486AB463336286DF5891EA9EE9EDFAFC8F98602D277CF61C5FE8A88E8A74F7
dark_room.exe  SHA256: 3D2B4D0C1435C9FFDF6E0A14607648A2F4A0FA9B3747DD592C90AF1D2A5031AB
```
