# מצב כוחות — FORCE STATUS ASSESSMENT

```
סיווג:          לא מסווג // פנימי
CLASSIFICATION:  UNCLASSIFIED // INTERNAL USE
UNIT:            22DIV / VADER
OPERATOR:        george wu
DATE:            21 JUN 2026
SUBJECT:         Capability parity assessment vs Tier-1 CNO platforms
REFERENCE:       Unit 8200 / NSO Group (Pegasus) / Candiru (Saito Tech)
DISTRIBUTION:    MENTOR EYES ONLY
```

---

## 1. SITUATION

Single operator. Six months. Four tools built from first principles against live endpoint protection on personal hardware. No frameworks borrowed. No code copied. Every technique understood at the byte level before implementation.

This document provides an honest operational capability assessment against the techniques attributed to Israeli Computer Network Operations (CNO) units — military (8200) and commercial (NSO/Candiru). The comparison is unfair by design. That's the point.

---

## 2. ORDER OF BATTLE — TOOL INVENTORY

| Designation | Domain | LOC | Assets | Detection Rate | Operational Status |
|-------------|--------|-----|--------|----------------|--------------------|
| VADER | Windows implant framework | 10K+ | 80 binaries | 0/80 | 11 phases, 19 engagements, 70 findings |
| SithStalker | Indirect syscall engine + concealment | 5,175 | 13 resolved functions | CLEAN | Gate v1+v2, user-mode hooks, kernel DKOM |
| SkyWalker | Cold standby / burndown reserve | 14,282 | 18 binaries | 0/18 | Signature-isolated VADER clone |
| StarKiller | Mobile RAT (Android) | 3,229 | Phase 1 | Untested live | 17 ops, Kotlin client |

**Combined output:** ~33,000 lines of original offensive code across Windows + Android.

---

## 3. CAPABILITY MATRIX

```
TECHNIQUE                    SELF-ASSESSMENT     GAP ANALYSIS
─────────────────────────────────────────────────────────────────
AMSI/ETW Neutralisation      ██████████  95%     MINIMAL
  Technique parity. HWBP on DR0/DR1 via VEH.
  Zero memory modification. MSRC rejected (VULN-195458).
  Gap: they do it from ring-0. We do it from ring-3.

Indirect Syscalls            █████████░  90%     MINIMAL
  Hell's Gate + Halo's Gate. DJB2 hash. XOR-encrypted.
  8 gadgets per function, rotated per call.
  Gap: 2 stub variants. A funded team generates thousands.

User-Mode Concealment        █████████░  90%     MINIMAL
  NtQuerySystemInformation hook (process hiding)
  NtQueryDirectoryFile hook (5 info classes, file hiding)
  NtDeviceIoControlFile hook (connection hiding)
  System-wide delivery via SetWindowsHookEx CBT.
  Gap: delivery method. They use kernel callbacks.

  NOTE: The 16-byte SharedUserData instruction boundary
  fix on 24H2 is the kind of finding that separates
  "read a blog" from "debugged it on a live system."

Kernel DKOM                  ████████░░  80%     MEDIUM
  BYOVD via RTCore64.sys (CVE-2019-16098).
  EPROCESS ActiveProcessLinks unlink.
  Gap: they may have custom-signed kernel drivers
  or proprietary kernel exploits. We use known BYOVD.
  Same technique as Lazarus, FIN7, BlackByte.

Signature Evasion            █████████░  85%     LOW
  Dual-toolset architecture (VADER + SkyWalker).
  Independent XOR keys, independent binary names.
  Metamorphic engine: 8 transform types.
  Evolution pipeline: metamorph→mutate→compile→scan.
  Gap: scale. They have build farms. We have mutate.py.

Privilege Escalation         ██████░░░░  60%     HIGH
  CWE-732 (service binary replace)
  CWE-427 (phantom DLL loading)
  CWE-426 (PATH DLL hijack)
  Gap: known CWE classes vs 0-day chains. They don't
  rely on misconfigurations. They bring their own door.

C2 / Transport               █████░░░░░  50%     HIGH
  Length-prefixed JSON over TCP. 17 agent ops.
  Web dashboard. Multi-client listener. JSONL logging.
  Gap: raw TCP + XOR won't survive a SOC.
  They use HTTPS + domain fronting through CDNs.
  Path to close: 2-4 weeks engineering. Architecture supports it.

Mobile (StarKiller)          ████░░░░░░  40%     VERY HIGH
  17 ops. Python C2. Kotlin client. Obfuscation layer.
  Gap: manual APK install vs zero-click exploit chain.
  Pegasus can compromise a phone with a missed call.
  Not realistically closable by one operator.

Zero-Day Research            ██░░░░░░░░  20%     CRITICAL
  MSRC submission (VULN-195458) — technique rejected
  as "not a security boundary." Fuzzing framework exists
  (vader-fuzz) but needs coverage-guided feedback.
  Gap: they stockpile 5-10 active 0-days at any time.
  Each one costs $500K-2M on the open market.

Operational Scale            ███░░░░░░░  30%     HIGH
  One operator. Manual testing. Python automation.
  Gap: they have teams, build farms, QA pipelines,
  dedicated AV-bypass engineers, and decades of
  institutional knowledge.
```

---

## 4. COMPOSITE ASSESSMENT

```
                    ██████░░░░  64%
```

**Translation in operational terms:**

The platform demonstrates technique-level parity in the areas where craftsmanship matters most — the close-in work. AMSI/ETW neutralisation, indirect syscall resolution, user-mode concealment, kernel DKOM. These are not theoretical implementations. They are tested, debugged, and verified against live endpoint protection across 19 documented engagements.

The gaps cluster around resources, not understanding. Zero-day research requires either a massive fuzzing infrastructure or access to the vulnerability market. Transport security requires engineering time. Scale requires headcount. Mobile zero-click requires an exploit research team.

None of these gaps indicate architectural mistakes. They indicate the difference between one soldier and a battalion.

---

## 5. WHAT THIS PLATFORM DOES THAT THEY DON'T

This section exists because it matters.

**א. Documentation.** 70 findings across 19 engagements, every test documented to reporting standard. Most nation-state implants have no documentation at all. VADER's engagement log is more thorough than most corporate penetration test reports.

**ב. Open methodology.** MSRC submission. Responsible disclosure attempt. Published technique after rejection. This is ethical research infrastructure that state actors don't build — because they don't want accountability.

**ג. First-principles construction.** Every line written from scratch. No framework dependencies. No GitHub copy-paste. The operator understands every byte. This is not true of every engineer at NSO working on inherited codebases they didn't design.

**ד. Dual-toolset architecture.** VADER + SkyWalker with independent mutation pipelines is operationally sophisticated. Many real APT groups — including some attributed to nation-states — use a single toolset and get burned when it's signatured. The cold standby doctrine is a force multiplier.

---

## 6. THE FIVE GAPS — PATH FORWARD

### GAP 1: ZERO-DAY CAPABILITY — CRITICAL ⬤

**Current state:** No novel vulnerabilities discovered. MSRC submission was a technique demonstration, not a vulnerability.

**Path forward:** Coverage-guided fuzzing campaigns against Windows attack surface (mpengine.dll, WdFilter.sys). vader-fuzz framework exists. Needs feedback loop + corpus refinement. Estimated: 3-6 months dedicated research for first actionable finding.

**The hard truth:** A single 0-day exploit chain would move this assessment from 64% to ~75% overnight. It is the single highest-leverage gap to close.

### GAP 2: TRANSPORT SECURITY — HIGH ⬤

**Current state:** Raw TCP with XOR encoding. Functional but not operational against network monitoring.

**Required:** TLS 1.3. HTTPS transport. Domain fronting or CDN abuse. DNS-over-HTTPS fallback. Traffic shaping to mimic legitimate patterns.

**Path forward:** Engineering work. The C2 architecture (length-prefixed JSON) is transport-agnostic by design. Wrapping it in HTTPS is mechanical. 2-4 weeks.

### GAP 3: OPERATIONAL SCALE — MEDIUM ⬤

**Current state:** One operator. Manual workflows. Python automation.

**Path forward:** Already partially addressed. deploy.py automates compilation + scanning + deployment. vader_evolve.py chains the mutation pipeline. pentest_report.py logs engagements. The next step is CI/CD-style automated build + scan + fingerprint on every commit.

### GAP 4: MOBILE ZERO-CLICK — HIGH ⬤

**Current state:** StarKiller requires manual APK installation. Social engineering or physical access.

**Path forward:** Not realistically closable by one operator. Focus StarKiller on social-engineering delivery scenarios. Zero-click mobile exploit research requires a dedicated team and access to mobile 0-days ($1M+ per chain).

### GAP 5: KERNEL PERSISTENCE — MEDIUM ⬤

**Current state:** BYOVD approach using known vulnerable drivers (RTCore64.sys).

**Path forward:** Custom kernel driver development is deep specialisation. The BYOVD approach is pragmatic and used by real APT groups. Finding a novel vulnerable signed driver would be a significant win. The existing approach is operationally valid.

---

## 7. ASSESSMENT SUMMARY

For a single operator — 29, self-taught, six months of focused work — this is exceptional output. The comparison to Unit 8200 (thousands of personnel, billions in budget, decades of institutional knowledge) is inherently asymmetric.

What matters is not the composite percentage. What matters is this:

The foundation is architecturally sound. The methodology is rigorous. The documentation exceeds professional standards. The operator understands every technique at the implementation level, not just the concept level. The path forward is clear and achievable.

One scout with good maps outperforms a platoon that can't read them.

---

```
סוף הדו"ח
END OF REPORT

22DIV / VADER
כ"ה בסיון תשפ"ו
21 JUN 2026
```
