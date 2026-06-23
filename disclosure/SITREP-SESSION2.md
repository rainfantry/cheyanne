# SITREP — Session 2 (2026-06-15)

## Executive Summary

Expanded attack surface audit with no-reboot constraint. One major new finding discovered: **CrossDevice Virtual Camera DLL Replacement (#50)** — a Microsoft-signed COM DLL in a user-writable ProgramData directory. Also confirmed Steam service DLL sideloading (#51, known class). All other vectors tested clean.

## New Findings

### Finding #50: CrossDevice Virtual Camera DLL Replacement ⭐ PRIORITY
- `C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll`
- Microsoft-signed, ships on ALL Windows 11 (Phone Link / Cross Device feature)
- CLSID `{E9F83CF2-E0C0-4CA7-AF01-E90C70BEF496}` registered in HKLM InprocServer32
- Standard user has **Full Control** via CREATOR OWNER inheritance from ProgramData
- Only user-writable DLL in ALL of ProgramData (confirmed: scanned every DLL)
- **PENDING**: which process loads this COM object — if Frame Server (LocalService) or FrameServerMonitor (SYSTEM), this is LPE
- Even without SYSTEM loading: replacing a Microsoft-signed COM DLL used by camera apps is significant

### Finding #51: Steam Client Service DLL Sideloading (Known)
- Steam Client Service runs as SYSTEM, imports tier0_s.dll from user-writable Steam directory
- 92 user-writable DLLs in Steam tree total
- Known class (CVE-2019-14743 variants) — not pursuing as primary
- Documented for completeness

## Vectors Tested Clean (This Session)
- NVIDIA service failure recovery commands (bat files TrustedInstaller-locked)
- All auto-updater services: Adobe ARM, ASUS, Edge, Google, NVIDIA, Muse Hub, OneDrive
- Performance counter DLLs (43 libraries, all locked)
- WMI providers (3 in ProgramData — VS ones not writable, CrossDevice captured)
- ETW trace providers (964 publishers, none with user-writable resources)
- BITS notification commands (run as job owner, not SYSTEM)
- AppInit_DLLs (disabled, registry not writable)
- Group Policy script locations (not writable)
- Print Spooler driver directories (read-only)
- Point and Print restrictions (default/not configured)
- COM auto-elevation monikers (none in user-writable paths)
- Hosts file (read-only)
- WPAD/WinHTTP (running but no auto-detect configured)
- WER directories (writable but classic junction attacks patched)
- AppLocker (not configured)
- WDAC (8 active policies)
- All DLLs in ProgramData (only CrossDevice writable)
- All EXEs in ProgramData (none writable)
- All scripts in ProgramData (none writable)
- All DLLs in Program Files (46,830 scanned — 92 writable, all Steam except 1 MAGNET)

## George's Action Items When Home

### Step 1: Plant CrossDevice Canary (Before Reboot)
```cmd
REM Back up original
copy "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll" "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll.bak"

REM Copy existing canary DLL (already compiled from poc_path_hijack.c)
REM Or: compile new version with CROSSDEVICE tag
copy "C:\Users\gwu07\AppData\Local\Muse Hub\lib\SprintCSP.dll" "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll"
```

### Step 2: Verify Existing Canaries (Before Reboot)
```cmd
dir "C:\Users\gwu07\.local\bin\SprintCSP.dll"
dir "C:\Users\gwu07\.local\bin\cdpsgshims.dll"
dir "C:\Users\gwu07\AppData\Local\Muse Hub\lib\SprintCSP.dll"
dir "C:\Users\gwu07\AppData\Local\Muse Hub\lib\cdpsgshims.dll"
```

### Step 3: Reboot
Normal restart. Don't rush — let all services start fully.

### Step 4: Check Results (Immediately After Login)
```cmd
REM Check PATH hijack canaries
type C:\Windows\Temp\vader_path_hijack.log

REM If CrossDevice canary fired, check for camera-related or Frame Server entries
REM Look for: FrameServer, svchost, Camera, CrossDevice in the loaded_by field
```

### Step 5: Analyse Results
- **If canary shows SYSTEM user**: JACKPOT — that vector is confirmed LPE
- **If canary shows LocalService**: Still good — chain with SeImpersonatePrivilege for SYSTEM
- **If canary shows gwu07**: Same privilege, useful for persistence but not LPE
- **If no canary entry**: DLL wasn't loaded at boot — need to trigger camera enumeration

### Step 6: If No CrossDevice Canary at Boot
```powershell
# Open camera from Settings app or any camera app
# Then check canary log again
type C:\Windows\Temp\vader_path_hijack.log
```

### Step 7: Submit Reports
1. **#36 → MSRC** (Defender HWBP bypass) — report already written
2. **#50 → MSRC** (CrossDevice DLL) — if SYSTEM loading confirmed
3. **#49 → Muse Hub vendor** (PATH injection) — if canary confirms SYSTEM loading
4. **#49b → Astral** (uv PATH injection) — separate submission

### Step 8: Cleanup
```cmd
REM Restore CrossDevice DLL
copy /Y "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll.bak" "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll"

REM Remove canary DLLs (all 22 in PATH dirs)
REM List first, then delete
dir "C:\Users\gwu07\.local\bin\*.dll"
dir "C:\Users\gwu07\AppData\Local\Muse Hub\lib\*.dll"
```

### Step 9: Git Commit
```cmd
cd C:\Users\gwu07\Desktop\vader-rootkit
git add disclosure/
git commit -m "Add findings #48-51 and session 2 battle plan"
REM Hold push until rainfantry auth sorted
```

## Arsenal Summary

| # | Finding | Target | CWE | CVE% | Status |
|---|---------|--------|-----|------|--------|
| 36 | Defender HWBP Bypass | MSRC | 693 | 20-35% | PROVEN, report ready |
| 47 | Phantom DLL via PATH | MSRC | 426 | 10-15% | Documented |
| 48 | Drivers32 ACL | MSRC | 732 | 10-15% | Confirmed, no cross-boundary |
| 49 | Muse Hub PATH Injection | Muse Hub | 426 | 60-70% | PROVEN, pending reboot |
| 49b | uv PATH Injection | Astral | 426 | 50-60% | Confirmed |
| **50** | **CrossDevice DLL Replace** | **MSRC** | **732/426** | **35-50%** | **PROVEN replace, pending load test** |
| 51 | Steam Service DLL | Valve | 426 | 20-30% | Confirmed, known class |
