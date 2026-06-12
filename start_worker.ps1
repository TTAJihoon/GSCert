<#
.SYNOPSIS
  download_worker를 백그라운드로 시작한다.
.PARAMETER DryRun
  --dry-run 모드로 실행한다.
.PARAMETER Live
  실제 ECM/Windows agent 자동화를 실행한다. 지정하지 않으면 dry-run으로 실행한다.
.PARAMETER Once
  --once 모드로 실행한다.
.PARAMETER NoHeadless
  live 모드에서 브라우저 창을 표시한다.
#>
param(
    [switch]$DryRun,
    [switch]$Live,
    [switch]$Once,
    [switch]$NoHeadless
)
$ErrorActionPreference = "Stop"

$RootDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $RootDir "venv\Scripts\python.exe"
}
if (-not (Test-Path $VenvPython)) {
    $resolved = Get-Command python -ErrorAction SilentlyContinue
    if (-not $resolved) {
        Write-Host "[ERROR] Python을 찾을 수 없습니다. Python 설치 또는 가상환경 설정이 필요합니다." -ForegroundColor Red
        Write-Host "        launcher 메뉴의 'S. 초기 환경 설정'을 먼저 실행해 주세요." -ForegroundColor Yellow
        exit 1
    }
    $VenvPython = $resolved.Source
}

$LogsDir = Join-Path $RootDir "logs"
$RunDir  = Join-Path $RootDir "run"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
New-Item -ItemType Directory -Path $RunDir  -Force | Out-Null

$PidFile = Join-Path $RunDir "download_worker.pid"

if (Test-Path $PidFile) {
    $existingPid = [int](Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[INFO] download_worker가 이미 실행 중입니다 (PID $existingPid)."
        exit 0
    }
    Write-Host "[WARN] 유령 PID 파일을 정리합니다."
    Remove-Item $PidFile -Force
}

$ArgumentList = @("manage.py", "run_download_worker")
if ($Live) {
    $ArgumentList += "--live"
} else {
    $ArgumentList += "--dry-run"
}
if ($Once)       { $ArgumentList += "--once" }
if ($NoHeadless) { $ArgumentList += "--no-headless" }

$ts     = Get-Date -Format "yyyyMMdd_HHmmss"
$OutLog = Join-Path $LogsDir "download_worker_${ts}_out.log"
$ErrLog = Join-Path $LogsDir "download_worker_${ts}_err.log"

$process = Start-Process -FilePath $VenvPython `
    -ArgumentList $ArgumentList `
    -WorkingDirectory $RootDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError  $ErrLog `
    -PassThru

Set-Content -Path $PidFile -Value $process.Id

$modeLabel = if ($Live) { "live" } else { "dry-run" }
Write-Host "[OK] download_worker 시작 (PID $($process.Id)), 모드: $modeLabel"
Write-Host "     stdout: $OutLog"
Write-Host "     stderr: $ErrLog"
