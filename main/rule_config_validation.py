"""점검규칙 config_json 검증 (저장/시드 시점).

규칙(`DownloadReviewRule`)의 `rule_type` + `config_json` 이 엔진이 실행할 수 있는
형태인지 *저장 전에* 검사한다. 목적은 "쉼표 하나 빠진 잘못된 config 가 점검 전체를
멈추는" 사고를 막는 것이다. (예: 알 수 없는 content_check type → 엔진이 점검 도중
DownloadReviewInspectionError 를 던져 해당 규칙이 오류로 중단됨.)

설계 원칙:
- Django/엔진 무거운 import 없이 순수 파이썬으로 동작(모델 clean()/시드에서 가볍게 호출).
- 지원 rule_type 목록은 엔진의 SUPPORTED_RULE_TYPES(단일 진실 소스)를 lazy import.
  (검증기가 자체 목록을 두면 엔진에 type 추가 시 멀쩡한 규칙을 '미지원'으로 오판함.)
- 미래의 config 키 추가를 막지 않도록, 모르는 키는 통과시키고 *알고 있는 키의
  형식*과 *핸들러가 반드시 참조하는 필수 키*만 검사한다(과도한 제약 회피).

반환: ``(errors, warnings)`` — errors 가 있으면 저장을 막아야 한다. warnings 는
권고 사항(저장은 허용).
"""

from __future__ import annotations

import re
from typing import Any


# 엔진 _run_content_check 의 분기와 일치해야 한다.
# all: 모두 필요한 키 / any: 각 그룹에서 최소 하나 / regex: 정규식으로 컴파일 검사할 키.
_CONTENT_CHECKS: dict[str, dict[str, Any]] = {
    "docx_table_next_cell_equals": {"all": ["label", "expected"], "any": [], "regex": []},
    "pdf_first_page_label_value_contains": {"all": ["label", "expected"], "any": [], "regex": []},
    "docx_text_contains": {"all": [], "any": [["text", "texts"]], "regex": []},
    "docx_header_contains": {"all": ["text"], "any": [], "regex": []},
    "docx_footer_contains": {"all": ["text"], "any": [], "regex": []},
    "docx_header_not_contains": {"all": [], "any": [["text", "texts"]], "regex": []},
    "docx_footer_not_contains": {"all": [], "any": [["text", "texts"]], "regex": []},
    "docx_next_paragraph_matches": {"all": ["regex"], "any": [["after_text", "after_texts"]], "regex": ["regex"]},
}

# rule_type 별 *핸들러가 반드시 참조하는* 최소 필수 키(없으면 점검이 깨짐).
# 값이 빈 리스트여도 "키 존재"로 통과한다(예: 홍보이미지 filename_keywords=[]).
_RULE_REQUIRED_KEYS: dict[str, list[str]] = {
    "required_artifact_file": ["filename_keywords"],
    "downloadable_artifact_check": ["filename_keywords"],
    "document_artifact_check": ["required_files"],
    "excel_feature_list_check": ["filename_keywords"],
    "test_plan_document_check": ["required_files"],
    "test_case_check": ["filename_keywords"],
    "rawdata_folder_structure_check": ["folder_checks"],
    "test_report_document_check": ["required_files"],
    "defect_report_check": ["filename_keywords", "version_pattern"],
    "inspection_checklist_check": ["filename_keywords"],
    "quality_inspection_table_check": ["filename_keywords"],
    "quality_evaluation_report_check": ["filename_keywords"],
    "required_file_name_contains": ["contains"],  # draft
}

# 형식 검사 대상 키.
_LIST_OF_STR_KEYS = {
    "folder_keyword_chain",
    "filename_keywords",
    "extensions",
    "forbidden_filename_keywords",
    "texts",
    "after_texts",
    "requires",
    "produces",
}
_INT_KEYS = {
    "exact_count",
    "min_count",
    "min_images_per_folder",
    "required_candidate_folder_count",
    "project_number_count",
    "quality_value_count",
    "line_window",
    "page_index",
    "exact_child_folders",
    "min_entries",
}
_LIST_OF_INT_KEYS = {"quality_value_excluded_indices"}
_TERM_LIST_KEYS = {"forbidden_footer_terms", "forbidden_header_terms", "required_footer_terms"}
_REGEX_KEYS = {"version_pattern"}


def _supported_rule_types() -> frozenset[str]:
    """엔진의 단일 진실 소스를 lazy import. import 실패 시 None(검사 생략)."""
    try:
        from gscert_review_core.engine import SUPPORTED_RULE_TYPES

        return SUPPORTED_RULE_TYPES
    except Exception:  # pragma: no cover - 엔진 import 불가 환경(검증만 건너뜀)
        return frozenset()


def _is_int(value: Any) -> bool:
    # bool 은 int 의 하위 클래스이므로 명시적으로 배제한다.
    return isinstance(value, int) and not isinstance(value, bool)


def _check_list_of_str(value: Any, key: str, where: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} '{key}' 는 리스트여야 합니다(현재: {type(value).__name__}).")
        return
    for i, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{where} '{key}'[{i}] 는 문자열이어야 합니다(현재: {type(item).__name__}).")


def _check_extensions(value: Any, where: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} 'extensions' 는 리스트여야 합니다.")
        return
    for i, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{where} 'extensions'[{i}] 는 문자열이어야 합니다.")
        elif item and not item.startswith("."):
            errors.append(f"{where} 'extensions'[{i}]='{item}' 는 점(.)으로 시작해야 합니다(예: '.pdf').")


def _check_regex(value: Any, key: str, where: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{where} '{key}' 정규식은 문자열이어야 합니다.")
        return
    try:
        re.compile(value)
    except re.error as exc:
        errors.append(f"{where} '{key}' 정규식 컴파일 실패: {exc}")


def _check_term_list(value: Any, key: str, where: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} '{key}' 는 리스트여야 합니다.")
        return
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{where} '{key}'[{i}] 는 객체여야 합니다(예: {{'text': ..., 'message': ...}}).")
            continue
        if not isinstance(item.get("text"), str) or not item.get("text"):
            errors.append(f"{where} '{key}'[{i}] 에 비어 있지 않은 'text' 가 필요합니다.")


def _check_required_files(value: Any, where: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} 'required_files' 는 리스트여야 합니다.")
        return
    if not value:
        errors.append(f"{where} 'required_files' 가 비어 있습니다(최소 1개 파일 사양 필요).")
    for i, item in enumerate(value):
        spec_where = f"{where} 'required_files'[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{spec_where} 는 객체여야 합니다.")
            continue
        if "extensions" in item:
            _check_extensions(item["extensions"], spec_where, errors)
        else:
            errors.append(f"{spec_where} 에 'extensions' 가 필요합니다.")
        for ck in ("exact_count", "min_count"):
            if ck in item and not _is_int(item[ck]):
                errors.append(f"{spec_where} '{ck}' 는 정수여야 합니다.")


def _check_folder_checks(value: Any, where: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} 'folder_checks' 는 리스트여야 합니다.")
        return
    if not value:
        errors.append(f"{where} 'folder_checks' 가 비어 있습니다.")
    for i, item in enumerate(value):
        fc_where = f"{where} 'folder_checks'[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{fc_where} 는 객체여야 합니다.")
            continue
        if not isinstance(item.get("keyword"), str) or not item.get("keyword"):
            errors.append(f"{fc_where} 에 비어 있지 않은 'keyword' 가 필요합니다.")
        for ik in ("exact_child_folders", "min_entries"):
            if ik in item and not _is_int(item[ik]):
                errors.append(f"{fc_where} '{ik}' 는 정수여야 합니다.")


def _check_content_checks(value: Any, where: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} 'content_checks' 는 리스트여야 합니다.")
        return
    for i, item in enumerate(value):
        cc_where = f"{where} 'content_checks'[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{cc_where} 는 객체여야 합니다.")
            continue
        check_type = str(item.get("type") or "").strip()
        spec = _CONTENT_CHECKS.get(check_type)
        if spec is None:
            errors.append(
                f"{cc_where} 알 수 없는 content_check type '{check_type or '(비어 있음)'}'. "
                f"지원: {', '.join(sorted(_CONTENT_CHECKS))}"
            )
            continue
        for req in spec["all"]:
            if req not in item:
                errors.append(f"{cc_where}(type={check_type}) 에 '{req}' 가 필요합니다.")
        for group in spec["any"]:
            if not any(k in item for k in group):
                errors.append(f"{cc_where}(type={check_type}) 에 {' 또는 '.join(group)} 중 하나가 필요합니다.")
        for rk in spec["regex"]:
            if rk in item:
                _check_regex(item[rk], rk, cc_where, errors)
        # 공통 형식 검사(텍스트 리스트/확장자).
        _validate_known_value_shapes(item, cc_where, errors)


def _validate_known_value_shapes(config: dict[str, Any], where: str, errors: list[str]) -> None:
    """dict 안의 *알고 있는 키*들에 대해서만 형식을 검사한다(모르는 키는 통과)."""
    for key, value in config.items():
        if key in _LIST_OF_STR_KEYS:
            if key == "extensions":
                _check_extensions(value, where, errors)
            else:
                _check_list_of_str(value, key, where, errors)
        elif key in _INT_KEYS:
            if not _is_int(value):
                errors.append(f"{where} '{key}' 는 정수여야 합니다(현재: {type(value).__name__}).")
        elif key in _LIST_OF_INT_KEYS:
            if not isinstance(value, list) or any(not _is_int(v) for v in value):
                errors.append(f"{where} '{key}' 는 정수 리스트여야 합니다.")
        elif key in _TERM_LIST_KEYS:
            _check_term_list(value, key, where, errors)
        elif key in _REGEX_KEYS:
            _check_regex(value, key, where, errors)


def validate_rule_config(
    rule_type: str,
    config: Any,
    *,
    code: str = "",
) -> tuple[list[str], list[str]]:
    """단일 규칙의 rule_type + config_json 을 검증한다.

    Returns:
        (errors, warnings). errors 가 비어 있지 않으면 저장을 막아야 한다.
    """
    errors: list[str] = []
    warnings: list[str] = []
    label = code or rule_type or "(규칙)"
    where = f"[{label}]"

    rule_type = (rule_type or "").strip()
    supported = _supported_rule_types()
    if not rule_type:
        errors.append(f"{where} rule_type 이 비어 있습니다.")
    elif supported and rule_type not in supported:
        errors.append(
            f"{where} 엔진이 지원하지 않는 rule_type '{rule_type}'. "
            f"지원 목록은 gscert_review_core.engine.SUPPORTED_RULE_TYPES 참고."
        )

    if not isinstance(config, dict):
        errors.append(f"{where} config_json 은 객체(JSON object)여야 합니다(현재: {type(config).__name__}).")
        return errors, warnings

    # 필수 키.
    for req in _RULE_REQUIRED_KEYS.get(rule_type, []):
        if req not in config:
            errors.append(f"{where}(type={rule_type}) 에 '{req}' 키가 필요합니다.")

    # 알고 있는 키 형식 검사.
    _validate_known_value_shapes(config, where, errors)

    # 구조 키 검사.
    if "required_files" in config:
        _check_required_files(config["required_files"], where, errors)
    if "content_checks" in config:
        _check_content_checks(config["content_checks"], where, errors)
    if "folder_checks" in config:
        _check_folder_checks(config["folder_checks"], where, errors)

    # 권고 사항(저장은 허용).
    if rule_type in _RULE_REQUIRED_KEYS and rule_type != "required_file_name_contains":
        if not config.get("artifact_column"):
            warnings.append(
                f"{where} 'artifact_column' 이 없습니다. 점검 결과가 기준 DB 컬럼에 매핑되지 않을 수 있습니다."
            )

    return errors, warnings


def validate_rule_spec(spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """시드 spec(dict) 검증 헬퍼. config 는 'config_json' 또는 'config' 키에서 읽는다."""
    config = spec.get("config_json")
    if config is None:
        config = spec.get("config", {})
    return validate_rule_config(
        spec.get("rule_type", ""),
        config,
        code=spec.get("code", "") or spec.get("name", ""),
    )


# ── 규칙셋 의존 그래프 검증 (requires / produces) ──────────────────────────────
#
# 규칙은 선행 규칙이 raw_detail.variables 로 남긴 산출 변수를 후속 규칙이 소비한다
# (예: 시험성적서 → 결함차수 → 결함리포트 → 잔여결함수 → 테스트케이스).
# 실행 순서는 sort_order 로 정해지므로, 운영자가 Admin 에서 순서를 바꾸거나 규칙을
# 비활성화하면 후속 규칙이 빈 변수를 받아 "제출물 문제가 아닌데 부적합"이 날 수 있다.
# 각 규칙이 config 에 requires/produces 를 선언하면 이 검증으로 사전에 잡는다.


def _graph_entry(code: str, name: str, sort_order: Any, config: Any) -> dict[str, Any]:
    cfg = config if isinstance(config, dict) else {}
    return {
        "code": code or name or "(규칙)",
        "sort_order": sort_order if _is_int(sort_order) else 0,
        "requires": [v for v in (cfg.get("requires") or []) if isinstance(v, str)],
        "produces": [v for v in (cfg.get("produces") or []) if isinstance(v, str)],
    }


def validate_rule_graph(entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """활성 규칙 entries 의 requires/produces 의존 그래프를 검증한다.

    각 entry: {code, sort_order, requires:[str], produces:[str]} (`_graph_entry` 로 생성).
    호출자가 *실행될 규칙만*(enabled=True) 넘겨야 한다.

    검사:
    - 각 requires 변수마다, 그 변수를 produces 하는 규칙이 *더 작은 sort_order* 로
      존재하는가? 없으면 error(후속 규칙이 빈 변수를 받음).
    - 같은 변수를 2개 이상이 produces → warning(모호).

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    producers: dict[str, list[tuple[int, str]]] = {}
    for entry in entries:
        for var in entry["produces"]:
            producers.setdefault(var, []).append((entry["sort_order"], entry["code"]))

    for var, plist in sorted(producers.items()):
        if len(plist) > 1:
            codes = ", ".join(code for _, code in sorted(plist))
            warnings.append(f"산출 변수 '{var}'를 여러 규칙이 생성합니다(모호): {codes}")

    for entry in entries:
        for var in entry["requires"]:
            plist = producers.get(var)
            if not plist:
                errors.append(
                    f"[{entry['code']}] 가 요구하는 변수 '{var}'를 생성하는 활성 규칙이 없습니다 "
                    f"(생성 규칙이 비활성화되었거나 오타일 수 있음)."
                )
                continue
            if not any(p_order < entry["sort_order"] for p_order, _ in plist):
                earliest = min(p_order for p_order, _ in plist)
                errors.append(
                    f"[{entry['code']}] (sort_order={entry['sort_order']}) 가 '{var}'를 요구하지만, "
                    f"이를 생성하는 규칙이 더 늦게/같이 실행됩니다(가장 이른 producer sort_order={earliest}). "
                    f"sort_order 를 조정하세요."
                )

    return errors, warnings


def validate_rule_graph_from_specs(specs: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """시드 spec 리스트로 그래프 검증(모든 spec 을 실행 대상으로 간주)."""
    entries = [
        _graph_entry(
            spec.get("code", ""),
            spec.get("name", ""),
            spec.get("sort_order"),
            spec.get("config_json") if spec.get("config_json") is not None else spec.get("config"),
        )
        for spec in specs
    ]
    return validate_rule_graph(entries)
