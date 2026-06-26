# PHASE 6 — ANTI-FORENSICS CLEANUP

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY
## Callsign: JULIET | XOR Key: 0x93

---

## What This Tool Does

Post-operation cleanup. Removes evidence of VADER operations from the target machine: canary files, event logs, prefetch entries, file timestamps.

## Compile

```cmd
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
cl.exe forensics\vader_clean_annotated.c /Fe:forensics\vader_clean.exe /O1 /GS- /utf-8 /link advapi32.lib
```

## Usage

```cmd
:: Full cleanup (standard user — canaries only)
forensics\vader_clean.exe

:: Full cleanup (SYSTEM — canaries + logs + prefetch)
forensics\vader_clean.exe

:: Dry run — show what would be cleaned
forensics\vader_clean.exe --dry-run

:: Timestomp a specific file to match kernel32.dll timestamps
forensics\vader_clean.exe --timestomp C:\path\to\deployed.dll

:: Full cleanup + schedule self-delete on reboot
forensics\vader_clean.exe --self
```

## Cleanup Phases

| Phase | Operation | Requires |
|-------|-----------|----------|
| 1 | Delete canary files (all 6 vectors) | Standard user |
| 2 | Clear event logs (PowerShell, Sysmon, Security, Application) | SYSTEM/Admin |
| 3 | Delete prefetch files (DARK_ROOM, VADER_INJECT, VADER_STAGER, VADER_CLEAN) | SYSTEM/Admin |
| 4 | Timestomp files (match kernel32.dll timestamps) | File owner |
| 5 | Self-delete (MoveFileEx DELAY_UNTIL_REBOOT) | SYSTEM/Admin |

## MITRE ATT&CK

| Technique | ID | Implementation |
|-----------|-----|---------------|
| Indicator Removal | T1070 | Multi-phase evidence cleanup |
| Clear Windows Event Logs | T1070.001 | EvtClearLog via dynamically resolved wevtapi.dll |
| File Deletion | T1070.004 | Canary and prefetch file removal |
| Timestomp | T1070.006 | SetFileTime matching kernel32.dll reference |

## Files

```
forensics/
├── vader_clean_annotated.c    # Cleanup tool source (annotated)
├── vader_clean.exe            # Compiled binary (when built)
└── README.md                  # This file
```
