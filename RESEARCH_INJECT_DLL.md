# INJECT_DLL — Structural Detection Research Plan

## Status: OPEN
**Date**: 2026-06-18 (updated with diff + detection research findings)
**Component**: vader_inject_dll (HOTEL signature set)
**Problem**: Defender detects via DUAL mechanism — static byte pattern + behavioral heuristic
**Evidence**: 10/10 key rotations detected (VADER), 8/10 detected before clean key found (SKYWALKER)

---

## KEY FINDING: Structural Diff (Direction 7 — COMPLETED)

**The two inject_dll files are functionally identical.** Zero logic differences. Same functions, same API calls, same compile flags, same control flow. The ONLY difference is the XOR key.

### Why VADER Fails 10/10 but SKYWALKER Finds Clean Keys

| Attribute | VADER (0x77) | SKYWALKER (0xE3) |
|-----------|-------------|------------------|
| Key high bit | 0 (ASCII range) | 1 (above ASCII) |
| Encoded byte range | 0x00 - 0x59 | 0x80 - 0xD9 |
| Bytes >= 0x80 | 0% | 100% |
| Bytes < 0x20 | 78% | 0% |
| Null bytes | 2 (from 'w' ^ 0x77) | 0 |

Key 0x77 produces a low-range byte cluster that is a statistical fingerprint for "XOR-encoded ASCII." Key 0xE3 pushes all bytes above 0x80, looking like normal binary data.

### Dual Detection Model

```
Layer A — Static byte pattern signature
  Key 0x77 → low-range clustering → ALWAYS MATCHES → DETECTED
  Key 0xE3 → high-range bytes     → MISSES          → passes static

Layer B — Behavioral/heuristic rule (API call sequence)
  Both keys → same code structure → SOMETIMES MATCHES → inconsistent

VADER:     Layer A hits 100% → always DETECTED
SKYWALKER: Layer A misses    → Layer B inconsistent → CLEAN after 8 tries
```

### Immediate Action: mutate.py Key Selection
- Prefer keys with high bit set (0x80-0xFF)
- Avoid keys that produce null bytes when XOR'd with common ASCII
- This defeats Layer A but NOT Layer B — code restructuring still needed

---

## The Detection Surface

Defender fingerprints this API call sequence in the compiled binary:

```
DllMain(DLL_PROCESS_ATTACH)
  ├── LoadLibraryA / GetModuleHandleA    ← DLL resolution
  ├── GetProcAddress                     ← function resolution
  ├── AddVectoredExceptionHandler(1, …)  ← VEH registration (priority=1)
  ├── GetCurrentThread / set_hwbp        ← self-thread DR manipulation
  ├── CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)  ← system-wide thread enum
  └── loop:
        ├── OpenThread(GET_CONTEXT | SET_CONTEXT | SUSPEND_RESUME)
        ├── SuspendThread
        ├── GetThreadContext → SetThreadContext(Dr0/Dr1/Dr7)
        └── ResumeThread
```

Plus the VEH handler pattern:
```
InjectHandler:
  ├── Check ExceptionCode == EXCEPTION_SINGLE_STEP
  ├── Compare Rip to stored function pointers
  ├── Set Rax (return value spoofing)
  ├── Read [Rsp] → set Rip (return address hijack)
  └── Rsp += 8 (stack pointer adjustment)
```

This combination — DLL that registers VEH + enumerates all threads + sets debug registers on each — is the detection signature. XOR key changes only affect encoded strings in .rdata, not this code structure.

---

## Where the Code Lives

| Repo | File | Key Macro |
|------|------|-----------|
| vader-rootkit | `injection/vader_inject_dll_annotated.c` | `XOR_KEY 0x77` |
| skywalker | `sw_thread_dll_annotated.c` | `XOR_KEY 0x93` |

---

## Research Directions

### 1. Decouple DllMain from Initialization
**What**: Move VEH registration + thread blinding OUT of DllMain into an exported init function.
**Why**: DllMain doing heavy work (VEH + thread enum + context manipulation) is a high-confidence heuristic trigger. Defender's emulator likely keys on DllMain as the entry point for behavioral analysis.
**How**: Export an init function (e.g. `VdrInit`). DllMain does nothing but `DisableThreadLibraryCalls`. Injector calls `VdrInit` via a second `CreateRemoteThread(GetProcAddress(hDll, "VdrInit"))` after LoadLibrary returns.
**Risk**: Two-stage injection is more complex. If the injector dies between stages, the DLL is loaded but inert.

### 2. Stagger the API Call Sequence
**What**: Don't do VEH + thread enum + SetThreadContext in one continuous burst.
**Why**: Defender's emulator has a limited execution budget (typically 5-10M instructions). If the suspicious API calls are spread across time or conditional branches, the emulator may not reach all of them in one pass.
**How**: Insert `Sleep()` or computation delays between VEH registration and thread enumeration. Or use a timer callback (`CreateTimerQueueTimer`) to trigger thread blinding after a delay.
**Risk**: Timing-based evasion is fragile. Cloud-based analysis has no time budget.

### 3. Direct Syscalls (NtSetContextThread / NtGetContextThread)
**What**: Replace Win32 API calls with direct NT syscall invocations.
**Why**: Removes `SetThreadContext`/`GetThreadContext`/`SuspendThread`/`ResumeThread` from the Import Address Table (IAT). Defender's static analysis can't see the function references. Emulation-based detection also struggles because the syscall stub bypasses the Win32 layer.
**Research**: SysWhispers2, SysWhispers3, HellsGate, TartarusGate — all on GitHub. These projects generate syscall stubs from the running kernel.
**How**: Replace `SetThreadContext(hThread, &ctx)` with `NtSetContextThread(hThread, &ctx)` via a syscall stub that reads the SSN from ntdll.dll at runtime.
**Risk**: Syscall numbers change between Windows builds. Must resolve at runtime. Also, ETW-TI (Threat Intelligence) can still see syscall-level thread context changes via kernel callbacks.

### 4. APC-Based Alternative
**What**: Instead of Suspend → SetContext → Resume, queue an APC to each thread that sets its own debug registers.
**Why**: Completely different API surface. No `SuspendThread`/`SetThreadContext` at all. Each thread sets its own DR registers when the APC fires, using `GetCurrentThread()` (pseudo-handle, no cross-thread access needed).
**How**: `QueueUserAPC(SetOwnHwbp, hThread, 0)` where `SetOwnHwbp` calls `GetThreadContext(GetCurrentThread(), ...)` and `SetThreadContext(GetCurrentThread(), ...)`.
**Risk**: APCs only fire when a thread enters an alertable wait state. If a thread never calls `SleepEx`/`WaitForSingleObjectEx`/etc., the APC never fires. PowerShell threads DO enter alertable waits, but timing is unpredictable.

### 5. Indirect VEH Registration
**What**: Register the VEH handler from a different context — not directly in the injection DLL's code.
**Why**: The pattern "DLL registers its own VEH handler" is suspicious. If the VEH handler is registered by the injector or by a separate module, the injection DLL's code path looks different.
**How**: Export the handler function. Have the injector register it via `AddVectoredExceptionHandler` in the target process before loading the DLL. Or use a shellcode stub that registers the VEH and then calls `LoadLibrary`.
**Risk**: More complex injection flow. Handler must still be in the target process's address space.

### 6. TLS Callbacks Instead of DllMain
**What**: Use Thread Local Storage (TLS) callbacks for initialization instead of DllMain.
**Why**: TLS callbacks execute before DllMain. Some AV emulators don't follow TLS callback execution. Different code path = different signature.
**How**: Add a TLS directory to the PE with a callback that does the VEH + HWBP setup. DllMain becomes a no-op.
**Risk**: Modern Defender DOES follow TLS callbacks. This is a known technique and may be specifically watched for.

### 7. Compare VADER vs SKYWALKER inject_dll
**What**: Structural diff between `vader_inject_dll_annotated.c` and `sw_thread_dll_annotated.c`.
**Why**: SKYWALKER's version found a clean key (0xE3) after 8 attempts. VADER's version failed 10/10. If the code is structurally identical, the difference is in the compiled output (compiler flags, optimizations, linked libraries). If there are code differences, identify which structural element reduces Defender's confidence.
**How**: `diff vader-rootkit/injection/vader_inject_dll_annotated.c skywalker/sw_thread_dll_annotated.c`
**This should be done first** — it's the cheapest experiment with the highest information yield.

---

## Priority Order

1. **Direction 7** — diff the two files (free, immediate intel)
2. **Direction 1** — decouple DllMain (moderate effort, high impact)
3. **Direction 3** — direct syscalls (high effort, high impact, educational value)
4. **Direction 4** — APC alternative (moderate effort, different attack surface)
5. **Direction 2** — stagger timing (low effort, uncertain impact)
6. **Direction 5** — indirect VEH (moderate effort, moderate impact)
7. **Direction 6** — TLS callbacks (low effort, likely detected anyway)

---

## Success Criteria

- `vader_inject.dll` compiles and passes `MpCmdRun.exe -Scan -ScanType 3 -File` with CLEAN result
- Mutation pipeline (`mutate.py`) achieves consistent CLEAN for inject_dll component
- Functional test: DLL injection into PowerShell still blinds AMSI + ETW after restructuring
- No regression in other components

---

## Research Findings (2026-06-18)

### Detection Chain — How Defender Catches inject_dll

Based on research into Defender's detection mechanisms, the detection chain is:

**Layer 1 — Static Analysis (IAT inspection)**
- Import table flags: `CreateToolhelp32Snapshot` + `SetThreadContext` + `OpenThread` + `AddVectoredExceptionHandler`
- Combination of thread manipulation APIs in a DLL with minimal exports = elevated heuristic score
- Defender maps imported APIs to threat categories and scores combinations

**Layer 2 — Emulation (mpengine.dll sandbox)**
- Emulator enters at `DllMain(DLL_PROCESS_ATTACH)` and follows code flow
- Heavy DllMain (VEH registration + thread enum + context manipulation) is a primary trigger
- Emulator has a finite instruction budget — it terminates after N instructions/API calls
- Known emulator artifacts: `GetComputerName` returns "HAL9TH", `GetUserName` returns "JohnDoe"
- All suspicious API calls happening in one DllMain burst = high confidence within budget

**Layer 3 — Runtime Behavioral (ETW-TI kernel telemetry)**
- `NtSetThreadContext` fires ETW-TI Task 5 (local) or Task 10 (remote)
- Kernel inspects DR0-DR3 values — if they resolve to addresses in amsi.dll or ntdll.dll, near-certain indicator
- This is the HIGHEST FIDELITY detection signal — kernel-level, cannot be hooked from usermode
- Source: Praetorian, CrowdStrike, FluxSec research

### Critical Finding — NtContinue ETW-TI Bypass

**Praetorian documented that `NtContinue` updates thread context (including debug registers) WITHOUT traversing the kernel code path that emits `EtwTiLogSetContextThread`.** This means:
- `NtSetContextThread` → fires ETW-TI → Defender sees DR manipulation → DETECTED
- `NtContinue` → NO ETW-TI event → Defender kernel telemetry is BLIND to the DR change

Source: [Praetorian: ETW-TI and Hardware Breakpoints](https://www.praetorian.com/blog/etw-threat-intelligence-and-hardware-breakpoints/)

This is the most significant gap in the detection chain for HWBP-based bypasses.

### Why dark_room Passes but inject_dll Fails

- dark_room.exe sets HWBP on its OWN thread only (`GetCurrentThread()` pseudo-handle)
- inject_dll sets HWBP on OTHER threads (remote `SetThreadContext` via `OpenThread`)
- Remote SetThreadContext fires ETW-TI Task 10 — local `GetCurrentThread` + `SetThreadContext` may only fire Task 5 or be ignored
- The thread enumeration pattern (`CreateToolhelp32Snapshot` → `OpenThread` → `SuspendThread` → `SetThreadContext`) is a textbook injection chain that Defender specifically recognizes

### APC as Alternative Attack Surface

- APC injection has "very low" EDR detection coverage per Outflank research
- EarlyBird APC (queue before thread initialization) bypasses many EDR hooks that load after `NtTestAlert`
- Avoids `SuspendThread`/`SetThreadContext` entirely — different API surface, different signature
- Risk: APCs only fire in alertable wait state — PowerShell threads DO use alertable waits, but timing is unpredictable

### Sources

- [Praetorian: ETW-TI and Hardware Breakpoints](https://www.praetorian.com/blog/etw-threat-intelligence-and-hardware-breakpoints/)
- [CrowdStrike: Patchless AMSI Bypass](https://www.crowdstrike.com/en-us/blog/crowdstrike-investigates-threat-of-patchless-amsi-bypass-attacks/)
- [FluxSec: Detecting VEH Abuse via Debug Registers](https://fluxsec.red/detecting-vectored-exception-handling-malware-rust-edr-windows-kernel)
- [BlackHat 2018: Reverse Engineering Defender Emulator](https://i.blackhat.com/us-18/Thu-August-9/us-18-Bulazel-Windows-Offender-Reverse-Engineering-Windows-Defenders-Antivirus-Emulator.pdf)
- [0xAlexei/WindowsDefenderTools](https://github.com/0xAlexei/WindowsDefenderTools)
- [Outflank: Early Cascade Injection](https://www.outflank.nl/blog/2024/10/15/introducing-early-cascade-injection-from-windows-process-creation-to-stealthy-injection/)
- [Hackmosphere: Bypass Defender 2025](https://www.hackmosphere.fr/en/bypass-windows-defender-antivirus-in-2025-evasion-techniques-using-direct-syscalls-and-xor-encryption-part-2/)
- [InfoGuard Labs: Fuzzing mpengine.dll](https://labs.infoguard.ch/posts/attacking_edr_part4_fuzzing_defender_scanning_and_emulation_engine/)

---

## Updated Priority Order (Post-Research)

1. **Direction 7** — diff VADER vs SKYWALKER inject_dll (free, immediate intel)
2. **NEW: Direction 8 — NtContinue for HWBP placement** (HIGH PRIORITY — documented ETW-TI blind spot)
3. **Direction 1** — decouple DllMain (moderate effort, high impact on emulation layer)
4. **Direction 4** — APC alternative (moderate effort, completely different detection surface)
5. **Direction 3** — direct syscalls (bypasses IAT + user-mode hooks, but NOT ETW-TI kernel)
6. **Direction 2** — stagger timing (may exceed emulator budget, low effort)
7. **Direction 5** — indirect VEH (moderate effort)
8. **Direction 6** — TLS callbacks (likely detected by modern Defender)

---

## Notes

- The VEH + HWBP technique itself is sound — dark_room.exe (self-only) passes clean
- The detection is specifically on the CROSS-THREAD variant (thread enum + remote SetThreadContext)
- ETW-TI kernel telemetry IS the primary detection signal — confirmed by multiple sources
- NtContinue is the documented gap in this telemetry
- Any fix must preserve the watchdog (VdrWatch) functionality for catching new threads
