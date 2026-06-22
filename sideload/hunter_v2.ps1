# hunter_v2.ps1 -- Phase 2 target scanner
# Finds SYSTEM services with writable directories, then checks
# for manifest-based DLL redirection hardening.
# Also scans scheduled tasks and COM hijack opportunities.

$ErrorActionPreference = 'SilentlyContinue'
$outFile = "C:\Users\gwu07\Desktop\vader-rootkit\sideload\hunt_v2_results.txt"
$results = @()

function Log($msg) {
    $results += $msg
    Write-Host $msg
}

# ============================================================
# PHASE 1: SYSTEM services with user-writable directories
# ============================================================
Log "=== PHASE 1: SYSTEM SERVICES WITH WRITABLE DIRS ==="
Log ""

$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$services = Get-WmiObject Win32_Service | Where-Object {
    $_.StartName -match 'LocalSystem|LocalService|NetworkService' -and
    $_.PathName -and
    $_.PathName -notmatch 'svchost|System32|SysWOW64|Windows\\servicing'
}

$svcTargets = @()
foreach ($svc in $services) {
    $path = $svc.PathName -replace '"',''
    if ($path -match '\s+-') { $path = ($path -split '\s+-')[0].Trim() }
    if (-not (Test-Path $path)) { continue }

    $dir = Split-Path $path -Parent

    # Check if current user can write to directory
    try {
        $acl = Get-Acl $dir
        $canWrite = $false
        foreach ($ace in $acl.Access) {
            if ($ace.IdentityReference -match 'BUILTIN\\Users|Everyone|Authenticated Users' -and
                $ace.FileSystemRights -match 'Write|FullControl|Modify' -and
                $ace.AccessControlType -eq 'Allow') {
                $canWrite = $true
                break
            }
        }
        if (-not $canWrite) { continue }
    } catch { continue }

    # Check for embedded manifest with <file> redirection
    $hasManifest = $false
    $manifestProtected = @()
    $manifestRaw = ""
    try {
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $text = [System.Text.Encoding]::ASCII.GetString($bytes)
        if ($text -match '<assembly.*?</assembly>') {
            $hasManifest = $true
            $manifestRaw = $Matches[0]
            # Extract <file name="..."> entries
            $fileMatches = [regex]::Matches($manifestRaw, '<file\s+name="([^"]+)"')
            foreach ($fm in $fileMatches) {
                $manifestProtected += $fm.Groups[1].Value.ToLower()
            }
        }
    } catch {}

    # Get imports via dumpbin or PE parse
    $imports = @()
    try {
        # Quick PE import parse
        $pe_off = [BitConverter]::ToInt32($bytes, 0x3C)
        $magic = [BitConverter]::ToUInt16($bytes, $pe_off + 24)
        $isPE32Plus = ($magic -eq 0x20b)

        if ($isPE32Plus) {
            $importRVA = [BitConverter]::ToUInt32($bytes, $pe_off + 24 + 120)
        } else {
            $importRVA = [BitConverter]::ToUInt32($bytes, $pe_off + 24 + 104)
        }

        $numSections = [BitConverter]::ToUInt16($bytes, $pe_off + 6)
        $optHdrSize = [BitConverter]::ToUInt16($bytes, $pe_off + 20)
        $sectStart = $pe_off + 24 + $optHdrSize

        $sections = @()
        for ($i = 0; $i -lt $numSections; $i++) {
            $so = $sectStart + $i * 40
            $vRVA = [BitConverter]::ToUInt32($bytes, $so + 12)
            $vSize = [BitConverter]::ToUInt32($bytes, $so + 8)
            $rawPtr = [BitConverter]::ToUInt32($bytes, $so + 20)
            $rawSz = [BitConverter]::ToUInt32($bytes, $so + 16)
            $sections += @{ VRVA=$vRVA; VSize=$vSize; RawPtr=$rawPtr; RawSize=$rawSz }
        }

        function RVAtoOff($rva) {
            foreach ($s in $sections) {
                if ($rva -ge $s.VRVA -and $rva -lt ($s.VRVA + $s.VSize)) {
                    return $s.RawPtr + ($rva - $s.VRVA)
                }
            }
            return -1
        }

        if ($importRVA -gt 0) {
            $off = RVAtoOff $importRVA
            if ($off -ge 0) {
                while ($true) {
                    $nameRVA = [BitConverter]::ToUInt32($bytes, $off + 12)
                    if ($nameRVA -eq 0) { break }
                    $nameOff = RVAtoOff $nameRVA
                    if ($nameOff -ge 0) {
                        $dllName = ""
                        $ci = 0
                        while ($bytes[$nameOff + $ci] -ne 0 -and $ci -lt 128) {
                            $dllName += [char]$bytes[$nameOff + $ci]
                            $ci++
                        }
                        $imports += $dllName
                    }
                    $off += 20
                }
            }
        }
    } catch {}

    # Check KnownDLLs
    $knownDlls = @()
    try {
        $regPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs'
        $knownDlls = (Get-ItemProperty $regPath).PSObject.Properties |
            Where-Object { $_.Name -notmatch '^PS' } |
            ForEach-Object { $_.Value.ToLower() }
    } catch {}

    # Find hijackable imports
    $hijackable = @()
    foreach ($imp in $imports) {
        $impLower = $imp.ToLower()
        $isKnown = $knownDlls -contains $impLower
        $isProtected = $manifestProtected -contains $impLower
        $existsInDir = Test-Path (Join-Path $dir $imp)

        if (-not $isKnown -and -not $isProtected) {
            $hijackable += @{
                DLL = $imp
                InKnownDLLs = $isKnown
                ManifestProtected = $isProtected
                AlreadyInDir = $existsInDir
            }
        }
    }

    $svcTargets += @{
        Name = $svc.Name
        DisplayName = $svc.DisplayName
        Path = $path
        Dir = $dir
        StartName = $svc.StartName
        State = $svc.State
        HasManifest = $hasManifest
        ManifestProtected = $manifestProtected
        AllImports = $imports
        Hijackable = $hijackable
    }
}

foreach ($t in $svcTargets) {
    Log "SERVICE: $($t.Name) ($($t.DisplayName))"
    Log "  Path: $($t.Path)"
    Log "  Dir:  $($t.Dir)"
    Log "  RunAs: $($t.StartName)"
    Log "  State: $($t.State)"
    Log "  Manifest: $($t.HasManifest)"
    if ($t.ManifestProtected.Count -gt 0) {
        Log "  Manifest-protected DLLs: $($t.ManifestProtected -join ', ')"
    }
    Log "  All imports: $($t.AllImports -join ', ')"
    if ($t.Hijackable.Count -gt 0) {
        Log "  *** HIJACKABLE IMPORTS ***"
        foreach ($h in $t.Hijackable) {
            Log "    -> $($h.DLL) [Known=$($h.InKnownDLLs) ManifestProt=$($h.ManifestProtected) InDir=$($h.AlreadyInDir)]"
        }
    } else {
        Log "  No hijackable imports (all KnownDLLs or manifest-protected)"
    }
    Log ""
}

# ============================================================
# PHASE 2: SCHEDULED TASKS running as SYSTEM
# ============================================================
Log "=== PHASE 2: SCHEDULED TASKS (SYSTEM) ==="
Log ""

$tasks = Get-ScheduledTask | Where-Object {
    $_.Principal.UserId -match 'SYSTEM|S-1-5-18' -and
    $_.State -ne 'Disabled'
}

foreach ($task in $tasks) {
    foreach ($action in $task.Actions) {
        if ($action.Execute) {
            $taskExe = $action.Execute -replace '"',''
            # Resolve environment variables
            $taskExe = [Environment]::ExpandEnvironmentVariables($taskExe)

            if ($taskExe -match 'System32|SysWOW64|Windows\\' -and $taskExe -notmatch 'AppData|ProgramData') { continue }
            if (-not (Test-Path $taskExe)) { continue }

            $taskDir = Split-Path $taskExe -Parent
            try {
                $acl = Get-Acl $taskDir
                $canWrite = $false
                foreach ($ace in $acl.Access) {
                    if ($ace.IdentityReference -match 'BUILTIN\\Users|Everyone|Authenticated Users' -and
                        $ace.FileSystemRights -match 'Write|FullControl|Modify' -and
                        $ace.AccessControlType -eq 'Allow') {
                        $canWrite = $true
                        break
                    }
                }
                if ($canWrite) {
                    Log "TASK: $($task.TaskPath)$($task.TaskName)"
                    Log "  Exe: $taskExe"
                    Log "  Dir: $taskDir"
                    Log "  WorkDir: $($action.WorkingDirectory)"
                    Log "  Triggers: $($task.Triggers.Count)"
                    Log "  WRITABLE DIRECTORY"
                    Log ""
                }
            } catch {}
        }
    }
}

# ============================================================
# PHASE 3: COM HIJACK candidates (HKCU vs HKLM CLSID)
# ============================================================
Log "=== PHASE 3: COM HIJACK CANDIDATES ==="
Log ""

# Find CLSIDs in HKLM that have InProcServer32 pointing to
# user-writable locations, OR CLSIDs that exist in HKLM but
# not in HKCU (HKCU takes precedence)
$comCount = 0
$hklmCLSIDs = Get-ChildItem 'HKLM:\SOFTWARE\Classes\CLSID' -ErrorAction SilentlyContinue | Select-Object -First 200
foreach ($clsid in $hklmCLSIDs) {
    $ips32 = Get-ItemProperty "$($clsid.PSPath)\InProcServer32" -ErrorAction SilentlyContinue
    if (-not $ips32 -or -not $ips32.'(default)') { continue }

    $dllPath = $ips32.'(default)' -replace '"',''
    $dllPath = [Environment]::ExpandEnvironmentVariables($dllPath)

    # Check if this CLSID exists in HKCU (if not, we can create it)
    $clsidName = $clsid.PSChildName
    $hkcuPath = "HKCU:\SOFTWARE\Classes\CLSID\$clsidName"
    $inHKCU = Test-Path $hkcuPath

    if (-not $inHKCU -and $dllPath -notmatch 'System32|SysWOW64') {
        $comCount++
        if ($comCount -le 20) {
            Log "COM: $clsidName"
            Log "  DLL: $dllPath"
            Log "  Not in HKCU (hijackable)"
            Log ""
        }
    }
}
Log "Total COM candidates checked: $($hklmCLSIDs.Count) (showing first 20 hijackable)"
Log ""

# ============================================================
# PHASE 4: Writable directories in SYSTEM PATH
# ============================================================
Log "=== PHASE 4: WRITABLE SYSTEM PATH DIRS ==="
Log ""

$sysPaths = [Environment]::GetEnvironmentVariable('PATH', 'Machine') -split ';'
foreach ($sp in $sysPaths) {
    if (-not $sp -or -not (Test-Path $sp)) { continue }
    try {
        $acl = Get-Acl $sp
        foreach ($ace in $acl.Access) {
            if ($ace.IdentityReference -match 'BUILTIN\\Users|Everyone|Authenticated Users' -and
                $ace.FileSystemRights -match 'Write|FullControl|Modify' -and
                $ace.AccessControlType -eq 'Allow') {
                Log "WRITABLE PATH: $sp"
                Log "  ACE: $($ace.IdentityReference) -> $($ace.FileSystemRights)"
                Log ""
                break
            }
        }
    } catch {}
}

# Write results
$results | Out-File $outFile -Encoding UTF8
Log ""
Log "=== SCAN COMPLETE ==="
Log "Results saved to $outFile"
