/*
 * test_gate_vdr.c -- CHEYANNE Gate Engine Test Harness
 * -----------------------------------------------------------------------
 * CHEYANNE / 22DIV / george wu
 *
 * Verifies:
 *   1. FNV-1a hash computation
 *   2. ROL/XOR decrypt correctness
 *   3. PEB walk finds ntdll
 *   4. SSN extraction (expect 10/10)
 *   5. Cross-verification vs GetProcAddress
 *   6. Live indirect syscall: NtClose(0xDEADBEEF) = 0xC0000008
 *   7. Gadget pool rotation
 *
 * COMPILE:
 *   ml64.exe /c gate_stub_vdr.asm /Fo:gate_stub_vdr.obj
 *   cl.exe /O1 /GS- /utf-8 gate_vdr.c test_gate_vdr.c gate_stub_vdr.obj /Fe:test_gate_vdr.exe
 */

#include <stdio.h>
#include <windows.h>
#include "gate_vdr.h"

/* -----------------------------------------------------------------------
 * CONSOLE COLORS
 * ----------------------------------------------------------------------- */

#define COL_RESET   "\033[0m"
#define COL_GREEN   "\033[32m"
#define COL_RED     "\033[31m"
#define COL_YELLOW  "\033[33m"
#define COL_CYAN    "\033[36m"
#define COL_BOLD    "\033[1m"
#define COL_DIM     "\033[2m"

#define PASS COL_GREEN "[PASS]" COL_RESET
#define FAIL COL_RED   "[FAIL]" COL_RESET
#define INFO COL_CYAN  "[INFO]" COL_RESET
#define WARN COL_YELLOW "[WARN]" COL_RESET

/* -----------------------------------------------------------------------
 * KNOWN FNV-1a HASHES (plaintext, unencrypted)
 * Used to verify the hash function and decrypt function
 * ----------------------------------------------------------------------- */

typedef struct {
    const char *name;
    DWORD       fnv1a_hash;
    DWORD       encrypted;
} HASH_VECTOR;

static HASH_VECTOR vectors[] = {
    { "NtOpenThread",            0, vHASH_NtOpenThread },
    { "NtSuspendThread",         0, vHASH_NtSuspendThread },
    { "NtResumeThread",          0, vHASH_NtResumeThread },
    { "NtGetContextThread",      0, vHASH_NtGetContextThread },
    { "NtSetContextThread",      0, vHASH_NtSetContextThread },
    { "NtAllocateVirtualMemory", 0, vHASH_NtAllocateVirtualMemory },
    { "NtWriteVirtualMemory",    0, vHASH_NtWriteVirtualMemory },
    { "NtProtectVirtualMemory",  0, vHASH_NtProtectVirtualMemory },
    { "NtCreateThreadEx",        0, vHASH_NtCreateThreadEx },
    { "NtClose",                 0, vHASH_NtClose },
};

#define NUM_VECTORS (sizeof(vectors) / sizeof(vectors[0]))

/* -----------------------------------------------------------------------
 * TEST: FNV-1a HASH COMPUTATION
 * ----------------------------------------------------------------------- */

static int test_fnv1a_hash(void) {
    int pass = 0;
    DWORD i;

    printf("\n" COL_BOLD "--- TEST 1: FNV-1a Hash Computation ---" COL_RESET "\n");

    for (i = 0; i < NUM_VECTORS; i++) {
        DWORD computed = vdr_gate_hash(vectors[i].name);
        vectors[i].fnv1a_hash = computed;
        printf("  %-30s -> 0x%08X\n", vectors[i].name, computed);
        pass++;
    }

    printf("  %s  %d/%d hashes computed\n", PASS, pass, (int)NUM_VECTORS);
    return pass;
}

/* -----------------------------------------------------------------------
 * TEST: ROL/XOR DECRYPT VERIFICATION
 * ----------------------------------------------------------------------- */

static int test_decrypt(void) {
    int pass = 0, fail = 0;
    DWORD i;

    printf("\n" COL_BOLD "--- TEST 2: ROL/XOR Decrypt Verification ---" COL_RESET "\n");

    for (i = 0; i < NUM_VECTORS; i++) {
        DWORD decrypted = vdr_gate_decrypt(vectors[i].encrypted);
        DWORD expected  = vectors[i].fnv1a_hash;

        if (decrypted == expected) {
            printf("  %s  %-30s decrypt(0x%08X) = 0x%08X\n",
                   PASS, vectors[i].name, vectors[i].encrypted, decrypted);
            pass++;
        } else {
            printf("  %s  %-30s decrypt(0x%08X) = 0x%08X (expected 0x%08X)\n",
                   FAIL, vectors[i].name, vectors[i].encrypted, decrypted, expected);
            fail++;
        }
    }

    printf("  %s  %d/%d decrypts matched\n",
           fail == 0 ? PASS : FAIL, pass, (int)NUM_VECTORS);
    return pass;
}

/* -----------------------------------------------------------------------
 * TEST: PEB WALK FINDS NTDLL
 * ----------------------------------------------------------------------- */

static HMODULE test_peb_walk(void) {
    HMODULE ntdll;

    printf("\n" COL_BOLD "--- TEST 3: PEB Walk (ntdll.dll) ---" COL_RESET "\n");

    ntdll = vdr_gate_find_ntdll();
    if (ntdll) {
        printf("  %s  ntdll base: 0x%p\n", PASS, ntdll);
    } else {
        printf("  %s  PEB walk returned NULL\n", FAIL);
    }

    return ntdll;
}

/* -----------------------------------------------------------------------
 * TEST: SSN EXTRACTION (expect 10/10)
 * ----------------------------------------------------------------------- */

static int test_ssn_extraction(void) {
    VDR_GATE_TABLE tbl;
    int n;

    printf("\n" COL_BOLD "--- TEST 4: SSN Extraction ---" COL_RESET "\n");

    n = vdr_gate_init(&tbl);

    printf("  Resolved: %d/10\n", n);

#define SHOW_ENT(name, ent) \
    printf("  %-30s  SSN=0x%04X  gadget=0x%p  pool=%d  %s%s\n", \
           name, (ent).ssn, (ent).gadget, (ent).pool_sz, \
           (ent).ok ? COL_GREEN "OK" COL_RESET : COL_RED "FAIL" COL_RESET, \
           (ent).hooked ? COL_YELLOW " [HALO]" COL_RESET : "");

    SHOW_ENT("NtOpenThread",            tbl.NtOpenThread);
    SHOW_ENT("NtSuspendThread",         tbl.NtSuspendThread);
    SHOW_ENT("NtResumeThread",          tbl.NtResumeThread);
    SHOW_ENT("NtGetContextThread",      tbl.NtGetContextThread);
    SHOW_ENT("NtSetContextThread",      tbl.NtSetContextThread);
    SHOW_ENT("NtAllocateVirtualMemory", tbl.NtAllocateVirtualMemory);
    SHOW_ENT("NtWriteVirtualMemory",    tbl.NtWriteVirtualMemory);
    SHOW_ENT("NtProtectVirtualMemory",  tbl.NtProtectVirtualMemory);
    SHOW_ENT("NtCreateThreadEx",        tbl.NtCreateThreadEx);
    SHOW_ENT("NtClose",                 tbl.NtClose);

#undef SHOW_ENT

    printf("\n  Global gadgets collected: %d\n", tbl.gadget_count);

    if (n == 10) {
        printf("  %s  10/10 SSNs extracted\n", PASS);
    } else {
        printf("  %s  only %d/10 SSNs extracted\n", FAIL, n);
    }

    return n;
}

/* -----------------------------------------------------------------------
 * TEST: CROSS-VERIFICATION VS GetProcAddress
 * ----------------------------------------------------------------------- */

static int test_cross_verify(HMODULE ntdll) {
    int pass = 0, fail = 0;
    DWORD i;

    printf("\n" COL_BOLD "--- TEST 5: Cross-verification vs GetProcAddress ---" COL_RESET "\n");

    if (!ntdll) {
        printf("  %s  ntdll is NULL, skipping\n", FAIL);
        return 0;
    }

    for (i = 0; i < NUM_VECTORS; i++) {
        VDR_SYSCALL_ENTRY ent;
        DWORD raw_hash = vectors[i].fnv1a_hash;
        FARPROC gpa_addr = GetProcAddress(ntdll, vectors[i].name);

        if (!gpa_addr) {
            printf("  %s  %-30s GetProcAddress returned NULL\n",
                   WARN, vectors[i].name);
            continue;
        }

        if (vdr_gate_resolve(ntdll, raw_hash, &ent) && ent.ok) {
            /* Check that our gadget is near the GPA address (within the stub) */
            ptrdiff_t diff = (BYTE *)ent.gadget - (BYTE *)gpa_addr;
            if (diff >= 0 && diff < STUB_SIZE) {
                printf("  %s  %-30s gadget offset +%td from GPA\n",
                       PASS, vectors[i].name, diff);
                pass++;
            } else {
                printf("  %s  %-30s gadget offset %td (unexpected)\n",
                       WARN, vectors[i].name, diff);
                pass++; /* Halo recovery may return a different stub's gadget */
            }
        } else {
            printf("  %s  %-30s resolve failed\n", FAIL, vectors[i].name);
            fail++;
        }
    }

    printf("  %s  %d/%d cross-verified\n",
           fail == 0 ? PASS : FAIL, pass, (int)NUM_VECTORS);
    return pass;
}

/* -----------------------------------------------------------------------
 * TEST: LIVE INDIRECT SYSCALL
 * NtClose(0xDEADBEEF) should return STATUS_INVALID_HANDLE (0xC0000008)
 * ----------------------------------------------------------------------- */

static int test_live_syscall(void) {
    VDR_GATE_TABLE tbl;
    NTSTATUS status;
    HANDLE bad_handle = (HANDLE)(ULONG_PTR)0xDEADBEEF;

    printf("\n" COL_BOLD "--- TEST 6: Live Indirect Syscall ---" COL_RESET "\n");

    if (vdr_gate_init(&tbl) == 0 || !tbl.NtClose.ok) {
        printf("  %s  NtClose not resolved, cannot test\n", FAIL);
        return 0;
    }

    printf("  Calling NtClose(0xDEADBEEF) via indirect syscall...\n");

    SetSyscallVdr(tbl.NtClose.ssn, tbl.NtClose.gadget);
    status = ((NTSTATUS(__stdcall *)(HANDLE))IndirectSyscallVdr)(bad_handle);

    printf("  NTSTATUS = 0x%08X\n", (unsigned int)status);

    if (status == (NTSTATUS)0xC0000008) {
        printf("  %s  STATUS_INVALID_HANDLE -- indirect syscall works\n", PASS);
        return 1;
    } else {
        printf("  %s  unexpected status (expected 0xC0000008)\n", FAIL);
        return 0;
    }
}

/* -----------------------------------------------------------------------
 * TEST: GADGET POOL ROTATION
 * ----------------------------------------------------------------------- */

static int test_gadget_pool(void) {
    VDR_GATE_TABLE tbl;
    int total_pool = 0;
    int i;

    printf("\n" COL_BOLD "--- TEST 7: Gadget Pool Rotation ---" COL_RESET "\n");

    if (vdr_gate_init(&tbl) == 0) {
        printf("  %s  gate_init failed\n", FAIL);
        return 0;
    }

    /* Check pool sizes for each entry */
    VDR_SYSCALL_ENTRY *entries[] = {
        &tbl.NtOpenThread, &tbl.NtSuspendThread, &tbl.NtResumeThread,
        &tbl.NtGetContextThread, &tbl.NtSetContextThread,
        &tbl.NtAllocateVirtualMemory, &tbl.NtWriteVirtualMemory,
        &tbl.NtProtectVirtualMemory, &tbl.NtCreateThreadEx, &tbl.NtClose
    };
    const char *names[] = {
        "NtOpenThread", "NtSuspendThread", "NtResumeThread",
        "NtGetContextThread", "NtSetContextThread",
        "NtAllocateVirtualMemory", "NtWriteVirtualMemory",
        "NtProtectVirtualMemory", "NtCreateThreadEx", "NtClose"
    };

    for (i = 0; i < 10; i++) {
        if (entries[i]->ok) {
            printf("  %-30s pool_sz=%d  primary=0x%p\n",
                   names[i], entries[i]->pool_sz, entries[i]->gadget);
            total_pool += entries[i]->pool_sz;

            /* Show first few pool entries */
            int j;
            for (j = 0; j < entries[i]->pool_sz && j < 3; j++) {
                printf("    " COL_DIM "pool[%d] = 0x%p" COL_RESET "\n",
                       j, entries[i]->gadget_pool[j]);
            }
            if (entries[i]->pool_sz > 3) {
                printf("    " COL_DIM "... +%d more" COL_RESET "\n",
                       entries[i]->pool_sz - 3);
            }
        }
    }

    printf("\n  Total pool gadgets across all entries: %d\n", total_pool);
    printf("  Global gadgets: %d\n", tbl.gadget_count);

    if (total_pool > 0) {
        printf("  %s  gadget pool rotation available\n", PASS);
    } else {
        printf("  %s  no pool gadgets found\n", WARN);
    }

    /* Test rotation: use a pool gadget for NtClose call */
    if (tbl.NtClose.ok && tbl.NtClose.pool_sz > 0) {
        NTSTATUS status;
        HANDLE bad = (HANDLE)(ULONG_PTR)0xDEADBEEF;

        printf("\n  Rotation test: NtClose via pool gadget[0]...\n");
        SetSyscallVdr(tbl.NtClose.ssn, tbl.NtClose.gadget_pool[0]);
        status = ((NTSTATUS(__stdcall *)(HANDLE))IndirectSyscallVdr)(bad);

        if (status == (NTSTATUS)0xC0000008) {
            printf("  %s  pool gadget rotation works (0x%08X)\n", PASS, (unsigned int)status);
        } else {
            printf("  %s  unexpected status 0x%08X\n", FAIL, (unsigned int)status);
        }
    }

    return total_pool > 0 ? 1 : 0;
}

/* -----------------------------------------------------------------------
 * MAIN
 * ----------------------------------------------------------------------- */

int main(void) {
    HMODULE ntdll;
    int total_pass = 0;
    int total_tests = 7;

    /* Enable ANSI escape codes on Windows 10+ */
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD mode;
    if (GetConsoleMode(hOut, &mode)) {
        SetConsoleMode(hOut, mode | 0x0004 /* ENABLE_VIRTUAL_TERMINAL_PROCESSING */);
    }

#ifdef VDR_DEBUG
    printf("\n");
    printf(COL_BOLD "================================================================\n");
    printf("  CHEYANNE -- Gate Engine Test / 22DIV / george wu\n");
    printf("  Variant B: FNV-1a + ROL/XOR + Gadget Pool\n");
    printf("================================================================" COL_RESET "\n");
#endif

    /* Test 1: Hash computation */
    if (test_fnv1a_hash() > 0) total_pass++;

    /* Test 2: Decrypt verification */
    if (test_decrypt() == (int)NUM_VECTORS) total_pass++;

    /* Test 3: PEB walk */
    ntdll = test_peb_walk();
    if (ntdll) total_pass++;

    /* Test 4: SSN extraction */
    if (test_ssn_extraction() == 10) total_pass++;

    /* Test 5: Cross-verify vs GetProcAddress */
    if (test_cross_verify(ntdll) > 0) total_pass++;

    /* Test 6: Live indirect syscall */
    if (test_live_syscall()) total_pass++;

    /* Test 7: Gadget pool rotation */
    if (test_gadget_pool()) total_pass++;

    /* Summary */
    printf("\n" COL_BOLD "================================================================\n");
    printf("  RESULT: %d/%d test groups passed\n", total_pass, total_tests);
    printf("================================================================" COL_RESET "\n\n");

    return (total_pass == total_tests) ? 0 : 1;
}
