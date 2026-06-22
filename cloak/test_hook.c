/*
 * test_hook.c — Single-Process Hook Test
 * 22DIV / george wu
 */

#include <windows.h>
#include <stdio.h>
#include <tlhelp32.h>
#include <iphlpapi.h>
#include <winternl.h>

#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "ntdll.lib")

#define SPI_CLASS 5

typedef struct _SYS_PROC_INFO {
    ULONG           NextEntryOffset;
    ULONG           NumberOfThreads;
    LARGE_INTEGER   WorkingSetPrivateSize;
    ULONG           HardFaultCount;
    ULONG           NumberOfThreadsHighWatermark;
    ULONGLONG       CycleTime;
    LARGE_INTEGER   CreateTime;
    LARGE_INTEGER   UserTime;
    LARGE_INTEGER   KernelTime;
    UNICODE_STRING  ImageName;
    LONG            BasePriority;
    HANDLE          UniqueProcessId;
    HANDLE          InheritedFromUniqueProcessId;
    ULONG           HandleCount;
    ULONG           SessionId;
    ULONG_PTR       UniqueProcessKey;
    SIZE_T          PeakVirtualSize;
    SIZE_T          VirtualSize;
    ULONG           PageFaultCount;
    SIZE_T          PeakWorkingSetSize;
    SIZE_T          WorkingSetSize;
    SIZE_T          QuotaPeakPagedPoolUsage;
    SIZE_T          QuotaPagedPoolUsage;
    SIZE_T          QuotaPeakNonPagedPoolUsage;
    SIZE_T          QuotaNonPagedPoolUsage;
    SIZE_T          PagefileUsage;
    SIZE_T          PeakPagefileUsage;
    SIZE_T          PrivatePageCount;
    LARGE_INTEGER   ReadOperationCount;
    LARGE_INTEGER   WriteOperationCount;
    LARGE_INTEGER   OtherOperationCount;
    LARGE_INTEGER   ReadTransferCount;
    LARGE_INTEGER   WriteTransferCount;
    LARGE_INTEGER   OtherTransferCount;
} SYS_PROC_INFO;

typedef NTSTATUS (NTAPI *pfnNtQuerySystemInformation)(
    ULONG, PVOID, ULONG, PULONG
);

static int count_process_direct(pfnNtQuerySystemInformation fn, const wchar_t *target) {
    ULONG bufSize = 1024 * 1024;
    BYTE *buf = (BYTE *)malloc(bufSize);
    if (!buf) return -2;

    ULONG retLen = 0;
    NTSTATUS st = fn(SPI_CLASS, buf, bufSize, &retLen);
    if (st != 0) {
        printf("    NtQuerySystemInformation returned 0x%08lX\n", st);
        free(buf);
        return -1;
    }

    int count = 0;
    int total = 0;
    SYS_PROC_INFO *curr = (SYS_PROC_INFO *)buf;
    for (;;) {
        total++;
        if (curr->ImageName.Buffer && curr->ImageName.Length > 0) {
            ULONG charLen = curr->ImageName.Length / sizeof(WCHAR);
            ULONG targetLen = (ULONG)wcslen(target);
            if (charLen == targetLen) {
                BOOL match = TRUE;
                for (ULONG j = 0; j < charLen; j++) {
                    wchar_t ca = curr->ImageName.Buffer[j];
                    wchar_t cb = target[j];
                    if (ca >= L'A' && ca <= L'Z') ca += 32;
                    if (cb >= L'A' && cb <= L'Z') cb += 32;
                    if (ca != cb) { match = FALSE; break; }
                }
                if (match) count++;
            }
        }
        if (curr->NextEntryOffset == 0) break;
        curr = (SYS_PROC_INFO *)((BYTE *)curr + curr->NextEntryOffset);
    }
    printf("    Total processes enumerated: %d\n", total);
    free(buf);
    return count;
}

static int count_port_connections(USHORT port) {
    DWORD size = 0;
    GetExtendedTcpTable(NULL, &size, FALSE, AF_INET,
                        TCP_TABLE_OWNER_PID_ALL, 0);
    if (size == 0) return 0;

    BYTE *buf = (BYTE *)malloc(size);
    if (!buf) return -1;

    DWORD ret = GetExtendedTcpTable(buf, &size, FALSE, AF_INET,
                                     TCP_TABLE_OWNER_PID_ALL, 0);
    if (ret != NO_ERROR) { free(buf); return -1; }

    MIB_TCPTABLE_OWNER_PID *table = (MIB_TCPTABLE_OWNER_PID *)buf;
    int count = 0;
    for (DWORD i = 0; i < table->dwNumEntries; i++) {
        USHORT lp = ntohs((u_short)table->table[i].dwLocalPort);
        USHORT rp = ntohs((u_short)table->table[i].dwRemotePort);
        if (lp == port || rp == port) count++;
    }
    free(buf);
    return count;
}

int main(void) {
    printf("\n  CHEYANNE CLOAK - Single-Process Hook Test\n");
    printf("  22DIV / george wu\n");
    printf("  ======================================\n");

    pfnNtQuerySystemInformation pNtQSI =
        (pfnNtQuerySystemInformation)GetProcAddress(
            GetModuleHandleA("ntdll.dll"), "NtQuerySystemInformation");

    if (!pNtQSI) {
        printf("  [!] Can't resolve NtQuerySystemInformation\n");
        return 1;
    }

    printf("\n  [BEFORE HOOKS]\n");
    int proc_before = count_process_direct(pNtQSI, L"dark_room.exe");
    int conn_before = count_port_connections(4443);
    printf("    dark_room.exe instances: %d\n", proc_before);
    printf("    Port 4443 connections:   %d\n", conn_before);

    printf("\n  [*] Loading cloak.dll...\n");
    HMODULE hCloak = LoadLibraryA("cloak.dll");
    if (!hCloak) {
        printf("  [!] LoadLibrary failed (error %lu)\n", GetLastError());
        return 1;
    }
    printf("  [+] cloak.dll loaded - hooks active\n");

    printf("\n  [AFTER HOOKS]\n");
    int proc_after = count_process_direct(pNtQSI, L"dark_room.exe");
    int conn_after = count_port_connections(4443);
    printf("    dark_room.exe instances: %d\n", proc_after);
    printf("    Port 4443 connections:   %d\n", conn_after);

    printf("\n  [RESULTS]\n");
    if (proc_before > 0 && proc_after == 0)
        printf("    [+] PROCESS HIDING: WORKING\n");
    else if (proc_before == 0)
        printf("    [?] PROCESS HIDING: UNTESTED (not running)\n");
    else if (proc_after < 0)
        printf("    [-] PROCESS HIDING: ERROR (NtQSI returned error)\n");
    else
        printf("    [-] PROCESS HIDING: FAILED (still visible: %d)\n", proc_after);

    if (conn_before > 0 && conn_after == 0)
        printf("    [+] CONNECTION HIDING: WORKING\n");
    else if (conn_before == 0)
        printf("    [?] CONNECTION HIDING: UNTESTED (no port 4443)\n");
    else
        printf("    [-] CONNECTION HIDING: FAILED (still visible: %d)\n", conn_after);

    printf("\n  [*] Unloading cloak.dll...\n");
    FreeLibrary(hCloak);
    printf("  [+] Hooks removed\n");

    printf("\n  [AFTER UNHOOK]\n");
    int proc_restored = count_process_direct(pNtQSI, L"dark_room.exe");
    printf("    dark_room.exe instances: %d\n", proc_restored);
    if (proc_before > 0 && proc_restored == proc_before)
        printf("    [+] Visibility restored correctly\n");

    printf("\n");
    return 0;
}
