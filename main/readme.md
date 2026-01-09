# main 앱 구조 문서 (README.md)

이 문서는 **Django 앱 `main`**의 폴더/파일 구조와 각 구성요소의 역할을 빠르게 파악하기 위한 내부 문서입니다.  
(요청 기준: 첨부된 5개 파이썬 파일 + 지정된 7개 폴더)

---

## 1) 폴더 구조

아래 폴더들은 `main/` 앱 하위에 존재한다고 가정합니다.

- **data/**  
  서버에서 관리하는 **원본 파일(업로드/샘플/중간 산출물 등)** 보관 폴더

- **commands/**  
  서버에서 **명령어 실행(배치/관리 작업 등)** 을 위한 파이썬 코드 보관 폴더  
  (예: Django management command 래퍼, subprocess 실행기 등)

- **static/**  
  Django 정적 자원 폴더 (**CSS / 이미지 / JS**)

- **templates/**  
  Django 템플릿 폴더 (**HTML**)

- **utils/**  
  서버에서 명령어 실행 시 동작하는 **공용 파이썬 유틸 코드** 보관 폴더  
  (예: 파일 처리, 파싱, 공통 서비스, 헬퍼 함수 등)

- **views/**  
  Django **view 함수/클래스**들이 보관된 폴더  
  (URL 라우팅에서 import 되는 `main.views.*` 모듈들이 여기에 위치)

---

## 2) 첨부된 핵심 파이썬 파일 5개

### 2.1 `apps.py` — 앱 설정(AppConfig)

- Django 앱 이름: `main`
- `ready()`가 존재하지만 현재는 **즉시 return** 하도록 되어 있어(실질 동작 없음)  
  추후 시그널 등록, 워밍업, 초기화 로직을 넣는 확장 포인트로 활용 가능

---

### 2.2 `models.py` — Job 모델(비동기/백그라운드 작업 상태 추적)

`Job` 모델은 “어떤 작업(task/job)이 진행 중인지/끝났는지/실패했는지”를 DB에 기록하기 위한 최소 단위 모델입니다.

- `id`: UUID (PK)
- `status`: `PENDING / RUNNING / DONE / ERROR` 상태 문자열
- `final_link`: 작업 완료 후 결과물 링크(URL) 저장
- `error`: 에러 메시지/스택 등 저장
- `created_at`, `updated_at`: 생성/수정 시각
- 기본 정렬: 최신 생성 순 (`ordering = ["-created_at"]`)

> 예상 사용 흐름: 작업 요청 시 Job 생성(PENDING) → 실행 시작 시 RUNNING → 완료 시 DONE + final_link → 실패 시 ERROR + error

---

### 2.3 `urls.py` — HTTP 라우팅(화면/기능 엔드포인트)

`main` 앱에서 제공하는 웹 페이지/기능 엔드포인트를 정의합니다.

#### 인증/기본 진입
- `/accounts/login/` : Django LoginView (템플릿 `registration/login.html`)
- `/` : `/index/` 로 리다이렉트
- `/index/` : 메인 화면

#### testing 관련
- `/history/` : 이력/히스토리
- `/similar/` : 유사도 기능(페이지)
- `/summarize_document/` : 문서 요약 처리
- `/security/` : 보안 페이지
- `/security/invicti/parse/` : Invicti 결과 파싱
- `/security/gpt/recommend/` : GPT 추천 수정 방안/권고(추정)

#### certy 관련
- `/prdinfo/` : 제품정보 페이지
- `/lookup_cert_info/` : 인증정보 조회(DB)
- `/generate_prdinfo/` : 제품정보 자동 생성
- `/source-excel/` : 원본 엑셀 소스 보기/업로드 등
- `/download-filled/` : 채워진 결과 다운로드

#### review 관련
- `/checkreport/` : 점검/리포트 페이지
- `/parse/` : 점검리포트 파싱

> `urls.py`는 `main.views.init`, `main.views.testing.*`, `main.views.certy.*`, `main.views.review.*` 를 import 해서 연결합니다.  
> 즉, 실 기능 구현은 `views/` 폴더 하위 모듈들에 위치합니다.

---

### 2.4 `routing.py` — WebSocket 라우팅(Channels)

Django Channels 사용 시 WebSocket URL 패턴을 정의합니다.

- WebSocket 엔드포인트:
  - `ws/status/<task_id>/`
  - `<task_id>`는 `[\w-]+` 로 정의되어 **UUID(하이픈 포함)** 도 수용 가능

---

### 2.5 `consumers.py` — WebSocket Consumer(진행상태 Push)

`StatusConsumer`는 특정 작업(task_id)의 상태를 **실시간으로 클라이언트에 푸시**하기 위한 Consumer입니다.

- connect:
  - URL에서 `task_id` 추출
  - 그룹명: `status_<task_id>`
  - `channel_layer.group_add()`로 그룹 구독
- disconnect:
  - `group_discard()`로 그룹 구독 해제
- send_progress(event):
  - 클라이언트로 JSON 전송:
    - `{"status": "...", "message": "..."}`

#### 서버에서 진행상태를 보내는 예시(개념)

백그라운드 작업 코드(예: `utils/` 또는 `commands/` 내부)에서 다음 형태로 그룹 전송을 하면,
클라이언트가 연결해 둔 websocket으로 상태가 전파됩니다.

```python
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

channel_layer = get_channel_layer()
async_to_sync(channel_layer.group_send)(
    f"status_{task_id}",
    {
        "type": "send_progress",   # consumers.py의 메서드명과 매칭
        "status": "RUNNING",
        "message": "문서 분석 중..."
    }
)
```

---

## 3) 권장 런타임 흐름(HTTP + WebSocket + Job)

1. 사용자가 페이지에서 “작업 실행” 버튼 클릭 → HTTP 요청(`/parse/`, `/generate_prdinfo/` 등)
2. 서버가 `Job`을 생성하고 `task_id`(UUID)를 클라이언트에 반환
3. 클라이언트는 `ws/status/<task_id>/` 로 WebSocket 연결
4. 서버의 실제 작업 로직이 진행되며 `group_send(type="send_progress")` 로 상태 push
5. 완료 시 `Job.status = DONE`, `final_link` 저장 → 클라이언트는 링크 표시/다운로드 제공
6. 실패 시 `Job.status = ERROR`, `error` 저장 → 클라이언트는 오류 표시

---

## 4) 체크포인트(유지보수 관점)

- `apps.py: ready()`가 현재 아무 것도 하지 않음  
  초기화 로직이 필요해지면 여기에 “시그널 등록/워밍업”을 넣는 패턴이 일반적입니다.
- `urls.py`는 기능이 많아질수록 “도메인별 urlconf 분리(예: testing_urls.py)”가 유지보수에 유리합니다.
- WebSocket 진행상태는 이벤트 구조를 표준화(예: `status`, `percent`, `stage`, `message`)하면
  프론트(UI) 구성과 테스트가 쉬워집니다.

---

## 5) TODO (문서 확장 포인트)

- `views/` 하위 실제 모듈별( testing / certy / review / init ) 기능 요약
- `templates/` 화면 목록과 각 화면이 호출하는 API/엔드포인트 매핑
- `static/` JS에서 websocket 연결하는 코드 위치 및 메시지 처리 규칙
- `data/` 폴더의 파일 정책(용량/보관 기간/정리 배치) 명시
