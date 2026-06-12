<#
.SYNOPSIS
  Django 개발/검증용 runserver를 중지한다.
#>
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir  = Join-Path $RootDir "run"
$PidFile = Join-Path $RunDir "django_runserver.pid"
$Port    = 8000

if (Test-Path $PidFile) {
    $targetPid = [int](Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Django runserver 프로세스 종료 (PID $targetPid)"
    } else {
        Write-Host "[INFO] PID $targetPid 프로세스가 이미 종료되었습니다."
    }
    Remove-Item $PidFile -Force
} else {
    Write-Host "[INFO] PID 파일이 없습니다."
}

$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    $ownerPid = ($portInUse | Select-Object -First 1).OwningProcess
    Write-Host "[WARN] 포트 $Port 가 아직 점유 중입니다 (PID $ownerPid). 종료 시도..."
    Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $portInUse2 = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($portInUse2) {
        Write-Host "[ERROR] 포트 $Port 해제에 실패했습니다."
        exit 1
    }
}

Write-Host "[OK] Django runserver 중지 완료."
