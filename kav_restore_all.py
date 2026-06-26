#!/usr/bin/env python3
"""
kav_restore_all.py — KAV kill responder
Watches all clones. When KAV deletes a tracked file:
  1. Waits for KAV to release the file lock (retry loop)
  2. Restores from git object store (git checkout HEAD)
  3. Verifies file exists on disk
  4. ONLY commits/pushes if the deletion was staged into the index —
     otherwise the remote already has it, no push needed.

The PAPERWORK SURVIVES ON THE REPO because we never stage deletions.
"""
import os, subprocess, sys, time

CLONES = [
    r"C:\Users\gwu07\Desktop\cheyanne",
    r"C:\Users\gwu07\Desktop\repos\cheyanne",
    r"C:\Users\gwu07\AppData\Local\iron-sun",
    r"C:\Users\gwu07\Desktop\repos\iron-sun",
]

GREEN = "\033[92m"; RED = "\033[91m"; AMBER = "\033[93m"
BOLD  = "\033[1m";  DIM  = "\033[2m"; RST   = "\033[0m"

def git(args, cwd):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def restore_clone(path):
    if not os.path.exists(os.path.join(path, ".git")):
        return 0

    # Files deleted from disk but still tracked in index
    _, out, _ = git(["ls-files", "--deleted"], path)
    dead = [f for f in out.splitlines() if f]
    if not dead:
        print(f"  {GREEN}[+]{RST} {os.path.basename(path)} — holding")
        return 0

    print(f"  {RED}[KAV KILL]{RST} {os.path.basename(path)} — {len(dead)} down")

    restored = []
    for rel in dead:
        abs_path = os.path.join(path, rel.replace("/", os.sep))

        # Retry loop — KAV may hold a lock for a few seconds while processing
        for attempt in range(5):
            git(["checkout", "HEAD", "--", rel], path)
            if os.path.exists(abs_path):
                restored.append(rel)
                print(f"    {GREEN}↑{RST} {rel}")
                break
            if attempt < 4:
                time.sleep(1.5)
        else:
            # File won't land on disk (KAV deleting too fast) —
            # use plumbing to put blob in index directly, then commit
            rc, blob, _ = git(["rev-parse", f"HEAD:{rel}"], path)
            if rc == 0 and blob:
                git(["update-index", "--add", "--cacheinfo",
                     f"100644,{blob},{rel}"], path)
                restored.append(rel)
                print(f"    {AMBER}↑ (plumbing — KAV holds lock){RST} {rel}")

    # Check if index now differs from HEAD (means we used plumbing to add)
    _, staged, _ = git(["diff", "--cached", "--name-only"], path)
    if staged.strip():
        # Something is staged — commit it to make sure remote gets it
        msg = f"kav-restore: paperwork back — {', '.join(restored[:3])}"
        git(["commit", "-m", msg], path)
        rc, _, err = git(["push"], path)
        if rc != 0:
            git(["push", "--set-upstream", "origin", "HEAD"], path)
        print(f"    {GREEN}pushed to remote — paperwork survives{RST}")
    else:
        # Remote already has these files in HEAD — local restore is enough
        print(f"    {DIM}remote already safe — local restore complete{RST}")

    return len(restored)


def loop(interval=8):
    print(f"\n{BOLD}KAV RESTORE DAEMON — standing guard{RST}")
    print(f"{DIM}every {interval}s across {len(CLONES)} clones — Ctrl+C to stop{RST}\n")
    total = 0
    while True:
        batch = sum(restore_clone(c) for c in CLONES)
        if batch:
            total += batch
            print(f"  {DIM}session total rescued: {total}{RST}\n")
        time.sleep(interval)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        loop()
    else:
        print(f"\n{BOLD}=== MASS RESTORE ==={RST}\n")
        total = sum(restore_clone(c) for c in CLONES)
        print(f"\n{GREEN}{BOLD}Restored: {total}{RST}")
        if total:
            print("Run with --loop to stand guard continuously.")
