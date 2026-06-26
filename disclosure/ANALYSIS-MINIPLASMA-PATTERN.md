# VADER Research: MiniPlasma Pattern Analysis & Novel Pathway Hunt

## Classification: INTERNAL RESEARCH — DO NOT PUBLISH

**Date**: 2026-06-15
**Researcher**: VADER (George Wu)
**Target System**: LAPTOP-R32M8MLI (Windows 11 Home Build 26200)
**Objective**: Reverse-engineer MiniPlasma, compare with vader-toctou, extract exploitation pattern, identify un-researched pathway for original CVE

---

## 1. MiniPlasma Mechanism (Reverse Engineered from Source)

### The Primitive: CfAbortOperation Race Condition in cldflt.sys

MiniPlasma exploits a race condition in the Windows Cloud Filter driver (`cldflt.sys`) that has existed since the Cloud Files API was introduced. The bug was originally reported by Google Project Zero but apparently never properly patched (or silently regressed).

**Core exploit flow (4 stages):**

```
STAGE 0 (Orchestrator)
  └─ Spawns Stages 1-3 as child processes

STAGE 1 (Race Engine)
  └─ Thread A: CfAbortOperation(pid, NULL, Block) in infinite loop
  └─ Thread B: SetImpersonationToken(anon) / SetImpersonationToken(null) racing
  └─ Result: cldflt!HsmOsBlockPlaceholderAccess runs with confused identity
  └─ Effect: Registry ACL operation completes as SYSTEM instead of user
  └─ Monitor: NotifyChange on target key detects when race wins

STAGE 2 (Symlink Setup)
  └─ Opens CloudFiles policy key under .DEFAULT
  └─ Sets permissive DACL: Everyone + Anonymous = GenericAll, Low IL
  └─ Deletes subtree (clean slate)
  └─ Creates symbolic link: BlockedApps → .DEFAULT\Volatile Environment
  └─ Runs Stage 1 again (race now applies ACLs to Volatile Environment via symlink)

STAGE 3 (Exploitation)
  └─ Cleans up symlink
  └─ Takes ownership of .DEFAULT\Volatile Environment
  └─ Sets windir = <exploit_dir>
  └─ Creates <exploit_dir>\System32\wermgr.exe (copy of self)
  └─ Triggers QueueReporting scheduled task (SYSTEM, uses %windir%)
  └─ Task Scheduler resolves %windir%\system32\wermgr.exe → attacker binary
  └─ Fake wermgr.exe runs as SYSTEM
  └─ Connects to named pipe MiniPlasmaWERPipe
  └─ Duplicates SYSTEM token → spawns conhost.exe in user's session
```

### Key Technical Details

**The Race**:
- `CfAbortOperation` with `AbortHydrationFlags.Block` triggers `cldflt!HsmOsBlockPlaceholderAccess`
- This kernel function modifies the `BlockedApps` registry key
- Simultaneously, the exploit thread toggles between anonymous token and no token
- When the timing aligns: cldflt performs the registry operation with SYSTEM identity instead of user identity
- The registry symbolic link redirects the write to the attacker's chosen target

**The Symlink**:
- `NtKey.CreateSymbolicLink(ROOT_KEY + "\\" + CLOUD_FILES + "\\" + BLOCKED_APPS, TARGET_KEY)`
- Source: `\Registry\User\.DEFAULT\Software\Policies\Microsoft\CloudFiles\BlockedApps`
- Target: `\Registry\User\.DEFAULT\Volatile Environment`
- Registry symlinks are transparent — operations on source path land on target path

**The Environment Hijack**:
- `.DEFAULT\Volatile Environment` is loaded into SYSTEM task environments
- Volatile Environment values OVERRIDE system-level environment variables
- Setting `windir` here overrides `C:\WINDOWS` from Session Manager\Environment
- Task Scheduler expands `%windir%\system32\wermgr.exe` using the hijacked value

**The Trigger**:
- QueueReporting: `%windir%\system32\wermgr.exe -upload`, RunAs SYSTEM
- SDDL: `D:(A;;FA;;;BA)(A;;FA;;;SY)(A;;FRFX;;;WD)` — World (Everyone) can read/execute
- `Start-ScheduledTask` from standard user triggers it

**The Token Harvest**:
- Named pipe `\\.\pipe\MiniPlasmaWERPipe` for IPC
- SYSTEM payload connects to pipe, writes marker
- User process gets SYSTEM token via `GetNamedPipeServerSessionId` + `DuplicateToken`
- `CreateProcessAsUser` spawns `conhost.exe` with SYSTEM token in user's session

---

## 2. Comparison: MiniPlasma vs vader-toctou

### vader-toctou Approach
| Aspect | vader-toctou | MiniPlasma |
|--------|-------------|------------|
| **Target Driver** | WdFilter.sys (Defender) | cldflt.sys (Cloud Filter) |
| **Primitive Type** | File write (oplock + junction → file overwrite) | Registry ACL manipulation (race + symlink) |
| **Trigger** | Defender scan pipeline (EICAR → oplock → swap) | CfAbortOperation + token impersonation race |
| **Execution** | Direct file overwrite in System32 | Environment variable hijack → scheduled task |
| **Complexity** | Moderate (3 building blocks: junction, oplock, trigger) | High (4 stages, race condition, 3 chained mechanisms) |
| **Reliability** | Low — race window is narrow, Defender actively defends | Moderate — race is probabilistic but loops until success |
| **Defender Interaction** | DIRECTLY fights Defender (target IS WdFilter) | AVOIDS Defender entirely (target is unrelated driver) |

### Why MiniPlasma Succeeds Where vader-toctou Struggles

**1. Target selection — avoid the defended target**
vader-toctou attacks Defender's own scan pipeline. This is like trying to pick a lock while the locksmith watches. Every improvement to Defender's TOCTOU defenses directly counters our approach. MiniPlasma targets cldflt.sys — a completely separate subsystem that Defender has no special insight into.

**2. Primitive type — registry is more permissive than filesystem**
File system operations in System32 are heavily monitored by WdFilter.sys (minifilter at altitude 328010). Registry operations on `.DEFAULT\Volatile Environment` are NOT monitored by any security product — it's just an environment variable key. MiniPlasma's primitive delivers results to an unmonitored location.

**3. Indirect execution — no direct file plant**
vader-toctou needs to WRITE a file into a protected location. MiniPlasma never writes a file into System32 at all — it changes an environment variable, then lets a legitimate SYSTEM task resolve a path to the attacker's OWN directory. The malicious binary lives in user-space the entire time.

**4. Race loop tolerance**
MiniPlasma's race (CfAbortOperation + token toggle) runs in an infinite loop with registry change notification. It can race indefinitely until it wins. vader-toctou's race (oplock + junction during scan) has a single narrow window per scan cycle.

### The Abstract Pattern

```
1. PRIMITIVE ACQUISITION
   Find a kernel driver accessible from user mode that performs
   privileged operations with a race condition in identity/authorization checks.
   
2. REDIRECTION MECHANISM  
   Use a transparent redirection (registry symlink, file junction, mount point)
   to route the privileged operation to your chosen target.
   
3. STRATEGIC TARGET
   Choose a target that is:
   - NOT monitored by security products
   - Controls a path/variable resolved by SYSTEM processes
   - Can be triggered by standard user
   
4. INDIRECT EXECUTION
   Don't plant binaries in protected locations.
   Instead, make SYSTEM processes resolve paths TO your user-writable location.
   
5. TOKEN HARVEST
   Use IPC (named pipe, shared memory) to transfer the SYSTEM token
   back to your interactive session.
```

**The key insight**: MiniPlasma's genius is NOT the race condition (that's a known bug class). It's the INDIRECTION — using registry symlinks + environment variable hijack + scheduled task path resolution to achieve SYSTEM without ever touching a protected filesystem location. Defender watches files. MiniPlasma operates entirely in registry + environment + process creation.

---

## 3. System Reconnaissance for Novel Pathways

### Confirmed Attack Surface on LAPTOP-R32M8MLI

**Running Minifilter Drivers with User-Mode APIs:**

| Driver | API DLL | State | Known Bugs | Notes |
|--------|---------|-------|------------|-------|
| cldflt.sys | cldapi.dll (53 Cf* exports) | RUNNING | MiniPlasma race (UNPATCHED) | Cloud Files — MiniPlasma's target |
| bindflt.sys | bindfltapi.dll (12 Bf* exports) | RUNNING | NONE PUBLIC | Bind mount filter — container tech |
| CimFS | cimfs.dll (27 Cim* exports) | RUNNING | NONE PUBLIC | Composite Image FS — requires privilege |
| UnionFS | UnionFSApi.dll | RUNNING | NONE PUBLIC | Layered filesystem |
| WdFilter.sys | None (IOCTL only) | RUNNING | vader-toctou target | Defender minifilter |
| luafv.sys | None (transparent) | RUNNING | Historical CVEs | UAC file virtualization |

**bindflt communication port**: `\BindFltPort` EXISTS (returns ACCESS_DENIED, not FILE_NOT_FOUND). Standard user denied. Uses `FilterConnectCommunicationPort` + `FilterSendMessage` for user-kernel communication.

**BfSetupFilter**: Returns ACCESS_DENIED (0x80070005) for standard user. Cannot create bind mounts directly.

**CimMountImage**: Returns ERROR_PRIVILEGE_NOT_HELD (0x80070522). API callable but requires SE_RESTORE_PRIVILEGE.

**SYSTEM Scheduled Tasks with User-Triggerable SDDL:**

| Task | Execute Path | SDDL User Access | Notes |
|------|-------------|-------------------|-------|
| **QueueReporting** | `%windir%\system32\wermgr.exe` | `(A;;FRFX;;;WD)` — Everyone | MiniPlasma's trigger |
| **MareBackup** | `%windir%\system32\compattelrunner.exe` | `(A;;GA;;;BU)` — Users FULL | 3 actions, all %windir% |
| **FamilySafetyMonitor** | `%windir%\System32\wpcmon.exe` | `(A;;FRFX;;;BU)` — Users RX | |
| **Hotpatch Monitoring** | `%systemroot%\system32\cmd.exe /d /c hpatchmonTask.cmd` | `(A;;FR;;;BU)` — Users R | cmd.exe + batch script! |
| **ScheduledDefrag** | `%windir%\system32\defrag.exe` | `(A;;FR;;;AU)` — Auth Users R | |
| **Consolidator** | `%SystemRoot%\System32\wsqmcons.exe` | `(A;OICI;GRGX;;;AU)` — Auth Users RX | |

40+ SYSTEM tasks total use `%windir%` or `%SystemRoot%` in Execute path.

**Registry Targets for ACL Primitive (all ReadKey-only for Users, writable via cldflt race):**

| Registry Path | What Loads It | Trigger | Novel? |
|---------------|--------------|---------|--------|
| `.DEFAULT\Volatile Environment\windir` | All %windir% tasks | Any task trigger | NO — MiniPlasma |
| `HKLM\...\Print\Environments\...\Print Processors` | Spooler (SYSTEM) | Print job | PARTIALLY — PrintNightmare variant |
| `HKLM\...\Print\Monitors` | Spooler (SYSTEM) | Print operation | PARTIALLY — known class |
| `HKLM\...\Control\Lsa\Notification Packages` | lsass.exe (SYSTEM) | Boot | YES — novel target for this primitive |
| `HKLM\...\Control\Lsa\Authentication Packages` | lsass.exe (SYSTEM) | Boot | YES — novel target |
| `HKLM\...\Control\Lsa\Security Packages` | lsass.exe (SYSTEM) | Boot | YES — novel target |
| `HKLM\...\Services\<svc>\ImagePath` | SCM (SYSTEM) | Service start | REQUIRES trigger |
| `HKLM\...\Session Manager\Environment` | All SYSTEM processes | Boot/logon | YES — nuclear option |
| `HKLM\...\Image File Execution Options\<exe>` | Any process start | Process launch | YES — debugger injection |

**Anomalous .DEFAULT\Environment Values:**
```
TEMP = C:\Users\gwu07\AppData\Local\Temp    ← USER-WRITABLE!
TMP  = C:\Users\gwu07\AppData\Local\Temp    ← USER-WRITABLE!
Path = C:\Users\gwu07\AppData\Local\Microsoft\WindowsApps;
```
These MAY be overridden by Session Manager\Environment values (TEMP = C:\WINDOWS\TEMP). Needs experimental verification — if Task Scheduler SYSTEM tasks actually inherit .DEFAULT\Environment\TEMP, that's a separate finding (no race needed).

---

## 4. Novel Pathway Candidates

### PATHWAY A: cldflt Race → Print Processor Registration → Spooler Execution
**Originality: MEDIUM** (known primitive + known target class, novel combination)

```
1. Use MiniPlasma's cldflt race to get ACL control of:
   HKLM\SYSTEM\CurrentControlSet\Control\Print\Environments\
   Windows x64\Print Processors
2. Register new print processor:
   SubKey: VaderProcessor
   Value: Driver = C:\Users\gwu07\payload.dll
3. Trigger: Submit a print job
4. Spooler (SYSTEM) loads payload.dll via LoadLibrary
5. SYSTEM code execution
```

**Pros**: Print Spooler is RUNNING, standard user can submit print jobs, DLL loads as SYSTEM.
**Cons**: PrintNightmare (CVE-2021-34527) was this exact vector but via different primitive (RPC). Microsoft hardened Spooler significantly post-PrintNightmare. May have added Authenticode checks on print processor DLLs.
**CVE Probability**: 15-25% (novel primitive → known target)

### PATHWAY B: cldflt Race → LSA Security Package Registration
**Originality: HIGH** (known primitive + un-researched target for this primitive class)

```
1. Use cldflt race to get ACL control of:
   HKLM\SYSTEM\CurrentControlSet\Control\Lsa
2. Add DLL name to "Security Packages" or "Notification Packages" REG_MULTI_SZ
3. DLL placed in System32 (via separate mechanism) OR in user dir if LSA resolves full paths
4. Next boot: lsass.exe loads the DLL as SYSTEM
5. Persistent SYSTEM code execution
```

**Pros**: lsass.exe is THE highest-privilege target. Security packages load at boot. Zero prior research combining cldflt with LSA targets.
**Cons**: Requires boot cycle (not instant). LSA PPL (Protected Process Light) may block unsigned DLLs. Needs a way to get DLL into System32 or trick LSA into loading from non-standard path.
**CVE Probability**: 10-20% (LSA hardening may block, but novel combination)

### PATHWAY C: bindflt Race Condition Discovery (Truly Novel Primitive)
**Originality: MAXIMUM** — completely new vulnerability class

```
1. Reverse-engineer bindflt.sys for race conditions
   - Focus on BfSetupFilter → BfAttachFilter kernel path
   - Look for TOCTOU between path validation and bind mount creation
   - The driver uses FilterConnectCommunicationPort (\BindFltPort)
   - Communication via FilterSendMessage (IOCTL-based)
2. If race found: use bind mount to overlay System32 with attacker directory
3. SYSTEM process loads binaries from overlay instead of real System32
4. No registry manipulation needed — pure filesystem confusion
```

**Pros**: ZERO prior public research. Completely original. George's name exclusively on CVE. Different primitive class from MiniPlasma (filesystem overlay vs registry ACL). bindflt is new code (containers/WSL2) — new code = more bugs.
**Cons**: Requires significant reverse engineering. ACCESS_DENIED on port and API — might need elevation to even trigger the race (which defeats the purpose). May require specific container runtime configuration.
**CVE Probability**: 30-50% IF a race is found (high value, novel). But FINDING the race requires deep RE.

### PATHWAY D: Environment Variable Hijack via Different Variable
**Originality: MEDIUM-HIGH** (same primitive class, novel target variable)

```
1. Use cldflt race to get ACL control of .DEFAULT\Volatile Environment
   (Same as MiniPlasma Stage 1-2)
2. Instead of windir, set a DIFFERENT variable:
   - COMSPEC = <exploit_dir>\cmd.exe
   - SYSTEMROOT = <exploit_dir>
   - APPDATA = <exploit_dir>\AppData\Roaming
   - PSModulePath = <exploit_dir>\Modules
3. Trigger a SYSTEM task that resolves the hijacked variable
   - Hotpatch Monitoring uses: cmd.exe /d /c hpatchmonTask.cmd
     → If COMSPEC is hijacked, cmd.exe loads from attacker path
   - PowerShell-based tasks resolve PSModulePath
4. SYSTEM execution via different chain than MiniPlasma
```

**Key target: Hotpatch Monitoring task**
```
Execute: %systemroot%\system32\cmd.exe /d /c %systemroot%\system32\hpatchmonTask.cmd
SDDL: D:P(A;;FA;;;BA)(A;;FA;;;SY)(A;;FR;;;BU)
```
This task runs `cmd.exe` which executes a `.cmd` batch script. The batch script may reference additional environment variables internally. If `%systemroot%` is hijacked, both `cmd.exe` AND `hpatchmonTask.cmd` resolve from attacker directory.

BUT: this task uses `%systemroot%` not `%windir%`. MiniPlasma hijacks `windir`. Can we hijack `systemroot` via Volatile Environment?

**Pros**: Different variable, different trigger task, different execution chain. Would be documented as independent variant with different attack surface.
**Cons**: Core primitive is still cldflt race (Nightmare-Eclipse's work). Microsoft may patch cldflt generically (blocking ALL variants).
**CVE Probability**: 20-30% (novel chain, but derivative primitive)

### PATHWAY E: .DEFAULT\Environment TEMP/TMP Misdirection (No Race Needed)
**Originality: HIGH** (potential zero-interaction misconfiguration finding)

```
Current state on this system:
  HKU\.DEFAULT\Environment\TEMP = C:\Users\gwu07\AppData\Local\Temp
  HKU\.DEFAULT\Environment\TMP  = C:\Users\gwu07\AppData\Local\Temp

If Task Scheduler SYSTEM tasks inherit .DEFAULT\Environment values:
  1. SYSTEM tasks write temp files to USER-WRITABLE directory
  2. User plants symlink in temp dir → redirects SYSTEM write to protected location  
  3. OR: user prepopulates temp file that SYSTEM task trusts (TOCTOU on temp)
  4. SYSTEM → arbitrary file write
```

**Verification needed**: Does Task Scheduler actually use .DEFAULT\Environment\TEMP for SYSTEM tasks, or does Session Manager\Environment\TEMP (C:\WINDOWS\TEMP) win?

**Pros**: No race condition needed. No exploit code needed. Pure misconfiguration finding. If confirmed, trivially reproducible. Affects all single-user Windows 11 Home installs where .DEFAULT inherits from first user.
**Cons**: Might not actually work (system env may override). Even if it works, Microsoft may classify as "won't fix" (user already has admin access on Home edition, or it's by-design for single-user systems).
**CVE Probability**: 5-15% (needs verification, may be wontfix)

### PATHWAY F: CimFS Composite Image Overlay (Future Research)
**Originality: MAXIMUM**

```
1. CimMountImage requires SE_RESTORE_PRIVILEGE (standard user blocked)
2. BUT: if a SYSTEM process mounts CIM images based on user-controllable input...
3. OR: if there's a token confusion race similar to cldflt...
4. Mount a CIM image overlaying System32 → SYSTEM loads from overlay
```

**Pros**: Zero prior research. Novel driver. Novel primitive class.
**Cons**: Blocked by privilege check. Requires finding a way around it.
**CVE Probability**: Too speculative to estimate. Future research direction.

---

## 5. Recommended Research Plan

### Priority Order (Optimized for CVE-with-George's-name)

**IMMEDIATE (Test when home):**

1. **Run MiniPlasma as-is** — confirm cldflt race works on this system
   - If it pops SYSTEM: validates the primitive, enables Pathways A/B/D
   - If it fails: cldflt may be patched (changes everything)

2. **Verify .DEFAULT\Environment\TEMP inheritance** (Pathway E)
   - Create a SYSTEM scheduled task that writes %TEMP% to a file
   - Check if output shows user temp or system temp
   - Zero risk, zero exploit code, just observation
   - If confirmed → immediate low-effort CVE candidate

**SHORT-TERM (Days):**

3. **Test Pathway D (different env var + different task)**
   - After confirming cldflt race works via MiniPlasma
   - Modify MiniPlasma to target `systemroot` instead of `windir`
   - Trigger Hotpatch Monitoring instead of QueueReporting
   - Document as independent variant with different attack surface
   - This is the fastest path to an original finding

4. **Test Pathway A (Print Processor)**
   - After confirming cldflt race works
   - Test if Spooler still loads unsigned print processor DLLs post-PrintNightmare patches
   - If yes: novel exploitation chain

**MEDIUM-TERM (Weeks):**

5. **Pathway C (bindflt reverse engineering)**
   - Set up IDA/Ghidra for bindflt.sys analysis
   - Map FilterSendMessage handler (IOCTL dispatch)
   - Look for TOCTOU between path validation and bind creation
   - HIGHEST payoff if successful — fully original CVE

6. **Pathway B (LSA packages)**
   - Test LSA PPL protection status
   - Check if unsigned DLLs can be loaded as Security Packages
   - If LSA PPL is disabled on Win11 Home: viable target

### What NOT to Pursue

- **vader-toctou's WdFilter approach**: Dead end. Defender watches its own pipeline. The abstract pattern shows why attacking the security product itself is the wrong strategy.
- **MiniPlasma exact reproduction**: Don't just run it and submit. That's Nightmare-Eclipse's CVE, not yours. Use it as VALIDATION of the primitive, then build YOUR OWN chain.
- **azureike.dll (#52)**: DEAD. All LoadLibraryExW hardened with 0x800.
- **HKCU COM → SYSTEM**: DEAD. Integrity level check since Vista.

---

## 6. The Pattern — Operational Summary

```
                    WHAT WORKS                          WHAT DOESN'T
                    ──────────                          ─────────────
Target:             Unmonitored subsystem               Security product itself
Primitive:          Registry/config manipulation         Direct file system write
Execution:          Indirect (env var → path resolve)    Direct (file in System32)
Location:           Attacker binary in user-space        Plant binary in protected dir  
Trigger:            Scheduled task w/ user SDDL          Manual/automated scan
Detection:          Invisible to EDR (reg + env)         Visible to minifilter
```

The winning strategy is INDIRECTION: don't fight the guards, make the guards walk to you.

---

## Appendix A: cldapi.dll Exports (53 Functions)

Potential race condition candidates beyond CfAbortOperation:
- `CfHydratePlaceholder` — triggers data hydration, similar kernel path
- `CfDehydratePlaceholder` / `CfDehydratePlaceholderEx` — reverse operation  
- `CfConvertToPlaceholder` — converts file to cloud placeholder
- `CfRevertPlaceholder` — removes placeholder status
- `CfSetPinState` — pins/unpins placeholder
- `CfUpdatePlaceholder` — updates placeholder metadata
- `CfOpenFileWithOplock` — opens file with oplock (!)

`CfOpenFileWithOplock` is particularly interesting — combines cloud files with oplock semantics. If this function has a race condition with token impersonation...

## Appendix B: bindfltapi.dll Exports (12 Functions)

- `BfSetupFilter` — creates bind filter on path
- `BfSetupFilterEx` — extended version
- `BfSetupFilterBatched` — batch configuration
- `BfAttachFilter` — attaches filter to volume
- `BfConfigureFilter` — modifies filter configuration
- `BfGetMappings` — queries active bind mappings
- `BfRemoveMapping` / `BfRemoveMappingEx` — removes bind mapping
- `BfGenerateBatchedConfig` — generates batch config
- `BfGenerateMappingConfiguration` — generates mapping config
- `BfTrackWritesFromSilo` — tracks writes from container silo
- `CreateBindLink` — high-level bind link creation (wraps BfSetupFilter)

Communication uses `FilterConnectCommunicationPort(\BindFltPort)` + `FilterSendMessage`.
Port exists but returns ACCESS_DENIED for standard user.

## Appendix C: Scheduled Task SDDL Decode

| SID | Identity | In MareBackup | In QueueReporting |
|-----|----------|---------------|-------------------|
| BA | BUILTIN\Administrators | GA (Full) | FA (Full) |
| SY | NT AUTHORITY\SYSTEM | GA (Full) | FA (Full) |
| BU | BUILTIN\Users | **GA (Full!)** | — |
| WD | Everyone (World) | — | **FRFX (Read/Execute)** |
| LS | LOCAL SERVICE | FRFX | — |
| AU | Authenticated Users | — | — |

MareBackup: any standard user has GENERIC_ALL. Can start, stop, modify, delete the task.
QueueReporting: everyone can read/execute. Can start the task.
