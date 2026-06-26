#!/usr/bin/env python3
"""
designate.py — Iron-Sun Operation Fork Designator

Run this on any new machine to fork iron-sun into a new private repo
with an auto-generated callsign. Each operation gets a unique identity.
The mother repo (iron-sun) is NEVER written to — only read from.

Usage:
    python designate.py              # Generate callsign only (preview)
    python designate.py --create     # Generate + create private GitHub repo + push
    python designate.py --callsign kfir-digger --create  # Force specific callsign

Requirements:
    - gh CLI authenticated (gh auth login)
    - git + SSH key configured for GitHub
    - Run from inside the iron-sun repo root
"""

import os
import sys
import socket
import hashlib
import subprocess
import argparse
from datetime import datetime

# ── CALLSIGN POOLS ───────────────────────────────────────────────────────────
# IDF-themed words (Hebrew military geography + warrior terms)
_IDF = [
    "kfir",      # lion cub (IDF fighter jet)
    "tavor",     # IDF bullpup rifle, also Mt Tabor
    "golan",     # Golan Heights
    "hermon",    # Mt Hermon (IDF northern outpost)
    "carmel",    # Mt Carmel
    "negev",     # Negev desert + IDF machine gun
    "galil",     # Galilee + IDF assault rifle
    "gibbor",    # warrior (Hebrew)
    "tzuk",      # cliff/rock (Operation Protective Edge)
    "ofek",      # horizon (Israeli satellite series)
    "keshet",    # bow/rainbow (Hebrew)
    "ariel",     # lion of God
    "gilad",     # eternal joy (Hebrew warrior name)
    "gideon",    # IDF operation + biblical warrior
    "dagan",     # Israeli grain deity, also MOSSAD chief
    "nimrod",    # mighty hunter (Hebrew)
    "samal",     # sergeant (IDF rank)
    "tzabar",    # native-born Israeli (sabra cactus)
    "sinai",     # Sinai Peninsula
    "shaked",    # almond tree (IDF operation)
]

# AUS Army themed words (ANZAC history + Australian military culture)
_AUS = [
    "digger",       # Australian/NZ soldier
    "anzac",        # Australian and NZ Army Corps
    "kokoda",       # Kokoda Track WWII (AUS defining battle)
    "tobruk",       # Siege of Tobruk
    "gallipoli",    # Gallipoli WWII
    "slouch",       # slouch hat (AUS Army iconic headgear)
    "bushranger",   # AUS outlaw warrior tradition
    "cobber",       # mate (Australian slang)
    "wren",         # AUS Women's Royal Naval Service
    "rats",         # Rats of Tobruk (legendary AUS unit)
    "lance",        # lancers (AUS cavalry)
    "swagman",      # wandering AUS worker (Waltzing Matilda)
    "brumby",       # wild horse (AUS special forces slang)
    "boomerang",    # returns to origin (AUS symbol)
    "dingo",        # AUS native dog + AUS Army vehicle
    "dundee",       # Crocodile Dundee (cultural icon)
    "eureka",       # Eureka Stockade (AUS uprising)
    "anzio",        # Anzio beachhead (AUS role in Italy)
    "mateship",     # AUS military brotherhood doctrine
    "outback",      # the unconquered frontier
]


def _generate_callsign() -> str:
    """
    Generate a deterministic-but-unique callsign from machine fingerprint.
    Same machine on same day = same callsign. Different machine = different.
    Override with --callsign flag if you want a specific name.
    """
    fp = f"{socket.gethostname()}:{datetime.now().strftime('%Y%m%d%H')}"
    h = hashlib.sha256(fp.encode()).hexdigest()
    idf_idx = int(h[0:4], 16) % len(_IDF)
    aus_idx  = int(h[4:8], 16) % len(_AUS)
    return f"{_IDF[idf_idx]}-{_AUS[aus_idx]}"


def _run(cmd: list, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _gh_create(callsign: str) -> bool:
    """Create private GitHub repo with the callsign as name."""
    print(f"  [*] Creating private repo: rainfantry/{callsign}")
    r = _run(["gh", "repo", "create", callsign,
               "--private", "--description",
               f"IRON-SUN fork — callsign {callsign} — 22DIV research"],
              check=False)
    if r.returncode != 0:
        print(f"  [!] gh error: {r.stderr.strip()}")
        return False
    print(f"  [+] Repo created: https://github.com/rainfantry/{callsign}")
    return True


def _git_push(callsign: str) -> bool:
    """Add remote and push all branches."""
    remote_url = f"git@github.com:rainfantry/{callsign}.git"
    print(f"  [*] Adding remote '{callsign}' → {remote_url}")
    _run(["git", "remote", "remove", callsign], check=False)
    _run(["git", "remote", "add", callsign, remote_url])

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    print(f"  [*] Pushing {branch} → {callsign}")
    r = _run(["git", "push", callsign, branch], check=False)
    if r.returncode != 0:
        print(f"  [!] Push error: {r.stderr.strip()}")
        return False
    print(f"  [+] Pushed. Repo live: https://github.com/rainfantry/{callsign}")
    return True


def _update_sitrep(callsign: str):
    """Append fork event to RELEASES.md."""
    entry = (
        f"\n## {callsign.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"- Fork of iron-sun\n"
        f"- Host: {socket.gethostname()}\n"
        f"- Repo: https://github.com/rainfantry/{callsign}\n"
        f"- Status: ACTIVE\n"
    )
    releases_path = os.path.join(os.path.dirname(__file__), "RELEASES.md")
    with open(releases_path, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"  [+] Fork logged in RELEASES.md")


def main():
    parser = argparse.ArgumentParser(description="Iron-Sun Operation Designator")
    parser.add_argument("--callsign", default=None,
                        help="Force a specific callsign (default: auto-generated)")
    parser.add_argument("--create", action="store_true",
                        help="Create GitHub repo + push (default: preview only)")
    args = parser.parse_args()

    callsign = args.callsign or _generate_callsign()

    print()
    print(f"  ╔══════════════════════════════════════════╗")
    print(f"  ║  IRON-SUN DESIGNATOR                    ║")
    print(f"  ║  Callsign: {callsign:<30}║")
    print(f"  ║  Repo:     rainfantry/{callsign:<19}║")
    print(f"  ╚══════════════════════════════════════════╝")
    print()

    if not args.create:
        print("  [i] Preview only. Run with --create to forge the repo.")
        print(f"  [i] Command: python designate.py --callsign {callsign} --create")
        print()
        return

    if not _gh_create(callsign):
        sys.exit(1)
    if not _git_push(callsign):
        sys.exit(1)
    _update_sitrep(callsign)

    print()
    print(f"  [✓] Operation {callsign.upper()} forged.")
    print(f"      Clone on new machine:")
    print(f"      git clone git@github.com:rainfantry/{callsign}.git")
    print()


if __name__ == "__main__":
    main()
