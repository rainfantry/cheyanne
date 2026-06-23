# V5 ECHO — DLL Proxy Sideload (VERSION.dll)

## Build
```cmd
vcvars64.bat
cl.exe version_proxy_annotated.c /Fe:VERSION.dll /LD /O1 /GS- /utf-8 /link /DEF:..\..\sideload\version.def
```

## Deploy
Copy `VERSION.dll` to any service directory that imports it and lacks manifest DLL redirection.

**WARNING:** Does NOT work against NativePushService — manifest hardening blocks it (Finding #40).

## Verify
```cmd
type C:\Windows\Temp\ver_cache.log
```

## Signature Set: ECHO
- XOR Key: 0x37
- Canary: `C:\Windows\Temp\ver_cache.log`
- Tag: `ECHO_PROXY`
