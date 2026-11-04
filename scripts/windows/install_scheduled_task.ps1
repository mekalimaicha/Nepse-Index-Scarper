<#
  Installs the automatic sync (no administrator rights needed):
    (a) a Startup-folder launcher  -> runs at every Windows login (catches up after the PC was off)
    (b) a scheduled task           -> Mon-Fri 17:00
  Both run scripts\windows\sync_local.ps1 from this repo.
#>
param(
    [string]$Time = "17:00",
    [string]$Dest = "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
)

$script = Join-Path $PSScriptRoot "sync_local.ps1"
$args   = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Dest `"$Dest`""

$startup = [Environment]::GetFolderPath("Startup")
Set-Content -Path "$startup\NEPSE_Index_Sync.bat" -Encoding ASCII `
    -Value "@echo off`r`nstart `"`" /min powershell $args"
Write-Host "Login sync installed: $startup\NEPSE_Index_Sync.bat" -ForegroundColor Green

try {
    $action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $args
    $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable
    Register-ScheduledTask -TaskName "NEPSE Index Data Sync" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Scheduled task installed (Mon-Fri $Time)." -ForegroundColor Green
} catch {
    Write-Host "Scheduled task NOT installed: $_" -ForegroundColor Yellow
}
