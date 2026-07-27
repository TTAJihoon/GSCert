# 유사 제품 자동 입력 문서 분석

## 지원 형식

- PDF: 텍스트 블록을 페이지 순서로 추출하고, 텍스트가 거의 없는 페이지만 Tesseract `kor+eng` OCR 적용
- DOCX: 본문, 표, 머리글, 바닥글, 각주, 미주, 메모의 OOXML 텍스트 추출
- DOC: Microsoft Word COM으로 DOCX 변환 후 분석
- XLSX: 시트·행·셀 주소, 표시값, 수식을 함께 보존
- XLS: Microsoft Excel COM으로 XLSX 변환 후 분석
- PPTX: 슬라이드 도형, 그룹 도형, 표, 차트 제목·계열, 발표자 노트 추출
- PPT: Microsoft PowerPoint COM으로 PPTX 변환 후 분석
- HWP: `olefile`로 HWP 5.x BodyText 레코드 직접 분석
- HWPX: ZIP/OWPML XML 섹션 직접 분석
- MD: 제목과 섹션 구조를 보존해 분석

암호·DRM이 설정된 문서는 우회하지 않는다. 사용자가 암호 또는 DRM을 해제한 사본을
업로드해야 한다.

## 서버 준비

1. Microsoft Word, Excel, PowerPoint가 설치되어 있어야 한다.
2. Python 패키지는 프로젝트 `requirements.txt`로 설치한다.
3. 관리자 PowerShell이 아닌 일반 사용자 PowerShell에서도 아래 스크립트를 실행할 수 있다.

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\install_document_parsers.ps1
```

이 스크립트는 Tesseract를 설치하고 한국어·영어 학습 데이터를
`%LOCALAPPDATA%\GSCert\tessdata`에 준비한다.

## 처리 흐름

자동 입력 파일은 동일한 하나의 제품 자료로 취급한다.

1. 브라우저에서 지원 확장자 파일을 복수 선택한다.
2. 서버가 작업 ID를 반환하고 백그라운드 분석을 시작한다.
3. 파일별로 실제 컨테이너 형식과 압축 안전성을 확인한다.
4. 모든 파서를 공통 `DocumentUnit` 구조로 변환한다.
5. Unicode 정규화와 완전 중복 제거 후 전체 블록을 검사한다.
6. 입력이 작으면 직접 요약하고, 크면 의미 블록 단위 map/reduce를 수행한다.
7. 최종 LLM 호출 한 번으로 원본 추출 요약 1개와 추천 요약 4개를 생성한다.
8. UI는 파일별 성공·실패·경고와 실제 반영 블록 수를 표시한다.

여러 파일 중 일부 파싱에 실패해도 성공한 파일이 하나 이상이면 계속 분석한다.

## 자원 안전 한도

UI에는 파일 개수 제한이 없다. 비정상 요청과 서버 고갈 방지를 위해 다음 서버 한도를 둔다.

- 전체 업로드 200MB
- 파일당 100MB
- multipart 파일 500개(숨은 악성 요청 방어선)
- PDF 파일당 500쪽
- 프레젠테이션 파일당 500장
- 스프레드시트 파일당 비어 있지 않은 셀 200,000개
- 압축 문서 내부 항목 20,000개, 해제 크기 1GB, 압축률 200:1
- 전체 추출 후보 텍스트 4,000,000자, LLM 선택 텍스트 1,200,000자

한도에 의해 LLM 입력이 선택된 경우 원문을 조용히 잘라내지 않고 UI 분석 경고와
coverage 정보에 표시한다.
