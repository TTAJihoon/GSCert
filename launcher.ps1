<#
.SYNOPSIS
  GSCert 서버 관리 메뉴 런처
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 환경 변수 로드 (PostgreSQL 자격증명 등)
$EnvFile = Join-Path $ScriptDir "env.ps1"
if (Test-Path $EnvFile) { . $EnvFile }

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
    Write-Host "  1. start_all      - Django 서버 + 워커 함께 시작$venvWarn"
    Write-Host "  2. start_server   - Django 개발 서버만 시작 (백그라운드)$venvWarn"
    Write-Host "  3. start_worker   - download_worker만 시작 (백그라운드)$venvWarn"
    Write-Host "  4. stop_all       - 서버 + 워커 함께 중지"
    Write-Host "  5. stop_server    - Django 서버만 중지"
    Write-Host "  6. stop_worker    - download_worker만 중지"
    Write-Host "  7. status         - 서버/워커 상태 확인"
    Write-Host "  8. run_ui_mock    - UI 목 서버 실행"
    Write-Host "  9. collectstatic  - 정적 파일(css/js) 수집 (nginx 반영)$venvWarn"
    Write-Host "  R. restart        - 서버/워커 재시작$venvWarn"
    $nginxColor = if ($nginxOk) { "Green" } else { "Red" }
    Write-Host "  N. nginx          - nginx 시작/중지/reload  $nginxStat" -ForegroundColor $nginxColor
    Write-Host "  S. setup          - 초기 환경 설정 (최초 1회 / 새 PC)"
    Write-Host "  W. weekly 동기화  - ECM xlsx 다운로드 → PostgreSQL reference DB 적재$venvWarn"
    Write-Host "  G. Google Sheets  - 인증위 시트 → PostgreSQL reference_project 적재$venvWarn"
    Write-Host "  I. FAISS 임베딩   - reference DB 신규 데이터 증분 임베딩$venvWarn"
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
        '9' {
            Write-Host ""
            Write-Host "=== 정적 파일 수집 (collectstatic) ===" -ForegroundColor Cyan
            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) {
                $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
            }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 S(초기 환경 설정)를 실행하세요." -ForegroundColor Red
            } else {
                & $VenvPython (Join-Path $ScriptDir "manage.py") collectstatic --noinput
                if ($?) {
                    Write-Host "[OK] 정적 파일 수집 완료. nginx가 새 css/js를 제공합니다." -ForegroundColor Green
                    Write-Host "     브라우저에서 새로고침(F5)하면 반영됩니다." -ForegroundColor Yellow
                }
            }
        }
        'R' {
            Write-Host ""
            Write-Host "재시작 대상을 선택하세요:"
            Write-Host "  1) 서버만 재시작 (Django runserver)"
            Write-Host "  2) 워커만 재시작 (download_worker)"
            Write-Host "  3) 전체 재시작   (서버 + 워커)"
            $sub = Read-Host "선택"
            Write-Host ""
            switch ($sub) {
                '1' {
                    Write-Host "=== Django 서버 중지 ===" -ForegroundColor Yellow
                    & (Join-Path $ScriptDir "stop_server.ps1")
                    Write-Host ""
                    Write-Host "=== Django 서버 시작 ===" -ForegroundColor Green
                    & (Join-Path $ScriptDir "start_server.ps1")
                }
                '2' {
                    $live = Ask-YesNo "워커를 Live 모드로 실행할까요? (No = dry-run)"
                    Write-Host ""
                    Write-Host "=== 워커 중지 ===" -ForegroundColor Yellow
                    & (Join-Path $ScriptDir "stop_worker.ps1")
                    Write-Host ""
                    Write-Host "=== 워커 시작 ===" -ForegroundColor Green
                    if ($live) {
                        & (Join-Path $ScriptDir "start_worker.ps1") -Live
                    } else {
                        & (Join-Path $ScriptDir "start_worker.ps1")
                    }
                }
                '3' {
                    $live = Ask-YesNo "워커를 Live 모드로 실행할까요? (No = dry-run)"
                    Write-Host ""
                    Write-Host "=== 전체 중지 ===" -ForegroundColor Yellow
                    & (Join-Path $ScriptDir "stop_all.ps1")
                    Write-Host ""
                    Write-Host "=== 전체 시작 ===" -ForegroundColor Green
                    if ($live) {
                        & (Join-Path $ScriptDir "start_all.ps1") -Live
                    } else {
                        & (Join-Path $ScriptDir "start_all.ps1")
                    }
                }
                default { Write-Host "올바른 번호를 입력해 주세요." -ForegroundColor Red }
            }
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
        'W' {
            Write-Host ""
            Write-Host "=== weekly 동기화 (ECM 다운로드 → PostgreSQL) ===" -ForegroundColor Cyan
            Write-Host "  1) 자동 다운로드 후 처리"
            Write-Host "  2) 이미 받은 인증획득제품 엑셀 파일 경로 지정"
            $mode = Read-Host "선택 (1/2)"
            Write-Host ""

            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 S(초기 환경 설정)를 실행하세요." -ForegroundColor Red
            } elseif ($mode -eq '1') {
                $targetDate = Read-Host "대상 날짜 입력 (yyyymmdd, 생략 시 최신)"
                if ($targetDate) {
                    $env:GSCERT_WEEKLY_TARGET_DATE = $targetDate
                    Write-Host "  대상 날짜: $targetDate" -ForegroundColor Cyan
                } else {
                    Remove-Item Env:\GSCERT_WEEKLY_TARGET_DATE -ErrorAction SilentlyContinue
                }
                Remove-Item Env:\GSCERT_WEEKLY_SOURCE_XLSX -ErrorAction SilentlyContinue
                & $VenvPython (Join-Path $ScriptDir "main\utils\weekly.py")
                Remove-Item Env:\GSCERT_WEEKLY_TARGET_DATE -ErrorAction SilentlyContinue
            } elseif ($mode -eq '2') {
                $xlsxPath = Read-Host "엑셀 파일 경로 입력"
                $xlsxPath = $xlsxPath.Trim('"').Trim("'")
                if (-not (Test-Path $xlsxPath)) {
                    Write-Host "[ERROR] 파일을 찾을 수 없습니다: $xlsxPath" -ForegroundColor Red
                } else {
                    $env:GSCERT_WEEKLY_SOURCE_XLSX = $xlsxPath
                    Remove-Item Env:\GSCERT_WEEKLY_TARGET_DATE -ErrorAction SilentlyContinue
                    Write-Host "  파일: $xlsxPath" -ForegroundColor Cyan
                    & $VenvPython (Join-Path $ScriptDir "main\utils\weekly.py")
                    Remove-Item Env:\GSCERT_WEEKLY_SOURCE_XLSX -ErrorAction SilentlyContinue
                }
            } else {
                Write-Host "올바른 번호를 입력해 주세요." -ForegroundColor Red
            }
        }
        'G' {
            Write-Host ""
            Write-Host "=== Google Sheets 동기화 (인증위 시트 → PostgreSQL reference_project) ===" -ForegroundColor Cyan
            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 S(초기 환경 설정)를 실행하세요." -ForegroundColor Red
            } else {
                & $VenvPython (Join-Path $ScriptDir "manage.py") sync_reference_projects_from_sheet
                if ($?) {
                    Write-Host "[OK] Google Sheets 동기화 완료" -ForegroundColor Green
                }
            }
        }
        'I' {
            Write-Host ""
            Write-Host "=== FAISS 증분 임베딩 (신규 데이터만) ===" -ForegroundColor Cyan
            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 S(초기 환경 설정)를 실행하세요." -ForegroundColor Red
            } else {
                & $VenvPython (Join-Path $ScriptDir "manage.py") embed_db
                if ($?) {
                    Write-Host "[OK] 임베딩 완료" -ForegroundColor Green
                }
            }
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
