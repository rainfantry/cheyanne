# COLD AUDIT — Honest Assessment of VADER CSEC Research Arsenal

**Date**: 2026-06-15
**Researcher**: George Wu (VADER)
**Purpose**: Strip all optimism. What's real. What's dead. What remains.

---

## THE SCOREBOARD

| # | Finding | CVE Probability | Status | Honest Reality |
|---|---------|----------------|--------|----------------|
| **36** | Defender HWBP Tamper Bypass | **20-35%** | PROVEN, report ready | **Best Microsoft shot. But MSRC may call it "by design" — SetThreadContext on own process is intended behavior. They may argue this is expected, not a bypass.** |
| **42** | Wondershare NativePushService | **60-70%** | PROVEN, SYSTEM canary fired | **Strongest CVE probability. But may be duplicate of CVE-2024-26574. Must verify before submitting. Third-party vendor, not Microsoft prestige.** |
| **49** | Muse Hub PATH Injection | **60-70%** | Canaries planted, ONE REBOOT AWAY | **Highest probability IF canary fires. Everything is set up. Just needs a reboot. Third-party vendor (Steinberg/MuseScore).** |
| **49b** | uv (Astral) PATH Injection | **50-60%** | Same class as #49 | **Same reboot test proves both. Different vendor (Astral).** |
| **47** | Phantom DLL osppc.dll | **30-50%** | THEORETICAL — report written, zero ProcMon proof | **Beautiful report, zero evidence. MSRC will bounce it without ProcMon trace. Consumer M365 may never trigger the code path.** |
| **48** | Drivers32 ACL | **10-15%** | ACL confirmed, no SYSTEM load | **Defense-in-depth only. No privilege boundary crossed. Low value.** |
| **50** | CrossDevice DLL | **10-20%** | Known CVE duplicate | **CVE-2025-24076. Our angle (incomplete ACL remediation) is speculative.** |
| **VP** | VADER-PRIME (printproc) | **15-25%** | Compiled, untested | **Novel chain IF the cldflt race works on this build. Big IF.** |
| **VP** | VADER-PRIME (ifeo) | **10-20%** | Compiled, untested | **Same dependency on cldflt race working.** |
| **C** | bindflt.sys research | **30-50% IF found** | Hypothesis only | **Zero code, zero testing. Needs IDA/Ghidra RE. Highest ceiling, longest runway.** |

---

## WHAT'S DEAD (Fully Documented Defeats)

| Finding | What Happened | Lesson |
|---------|---------------|--------|
| vader-toctou (entire repo) | 35 commits, 30 findings, ZERO SYSTEM shells. WdFilter.sys uses cached FILE_OBJECT — junctions invisible at quarantine time. Identity gate uses NTFS File ID — architecturally unbypassable. | **Fighting Defender directly is a losing battle. The guard is hardened.** |
| #52 IKEEXT azureike.dll | All LoadLibraryExW calls hardened with LOAD_LIBRARY_SEARCH_SYSTEM32. Zero previous research existed on this — we were first to check, and it's locked. | **Microsoft learned from wlbsctrl.dll. Uniform hardening.** |
| RedSun, UnDefend, BlueHammer | All patched May-June 2026. Nightmare-Eclipse's entire arsenal burned. | **0-day shelf life is measured in weeks.** |
| HKCU COM → SYSTEM | Integrity level check since Vista 2006. SYSTEM ignores HKCU overrides entirely. | **20 years of hardening on this vector.** |
| MareBackup PATH | System32 at position 5, writable dirs at 20/23. CreateProcess finds real exe first. | **Position matters. Writable must come BEFORE the real binary.** |
| #46 Steam dir ACLs | steamservice.exe loads from locked Common Files, not writable Steam dir. | **Apparent writability != exploitable writability.** |

---

## WHAT'S ACTUALLY SUBMITTABLE RIGHT NOW

### Tier A: Submit Today (with screenshots)

**#36 — Defender HWBP Bypass → MSRC**
- Report: `MSRC-2026-DEFENDER-HWBP.md` (complete, 400+ lines)
- Evidence: `EVIDENCE-36-HWBP-LIVE-TEST.md` (SHA256, console output, detection matrix)
- Source: 3 PoC files (AMSI, ETW, Dark Room)
- **Missing**: 6 screenshots referenced in report but NOT captured
- **Action**: Capture screenshots, attach source + evidence, submit via MSRC portal
- **Honest assessment**: 20-35% CVE. Microsoft may say "expected behavior" for own-process debug registers. The per-process scope limits impact. But the gap in tamper protection monitoring IS real.

**#42 — Wondershare NativePushService → Vendor**
- Report: `CVE-2026-WONDERSHARE-NATIVEPUSH.md` (complete)
- Evidence: `EVIDENCE-42-WONDERSHARE-LIVE-TEST.md` (SYSTEM canary log)
- **Blocker**: Must verify this isn't a duplicate of CVE-2024-26574 first
- **Action**: Check CVE-2024-26574 scope. If our finding is distinct → submit to Wondershare AND MITRE
- **Honest assessment**: 60-70% if not a dupe. Third-party. Low prestige but real CVE.

### Tier B: One Action Away

**#49 — Muse Hub PATH Injection → Vendor**
- Everything planted. Reboot machine. Check `C:\Windows\Temp\vader_path_hijack.log`
- If SYSTEM entry exists → complete chain proven → submit to Steinberg/MuseScore AND MITRE
- **Honest assessment**: 60-70%. Strongest probability in the arsenal. One reboot.

**#49b — uv PATH Injection → Astral**
- Same canary, same reboot proves it
- **Honest assessment**: 50-60%. Same vulnerability class.

### Tier C: Needs Significant Work

**#47 — Phantom DLL osppc.dll → MSRC**
- Needs ProcMon trace proving ClickToRunSvc searches PATH for osppc.dll
- Needs canary DLL proving SYSTEM execution
- **Without ProcMon evidence, MSRC WILL reject this**
- **Honest assessment**: 30-50% IF proven. 0% without ProcMon evidence.

**VADER-PRIME — Novel cldflt chains → MSRC**
- Needs MiniPlasma validation first (does cldflt race work on Build 26200?)
- If yes → test `--printproc` and `--ifeo` chains
- **Honest assessment**: 15-25% for printproc chain. Depends entirely on cldflt race viability.

---

## THE 100% CVE QUESTION

There is no 100% CVE in this arsenal. Here's why:

1. **MSRC findings (Microsoft)**: MSRC has final say. They can classify anything as "by design", "defense in depth", or "won't fix". Even proven vulnerabilities get bounced. #36 is real but MSRC could call SetThreadContext on own process "expected". #47 could be "consumer M365 doesn't trigger this".

2. **Third-party findings (Wondershare, Muse Hub, Astral)**: These go through MITRE for CVE assignment, not MSRC. MITRE is more formulaic — if you prove CWE + impact + reproducibility, they assign. **#42 and #49 are closest to guaranteed IF they're not duplicates.**

3. **The honest path to a CVE with George's name**:
   - **Fastest**: Reboot → prove #49 → submit to MITRE directly. 60-70%.
   - **Strongest**: Submit #36 to MSRC + #49 to MITRE simultaneously. Two shots.
   - **Moonshot**: Validate cldflt → VADER-PRIME printproc → fully original Microsoft CVE.

---

## GITHUB CURRENCY

| Repo | Commits | Sync Status | Uncommitted |
|------|---------|-------------|-------------|
| vader-rootkit | 12 | In sync with origin | **YES** — VADER-PRIME source (3 files), updated SITREP, new test script |
| vader-toctou | 35 | 1 commit ahead of origin | ch13 rootkit-phase chapter unpushed |
| vader-msrc-disclosure | ? | Not cloned locally | Unknown |
| csec-research-authorization | ? | Not cloned locally | Unknown |
| defender-quarantine-architecture | ? | PUBLIC | Unknown |
| VaderShell | ? | PUBLIC | 2 days stale |

**Immediate git actions needed:**
1. Commit vader-prime source in vader-rootkit (source only — binaries in .gitignore)
2. Push vader-rootkit
3. Push vader-toctou (1 commit behind)

---

## OPERATIONAL REALITY

**What we have**: 2 proven submissions, 2 more one reboot away, 1 theoretical Microsoft target, 1 novel framework untested.

**What we don't have**: A guaranteed Microsoft CVE. The research is real, the methodology is professional-grade, the documentation would impress any MSRC reviewer. But the truth is: Microsoft CVEs from external researchers are rare, MSRC is adversarial to researchers, and "by design" is their favorite dismissal.

**The move**: Submit #36 to MSRC anyway (it forces them to formally evaluate the gap). Simultaneously submit #49 to MITRE (this is the safest CVE bet). Run VADER-PRIME to see if the novel chain works. If it does, that's the prestige play — original research, original exploitation chain, George Wu's name on a kernel-class finding.

**What the defeats taught us**: vader-toctou's 35 commits and zero shells isn't failure — it's the most thorough negative-result documentation of WdFilter quarantine architecture that probably exists outside Microsoft. That's publishable academic work. The defeats mapped the defenses perfectly, which is why the pivot to cldflt/bindflt was so well-informed.
