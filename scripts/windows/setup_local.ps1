<#
  One-time setup of a PC: clone the repo, create the Python venv, first sync, install automatic runs.

  First PC (defaults):
    .\setup_local.ps1 -RepoUrl https://github.com/<user>/<repo>.git

  Second PC (own folders; Python + logs kept OUTSIDE the repo folder so two PCs sharing a MEGA folder cannot clash):
    .\setup_local.ps1 -RepoUrl ... -RepoDir "D:\MEGA\NEPSE Analysis\NEPSE Index Scraper" `
        -Dest "D:\MEGA\NEPSE Analysis\NEPSE Index Data" `
        -FundDest "D:\MEGA\NEPSE Analysis\Fundamental Data\Fundamental Data sheets" `
        -VenvDir "$env:LOCALAPPDATA\NEPSE-Index-Scraper\venv" -StateDir "$env:LOCALAPPDATA\NEPSE-Index-Scraper"
#>
param(
    [Parameter(Mandatory = $true)][string]$RepoUrl,
    [string]$RepoDir  = "F:\MEGA\NEPSE Analysis\NEPSE Index Scraper",
    [string]$Dest     = "F:\MEGA\NEPSE Analysis\NEPSE Index Data",
    [string]$FundDest = "F:\MEGA\NEPSE Analysis\Fundamental Data\Fundamental Data sheets",
    [string]$VenvDir  = "",
    [string]$StateDir = ""
)

if (Test-Path "$RepoDir\.git") { git -C $RepoDir pull --ff-only } else { git clone $RepoUrl $RepoDir }
if ($LASTEXITCODE -ne 0) { throw "git clone/pull failed" }

$venv = if ($VenvDir) { $VenvDir } else { Join-Path $RepoDir ".venv" }
$py   = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) { py -m venv $venv; if ($LASTEXITCODE -ne 0) { throw "Python (py) not found - install Python 3.10+" } }
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -e $RepoDir
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$pyArg = if ($VenvDir) { $py } else { "" }
& "$RepoDir\scripts\windows\sync_local.ps1" -Dest $Dest -FundDest $FundDest -Python $pyArg -StateDir $StateDir
& "$RepoDir\scripts\windows\install_scheduled_task.ps1" -Dest $Dest -FundDest $FundDest -Python $pyArg -StateDir $StateDir

$logDir = if ($StateDir) { $StateDir } else { Join-Path $RepoDir "logs" }
Write-Host "`nDone. Log: $logDir\local_sync.log"
