<#
.SYNOPSIS
  GSCert 서버 관리 메뉴 런처
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 환경 변수 로드 (PostgreSQL 자격증명 등)
$EnvFile = Join-Path $ScriptDir "env.ps1"
if (Test-Path $EnvFile) { . $EnvFile }

# PID 파일 기반 실행 여부 확인 (서버/워커)
function Test-PidRunning($pidFile) {
    if (-not (Test-Path $pidFile)) { return $false }
    try {
        $procId = [int]((Get-Content $pidFile -Raw).Trim())
    } catch {
        return $false
    }
    return (Get-Process -Id $procId -ErrorAction SilentlyContinue) -ne $null
}

function Show-Menu {
    $venvOk = (Test-Path (Join-Path $ScriptDir ".venv\Scripts\python.exe")) -or
              (Test-Path (Join-Path $ScriptDir "venv\Scripts\python.exe"))
    $nginxOk   = (Get-Process -Name nginx -ErrorAction SilentlyContinue) -ne $null
    $serverOk  = Test-PidRunning (Join-Path $ScriptDir "run\django_runserver.pid")
    $workerOk  = Test-PidRunning (Join-Path $ScriptDir "run\download_worker.pid")
    $venvWarn  = if (-not $venvOk) { " [!setup 실행 필요]" } else { "" }

    $srvStat = if ($serverOk) { "[실행중]" } else { "[중지됨]" }
    $wrkStat = if ($workerOk) { "[실행중]" } else { "[중지됨]" }
    $ngxStat = if ($nginxOk)  { "[실행중]" } else { "[중지됨]" }

    $nginxModeFile = Join-Path $ScriptDir "run\nginx_mode.txt"
    $ngxModeLabel  = ""
    if ($nginxOk -and (Test-Path $nginxModeFile)) {
        $m = (Get-Content $nginxModeFile -Raw).Trim()
        $ngxModeLabel = if ($m -eq 'ConsultationOnly') { " (consultation만 HTTPS)" } else { " (전체 HTTPS)" }
    }
    $srvColor = if ($serverOk) { "Green" } else { "DarkGray" }
    $wrkColor = if ($workerOk) { "Green" } else { "DarkGray" }
    $ngxColor = if ($nginxOk)  { "Green" } else { "DarkGray" }

    Clear-Host
    Write-Host "=======================================" -ForegroundColor Cyan
    Write-Host "       GSCert 서버 관리 메뉴" -ForegroundColor Yellow
    if (-not $venvOk) {
        Write-Host "  [경고] 가상환경이 없습니다. 'setup'을 먼저 실행하세요." -ForegroundColor Red
    }
    Write-Host "=======================================" -ForegroundColor Cyan
    # 실행 상태 요약 (서버 / 워커 / nginx)
    Write-Host "  상태  " -NoNewline
    Write-Host "서버 $srvStat" -ForegroundColor $srvColor -NoNewline
    Write-Host "   워커 $wrkStat" -ForegroundColor $wrkColor -NoNewline
    Write-Host "   nginx $ngxStat$ngxModeLabel" -ForegroundColor $ngxColor
    Write-Host "---------------------------------------" -ForegroundColor DarkGray
    Write-Host "  1.    start        - 서버/워커 시작 (all/server/worker 선택)$venvWarn"
    Write-Host "  2.    stop         - 서버/워커 중지 (all/server/worker 선택)"
    Write-Host "  R.    restart      - 서버/워커 재시작$venvWarn"
    Write-Host "  s.    status       - 서버/워커 상태 확인"
    Write-Host "  C.    collectstatic- 정적 파일(css/js) 수집 (nginx 반영)$venvWarn"
    Write-Host "  N.    nginx        - nginx 시작/중지/reload  $ngxStat" -ForegroundColor $ngxColor
    Write-Host "  W.    weekly 동기화 - ECM xlsx → PostgreSQL reference DB 적재 + 신규 건 점검대상 프로젝트 반영$venvWarn"
    Write-Host "  f.    FAISS 임베딩  - reference DB 신규 데이터 증분 임베딩$venvWarn"
    Write-Host "  D.    점검규칙 관리 - 반영(seed) / 규칙·세부항목 on-off$venvWarn"
    Write-Host "  B.    로컬 검토 앱   - 빌드 / 빌드 없이 실행 선택"
    Write-Host "  LLM.  LLM 모델 관리 - 사용 가능 모델 조회 / 현재 모델 전환"
    Write-Host "  git.  Git 관리      - 원격 pull / 로컬 커밋·push"
    $pgHost = if ($env:REFERENCE_PG_HOST) { $env:REFERENCE_PG_HOST } else { "미설정" }
    Write-Host "  P.    PostgreSQL 설정- 현재 HOST: $pgHost"
    Write-Host "  setup. 초기 환경 설정 - 최초 1회 / 새 PC"
    Write-Host "  0.    종료"
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

# 서버/워커 대상 선택 (start/stop 공용). 반환: 'all' | 'server' | 'worker' | $null(취소)
function Select-Target($verb) {
    Write-Host "$verb 대상을 선택하세요:"
    Write-Host "  1) all     - 서버 + 워커"
    Write-Host "  2) server  - Django 서버만"
    Write-Host "  3) worker  - download_worker만"
    $sel = Read-Host "선택 (1/2/3)"
    switch ($sel) {
        '1' { return 'all' }
        '2' { return 'server' }
        '3' { return 'worker' }
        default { return $null }
    }
}

# weekly 동기화가 갱신한 main/data/reference.xlsx를 커밋·푸시한다.
# 변경이 없으면 조용히 넘어간다(빈 커밋 방지). git push 전에는 pull --rebase로
# 원격 변경을 먼저 통합해 non-fast-forward 거부를 방지한다(GIT 메뉴와 동일 패턴).
function Sync-ReferenceDataFile {
    $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    Push-Location $ScriptDir
    try {
        $dataFile = "main/data/reference.xlsx"
        $changed = (git status --porcelain -- $dataFile)
        if (-not $changed) {
            Write-Host "  reference.xlsx 변경 없음 — 커밋 생략." -ForegroundColor Gray
            return
        }
        Write-Host ""
        Write-Host "  reference.xlsx 변경을 커밋·푸시합니다..." -ForegroundColor Cyan
        git add -- $dataFile
        git commit -m "data: reference.xlsx 갱신"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] git commit 실패. 위 출력을 확인하세요." -ForegroundColor Red
            return
        }
        git pull --rebase
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] git pull --rebase 실패(충돌 가능). 'git status'로 충돌 해결 후 GIT 메뉴에서 다시 push 하세요." -ForegroundColor Red
            return
        }
        git push
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] reference.xlsx 커밋·푸시 완료." -ForegroundColor Green
        } else {
            Write-Host "[ERROR] git push 실패. 위 출력을 확인하세요." -ForegroundColor Red
        }
    } finally {
        Pop-Location
        $ErrorActionPreference = $prevEAP
    }
}

# HTTPS 적용 범위 선택 (nginx 시작/모드 변경 공용). 반환: 'All' | 'ConsultationOnly' | $null(취소)
function Select-HttpsMode {
    Write-Host "HTTPS 적용 범위를 선택하세요:"
    Write-Host "  1) 전체 HTTPS           - 모든 페이지를 https로 서비스 (기본)"
    Write-Host "  2) consultation만 HTTPS - /consultation/ 만 https, 나머지는 http로 접속"
    $sel = Read-Host "선택 (1/2)"
    switch ($sel) {
        '1' { return 'All' }
        '2' { return 'ConsultationOnly' }
        default { return $null }
    }
}

while ($true) {
    Show-Menu
    $choice = Read-Host "`n번호 선택"

    switch ($choice.ToUpper()) {
        '1' {
            Write-Host ""
            $target = Select-Target "시작"
            Write-Host ""
            switch ($target) {
                'all'    { & (Join-Path $ScriptDir "start_all.ps1") -Live }
                'server' { & (Join-Path $ScriptDir "start_server.ps1") }
                'worker' {
                    $once   = Ask-YesNo "--once 모드로 실행할까요?"
                    $nohead = Ask-YesNo "브라우저 창을 표시할까요? (No = headless)"
                    Write-Host ""
                    $params = @{ Live = $true }
                    if ($once)   { $params['Once'] = $true }
                    if ($nohead) { $params['NoHeadless'] = $true }
                    & (Join-Path $ScriptDir "start_worker.ps1") @params
                }
                default  { Write-Host "취소했습니다." -ForegroundColor Yellow }
            }
        }
        '2' {
            Write-Host ""
            $target = Select-Target "중지"
            Write-Host ""
            switch ($target) {
                'all'    { & (Join-Path $ScriptDir "stop_all.ps1") }
                'server' { & (Join-Path $ScriptDir "stop_server.ps1") }
                'worker' { & (Join-Path $ScriptDir "stop_worker.ps1") }
                default  { Write-Host "취소했습니다." -ForegroundColor Yellow }
            }
        }
        'S' {
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
                Write-Host "  3) HTTPS 적용 범위 변경 (conf 재생성 후 reload)"
                $sub = Read-Host "선택"
                if ($sub -eq '1') { Start-Process -FilePath $NginxExe -ArgumentList "-s reload" -WorkingDirectory $NginxDir -Wait -WindowStyle Hidden; Write-Host "[OK] nginx reload 완료" -ForegroundColor Green }
                elseif ($sub -eq '2') { & (Join-Path $ScriptDir "stop_nginx.ps1") }
                elseif ($sub -eq '3') {
                    $mode = Select-HttpsMode
                    if ($mode) { & (Join-Path $ScriptDir "start_nginx.ps1") -Mode $mode }
                    else { Write-Host "취소했습니다." -ForegroundColor Yellow }
                }
            } else {
                $mode = Select-HttpsMode
                if ($mode) { & (Join-Path $ScriptDir "start_nginx.ps1") -Mode $mode }
                else { Write-Host "취소했습니다." -ForegroundColor Yellow }
            }
        }
        'SETUP' {
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
                if ($?) { Sync-ReferenceDataFile }
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
                    if ($?) { Sync-ReferenceDataFile }
                }
            } else {
                Write-Host "올바른 번호를 입력해 주세요." -ForegroundColor Red
            }
        }
        'F' {
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
        'LLM' {
            Write-Host ""
            Write-Host "=== LLM 모델 관리 ===" -ForegroundColor Cyan
            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 setup(초기 환경 설정)을 실행하세요." -ForegroundColor Red
            } else {
                $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                & $VenvPython (Join-Path $ScriptDir "manage.py") llm_model list
                $listOk = ($LASTEXITCODE -eq 0)
                if ($listOk) {
                    Write-Host ""
                    $modelIndex = Read-Host "전환할 모델 번호 입력 (변경하지 않으려면 Enter)"
                    if ($modelIndex) {
                        & $VenvPython (Join-Path $ScriptDir "manage.py") llm_model select --index $modelIndex
                        if ($LASTEXITCODE -eq 0) {
                            Write-Host "  이후 모든 AI 기능에 즉시 적용됩니다." -ForegroundColor Yellow
                        }
                    } else {
                        Write-Host "변경하지 않았습니다." -ForegroundColor Yellow
                    }
                } else {
                    Write-Host "[ERROR] LLM 모델 목록을 조회하지 못했습니다." -ForegroundColor Red
                }
                $ErrorActionPreference = $prevEAP
            }
        }
        'P' {
            Write-Host ""
            Write-Host "=== PostgreSQL 접속 설정 ===" -ForegroundColor Cyan
            # env.ps1 이 시스템 환경변수(Machine→User)를 참조하므로, 여기서도
            # 파일이 아니라 OS 환경변수에 저장한다. (관리자면 Machine, 아니면 User)
            $curHost = [Environment]::GetEnvironmentVariable('REFERENCE_PG_HOST','Machine')
            if (-not $curHost) { $curHost = [Environment]::GetEnvironmentVariable('REFERENCE_PG_HOST','User') }
            if (-not $curHost) { $curHost = "(미설정 → 기본 localhost)" }
            Write-Host "  현재 HOST : $curHost" -ForegroundColor Yellow
            Write-Host ""
            $newHost = Read-Host "새 HOST 입력 (생략 시 변경 없음)"
            if ($newHost) {
                $scope = 'Machine'
                try {
                    [Environment]::SetEnvironmentVariable('REFERENCE_PG_HOST', $newHost, 'Machine')
                } catch {
                    $scope = 'User'
                    [Environment]::SetEnvironmentVariable('REFERENCE_PG_HOST', $newHost, 'User')
                }
                $env:REFERENCE_PG_HOST = $newHost
                Write-Host "[OK] REFERENCE_PG_HOST 저장 ($scope): $newHost" -ForegroundColor Green
                Write-Host "     서버/워커를 재시작하면 반영됩니다." -ForegroundColor Yellow
            }
        }
        'D' {
            Write-Host ""
            Write-Host "=== 점검규칙 관리 ===" -ForegroundColor Cyan
            Write-Host "  1) 반영 - 점검규칙 정의(config_json)를 PostgreSQL(reference DB)에 반영 (seed)"
            Write-Host "  2) 수정 - 규칙 전체 또는 세부항목을 켜고 끄기"
            $dSel = Read-Host "선택 (1/2)"

            $VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
            if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
            if (-not (Test-Path $VenvPython)) {
                Write-Host "[ERROR] 가상환경 Python을 찾을 수 없습니다. 먼저 S(초기 환경 설정)를 실행하세요." -ForegroundColor Red
            } elseif ($dSel -eq '1') {
                Write-Host ""
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
            } elseif ($dSel -eq '2') {
                Write-Host ""
                Write-Host "  1) 규칙별   - 규칙 하나를 통째로 켜거나 끈다"
                Write-Host "  2) 세부항목별 - 규칙 안의 세부 점검항목 하나만 켜거나 끈다"
                $modeSel = Read-Host "선택 (1/2)"
                $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'

                if ($modeSel -eq '1') {
                    Write-Host ""
                    & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle list-rules
                    Write-Host ""
                    $code = Read-Host "on/off 할 규칙의 code 입력 (예: artifact_12)"
                    if ($code) {
                        $onoff = Read-Host "켤까요, 끌까요? (on/off)"
                        if ($onoff -eq 'on') {
                            & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle toggle-rule --code $code --enable
                        } elseif ($onoff -eq 'off') {
                            & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle toggle-rule --code $code --disable
                        } else {
                            Write-Host "[취소] on 또는 off 만 입력할 수 있습니다." -ForegroundColor Yellow
                        }
                    }
                } elseif ($modeSel -eq '2') {
                    Write-Host ""
                    & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle list-rules
                    Write-Host ""
                    $code = Read-Host "세부항목을 볼 규칙의 code 입력 (예: artifact_11)"
                    if ($code) {
                        Write-Host ""
                        & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle list-sub-checks --code $code
                        Write-Host ""
                        $position = Read-Host "on/off 할 세부항목 번호 입력"
                        $onoff = Read-Host "켤까요, 끌까요? (on/off)"
                        if ($position -and $onoff -eq 'on') {
                            & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle toggle-sub-check --code $code --position $position --enable
                        } elseif ($position -and $onoff -eq 'off') {
                            & $VenvPython (Join-Path $ScriptDir "manage.py") rule_toggle toggle-sub-check --code $code --position $position --disable
                        } else {
                            Write-Host "[취소] 번호와 on/off를 모두 입력해야 합니다." -ForegroundColor Yellow
                        }
                    }
                } else {
                    Write-Host "[취소] 1 또는 2를 선택해 주세요." -ForegroundColor Yellow
                }
                $ErrorActionPreference = $prevEAP
                Write-Host ""
                Write-Host "  변경은 즉시 reference DB에 저장됩니다. 이미 실행 중인 점검에는 영향 없고, 새로 시작하는 점검부터 적용됩니다." -ForegroundColor Gray
            } else {
                Write-Host "[취소] 1 또는 2를 선택해 주세요." -ForegroundColor Yellow
            }
        }
        'GIT' {
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
                    # 워킹트리에 커밋되지 않은(수정된 추적) 파일이 있으면 rebase pull 이
                    # "cannot pull with rebase: You have unstaged changes" 로 막힌다.
                    # 이때 어떤 파일인지 콘솔에서 바로 보여주고 처리 방법을 고르게 한다.
                    $dirty = (git status --porcelain)
                    if ($dirty) {
                        Write-Host "[!] 커밋되지 않은 로컬 변경이 있어 pull 이 막힙니다. 변경된 파일:" -ForegroundColor Yellow
                        git status --short
                        Write-Host ""
                        Write-Host "  s) stash 후 pull  - 변경을 임시 보관 → pull → 자동 복원 (안전)" -ForegroundColor Gray
                        Write-Host "  d) 버리고 pull    - 로컬 변경 폐기 후 pull (되돌릴 수 없음)" -ForegroundColor Gray
                        Write-Host "  c) 취소" -ForegroundColor Gray
                        $act = Read-Host "선택"
                        if ($act -eq 's') {
                            git stash push -u -m "console-pull-autostash"
                            if ($LASTEXITCODE -ne 0) {
                                Write-Host "[ERROR] stash 실패. 중단합니다." -ForegroundColor Red
                            } else {
                                git pull
                                $pullOk = ($LASTEXITCODE -eq 0)
                                Write-Host "  보관한 변경을 복원(stash pop)합니다..." -ForegroundColor Gray
                                git stash pop
                                if (-not $pullOk) {
                                    Write-Host "[ERROR] git pull 실패. 위 출력을 확인하세요." -ForegroundColor Red
                                } elseif ($LASTEXITCODE -ne 0) {
                                    Write-Host "[!] pull 은 됐으나 stash 복원 중 충돌이 있습니다. 'git status'로 해결하세요." -ForegroundColor Yellow
                                } else {
                                    Write-Host "[OK] git pull + 변경 복원 완료. 코드 변경이 있으면 재시작(R)." -ForegroundColor Green
                                }
                            }
                        } elseif ($act -eq 'd') {
                            git restore .
                            git pull
                            if ($LASTEXITCODE -eq 0) { Write-Host "[OK] 로컬 변경 폐기 후 git pull 완료. 코드 변경이 있으면 재시작(R)." -ForegroundColor Green }
                            else { Write-Host "[ERROR] git pull 실패. 위 출력을 확인하세요." -ForegroundColor Red }
                        } else {
                            Write-Host "취소했습니다." -ForegroundColor Yellow
                        }
                    } else {
                        git pull
                        if ($LASTEXITCODE -eq 0) { Write-Host "[OK] git pull 완료. 코드 변경이 있으면 서버/워커를 재시작하세요(R)." -ForegroundColor Green }
                        else { Write-Host "[ERROR] git pull 실패. 위 출력을 확인하세요." -ForegroundColor Red }
                    }
                } elseif ($sub -eq '2') {
                    git status --short
                    Write-Host ""
                    $msg = Read-Host "커밋 메시지 입력 (생략 시 취소)"
                    if ($msg) {
                        git add -A
                        git commit -m $msg
                        # push 전에 원격 변경을 먼저 통합(rebase)해 non-fast-forward 거부를 방지한다.
                        git pull --rebase
                        if ($LASTEXITCODE -ne 0) {
                            Write-Host "[ERROR] git pull --rebase 실패(충돌 가능). 'git status'로 충돌 해결 후 다시 시도하세요." -ForegroundColor Red
                        } else {
                            git push
                            if ($LASTEXITCODE -eq 0) { Write-Host "[OK] git push 완료." -ForegroundColor Green }
                            else { Write-Host "[ERROR] git push 실패. 위 출력을 확인하세요." -ForegroundColor Red }
                        }
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
            Write-Host "=== 로컬 검토 앱 (GSCertLocalReviewDashboard) ===" -ForegroundColor Cyan
            Write-Host "  1) 빌드          - exe 재빌드 (수 분 소요, 배포용)"
            Write-Host "  2) 빌드 없이 실행 - .venv python으로 run_dashboard.py 바로 실행 (빠른 테스트용)"
            $bsub = Read-Host "선택 (1/2)"
            Write-Host ""
            $AppDir    = Join-Path $ScriptDir "local_review_app"
            $AppPython = Join-Path $AppDir ".venv\Scripts\python.exe"
            if ($bsub -eq '1') {
                $BuildScript = Join-Path $AppDir "scripts\package_windows_dashboard.ps1"
                if (-not (Test-Path $BuildScript)) {
                    Write-Host "[ERROR] 빌드 스크립트를 찾을 수 없습니다: $BuildScript" -ForegroundColor Red
                } elseif (-not (Test-Path $AppPython)) {
                    Write-Host "[ERROR] 앱 전용 가상환경이 없습니다: $AppPython" -ForegroundColor Red
                    Write-Host "        먼저 아래로 생성 후 다시 시도하세요:" -ForegroundColor Yellow
                    Write-Host "          cd `"$AppDir`"; python -m venv .venv" -ForegroundColor Gray
                } else {
                    Write-Host "  최신 gscert_review_core(엔진)를 포함해 exe 를 다시 빌드합니다. (수 분 소요)" -ForegroundColor Gray
                    Write-Host "  실행 중인 GSCertLocalReviewDashboard.exe 가 있으면 종료합니다." -ForegroundColor Gray
                    # taskkill 은 프로세스가 없으면 stderr 를 내므로 Stop-Process 로 대체(없어도 무해).
                    Get-Process -Name GSCertLocalReviewDashboard -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
                    $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
                    & powershell -ExecutionPolicy Bypass -File $BuildScript
                    $buildOk = ($LASTEXITCODE -eq 0)
                    $ErrorActionPreference = $prevEAP
                    if ($buildOk) {
                        Write-Host "[OK] 앱 빌드 완료. local_review_app\dist\GSCertLocalReviewDashboard 의 exe 를 배포하세요." -ForegroundColor Green
                    } else {
                        Write-Host "[ERROR] 앱 빌드 실패. 위 출력을 확인하세요." -ForegroundColor Red
                    }
                }
            } elseif ($bsub -eq '2') {
                $RunScript = Join-Path $AppDir "run_dashboard.py"
                if (-not (Test-Path $AppPython)) {
                    Write-Host "[ERROR] 앱 전용 가상환경이 없습니다: $AppPython" -ForegroundColor Red
                    Write-Host "        먼저 아래로 생성 후 다시 시도하세요:" -ForegroundColor Yellow
                    Write-Host "          cd `"$AppDir`"; python -m venv .venv" -ForegroundColor Gray
                } elseif (-not (Test-Path $RunScript)) {
                    Write-Host "[ERROR] 실행 스크립트를 찾을 수 없습니다: $RunScript" -ForegroundColor Red
                } else {
                    Write-Host "  빌드 없이 .venv python 으로 바로 실행합니다(빌드 반영 안 됨, 코드 테스트용)." -ForegroundColor Gray
                    Start-Process -FilePath $AppPython -ArgumentList "run_dashboard.py" -WorkingDirectory $AppDir
                    Write-Host "[OK] 실행했습니다. 앱 창을 확인하세요(메뉴는 바로 계속 사용할 수 있습니다)." -ForegroundColor Green
                }
            } else {
                Write-Host "올바른 번호를 입력해 주세요." -ForegroundColor Red
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
