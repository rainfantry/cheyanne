#!/usr/bin/env python3
"""
kav_restore_all.py — emergency mass restore
Run this any time KAV kills soldiers. Restores ALL tracked files from git HEAD
across all known cheyanne/iron-sun clone locations.
"""
import os, subprocess, sys

CLONES = [
    r"C:\Users\gwu07\Desktop\cheyanne",
    r"C:\Users\gwu07\Desktop\repos\cheyanne",
    r"C:\Users\gwu07\AppData\Local\iron-sun",
    r"C:\Users\gwu07\Desktop\repos\iron-sun",
]

GREEN = "\033[92m"; RED = "\033[91m"; BOLD = "\033[1m"; RST = "\033[0m"

def restore_clone(path):
    if not os.path.exists(os.path.join(path, ".git")):
        print(f"  {RED}[!]{RST} {path} — not a git repo, skipping")
        return 0

    r = subprocess.run(["git", "ls-files", "--deleted"],
                       cwd=path, capture_output=True, text=True)
    dead = [f for f in r.stdout.strip().splitlines() if f]

    if not dead:
        print(f"  {GREEN}[+]{RST} {path} — no casualties")
        return 0

    print(f"  {RED}[KAV KILL]{RST} {path} — {len(dead)} dead: {', '.join(dead)}")
    subprocess.run(["git", "checkout", "HEAD", "--"] + dead,
                   cwd=path, capture_output=True)
    print(f"  {GREEN}[+]{RST} {len(dead)} restored")
    return len(dead)

if __name__ == "__main__":
    print(f"\n{BOLD}=== MASS RESTORE — all known clones ==={RST}\n")
    total = 0
    for c in CLONES:
        total += restore_clone(c)
    print(f"\n{GREEN}{BOLD}Total restored: {total}{RST}\n")
    if total:
        print("Run this again in 10s to confirm KAV hasn't killed them again.")
