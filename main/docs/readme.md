# main/docs

## 역할

프로젝트 설계 문서를 보관한다.

## 관리 기준

- `00_*.md`처럼 숫자 prefix가 붙은 설계 문서는 이 폴더에 둔다.
- 각 코드, 템플릿, static 폴더의 `readme.md`는 해당 폴더 안에 유지한다.
- 다른 PC에서 이어가기 위한 즉시 인수인계 문서는 `00_next_step.md`에 최신 상태만 간결하게 남긴다.
- 누적 설계와 결정사항은 주제별 문서에 나누어 기록한다.

## 주요 문서

| 문서 | 역할 |
| --- | --- |
| `00_next_step.md` | 직전 작업과 바로 다음 작업 |
| `02_database_design.md` | `ecmlist.db`, `workflow.db` 설계 |
| `05_zip_inspection.md` | 다운로드 파일 점검과 규칙 결과 관리 |
| `08_ui_api_design.md` | download-review UI/API 계약 |
| `15_open_decisions.md` | 남은 결정사항 |
| `17_llm_review_interface.md` | LLM 기반 점검 인터페이스와 수동 테스트 방식 |
| `codex_skills/` | 다른 개발 PC에서 설치할 Codex skill 배포용 사본 |
