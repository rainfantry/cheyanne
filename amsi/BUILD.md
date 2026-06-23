# V1 ALPHA — AMSI Hardware Breakpoint Bypass

## Build
```cmd
vcvars64.bat
cl.exe amsi_bypass_hwbp_annotated.c /Fe:amsi_hwbp.exe /O1 /GS-
```

## Run
```cmd
amsi_hwbp.exe            REM Set HWBP, spawn PowerShell
amsi_hwbp.exe --check    REM Locate AMSI only
amsi_hwbp.exe --test     REM Set HWBP, verify, exit
```

## Verify
Output shows `BYPASS CONFIRMED — AMSI is blind`

## Signature Set: ALPHA
- XOR Key: 0x41 (shared with V2/V3 — acceptable, process-local only)
- Canary: stdout (no disk artifact)
- Tag: `AMSI_HWBP`

## Mechanism
DR0 → AmsiScanBuffer entry point. VEH handler catches EXCEPTION_SINGLE_STEP,
returns E_INVALIDARG before any AMSI code executes. Zero memory modification —
no patching, no byte writes to .text section. Invisible to integrity checks.

## Limitation
Hardware breakpoints are per-thread. Child processes (spawned PowerShell)
need their own breakpoints set via injection or thread creation hooks.
