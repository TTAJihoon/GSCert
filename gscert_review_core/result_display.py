"""Shared presentation helpers for inspection results.

This module is deliberately UI-framework independent.  The web UI and the
Windows app both use these helpers so numbering, sub-check expansion, and
user-facing expected/actual/message text stay in one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .types import ERROR, FAIL, PASS, UNSUPPORTED


@dataclass(frozen=True)
class DisplayResultRow:
    parent_index: int
    sub_index: int
    display_number: str
    rule_code: str
    rule_name: str
    status: str
    expected: str
    actual: str
    message: str
    file_path: str = ""
    file_name: str = ""
    raw_detail: dict[str, Any] | None = None


def build_display_rows(results: Iterable[Any]) -> list[DisplayResultRow]:
    """Flatten rule results into user-facing rows.

    A rule with detailed ``raw_detail.sub_checks`` becomes rows such as
    ``6-1``, ``6-2``.  A rule without sub-checks becomes ``N-1``.
    """

    rows: list[DisplayResultRow] = []
    for parent_index, result in enumerate(results, start=1):
        sub_checks = _raw_sub_checks(result)
        if sub_checks:
            for sub_index, sub in enumerate(sub_checks, start=1):
                passed = sub.get("passed")
                status = PASS if passed is True else FAIL if passed is False else _get_text(result, "status")
                expected_raw = str(sub.get("expected") or "-")
                actual_raw = str(sub.get("actual") or "-")
                message_raw = str(sub.get("message") or "")
                sub_label, expected_body = split_sub_label(expected_raw)
                base_name = _get_text(result, "rule_name", "name")
                title = base_name if not sub_label else f"{base_name} - {sub_label}"
                expected = friendly_expected(expected_body or expected_raw)
                actual = friendly_actual(actual_raw)
                message = friendly_message(status, message_raw, expected, actual)
                rows.append(
                    DisplayResultRow(
                        parent_index=parent_index,
                        sub_index=sub_index,
                        display_number=f"{parent_index}-{sub_index}",
                        rule_code=_get_text(result, "rule_code", "code"),
                        rule_name=title,
                        status=status,
                        expected=expected,
                        actual=actual,
                        message=message,
                        file_path=_get_text(result, "file_path"),
                        file_name=_get_text(result, "file_name"),
                        raw_detail={
                            "selected_sub_check": sub,
                            "parent_rule": base_name,
                            "parent_raw_detail": _raw_detail(result),
                        },
                    )
                )
            continue

        status = _get_text(result, "status")
        expected = friendly_expected(_get_text(result, "expected"))
        actual = friendly_actual(_get_text(result, "actual"))
        message = friendly_message(status, _get_text(result, "message"), expected, actual)
        rows.append(
            DisplayResultRow(
                parent_index=parent_index,
                sub_index=1,
                display_number=f"{parent_index}-1",
                rule_code=_get_text(result, "rule_code", "code"),
                rule_name=_get_text(result, "rule_name", "name"),
                status=status,
                expected=expected,
                actual=actual,
                message=message,
                file_path=_get_text(result, "file_path"),
                file_name=_get_text(result, "file_name"),
                raw_detail=_raw_detail(result),
            )
        )
    return rows


def serialize_display_row(
    row: DisplayResultRow,
    *,
    status_labeler: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    status_label = status_labeler(row.status) if status_labeler else row.status
    return {
        "parent_index": row.parent_index,
        "sub_index": row.sub_index,
        "display_number": row.display_number,
        "rule_code": row.rule_code,
        "rule_name": row.rule_name,
        "status": row.status,
        "status_label": status_label,
        "expected": row.expected,
        "actual": row.actual,
        "message": row.message,
        "file_path": row.file_path,
        "file_name": row.file_name,
    }


def split_sub_label(text: str) -> tuple[str, str]:
    match = re.match(r"^\s*\[([^\]]+)\]\s*(.*)$", text or "")
    if not match:
        return "", text or ""
    return match.group(1).strip(), match.group(2).strip()


def friendly_expected(value: str) -> str:
    text = clean_display_text(value)
    text = re.sub(
        r"다음 문단이\s+\^.*?\s+형식",
        "다음 문단이 날짜 형식(예: 2026.04.17)",
        text,
    )
    text = re.sub(
        r"파일명에\s+(.+?)\s+포함\s*\n-\s*1개\s*\n-\s*확장자\s+([.\w, ]+)",
        r"파일명에 \1 이(가) 포함된 \2 파일 1개",
        text,
        flags=re.S,
    )
    text = text.replace("{시작일} ~ {종료일} 기준정보", "기준정보의 시험 시작일~종료일 범위")
    text = text.replace("rawdata 폴더 구조 충족", "RawData 폴더 구조가 기준에 맞게 구성")
    text = text.replace("단일 시트", "시트 1개")
    text = text.replace("파싱 가능", "파일을 열어 내용을 읽을 수 있어야 함")
    return text or "-"


def friendly_actual(value: str) -> str:
    text = clean_display_text(value)
    replacements = {
        "일치 파일 없음": "조건에 맞는 파일을 찾지 못했습니다.",
        "정상": "기준을 충족했습니다.",
        "{결함차수} 없음": "시험성적서에서 결함 차수를 확인하지 못했습니다.",
        "날짜 없음": "문서에서 필요한 날짜를 찾지 못했습니다.",
    }
    return replacements.get(text, text or "-")


def friendly_message(status: str, message: str, expected: str, actual: str) -> str:
    issue = friendly_issue(message, expected, actual)
    if status == PASS:
        return "기대값과 실제값이 일치합니다."
    if status == UNSUPPORTED:
        return f"자동 점검 대상이 아닙니다. 수동으로 확인해 주세요.\n확인 기준: {expected}"
    if status == ERROR:
        return f"점검 중 오류가 발생했습니다. 오류 내용: {actual or issue}"
    return f"차이: {issue}"


def friendly_issue(message: str, expected: str, actual: str) -> str:
    text = clean_display_text(message)
    text = re.sub(r"\(현재 값:\s*(.*?)\)", r"(실제값: \1)", text)
    text = text.replace("잘못 작성됨", "기준과 다르게 작성되어 있습니다")
    text = text.replace("틀림", "기준과 다릅니다")
    text = text.replace("찾을 수 없습니다", "찾지 못했습니다")
    text = text.replace("1개 이상임", "1개보다 많습니다")

    expected_flat = expected.replace("\n", " ")
    actual_flat = actual.replace("\n", " ")
    if "금지어" in expected_flat and ("금지어 포함" in actual_flat or "작성되면 안됨" in text):
        return f"문서에 포함되면 안 되는 문구가 발견되었습니다.\n실제값: {actual_flat}"
    if "필수어" in expected_flat and ("누락" in text or actual_flat in {"-", "/"}):
        return f"문서에 반드시 들어가야 하는 문구가 누락되었습니다.\n기대값: {expected_flat}\n실제값: {actual_flat}"
    if "작성자" in expected_flat or "검토자" in expected_flat or "PL" in text:
        return f"작성자/검토자 정보가 기준정보와 다릅니다.\n기대값: {expected_flat}\n실제값: {actual_flat}"
    if "파일" in expected_flat and ("찾지 못했습니다" in text or "조건에 맞는 파일" in actual_flat):
        return f"필요한 파일이 없거나 파일명이 기준과 맞지 않습니다.\n기대값: {expected_flat}\n실제값: {actual_flat}"
    if "시트" in expected_flat and "시트" in actual_flat:
        return f"Excel 시트 구성이 기준과 다릅니다.\n기대값: {expected_flat}\n실제값: {actual_flat}"
    if any(token in expected_flat for token in ["날짜", "기간", "보고일자", "작성일"]) or any(
        token in text for token in ["날짜", "기간", "보고일자", "작성일"]
    ):
        return f"문서의 날짜/기간 값이 기준정보와 다릅니다.\n기대값: {expected_flat}\n실제값: {actual_flat}"
    if any(token in expected_flat for token in ["점수표", "품질부특성", "측정값"]) or any(
        token in text for token in ["품질부특성", "값이 다름", "상이함"]
    ):
        return f"품질 관련 값 비교 결과가 기준과 다릅니다.\n기대값: {expected_flat}\n실제값: {actual_flat}"
    return text or f"기대값은 {expected_flat}\n실제값은 {actual_flat}입니다."


def clean_display_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    text = text.replace(" / ", "\n- ")
    if "\n- " in text and not text.startswith("- "):
        text = "- " + text
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _get_text(source: Any, *names: str) -> str:
    for name in names:
        if isinstance(source, dict):
            value = source.get(name)
        else:
            value = getattr(source, name, None)
        if value is not None:
            return str(value)
    return ""


def _raw_detail(source: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        value = source.get("raw_detail") or source.get("raw_detail_json")
    else:
        value = getattr(source, "raw_detail", None)
        if value is None:
            value = getattr(source, "raw_detail_json", None)
    return value if isinstance(value, dict) else {}


def _raw_sub_checks(source: Any) -> list[dict[str, Any]]:
    sub_checks = _raw_detail(source).get("sub_checks")
    return [item for item in sub_checks if isinstance(item, dict)] if isinstance(sub_checks, list) else []
