<#
  Pull the latest data from GitHub and merge it into the local data folder.
  Log: <repo>\logs\local_sync.log

  -OnlyIfChanged : quiet "poll" mode used every 5 minutes. Does a cheap `git fetch` and
                   only syncs (and only logs) when GitHub has a commit not yet synced to F:.
  Without it     : always pulls and syncs (used at 17:00 and at login).
#>
param(
    [string]$Dest = "F:\MEGA\NEPSE Analysis\NEPSE Index Data",
    [switch]$OnlyIfChanged
)

$Repo   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$log    = Join-Path $Repo "logs\local_sync.log"
$marker = Join-Path $Repo "logs\last_synced_commit.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Log($m) { $l = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m; Write-Host $l; Add-Content $log $l }

# One sync at a time (the 5-minute poll, the 17:00 run and the login run must not overlap)
$mutex = New-Object System.Threading.Mutex($false, "Global\NEPSE_Index_Sync")
if (-not $mutex.WaitOne(0)) { exit 0 }

try {
    Set-Location $Repo

    if ($OnlyIfChanged) {
        git fetch origin 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { exit 0 }                    # offline: try again in 5 minutes
        $remote = (git rev-parse origin/main).Trim()
        $done   = if (Test-Path $marker) { (Get-Content $marker -Raw).Trim() } else { "" }
        if ($remote -eq $done) { exit 0 }                       # nothing new -> silent
        Log "New data on GitHub ($($remote.Substring(0,7))) - syncing now"
    }

    if (-not (Test-Path (Split-Path $Dest -Qualifier))) { throw "Drive $(Split-Path $Dest -Qualifier) is not available" }

    Log "git pull"
    $out = git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
    Log ($out -join " ")

    $py  = Join-Path $Repo ".venv\Scripts\python.exe"
    $res = & $py -m nepse_scraper sync --dst $Dest
    if ($LASTEXITCODE -ne 0) { throw "sync failed" }
    $res | ForEach-Object { Add-Content $log "    $_" }

    (git rev-parse HEAD).Trim() | Set-Content $marker
    Log "OK"
    exit 0
} catch {
    Log "FAILED: $_"
    exit 1
} finally {
    $mutex.ReleaseMutex()
}
