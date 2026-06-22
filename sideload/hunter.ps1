# hunter.ps1 -- DLL Sideload Candidate Discovery
# VADER ROOTKIT -- 22DIV / george wu
#
# Scans this machine for privilege escalation via DLL sideloading:
#   1. Enumerate SYSTEM services and their binary paths
#   2. Find user-writable directories in DLL search order
#   3. Check PATH for user-writable entries
#   4. Cross-reference imports against KnownDLLs
#   5. Scan scheduled tasks running as SYSTEM
#   6. Check ProgramData subdirectory ACLs
#   7. Rank candidates by exploitability

param(
    [switch]$Full,       # Run all phases including slow import analysis
    [switch]$PathOnly,   # Only check PATH variable
    [switch]$Quiet       # Minimal output
)

$ErrorActionPreference = "SilentlyContinue"

# ═══════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════

$findings = @()
$findingCount = 0

function Log-Finding {
    param($Category, $Severity, $Detail)
    $script:findingCount++
    $obj = [PSCustomObject]@{
        ID       = $script:findingCount
        Category = $Category
        Severity = $Severity
        Detail   = $Detail
    }
    $script:findings += $obj
    if (-not $Quiet) {
        $color = switch ($Severity) {
            "CRITICAL" { "Red" }
            "HIGH"     { "Yellow" }
            "MEDIUM"   { "Cyan" }
            "LOW"      { "Gray" }
            default    { "White" }
        }
        Write-Host "  [#$($script:findingCount)] [$Severity] $Category" -ForegroundColor $color
        Write-Host "       $Detail" -ForegroundColor White
    }
}

function Test-WritableByUser {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    try {
        $acl = Get-Acl $Path
        $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent()
        $userSid = $currentUser.User
        $groups = $currentUser.Groups

        foreach ($ace in $acl.Access) {
            $sid = $ace.IdentityReference
            try { $sid = (New-Object System.Security.Principal.NTAccount($ace.IdentityReference)).Translate([System.Security.Principal.SecurityIdentifier]) } catch { continue }

            $isUser = ($sid -eq $userSid)
            $isGroup = ($groups | Where-Object { $_.Value -eq $sid.Value }) -ne $null

            # Also check well-known writable SIDs
            $builtinUsers = "S-1-5-32-545"       # BUILTIN\Users
            $everyone = "S-1-1-0"                  # Everyone
            $authenticated = "S-1-5-11"            # Authenticated Users
            $interactive = "S-1-5-4"               # INTERACTIVE

            $isWellKnown = ($sid.Value -eq $builtinUsers) -or
                           ($sid.Value -eq $everyone) -or
                           ($sid.Value -eq $authenticated) -or
                           ($sid.Value -eq $interactive)

            if (($isUser -or $isGroup -or $isWellKnown) -and
                ($ace.AccessControlType -eq "Allow") -and
                (($ace.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Write) -or
                 ($ace.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Modify) -or
                 ($ace.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -or
                 ($ace.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::CreateFiles))) {
                return $true
            }
        }
    } catch {}
    return $false
}

# ═══════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "  +======================================================+" -ForegroundColor Cyan
Write-Host "  |  VADER DLL SIDELOAD HUNTER -- 22DIV / george wu      |" -ForegroundColor Cyan
Write-Host "  |  Phase 3: Privilege Escalation Discovery              |" -ForegroundColor Cyan
Write-Host "  +======================================================+" -ForegroundColor Cyan
Write-Host "  |  Target: SYSTEM service loading DLL from writable path|" -ForegroundColor Cyan
Write-Host "  |  Goal: Standard user -> SYSTEM = CVE                  |" -ForegroundColor Cyan
Write-Host "  +======================================================+" -ForegroundColor Cyan
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 1: PATH VARIABLE ANALYSIS
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 1: PATH VARIABLE ANALYSIS ---" -ForegroundColor White
Write-Host ""

$systemPath = [Environment]::GetEnvironmentVariable("Path", "Machine") -split ";"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User") -split ";"
$allPaths = ($systemPath + $userPath) | Where-Object { $_ -and $_.Trim() }

$writablePaths = @()
foreach ($dir in $allPaths) {
    $dir = $dir.Trim()
    if (-not $dir) { continue }
    if (Test-WritableByUser $dir) {
        $writablePaths += $dir
        $pathType = if ($systemPath -contains $dir) { "SYSTEM PATH" } else { "USER PATH" }
        Log-Finding "PATH_WRITABLE" "HIGH" "$pathType writable by current user: $dir"
    }
}

if ($writablePaths.Count -eq 0) {
    Write-Host "  [*] No writable directories in PATH" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  [!] $($writablePaths.Count) writable PATH entries found" -ForegroundColor Yellow
    Write-Host "      ANY non-KnownDLL loaded by a SYSTEM service is a candidate" -ForegroundColor Yellow
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 2: SYSTEM SERVICES ENUMERATION
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 2: SYSTEM SERVICES ---" -ForegroundColor White
Write-Host ""

$services = Get-WmiObject Win32_Service | Where-Object {
    $_.StartName -eq "LocalSystem" -or
    $_.StartName -eq "NT AUTHORITY\SYSTEM" -or
    $_.StartName -eq "NT AUTHORITY\LocalService" -or
    $_.StartName -eq "NT AUTHORITY\NetworkService" -or
    $_.StartName -like "*SYSTEM*"
}

$systemServices = @()
foreach ($svc in $services) {
    $binPath = $svc.PathName
    if (-not $binPath) { continue }

    # Extract exe path (handle quoted paths and arguments)
    if ($binPath.StartsWith('"')) {
        $exePath = ($binPath -split '"')[1]
    } else {
        $exePath = ($binPath -split ' ')[0]
    }

    if (-not (Test-Path $exePath)) { continue }

    $exeDir = Split-Path $exePath -Parent

    $systemServices += [PSCustomObject]@{
        Name     = $svc.Name
        Display  = $svc.DisplayName
        State    = $svc.State
        Start    = $svc.StartMode
        Account  = $svc.StartName
        ExePath  = $exePath
        ExeDir   = $exeDir
    }
}

Write-Host "  [+] Found $($systemServices.Count) services running as SYSTEM/LocalService/NetworkService" -ForegroundColor Green

# Check if any service exe directories are writable
$writableSvcDirs = @()
foreach ($svc in $systemServices) {
    if (Test-WritableByUser $svc.ExeDir) {
        $writableSvcDirs += $svc
        Log-Finding "SVC_DIR_WRITABLE" "CRITICAL" "Service '$($svc.Name)' ($($svc.Account)) exe dir writable: $($svc.ExeDir)"
    }
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 3: KNOWNSDLLS ENUMERATION
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 3: KnownDLLs PROTECTION ---" -ForegroundColor White
Write-Host ""

$knownDlls = @()
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs"
$regKeys = Get-ItemProperty $regPath
foreach ($prop in $regKeys.PSObject.Properties) {
    if ($prop.Name -notlike "PS*" -and $prop.Name -ne "DllDirectory" -and $prop.Name -ne "DllDirectory32") {
        $knownDlls += $prop.Value.ToLower()
    }
}

Write-Host "  [+] KnownDLLs count: $($knownDlls.Count)" -ForegroundColor Green
Write-Host "  [*] Protected: kernel32, ntdll, user32, advapi32, etc." -ForegroundColor Gray
Write-Host "  [*] NOT protected: version.dll, dbghelp.dll, wer.dll, etc." -ForegroundColor Yellow
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 4: PROGRAMDATA WRITABLE SUBDIRECTORIES
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 4: PROGRAMDATA WRITABLE PATHS ---" -ForegroundColor White
Write-Host ""

$pdCount = 0
$pdWritable = @()
Get-ChildItem "C:\ProgramData" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    if (Test-WritableByUser $_.FullName) {
        $pdWritable += $_.FullName
        $pdCount++
    }
    # Check one level deeper
    Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-WritableByUser $_.FullName) {
            $pdWritable += $_.FullName
            $pdCount++
        }
    }
}

Write-Host "  [+] Found $pdCount writable ProgramData subdirectories" -ForegroundColor $(if ($pdCount -gt 0) { "Yellow" } else { "Green" })

foreach ($pd in $pdWritable) {
    # Check if any SYSTEM service references this path
    foreach ($svc in $systemServices) {
        if ($svc.ExePath -like "$pd*") {
            Log-Finding "PD_SVC_WRITABLE" "CRITICAL" "SYSTEM service '$($svc.Name)' exe in writable ProgramData: $pd"
        }
    }
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 5: SCHEDULED TASKS AS SYSTEM
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 5: SCHEDULED TASKS (SYSTEM) ---" -ForegroundColor White
Write-Host ""

$taskCount = 0
$taskHits = 0
try {
    $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        $_.Principal.UserId -eq "SYSTEM" -or
        $_.Principal.UserId -eq "NT AUTHORITY\SYSTEM" -or
        $_.Principal.UserId -eq "S-1-5-18" -or
        $_.Principal.RunLevel -eq "Highest"
    }

    foreach ($task in $tasks) {
        $taskCount++
        foreach ($action in $task.Actions) {
            if ($action.Execute) {
                $taskExe = $action.Execute
                # Resolve %SystemRoot% etc
                $taskExe = [Environment]::ExpandEnvironmentVariables($taskExe)
                $taskDir = Split-Path $taskExe -Parent -ErrorAction SilentlyContinue
                if ($taskDir -and (Test-WritableByUser $taskDir)) {
                    $taskHits++
                    Log-Finding "TASK_DIR_WRITABLE" "CRITICAL" "SYSTEM task '$($task.TaskName)' exe dir writable: $taskDir"
                }

                # Check working directory
                if ($action.WorkingDirectory) {
                    $wd = [Environment]::ExpandEnvironmentVariables($action.WorkingDirectory)
                    if (Test-WritableByUser $wd) {
                        $taskHits++
                        Log-Finding "TASK_WD_WRITABLE" "HIGH" "SYSTEM task '$($task.TaskName)' working dir writable: $wd"
                    }
                }
            }
        }
    }
} catch {}

Write-Host "  [+] Found $taskCount SYSTEM scheduled tasks, $taskHits with writable paths" -ForegroundColor $(if ($taskHits -gt 0) { "Yellow" } else { "Green" })
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 6: UNQUOTED SERVICE PATHS
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 6: UNQUOTED SERVICE PATHS ---" -ForegroundColor White
Write-Host ""

$unquotedCount = 0
foreach ($svc in $services) {
    $binPath = $svc.PathName
    if (-not $binPath) { continue }
    # Unquoted path with spaces = classic EoP vector
    if ($binPath -notlike '"*' -and $binPath -match ' ' -and $binPath -notlike '*.exe') {
        # Check if intermediate path segments are writable
        $parts = $binPath -split ' '
        $accumulated = ""
        foreach ($part in $parts) {
            $accumulated += $part
            $testPath = Split-Path $accumulated -Parent -ErrorAction SilentlyContinue
            if ($testPath -and (Test-WritableByUser $testPath)) {
                $unquotedCount++
                Log-Finding "UNQUOTED_PATH" "HIGH" "Service '$($svc.Name)' unquoted path, writable intermediate: $testPath (Full: $binPath)"
                break
            }
            $accumulated += " "
        }
    }
}

Write-Host "  [+] Found $unquotedCount unquoted service path vulnerabilities" -ForegroundColor $(if ($unquotedCount -gt 0) { "Yellow" } else { "Green" })
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# PHASE 7: DLL IMPORT ANALYSIS (slow -- only with -Full)
# ═══════════════════════════════════════════════════════════════

if ($Full) {
    Write-Host "  --- PHASE 7: DLL IMPORT ANALYSIS ---" -ForegroundColor White
    Write-Host ""

    # Check if dumpbin is available
    $dumpbin = $null
    $vsPath = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC"
    if (Test-Path $vsPath) {
        $dumpbin = Get-ChildItem $vsPath -Recurse -Filter "dumpbin.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    }

    if ($dumpbin) {
        Write-Host "  [+] dumpbin found: $($dumpbin.FullName)" -ForegroundColor Green

        $importHits = @()
        $checked = 0
        foreach ($svc in $systemServices) {
            if ($checked -ge 50) { break }  # Cap at 50 services
            $checked++

            $output = & $dumpbin.FullName /imports $svc.ExePath 2>$null
            if (-not $output) { continue }

            foreach ($line in $output) {
                if ($line -match '^\s+(\S+\.dll)') {
                    $dll = $Matches[1].ToLower()
                    if ($knownDlls -notcontains $dll) {
                        $importHits += [PSCustomObject]@{
                            Service = $svc.Name
                            Account = $svc.Account
                            DLL     = $dll
                            ExePath = $svc.ExePath
                        }
                    }
                }
            }

            # Check delay-loaded imports
            $delayOutput = & $dumpbin.FullName /imports $svc.ExePath 2>$null | Select-String -Pattern "delay" -Context 0,5
            if ($delayOutput) {
                foreach ($match in $delayOutput) {
                    if ($match.Line -match '(\S+\.dll)') {
                        Log-Finding "DELAY_IMPORT" "MEDIUM" "Service '$($svc.Name)' delay-loads: $($Matches[1])"
                    }
                }
            }
        }

        # Report non-KnownDLL imports from SYSTEM services
        $grouped = $importHits | Group-Object DLL | Sort-Object Count -Descending
        Write-Host ""
        Write-Host "  Non-KnownDLL imports by SYSTEM services (top 20):" -ForegroundColor Yellow
        $grouped | Select-Object -First 20 | ForEach-Object {
            $inWritablePath = $false
            foreach ($wp in $writablePaths) {
                $testDll = Join-Path $wp $_.Name
                if (-not (Test-Path (Join-Path "C:\Windows\System32" $_.Name))) {
                    $inWritablePath = $true
                }
            }
            $marker = if ($inWritablePath) { " [!]" } else { "" }
            Write-Host "    $($_.Count.ToString().PadLeft(3)) services import: $($_.Name)$marker" -ForegroundColor $(if ($inWritablePath) { "Red" } else { "White" })
        }
    } else {
        Write-Host "  [!] dumpbin not found -- skipping import analysis" -ForegroundColor Red
        Write-Host "      Run from VS Developer Command Prompt for this phase" -ForegroundColor Gray
    }
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# PHASE 8: MISSING DLL PROBE (live test)
# ═══════════════════════════════════════════════════════════════

Write-Host "  --- PHASE 8: MISSING DLL SEARCH ORDER PROBE ---" -ForegroundColor White
Write-Host ""

# Common DLLs NOT in KnownDLLs that SYSTEM services often try to load
$probeDlls = @(
    "version.dll", "dbghelp.dll", "wer.dll", "uxtheme.dll",
    "propsys.dll", "profapi.dll", "IPHLPAPI.DLL", "dhcpcsvc.DLL",
    "dhcpcsvc6.DLL", "dnsapi.dll", "rasadhlp.dll", "fwpuclnt.dll",
    "winnsi.dll", "nlaapi.dll", "mswsock.dll", "napinsp.dll",
    "pnrpnsp.dll", "wshbth.dll", "NLAapi.dll", "winrnr.dll",
    "cdpsgshims.dll", "TextShaping.dll", "edputil.dll",
    "wldp.dll", "urlmon.dll", "iertutil.dll", "winhttp.dll",
    "WindowsCodecs.dll", "apphelp.dll"
)

$probeResults = @()
foreach ($dll in $probeDlls) {
    $dllLower = $dll.ToLower()
    $inKnown = $knownDlls -contains $dllLower

    if (-not $inKnown) {
        $inSystem32 = Test-Path (Join-Path "C:\Windows\System32" $dll)
        $inWritable = $false

        foreach ($wp in $writablePaths) {
            $candidate = Join-Path $wp $dll
            if (-not (Test-Path $candidate)) {
                # This writable PATH dir doesn't have this DLL -- we could plant one
                $inWritable = $true
            }
        }

        $probeResults += [PSCustomObject]@{
            DLL        = $dll
            KnownDLL   = $inKnown
            InSystem32 = $inSystem32
            Plantable  = ($inWritable -and $writablePaths.Count -gt 0)
        }

        if ($inWritable -and $writablePaths.Count -gt 0 -and -not $inSystem32) {
            Log-Finding "DLL_PLANTABLE" "CRITICAL" "$dll NOT in KnownDLLs, NOT in System32, plantable in writable PATH"
        } elseif ($inWritable -and $writablePaths.Count -gt 0) {
            Log-Finding "DLL_SHADOW" "MEDIUM" "$dll NOT in KnownDLLs, exists in System32, could be shadowed via writable PATH if PATH dir searched first"
        }
    }
}
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════

Write-Host "  ======================================================" -ForegroundColor Cyan
Write-Host "  HUNT SUMMARY" -ForegroundColor Cyan
Write-Host "  ======================================================" -ForegroundColor Cyan
Write-Host ""

$critical = ($findings | Where-Object { $_.Severity -eq "CRITICAL" }).Count
$high = ($findings | Where-Object { $_.Severity -eq "HIGH" }).Count
$medium = ($findings | Where-Object { $_.Severity -eq "MEDIUM" }).Count
$low = ($findings | Where-Object { $_.Severity -eq "LOW" }).Count

Write-Host "  Total findings: $($findings.Count)" -ForegroundColor White
Write-Host "    CRITICAL: $critical" -ForegroundColor Red
Write-Host "    HIGH:     $high" -ForegroundColor Yellow
Write-Host "    MEDIUM:   $medium" -ForegroundColor Cyan
Write-Host "    LOW:      $low" -ForegroundColor Gray
Write-Host ""

if ($critical -gt 0) {
    Write-Host "  CRITICAL FINDINGS (exploitable for EoP):" -ForegroundColor Red
    Write-Host ""
    $findings | Where-Object { $_.Severity -eq "CRITICAL" } | ForEach-Object {
        Write-Host "  [#$($_.ID)] $($_.Category)" -ForegroundColor Red
        Write-Host "       $($_.Detail)" -ForegroundColor White
        Write-Host ""
    }
}

if ($high -gt 0) {
    Write-Host "  HIGH FINDINGS:" -ForegroundColor Yellow
    Write-Host ""
    $findings | Where-Object { $_.Severity -eq "HIGH" } | ForEach-Object {
        Write-Host "  [#$($_.ID)] $($_.Category)" -ForegroundColor Yellow
        Write-Host "       $($_.Detail)" -ForegroundColor White
        Write-Host ""
    }
}

# Export results
$outPath = "C:\Users\gwu07\Desktop\vader-rootkit\sideload\hunt_results.txt"
$findings | Format-Table -AutoSize | Out-String | Out-File $outPath -Encoding utf8
Write-Host "  [*] Results exported to: $outPath" -ForegroundColor Gray
Write-Host ""
Write-Host "  Next: Run with -Full for import table analysis" -ForegroundColor Gray
Write-Host "  Next: Use ProcMon for live DLL load monitoring" -ForegroundColor Gray
Write-Host ""
