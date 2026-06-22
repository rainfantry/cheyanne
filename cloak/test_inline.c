/*
 * test_inline.c — Standalone inline hook test
 * No DLL, no filtering — just hook and call through trampoline.
 */

#include <windows.h>
#include <stdio.h>

typedef long (NTAPI *pfnNtQSI)(ULONG, PVOID, ULONG, PULONG);

static BYTE  g_saved[24];
static BYTE *g_trampoline = NULL;
static BYTE *g_target = NULL;

#define STUB_SIZE  24  /* full NT stub: mov r10 + mov eax + test + jne + syscall + ret + int2e + ret */
#define PATCH_SIZE 12  /* mov rax, addr; jmp rax */

static long NTAPI my_hook(ULONG cls, PVOID buf, ULONG len, PULONG retLen) {
    pfnNtQSI orig = (pfnNtQSI)g_trampoline;
    long st = orig(cls, buf, len, retLen);
    return st;
}

static void write_jmp(BYTE *dst, void *target) {
    dst[0] = 0x48; dst[1] = 0xB8;
    *(UINT64 *)(dst + 2) = (UINT64)target;
    dst[10] = 0xFF; dst[11] = 0xE0;
}

int main(void) {
    printf("\n  Standalone Inline Hook Test (Full-Stub Trampoline)\n\n");

    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    g_target = (BYTE *)GetProcAddress(ntdll, "NtQuerySystemInformation");
    printf("  Target: %p\n", g_target);

    printf("  Original bytes (24): ");
    for (int i = 0; i < STUB_SIZE; i++) printf("%02X ", g_target[i]);
    printf("\n");

    g_trampoline = (BYTE *)VirtualAlloc(NULL, 64,
        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    printf("  Trampoline at: %p\n", g_trampoline);

    memcpy(g_saved, g_target, STUB_SIZE);

    /* self-contained trampoline: full stub copy, NO JMP back to ntdll */
    memcpy(g_trampoline, g_saved, STUB_SIZE);
    FlushInstructionCache(GetCurrentProcess(), g_trampoline, STUB_SIZE);

    printf("  Trampoline bytes (24): ");
    for (int i = 0; i < STUB_SIZE; i++) printf("%02X ", g_trampoline[i]);
    printf("\n");

    printf("\n  [Test 1] Call trampoline directly (no patch yet)...\n");
    {
        pfnNtQSI fn = (pfnNtQSI)g_trampoline;
        BYTE tbuf[512]; ULONG tret = 0;
        long st = fn(2, tbuf, sizeof(tbuf), &tret);
        printf("  Result: 0x%08lX  retLen=%lu\n", st, tret);
    }

    /* patch target: 12-byte JMP + NOP remaining 12 bytes */
    DWORD oldProt;
    VirtualProtect(g_target, STUB_SIZE, PAGE_EXECUTE_READWRITE, &oldProt);
    write_jmp(g_target, my_hook);
    for (int i = PATCH_SIZE; i < STUB_SIZE; i++) g_target[i] = 0x90;
    DWORD dummy;
    VirtualProtect(g_target, STUB_SIZE, oldProt, &dummy);
    FlushInstructionCache(GetCurrentProcess(), g_target, STUB_SIZE);

    printf("\n  Patched bytes: ");
    for (int i = 0; i < STUB_SIZE; i++) printf("%02X ", g_target[i]);
    printf("\n");

    printf("\n  [Test 2] Call NtQSI class 2 through hook...\n");
    {
        pfnNtQSI fn = (pfnNtQSI)g_target;
        BYTE tbuf[512]; ULONG tret = 0;
        long st = fn(2, tbuf, sizeof(tbuf), &tret);
        printf("  Result: 0x%08lX  retLen=%lu\n", st, tret);
    }

    printf("\n  [Test 3] Call NtQSI class 5 through hook (1MB buf)...\n");
    {
        pfnNtQSI fn = (pfnNtQSI)g_target;
        ULONG bsz = 1024*1024;
        BYTE *bigbuf = (BYTE *)malloc(bsz);
        ULONG tret = 0;
        long st = fn(5, bigbuf, bsz, &tret);
        printf("  Result: 0x%08lX  retLen=%lu\n", st, tret);
        free(bigbuf);
    }

    /* restore */
    VirtualProtect(g_target, STUB_SIZE, PAGE_EXECUTE_READWRITE, &oldProt);
    memcpy(g_target, g_saved, STUB_SIZE);
    VirtualProtect(g_target, STUB_SIZE, oldProt, &dummy);
    FlushInstructionCache(GetCurrentProcess(), g_target, STUB_SIZE);

    VirtualFree(g_trampoline, 0, MEM_RELEASE);

    printf("\n  [Test 4] Call NtQSI after restore...\n");
    {
        pfnNtQSI fn = (pfnNtQSI)g_target;
        BYTE tbuf[512]; ULONG tret = 0;
        long st = fn(2, tbuf, sizeof(tbuf), &tret);
        printf("  Result: 0x%08lX  retLen=%lu\n", st, tret);
    }

    printf("\n");
    return 0;
}
