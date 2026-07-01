# 런처(start_server.ps1 / start_worker.ps1)가 로드하는 환경 설정 파일.
#
# ★ 이 파일에는 비밀값(비밀번호/API 키)을 두지 않는다 → 안전하게 버전관리/푸시 가능.
#   비밀값은 set-secrets.ps1 로 시스템(Machine) 환경변수에 저장하고, 여기서 읽어온다.
#   새 서버에서는 set-secrets.ps1 을 복사해 1회 실행한 뒤 서버/워커를 기동하면 된다.

# ── 비밀 아님(표준 접속 설정) — 서버별로 다르면 이 값만 수정 ──
$env:REFERENCE_PG_NAME = "gscert_reference"
$env:REFERENCE_PG_USER = "postgres"
$env:REFERENCE_PG_HOST = "localhost"
$env:REFERENCE_PG_PORT = "5432"

# ── 비밀값: 프로세스 환경에 없으면 Machine → User 순으로 끌어온다 ──
# (환경변수는 프로세스 시작 시점에만 상속되므로, 런처가 여기서 명시적으로 주입한다.)
function Import-SecretEnv([string]$Name) {
    if ([Environment]::GetEnvironmentVariable($Name, 'Process')) { return }
    $value = [Environment]::GetEnvironmentVariable($Name, 'Machine')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if ($value) { Set-Item -Path "Env:$Name" -Value $value }
}

Import-SecretEnv 'REFERENCE_PG_PASSWORD'   # PostgreSQL 비밀번호
Import-SecretEnv 'GEMINI_API_KEY'          # 보안성 AI 추천 등
Import-SecretEnv 'GOOGLE_API_KEY'          # GEMINI_API_KEY 대체용(선택)

# ── 필수 비밀값 누락 시 경고 ──
foreach ($required in @('REFERENCE_PG_PASSWORD', 'GEMINI_API_KEY')) {
    if (-not [Environment]::GetEnvironmentVariable($required, 'Process')) {
        Write-Warning "$required 가(이) 설정되지 않았습니다. 관리자 PowerShell에서 set-secrets.ps1 을 먼저 실행하세요."
    }
}
