# VADER Research: bindflt.sys & wcifs.sys — Un-Researched Attack Surface Analysis

## Classification: INTERNAL RESEARCH — DO NOT PUBLISH

**Date**: 2026-06-15
**Researcher**: VADER (George Wu)
**Target System**: LAPTOP-R32M8MLI (Windows 11 Home Build 26200)
**Objective**: Map the un-researched attack surface of Windows container filesystem drivers for original CVE discovery

---

## Executive Summary

bindflt.sys and wcifs.sys are Windows container filesystem drivers with **ZERO** public CVEs for privilege escalation. Both import the same vulnerability-class APIs (token impersonation + I/O redirection) that make cldflt.sys exploitable by MiniPlasma. Both have communication ports (`\BindFltPort`, `\WcifsPort`) that exist but deny standard user access. The key finding: **AppXSvc (SYSTEM) uses bindflt via `BfSetupFilterEx`**, and standard users can trigger AppX operations — creating an indirect SYSTEM→bindflt execution path.

---

## 1. bindflt.sys — Bind Filter Driver

### Driver Profile

| Property | Value |
|----------|-------|
| File | `C:\Windows\System32\drivers\bindflt.sys` |
| Size | 198,112 bytes |
| Version | 10.0.26100.8655 |
| Updated | June 10, 2026 |
| Altitude | 409800 (FSFilter Top — highest minifilter) |
| Start | 2 (Auto/Boot) |
| Group | FSFilter Top |
| Port | `\BindFltPort` (EXISTS, ACCESS_DENIED for standard user) |
| Public CVEs | **ZERO** |
| Named Researchers | **NONE** |

### Function

Binds filesystem namespaces to different locations and hides the remapping from the user. Used by:
- Windows Containers (Docker, Hyper-V containers)
- WSL2 (Linux filesystem sharing)
- Windows Sandbox
- MSIX package VFS (Virtual File System)
- AppX deployment (package activation filesystem isolation)

### Source File Map (from PDB paths)

```
onecore\base\fs\wci\bindflt\filter\
├── bindflt.c      — Main driver entry, registration
├── mapping.c      — Bind mount mapping management
├── create.c       — IRP_MJ_CREATE handler (file open/create)
├── namesup.c      — Name support (path resolution/normalization)
├── fsctrl.c       — FSCTL/IOCTL dispatch (communication port messages)
├── message.c      — Filter port message handling
├── context.c      — Instance/stream/stream-handle contexts
├── dirctrl.c      — Directory control (enumeration)
├── sfo.c          — Stream file object handling
├── utils.c        — Utility functions
├── telemetry.c    — ETW telemetry
```

### User-Mode API (bindfltapi.dll — 13 exports)

| Export | Purpose |
|--------|---------|
| `CreateBindLink` | Public Win32 API — create bind link (ACCESS_DENIED for std user) |
| `RemoveBindLink` | Public Win32 API — remove bind link (ACCESS_DENIED for std user) |
| `BfSetupFilter` | Low-level — set up bind filter via port message |
| `BfSetupFilterEx` | Extended version with additional parameters |
| `BfSetupFilterBatched` | Batched bind mount setup |
| `BfAttachFilter` | Attach filter to volume |
| `BfConfigureFilter` | Configure filter settings |
| `BfGenerateBatchedConfig` | Generate batch configuration |
| `BfGenerateMappingConfiguration` | Generate mapping config |
| `BfGetMappings` | Enumerate current bind mounts |
| `BfRemoveMapping` | Remove a single mapping |
| `BfRemoveMappingEx` | Extended remove |
| `BfTrackWritesFromSilo` | Track writes from silo/container context |

### Security-Critical Kernel Imports

**Token Impersonation** (same class as cldflt.sys vulnerability):
- `SeImpersonateClientEx` — impersonate client token
- `PsImpersonateClient` — process-level impersonation
- `PsRevertToSelf` — (in prior analysis, confirmed present)
- `PsReferenceImpersonationToken` / `PsDereferenceImpersonationToken`
- `SeCreateClientSecurityFromSubjectContext`
- `SeCaptureSubjectContext` / `SeReleaseSubjectContext`
- `SeQueryAuthenticationIdToken` / `SeQueryInformationToken`

**I/O Redirection** (same class as cldflt.sys):
- `FltAdjustDeviceStackSizeForIoRedirection`
- `IoReplaceFileObjectName` — renames file object mid-operation
- `FltCreateFileEx2` — creates files on behalf of callers

**Communication Port**:
- `FltCreateCommunicationPort` — creates `\BindFltPort`
- `FltBuildDefaultSecurityDescriptor` — builds port SD
- `FltFreeSecurityDescriptor`

**Silo/Container Context**:
- `PsGetSiloContext` / `PsInsertSiloContext` / `PsDereferenceSiloContext`
- `PsGetCurrentSilo` / `PsGetHostSilo` / `PsGetJobSilo` / `PsGetParentSilo`
- `PsAllocSiloContextSlot` / `PsFreeSiloContextSlot`
- `PsCreateSiloContext` / `PsIsHostSilo`
- `IoGetSilo`

**Package Identity**:
- `RtlQueryPackageIdentity` — queries AppX/MSIX package identity

### Access Control Testing Results

| Test | Result |
|------|--------|
| `\\.\BindFlt` (CreateFile) | ERROR_FILE_NOT_FOUND (2) |
| `\\.\BindFltPort` (CreateFile) | ERROR_FILE_NOT_FOUND (2) |
| `\BindFltPort` (FilterConnectCommunicationPort) | **ACCESS_DENIED** (port EXISTS) |
| `CreateBindLink` (user paths) | ACCESS_DENIED |
| `CreateBindLink` (READ_ONLY flag) | ACCESS_DENIED |
| `BfSetupFilter` (NULL job handle) | ACCESS_DENIED |
| `BfGetMappings` | AccessViolationException (sig mismatch or access denied) |
| `CreateBindLink` (system target path) | ACCESS_DENIED |

### Indirect Access Paths (Standard User → SYSTEM → bindflt)

**Path 1: AppXSvc (HIGHEST PRIORITY)**
```
Standard User
  └─ Add-AppxPackage / PackageManager.AddPackageAsync()
      └─ AppXSvc (svchost.exe, SYSTEM, wsappx group)
          └─ appxdeploymentserver.dll
              └─ BfSetupFilterEx() — sets up per-package bind mounts
              └─ BfRemoveMappingEx() — removes bind mounts
              └─ bindflt.sys (kernel) processes the request
```

**Path 2: container.dll (Containers/Docker/WSL)**
```
Container Service (SYSTEM)
  └─ container.dll
      └─ WcSetupFilesystemNamespace()
          └─ BfSetupFilter() / BfSetupFilterBatched() / BfAttachFilter()
              └─ bindflt.sys (kernel) processes the request
```

**Path 3: MSIX VFS (Virtual File System)**
```
Package Activation (SYSTEM)
  └─ AppXSvc processes package with VFS folder structure
      └─ Package\VFS\ProgramFilesX64\ → C:\Program Files\
      └─ Package\VFS\SystemX86\ → C:\Windows\SysWOW64\
      └─ Package\VFS\Windows\ → C:\Windows\
      └─ These are per-process (silo-scoped) bind mounts via bindflt
```

---

## 2. wcifs.sys — Windows Container Isolation File System

### Driver Profile

| Property | Value |
|----------|-------|
| File | `C:\Windows\System32\drivers\wcifs.sys` |
| Size | 255,448 bytes |
| Version | 10.0.26100.8521 |
| Updated | May 27, 2026 |
| Altitude | 189900 (FSFilter Virtualization) |
| Start | 2 (Auto/Boot) |
| Group | FSFilter Virtualization |
| Port | `\WcifsPort` (EXISTS, ACCESS_DENIED for standard user) |
| Public LPE CVEs | **ZERO** |
| Only Research | Daniel Avinoam (2023) — AV bypass via altitude position, NOT LPE |

### Source File Map

```
onecore\base\fs\wci\wcifs\
├── wcifs.c        — Main driver
├── create.c       — File create handling
├── expansion.c    — Layer expansion
├── context.c      — Context management
├── fsctrl.c       — FSCTL/IOCTL dispatch
├── message.c      — Port message handling
├── dir.c          — Directory operations
├── fileinfo.c     — File information queries
├── readwrite.c    — Read/write operations
├── tombstone.c    — Tombstone handling (deleted layer files)
├── utils.c        — Utilities
├── telemetry.c    — ETW telemetry
```

### Key Imports (Security-Relevant)

Same I/O redirection pattern as bindflt:
- `FltAdjustDeviceStackSizeForIoRedirection`
- `FltIsIoRedirectionAllowed`
- `IoReplaceFileObjectName`
- `FltCreateFileEx` / `FltCreateFileEx2`
- `FltCreateCommunicationPort`
- `FltBuildDefaultSecurityDescriptor`
- `ObReferenceObjectByHandle`
- `FsRtlChangeBackingFileObject`
- `FsRtlValidateReparsePointBuffer`

Container/silo imports:
- `PsCreateSiloContext` / `PsGetSiloContext` (confirmed via ASCII strings)

---

## 3. CVE Research Intelligence

### Public CVE History (from exhaustive search)

| Driver | CVEs (2024-2026) | Classes | Status |
|--------|-------------------|---------|--------|
| cldflt.sys | 5+ (CVE-2025-55680, -62221, -62454, CVE-2026-27926, CVE-2026-33825/MiniPlasma) | TOCTOU, UAF, integer overflow, race, incomplete patch | SATURATED |
| cimfs.sys | 1 (CVE-2024-26170) | OOB read → arb R/W (missing FILE_DEVICE_SECURE_OPEN) | Container interaction unexplored |
| bindflt.sys | **0** | N/A | **COMPLETELY UN-RESEARCHED** |
| wcifs.sys | **0 LPE** (1 AV bypass paper) | N/A for LPE | **LARGELY UN-RESEARCHED** |
| luafv.sys | 0 (2024-2026), 3 in 2019 | Delayed virtualization, handle dup, cache poison | Interaction with container stack unexplored |

### Key Implication

Every public CVE in the container filesystem space targets cldflt.sys. Five distinct vulnerability classes, four research groups. **bindflt.sys has the same API surface, same import pattern, same vulnerability indicators, and ZERO scrutiny.** This is the strongest lead for an original CVE.

---

## 4. Vulnerability Hypotheses

### Hypothesis A: AppXSvc BfSetupFilterEx TOCTOU (HIGHEST PRIORITY)

**Theory**: When AppXSvc calls `BfSetupFilterEx` during MSIX package deployment, the path parameters derive from the package content (user-controlled MSIX). If bindflt.sys validates the path and then uses it non-atomically, a junction/symlink swap between validation and use redirects the bind mount.

**Attack flow**:
1. Craft MSIX package with specific VFS directory structure
2. Plant junction in VFS path pointing to benign location
3. Trigger `Add-AppxPackage` → AppXSvc (SYSTEM) → `BfSetupFilterEx`
4. Race: swap junction target to system directory between validation and bind mount creation
5. Result: bind mount overlays system directory with user-controlled content
6. SYSTEM process reads "system" file but gets attacker content

**Supporting evidence**:
- `BfSetupFilterEx` is called by appxdeploymentserver.dll (confirmed)
- bindflt.sys imports `IoReplaceFileObjectName` (can rename file objects mid-op)
- bindflt.sys `namesup.c` handles path normalization (potential validation point)
- bindflt.sys `create.c` handles file creates (potential use point)
- TOCTOU between namesup validation → create/mapping use is the target window

**What's needed**: Disassembly of `BfSetupFilterEx` → trace into bindflt.sys `message.c` → identify validation/use gap in `mapping.c`/`create.c`.

### Hypothesis B: Cross-Altitude TOCTOU (luafv → wcifs → bindflt)

**Theory**: Three minifilters at different altitudes process the same I/O requests. Lower-altitude filter makes an access decision, higher-altitude filter modifies the path AFTER the decision.

```
Altitude Stack:
  409800  bindflt.sys  (bind mounts — can redirect paths)
  189900  wcifs.sys    (container isolation — ghost files)
  135000  luafv.sys    (User Access Control virtualization)
```

If luafv grants access at altitude 135000, then bindflt at altitude 409800 redirects the file object to a different target... the granted access applies to a different file.

**Supporting evidence**:
- Both bindflt and wcifs import `FltAdjustDeviceStackSizeForIoRedirection`
- Both import `IoReplaceFileObjectName`
- luafv makes delayed virtualization decisions that can be invalidated

**Limitation**: Requires active bind mounts or container state. On a stock Win11 Home without Docker/WSL, this path is dormant.

### Hypothesis C: Port Security Descriptor Misconfiguration

**Theory**: `FltBuildDefaultSecurityDescriptor` builds a restrictive SD, but the driver might modify it or apply a less restrictive one for specific scenarios (e.g., silo contexts, package identity contexts).

**What to check**: Disassemble the port creation code in `bindflt.c` — does it ever create the port with a non-default SD? Does `RtlQueryPackageIdentity` influence access decisions?

### Hypothesis D: BfGetMappings Information Leak

**Theory**: `BfGetMappings` crashed with AccessViolationException when called with NULL job handle. This could indicate a NULL pointer dereference in the kernel path. If the driver doesn't properly validate the job handle before dereferencing...

**Note**: The crash was in user-mode P/Invoke, not necessarily in the kernel. But the function signature needs validation against the actual API.

---

## 5. Recommended Research Path

### Phase 1: Static Analysis (IDA/Ghidra)

1. Load `bindflt.sys` into IDA/Ghidra
2. Map the communication port message handler (`message.c` code)
3. Identify the `BfSetupFilterEx` kernel handler — trace parameter validation
4. Look for TOCTOU between path validation (`namesup.c`) and path use (`mapping.c`, `create.c`)
5. Check `FltBuildDefaultSecurityDescriptor` call — is the SD ever weakened?
6. Check `IoReplaceFileObjectName` usage — when does bindflt rename file objects?

### Phase 2: Dynamic Analysis (AppXSvc Triggering)

1. Create a minimal MSIX package with VFS directory structure
2. Use Process Monitor to trace AppXSvc → bindflt calls during package deployment
3. Identify the exact paths passed to `BfSetupFilterEx`
4. Look for junction/symlink following in the path resolution
5. Attempt TOCTOU race during package deployment

### Phase 3: Cross-Driver Analysis

1. Enable WSL2 or Windows Sandbox to activate the full bindflt/wcifs stack
2. Trace cross-altitude I/O request handling
3. Look for path redirection between altitude 135000 and 409800

---

## 6. Comparison: Why This Is Stronger Than cldflt.sys

| Factor | cldflt.sys | bindflt.sys |
|--------|-----------|-------------|
| Prior CVEs | 5+ (saturated) | ZERO |
| Prior researchers | 4+ groups | NONE |
| Vulnerability class indicators | Confirmed exploitable | Same indicators, unexplored |
| Standard user trigger | CfAbortHydration API | AppXSvc (Add-AppxPackage) |
| MSRC familiarity | High — they expect cldflt bugs | LOW — novel target |
| CVE probability if vuln found | Low (crowded) | **HIGH** (virgin territory) |

---

## Appendix A: ETW Providers

- `Microsoft-Windows-Containers-BindFlt` (Debug + Operational channels)
- `Microsoft-Windows-Containers-Wcifs` (Debug + Operational channels)

## Appendix B: Container System Architecture

```
User Mode:
  bindfltapi.dll (13 exports) → \BindFltPort (ACCESS_DENIED)
  container.dll (39 exports)  → BfSetupFilter, BfSetupFilterBatched, BfAttachFilter
  appxdeploymentserver.dll    → BfSetupFilterEx, BfRemoveMappingEx
  computestorage.dll          → HcsAttachLayerStorageFilter, HcsDetachLayerStorageFilter

Kernel Mode:
  bindflt.sys  (alt 409800) — bind mount management, path redirection
  wcifs.sys    (alt 189900) — container filesystem isolation, ghost files
  cimfs.sys    (boot start) — container image filesystem
  luafv.sys    (alt 135000) — UAC file virtualization
  cldflt.sys   (alt 180451) — cloud files sync engine
```

## Appendix C: Services Using bindflt

| Service | DLL | bindflt Functions | Runs As |
|---------|-----|-------------------|---------|
| AppXSvc | appxdeploymentserver.dll | BfSetupFilterEx, BfRemoveMappingEx | **SYSTEM** |
| (container runtime) | container.dll | BfSetupFilter, BfSetupFilterBatched, BfAttachFilter | **SYSTEM** |
| (HCS) | computestorage.dll | HcsAttachLayerStorageFilter (indirect) | **SYSTEM** |
