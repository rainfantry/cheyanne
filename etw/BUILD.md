# V2 BRAVO — ETW Hardware Breakpoint Bypass

## Build
```cmd
vcvars64.bat
cl.exe etw_hwbp_annotated.c /Fe:etw_hwbp.exe /O1 /GS-
```

## Run
```cmd
etw_hwbp.exe             REM Set HWBP on ETW
etw_hwbp.exe --check     REM Locate only
etw_hwbp.exe --test      REM Set + verify
```

## Verify
Output shows `ETW bypass confirmed — telemetry is blind`

## Signature Set: BRAVO
- XOR Key: 0x41 (shared with V1/V3 — acceptable, process-local only)
- Canary: stdout (no disk artifact)
- Tag: `ETW_HWBP`

## Mechanism
DR1 → EtwEventWrite entry point. VEH handler catches EXCEPTION_SINGLE_STEP,
returns STATUS_SUCCESS — all process telemetry events silently discarded.
Zero memory modification. EDR/SIEM sees no events from this process.
