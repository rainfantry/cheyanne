# VADER ROOTKIT

```
 ██╗   ██╗ █████╗ ██████╗ ███████╗██████╗
 ██║   ██║██╔══██╗██╔══██╗██╔════╝██╔══██╗
 ██║   ██║███████║██║  ██║█████╗  ██████╔╝
 ╚██╗ ██╔╝██╔══██║██║  ██║██╔══╝  ██╔══██╗
  ╚████╔╝ ██║  ██║██████╔╝███████╗██║  ██║
   ╚═══╝  ╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝
```

**22DIV // george wu // rainfantry.github.io**

```
           .          .
        .  |\        /|  .
           | \______/ |
      .    |  ______  |    .
           | |  ..  | |
           | |  ::  | |
           | | /__\ | |
           |  \____/  |
            \________/
```

> *"The hunt never ends."*

---

### What This Is

A complete rootkit kill chain — 11 phases, 19 engagements, 70 findings — built from first principles against live Windows Defender on my own hardware. Not downloaded. Not forked. Not copied from a blog post. Every line written, tested, and documented by hand.

Started as a TOCTOU race condition study against Defender's quarantine pipeline (`vader-toctou`). Six engagements. Thirty findings. The deletion primitive was defeated by Microsoft's defense-in-depth. The wall held — but the wall taught me how it was built.

Every finding from that campaign feeds forward into a full rootkit: C2 shell, AMSI/ETW bypass via hardware breakpoints, privilege escalation, process injection, HTTP staging, anti-forensics cleanup, and an automated XOR mutation pipeline that defeats all static signatures.

### Why

I'm 29. CSEC student. No degree. Criminal record that blocks every corporate door. The only path that respects what I actually am — not what HR filters say I should be — is becoming someone who finds the bugs that matter. Exploit research. Responsible disclosure. CVE credits. The kind of work where your GitHub speaks louder than your background check.

This repo is the foundation of that specialisation.

Every technique here is studied on my own machines, documented to reporting standard, and built with the intent of responsible disclosure via MSRC if a novel vulnerability is discovered. The goal isn't destruction — it's understanding Windows security architecture deeply enough to find what Microsoft missed.

### Classification

```
CLASSIFICATION:  UNCLASSIFIED // ACADEMIC USE ONLY
OPERATOR:        VADER (george wu / 22DIV)
AUTHORISATION:   CSEC academic research, own hardware
DOCTRINE:        Israeli cyber methodology — Unit 8200 principles
                 Build from scratch. Understand fundamentals.
                 Dual-toolset resilience. Tool burn protocol.
                 If you can't build it, you don't understand it.
DISCLOSURE:      Responsible disclosure via MSRC
MSRC:            VULN-195458 (HWBP bypass — rejected, detection bypasses out of scope)
TARGET:          Windows 11 Home Build 26200 (24H2)
                 Standard user context
                 Defender RTP ENABLED, Tamper Protection OFF
STATIC SCAN:     0/82 BINARIES DETECTED
RUNTIME:         0 BEHAVIOURAL DETECTIONS
MEMORY MODIFIED: ZERO BYTES
VALIDATION:      Every binary built from first principles — no Metasploit,
                 no Cobalt Strike, no copied shellcode. 29,536+ LOC hand-written.
                 4 independent repos, each with own mutation pipeline.
                 Surviving 8200 doctrine standard: can rebuild entire toolset
                 from memory if all repos are burned.
```

### Kill Chain

```
  PHASE 0        PHASE 1        PHASE 2        PHASE 3
  C2 SHELL  -->  AMSI BLIND --> ETW BLIND  --> PRIVESC
  (ALPHA)        (DELTA)        (FOXTROT)      (GOLF)
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
     |              |              |
     v              v              v
  PHASE 7        PHASE 8        PHASE 9
  CLOAK     -->  BYOVD     -->  C2 AGENT
  (KILO)         (LIMA)         (MIKE)
  NtQuery        RTCore64.sys   17-op remote
  inline hook    CVE-2019-16098 agent: shell,
  proc/file/     token steal,   screenshot,
  conn hide      callback kill  mic, keylog,
  system-wide    DSE bypass     sftp, persist
     |
     v
  PHASE 10       META-2
  METAMORPH -->  EVOLUTION
  (NOVEMBER)     (vader_evolve)
  dead code,     metamorph +
  opaque pred,   mutate +
  junk API,      compile +
  const split    scan loop
```

| Phase | Codename | Component | Status | Technique |
|-------|----------|-----------|--------|-----------|
| 0 | ALPHA | C2 Reverse Shell | **BUILT** | XOR-obfuscated callback, automated listener |
| 1 | DELTA | AMSI Bypass | **CONFIRMED** | Hardware breakpoint DR0 on AmsiScanBuffer |
| 2 | FOXTROT | ETW Bypass | **CONFIRMED** | Hardware breakpoint DR1 on EtwEventWrite |
| 1+2 | — | Dark Room | **OPERATIONAL** | Dual HWBP, zero memory modification |
| 3 | GOLF | Privilege Escalation | **SYSTEM** | CWE-732 service binary replacement |
| 4 | HOTEL | Process Injection | **CONFIRMED** | DLL injection + HWBP propagation all threads |
| 5 | INDIA | HTTP Stager | **BUILT** | WinHTTP download cradle + C2 file server |
| 6 | JULIET | Anti-Forensics | **BUILT** | Canary wipe, log clear, prefetch, timestomp, self-delete |
| 7 | KILO | User-Mode Cloak | **OPERATIONAL** | NtQuery* inline hooks — process/file/connection hiding, system-wide CBT hook injection |
| 8 | LIMA | BYOVD Kernel Persistence | **BUILT** | RTCore64.sys / dbutil_2_3.sys arbitrary R/W, token stealing, EDR callback removal, DSE bypass |
| 9 | MIKE | C2 Remote Agent | **BUILT** | 17-op agent: screenshot, mic, keylog, SFTP, VNC, persist (schtask/reg/WMI/IFEO) |
| 10 | NOVEMBER | Metamorphic Engine | **OPERATIONAL** | Dead code injection, opaque predicates, junk API, constant splitting, identifier mutation |
| Meta | — | Auto-Mutation | **BUILT** | XOR key rotation + recompile + Defender rescan loop |
| Meta-2 | — | Evolution Pipeline | **BUILT** | metamorph + mutate + compile + scan in one command, multi-cycle support |

### XOR Signature Isolation

Each component has its own XOR key. If Defender signatures one binary, the others survive. `mutate.py` rotates all keys automatically.

```
  Component        Key     Arrays    Binary
  ─────────────────────────────────────────────
  dark_room        0x41    5         dark_room.exe
  shell            0x41    2         vader_shell.exe
  inject_dll       0x77    5         vader_inject.dll
  inject_exe       0x77    3         vader_inject.exe
  v4_svc_replace   0x52    2         WsNativePushService.exe
  v5_dll_proxy     0x37    8         VERSION.dll
  v6_path_hijack   0x63    1         targetname.dll
  v7_phantom_dll   0x19    1         osppc.dll
```

### Architecture

```
vader-rootkit/
├── shell/              PHASE 0: XOR reverse shell + listener
├── amsi/               PHASE 1: AMSI bypass (classic + HWBP)
├── etw/                PHASE 2: ETW bypass (classic + HWBP)
├── dark_room/          PHASE 1+2: Combined dual HWBP loader
├── sideload/           PHASE 3: CWE-732 service replacement + mutations
├── injection/          PHASE 4: DLL injection + HWBP propagation
├── stagers/            PHASE 5: WinHTTP download cradle
├── forensics/          PHASE 6: Anti-forensics cleanup
├── vectors/            Signature-isolated attack modules (v4-v7)
├── cloak/              PHASE 7: User-mode rootkit (proc/file/conn hiding)
├── byovd/              PHASE 8: BYOVD kernel persistence (RTCore64/dbutil_2_3)
├── recon/              17-section automated recon scanner
├── docs/               EVC website + field manual
├── deploy.py           Build + scan + deploy automation
├── mutate.py           XOR key mutation pipeline
├── metamorph.py        Metamorphic source transformer (Phase 10)
├── vader_evolve.py     Evolution pipeline (metamorph + mutate + compile + scan)
├── vader_menu.py       Terminal dashboard (ANSI art)
├── vader_ui.py         Web C2 dashboard (browser UI) + agent listener
└── vader_agent.py      Remote agent (deploy on target, connects back)
```

### Stealth Profile

```
  TEST                           RESULT
  ──────────────────────────────────────────
  Static scan (28 binaries)      0 DETECTED
  Runtime behavioural            0 DETECTED
  Memory integrity               ZERO bytes modified
  VirtualProtect calls           NONE
  Tamper Protection trigger      DID NOT DETECT
  AMSI scan result               E_INVALIDARG (blind)
  ETW telemetry                  STATUS_SUCCESS (silenced)
  Privilege required             Standard user
  Fuzzing campaign (100K iter)   0 crashes, 0 hangs
```

**70 findings across 19 engagements. 11 operational phases. 80 clean binaries. Kernel persistence survives restart. Metamorphic obfuscation produces unique binary identity per evolution cycle.** Standard user → LocalSystem confirmed via service binary replacement (CWE-732) and phantom DLL plant (CWE-427). AMSI + ETW simultaneously bypassed via hardware breakpoints, zero memory modification. Finding #36 (HWBP bypass) submitted to MSRC as VULN-195458 — **rejected**, detection bypasses out of scope. Technique published openly.

### What Carries Forward From vader-toctou

| Finding | What It Taught Us | How It Applies Here |
|---------|-------------------|---------------------|
| #14/#17 | SYSTEM reads through junctions | Sideload: SYSTEM services follow junctions when loading DLLs |
| #20 | Security checks fire at specific moments, not continuously | AMSI: patch the check function before it fires |
| #21 | Fail-and-forget retry model | Sideload: services that retry DLL loads = wider race window |
| #26 | Kernel-mode I/O bypasses user-mode hooks | ETW: know what kernel telemetry survives our patches |
| #29 | Path re-resolution follows junctions | Sideload: junction-based DLL redirect is viable |
| #30 | Single-handle architecture | Know when single-handle defense applies vs when it doesn't |

### Key Findings

**HWBP Blind Spot (Finding #36, MSRC VULN-195458):** Defender monitors memory-level modifications (VirtualProtect, byte writes) but does NOT monitor CPU debug register manipulation. Hardware breakpoints via SetThreadContext on DR0-DR3, combined with a Vectored Exception Handler, intercept and neuter AMSI and ETW without modifying a single byte of target memory. No behavioural rule exists. No detection. **MSRC rejected** — "not a security boundary." Embargo voided. Technique published openly.

**CWE-732 Privilege Escalation (Finding #42):** Standard user → SYSTEM via Wondershare NativePushService service binary replacement. Full SYSTEM token, no UAC, no admin creds.

**Phantom DLL (Finding #47):** Microsoft Office ClickToRunSvc loads osppc.dll that doesn't exist on disk. User-writable PATH fills the void. LocalSystem auto-start service loads attacker DLL. CWE-427.

**DLL Injection + HWBP Propagation (Finding #51):** DLL injected into target process sets hardware breakpoints on ALL threads via VdrWatch re-enumeration. CREATE_SUSPENDED spawn = target born blind before first instruction executes.

**BYOVD Kernel Persistence (Phase 8):** Bring Your Own Vulnerable Driver — loads RTCore64.sys (CVE-2019-16098) or dbutil_2_3.sys (CVE-2021-21551) via SCM, obtains arbitrary kernel R/W through signed driver IOCTLs. Token stealing via EPROCESS walk (ActiveProcessLinks offset 0x448, Token offset 0x4B8) — copies SYSTEM token to any process. EDR callback removal by zeroing PspCreate*NotifyRoutine arrays. DSE bypass via CI!g_CiOptions write. 157 KB binary, 0 Defender detections.

**C2 Remote Agent (Phase 9):** 16-operation remote access agent over VADER protocol (length-prefixed JSON, TCP 8667). Ops: sysinfo, exec, scan, upload, recon, ls, download, screenshot (GDI), mic recording (waveIn API), keylogger (GetAsyncKeyState), SFTP get/put/sync with SHA-256 verification, multi-method persistence (scheduled task, registry run, WMI event subscription, IFEO debugger).

**100K Fuzzing Campaign:** mpengine.dll mutation fuzzer — 100,000 iterations, 4 workers, 33 seeds, ~9 hours runtime. Zero crashes, zero hangs. Parser is robust at this mutation depth.

### Compile Environment

```
Compiler:  cl.exe (MSVC via Visual Studio 18 Community)
vcvars:    "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
Target:    x64 Windows 11
Flags:     /O1 /GS- /utf-8
Linker:    ws2_32.lib (shell), ntdll.lib (ETW/AMSI patches)
```

### Rules of Engagement

1. All testing on own hardware only
2. Defender RTP stays ENABLED during testing (we fight the live system)
3. Annotated version is the master — deployment variant is generated from it
4. Every test run documented in ENGAGEMENT_LOG.md
5. Novel vulnerabilities disclosed via MSRC within 90 days (VULN-195458 rejected — detection bypasses out of scope)
6. HWBP technique (Finding #36) published openly — embargo void after MSRC rejection
7. Binaries never committed to repo (.gitignore)

### Automation

| Tool | Command | Purpose |
|------|---------|---------|
| `deploy.py` | `python deploy.py --compile` | Build all components |
| `deploy.py` | `python deploy.py --scan` | Defender scan all binaries |
| `deploy.py` | `python deploy.py --deploy` | Full build → scan → deploy |
| `mutate.py` | `python mutate.py` | Rotate all XOR keys + recompile + rescan |
| `mutate.py` | `python mutate.py --status` | Show current keys |
| `mutate.py` | `python mutate.py --dry-run` | Preview without modifying |
| `vader_menu.py` | `python vader_menu.py` | Interactive terminal dashboard |
| `vader_ui.py` | `python vader_ui.py` | Web C2 dashboard (http://0.0.0.0:8666) + agent listener (:8667) |
| `vader_agent.py` | `python vader_agent.py <ip>` | Remote agent client (deploy on target) |
| `cloak/build_cloak.py` | `python cloak/build_cloak.py` | Build cloak.dll + loader + dropper |
| `byovd/build_byovd.py` | `python byovd/build_byovd.py` | Build BYOVD kernel persistence tool |
| `metamorph.py` | `python metamorph.py` | Metamorphic source transforms (Phase 10) |
| `metamorph.py` | `python metamorph.py --intensity high` | Maximum transform density |
| `metamorph.py` | `python metamorph.py --restore` | Restore all sources from backups |
| `vader_evolve.py` | `python vader_evolve.py` | Full pipeline: metamorph → mutate → compile → scan |
| `vader_evolve.py` | `python vader_evolve.py --cycles 3` | Run 3 evolution cycles |
| `vader_evolve.py` | `python vader_evolve.py --scan-only` | Scan all existing binaries |

### Related Repos

| Repo | Purpose |
|------|---------|
| vader-toctou | TOCTOU race condition research — 6 engagements, 30 findings |
| vader-fuzz | mpengine.dll mutation fuzzer — 100K+ iterations |
| vader-library | Forbidden Knowledge — 67 chapters, field manuals, evidence |
| vader-rce | 0-Day RCE research program |
| rainfantry.github.io | Public website — teaching material only, no exploit code |

---

*Built from the ashes of vader-toctou. The wall held, but the scout mapped every brick.*
*Now the scout has a kill chain, a mutation engine, and zero detections.*
