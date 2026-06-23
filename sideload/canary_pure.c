/*
 * canary_pure.c -- Minimal DLL with no proxy pattern
 * Tests whether Defender flags the DLL proxy signature specifically,
 * or blocks ANY DLL sideloaded into the Wondershare directory.
 * No LoadLibrary, no GetProcAddress, no forwarding.
 * Just DllMain + breadcrumb write.
 */

#include <windows.h>

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p)
{
    HANDLE f;
    DWORD w;
    char b[256];
    int n;
    SYSTEMTIME t;
    char u[64];
    DWORD ul = 64;

    (void)h; (void)p;
    if (r != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(h);

    GetLocalTime(&t);
    GetUserNameA(u, &ul);
    n = wsprintfA(b, "%04d%02d%02d_%02d%02d%02d %s %lu\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        u, GetCurrentProcessId());

    f = CreateFileA("C:\\Windows\\Temp\\ws_diag.log",
        GENERIC_WRITE, FILE_SHARE_READ, NULL, OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        SetFilePointer(f, 0, NULL, FILE_END);
        WriteFile(f, b, n, &w, NULL);
        CloseHandle(f);
    }
    return TRUE;
}
