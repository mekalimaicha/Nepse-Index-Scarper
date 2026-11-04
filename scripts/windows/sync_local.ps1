<#
  Pull the latest data from GitHub and merge it into the local data folder.
  Log: <repo>\logs\local_sync.log . Safe to run any time, any number of times.
#>
param(
    [string]$Dest = "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
)

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$log  = Join-Path $Repo "logs\local_sync.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Log($m) { $l = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m; Write-Host $l; Add-Content $log $l }

try {
    if (-not (Test-Path (Split-Path $Dest -Qualifier))) { throw "Drive $(Split-Path $Dest -Qualifier) is not available" }
    Set-Location $Repo
    Log "git pull"
    $out = git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
    Log ($out -join " ")
    $py  = Join-Path $Repo ".venv\Scripts\python.exe"
    $res = & $py -m nepse_scraper sync --dst $Dest
    if ($LASTEXITCODE -ne 0) { throw "sync failed" }
    $res | ForEach-Object { Add-Content $log "    $_" }
    Log "OK"
    exit 0
} catch {
    Log "FAILED: $_"
    exit 1
}
