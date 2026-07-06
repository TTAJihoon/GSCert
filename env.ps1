# 런처(start_server.ps1 / start_worker.ps1)가 로드하는 환경 설정 파일.
#
# ★ 이 파일에는 비밀값(비밀번호/API 키)을 두지 않는다 → 안전하게 버전관리/푸시 가능.
#   비밀값은 set-secrets.ps1 로 시스템(Machine) 환경변수에 저장하고, 여기서 읽어온다.
#   새 서버에서는 set-secrets.ps1 을 복사해 1회 실행한 뒤 서버/워커를 기동하면 된다.

# ── 모든 설정을 시스템 환경변수(Machine → User)에서 "참조"한다 ──
# 두 서버(194/241)가 똑같은 변수 이름을 쓰고, 값만 각 서버의 OS 환경변수로 다르게 준다.
#   · 접속 설정(NAME/USER/HOST/PORT): 환경변수 없으면 기본값 사용
#   · 비밀값(PASSWORD/API 키): 환경변수 없으면 경고 (파일에 직접 입력하지 않는다)
# 환경변수는 프로세스 시작 시점에만 상속되므로, 여기서 명시적으로 Process 에 주입한다.
function Resolve-Env([string]$Name, [string]$Default = $null) {
    $value = [Environment]::GetEnvironmentVariable($Name, 'Machine')
    if ([string]::IsNullOrEmpty($value)) { $value = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if ([string]::IsNullOrEmpty($value)) { $value = $Default }
    if (-not [string]::IsNullOrEmpty($value)) { Set-Item -Path "Env:$Name" -Value $value }
}

# 표준 접속 설정 (환경변수 없으면 기본값 — 194 는 기본값이 곧 기존 동작)
Resolve-Env 'REFERENCE_PG_NAME' 'gscert_reference'
Resolve-Env 'REFERENCE_PG_USER' 'postgres'
Resolve-Env 'REFERENCE_PG_HOST' 'localhost'
Resolve-Env 'REFERENCE_PG_PORT' '5432'

# 비밀값 (환경변수 필수 — 기본값 없음)
Resolve-Env 'REFERENCE_PG_PASSWORD'   # PostgreSQL 비밀번호
Resolve-Env 'GEMINI_API_KEY'          # 보안성 AI 추천 등
Resolve-Env 'GOOGLE_API_KEY'          # GEMINI_API_KEY 대체용(선택)

# ── 필수 비밀값 누락 시 경고 ──
foreach ($required in @('REFERENCE_PG_PASSWORD', 'GEMINI_API_KEY')) {
    if (-not [Environment]::GetEnvironmentVariable($required, 'Process')) {
        Write-Warning "$required 환경변수가 설정되지 않았습니다. 시스템 환경변수(Machine/User)에 등록 후 재시작하세요."
    }
}
