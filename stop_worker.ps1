<#
.SYNOPSIS
  download_worker를 중지한다.
#>
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir  = Join-Path $RootDir "run"
$PidFile = Join-Path $RunDir "download_worker.pid"

if (Test-Path $PidFile) {
    $pid = [int](Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] download_worker 프로세스 종료 (PID $pid)"
    } else {
        Write-Host "[INFO] PID $pid 프로세스가 이미 종료되었습니다."
    }
    Remove-Item $PidFile -Force
} else {
    Write-Host "[INFO] PID 파일이 없습니다. worker가 실행 중이지 않습니다."
}

Write-Host "[OK] download_worker 중지 완료."
