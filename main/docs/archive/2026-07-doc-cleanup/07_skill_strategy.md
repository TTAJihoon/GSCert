# Skill 활용 전략

## 목적

반복되는 설계, 자동화, 검사 규칙 작성 작업을 Codex Skill로 분리하여 이후 개발과 유지보수를 더 안정적으로 진행한다.

## 지금 당장 만들지 않는 이유

아직 자동화 흐름과 검사 규칙이 완전히 확정되지 않았다.

먼저 루트 MD 문서로 설계를 안정화하고, 반복되는 작업 패턴이 명확해진 뒤 Skill로 분리한다.

## Skill 후보 1: ECM 자동화 설계 Skill

용도:

- 웹페이지1 자동화 흐름을 검토할 때
- Playwright selector를 안정화할 때
- 에이전트 다운로드 창 처리 흐름을 수정할 때

포함할 내용:

- 웹페이지1 주소
- 프로젝트 폴더 탐색 방식
- 다운로드 메뉴 실행 방식
- 폴더 찾아보기 팝업 처리 방식
- 전송현황/시스템 알림 창 처리 방식

적합도:

- 높음

이유:

- 자동화 절차가 환경 의존적이고 실수 가능성이 높다.
- selector, 창 제목, 실패 정책을 매번 다시 설명하지 않아도 된다.

## Skill 후보 2: 검사 규칙 작성 Skill

용도:

- Word/Excel/PDF/파일명 검사 규칙을 추가할 때
- DB에 저장할 rule_type과 config_json을 설계할 때
- 규칙별 결과 메시지 형식을 통일할 때

포함할 내용:

- 검사 규칙 DB 구조
- Excel 셀 검사 예시
- Word 표 위치 검사 예시
- 파일명/확장자/수정시간 검사 예시
- pass/fail/warning/error 기준

적합도:

- 매우 높음

이유:

- 앞으로 규칙을 하나씩 계속 추가할 예정이므로 재사용성이 크다.

## Skill 후보 3: 프로젝트 문서화 Skill

용도:

- 각 폴더의 readme.md를 한글로 갱신할 때
- 루트 설계 MD 문서를 최신 상태로 유지할 때
- 코드 변경 후 문서 누락을 확인할 때

포함할 내용:

- 문서 작성 규칙
- 폴더별 readme.md 필수 항목
- 설계 변경 시 갱신해야 할 루트 MD 목록
- 루트 설계 문서와 폴더별 readme.md의 역할 구분

적합도:

- 중간

이유:

- 문서화는 중요하지만 자동화/검사 규칙보다 절차 복잡도는 낮다.

## 추천 순서

1. download-review 유지보수 Skill
2. 검사 규칙 작성 Skill
3. ECM 자동화 설계 Skill
4. 프로젝트 문서화 Skill

## 제작 완료

### `gscert-download-review-maintainer`

위치:

```text
C:\Users\jh910\.codex\skills\gscert-download-review-maintainer
```

저장소 배포용 사본:

```text
main/docs/codex_skills/gscert-download-review-maintainer
```

다른 개발 PC 설치:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force `
  ".\main\docs\codex_skills\gscert-download-review-maintainer" `
  "$env:USERPROFILE\.codex\skills\gscert-download-review-maintainer"
```

용도:

- `/download-review/` UI/API/worker/DB 구조를 이어서 수정할 때
- `main/docs/00_next_step.md` 중심으로 handoff를 갱신할 때
- 센터 분기, active job 전역 기준, `ecmlist*.db`/`workflow.db` 분리를 다시 확인할 때
- 실제 규칙 작성 전후로 draft 규칙 운영 정책을 확인할 때

구성:

- `SKILL.md`: 핵심 workflow와 검증 명령
- `references/architecture.md`: 파일 구조, DB 분리, API 원칙
- `references/operations.md`: 서버/worker/ECM 자동화/검증 절차
- `references/ecm_navigation.md`: ECM 트리 탐색과 문서 목록 체크박스 선택 지침
- `references/rules.md`: draft 규칙, 실제 규칙 전환, 결과 저장 기준

검증:

```powershell
.\.venv\Scripts\python.exe C:\Users\jh910\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\jh910\.codex\skills\gscert-download-review-maintainer
```

## Skill 생성 전 확정할 것

- 검사 규칙 작성 Skill: 실제 규칙 예시 3개 이상
- ECM 자동화 Skill: 영남 live 다운로드 검증 결과
- 프로젝트 문서화 Skill: 폴더별 `readme.md` 갱신 자동화 범위

## 문서화 Skill에 반영할 현재 정책

폴더별 `readme.md`는 설계 회의록이 아니라 해당 폴더의 하위 폴더와 파일 내용을 설명하는 가이드 문서로 작성한다.

상세 정책은 `11_readme_policy.md`에서 관리한다.
