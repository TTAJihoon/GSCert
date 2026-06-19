param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
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

Invoke-Native $Python -m pip install -r requirements.txt
Invoke-Native $Python -m PyInstaller `
    --name GSCertLocalReview `
    --noconfirm `
    --windowed `
    --clean `
    --hidden-import fitz `
    --hidden-import openpyxl `
    --distpath dist `
    --workpath build `
    --specpath build `
    run.py

Write-Host "Built: $Root\dist\GSCertLocalReview"
