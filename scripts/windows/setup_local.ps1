<#
  One-time setup: clone the repo onto F:, create the Python venv, first sync, install automatic runs.
    .\setup_local.ps1 -RepoUrl https://github.com/<user>/<repo>.git
#>
param(
    [Parameter(Mandatory = $true)][string]$RepoUrl,
    [string]$RepoDir = "F:\MEGA\NEPSE Analysis\NEPSE Index Scraper",
    [string]$Dest    = "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
)

if (Test-Path "$RepoDir\.git") { git -C $RepoDir pull --ff-only } else { git clone $RepoUrl $RepoDir }
if ($LASTEXITCODE -ne 0) { throw "git clone/pull failed" }

Set-Location $RepoDir
if (-not (Test-Path ".venv\Scripts\python.exe")) { py -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -e .
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

& "$RepoDir\scripts\windows\sync_local.ps1" -Dest $Dest
& "$RepoDir\scripts\windows\install_scheduled_task.ps1" -Dest $Dest
Write-Host "`nDone. Log: $RepoDir\logs\local_sync.log"
