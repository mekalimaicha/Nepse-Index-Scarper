<#
  Registers a Windows Task Scheduler job that runs sync_local.ps1 every
  Monday-Friday at 17:00 (after the GitHub Action has published the day's data).
  If the PC was off, the task runs as soon as it is next available.
#>
param(
    [string]$Time = "17:00",
    [string]$Dest = "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
)

$script = Join-Path $PSScriptRoot "sync_local.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Dest `"$Dest`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries

Register-ScheduledTask -TaskName "NEPSE Index Data Sync" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Merge NEPSE index CSVs from GitHub into $Dest" -Force
Write-Host "Task 'NEPSE Index Data Sync' registered for Mon-Fri at $Time."
