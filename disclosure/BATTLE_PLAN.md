# VADER Security Research — Battle Plan

## Audit Scope Completed (2026-06-15)

Full attack surface audit of LAPTOP-R32M8MLI (Windows 11 Home Build 26200):

### Vectors Tested
- [x] SYSTEM services with user-writable binaries
- [x] SYSTEM services with unquoted paths  
- [x] SYSTEM scheduled tasks with user-controllable paths
- [x] svchost ServiceDll registry paths (197 checked)
- [x] HKLM service registry key write access (905 checked)
- [x] HKLM high-value registry key write access (5 hives scanned)
- [x] COM CLSID hijacking (7500+ CLSIDs scanned)
- [x] HKCU COM override for SYSTEM process injection
- [x] Phantom DLL loading via PATH injection
- [x] MSI repair privilege escalation
- [x] Program Files directory write access
- [x] Print Spooler / Point and Print attack surface
- [x] Credential Provider DLL registration
- [x] Authentication/Security Package registration
- [x] Named pipe impersonation targets
- [x] Windows Error Reporting directory permissions
- [x] Windows Defender update mechanism TOCTOU
- [x] Image File Execution Options (IFEO) write access
- [x] Print Monitor registration
- [x] LSA/SecurityProviders write access
- [x] Junction/symlink creation capabilities
- [x] Drivers32 multimedia driver registry ACLs
- [x] SYSTEM process multimedia module loading
- [x] Windows Store/EditionOverrides registry keys
- [x] Windows Installer cached MSI custom actions
- [x] AppX/MSIX service paths

---

## Findings — Ranked by CVE Probability

### #1 PRIORITY: Finding #36 — Defender HWBP Tamper Protection Bypass
- **Target**: Microsoft (MSRC)
- **CWE**: CWE-693 Protection Mechanism Failure
- **Boundary**: Standard user bypasses Defender Tamper Protection
- **CVE Probability**: 20-35%
- **Status**: FULLY PROVEN, report + evidence complete
- **Evidence**: EVIDENCE-36-HWBP-LIVE-TEST.md
- **Report**: MSRC-2026-DEFENDER-HWBP.md
- **Action**: SUBMIT TO MSRC

### #2: Finding #49 — Muse Hub System PATH Injection  
- **Target**: Muse Hub vendor (MuseScore/Steinberg)
- **CWE**: CWE-426 Untrusted Search Path Element
- **Boundary**: Standard user → SYSTEM via DLL hijack
- **CVE Probability**: 60-70%
- **Status**: PATH injection proven, DLLs planted, PENDING reboot execution proof
- **Evidence**: FINDING-49-MUSEHUB-PATH-INJECTION.md
- **Action**: REBOOT TO PROVE, then submit to vendor + MITRE

### #3: Finding #50 — CrossDevice DLL Replacement ⚠️ KNOWN CVE + INCOMPLETE REMEDIATION
- **Target**: Microsoft (MSRC) — only if incomplete remediation confirmed
- **CWE**: CWE-732 Incorrect Permission Assignment + CWE-426 Untrusted Search Path
- **Boundary**: Standard user replaces Microsoft-signed COM DLL; loader patched but ACLs NOT fixed
- **Original CVE**: CVE-2025-24076 (SYSTEM) / CVE-2025-24994 (user) — Compass Security, March 2025
- **CVE Probability**: 10-20% (incomplete remediation angle) / 0% (original finding is duplicate)
- **Status**: DUPLICATE of known CVE. ACLs still wrong post-patch. Testing if remediation is incomplete.
- **Evidence**: FINDING-50-CROSSDEVICE-DLL-HIJACK.md
- **Action**: Still worth planting canary — if ANY process loads the COM DLL without signature checks, remediation is incomplete
- **Key Facts**:
  - DLL still user-writable on fully-patched system (June 2026)
  - HKLM COM registration still points to ProgramData path
  - Microsoft fixed the LOADER (signature check), NOT the filesystem ACLs
  - Any third-party COM client loading CLSID {E9F83CF2-...} would hit user-writable DLL
  - PoC: github.com/mbanyamer/CVE-2025-24076

### DEAD: Finding #52 — IKEEXT azureike.dll Phantom DLL
- **Target**: N/A — not exploitable
- **CWE**: CWE-426 (would be, if not hardened)
- **Status**: DEAD — LoadLibraryExW hardened with LOAD_LIBRARY_SEARCH_SYSTEM32 (0x800)
- **Evidence**: FINDING-52-IKEEXT-AZUREIKE-PHANTOM.md
- **Key Facts**:
  - Zero prior research — undocumented Azure VPN gateway phantom DLL
  - IKEEXT runs as LocalSystem, azureike.dll doesn't exist on disk
  - ALL 3 LoadLibraryExW calls in ikeext.dll use 0x800 flag (System32-only search)
  - Registry key IKEEXT\Parameters not writable by standard user
  - Microsoft uniformly hardened all DLL loads in IKEEXT, not just the known wlbsctrl.dll

### #4: Finding #49b — uv (Astral) System PATH Injection
- **Target**: Astral (uv Python package manager)
- **CWE**: CWE-426 Untrusted Search Path Element  
- **Boundary**: Standard user → SYSTEM via DLL hijack
- **CVE Probability**: 50-60%
- **Status**: PATH injection confirmed, same class as #49
- **Action**: Submit to Astral separately after Muse Hub proven

### #5: Finding #48 — Drivers32 HKLM User-Writable ACL
- **Target**: Microsoft (MSRC)
- **CWE**: CWE-732 Incorrect Permission Assignment
- **Boundary**: NO cross-boundary — persistence/injection only
- **CVE Probability**: 10-15% (defense-in-depth, not security boundary)
- **Status**: ACL anomaly confirmed, no SYSTEM loading
- **Evidence**: FINDING-48-DRIVERS32-ACL.md
- **Action**: Submit as defense-in-depth recommendation with #36

### #6: Finding #47 — Phantom DLL Load via PATH
- **Target**: Microsoft (MSRC)
- **CWE**: CWE-426 Untrusted Search Path Element
- **Boundary**: Depends on third-party PATH injection
- **CVE Probability**: 10-15%
- **Status**: Documented but Microsoft will blame third-party installer
- **Report**: MSRC-2026-PHANTOM-DLL.md
- **Action**: Bundle with #49 as attack chain documentation

### DEAD: Finding #42 — Wondershare NativePushService
- **Status**: DUPLICATE of CVE-2024-26574
- **Action**: None — already reported by others

### DEAD: Finding #52 — IKEEXT azureike.dll Phantom DLL
- **Status**: DEAD — LoadLibraryExW uses LOAD_LIBRARY_SEARCH_SYSTEM32
- **Action**: None — documented for completeness. Detection rule value only.

---

## Immediate Action Items

### Phase 0: MiniPlasma Validation (HIGHEST PRIORITY)
1. **Run MiniPlasma PoC** — confirms cldflt race works on this system
   ```cmd
   cd "C:\Users\gwu07\Desktop\CSEC\Semester 2\MiniPlasma-main\MiniPlasma-main"
   REM Build with dotnet build or Visual Studio
   REM Run — if SYSTEM shell pops, primitive is LIVE
   ```
2. If MiniPlasma works → Pathways D and A become immediately testable
3. If MiniPlasma fails → cldflt may be patched, pivot to Pathway C (bindflt RE)

### Phase 0.5: TEMP Inheritance Test (Zero Risk, Potential Standalone Finding)
4. Run `tests\test_system_temp_inheritance.ps1 -Register` (admin)
5. Run `tests\test_system_temp_inheritance.ps1 -Trigger` (standard user)
6. Run `tests\test_system_temp_inheritance.ps1 -Check` — if SYSTEM task got user TEMP → misconfiguration finding

### Phase 1: Novel Pathway Testing (After MiniPlasma Validates)
7. **Pathway D**: Modify MiniPlasma to target `systemroot` + trigger Hotpatch Monitoring
8. **Pathway A**: Test Print Processor registration via cldflt race → Spooler DLL load
9. Document each variant as independent finding with separate attack surface

### Phase 2: Original Research — bindflt.sys (ZERO Prior CVEs)
10. **Full analysis**: `ANALYSIS-BINDFLT-WCIFS.md`
11. **Pathway C — AppXSvc → BfSetupFilterEx TOCTOU**:
    - Craft minimal MSIX with VFS directory structure + junction in VFS path
    - Trigger `Add-AppxPackage` → observe AppXSvc → bindflt flow with Procmon
    - Look for TOCTOU between path validation (namesup.c) and bind mount creation (mapping.c)
    - Race junction swap during deployment window
    - If race found → fully original CVE, George's name exclusively
12. **Pathway C2 — wcifs.sys**: Same analysis methodology, same zero-CVE status
    - `\WcifsPort` confirmed to exist (ACCESS_DENIED)
    - Same I/O redirection imports as bindflt
13. **Static RE**: Load bindflt.sys in IDA/Ghidra → map message.c port handler → trace BfSetupFilterEx kernel path → find validation/use gap
14. **Key intel**: bindflt.sys imports RtlQueryPackageIdentity — package-identity-aware access decisions. AppXSvc calls BfSetupFilterEx during MSIX deployment (confirmed via string analysis of appxdeploymentserver.dll)

### Phase 3: Existing Findings
13. Reboot for PATH canary test (#49)
14. Check: `type C:\Windows\Temp\vader_path_hijack.log`
15. Submit #36 to MSRC (Defender HWBP bypass)
16. If PATH canary confirmed → submit #49 to Muse Hub vendor  
17. If PATH canary confirmed → submit #49b to Astral (uv)
18. Git commit all disclosure files

---

## Vectors Tested This Session (Session 2 — No-Reboot Sweep)

### Dead Ends (Fully Tested, Nothing Found)
- NVIDIA service failure recovery commands — bat files are TrustedInstaller-locked
- Auto-updater DLL sideloading (Adobe, ASUS, Edge, Google, NVIDIA, Muse Hub, OneDrive) — all Program Files, read-only
- Performance Counter DLLs — 43 libraries, all locked down
- WMI providers in user-writable paths — only CrossDevice (already captured)
- ETW providers — 964 publishers, no user-writable resource files
- BITS notification commands — run as job owner (user), not SYSTEM
- AppInit_DLLs — disabled, registry not writable
- Group Policy script locations — not writable
- Print Spooler driver directories — read-only for Everyone
- Point and Print — not configured (default)
- COM auto-elevation monikers — none point to user-writable DLLs
- Hosts file — read-only
- Visual Studio Setup WMI DLLs (ProgramData) — directory exists but DLLs not writable
- WER ReportQueue — writable but classic junction attacks patched, WerSvc stopped

### Coverage Totals (Across Both Sessions)
- Service registry keys: 905
- Svchost ServiceDlls: 197
- COM CLSIDs: 9,255
- Performance counter libraries: 43
- ETW publishers: 964
- Auto-updater services: 12
- DLLs in ProgramData: ALL scanned (only 1 writable — CrossDevice)
- Service failure recovery commands: ALL checked (3 with commands, all locked)

---

## Notes for George

**MiniPlasma Pattern Analysis Complete** — full reverse engineering and comparison documented in `ANALYSIS-MINIPLASMA-PATTERN.md`. The abstract exploitation pattern is: kernel driver race → registry symlink redirection → environment variable hijack → SYSTEM task path resolution → indirect execution. The key insight is INDIRECTION — never touch protected filesystem locations. Make SYSTEM resolve paths TO your user-writable directory.

**Don't just run MiniPlasma and submit.** That's Nightmare-Eclipse's CVE. Use it as VALIDATION of the cldflt primitive, then build YOUR OWN chain. Pathway D (different env var + different trigger task) is the fastest path to an original finding. Pathway C (bindflt reverse engineering) is the highest-payoff for a fully original CVE.

**6 novel pathways identified, ranked by CVE probability and originality:**
- **A**: cldflt race → Print Processor registration → Spooler DLL load (15-25%)
- **B**: cldflt race → LSA Security Package registration (10-20%)  
- **C**: bindflt.sys race condition discovery (30-50% IF found — fully original)
- **D**: cldflt race → systemroot hijack → Hotpatch Monitoring task (20-30%)
- **E**: .DEFAULT\Environment TEMP misdirection (5-15%, zero exploit code)
- **F**: CimFS overlay (future research, speculative)

**CrossDevice (#50) is now a KNOWN CVE (CVE-2025-24076).** Incomplete remediation angle at 10-20%. Low priority.

**azureike.dll (#52) is DEAD.** All LoadLibraryExW hardened with 0x800.

**Kill chains are legitimate CVEs.** Multi-vector chains absolutely count. Finding #49 (PATH injection + phantom DLL) is exactly this pattern.

**#36 (Defender HWBP bypass) is STILL the strongest immediate play.** Submit it regardless. 20-35% CVE probability but highest prestige.

**Muse Hub (#49) is the safest bet.** 60-70% CVE probability. Third-party, not Microsoft. Still worth pursuing.

**bindflt.sys is the most promising un-researched target.** Running on the system, user-mode API exists (bindfltapi.dll), communication port `\BindFltPort` confirmed to exist (ACCESS_DENIED, not FILE_NOT_FOUND). ZERO public CVEs for race conditions in bindflt. Container/WSL2 code — new code = more bugs. If you find a race here, it's 100% your CVE.

**NEW (Session 3c) — AppXSvc → bindflt chain confirmed.** `appxdeploymentserver.dll` calls `BfSetupFilterEx` and `BfRemoveMappingEx`. AppXSvc runs as SYSTEM. Standard users trigger AppX operations via `Add-AppxPackage`. This means standard user → SYSTEM → bindflt kernel operations. The MSIX VFS directory structure provides user-controlled paths that flow through this chain. A TOCTOU in bindflt's path handling during BfSetupFilterEx would be exploitable via this indirect path.

**CVE research confirmed cldflt is SATURATED** (5+ CVEs, 4 research groups, Exodus Intel, Project Zero, etc.). bindflt has ZERO CVEs, ZERO named researchers. Same vulnerability class indicators (token impersonation + I/O redirection + security context capture). This is where the open surface is.

**wcifs.sys is the secondary target.** Also zero LPE CVEs. `\WcifsPort` confirmed to exist. Same I/O redirection imports. Used for container ghost-file isolation. Cross-altitude TOCTOU with bindflt (409800) and luafv (135000) is an unexplored interaction.
