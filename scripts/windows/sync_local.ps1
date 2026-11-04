<#
  Pull the latest data from GitHub and merge it into the local clone folder.
  Run manually or via install_scheduled_task.ps1.
#>
param(
    [string]$Dest = "F:\MEGA\NEPSE Analysis\NEPSE Index Data"
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repo

Write-Host "Pulling latest data from GitHub..."
git pull --ff-only

$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

& $py -m nepse_scraper sync --dst "$Dest"
exit $LASTEXITCODE
