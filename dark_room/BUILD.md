# V3 CHARLIE — Dark Room (AMSI + ETW Combined)

## Build
```cmd
vcvars64.bat
cl.exe dark_room_annotated.c /Fe:dark_room.exe /O1 /GS-
```

## Run
```cmd
dark_room.exe            REM Blind both, spawn PowerShell
dark_room.exe --test     REM Blind both, verify, exit
dark_room.exe --check    REM Locate targets only
```

## Verify
Both `AMSI: BLIND` and `ETW: BLIND` in output.

## Signature Set: CHARLIE
- XOR Key: 0x41 (shared with V1/V2 — acceptable, process-local only)
- Canary: stdout (no disk artifact)
- Tag: `DARK_ROOM`

## Mechanism
Single VEH handler, two debug registers:
- DR0 → AmsiScanBuffer (returns E_INVALIDARG)
- DR1 → EtwEventWrite (returns STATUS_SUCCESS)

Complete user-mode telemetry blackout. AMSI can't scan scripts,
ETW can't log events. The process operates in total darkness —
no scanning, no telemetry, no visibility for Defender or EDR.

## Kill Chain Role
Phase 1+2 combined. Deploy before any payload execution to blind
both detection systems simultaneously. Spawns PowerShell in the
dark room for follow-on operations.
