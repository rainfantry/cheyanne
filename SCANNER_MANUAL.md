# VADER RECON SCANNER — USER MANUAL

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Operator: VADER (george wu / 22DIV)
## Authorisation: Own hardware only. CSEC academic research.

---

## What This Tool Does

`vader_recon.ps1` is a 20-section reconnaissance scanner that profiles a Windows machine for privilege escalation attack surfaces. It runs as a standard user — no admin required — and outputs a timestamped log file with everything an operator needs to choose and deploy the right VADER vector.

The scanner includes a **pure PowerShell PE import parser** that reads binary import tables directly — no dumpbin, no Visual Studio, no external tools. It works on any Windows machine with PowerShell 5.1+.

---

## Quick Start

```powershell
# Run from the vader-rootkit directory
powershell -ExecutionPolicy Bypass -File recon\vader_recon.ps1

# Or from anywhere with full path
powershell -ep bypass "C:\path\to\vader-rootkit\recon\vader_recon.ps1"
```

**Output:** A log file at `recon\RECON_<HOSTNAME>_<TIMESTAMP>.log`

**Runtime:** 30-90 seconds depending on number of services installed.

---

## What Each Section Reports

### Section 1: SYSTEM INFO

Basic machine identification.

| Field | What It Tells You |
|-------|-------------------|
| Hostname | Target machine name (used in log filename) |
| OS Version | Windows build — affects API availability |
| Architecture | x64 vs x86 — VADER is x64 only |
| Domain | Workgroup vs domain-joined (domain = more monitoring) |
| Uptime | How long since last reboot (services may need restart to trigger) |

**What to look for:** Windows 11 x64 is the expected target. If the architecture is x86, VADER binaries won't run.

---

### Section 2: USER CONTEXT

Who you are on this machine.

| Field | What It Tells You |
|-------|-------------------|
| Username | Current user identity |
| Is Admin | Whether the current session has admin rights |
| Integrity Level | Medium (standard) vs High (elevated) |
| UAC Status | Whether UAC is active and at what level |

**What to look for:** You want `Is Admin: False` and `Integrity: Medium`. The entire VADER chain assumes standard user — if you're already admin, the escalation proves nothing.

---

### Section 3: DEFENDER STATUS

Windows Defender configuration and version.

| Field | What It Tells You |
|-------|-------------------|
| RTP (Real-Time Protection) | ON = live scanning active. Must be ON for valid testing |
| Engine Version | mpengine.dll version — affects what signatures exist |
| Signature Version | VDM database version — daily updates change detection |
| Last Updated | When sigs were last refreshed |
| Tamper Protection | ON = can't disable Defender programmatically post-SYSTEM |

**What to look for:**
- RTP must be ON. If it's off, the test is meaningless.
- Tamper Protection ON means even after achieving SYSTEM, you can't disable Defender without a reboot. This is expected on modern Windows 11.
- Note the signature version — if a binary gets caught, updating sigs and retesting confirms it's a new signature, not a fluke.

---

### Section 4: DEFENDER EXCLUSIONS

Any paths or extensions excluded from scanning.

**What to look for:** Exclusions are gold. If a directory is excluded, anything placed there bypasses all Defender scanning. Check if any user-writable paths are excluded.

---

### Section 5: ASR RULES (Attack Surface Reduction)

Microsoft's behavioural rules that block specific attack patterns.

**What to look for:** ASR rules can block process injection, Office child process creation, and other techniques. If ASR is fully enabled, some VADER vectors may be blocked at the behavioural layer even if the binary evades static detection. Most consumer Windows 11 machines have ASR disabled or in audit mode.

---

### Section 6: SERVICES (Running as SYSTEM)

All Windows services running under the LocalSystem account.

**What to look for:** These are the targets. A SYSTEM service that loads your DLL = SYSTEM-level code execution from standard user. The scanner lists every SYSTEM service with its binary path and start type.

---

### Section 7: WRITABLE SERVICE BINARIES

Services where the standard user can modify the executable.

**What to look for:**
- **`[VULN]` markers** = the service binary is in a user-writable location
- This is the V4 DELTA attack surface (CWE-732)
- Common hit: Wondershare NativePushService (binary in user's AppData)
- If any SYSTEM service has a writable binary, V4 is viable

**Example output:**
```
[VULN] NativePushService (LocalSystem) at C:\Users\user\AppData\Local\Wondershare\...
  Owner: BUILTIN\Users
  BUILTIN\Users has: FullControl
```

---

### Section 8: PATH DIRECTORIES

Machine PATH environment variable contents and write permissions.

**What to look for:**
- Directories in the machine PATH that the current user can write to
- `[W]` marker = writable by current user
- Common hits: `%USERPROFILE%\.local\bin`, `Muse Hub\lib`
- These are the V6 FOXTROT and V7 GOLF attack surfaces
- The scanner uses `Test-WritablePractical` which actually attempts a file write (not just ACL check) to catch user-owned directories that ACL-only checks miss

---

### Section 9: DLL SEARCH ORDER

How Windows resolves DLL names — the foundation of all DLL hijack attacks.

**What to look for:** Understanding only. The search order is:
1. Application directory
2. System32
3. System directory (16-bit legacy)
4. Windows directory
5. Current directory
6. PATH directories

Steps 1-4 are controlled by the system. Step 6 (PATH) is where user-writable directories create the attack surface.

---

### Section 10: INSTALLED SOFTWARE

Software inventory via registry.

**What to look for:**
- **Microsoft Office** → V7 GOLF is viable (ClickToRunSvc + osppc.dll phantom)
- **Wondershare products** → V4 DELTA is viable (writable service binary)
- Third-party software with its own services → potential custom vectors

---

### Section 11: SCHEDULED TASKS

Tasks running as SYSTEM or with elevated privileges.

**What to look for:**
- Tasks with writable binaries or scripts
- Tasks that run frequently (short trigger wait time)
- Office-related tasks (Office Automatic Updates 2.0 triggers ClickToRunSvc)

---

### Section 12: SERVICE MANIFESTS

Application manifests that specify DLL loading behaviour.

**What to look for:** If a service binary has a manifest with `<dllRedirection>`, it may load DLLs from a specific directory instead of following the standard search order. This can block or redirect DLL hijack attempts. Most services don't have custom DLL redirection.

---

### Section 13: AMSI PROVIDERS

Registered AMSI (Antimalware Scan Interface) providers.

**What to look for:** Lists which security products hook into AMSI. Windows Defender is always present. Third-party AV may add additional providers. The dark room bypasses ALL AMSI providers because it intercepts at the AmsiScanBuffer level (before any provider sees the data).

---

### Section 14: ETW PROVIDERS

Event Tracing for Windows — the telemetry pipeline.

**What to look for:** Lists active ETW sessions. Microsoft-Windows-Threat-Intelligence is the key one — it feeds Defender's behavioural detection. The dark room's ETW bypass (DR1 on EtwEventWrite) blinds this entire pipeline.

---

### Section 15: WRITABLE SYSTEM DIRECTORIES

Directories under `C:\ProgramData`, `C:\Program Files`, etc. that the standard user can write to.

**What to look for:** Writable directories in system locations can be used for DLL planting, persistence, or staging. The count matters — more writable dirs = more attack surface.

---

### Section 16: INTERESTING FILES

Key world-writable locations and remote access tools.

**What to look for:**
- `C:\Windows\Temp` writable = canary files will work
- Remote access tools (TeamViewer, AnyDesk) = potential lateral movement
- TeamViewer registry details if present

---

### Section 17: SHARES & REMOTE ACCESS

Network shares, RDP status, WinRM configuration.

**What to look for:** Administrative shares (C$, ADMIN$) are default on all Windows machines. RDP disabled is typical for home machines. WinRM enabled = remote management possible.

---

### Section 18: PRIVESC QUICK CHECKS

Fast checks for common privilege escalation misconfigurations.

| Check | What It Means |
|-------|---------------|
| AlwaysInstallElevated | If set in both HKLM+HKCU, ANY .msi runs as SYSTEM. Instant privesc. |
| AppInit_DLLs | DLLs auto-loaded into every user-mode process. If writable, universal injection. |
| IFEO Debugger | Image File Execution Options — redirects any exe to a debugger. Persistence mechanism. |
| Print Monitor DLLs | Custom print monitors load as SYSTEM. Checks if all are in System32 (safe) or elsewhere (suspicious). |
| LSA Auth Packages | Authentication packages — if modified, credential interception. |
| WMI Event Subscriptions | Persistent WMI consumers — fileless persistence mechanism. |
| Token Privileges | Dangerous privileges (SeImpersonate, SeDebug, SeAssignPrimaryToken, etc.). Standard user should have none. |
| Named Pipes | Sample of non-standard named pipes — potential for pipe impersonation attacks. |

**What to look for:** All checks should show secure/clean on a standard Windows 11 machine. Any `[HIGH]` or `[CRITICAL]` marker = immediate escalation path that doesn't need VADER's vectors at all.

---

### Section 19: PHANTOM DLL HUNTING

**This is the crown jewel of the scanner.** It uses a pure PowerShell PE import parser to read the import tables of every SYSTEM service binary, cross-references against DLLs that actually exist on disk, and identifies phantom DLLs — imports that resolve to nothing.

#### How It Works

```
For each SYSTEM service:
  1. Read the service binary's PE headers
  2. Parse the Import Directory Table (normal imports)
  3. Parse the Delay-Load Import Directory (index 13)
  4. For each imported DLL:
     a. Is it in KnownDLLs registry? → Skip (always found)
     b. Does it exist in System32/SysWOW64/Windows dir? → Skip
     c. Does it exist in the application's own directory? → Skip
     d. None of the above? → PHANTOM
  5. For each phantom DLL:
     a. Is there a user-writable PATH directory? → PLANTABLE
```

#### Key Concepts

- **KnownDLLs**: Registry key (`HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs`) listing DLLs that Windows pre-maps. These are always found immediately and can't be hijacked via PATH.
- **Normal imports**: DLLs listed in the PE Import Directory Table (data directory index 1). Loaded at process start.
- **Delay-load imports**: DLLs in the Delay-Load Import Directory (data directory index 13). Loaded on first function call. **Critical: osppc.dll is a delay-load import — a normal-only parser would miss it entirely.**
- **Phantom**: A DLL in the import table that doesn't exist anywhere on disk. When the loader searches for it, it falls through to PATH directories.
- **Plantable**: A phantom DLL where at least one user-writable directory exists in the machine PATH. Plant your DLL there, and the SYSTEM service loads it as SYSTEM.

#### Reading the Output

```
[CRITICAL] PHANTOM_DLL -- Service 'ClickToRunSvc' (LocalSystem) DELAY-imports 'osppc.dll'
           -- NOT ON DISK -- PLANTABLE via writable PATH
```

This means:
1. ClickToRunSvc (Microsoft Office service) runs as LocalSystem
2. It delay-imports osppc.dll
3. osppc.dll doesn't exist on disk
4. There's a user-writable PATH directory where you can plant it
5. **Result: V7 GOLF is viable**

#### Known Phantoms (Validated on Test Machine)

| Phantom DLL | Service | Import Type | MSRC Potential |
|------------|---------|-------------|----------------|
| osppc.dll | ClickToRunSvc (Office) | Delay-load | HIGH — first-party Microsoft |
| osppcext.dll | ClickToRunSvc (Office) | Delay-load | HIGH — same service |
| CCGLaunchPad.dll | vmcompute (Hyper-V) | Delay-load | HIGH — first-party Microsoft |

#### The Writable PATH Fix

**Bug encountered during development:** The original `Test-Writable` function checked ACLs for group SIDs (BUILTIN\Users, Everyone, Authenticated Users, Interactive) but missed directories where the user's personal SID has FullControl. This caused `%USERPROFILE%\.local\bin` to report as NOT writable despite the user owning it.

**Fix applied:** `Test-WritablePractical` function attempts an actual file write as a fallback. If ACL check fails but a real file can be created and deleted, the directory is writable. This correctly identifies user-owned PATH directories.

---

### Section 20: VADER VECTOR ASSESSMENT

Automated scoring of available attack vectors based on all collected data.

#### Scoring

| Vector | Base Score Conditions | Bonus |
|--------|----------------------|-------|
| V4 DELTA | 80 if writable SYSTEM service found | — |
| V6 FOXTROT | 60 if writable PATH dir exists | — |
| V7 GOLF | 90 if Office installed + phantom DLL found + writable PATH | +5 if PATH dir confirmed writable |
| Dark Room | Always viable (standard user, no elevation needed) | — |

#### Output

The scanner recommends a primary vector (highest score) and fallback, plus the deploy command:

```
RECOMMENDED ATTACK PATH:
  PRIMARY:  V7 GOLF (score 95)
  FALLBACK: V4 DELTA (score 80)
  DARK ROOM: VIABLE

DEPLOY COMMAND:
  python deploy.py --pentest --skip-recon
```

---

## Summary Block

At the very end, the scanner outputs a summary:

```
================================================================
  RECON COMPLETE
  Output: recon\RECON_HOSTNAME_TIMESTAMP.log
  Hostname: LAPTOP-R32M8MLI
  Time: 2026-06-17 19:53:54
  Sections: 20
  Phantom DLLs: 3
  Recommended: V7 GOLF (score 95)
================================================================
```

---

## Interpreting Results for Vector Selection

### Decision Flow

```
Phantom DLLs found + writable PATH?
├── YES → V7 GOLF (score 90-95)
│         Best option. First-party MS service.
│         Auto-triggers on Office task schedule or app launch.
│
└── NO  → Writable SYSTEM service binary?
          ├── YES → V4 DELTA (score 80)
          │         Direct binary replacement.
          │         Triggers on service restart or reboot.
          │
          └── NO  → Writable PATH dir exists?
                    ├── YES → V6 FOXTROT (score 60)
                    │         Generic PATH plant.
                    │         Need to find a DLL gap manually.
                    │
                    └── NO  → No standard privesc available.
                              Dark room still works (AMSI+ETW bypass).
                              Look for non-standard escalation paths
                              in Section 18 quick checks.
```

### Profile-Based Selection (deploy.py Integration)

When using `deploy.py --pentest --profile radon`, the auto-selector applies profile constraints:

- **RADON profile**: Excludes V4 (no Wondershare), prefers V7 > V6. V7 GOLF gets +20 preference bonus.
- **LOCAL profile**: No exclusions, no preferences. Pure score-based selection.

---

## Running on a New Machine

### Prerequisites

- PowerShell 5.1+ (built into Windows 10/11)
- Standard user account (no admin required)
- No external tools needed (no dumpbin, no Visual Studio)

### Procedure

```powershell
# 1. Copy the scanner to the target
#    (USB, network share, git clone — whatever works)

# 2. Run it
powershell -ep bypass .\recon\vader_recon.ps1

# 3. Read the log
#    Output is in recon\RECON_<HOSTNAME>_<TIMESTAMP>.log

# 4. Check the summary at the bottom for:
#    - Phantom DLL count
#    - Recommended vector
#    - Deploy command
```

### What to Do With the Results

1. **Check Section 19** — Are there phantom DLLs? Are they plantable?
2. **Check Section 7** — Any writable service binaries?
3. **Check Section 20** — What does the auto-assessment recommend?
4. **Check Section 18** — Any quick-win misconfigs?
5. **Check Section 3** — Is Defender running with current sigs?

If V7 GOLF is recommended, proceed with:
```cmd
python deploy.py --pentest --skip-recon
```

---

## Technical Details: PE Import Parser

The scanner includes a ~100-line pure PowerShell PE parser (`Get-PEImports` function) that reads:

1. **DOS Header** — Reads `e_lfanew` at offset 0x3C (pointer to PE header)
2. **PE Signature** — Validates `PE\0\0` (0x00004550)
3. **COFF Header** — Number of sections, size of optional header
4. **Optional Header** — Magic number (0x10B = PE32, 0x20B = PE32+), data directory entries
5. **Data Directories** — Import table (index 1), delay-load table (index 13)
6. **Section Headers** — Maps RVA (Relative Virtual Address) to file offset for reading import names
7. **Import Directory Table** — Walks the linked list of IMAGE_IMPORT_DESCRIPTOR entries, reads DLL name strings

Returns a hashtable: `@{ Normal = @("dll1.dll", ...); DelayLoad = @("dll2.dll", ...) }`

This parser handles both PE32 and PE32+ binaries and reads delay-load imports — critical because the most valuable phantoms (osppc.dll, CCGLaunchPad.dll) are delay-loads that a normal-import-only parser would miss entirely.

---

## Known Limitations

1. **PE parser reads files, not running processes** — If a service loads additional DLLs dynamically (via LoadLibrary at runtime), the parser won't see those imports. Only statically-declared imports are checked.

2. **KnownDLLs bypass** — DLLs in the KnownDLLs registry are skipped because they can't be hijacked via PATH. If a DLL is in KnownDLLs but missing from disk, the scanner won't flag it (correctly — it's not exploitable).

3. **Access denied on some binaries** — Protected system binaries may fail to read. The parser silently skips these. The "Services scanned (unique binaries)" count in the output shows how many were successfully parsed vs total.

4. **Box-drawing characters** — Unicode box-drawing characters in Section 20 may display as `?` in some terminals (particularly Git Bash). The log file is UTF-8 encoded and preserves them correctly. This is cosmetic only.

5. **Service binary resolution** — Some services use `svchost.exe -k` with a DLL specified in registry parameters. The scanner resolves the actual service DLL where possible, but complex svchost configurations may be missed.

---

## Bugs Encountered During Development

### PATH Writable False Negative (Fixed)

**Problem:** `Test-Writable` checked ACLs for group SIDs (BUILTIN\Users S-1-5-32-545, Everyone S-1-1-0, etc.) but missed user-owned directories where the personal user SID has FullControl.

**Symptom:** `%USERPROFILE%\.local\bin` reported as NOT writable. Phantom DLLs showed "Plantable: False". V7 score was 90 instead of 95.

**Root cause:** Windows ACLs can grant access via personal SID (S-1-5-21-...) which isn't in the hardcoded group SID list.

**Fix:** Added `Test-WritablePractical` — attempts actual file creation as fallback. If the ACL check misses the grant but a real file write succeeds, the directory is correctly identified as writable.

### PowerShell Variable Reference Parse Error (Fixed)

**Problem:** `W "  $ctype: $cname"` — PowerShell interpreted `$ctype:` as a drive-qualified variable reference (like `env:PATH`).

**Symptom:** Parse error on scanner load.

**Fix:** Changed to `W "  ${ctype}: ${cname}"` using brace-delimited variable names.

### Unicode Display in Git Bash (Known, Cosmetic)

**Problem:** Box-drawing characters (┌─┐└─┘) in Section 20 display as `?` when output is piped through Git Bash.

**Impact:** Cosmetic only. Log file preserves characters correctly.

**Workaround:** Run from PowerShell directly, or read the log file instead of terminal output.

---

*VADER ROOTKIT — 22DIV / george wu*
*CSEC Tactical Cyber Operations*
