# PHASE 4 — PROCESS HOLLOWING / INJECTION

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Status: PENDING — After DLL sideloading (Phase 3)

---

## Objective

Execute payload code inside a legitimate process. The process appears
normal to Task Manager / Defender but runs our code internally.
Evasion technique — not directly CVE-generating unless we find a way
to inject into a higher-privilege process from standard user.

## Techniques

### Process Hollowing (RunPE)

1. CreateProcess("svchost.exe", ..., CREATE_SUSPENDED) — legitimate process, suspended
2. NtUnmapViewOfSection — hollow out the legitimate code
3. VirtualAllocEx — allocate memory in the target process
4. WriteProcessMemory — write our payload into allocated space
5. SetThreadContext — redirect EIP/RIP to our code
6. ResumeThread — process runs our code under svchost.exe's identity

**Privilege boundary:** Standard user can only hollow processes at same
or lower privilege level. Cannot hollow SYSTEM processes without an EoP.

### DLL Injection (LoadLibrary)

1. OpenProcess(target) — need PROCESS_ALL_ACCESS
2. VirtualAllocEx — allocate string buffer in target
3. WriteProcessMemory — write DLL path string
4. CreateRemoteThread(LoadLibraryA, dllPath) — target loads our DLL

### APC Injection

1. Queue APC to target thread via QueueUserAPC or NtQueueApcThread
2. When target thread enters alertable wait, APC executes
3. Our code runs in target's context

### Thread Hijacking

1. SuspendThread on target
2. GetThreadContext — save registers
3. Allocate + write shellcode in target process
4. SetThreadContext — redirect RIP to shellcode
5. ResumeThread

## Detection Concerns (from ETW research)

Kernel-mode EtwTi logs ALL of these:
- `EtwTiLogReadWriteVm` → WriteProcessMemory
- `EtwTiLogSetContextThread` → SetThreadContext
- `EtwTiLogInsertQueueUserApc` → QueueUserAPC
- `EtwTiLogSuspendResumeThread` → SuspendThread/ResumeThread
- `EtwTiLogAllocExecVm` → VirtualAllocEx with EXECUTE

User-mode ETW patch (Phase 2) does NOT blind these. They fire at kernel level.
Full evasion requires either:
- Syscall-level unhooking (direct syscalls bypassing ntdll hooks)
- Or acceptance that kernel telemetry will fire

## Implementation Plan

### Phase 4a — Process Hollowing PoC
1. Hollow a user-mode process (notepad.exe → our payload)
2. Annotated version with full API documentation
3. Test Defender detection rate

### Phase 4b — Direct Syscalls
1. Implement NtAllocateVirtualMemory / NtWriteVirtualMemory via direct syscall
2. Bypass ntdll hooks (EDR userland hooks, not relevant for Defender-only)
3. Test if kernel EtwTi still fires (it will — this bypasses hooks, not kernel)

## Files (when built)

```
injection/
+-- hollow_annotated.c     # Process hollowing with full commentary
+-- hollow.c               # Deployment variant
+-- inject_dll_annotated.c # DLL injection variant
+-- README.md              # This file
```
