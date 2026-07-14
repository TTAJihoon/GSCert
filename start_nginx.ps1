<#
.SYNOPSIS
  nginx를 시작한다. HTTPS 적용 범위(모드)를 선택할 수 있다.
.PARAMETER Mode
  All              - 모든 페이지를 HTTPS로 서비스
  ConsultationOnly - /consultation/ 만 HTTPS, 나머지는 HTTP
  생략 시 마지막으로 적용했던 모드(run\nginx_mode.txt)를 유지하고, 기록이 없으면 All.
#>
param(
    [ValidateSet('All', 'ConsultationOnly')]
    [string]$Mode
)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NginxDir = "C:\nginx-1.29.8"
$NginxExe = Join-Path $NginxDir "nginx.exe"

if (-not (Test-Path $NginxExe)) {
    Write-Host "[ERROR] nginx를 찾을 수 없습니다: $NginxExe" -ForegroundColor Red
    Write-Host "        launcher 메뉴의 'S. 초기 환경 설정'을 먼저 실행해 주세요." -ForegroundColor Yellow
    exit 1
}

if (-not $Mode) {
    $ModeFile = Join-Path $ScriptDir "run\nginx_mode.txt"
    $Mode = if (Test-Path $ModeFile) { (Get-Content $ModeFile -Raw).Trim() } else { 'All' }
}

& (Join-Path $ScriptDir "setup\Update-NginxConf.ps1") -Mode $Mode
if ($LASTEXITCODE -ne 0) { exit 1 }

$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($running) {
    $reloadProc = Start-Process -FilePath $NginxExe -ArgumentList "-s reload" -WorkingDirectory $NginxDir -Wait -WindowStyle Hidden -PassThru
    if ($reloadProc.ExitCode -eq 0) {
        Write-Host "[INFO] nginx가 이미 실행 중이라 conf를 reload 했습니다. (모드: $Mode)"
        exit 0
    } else {
        Write-Host "[ERROR] nginx reload 실패 (종료 코드 $($reloadProc.ExitCode)). $NginxDir\logs\error.log 를 확인하세요." -ForegroundColor Red
        exit 1
    }
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
