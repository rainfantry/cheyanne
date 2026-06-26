# VADER Research: Test if SYSTEM scheduled tasks inherit .DEFAULT\Environment\TEMP
#
# WHY: .DEFAULT\Environment has TEMP/TMP pointing to USER-WRITABLE directory
#      (C:\Users\gwu07\AppData\Local\Temp instead of C:\WINDOWS\TEMP)
#      If SYSTEM tasks inherit this, it's a misconfiguration finding.
#
# SAFETY: Creates a one-shot scheduled task that writes env vars to a file.
#         Zero risk. No exploit code. Pure observation.
#
# USAGE: Run from elevated PowerShell (admin) to register the task.
#        Then run from standard user to trigger and check.

param(
    [switch]$Register,
    [switch]$Trigger,
    [switch]$Check,
    [switch]$Cleanup
)

$TaskName = "VADER_TempInheritanceTest"
$OutputFile = "C:\Windows\Temp\vader_temp_test.txt"

if ($Register) {
    Write-Host "[*] Registering one-shot SYSTEM task..." -ForegroundColor Cyan

    # Task action: write environment variables to output file
    $cmd = @"
cmd.exe /c "echo TEMP=%TEMP% > $OutputFile & echo TMP=%TMP% >> $OutputFile & echo windir=%windir% >> $OutputFile & echo SystemRoot=%SystemRoot% >> $OutputFile & echo USERPROFILE=%USERPROFILE% >> $OutputFile & echo USERNAME=%USERNAME% >> $OutputFile & echo APPDATA=%APPDATA% >> $OutputFile & echo LOCALAPPDATA=%LOCALAPPDATA% >> $OutputFile & echo PATH=%PATH% >> $OutputFile & whoami >> $OutputFile"
"@

    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"echo TEMP=%TEMP% > $OutputFile & echo TMP=%TMP% >> $OutputFile & echo windir=%windir% >> $OutputFile & echo SystemRoot=%SystemRoot% >> $OutputFile & echo USERPROFILE=%USERPROFILE% >> $OutputFile & echo USERNAME=%USERNAME% >> $OutputFile & whoami >> $OutputFile`""
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries

    Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal -Settings $settings -Force

    # Set permissive SDDL so standard user can trigger
    # (A;;GA;;;BU) = BUILTIN\Users generic all
    $task = Get-ScheduledTask -TaskName $TaskName
    Write-Host "[+] Task registered. Run with -Trigger from standard user." -ForegroundColor Green
}

if ($Trigger) {
    Write-Host "[*] Triggering task as standard user..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Write-Host "[+] Task triggered. Run with -Check to see results." -ForegroundColor Green
}

if ($Check) {
    Write-Host "[*] Reading SYSTEM task environment output..." -ForegroundColor Cyan
    if (Test-Path $OutputFile) {
        Write-Host ""
        Get-Content $OutputFile
        Write-Host ""

        $content = Get-Content $OutputFile -Raw
        if ($content -match 'TEMP=C:\\Users\\') {
            Write-Host "[!!!] SYSTEM TASK INHERITED USER TEMP DIRECTORY!" -ForegroundColor Red
            Write-Host "[!!!] This is a potential misconfiguration finding." -ForegroundColor Red
        } elseif ($content -match 'TEMP=C:\\WINDOWS\\TEMP') {
            Write-Host "[*] SYSTEM task uses system TEMP (C:\WINDOWS\TEMP). Expected behavior." -ForegroundColor Yellow
        }
    } else {
        Write-Host "[-] Output file not found. Task may not have run yet." -ForegroundColor Red
    }
}

if ($Cleanup) {
    Write-Host "[*] Cleaning up..." -ForegroundColor Cyan
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $OutputFile -Force -ErrorAction SilentlyContinue
    Write-Host "[+] Cleaned up." -ForegroundColor Green
}

if (-not ($Register -or $Trigger -or $Check -or $Cleanup)) {
    Write-Host @"
VADER TEMP Inheritance Test
===========================
Usage:
  .\test_system_temp_inheritance.ps1 -Register   # Run as ADMIN to create task
  .\test_system_temp_inheritance.ps1 -Trigger     # Run as standard user
  .\test_system_temp_inheritance.ps1 -Check       # Check results
  .\test_system_temp_inheritance.ps1 -Cleanup     # Remove task and output
"@
}
