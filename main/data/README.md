# main/data Git Policy

서버 실행에 필요한 기준 데이터는 Git에 포함하고, 실행 중 계속 바뀌는 상태 파일은 제외한다.

## Git 포함

- `ecmlist.db`: download-review 프로젝트 목록과 점검 결과 기준 DB
- `reference.db`: 기존 이력/제품정보 조회 화면에서 사용하는 SQLite DB
- `reference.xlsx`: ECM에서 내려받아 누적 관리하는 기준 원본 데이터
- `prdinfo.xlsx`: 제품정보 양식 원본
- `security.xlsx`: 보안 취약점 매핑 데이터

`reference.db`는 아래 명령으로 `reference.xlsx`에서 재생성할 수 있다. 기본 실행은 DB 생성 후
`reference.xlsx`와 `reference.db` 변경분을 Git commit/push까지 수행한다.

이 명령은 실행될 때만 동작한다. 별도 스케줄러를 만들지 않았으며, 운영에서는 기존처럼
`weekly.py` 또는 배치 파일이 이 흐름을 시작한다. 현재 `weekly.py`는 ECM 원천 데이터를
`reference.xlsx`에 반영한 뒤 `manage.py sqlite`를 직접 호출한다.

```powershell
.\.venv\Scripts\python.exe manage.py sqlite
```

로컬 검증만 하고 Git 반영을 생략하려면 아래처럼 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py sqlite --no-git-sync
```

## Git 제외

- `workflow.db`: 작업 요청, 대기열, 진행상태, 로그 등 실행 이력 DB
- `ecm_agent.lock`: ECM/agent 동시 접근 방지용 로컬 잠금 파일
- `faiss_bge_m3_ko.idmap.index`, `ngram_table.npz`: 유틸리티가 생성하는 검색 인덱스
