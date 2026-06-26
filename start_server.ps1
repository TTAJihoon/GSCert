<#
.SYNOPSIS
  Django 개발/검증용 runserver를 백그라운드로 시작한다.
#>
$ErrorActionPreference = "Stop"

$RootDir    = Split-Path -Parent $MyInvocation.MyCommand.Path

# 환경 변수 로드 (env.ps1 존재 시)
$EnvFile = Join-Path $RootDir "env.ps1"
if (Test-Path $EnvFile) { . $EnvFile }
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

$PidFile = Join-Path $RunDir "django_runserver.pid"
$Port    = 8000

# --- 이미 실행 중인지 확인 ---
if (Test-Path $PidFile) {
    $existingPid = [int](Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[INFO] Django runserver가 이미 실행 중입니다 (PID $existingPid)."
        exit 0
    }
    Write-Host "[WARN] 유령 PID 파일을 정리합니다."
    Remove-Item $PidFile -Force
}

# --- 포트 점유 확인 ---
$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    $ownerPid = ($portInUse | Select-Object -First 1).OwningProcess
    Write-Host "[ERROR] 포트 $Port 가 이미 사용 중입니다 (PID $ownerPid)."
    exit 1
}

# --- 시작 ---
$ts     = Get-Date -Format "yyyyMMdd_HHmmss"
$OutLog = Join-Path $LogsDir "django_runserver_${ts}_out.log"
$ErrLog = Join-Path $LogsDir "django_runserver_${ts}_err.log"

# Windows 로케일(cp1252 등)에서 한글 로그 출력 시 UnicodeEncodeError를
# 방지하기 위해 자식 프로세스의 stdout/stderr를 UTF-8로 고정한다.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$process = Start-Process -FilePath $VenvPython `
    -ArgumentList @("manage.py", "runserver", "--noreload", "0.0.0.0:$Port") `
    -WorkingDirectory $RootDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError  $ErrLog `
    -PassThru

Set-Content -Path $PidFile -Value $process.Id
Write-Host "[OK] Django runserver 시작 (PID $($process.Id)), 포트 $Port"
Write-Host "     stdout: $OutLog"
Write-Host "     stderr: $ErrLog"
