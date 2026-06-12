<#
.SYNOPSIS
  nginx를 시작한다.
#>
$ErrorActionPreference = "Stop"
$NginxDir = "C:\nginx-1.29.8"
$NginxExe = Join-Path $NginxDir "nginx.exe"

if (-not (Test-Path $NginxExe)) {
    Write-Host "[ERROR] nginx를 찾을 수 없습니다: $NginxExe" -ForegroundColor Red
    Write-Host "        launcher 메뉴의 'S. 초기 환경 설정'을 먼저 실행해 주세요." -ForegroundColor Yellow
    exit 1
}

$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[INFO] nginx가 이미 실행 중입니다."
    exit 0
}

Start-Process -FilePath $NginxExe -WorkingDirectory $NginxDir -WindowStyle Hidden
Start-Sleep -Seconds 1
$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "[OK] nginx 시작 완료"
} else {
    Write-Host "[ERROR] nginx 시작에 실패했습니다. $NginxDir\logs\error.log 를 확인하세요." -ForegroundColor Red
    exit 1
}
