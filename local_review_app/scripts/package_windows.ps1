param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& $Python -m pip install -r requirements.txt
& $Python -m PyInstaller `
    --name GSCertLocalReview `
    --noconfirm `
    --windowed `
    --clean `
    --distpath dist `
    --workpath build `
    --specpath build `
    run.py

Write-Host "Built: $Root\dist\GSCertLocalReview"
