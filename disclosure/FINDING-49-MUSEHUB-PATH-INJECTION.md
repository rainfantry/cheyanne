# Finding #49: Muse Hub System PATH Injection (CWE-426 LPE)

## Classification

| Field | Value |
|-------|-------|
| **CWE** | CWE-426: Untrusted Search Path Element |
| **Target** | Muse Hub (MuseScore/Steinberg) |
| **Severity** | High — Standard user → SYSTEM/LocalService privilege escalation |
| **CVE Probability** | 60-70% — distinct from CVE-2025-13433 (CWE-428 unquoted path) |
| **Test Date** | 2026-06-15 |
| **OS** | Windows 11 Home Build 26200 |
| **User Context** | Standard user (gwu07, no admin) |

## Finding

The Muse Hub installer adds a **user-profile directory** to the **HKLM system-wide PATH**:

```
C:\Users\gwu07\AppData\Local\Muse Hub\lib
```

This directory is **fully writable by the user** and is included in the DLL search path for ALL processes on the system, including SYSTEM services.

### Distinction from CVE-2025-13433

| | CVE-2025-13433 | This Finding |
|---|---|---|
| CWE | CWE-428 (Unquoted Service Path) | CWE-426 (Untrusted Search Path) |
| Vector | Unquoted ImagePath allows binary planting | User-writable dir in HKLM PATH allows DLL hijack |
| Scope | Muse Hub's own services only | ALL SYSTEM services that use DLL search path |
| Root Cause | Missing quotes in service registration | User-profile dir injected into machine-level PATH |

## Evidence Chain

### Step 1: PATH Injection Confirmed

```
HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment
PATH = ...;C:\Users\gwu07\AppData\Local\Muse Hub\lib;...
```

### Step 2: Directory is User-Writable

```
C:\Users\gwu07\AppData\Local\Muse Hub\lib
    LAPTOP-R32M8MLI\gwu07:(OI)(CI)(F)   ← FULL CONTROL
    NT AUTHORITY\SYSTEM:(OI)(CI)(F)
    BUILTIN\Administrators:(OI)(CI)(F)
```

### Step 3: SYSTEM Services Reference Phantom DLLs

Windows SYSTEM services attempt to load DLLs that don't exist in System32:

| Service | Account | Phantom DLL | Reference |
|---------|---------|-------------|-----------|
| StorSvc | LocalSystem | SprintCSP.dll | CVE-2023-21746 (delay-loaded) |
| CdpSvc | LocalService | cdpsgshims.dll | MSRC Case 54347 (unpatched) |

When these services can't find the DLLs in the application directory or System32, the search falls through to PATH directories — including the user-writable Muse Hub directory.

### Step 4: Standard User Plants DLL

```cmd
copy payload.dll "C:\Users\gwu07\AppData\Local\Muse Hub\lib\SprintCSP.dll"
copy payload.dll "C:\Users\gwu07\AppData\Local\Muse Hub\lib\cdpsgshims.dll"
```

### Step 5: PENDING — SYSTEM Execution on Service Restart/Reboot

DLLs are planted. On next reboot (or service restart), the service will search PATH and load our DLL as SYSTEM/LocalService.

**Canary DLL**: `poc_path_hijack.c` — writes timestamp, username, elevation status, PID to `C:\Windows\Temp\vader_path_hijack.log`
**SHA256**: `F4DEF9FFE9875DEDDC2C22E11A3207EF9DA81E7F2FBEBD1F7273D557F8D9CDDF`

## Additional PATH Injection: uv (Astral)

The `uv` Python package manager (v0.10.4) also injects a user-writable directory into HKLM PATH:

```
C:\Users\gwu07\.local\bin
```

Same vulnerability class — different vendor. Could be a separate CVE submission to Astral.

## Attack Chain Summary

```
Standard User (no admin)
  ├── 1. Muse Hub installer added user-writable dir to HKLM PATH [PROVEN]
  ├── 2. User creates malicious DLL in that directory [PROVEN]
  ├── 3. SYSTEM services search for phantom DLLs [DOCUMENTED]
  ├── 4. DLL search falls through to PATH directories [DLL SEARCH ORDER]
  └── 5. SYSTEM loads user-planted DLL [PENDING REBOOT PROOF]
```

## Remediation

1. **Muse Hub**: Do not add user-profile directories to HKLM system PATH. Use per-application PATH or application directory only.
2. **uv (Astral)**: Same — use per-user PATH (HKCU) instead of system-wide HKLM PATH for user-specific directories.
3. **Microsoft**: Consider validating DLL paths loaded by SYSTEM services against a whitelist of trusted directories, or adding SafeDllSearchMode enforcement for PATH-based loading.
