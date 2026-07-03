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
    Write-Host "  C. collectstatic  - 정적 파일(css/js) 수집 (nginx 반영)$venvWarn"
    Write-Host "  R. restart        - 서버/워커 재시작$venvWarn"
    $nginxColor = if ($nginxOk) { "Green" } else { "Red" }
    Write-Host "  N. nginx          - nginx 시작/중지/reload  $nginxStat" -ForegroundColor $nginxColor
    Write-Host "  S. setup          - 초기 환경 설정 (최초 1회 / 새 PC)"
    Write-Host "  W. weekly 동기화  - ECM xlsx 다운로드 → PostgreSQL reference DB 적재$venvWarn"
    Write-Host "  G. Google Sheets  - 인증위 시트 → PostgreSQL reference_project 적재$venvWarn"
    Write-Host "  I. FAISS 임베딩   - reference DB 신규 데이터 증분 임베딩$venvWarn"
    $pgHost = if ($env:REFERENCE_PG_HOST) { $env:REFERENCE_PG_HOST } else { "미설정" }
    Write-Host "  P. PostgreSQL 설정 - 현재 HOST: $pgHost"
    Write-Host "  D. 규칙 DB 반영    - 점검규칙(config)을 PostgreSQL에 반영 (seed)$venvWarn"
    Write-Host "  B. 앱 빌드         - 로컬 검토 앱(GSCertLocalReview.exe) 재빌드"
    Write-Host "  U. Git 관리        - 원격 pull / 로컬 커밋·push"
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
            & (Join-Path $ScriptDir "start_all.ps1") -Live
        }
        '2' {
            Write-Host ""
            & (Join-Path $ScriptDir "start_server.ps1")
        }
        '3' {
            Write-Host ""
            $once   = Ask-YesNo "--once 모드로 실행할까요?"
            $nohead = Ask-YesNo "브라우저 창을 표시할까요? (No = headless)"
            Write-Host ""
            $params = @{ Live = $true }
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
        'C' {
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
                    Write-Host "=== 워커 중지 ===" -ForegroundColor Yellow
                    & (Join-Path $ScriptDir "stop_worker.ps1")
                    Write-Host ""
                    Write-Host "=== 워커 시작 ===" -ForegroundColor Green
                    & (Join-Path $ScriptDir "start_worker.ps1") -Live
                }
                '3' {
                    Write-Host "=== 전체 중지 ===" -ForegroundColor Yellow
                    & (Join-Path $ScriptDir "stop_all.ps1")
                    Write-Host ""
                    Write-Host "=== 전체 시작 ===" -ForegroundColor Green
                    & (Join-Path $ScriptDir "start_all.ps1") -Live
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
                if ($sub -eq '1') { Start-Process -FilePath $NginxExe -ArgumentList "-s reload" -WorkingDirectory $NginxDir -Wait -WindowStyle Hidden; Write-Host "[OK] nginx reload 완료" -ForegroundColor Green }
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
                $xlsxPath = Read-Host "폴더 또는 파일 경로 입력 (폴더 지정 시 인증획득제품 최신 파일 자동 선택)"
                $xlsxPath = $xlsxPath.Trim('"').Trim("'")
                if (-not (Test-Path $xlsxPath)) {
                    Write-Host "[ERROR] 경로를 찾을 수 없습니다: $xlsxPath" -ForegroundColor Red
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
                & $VenvPython -u (Join-Path $ScriptDir "manage.py") embed_db
                if ($?) {
                    Write-Host "[OK] 임베딩 완료" -ForegroundColor Green
                }
            }
        }
        'P' {
            Write-Host ""
            Write-Host "=== PostgreSQL 접속 설정 ===" -ForegroundColor Cyan
            $EnvFile = Join-Path $ScriptDir "env.ps1"
            $curHost = if ($env:REFERENCE_PG_HOST) { $env:REFERENCE_PG_HOST } else { "(미설정)" }
            $curPort = if ($env:REFERENCE_PG_PORT) { $env:REFERENCE_PG_PORT } else { "5432" }
            Write-Host "  현재 HOST : $curHost" -ForegroundColor Yellow
            Write-Host "  현재 PORT : $curPort" -ForegroundColor Yellow
            Write-Host ""
            $newHost = Read-Host "새 HOST 입력 (생략 시 변경 없음)"
            if ($newHost) {
                if (Test-Path $EnvFile) {
                    $content = Get-Content $EnvFile -Raw
                    $content = $content -replace '(\$env:REFERENCE_PG_HOST\s*=\s*")[^"]*(")', "`${1}$newHost`${2}"
                    [System.IO.File]::WriteAllText($EnvFile, $content, [System.Text.Encoding]::UTF8)
                    $env:REFERENCE_PG_HOST = $newHost
                    Write-Host "[OK] REFERENCE_PG_HOST 변경 완료: $newHost" -ForegroundColor Green
                    Write-Host "     서버/워커를 재시작해야 변경이 반영됩니다." -ForegroundColor Yellow
                } else {
                    Write-Host "[ERROR] env.ps1 파일이 없습니다. S(setup)를 먼저 실행하세요." -ForegroundColor Red
                }
            }
        }
        'D' {
            Write-Host ""
            Write-Host "=== 점검규칙 DB 반영 (seed_download_review_rules) ===" -ForegroundColor Cyan
            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 S(초기 환경 설정)를 실행하세요." -ForegroundColor Red
            } else {
                Write-Host "  코드의 점검규칙 정의(config_json)를 PostgreSQL(reference DB)에 반영합니다." -ForegroundColor Gray
                Write-Host "  ※ 주 서버(reference PostgreSQL)에서 실행해야 합니다." -ForegroundColor Yellow
                Write-Host ""
                $seedArgs = @((Join-Path $ScriptDir "manage.py"), "seed_download_review_rules", "--only-real", "--update-existing", "--enable")
                # 네이티브 명령의 stderr 가 종료성 오류로 처리되지 않도록 잠시 완화한다.
                $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                & $VenvPython @seedArgs
                $seedOk = ($LASTEXITCODE -eq 0)
                $ErrorActionPreference = $prevEAP
                if ($seedOk) {
                    Write-Host "[OK] 점검규칙 DB 반영 완료. 새로 시작되는 점검 작업부터 적용됩니다." -ForegroundColor Green
                } else {
                    Write-Host "[ERROR] seed 실패. 위 출력을 확인하세요(주 서버 PostgreSQL 접속/규칙 검증)." -ForegroundColor Red
                }
            }
        }
        'U' {
            Write-Host ""
            Write-Host "=== Git 관리 ===" -ForegroundColor Cyan
            Write-Host "  1) pull  - 원격 최신 코드 받기"
            Write-Host "  2) push  - 로컬 변경 커밋 후 업로드"
            $sub = Read-Host "선택"
            Write-Host ""
            # git 은 진행 메시지를 stderr 로 내보내므로, 종료성 오류로 처리되지 않게 완화한다.
            $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
            Push-Location $ScriptDir
            try {
                $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
                if ($branch) { Write-Host "  현재 브랜치: $($branch.Trim())" -ForegroundColor Gray }
                if ($sub -eq '1') {
                    git pull
                    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] git pull 완료. 코드 변경이 있으면 서버/워커를 재시작하세요(R)." -ForegroundColor Green }
                    else { Write-Host "[ERROR] git pull 실패. 위 출력을 확인하세요." -ForegroundColor Red }
                } elseif ($sub -eq '2') {
                    git status --short
                    Write-Host ""
                    $msg = Read-Host "커밋 메시지 입력 (생략 시 취소)"
                    if ($msg) {
                        git add -A
                        git commit -m $msg
                        git push
                        if ($LASTEXITCODE -eq 0) { Write-Host "[OK] git push 완료." -ForegroundColor Green }
                        else { Write-Host "[ERROR] git push 실패(또는 커밋할 변경 없음). 위 출력을 확인하세요." -ForegroundColor Red }
                    } else {
                        Write-Host "커밋 메시지가 없어 취소했습니다." -ForegroundColor Yellow
                    }
                } else {
                    Write-Host "올바른 번호를 입력해 주세요." -ForegroundColor Red
                }
            } finally {
                Pop-Location
                $ErrorActionPreference = $prevEAP
            }
        }
        'B' {
            Write-Host ""
            Write-Host "=== 로컬 검토 앱 빌드 (GSCertLocalReview.exe) ===" -ForegroundColor Cyan
            $AppDir      = Join-Path $ScriptDir "local_review_app"
            $BuildScript = Join-Path $AppDir "scripts\package_windows.ps1"
            $AppPython   = Join-Path $AppDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $BuildScript)) {
                Write-Host "[ERROR] 빌드 스크립트를 찾을 수 없습니다: $BuildScript" -ForegroundColor Red
            } elseif (-not (Test-Path $AppPython)) {
                Write-Host "[ERROR] 앱 전용 가상환경이 없습니다: $AppPython" -ForegroundColor Red
                Write-Host "        먼저 아래로 생성 후 다시 시도하세요:" -ForegroundColor Yellow
                Write-Host "          cd `"$AppDir`"; python -m venv .venv" -ForegroundColor Gray
            } else {
                Write-Host "  최신 gscert_review_core(엔진)를 포함해 exe 를 다시 빌드합니다. (수 분 소요)" -ForegroundColor Gray
                Write-Host "  실행 중인 GSCertLocalReview.exe 가 있으면 종료합니다." -ForegroundColor Gray
                # taskkill 은 프로세스가 없으면 stderr 를 내므로 Stop-Process 로 대체(없어도 무해).
                Get-Process -Name GSCertLocalReview -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
                $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                & powershell -ExecutionPolicy Bypass -File $BuildScript
                $buildOk = ($LASTEXITCODE -eq 0)
                $ErrorActionPreference = $prevEAP
                if ($buildOk) {
                    Write-Host "[OK] 앱 빌드 완료. local_review_app\dist\GSCertLocalReview 의 exe 를 배포하세요." -ForegroundColor Green
                } else {
                    Write-Host "[ERROR] 앱 빌드 실패. 위 출력을 확인하세요." -ForegroundColor Red
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
