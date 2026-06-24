"""점검 엔진 공용 데이터 타입 (Django 비종속)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# ── 점검 상태 ────────────────────────────────────────────────────────────────
PASS = "pass"
FAIL = "fail"
UNSUPPORTED = "unsupported"
ERROR = "error"


@dataclass(frozen=True)
class EngineFile:
    """점검 대상 파일 1개에 대한 어댑터 비종속 표현.

    - name: 파일명 (확장자 포함)
    - extension: 소문자 확장자(점 포함, 예: ".docx")
    - path: 표시/상대 경로 (zip 내부 경로 또는 폴더 상대경로)
    - size: 바이트 크기
    - reader: 호출 시 파일 내용을 bytes로 반환하는 콜백.
      웹 어댑터는 zip 내부/.doc 변환을 처리하고, 로컬 어댑터는 디스크에서 읽는다.
    """

    name: str
    extension: str
    path: str
    size: int
    reader: Callable[[], bytes] | None = None

    def read_bytes(self) -> bytes:
        if self.reader is None:
            raise RuntimeError(f"파일 reader가 설정되지 않았습니다: {self.path}")
        return self.reader()

    @property
    def segments(self) -> list[str]:
        """경로를 폴더/파일 세그먼트 리스트로 분해한다(folder_keyword_chain용)."""
        normalized = str(self.path or "").replace("\\", "/")
        return [segment for segment in normalized.split("/") if segment]


@dataclass(frozen=True)
class RuleSpec:
    """점검 규칙 1개의 어댑터 비종속 표현.

    웹은 DownloadReviewRule 모델에서, 로컬은 rule bundle dict에서 만든다.
    """

    rule_type: str
    code: str
    name: str
    config: dict[str, Any] = field(default_factory=dict)
    target_file_type: str = ""
    target_file_pattern: str = ""

    @property
    def config_json(self) -> dict[str, Any]:
        # 서버 코드가 rule.config_json 으로 접근하던 것과의 호환.
        return self.config


@dataclass
class RuleContext:
    """프로젝트 메타데이터 기반 점검 컨텍스트.

    derived_variables 는 규칙 실행 중 후속 규칙용으로 채워지므로 가변 dict.
    """

    project_number: str = ""
    product_raw: str = ""
    product: str = ""
    version: str = ""
    company: str = ""
    pl: str = ""
    wd: str = ""
    start_date: str = ""
    end_date: str = ""
    year: str = ""
    request_date: str = ""
    contract_date: str = ""
    certification_committee_date: str = ""
    derived_variables: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleEvaluation:
    """규칙 1개 실행 결과 (어댑터 비종속)."""

    rule_code: str
    rule_name: str
    status: str
    expected: str
    actual: str
    message: str
    file_path: str = ""
    file_name: str = ""
    raw_detail: dict[str, Any] | None = None
