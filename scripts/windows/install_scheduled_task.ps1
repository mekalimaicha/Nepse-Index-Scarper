<#
  Installs the automatic sync (no administrator rights needed):
    (a) Startup-folder launcher            -> full sync at every Windows login
    (b) task "NEPSE Index Data Sync"       -> full sync Mon-Fri 17:00 (unchanged schedule)
    (c) task "NEPSE Index Data Sync Poll"  -> every 5 minutes, silent: if GitHub has new data
                                              (e.g. you ran the workflow manually) it is pulled
                                              into the F: folder within minutes.
  All run scripts\windows\sync_local.ps1 from this repo.
#>
param(
    [string]$Time = "17:00",
    [int]$PollMinutes = 5,
    [string]$Dest = "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
)

$script = Join-Path $PSScriptRoot "sync_local.ps1"
$vbs    = Join-Path $PSScriptRoot "run_hidden.vbs"
$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Dest `"$Dest`""

# (a) login
$startup = [Environment]::GetFolderPath("Startup")
Set-Content -Path "$startup\NEPSE_Index_Sync.bat" -Encoding ASCII `
    -Value "@echo off`r`nstart `"`" /min powershell $psArgs"
Write-Host "Login sync installed: $startup\NEPSE_Index_Sync.bat" -ForegroundColor Green

# (b) Mon-Fri 17:00
try {
    $action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
    $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable
    Register-ScheduledTask -TaskName "NEPSE Index Data Sync" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Scheduled task installed (Mon-Fri $Time)." -ForegroundColor Green
} catch {
    Write-Host "17:00 task NOT installed: $_" -ForegroundColor Yellow
}

# (c) 5-minute poll
try {
    $pollAction   = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//B //Nologo `"$vbs`" `"$script`" `"$Dest`""
    $pollTrigger  = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
                        -RepetitionInterval (New-TimeSpan -Minutes $PollMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
    $pollSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                        -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask -TaskName "NEPSE Index Data Sync Poll" -Action $pollAction -Trigger $pollTrigger -Settings $pollSettings -Force | Out-Null
    Write-Host "Poll task installed: checks GitHub every $PollMinutes minutes." -ForegroundColor Green
} catch {
    Write-Host "Poll task NOT installed: $_" -ForegroundColor Yellow
}
