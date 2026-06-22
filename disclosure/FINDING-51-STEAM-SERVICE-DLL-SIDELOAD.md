# Finding #51: Steam Client Service DLL Sideloading (Known Class)

## Classification

| Field | Value |
|-------|-------|
| **CWE** | CWE-426: Untrusted Search Path Element |
| **Target** | Valve (Steam) |
| **Severity** | High — Standard user → SYSTEM via DLL replacement |
| **CVE Probability** | 20-30% — known vulnerability class, prior CVEs exist (CVE-2019-14743, CVE-2019-15316) |
| **Test Date** | 2026-06-15 |
| **Status** | CONFIRMED but likely known/disputed by vendor |

## Finding

Steam Client Service (`steamservice.exe`) runs as **LocalSystem** from `C:\Program Files (x86)\Common Files\Steam\` (TrustedInstaller-locked). However, it imports `tier0_s.dll` which only exists in `C:\Program Files (x86)\Steam\` — a directory writable by standard user.

### DLL Import Analysis

| DLL | Application Dir (Locked) | Steam Root/Bin (Writable) | Exploitable |
|-----|--------------------------|---------------------------|-------------|
| SteamService.dll | YES (Common Files) | YES (Steam\bin) | NO — locked copy loads first |
| crashhandler.dll | YES (Common Files) | YES (Steam root) | NO — locked copy loads first |
| cpuidsdk.dll | YES (Common Files) | YES (Steam\bin) | NO — locked copy loads first |
| **tier0_s.dll** | **NO** | **YES (Steam root)** | **YES — only copy is writable** |

### 92 User-Writable DLLs in Steam Directory

Full scan of 46,830 DLLs across both Program Files directories found 92 user-writable DLLs. 91 are in the Steam directory tree; 1 is MAGNET Office.

### Prior Art

This is a known class of Steam vulnerability:
- CVE-2019-14743: Steam privilege escalation via writable service directory
- CVE-2019-15316: Steam Client Service LPE
- Valve has disputed some variants as "by design" since users already run arbitrary code (games) via Steam

### Verdict

**Not pursuing as primary target.** Known class, disputed by vendor, prior CVEs cover the pattern. Document for completeness. If Valve has patched the specific tier0_s.dll loading (e.g., via manifest or explicit path), re-check.

## Proof of Concept

```powershell
# tier0_s.dll is writable and loaded by SYSTEM service
$s = [System.IO.File]::Open(
    "C:\Program Files (x86)\Steam\tier0_s.dll",
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::ReadWrite)
$s.Close()  # Confirmed writable

# Replace tier0_s.dll → SYSTEM execution on next service start
```
