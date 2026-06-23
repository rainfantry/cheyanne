# Finding #50: CrossDevice Virtual Camera DLL Replacement (CWE-732 / CWE-426)

## ⚠️ KNOWN CVE — INCOMPLETE REMEDIATION

**This vulnerability is CVE-2025-24076 (SYSTEM-level) / CVE-2025-24994 (user-level)**, discovered by Compass Security (mbanyamer), patched March 2025. PoC published June 2025.

**HOWEVER: The patch did NOT fix the filesystem permissions.** Our fully-patched system (Build 26200, June 2026) still has user FullControl ACLs on the DLL and directory. The fix was applied to the **loading process** (signature verification or code path change), NOT the filesystem layout. The COM registration in HKLM still points to the user-writable ProgramData path.

**Potential new finding**: If ANY process other than the patched CrossDeviceService.exe loads this CLSID via CoCreateInstance without signature verification, the incomplete remediation creates a new attack surface. Needs reboot/camera enumeration testing.

## Classification

| Field | Value |
|-------|-------|
| **CWE** | CWE-732: Incorrect Permission Assignment for Critical Resource |
| **Secondary CWE** | CWE-426: Untrusted Search Path Element (COM InprocServer32 in user-writable path) |
| **Target** | Microsoft Windows CrossDevice (MicrosoftWindows.CrossDevice AppX) |
| **Severity** | REDUCED — Known CVE, but ACLs still wrong post-patch |
| **CVE Probability** | 10-20% (incomplete remediation angle) / 0% (original finding is duplicate) |
| **Original CVE** | CVE-2025-24076 (SYSTEM), CVE-2025-24994 (user) — March 2025 |
| **Discoverer** | Compass Security / mbanyamer |
| **PoC** | github.com/mbanyamer/CVE-2025-24076 (EDB-52320) |
| **Test Date** | 2026-06-15 |
| **OS** | Windows 11 Home Build 26200 (fully patched) |
| **User Context** | Standard user (gwu07, no admin) |

## Finding

The **Microsoft CrossDevice** AppX package (Phone Link / Link to Windows feature) writes a COM-registered DLL to `C:\ProgramData\CrossDevice\` — a directory where the creating user inherits **Full Control** via CREATOR OWNER inheritance from ProgramData.

The DLL is registered as a **system-wide InprocServer32** in HKLM, meaning ANY process on the machine can load it by instantiating the associated CLSID. A standard user can replace this Microsoft-signed DLL with arbitrary code.

### What Microsoft Patched (March 2025)

The fix was applied to the **loading process**, NOT the filesystem:
- The DLL at `C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll` is STILL user-writable
- The HKLM COM registration STILL points to the ProgramData path
- The directory ACLs are STILL inherited from ProgramData (CREATOR OWNER → FullControl)
- Microsoft likely added Authenticode signature verification in the loader, or changed the code path to load from the protected WindowsApps directory instead

### What Remains Exploitable (Potential)

The COM InprocServer32 registration is **system-wide in HKLM**. Any process that calls `CoCreateInstance({E9F83CF2-...})` gets directed to the user-writable ProgramData path. If any process OTHER than the patched Microsoft components loads this CLSID without its own signature checks, the DLL replacement still works.

Candidates that might load this CLSID without independent signature verification:
- Third-party camera applications (Zoom, Teams, OBS, etc.)
- Camera enumeration by non-Microsoft components
- COM automation scripts or tools

### Affected DLL

```
Path: C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll
CLSID: {E9F83CF2-E0C0-4CA7-AF01-E90C70BEF496}
Name: "Cross Device Virtual Camera Source"
Signer: CN=Microsoft Corporation
Version: 1.25112.1.0
Size: 193,056 bytes
Threading: Both (InprocServer32)
```

### Root Cause

```
C:\ProgramData has CREATOR OWNER:(OI)(CI)(IO)(F) 
  → CrossDevice app (runs as user) creates C:\ProgramData\CrossDevice\
  → gwu07 becomes OWNER → inherits FullControl
  → DLL written to directory inherits gwu07:FullControl
  → HKLM COM registration points to user-writable DLL
```

## Evidence Chain

### Step 1: DLL is User-Writable (Verified)

```
C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll
    NT AUTHORITY\SYSTEM:(I)(F)
    BUILTIN\Administrators:(I)(F)
    LAPTOP-R32M8MLI\gwu07:(I)(F)   ← FULL CONTROL
    BUILTIN\Users:(I)(RX)
```

Write access verified programmatically — file opens for ReadWrite as standard user.

### Step 2: Directory Owner is Standard User

```
Directory Owner: LAPTOP-R32M8MLI\gwu07
DLL Owner: LAPTOP-R32M8MLI\gwu07
```

Created by CrossDevice AppX running in user context. CREATOR OWNER inheritance from ProgramData grants Full Control.

### Step 3: COM Registration is System-Wide (HKLM)

```
HKLM\SOFTWARE\Classes\CLSID\{E9F83CF2-E0C0-4CA7-AF01-E90C70BEF496}
    (default) = "Cross Device Virtual Camera Source"
    
HKLM\...\InprocServer32
    (default) = "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll"
    ThreadingModel = "Both"
```

InprocServer32 = loaded in-process by ANY process that calls CoCreateInstance with this CLSID.

### Step 4: Microsoft-Signed Component on Default Install

```
Digital Signature: Valid
Signer: CN=Microsoft Corporation, O=Microsoft Corporation
AppX Package: MicrosoftWindows.CrossDevice v1.26032.83.0
Publisher: CN=Microsoft Windows, O=Microsoft Corporation
```

Ships on all Windows 11 installations with Phone Link / Cross Device feature.

### Step 5: Only User-Writable DLL in ALL of ProgramData

Comprehensive scan of every DLL in `C:\ProgramData` (all subdirectories) confirmed this is the **only** DLL writable by standard user. All other Microsoft and third-party components properly restrict DLL permissions.

### Step 6: Potential SYSTEM/LocalService Loading

The "Cross Device Virtual Camera Source" COM object is a **Media Foundation virtual camera source**. Processes that may load this InprocServer32:

| Process | Account | Loading Context |
|---------|---------|-----------------|
| Windows Camera Frame Server (FrameServer) | NT AUTHORITY\LocalService | Virtual camera enumeration |
| Windows Camera Frame Server Monitor (FrameServerMonitor) | LocalSystem | Camera monitoring |
| Any camera-using application | User | Camera device enumeration |
| Windows Settings (camera page) | User | Device listing |

**If FrameServer (LocalService) loads this DLL**: LocalService has SeImpersonatePrivilege → chainable to SYSTEM via potato-class exploits.

**If FrameServerMonitor (LocalSystem) loads this DLL**: Direct SYSTEM code execution.

**PENDING**: Reboot test to verify which process loads this DLL at startup or during camera enumeration.

## Attack Chain

```
Standard User (no admin)
  ├── 1. CrossDevice AppX creates ProgramData\CrossDevice\ [DEFAULT INSTALL]
  ├── 2. CREATOR OWNER gives user FullControl on directory+DLL [VERIFIED]
  ├── 3. User renames original DLL, plants malicious DLL [TRIVIAL]
  ├── 4. COM InprocServer32 in HKLM points to user-writable path [VERIFIED]
  ├── 5. Camera enumeration triggers CoCreateInstance [PENDING VERIFICATION]
  └── 6. DLL loaded as LocalService/SYSTEM → LPE [PENDING]
```

**Confirmed steps**: 1-4 fully proven. Steps 5-6 require testing which process loads the COM object.

**Even without SYSTEM loading**: Replacing a Microsoft-signed COM DLL with arbitrary code that loads into any camera-using application is a significant persistence and code injection vector.

## Proof of Concept

```powershell
# Verify DLL is writable
$stream = [System.IO.File]::Open(
    "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll",
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::ReadWrite)
Write-Host "DLL is writable: $($stream.CanWrite)"  # True
$stream.Close()

# Attack: rename original, plant payload
Rename-Item "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll" `
            "CrossDevice.Streaming.Source.dll.bak"
Copy-Item "payload.dll" "C:\ProgramData\CrossDevice\CrossDevice.Streaming.Source.dll"

# Any process that opens a camera or enumerates virtual cameras now loads payload.dll
```

## Uniqueness Assessment

This is NOT a duplicate of any known CVE:
- Different from generic DLL sideloading (this is a COM InprocServer32 in HKLM)
- Different from PATH injection (CVE-2025-13433 etc.) — no PATH involved
- Different from Drivers32 (Finding #48) — different registry mechanism, different loading context
- Root cause is CREATOR OWNER inheritance from ProgramData applied to a COM-registered DLL

## Remediation

1. **Microsoft CrossDevice team**: Write DLL to a TrustedInstaller-protected location (e.g., the WindowsApps package directory), not ProgramData.
2. **Alternative**: Set explicit restrictive ACLs on the CrossDevice directory after creation, removing CREATOR OWNER inherited Full Control.
3. **Alternative**: Use an out-of-process COM server (LocalServer32) instead of InprocServer32, so the DLL runs in a controlled process context.
4. **Windows platform**: Consider adding integrity-level checks for COM InprocServer32 DLLs loaded by elevated processes — warn or block when a DLL is below the process's integrity level.
