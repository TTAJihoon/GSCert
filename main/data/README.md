# main/data Git Policy

서버 실행에 필요한 기준 데이터는 Git에 포함하고, 실행 중 계속 바뀌는 상태 파일은 제외한다.

## Git 포함

- `ecmlist.db`: download-review 프로젝트 목록과 점검 결과 기준 DB
- `reference.db`: 기존 이력/제품정보 조회 화면에서 사용하는 SQLite DB
- `reference.csv`: `reference.db` 재생성 원본 데이터
- `prdinfo.xlsx`: 제품정보 양식 원본
- `security.xlsx`: 보안 취약점 매핑 데이터
- `csv`: 기존 호환용 데이터 파일

`reference.db`는 아래 명령으로 `reference.csv`에서 재생성할 수 있다.

```powershell
.\.venv\Scripts\python.exe main\utils\build_reference_db.py
```

## Git 제외

- `workflow.db`: 작업 요청, 대기열, 진행상태, 로그 등 실행 이력 DB
- `ecm_agent.lock`: ECM/agent 동시 접근 방지용 로컬 잠금 파일
- `faiss_bge_m3_ko.idmap.index`, `ngram_table.npz`: 유틸리티가 생성하는 검색 인덱스
