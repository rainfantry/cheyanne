# RECON -- Target Reconnaissance Package

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY

---

## Purpose

Self-contained reconnaissance package for target profiling. Runs as
standard user, no elevation needed. Outputs an organised log to the
same directory as the script. Designed for USB drop or local execution
on targets where remote access is unavailable.

## Usage

```
powershell -ExecutionPolicy Bypass -File vader_recon.ps1
powershell -ep bypass .\vader_recon.ps1
```

Output: `RECON_<hostname>_<YYYYMMDD_HHMMSS>.log` in script directory.

## Sections (17)

| # | Section | What It Collects |
|---|---------|-----------------|
| 1 | System Identity | OS, build, CPU, RAM, BIOS, hotfixes |
| 2 | User & Privilege Context | Username, SID, groups, token privileges, local accounts |
| 3 | UAC & Security Config | ConsentPromptBehavior, EnableLUA, secure desktop |
| 4 | Defender / AV Status | RTP, behavior monitor, tamper protection, engine version |
| 5 | VBS / HVCI / Secure Boot | Virtualization-based security, credential guard |
| 6 | Network State | Adapters, listening ports, firewall profiles, ARP table |
| 7 | System Services Privesc Hunt | All SYSTEM/LocalService services, writable binary/dir detection |
| 8 | Service Binary ACLs | Detailed ACL dump on high-value service binaries |
| 9 | Scheduled Tasks | Tasks running as SYSTEM, action paths, writable checks |
| 10 | PATH Variable | Writable PATH entries for DLL/EXE planting |
| 11 | KnownDLLs | Registry enumeration of protected DLLs |
| 12 | Installed Software | All installed programs with versions |
| 13 | Running Processes | Active processes with paths and session IDs |
| 14 | Autorun / Persistence | Registry Run keys, startup folders |
| 15 | Writable ProgramData | Directories writable by standard user |
| 16 | Interesting Files | RAT indicators (TeamViewer, AnyDesk, etc.), cloud sync, dev tools |
| 17 | Shares & Remote Access | Network shares, RDP status, WinRM status |

## Findings Severity

Findings are tagged inline:

- `[CRITICAL]` -- Immediate privesc vector (writable SYSTEM service binary)
- `[HIGH]` -- Strong lead (unquoted service path, service in user profile, RAT running)
- `[MEDIUM]` -- Noteworthy condition (RTP active, writable PATH entry)

## Writable Detection

Uses SID-based ACL analysis checking for write permissions granted to:
- `S-1-5-32-545` (BUILTIN\Users)
- `S-1-1-0` (Everyone)
- `S-1-5-11` (Authenticated Users)
- `S-1-5-4` (INTERACTIVE)

Checks both FileSystemRights bitmask (`Write`, `Modify`, `FullControl`)
and generic access masks (`GENERIC_WRITE`).

## Files

```
recon/
+-- vader_recon.ps1     # The recon script
+-- README.md           # This file
```

Output logs are gitignored (`*.log`).

## Tested Output

On dev machine (gwu07): 1169 lines, 5 findings flagged:
- 1 CRITICAL (NativePushService writable binary -- known CWE-732)
- 2 HIGH (service in user profile, pgbouncer unquoted path)
- 1 HIGH (TeamViewer running)
- 1 MEDIUM (RTP active)

## Operational Notes

1. Script runs ~30-60 seconds depending on service count
2. No network connections made -- passive local recon only
3. No files modified on target -- read-only except writing its own log
4. No elevation attempted -- stays within standard user permissions
5. Log file contains hostname and timestamp for multi-target tracking
6. Designed for offline analysis -- copy log back for review
