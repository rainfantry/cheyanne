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
- [x] 88/88 binaries CLEAN against Defender RTP
- [x] MSRC VULN-195458 submitted (HWBP blind spot) — rejected, "Won't Fix"
- [x] 100K fuzzing campaign (mpengine.dll) — 0 crashes
- [x] Full documentation (README, BUILD_FROM_ASHES, CODE_WALKTHROUGH, VADER_MANUAL)
- [x] Encrypted backup (7z, password 668340)

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
- [ ] Internet payload (WAN) — port forward or ngrok, compile with public IP
- [ ] Role reversal — Radon as C2 operator, George's machine as target
- [ ] HANDLER model upgrade — test with llama3.1/qwen2.5 for better tool compliance
- [ ] Web dashboard update — integrate Discord C2 sessions into browser UI
- [ ] Steganographic C2 — hide commands in image EXIF/pixel data (ghost encoder extension)

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
