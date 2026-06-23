"""
steg_demo.py — Steganography demo (text + image)
22DIV / george wu

Zero-width Unicode steganography: hides arbitrary data inside
normal-looking text. `type` or `cat` shows the cover text.
The payload is invisible.

Usage:
    python steg_demo.py encode "secret message" cover.txt output.txt
    python steg_demo.py decode output.txt
    python steg_demo.py encode-file payload.exe cover.txt output.txt
    python steg_demo.py decode-file output.txt extracted.exe
    python steg_demo.py img-encode payload.exe cover.png output.png
    python steg_demo.py img-decode output.png extracted.exe
"""

import sys
import os
import base64
import struct

# zero-width chars — invisible in terminals and text editors
ZW_ZERO = '​'   # zero-width space      = bit 0
ZW_ONE  = '‌'   # zero-width non-joiner  = bit 1
ZW_SEP  = '‍'   # zero-width joiner      = byte separator
ZW_MARK = '﻿'   # BOM / zero-width no-break space = start/end marker


def bytes_to_zw(data):
    zw = ZW_MARK
    for byte in data:
        for i in range(7, -1, -1):
            bit = (byte >> i) & 1
            zw += ZW_ONE if bit else ZW_ZERO
        zw += ZW_SEP
    zw += ZW_MARK
    return zw


def zw_to_bytes(zw_str):
    chars = []
    inside = False
    for c in zw_str:
        if c == ZW_MARK:
            if inside:
                break
            inside = True
            continue
        if inside and c in (ZW_ZERO, ZW_ONE, ZW_SEP):
            chars.append(c)

    bits = []
    result = bytearray()
    for c in chars:
        if c == ZW_SEP:
            if len(bits) == 8:
                val = 0
                for b in bits:
                    val = (val << 1) | b
                result.append(val)
            bits = []
        elif c == ZW_ZERO:
            bits.append(0)
        elif c == ZW_ONE:
            bits.append(1)
    return bytes(result)


def encode_text(secret, cover_path, output_path):
    with open(cover_path, 'r', encoding='utf-8') as f:
        cover = f.read()

    zw_payload = bytes_to_zw(secret.encode('utf-8'))

    lines = cover.split('\n')
    if len(lines) >= 2:
        lines[0] = lines[0] + zw_payload
    else:
        lines.append(zw_payload)

    steg_text = '\n'.join(lines)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(steg_text)

    print(f"[+] Encoded {len(secret)} chars into {output_path}")
    print(f"    Cover size: {len(cover)} chars")
    print(f"    Output size: {len(steg_text)} chars")
    print(f"    Overhead: {len(steg_text) - len(cover)} invisible chars added")
    print(f"\n[*] Try: type {output_path}")
    print(f"    Looks identical to the original. Payload is invisible.")


def decode_text(steg_path):
    with open(steg_path, 'r', encoding='utf-8') as f:
        content = f.read()

    extracted = zw_to_bytes(content)
    if extracted:
        print(f"[+] Hidden message found ({len(extracted)} bytes):")
        print(f"    {extracted.decode('utf-8', errors='replace')}")
    else:
        print("[-] No hidden data found.")


def encode_file(payload_path, cover_path, output_path):
    with open(payload_path, 'rb') as f:
        payload = f.read()

    b64 = base64.b64encode(payload)

    with open(cover_path, 'r', encoding='utf-8') as f:
        cover = f.read()

    zw_payload = bytes_to_zw(b64)

    lines = cover.split('\n')
    lines[0] = lines[0] + zw_payload

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"[+] Encoded {len(payload)} bytes ({len(b64)} b64) into {output_path}")
    print(f"    Cover: {cover_path} ({len(cover)} chars)")
    print(f"    Payload hidden in zero-width Unicode characters")
    print(f"    `type {output_path}` shows only the cover text")


def decode_file(steg_path, output_path):
    with open(steg_path, 'r', encoding='utf-8') as f:
        content = f.read()

    b64_data = zw_to_bytes(content)
    if not b64_data:
        print("[-] No hidden data found.")
        return

    payload = base64.b64decode(b64_data)
    with open(output_path, 'wb') as f:
        f.write(payload)

    print(f"[+] Extracted {len(payload)} bytes to {output_path}")


def img_encode(payload_path, cover_path, output_path):
    with open(cover_path, 'rb') as f:
        img_data = f.read()

    with open(payload_path, 'rb') as f:
        payload = f.read()

    # append after image EOF
    # works for PNG (IEND chunk), JPEG (FFD9), BMP, etc.
    # image viewers read up to EOF marker and ignore the rest
    marker = b'<<CHEYANNE>>'
    size_bytes = struct.pack('<I', len(payload))

    steg = img_data + marker + size_bytes + payload

    with open(output_path, 'wb') as f:
        f.write(steg)

    print(f"[+] Image steg: {payload_path} ({len(payload)} bytes) hidden in {output_path}")
    print(f"    Cover image: {len(img_data)} bytes")
    print(f"    Output image: {len(steg)} bytes")
    print(f"    The image opens normally in any viewer.")
    print(f"    Payload is appended after the image EOF marker.")


def img_decode(steg_path, output_path):
    with open(steg_path, 'rb') as f:
        data = f.read()

    marker = b'<<CHEYANNE>>'
    idx = data.find(marker)
    if idx == -1:
        print("[-] No hidden payload found in image.")
        return

    size_offset = idx + len(marker)
    payload_size = struct.unpack('<I', data[size_offset:size_offset+4])[0]
    payload = data[size_offset+4:size_offset+4+payload_size]

    with open(output_path, 'wb') as f:
        f.write(payload)

    print(f"[+] Extracted {len(payload)} bytes from image to {output_path}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "encode" and len(sys.argv) >= 5:
        encode_text(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "decode" and len(sys.argv) >= 3:
        decode_text(sys.argv[2])
    elif cmd == "encode-file" and len(sys.argv) >= 5:
        encode_file(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "decode-file" and len(sys.argv) >= 4:
        decode_file(sys.argv[2], sys.argv[3])
    elif cmd == "img-encode" and len(sys.argv) >= 5:
        img_encode(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "img-decode" and len(sys.argv) >= 4:
        img_decode(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
