# myproject/playwright_job/parsers.py
from __future__ import annotations

import re
from typing import Optional

URL_RE = re.compile(r"(https?://\S+)", re.IGNORECASE)
DOC_EXT_RE = re.compile(r"\.(docx?|hwp|pdf)\b", re.IGNORECASE)


def pick_best_file_url(clipboard_text: str) -> Optional[str]:
    """
    클립보드 텍스트(여러 줄)에서 "파일 URL"만 골라냄.
    규칙(임의 폴백 없음):
      1) '시험성적서'가 포함된 줄에 URL이 있으면 그 URL
      2) (1)이 없으면 .doc/.docx/.hwp/.pdf 확장자 표기가 포함된 줄에 URL이 있으면 그 URL
      3) 위 둘 다 못 찾으면 None
    """
    if not clipboard_text:
        return None

    lines = clipboard_text.splitlines()

    # 1) 시험성적서 줄 우선
    for line in lines:
        if "시험성적서" in line:
            m = URL_RE.search(line)
            if m:
                return m.group(1)

    # 2) 파일 확장자 힌트 줄
    for line in lines:
        if DOC_EXT_RE.search(line):
            m = URL_RE.search(line)
            if m:
                return m.group(1)

    return None
