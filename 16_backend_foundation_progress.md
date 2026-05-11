# 백엔드 기반 구현 진행 기록

이 문서는 UI 검토 브랜치와 충돌하지 않도록 백엔드 기반 작업만 별도 브랜치에서 진행한 내용을 기록한다.

## 현재 브랜치

- 브랜치: `codex-backend-foundation`
- 기준 브랜치: `codex-job-runner-persistence`
- 목적: UI 파일 변경을 피하고, 작업 실행에 필요한 백엔드 기반을 먼저 구축한다.

## 구현 완료

### reference.db 조회 계층

`playwright_job/reference_repository.py`를 추가했다.

역할:

- `main/data/reference.db`의 `ecm` 테이블을 조회한다.
- `ecm` 테이블의 필수 컬럼이 모두 있는지 검증한다.
- `프로젝트번호`로 단건 프로젝트를 조회한다.
- 프로젝트 목록을 검색하고 전체 건수를 조회한다.

기본 기준:

- DB 경로: `main/data/reference.db`
- 테이블명: `ecm`
- 컬럼 타입: 문자열 기준
- 주요 검색 조건: 프로젝트번호, 회사명, 제품명, 시험PL, 점검결과

오류 구분:

- DB 파일 없음: `ReferenceDbNotFound`
- `ecm` 테이블 없음: `ReferenceTableNotFound`
- 필수 컬럼 누락: `ReferenceColumnMismatch`

### 단위 테스트

`playwright_job/tests/test_reference_repository.py`를 추가했다.

테스트 내용:

- 정상 스키마 검증
- 필수 컬럼 누락 검출
- DB 파일 없음 오류 검출
- `프로젝트번호` 단건 조회
- 회사명 부분 검색과 건수 조회

실행 명령:

```powershell
.\.venv\Scripts\python.exe -m unittest discover playwright_job/tests
```

현재 결과:

```text
Ran 5 tests
OK
```

## 다음 작업 후보

UI 파일을 건드리지 않고 이어갈 수 있는 다음 작업은 아래 순서가 적합하다.

1. `workflow.db` 저장소 계층 구현
2. 작업 락 저장소 구현
3. 작업 생성/진행상태/결과 조회용 서비스 계층 구현
4. 별도 작업자 프로세스의 dry-run 골격 구현
5. 다운로드 폴더 경로 설정값 관리 구현

## 아직 확정해야 할 점

- `workflow.db`의 실제 저장 위치와 백업 정책
- 작업 락에 DB row만 사용할지, PID 또는 heartbeat 정보를 함께 둘지
- 작업자 프로세스 시작/중지 스크립트 이름과 배포 위치
- 에이전트 다운로드 폴더 선택 팝업 자동화의 최종 검증 방식
- 실제 `reference.db` 샘플을 받았을 때 컬럼명과 값 형식이 설계와 완전히 일치하는지
