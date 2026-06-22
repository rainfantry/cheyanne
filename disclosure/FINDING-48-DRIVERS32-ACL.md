# Finding #48: HKLM Drivers32 User-Writable ACL (Persistence Vector)

## Classification

| Field | Value |
|-------|-------|
| **CWE** | CWE-732: Incorrect Permission Assignment for Critical Resource |
| **Target** | HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Drivers32 |
| **Severity** | Low-Medium (persistence, not privilege escalation) |
| **CVE Probability** | 10-15% — known persistence location, ACL anomaly may be "by design" |
| **Test Date** | 2026-06-15 |
| **OS** | Windows 11 Home Build 26200 |
| **User Context** | Standard user (gwu07, no admin) |

## Finding

The registry key `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Drivers32` has an **explicit, non-inherited ACE** granting:

```
NT AUTHORITY\Authenticated Users: SetValue, CreateSubKey, ReadKey
InheritanceFlags: ContainerInherit, ObjectInherit
IsInherited: False
```

This means **any authenticated user** (including standard users) can:
- Create new values (register new multimedia drivers)
- Modify existing values (redirect system audio/video codec loading)
- Create subkeys

### Anomaly Evidence

Sibling keys under `HKLM\...\CurrentVersion` do NOT have this ACE:

| Key | User-Writable |
|-----|--------------|
| **Drivers32** | **YES (SetValue, CreateSubKey)** |
| AppCompatFlags | NO |
| Winlogon | NO |
| ProfileList | NO |
| Fonts | NO |
| Image File Execution Options | NO |
| Windows | NO |

The ACE is set **directly on the key** (IsInherited: False), not inherited from a parent.

## Impact Assessment

### What IS exploitable
- Standard user can register malicious multimedia codecs system-wide
- Any process that plays audio/video will load the attacker's DLL
- Effective for **persistence** and **same-privilege injection** (e.g., into other standard-user processes)
- Survives reboot — HKLM is persistent

### What is NOT exploitable (no cross-boundary)
- No SYSTEM process currently loads winmm.dll or Drivers32 codecs
- AudioSrv and AudioEndpointBuilder (LocalService/LocalSystem) do NOT load Drivers32 entries
- SYSTEM account has no sound scheme configured (HKU\.DEFAULT\AppEvents absent)
- Cannot be used for standard user → SYSTEM privilege escalation

### Confirmed loaded by
- explorer.exe (user-mode)
- Steam, python, WindowsTerminal (user-mode applications)
- Any process calling PlaySound, waveOutOpen, mciSendCommand

## Proof of Concept

```powershell
# Standard user can create/modify values in HKLM Drivers32
$key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
    "SOFTWARE\Microsoft\Windows NT\CurrentVersion\Drivers32", $true)

# Create new codec entry
$key.SetValue("vidc.vader", "C:\Users\gwu07\malicious_codec.dll")

# Modify existing wavemapper (affects ALL audio playback system-wide)
$key.SetValue("wavemapper", "C:\Users\gwu07\proxy_msacm32.dll")

$key.Close()
```

## Recommendation

Microsoft should restrict the Drivers32 ACL to match sibling keys:
- Remove `Authenticated Users: SetValue, CreateSubKey`
- Retain `BUILTIN\Users: ReadKey` for codec enumeration
- Require admin/TrustedInstaller for modifications
