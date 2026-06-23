# CHEYANNE ROADMAP

```
22DIV / george wu
Updated: 2026-06-23
```

---

## DONE

- [x] Phase 0-10: Full rootkit kill chain (C2, AMSI, ETW, privesc, injection, stager, forensics, cloak, BYOVD, metamorph)
- [x] Phase 11: Discord C2 implant (PyInstaller, GDI screenshot, persistence)
- [x] Phase 12: HANDLER AI operator (Ollama/Claude, 8 tools, prompt-based calling)
- [x] Auto-deploy pipeline (compile → serve → deploy → screenshot)
- [x] Menu restructure (Phase 1-4 + Toolkit)
- [x] TCP C2 v2 with shortcuts (deploy, screenshot, watch, kill, recon, persist)
- [x] Dual-payload deploy (Discord implant + TCP shell, XOR-baked IP, zero args)
- [x] Live watch (single while-loop, HTTP POST-back frames, fetch+blob viewer on :8892)
- [x] Screenshot auto-pull (one-shot HTTP receiver on :8891)
- [x] Dual persist (WindowsSecurityHealth + WindowsSecurityUpdate registry keys)
- [x] HANDLER Kimi K2.5 backend via OpenRouter
- [x] `--tcp-cmd` non-interactive mode for web UI integration
- [x] Web dashboard mobile responsive + full terminal parity (all 4 phases + TCP shortcuts)
- [x] `setup_firewall.bat` — permanent rules for all 6 ports
- [x] 88/88 binaries CLEAN against Defender RTP
- [x] MSRC VULN-195458 submitted (HWBP blind spot) — rejected, "Won't Fix"
- [x] 100K fuzzing campaign (mpengine.dll) — 0 crashes
- [x] Full documentation (README, BUILD_FROM_ASHES, CODE_WALKTHROUGH, VADER_MANUAL)
- [x] Encrypted backup (7z, password 668340)
- [x] Bidirectional Discord C2 (operator sends commands, implant polls + responds)
- [x] VCVARS auto-detection via cheyanne_config.py (no manual path editing)
- [x] Persist safety check (warns if deploy not run first)
- [x] Manual audit: 8 inaccuracies fixed in BUILD_FROM_ASHES
- [x] Bootstrap recovery procedure documented (first deploy must be TCP)
- [x] Watch cleanup: kill PowerShell on target after Ctrl+C
- [x] Interactive shell recv fix: trailing read catches split packets
- [x] Multi-session: prompt to select target when multiple sessions online

## NEEDS HUMAN TESTING (code pushed, not yet verified live)
- [ ] Multi-session picker (prompt when no SID given, multiple sessions online)
- [ ] Watch → Ctrl+C → interact flow (PowerShell kill + cmd.exe recovery)
- [ ] Interactive shell output (recv trailing read — should return ghaleb not echo)
- [ ] Discord bidirectional commands (requires fresh svchost_update.exe deployed via TCP first)

---

## NEXT — CVE Submission Package

### 1. DNS Tunneling C2 (Phase 13)
**Why:** Proves the HWBP bypass works across multiple C2 channels. Current Discord C2 is blocked by any network that blocks Discord. DNS tunneling bypasses ALL firewalls because DNS is always allowed.

**Tasks:**
- [ ] DNS server (Python, listen UDP 53)
- [ ] TXT record encoding (base64 payload in DNS queries)
- [ ] Chunked exfiltration (split data across multiple queries)
- [ ] Implant DNS client (replaces Discord webhook with DNS queries)
- [ ] Tunnel shell (interactive command execution over DNS)
- [ ] Detection test: Does Defender flag DNS tunneling traffic? (Probably not — it's network-layer, not endpoint)

**Estimated effort:** 2 sessions (6-10 hours paired work)

### 2. Academic Paper — "Hardware Breakpoint Blind Spot in Windows Defender"
**Why:** CVE requests carry more weight with a published paper. CSEC portfolio piece. Demonstrates systematic research methodology.

**Structure:**
- [ ] Abstract (200 words)
- [ ] Introduction (problem statement, scope)
- [ ] Background (AMSI architecture, ETW pipeline, hardware breakpoints, VEH)
- [ ] Related Work (prior AMSI bypasses — memory patch, unhooking, reflection)
- [ ] Methodology (CSEC lab environment, own hardware, Defender versions tested)
- [ ] Findings
  - Finding #36: HWBP blind spot (DR0-DR3 + VEH, zero memory modification)
  - Finding #42: CWE-732 service binary replacement
  - Finding #47: Phantom DLL (Office osppc.dll)
  - 100K fuzzing campaign results
- [ ] Proof of Concept (sanitized code snippets, not full exploit)
- [ ] MSRC Disclosure Timeline (submitted → acknowledged → rejected → embargo void)
- [ ] Discussion (why this matters, defense-in-depth gap, mitigation recommendations)
- [ ] Conclusion
- [ ] References

**Estimated effort:** 2 sessions (6-10 hours paired work)

### 3. Fuzz Other Windows APIs with HWBP Technique
**Why:** If AMSI/ETW are blind to HWBP, what else is? Finding additional blind spots strengthens the CVE case from "one bypass" to "systemic architectural gap."

**Targets to fuzz:**
- [ ] `NtCreateFile` — can we intercept file creation checks?
- [ ] `NtOpenProcess` — can we blind process protection?
- [ ] `NtWriteVirtualMemory` — can we bypass memory write monitoring?
- [ ] `CryptVerifySignature` — can we bypass signature verification?
- [ ] `WldpQueryDynamicCodeTrust` — can we bypass WDAC/arbitrary code guard?
- [ ] PPL (Protected Process Light) callbacks — can HWBP intercept these?
- [ ] Kernel callback notification routines (from user-mode via BYOVD)

**Approach:** Same HWBP + VEH pattern, DR2/DR3 (DR0/DR1 already used by dark_room). Set breakpoint on target API → intercept in VEH → modify return value → measure if Defender/Windows notices.

**Estimated effort:** 3-4 sessions (10-16 hours paired work)

---

## BACKLOG (Lower Priority)

- [ ] Kernel-mode DKOM — hide from `tasklist`/`netstat` (currently GUI-only via cloak)
- [ ] Anti-analysis — sandbox detection, debugger detection, VM evasion
- [~] Internet payload (WAN) — **IN TEST 2026-06-24**: ngrok tcp tunnel (0.tcp.au.ngrok.io), ghost_loader.exe (steg PS1 in exe, 0 disk writes), testing on owned LAN PC via ngrok WAN path
- [ ] Role reversal — Radon as C2 operator, George's machine as target
- [ ] HANDLER model upgrade — test with llama3.1/qwen2.5 for better tool compliance
- [ ] Web dashboard update — integrate Discord C2 sessions into browser UI
- [ ] Steganographic C2 — hide commands in image EXIF/pixel data (ghost encoder extension)

---

## PHASE 4.5 — WAN C2 (BIDIRECTIONAL DISCORD)

WAN C2 via Discord. TCP shell remains LAN-only (`inet_addr()` = IP-only, no DNS). Bidirectional Discord gives full interactive C2 from anywhere without port forwarding.

### Current State
- **Discord**: WAN, **bidirectional** — operator sends commands via bot API, implant polls and responds
- **TCP**: LAN-only, full interactive (shell, files, screenshot, watch, deploy, persist)
- **Gap**: ~~TCP DNS resolution needed for hostname-based WAN~~ — **FIXED 2026-06-24**: replaced `inet_addr()` with `getaddrinfo()` in vader_shell_annotated.c + live.c. Shell now resolves DDNS hostnames. File transfer via Discord limited to 25MB.

### 1. Bidirectional Discord C2 — DONE

Operator-side implemented in `vader_c2_v2.py`. Implant already had polling. All shortcuts route through Discord when no TCP session.

**Completed:**
- [x] Implant polls a command channel every N seconds for operator messages
- [x] Command execution — runs received command, posts stdout back to channel
- [x] Screenshot on demand via Discord command
- [x] Session management — multiple targets in one channel, target ID prefixes
- [x] Operator-side: `chey>` shell routes commands through Discord when no TCP session available
- [x] Auto-fallback: try TCP first, fall back to Discord if no direct connection

**Remaining:**
- [ ] File transfer via Discord attachments (25MB per message limit)
- [ ] Rate limit handling (Discord API: ~50 req/sec)
- [ ] Auto-fallback: try TCP first, fall back to Discord if no direct connection

**Estimated effort:** 1-2 sessions (4-8 hours)

### 2. TCP Shell DNS Resolution

**Why:** `inet_addr()` on line 143 of vader_shell_annotated.c only handles dotted-quad IPs. Replace with `getaddrinfo()` to resolve hostnames. Then compile with a DDNS domain instead of a raw IP.

**Tasks:**
- [ ] Replace `inet_addr(c2ip)` with `getaddrinfo()` in C source
- [ ] Fresh Build accepts hostname or IP for `--compile-shell`
- [ ] DDNS auto-update script (DuckDNS/No-IP — free tier)
- [ ] Public IP auto-detect option in Fresh Build (`curl ifconfig.me`)
- [ ] Fallback chain: domain → public IP → LAN IP

**Estimated effort:** 1 session (2-4 hours)

### 3. Port Multiplexing

**Why:** Currently 6 ports open. Over WAN, fewer ports = less exposure. Multiplex all traffic over a single port (4443).

**Tasks:**
- [ ] Protocol header byte to distinguish C2/screenshot/watch/file/agent traffic
- [ ] Single-port listener with traffic routing
- [ ] Reduce firewall surface to one port

**Estimated effort:** 1 session (3-5 hours)

---

## PHASE 5 — FULL REMOTE ACCESS

Full sensory control of the target. Webcam, mic, desktop — all through the same HTTP POST-back architecture proven by watch/screenshot.

### 1. Webcam Capture (Photo + Live Stream)

**Why:** Screenshot gives the screen. Webcam gives the room. Same POST-back pattern as watch — target captures frames, POSTs to operator, browser viewer refreshes.

**Tasks:**
- [ ] Single photo capture via PowerShell (`System.Windows.Media.Imaging` or DirectShow)
- [ ] Live stream mode — while-loop captures frames, HTTP POSTs to operator on `:8891`
- [ ] Browser viewer on `:8892` — same fetch+blob pattern as watch
- [ ] `chey> cam` shortcut for single photo
- [ ] `chey> camwatch` / `chey> camwatch 3` for live stream with configurable interval
- [ ] Front/rear camera selection (if multiple devices)
- [ ] Menu + web dashboard integration (Phase 4 operate)

**Estimated effort:** 1 session (3-5 hours)

### 2. Full VNC — Remote Desktop with Input Relay

**Why:** Watch is view-only. VNC adds keyboard and mouse input — full interactive control of the target desktop from the operator's browser.

**Tasks:**
- [ ] Target-side input receiver — PowerShell/C agent accepts mouse move/click/key events over TCP or WebSocket
- [ ] Operator-side browser UI — canvas-based desktop viewer with mouse capture and keyboard forwarding
- [ ] Frame compression — JPEG quality scaling based on bandwidth
- [ ] Cursor overlay rendering on operator viewer
- [ ] Input encoding protocol (mouse: x,y,button,action; keyboard: keycode,action)
- [ ] Latency optimization — frame delta encoding or dirty-rect detection
- [ ] `chey> vnc` shortcut to start interactive session
- [ ] WebSocket upgrade path (HTTP POST-back too slow for interactive use)

**Estimated effort:** 2-3 sessions (8-12 hours)

### 3. Mic Recording + Exfil

**Why:** Audio surveillance. Record ambient sound from target mic, exfil the file or stream live.

**Tasks:**
- [ ] PowerShell mic capture via `NAudio` or `System.Media.SoundRecorder` / WinRT AudioGraph
- [ ] Timed recording — `chey> mic 30` records 30 seconds
- [ ] File exfil — POST WAV/MP3 back to operator HTTP receiver
- [ ] Live stream mode — chunked audio POST-back (opus/wav segments)
- [ ] Operator playback — browser `<audio>` element or local file open
- [ ] `chey> mic` shortcut for default 10s recording
- [ ] `chey> micstream` for continuous live audio
- [ ] Menu + web dashboard integration

**Estimated effort:** 1-2 sessions (4-8 hours)

---

## CVE SUBMISSION TIMELINE

```
Week 1:  DNS tunneling C2 (build + test)
Week 2:  Fuzz other APIs (build harness + first targets)
Week 3:  Fuzz continued + academic paper draft
Week 4:  Paper review + CVE submission to MITRE
```

**Total estimated: 7-10 sessions across 4 weeks**

MITRE CVE assignment typically takes 2-8 weeks after submission. Paper can be submitted to arXiv or a security conference simultaneously.

---

*For Cheyanne. Always.*
