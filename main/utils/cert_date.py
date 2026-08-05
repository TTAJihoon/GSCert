"""인증일자(SwData.cert_date / ReferenceProject.cert_date) 텍스트 공용 처리.

원본 데이터는 "2026.6.8"처럼 0-패딩 없는 자유 형식 텍스트라(구분자도 '.', '-', '/'가
혼재) 화면마다 표기가 들쭉날쭉하고 문자열 정렬/비교도 어긋난다. 저장값 자체는
바꾸지 않고, 화면 표시와 기간 필터링에서만 이 모듈을 거쳐 통일한다.
"""
import re
from datetime import date

_CERT_DATE_RE = re.compile(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")


def parse_cert_date(value):
    """텍스트에서 (year, month, day)를 뽑아 date로 반환한다. 파싱 불가하면 None."""
    text = str(value or "").strip()
    match = _CERT_DATE_RE.search(text)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def format_cert_date(value):
    """화면 표시용으로 'yyyy.mm.dd' 형태로 통일한다. 파싱 불가하면 원본 그대로."""
    text = str(value or "").strip()
    if not text or text in ("-", "None"):
        return "-"
    parsed = parse_cert_date(text)
    if not parsed:
        return text
    return parsed.strftime("%Y.%m.%d")
