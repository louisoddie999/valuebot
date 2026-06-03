# Register a Windows Scheduled Task that auto-refreshes ValueBot every N hours.
# Run ONCE (right-click > Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File scripts\setup-autorefresh.ps1).
param([int]$EveryHours = 6, [string]$Scope = "week")
$ErrorActionPreference = 'Stop'
$proj = Split-Path -Parent $PSScriptRoot
$ps   = Join-Path $proj 'scripts\refresh.ps1'
$name = 'ValueBot Auto-Refresh'

$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
           -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$ps`" -Scope $Scope"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
           -RepetitionInterval (New-TimeSpan -Hours $EveryHours)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
            -AllowStartIfOnBatteries -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Registered '$name': every $EveryHours h, scope=$Scope (runs only while PC is on)." -ForegroundColor Green
Write-Host "Remove later with:  Unregister-ScheduledTask -TaskName '$name' -Confirm:`$false" -ForegroundColor DarkGray