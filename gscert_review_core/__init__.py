"""GSCert 점검 공유 엔진.

웹(Django)과 로컬 검토 프로그램(PySide6)이 동일한 점검 로직을 사용하기 위한
Django 비종속 패키지. 어떤 모듈도 django, settings, ORM에 의존하지 않는다.
"""

from .types import (
    ERROR,
    FAIL,
    PASS,
    UNSUPPORTED,
    EngineFile,
    RuleContext,
    RuleEvaluation,
    RuleSpec,
)
from .result_display import (
    DisplayResultRow,
    build_display_rows,
    serialize_display_row,
)

# 공유 점검 엔진 버전. 규칙셋이 요구하는 최소 엔진 버전(rulebase manifest 의
# engine_min_version)과 비교해, 낡은 앱/서버에 신규 규칙이 적용되는 것을 막는다.
# 엔진에 새 규칙유형/검사옵션을 추가하면 이 값을 올린다.
ENGINE_VERSION = "0.2.0"

__all__ = [
    "PASS",
    "FAIL",
    "UNSUPPORTED",
    "ERROR",
    "EngineFile",
    "RuleContext",
    "RuleEvaluation",
    "RuleSpec",
    "DisplayResultRow",
    "build_display_rows",
    "serialize_display_row",
    "ENGINE_VERSION",
]
