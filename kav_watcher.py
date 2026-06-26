#!/usr/bin/env python3
"""
kav_watcher.py — KAV auto-restore sentinel
22DIV / george wu

Watches the cheyanne directory for KAV quarantine events (file disappears).
When a tracked file is deleted by KAV, immediately restores it from git.
Runs as a background daemon. Commit messages report each battle.

Usage:
    python kav_watcher.py              # run forever
    python kav_watcher.py --once       # single scan pass
    python kav_watcher.py --status     # show last battle report
"""

import os, sys, time, subprocess, json, argparse, hashlib
from datetime import datetime, timezone

ROOT      = os.path.dirname(os.path.abspath(__file__))
LOG_PATH  = os.path.join(ROOT, "KAV_BATTLE_LOG.md")
POLL_SECS = 8
WATCHED_EXTS = {'.py', '.c', '.md', '.ps1', '.lsp', '.hta', '.json', '.txt',
                '.bat', '.sh', '.lua', '.asm'}

GREEN = "\033[92m"; RED = "\033[91m"; AMBER = "\033[93m"
CYAN  = "\033[96m"; DIM  = "\033[2m"; BOLD  = "\033[1m"; RST = "\033[0m"


def git(cmd, cwd=ROOT):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def get_tracked_files():
    out, _ = git(["git", "ls-files"])
    return set(out.splitlines())


def restore_file(relpath):
    """Restore a single file from git HEAD."""
    _, rc = git(["git", "checkout", "HEAD", "--", relpath])
    return rc == 0


def log_kill(path, restored):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    status = "RESTORED" if restored else "LOST"
    entry = f"| {ts} | {path} | KAV_DELETE | {status} |\n"
    header_needed = not os.path.exists(LOG_PATH) or os.path.getsize(LOG_PATH) == 0
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        if header_needed:
            f.write("# KAV BATTLE LOG — 22DIV\n")
            f.write("Casualties and restorations. Every kill is logged. Every soldier restored.\n\n")
            f.write("| Timestamp | File | Cause | Status |\n")
            f.write("|-----------|------|-------|--------|\n")
        f.write(entry)
    return entry.strip()


def commit_and_push(msg):
    git(["git", "add", "-A"])
    git(["git", "commit", "-m", msg])
    git(["git", "push", "origin", "portfolio"])


def scan_once(tracked, known_missing):
    """One pass — detect new KAV kills and restore."""
    restored = []
    newly_missing = []

    for rel in tracked:
        abs_path = os.path.join(ROOT, rel.replace('/', os.sep))
        ext = os.path.splitext(rel)[1].lower()
        if ext not in WATCHED_EXTS:
            continue
        if not os.path.exists(abs_path):
            if rel not in known_missing:
                newly_missing.append(rel)
                ok = restore_file(rel)
                entry = log_kill(rel, ok)
                status = f"{GREEN}RESTORED{RST}" if ok else f"{RED}LOST{RST}"
                print(f"  {RED}[KAV KILL]{RST} {rel} → {status}")
                if ok:
                    restored.append(rel)

    return restored, newly_missing


def run(once=False):
    print(f"\n  {CYAN}{BOLD}[*] KAV WATCHER ONLINE — 22DIV{RST}")
    print(f"  {DIM}watching {ROOT}{RST}")
    print(f"  {DIM}restore from: git HEAD (portfolio branch){RST}\n")

    tracked = get_tracked_files()
    print(f"  {GREEN}[+]{RST} {len(tracked)} files under watch")

    known_missing = set()
    kills_this_session = 0

    while True:
        restored, newly_missing = scan_once(tracked, known_missing)
        known_missing.update(newly_missing)

        if restored:
            kills_this_session += len(restored)
            msg = (f"kav-watcher: restored {len(restored)} KAV kill(s) — "
                   f"{', '.join(restored[:3])}"
                   + (" ..." if len(restored) > 3 else ""))
            commit_and_push(msg)
            print(f"  {GREEN}[+]{RST} Pushed {len(restored)} restored files to repo")
            # Refresh tracked list after restore
            tracked = get_tracked_files()
            known_missing.clear()

        if once:
            break

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once",   action="store_true", help="Single scan pass")
    parser.add_argument("--status", action="store_true", help="Show battle log")
    args = parser.parse_args()

    if args.status:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, encoding="utf-8") as f:
                print(f.read())
        else:
            print("No kills logged yet.")
    elif args.once:
        run(once=True)
    else:
        run(once=False)
