/*
 * test_debug.c — Detailed hook debugging
 */

#include <windows.h>
#include <stdio.h>

typedef long (NTAPI *pfnNtQSI)(ULONG, PVOID, ULONG, PULONG);

static void dump(const char *label, BYTE *addr, int n) {
    printf("  %-20s ", label);
    for (int i = 0; i < n; i++) printf("%02X ", addr[i]);
    printf("\n");
}

int main(void) {
    printf("\n  CHEYANNE CLOAK - Hook Debug\n\n");

    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    pfnNtQSI pNtQSI = (pfnNtQSI)GetProcAddress(ntdll, "NtQuerySystemInformation");
    BYTE *target = (BYTE *)pNtQSI;

    printf("  NtQSI at %p\n", target);
    dump("[BEFORE LOAD]", target, 24);

    ULONG bufSize = 2 * 1024 * 1024;
    BYTE *buf = (BYTE *)malloc(bufSize);
    ULONG retLen = 0;
    long st = pNtQSI(5, buf, bufSize, &retLen);
    printf("  Pre-hook call: NTSTATUS=0x%08lX  retLen=%lu\n\n", st, retLen);

    printf("  Loading cloak.dll...\n");
    HMODULE hCloak = LoadLibraryA("cloak.dll");
    if (!hCloak) { printf("  FAILED: %lu\n", GetLastError()); return 1; }

    dump("[AFTER LOAD]", target, 24);

    printf("\n  Calling NtQSI through hook...\n");
    retLen = 0;
    st = pNtQSI(5, buf, bufSize, &retLen);
    printf("  Hooked call: NTSTATUS=0x%08lX  retLen=%lu\n", st, retLen);

    if (st == 0) {
        typedef struct { ULONG NextOff; ULONG NumThreads; char pad[32];
            USHORT NameLen; USHORT NameMax; WCHAR *NameBuf; } MINI;
        /* just count entries */
        int n = 0;
        BYTE *p = buf;
        for (;;) {
            n++;
            ULONG nxt = *(ULONG *)p;
            if (nxt == 0) break;
            p += nxt;
        }
        printf("  Process entries: %d\n", n);
    }

    printf("\n  Non-SPI call (class=2, SystemPerformanceInformation)...\n");
    BYTE smallbuf[512];
    st = pNtQSI(2, smallbuf, sizeof(smallbuf), &retLen);
    printf("  Class 2: NTSTATUS=0x%08lX  retLen=%lu\n", st, retLen);

    printf("\n  Unloading...\n");
    FreeLibrary(hCloak);
    dump("[AFTER UNLOAD]", target, 24);

    retLen = 0;
    st = pNtQSI(5, buf, bufSize, &retLen);
    printf("  Post-unhook: NTSTATUS=0x%08lX  retLen=%lu\n", st, retLen);

    free(buf);
    printf("\n");
    return 0;
}
