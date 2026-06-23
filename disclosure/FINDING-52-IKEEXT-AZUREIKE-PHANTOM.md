# Finding #52: IKEEXT azureike.dll Phantom DLL (DEAD — Hardened)

## Classification

| Field | Value |
|-------|-------|
| **CWE** | CWE-426: Untrusted Search Path Element |
| **Target** | Microsoft (IKEEXT service) |
| **Severity** | NONE — LoadLibraryExW hardened with LOAD_LIBRARY_SEARCH_SYSTEM32 |
| **CVE Probability** | 0% — Not exploitable |
| **Test Date** | 2026-06-15 |
| **Status** | DEAD END — Fully analysed, not exploitable |

## Finding

The IKEEXT service (IKE and AuthIP IPsec Keying Modules) running as **LocalSystem** contains code to load `azureike.dll` — a DLL that does NOT exist on standard Windows installations (phantom DLL). The code path is for Azure VPN gateway functionality.

**Despite being a phantom DLL loaded by a SYSTEM service, this is NOT exploitable** because Microsoft uses `LoadLibraryExW` with `LOAD_LIBRARY_SEARCH_SYSTEM32` (0x800), which restricts the DLL search to `%SystemRoot%\System32\` only. User-writable PATH directories are never searched.

## Analysis

### Code Flow (Static Binary Analysis of ikeext.dll)

```
ikeext.dll v10.0.26100.3915 (Windows 11 26200)

1. IkeGetGwSvcIkeDllName()
   - Reads HKLM\SYSTEM\CurrentControlSet\Services\IKEEXT\Parameters\GwSvcIkeDll
   - If registry value absent: uses hardcoded default "azureike.dll"
   - Writes result to caller-provided buffer

2. IkeGwSvcDelayLoad()
   - Calls LoadLibraryExW(dllName, NULL, 0x800)
   - 0x800 = LOAD_LIBRARY_SEARCH_SYSTEM32 → search restricted to System32
   - If load succeeds: GetProcAddress for CreateTunnel, CloseTunnel exports
   - If load fails: silently continues (phantom DLL doesn't exist)
```

### Binary Evidence

Reference to `azureike.dll` Unicode string at file offset `0x1378D0`:
```
0x9A3D8: 4C 8D 05 F1 D4 09 00  ; LEA r8, [rip+0x9D4F1] → "azureike.dll"
0x9A3DF: BA 04 01 00 00        ; MOV edx, 0x104          → MAX_PATH (buffer size)
0x9A3E4: 48 8B CB              ; MOV rcx, rbx            → output buffer
0x9A3E7: E8 94 BE FB FF        ; CALL IkeGetGwSvcIkeDllName (0x56280)
```

LoadLibraryExW call site for azureike.dll at file offset `0x9A627`:
```
0x9A619: 33 D2                 ; XOR edx, edx            → hFile = NULL
0x9A61B: 48 8D 4D E0           ; LEA rcx, [rbp-0x20]     → lpLibFileName (buffer)
0x9A61F: 41 B8 00 08 00 00     ; MOV r8d, 0x800          → LOAD_LIBRARY_SEARCH_SYSTEM32
0x9A625: 48 FF 15 83 0D 09 00  ; CALL [LoadLibraryExW]   → IAT slot at 0x12B3B0
```

### All LoadLibraryExW Call Sites in ikeext.dll

| Offset | DLL Loaded | dwFlags | Exploitable |
|--------|-----------|---------|-------------|
| 0x58554 | wlbsctrl.dll (hardcoded string) | 0x800 | NO — known, patched since Win 8.1 |
| 0x9A627 | azureike.dll (via buffer/registry) | 0x800 | NO — safe search flag |
| 0x9C8BB | Stack buffer (unknown, likely GwSvc related) | 0x800 | NO — safe search flag |

**ALL three LoadLibraryExW calls are hardened with LOAD_LIBRARY_SEARCH_SYSTEM32.**

### Registry Key Analysis

```
Key:   HKLM\SYSTEM\CurrentControlSet\Services\IKEEXT\Parameters
ACL:   NT AUTHORITY\SYSTEM:(F), Administrators:(F)
       Standard user: NO WRITE ACCESS
Value: GwSvcIkeDll does NOT exist (hardcoded default used)
```

Even if the registry value could be set to a full path (e.g., `C:\Users\evil.dll`), `LOAD_LIBRARY_SEARCH_SYSTEM32` would prevent loading from outside System32.

### System State

| Check | Result |
|-------|--------|
| azureike.dll exists in System32 | NO (phantom confirmed) |
| azureike.dll exists anywhere on disk | NO |
| GwSvcIkeDll registry value exists | NO |
| IKEEXT\Parameters writable by user | NO |
| IKEEXT service account | LocalSystem |
| LoadLibraryExW flags | 0x800 (LOAD_LIBRARY_SEARCH_SYSTEM32) |

### Prior Art

- **wlbsctrl.dll**: Same service, similar phantom DLL. Discovered 2012 (Frederic Bourla / High-Tech Bridge). Patched Win 8.1+ with LOAD_LIBRARY_SEARCH_SYSTEM32. Metasploit module `exploit/windows/local/ikeext_service` exists for pre-8.1.
- **azureike.dll**: **ZERO prior public research.** Not in any detection rules (Sigma, Elastic). Not in any CVE database. Undocumented Microsoft internal component for Azure VPN gateway IKE integration.
- **CVE-2026-33824**: Unrelated IKEEXT vulnerability (IKEv2 fragment reassembly double-free, wormable RCE). Patched April 2026. Different code path entirely.

### GwSvc Function Family (Extracted from Binary)

```
IkeGetGwSvcIkeDllName
IkeGwSvcDelayLoad
IkeUpdateGwSvcTunnelParams
IkeCreateGwSvcTunnelIkeV2
IkeCloseGwSvcTunnelIkeV2
IkeIndicateIncomingCallGwSvcIkeV2
IkeIndicateDriverInitiatedCallGwSvcIkeV2
IkeCallGwSvcCloseTunnel
IkeCallGwSvcCloseTunnelFail
IkeGwSvcCloseTunnel
```

These functions handle Azure VPN gateway tunnel operations. The delay-load triggers on tunnel creation/incoming call events — requires Azure VPN configuration that doesn't exist on standard consumer installations.

## Verdict

**NOT EXPLOITABLE.** The `LOAD_LIBRARY_SEARCH_SYSTEM32` flag prevents PATH-based DLL hijacking. The registry key is not writable by standard user. The phantom DLL is an interesting undocumented artefact but has no security impact.

### Why This Was Worth Investigating

1. Zero prior public research — nobody had documented azureike.dll
2. IKEEXT has historical phantom DLL vulnerabilities (wlbsctrl.dll)
3. Our system has 17 user-writable PATH directories (Muse Hub/uv injection)
4. IKEEXT runs as LocalSystem — any DLL load would be instant SYSTEM
5. The GwSvc code path is separate from the patched wlbsctrl.dll path — it was plausible that Microsoft only hardened the known vector

### What We Learned

Microsoft hardened ALL LoadLibraryExW calls in ikeext.dll uniformly, not just the known wlbsctrl.dll vector. This is proper defense-in-depth — new code paths (azureike.dll/GwSvc) were written with the same safe search flags as the patched old code paths.

## Detection Value

Even though not exploitable, azureike.dll is useful for defenders:

- **Not in any detection rule set** (Sigma, Elastic, CrowdStrike) — adding it improves phantom DLL monitoring
- If azureike.dll DOES appear on disk outside System32 → malicious activity indicator
- The GwSvc registry value `GwSvcIkeDll` appearing in IKEEXT\Parameters → suspicious (doesn't exist by default)
