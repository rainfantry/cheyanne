# 22DIV — SITE & REPO MAP
## Last updated: 2026-06-26 // Machine gwu07 being retired

---

## PUBLIC-FACING (front = 22nd Survey Division)

### Sites (GitHub Pages)
| URL | Repo | Purpose |
|-----|------|---------|
| `rainfantry.github.io` | `rainfantry/rainfantry.github.io` | **Main research portfolio** — personal security research, MSRC disclosure, field manuals, courses |
| `rainfantry.github.io/22nd-survey-division/` | `rainfantry/22nd-survey-division` | **Company portfolio** — 22nd Survey Division front, arsenal showcase, doctrine, contact |

### Site internal pages (rainfantry.github.io)
| Path | Purpose |
|------|---------|
| `/` | Index / hero |
| `/labs/cheyanne.html` | CHEYANNE interactive course |
| `/labs/ghost.html` | Ghost Encoder course |
| `/labs/rootkit.html` | VADER Rootkit / TOCTOU course |
| `/labs/starkiller.html` | StarKiller Android RAT course |
| `/labs/vader.html` | VADER Discord bot / persona course |
| `/labs/kwlinks.js` | Color-coded keyword → book links |
| `/books/reader.html?b=SLUG` | Hidden field manual reader (noindex) |
| `/books/01_OFFENSIVE_MINDSET.md` … | 21 field manual chapters (raw .md, Jekyll passthrough) |
| `/books.html` | Field manual index |

### Public Repos (tools/research — open source)
| Repo | Visibility | What it is |
|------|-----------|------------|
| `rainfantry/winrecon` | PUBLIC | PowerShell privesc audit script |
| `rainfantry/ghost-encoder` | PUBLIC | Unicode steganographic PS1 encoder |
| `rainfantry/defender-quarantine-architecture` | PUBLIC | Windows Defender quarantine research |
| `rainfantry/discord-relay` | PUBLIC | Discord relay utility |

---

## PRIVATE (weapons, ops, intel)

### Active Ops
| Repo | What it is |
|------|-----------|
| `rainfantry/cheyanne` | **CHEYANNE C2 framework** — primary red team tool |
| `rainfantry/starkiller` | Android RAT (Phase 1 complete) |
| `rainfantry/eclipse` | Anti-forensics / OPSEC cleanup |
| `rainfantry/skywalker` | Cold standby kill chain |
| `rainfantry/sith-stalker` | OSINT / stalker module |

### Research & Disclosure
| Repo | What it is |
|------|-----------|
| `rainfantry/vader-rootkit` | Modular rootkit (26 binaries, all clean) |
| `rainfantry/vader-toctou` | TOCTOU exploit study (MSRC VULN-195458) |
| `rainfantry/vader-fuzz` | mpengine.dll mutation fuzzer |
| `rainfantry/cve-submissions` | MSRC / MITRE submission packages |
| `rainfantry/csec-research-authorization` | Authorization docs for AI exemptions |
| `rainfantry/vader-msrc-disclosure` | MSRC disclosure evidence |
| `rainfantry/vader-rce` | 0-day RCE research |

### ASF Tactics (sub-research)
| Repo | What it is |
|------|-----------|
| `rainfantry/asf-infiltration` | DLL search order exploitation |
| `rainfantry/asf-counterintel` | HWBP AMSI bypass |
| `rainfantry/asf-concealment` | XOR obfuscation doctrine |

### Field Manuals / Knowledge
| Repo | What it is |
|------|-----------|
| `rainfantry/vader-library` | Full 67-chapter forbidden knowledge archive |
| `rainfantry/vader-palace` | Operator memory palace / AI context |
| `rainfantry/vader-hunt` | Automated Windows pentesting framework |
| `rainfantry/offsec-vader-assessment` | Full kill chain assessment docs |

### Infrastructure / Tools
| Repo | What it is |
|------|-----------|
| `rainfantry/22DIV` | VADER terminal AI agent |
| `rainfantry/hermes-setup` | Hermes gateway (OpenRouter/Claude) |
| `rainfantry/22div-arsenal` | Arsenal/tools archive |
| `rainfantry/22div-vault` | Archived profile pages |
| `rainfantry/portfoliobackup` | Old portfolio backup |

---

## WHAT TO UPLOAD TO YOUR OWN WEBSITE (future)

### Safe to showcase publicly
- Arsenal cards from `22nd-survey-division` site
- Course lab links (all 5 courses)
- MSRC VULN-195458 disclosure writeup (sanitized)
- winrecon, ghost-encoder (already public)
- defender-quarantine-architecture (already public)
- Field manual chapter excerpts via reader.html

### Keep private / never publish raw
- ghost_fud.exe, svchost_update.exe, ghost_loader.exe (AV bypass — never publish)
- cheyanne, starkiller, eclipse, skywalker source
- PENTEST_LOG.md (target names, IPs, session data)
- .env files, API keys, tokens
- The .7z archives

---

## AI RESEARCH EXEMPTION PACKAGE
To apply to Claude/ChatGPT for cybersecurity research exemptions, submit:

1. **`rainfantry/csec-research-authorization`** — academic authorization docs
2. **MSRC VULN-195458** — evidence of responsible disclosure
3. **`rainfantry/rainfantry.github.io`** — public research portfolio
4. **`rainfantry/22nd-survey-division`** — company/research front
5. **Course labs** (cheyanne, ghost, rootkit, starkiller, vader) — educational context
6. **`rainfantry/cve-submissions`** — MSRC/MITRE packages

Summary statement for exemption:
> *"Independent CSEC student researcher. Academic authorization documented. MSRC responsible disclosure submitted (VULN-195458). All research on own hardware or explicitly authorised targets. No mass targeting. No DoS. Public research portfolio at rainfantry.github.io. Company context: 22nd Survey Division (rainfantry.github.io/22nd-survey-division/)."*

---

## MACHINE GWU07 RETIREMENT CHECKLIST

- [ ] Git push everything from Desktop/cheyanne (DONE with this commit)
- [ ] Confirm `.7z` archives in `.cheyanne/` are committed or backed up
- [ ] Clone `rainfantry/cheyanne` to new machine (NOT to Desktop or watched dirs)
- [ ] Copy `.env` files manually (gitignored, not in repo)
- [ ] Transfer binaries from `.cheyanne/*.7z` to new machine (do NOT rebuild)
- [ ] Verify `python listener.py` works on new machine
- [ ] Update `PENTEST_LOG.md` with new machine IP / new operator IP
- [ ] Port-forward TCP 4443 on new machine for WAN access
