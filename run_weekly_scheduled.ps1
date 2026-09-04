<#
.SYNOPSIS
  예약 작업(Task Scheduler) 전용: 매일 18:00 weekly 동기화(자동 다운로드) 실행 후,
  정규화 후 신규 행이 있으면 FAISS 임베딩까지 자동 수행한다.

.DESCRIPTION
  서버 관리 콘솔(launcher.ps1)의 'W. weekly 동기화 > 1) 자동 다운로드 후 처리'와 동일한
  방식으로 main\utils\weekly.py 를 실행한다. 단, 이 스케줄 작업은 reference.xlsx 의
  git commit/push 는 수행하지 않는다(로컬 PostgreSQL reference DB 반영까지만).
  필요 시 콘솔의 W 메뉴에서 수동으로 git push 하면 된다.

  main\utils\weekly.py 의 종료 코드:
    0 = 정상 종료, 정규화 후 신규 행 없음
    2 = 정상 종료, 정규화 후 신규 행 있음(A~N + O/P/Q > 0) -> FAISS 임베딩 실행
    1 = 처리 중 예외 발생
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$EnvFile = Join-Path $ScriptDir "env.ps1"
if (Test-Path $EnvFile) { . $EnvFile }

$LogDir = Join-Path $ScriptDir "run"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "scheduled_weekly.log"

function Write-Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line
}

$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { $VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe" }
if (-not (Test-Path $VenvPython)) {
    Write-Log "[ERROR] 가상환경 Python을 찾을 수 없습니다: $VenvPython"
    exit 1
}

# 자동 다운로드(최신) 모드 강제 — 콘솔 W>1) 에서 대상 날짜를 생략한 것과 동일
Remove-Item Env:\GSCERT_WEEKLY_TARGET_DATE -ErrorAction SilentlyContinue
Remove-Item Env:\GSCERT_WEEKLY_SOURCE_XLSX -ErrorAction SilentlyContinue

Write-Log "=== weekly 동기화 시작 (자동 다운로드 후 처리) ==="

# 네이티브 프로세스 stderr 가 종료성 오류로 처리되지 않도록 완화(launcher.ps1과 동일 패턴)
$prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $VenvPython (Join-Path $ScriptDir "main\utils\weekly.py")
$weeklyExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

switch ($weeklyExit) {
    1 { Write-Log "[ERROR] weekly 동기화 실패(예외, exit=$weeklyExit). 상세: main\data\weekly_gs_sync.log 확인." }
    2 { Write-Log "[OK] weekly 동기화 완료(정규화 후 신규 행 있음, exit=$weeklyExit) -> FAISS 임베딩 실행." }
    0 { Write-Log "[OK] weekly 동기화 완료(신규 행 없음, exit=$weeklyExit) -> FAISS 임베딩 생략." }
    default { Write-Log "[WARN] weekly 동기화 종료 코드가 예상 범위를 벗어남: exit=$weeklyExit" }
}

if ($weeklyExit -eq 2) {
    $prevEAP = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $VenvPython -u (Join-Path $ScriptDir "manage.py") embed_db
    $embedExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP

    if ($embedExit -eq 0) {
        Write-Log "[OK] FAISS 임베딩 완료(exit=$embedExit)."
    } else {
        Write-Log "[ERROR] FAISS 임베딩 실패(exit=$embedExit)."
    }
}

Write-Log "=== 종료 ==="
