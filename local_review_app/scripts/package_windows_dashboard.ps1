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

$SplashImage = Join-Path $Root "assets\splash.png"
$AppIcon = Join-Path $Root "assets\app_icon.ico"
$WinVersionInfoFile = Join-Path $Root "assets\version_info.txt"
$ServerCert = Join-Path $Root "certs\gscert.crt"
$VersionFile = Join-Path $Root "APP_VERSION"

# 빌드마다 새 버전 문자열을 찍는다(자동 업데이트가 "새 버전 있음"을 판단하는 기준).
# 사람이 기억해서 올릴 필요 없이, 빌드 시각을 그대로 버전으로 쓴다.
$AppVersion = Get-Date -Format "yyyy.MM.dd.HHmmss"
Set-Content -Path $VersionFile -Value $AppVersion -NoNewline -Encoding ascii
Write-Host "App version: $AppVersion"

Invoke-Native $Python -m pip install -r requirements.txt
$PyInstallerArguments = @(
    "-m", "PyInstaller",
    "--name", "GSCertLocalReviewDashboard",
    "--noconfirm",
    "--windowed",
    "--clean",
    "--icon", $AppIcon,
    "--version-file", $WinVersionInfoFile,
    "--paths", $RepoRoot,
    "--collect-submodules", "gscert_review_core",
    "--hidden-import", "fitz",
    "--hidden-import", "lxml.etree",
    "--hidden-import", "openpyxl",
    "--hidden-import", "xlrd",
    "--hidden-import", "xlrd.compdoc"
)

# PyInstaller의 splash 기능만 완전한 Tcl/Tk 런타임을 요구한다. tkinter 모듈을
# import할 수 있어도 Tcl/Tk 데이터 파일이 빠진 Python 설치는 PyInstaller 기준으로
# 사용할 수 없으므로, PyInstaller가 실제로 쓰는 가용성 판정을 그대로 확인한다.
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -c "from PyInstaller.utils.hooks.tcl_tk import tcltk_info; raise SystemExit(0 if tcltk_info.available else 1)" 2>$null
$TclTkAvailable = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $PreviousErrorActionPreference
if ($TclTkAvailable) {
    $PyInstallerArguments += @("--splash", $SplashImage)
}
else {
    Write-Warning "완전한 Tcl/Tk 런타임이 없어 splash 화면을 생략합니다. 앱 기능에는 영향이 없습니다."
}

$PyInstallerArguments += @(
    "--add-data", "${ServerCert}:certs",
    "--add-data", "${VersionFile}:.",
    "--add-data", "${AppIcon}:assets",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", "build",
    "run_dashboard.py"
)
Invoke-Native $Python @PyInstallerArguments

$ExePath = Join-Path $Root "dist\GSCertLocalReviewDashboard\GSCertLocalReviewDashboard.exe"
Invoke-ExeCheck $ExePath @("--self-check")

Write-Host "Built: $Root\dist\GSCertLocalReviewDashboard"
