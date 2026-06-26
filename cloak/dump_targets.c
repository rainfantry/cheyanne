/*
 * dump_targets.c — Dump target function prologues
 * Verify byte patterns before hooking.
 */

#include <windows.h>
#include <stdio.h>
#include <iphlpapi.h>

#pragma comment(lib, "iphlpapi.lib")

static void dump_bytes(const char *name, void *addr, int count) {
    if (!addr) {
        printf("  %-30s NOT FOUND\n", name);
        return;
    }
    BYTE *p = (BYTE *)addr;
    printf("  %-30s %p  ", name, addr);
    for (int i = 0; i < count; i++)
        printf("%02X ", p[i]);
    printf("\n");
}

int main(void) {
    printf("\n  CHEYANNE CLOAK - Target Function Prologues\n");
    printf("  ========================================\n\n");

    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    HMODULE iphlp = LoadLibraryA("iphlpapi.dll");

    if (ntdll) {
        dump_bytes("NtQuerySystemInformation",
            GetProcAddress(ntdll, "NtQuerySystemInformation"), 32);
        dump_bytes("NtQueryDirectoryFile",
            GetProcAddress(ntdll, "NtQueryDirectoryFile"), 32);
    }

    if (iphlp) {
        dump_bytes("GetExtendedTcpTable",
            GetProcAddress(iphlp, "GetExtendedTcpTable"), 32);
    }

    printf("\n  NT stub expected pattern:\n");
    printf("    4C 8B D1          mov r10, rcx       (3B)\n");
    printf("    B8 XX XX 00 00    mov eax, <num>     (5B)\n");
    printf("    F6 04 25 ...      test byte [..], 1  (8B)\n");
    printf("    = 16 bytes at clean boundary\n\n");

    return 0;
}
