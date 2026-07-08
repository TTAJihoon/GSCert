param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $Root
Set-Location $Root

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-ExeCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments = @()
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "Command failed with exit code $($process.ExitCode): $FilePath $($Arguments -join ' ')"
    }
}

Invoke-Native $Python -m pip install -r requirements.txt
Invoke-Native $Python -m PyInstaller `
    --name GSCertLocalReviewDashboard `
    --noconfirm `
    --windowed `
    --clean `
    --paths $RepoRoot `
    --collect-submodules gscert_review_core `
    --hidden-import fitz `
    --hidden-import lxml.etree `
    --hidden-import openpyxl `
    --hidden-import xlrd `
    --hidden-import xlrd.compdoc `
    --distpath dist `
    --workpath build `
    --specpath build `
    run_dashboard.py

$ExePath = Join-Path $Root "dist\GSCertLocalReviewDashboard\GSCertLocalReviewDashboard.exe"
Invoke-ExeCheck $ExePath @("--self-check")

Write-Host "Built: $Root\dist\GSCertLocalReviewDashboard"
