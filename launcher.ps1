<#
.SYNOPSIS
  GSCert 서버 관리 메뉴 런처
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Show-Menu {
    $venvOk = (Test-Path (Join-Path $ScriptDir ".venv\Scripts\python.exe")) -or
              (Test-Path (Join-Path $ScriptDir "venv\Scripts\python.exe"))
    $venvOk    = (Test-Path (Join-Path $ScriptDir ".venv\Scripts\python.exe")) -or
                  (Test-Path (Join-Path $ScriptDir "venv\Scripts\python.exe"))
    $nginxOk   = (Get-Process -Name nginx -ErrorAction SilentlyContinue) -ne $null
    $venvWarn  = if (-not $venvOk) { " [!S 실행 필요]" } else { "" }
    $nginxStat = if ($nginxOk) { "[실행중]" } else { "[중지됨]" }

    Clear-Host
    Write-Host "=======================================" -ForegroundColor Cyan
    Write-Host "       GSCert 서버 관리 메뉴" -ForegroundColor Yellow
    if (-not $venvOk) {
        Write-Host "  [경고] 가상환경이 없습니다. S를 먼저 실행하세요." -ForegroundColor Red
    }
    Write-Host "=======================================" -ForegroundColor Cyan
    Write-Host "  1. start_all      - nginx + Django 서버 + 워커 함께 시작$venvWarn"
    Write-Host "  2. start_server   - Django 개발 서버만 시작 (백그라운드)$venvWarn"
    Write-Host "  3. start_worker   - download_worker만 시작 (백그라운드)$venvWarn"
    Write-Host "  4. stop_all       - 서버 + 워커 + nginx 함께 중지"
    Write-Host "  5. stop_server    - Django 서버만 중지"
    Write-Host "  6. stop_worker    - download_worker만 중지"
    Write-Host "  7. status         - 서버/워커 상태 확인"
    Write-Host "  8. run_ui_mock    - UI 목 서버 실행"
    $nginxColor = if ($nginxOk) { "Green" } else { "Red" }
    Write-Host "  N. nginx          - nginx 시작/중지/reload  $nginxStat" -ForegroundColor $nginxColor
    Write-Host "  S. setup          - 초기 환경 설정 (최초 1회 / 새 PC)"
    Write-Host "  0. 종료"
    Write-Host "=======================================" -ForegroundColor Cyan
}

function Ask-YesNo($prompt) {
    while ($true) {
        $ans = Read-Host "$prompt [y/n]"
        if ($ans -eq 'y' -or $ans -eq 'Y') { return $true }
        if ($ans -eq 'n' -or $ans -eq 'N') { return $false }
        Write-Host "  y 또는 n 을 입력해 주세요." -ForegroundColor Red
    }
}

while ($true) {
    Show-Menu
    $choice = Read-Host "`n번호 선택"

    switch ($choice.ToUpper()) {
        '1' {
            Write-Host ""
            $live = Ask-YesNo "워커를 Live 모드로 실행할까요? (No = dry-run)"
            Write-Host ""
            if ($live) {
                & (Join-Path $ScriptDir "start_all.ps1") -Live
            } else {
                & (Join-Path $ScriptDir "start_all.ps1")
            }
        }
        '2' {
            Write-Host ""
            & (Join-Path $ScriptDir "start_server.ps1")
        }
        '3' {
            Write-Host ""
            $live   = Ask-YesNo "Live 모드로 실행할까요? (No = dry-run)"
            $once   = Ask-YesNo "--once 모드로 실행할까요?"
            $nohead = if ($live) { Ask-YesNo "브라우저 창을 표시할까요? (No = headless)" } else { $false }
            Write-Host ""
            $params = @{}
            if ($live)   { $params['Live'] = $true }
            if ($once)   { $params['Once'] = $true }
            if ($nohead) { $params['NoHeadless'] = $true }
            & (Join-Path $ScriptDir "start_worker.ps1") @params
        }
        '4' {
            Write-Host ""
            & (Join-Path $ScriptDir "stop_all.ps1")
        }
        '5' {
            Write-Host ""
            & (Join-Path $ScriptDir "stop_server.ps1")
        }
        '6' {
            Write-Host ""
            & (Join-Path $ScriptDir "stop_worker.ps1")
        }
        '7' {
            Write-Host ""
            & (Join-Path $ScriptDir "status.ps1")
        }
        '8' {
            Write-Host ""
            & (Join-Path $ScriptDir "run_ui_mock_server.ps1")
        }
        'N' {
            Write-Host ""
            $NginxDir = "C:\nginx-1.29.8"
            $NginxExe = Join-Path $NginxDir "nginx.exe"
            $running  = Get-Process -Name nginx -ErrorAction SilentlyContinue
            if ($running) {
                Write-Host "nginx 현재 실행 중입니다. 작업을 선택하세요:"
                Write-Host "  1) reload (conf 재적용)"
                Write-Host "  2) stop  (중지)"
                $sub = Read-Host "선택"
                if ($sub -eq '1') { & $NginxExe -s reload; Write-Host "[OK] nginx reload 완료" -ForegroundColor Green }
                elseif ($sub -eq '2') { & (Join-Path $ScriptDir "stop_nginx.ps1") }
            } else {
                & (Join-Path $ScriptDir "start_nginx.ps1")
            }
        }
        'S' {
            Write-Host ""
            Write-Host "=== 초기 환경 설정 ===" -ForegroundColor Cyan
            $automation = Ask-YesNo "Automation 패키지도 설치할까요? (playwright, pywin32 등)"
            $search     = Ask-YesNo "Search 패키지도 설치할까요? (faiss, sentence-transformers 등)"
            Write-Host ""
            $setupParams = @{}
            if ($automation) { $setupParams['InstallAutomation'] = $true }
            if ($search)     { $setupParams['InstallSearch'] = $true }
            & (Join-Path $ScriptDir "setup.ps1") @setupParams
        }
        '0' {
            Write-Host "`n종료합니다." -ForegroundColor Yellow
            exit
        }
        default {
            Write-Host "`n올바른 번호를 입력해 주세요." -ForegroundColor Red
        }
    }

    Write-Host ""
    Read-Host "계속하려면 Enter 키를 누르세요"
}
