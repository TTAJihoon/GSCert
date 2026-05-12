<#
.SYNOPSIS
  download_worker를 백그라운드로 시작한다.
.PARAMETER DryRun
  --dry-run 모드로 실행한다.
.PARAMETER Once
  --once 모드로 실행한다.
#>
param(
    [switch]$DryRun,
    [switch]$Once
)
$ErrorActionPreference = "Stop"

$RootDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $RootDir "venv\Scripts\python.exe"
}
if (-not (Test-Path $VenvPython)) { $VenvPython = "python" }

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
if ($DryRun) { $ArgumentList += "--dry-run" }
if ($Once)   { $ArgumentList += "--once" }

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

$modeLabel = if ($DryRun) { "dry-run" } else { "live" }
Write-Host "[OK] download_worker 시작 (PID $($process.Id)), 모드: $modeLabel"
Write-Host "     stdout: $OutLog"
Write-Host "     stderr: $ErrLog"
