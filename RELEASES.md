# IRON-SUN — RELEASE LOG

All forks and operations are logged here chronologically.
NEVER delete entries. Dead ops stay in the log.

---

## IRON-SUN — 2026-06-26 — MOTHER REPO

- **Type**: Origin / Template
- **Repo**: https://github.com/rainfantry/iron-sun (PRIVATE)
- **Status**: BATTLE-TESTED — DO NOT MODIFY CORE
- **Machine**: RADON (GIGABYTE G7 GD, Ghaleb Jomma account, Win11 26200)

### What was battle-tested
- vader_shell.c → gcc 15.2 → 319KB → Defender CLEAN (static + behavioral)
- Kaspersky flags MSVC build only (PE signature diff) — gcc build evades
- HWBP bypass: Tamper Protection OFF on RADON, DR0/DR1 available
- 28 vader-rootkit binaries Defender-clean (prior campaign)

### Mentor doctrine applied (asi dev — IDF Staff Sergeant First Class)
- Replaced Discord C2 transport architecture with pure TCP design
- 20fps VNC stream architecture specified (pending implementation)
- Iron-Sun banner: Australian Army Rising Sun badge with IDF ✡ enshrouded

### v1.0.0 — 2026-06-26
- Initial release from cheyanne base
- Banners replaced: vader_c2_v2.py, vader_listener.py, discord_c2.py, vader_menu.py, vader_ui.py
- README: full cross-machine SITREP format
- designate.py: auto-fork callsign generator
- INSTALL.md: complete cold-start guide

---

## PROOF — RADON LIVE TEST — 2026-06-26 11:43

- **Screenshot**: `docs/PROOF_iron_sun_radon_20260626.png`
- **Machine**: RADON (GIGABYTE G7 GD, Ghaleb Jomma, Win11 26200)
- **Python**: 3.14.6 via Scoop (no admin)
- **Banner**: Rising Sun + ✡ (IDF Star of David) — gold/blue ANSI, CONFIRMED RENDERING
- **Callsign generated**: `hermon-bushranger` (RADON fingerprint 2026-06-26 11:xx)
- **Build state**: vader_shell.c → gcc 15.2 → 319KB → Defender CLEAN
- **SSH push**: rainfantry/iron-sun — OK
- **Tag**: v1.0.0

---

*Forks created by `python designate.py --create` are appended below this line.*
