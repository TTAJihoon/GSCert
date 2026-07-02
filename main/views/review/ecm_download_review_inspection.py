"""ECM 다운로드 점검 — 웹(Django) 어댑터.

평가 로직 전체는 Django 비종속 공유 엔진 ``gscert_review_core.engine`` 으로 이전했다.
이 모듈은 Django 결합부만 담당하는 thin adapter 이다:

- 오케스트레이션(run_download_inspection): 규칙 조회 → 엔진 호출 → 결과 DB 저장
- 컨텍스트 생성(_build_rule_context) + reference 날짜(_reference_start_end_dates, PostgreSQL)
- 산출물 저장(WebArtifactSink): PDF 1페이지/원본/Excel 영역 캡처를 미디어 디렉터리에 저장
- 다운로드 폴더 정리(cleanup_download_dir), 후속 규칙용 변수 수집(get_rule_output_variables)

평가기·파서·파일모델·헬퍼는 모두 엔진에 있으며, 외부(tests/worker)가 이 모듈에서
import 하던 심볼은 아래에서 재노출한다.
"""

import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("main.views.review.ecm_download_review_inspection")

from main.models import (
    DownloadReviewProjectReviewStatus,
    DownloadReviewRule,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
    SwData,
)
from main.views.review.ecm_reference_db import ARTIFACT_REVIEW_COLUMNS

from gscert_review_core import engine

# 외부(main/tests.py, ecm_download_review_worker.py)가 이 모듈에서 import 하던 심볼 재노출.
# 예외 클래스는 반드시 엔진과 동일한 클래스를 써야 평가기 내부 except 가 맞물린다.
from gscert_review_core.engine import (  # noqa: F401
    DownloadReviewCleanupSafetyError,
    DownloadReviewInspectionError,
    ExcelSheet,
    ExcelWorkbook,
    FileInfo,
    RuleContext,
    RuleEvaluation,
    _check_defect_report_environment,
    _is_ignorable_file,
    _list_mismatches,
    _raw_detail_variables,
)

IMAGE_EXTENSIONS = engine.IMAGE_EXTENSIONS
WORD_EXTENSIONS = engine.WORD_EXTENSIONS


@dataclass(frozen=True)
class InspectionOutcome:
    project_review_status: str
    reference_review: str
    artifact_results: dict
    passed_count: int
    failed_count: int
    result_count: int


@dataclass(frozen=True)
class CleanupOutcome:
    deleted: bool
    message: str
    file_count: int = 0


# ══════════════════════════════════════════════════════════════════════════════
# 오케스트레이션
# ══════════════════════════════════════════════════════════════════════════════

def run_download_inspection(project, verify_result, file_summary) -> InspectionOutcome:
    """등록된 활성 규칙을 공유 엔진으로 실행하고 규칙별 결과를 저장한다."""
    # 점검규칙은 주 서버 PostgreSQL(reference)에 단일 저장되어 194/241이 공유한다.
    # (서브 서버는 reference DB 연결이 주 서버 PG를 가리키므로 동일 규칙을 읽는다.)
    rules = list(DownloadReviewRule.objects.filter(enabled=True).order_by("sort_order", "name", "id"))
    if not rules:
        raise DownloadReviewInspectionError(
            "활성화된 점검규칙이 없습니다. 주 서버 PostgreSQL에 규칙이 등록/활성화되어 있는지 확인하세요."
        )

    _ensure_soffice_env()  # .doc 변환 경로(settings) 보존
    context = _build_rule_context(project)

    evaluations = engine.evaluate_rules(
        rules,
        context,
        verify_result,  # verify_result 객체를 그대로 전달(zip 확장 캐시·오류가 원본에 누적)
        project=project,
        sink=WebArtifactSink(),
    )

    result_rows = [
        DownloadReviewRuleResult(
            job_project=project,
            rule_code=evaluation.rule.code,
            rule_name=evaluation.rule.name,
            sequence=evaluation.sequence,
            file_path=evaluation.file_path,
            file_name=evaluation.file_name,
            status=evaluation.status,
            expected=evaluation.expected,
            actual=evaluation.actual,
            message=evaluation.message,
            raw_detail_json=evaluation.raw_detail or {},
        )
        for evaluation in evaluations
    ]

    # 임시파일(~$) 검사 — DB 규칙과 무관한 전역 검사.
    temp_files = _find_temp_files(verify_result)
    temp_failed = bool(temp_files)
    result_rows.append(
        DownloadReviewRuleResult(
            job_project=project,
            rule_code="temp_file_check",
            rule_name="임시파일 검사",
            sequence=len(evaluations) + 1,
            file_path="",
            file_name="",
            status=DownloadReviewRuleStatus.FAIL if temp_failed else DownloadReviewRuleStatus.PASS,
            expected="임시/잠금 파일(~$) 없음",
            actual=("삭제 필요:\n" + "\n".join(temp_files[:20])) if temp_failed else "임시파일 없음",
            message=(
                "MS Office 임시파일(~$)이 포함되어 있습니다. 해당 파일을 삭제 후 다시 제출하세요."
                if temp_failed
                else "임시파일이 없습니다."
            ),
            raw_detail_json={"temp_files": temp_files},
        )
    )

    DownloadReviewRuleResult.objects.filter(job_project=project).delete()
    DownloadReviewRuleResult.objects.bulk_create(result_rows)

    failed_count = sum(
        1
        for evaluation in evaluations
        if evaluation.status in (DownloadReviewRuleStatus.FAIL, DownloadReviewRuleStatus.ERROR)
    )
    if temp_failed:
        failed_count += 1
    total_count = len(evaluations) + 1
    passed_count = total_count - failed_count
    artifact_results = _artifact_results_from_evaluations(evaluations)

    if failed_count:
        return InspectionOutcome(
            project_review_status=DownloadReviewProjectReviewStatus.NEEDS_FIX,
            reference_review="X",
            artifact_results=artifact_results,
            passed_count=passed_count,
            failed_count=failed_count,
            result_count=total_count,
        )

    return InspectionOutcome(
        project_review_status=DownloadReviewProjectReviewStatus.COMPLETED,
        reference_review="O",
        artifact_results=artifact_results,
        passed_count=passed_count,
        failed_count=0,
        result_count=total_count,
    )


def cleanup_download_dir(project, download_dir=None) -> CleanupOutcome:
    """프로젝트 다운로드 폴더를 삭제한다(허용 경로·프로젝트번호 검증 후)."""
    raw_path = str(download_dir or project.download_dir or "").strip()
    if not raw_path:
        return CleanupOutcome(deleted=False, message="삭제할 다운로드 폴더가 없습니다.")

    target = Path(raw_path).resolve()
    base_dir = Path(getattr(settings, "AGENT_DOWNLOAD_BASE_DIR")).resolve()
    _validate_cleanup_target(project.project_number, base_dir, target)

    if not target.exists():
        project.zip_deleted_at = timezone.now()
        project.save(update_fields=["zip_deleted_at", "updated_at"])
        return CleanupOutcome(deleted=False, message="다운로드 폴더가 이미 없습니다.")

    file_count = sum(1 for item in target.rglob("*") if item.is_file())
    shutil.rmtree(target)

    project.zip_deleted_at = timezone.now()
    project.save(update_fields=["zip_deleted_at", "updated_at"])
    return CleanupOutcome(
        deleted=True,
        message="다운로드 폴더를 삭제했습니다.",
        file_count=file_count,
    )


def get_rule_output_variables(job_project):
    """이미 저장된 규칙 결과에서 후속 규칙용 산출 변수를 모은다."""
    variables = {}
    results = DownloadReviewRuleResult.objects.filter(job_project=job_project).order_by("sequence", "id")
    for result in results:
        variables.update(_raw_detail_variables(result.raw_detail_json or {}))
    return variables


# ══════════════════════════════════════════════════════════════════════════════
# 컨텍스트 / reference 조회 (PostgreSQL)
# ══════════════════════════════════════════════════════════════════════════════

def _build_rule_context(project):
    ecm_row = project.ecm_row_json or {}
    start_date, end_date = _reference_start_end_dates(project)
    return engine.build_context(
        project_number=project.project_number,
        product_name=ecm_row.get("product") or ecm_row.get("제품명") or "",
        company=ecm_row.get("company") or ecm_row.get("회사명") or "",
        pl=ecm_row.get("pl") or ecm_row.get("시험PL") or "",
        wd=ecm_row.get("wd") or ecm_row.get("WD") or "",
        start_date=start_date,
        end_date=end_date,
        request_date=ecm_row.get("request_date") or ecm_row.get("신청일") or "",
        contract_date=ecm_row.get("contract_date") or ecm_row.get("계약일") or "",
        certification_committee_date=ecm_row.get("cert_date") or ecm_row.get("인증일자") or "",
        center=getattr(project, "center_code", "") or "",
    )


def _reference_start_end_dates(project):
    """reference 에서 시험번호로 시작/종료일자를 조회한다.

    DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH 설정이 지정되면 해당 SQLite 파일에서
    조회하고(테스트/레거시 호환), 없으면 PostgreSQL reference(SwData)에서 조회한다(운영).
    weekly 동기화가 PostgreSQL 로 이전됐으므로 운영 기본은 PG 이며 stale reference.db
    를 읽지 않는다.
    """
    master_db = getattr(settings, "DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH", None)
    if master_db:
        return _reference_dates_from_sqlite(Path(master_db), project.project_number)
    return _reference_dates_from_pg(project.project_number)


def _reference_dates_from_pg(project_number):
    alias = getattr(settings, "REFERENCE_DATABASE_ALIAS", "reference")
    try:
        row = (
            SwData.objects.using(alias)
            .filter(test_number=project_number)
            .values("start_date", "end_date")
            .first()
        )
    except Exception:
        return "", ""
    if not row:
        return "", ""
    return engine._format_dot_date(row.get("start_date")), engine._format_dot_date(row.get("end_date"))


def _reference_dates_from_sqlite(db_path, project_number):
    table_name = getattr(settings, "DOWNLOAD_REVIEW_REFERENCE_MASTER_TABLE", "sw_data")
    if not db_path.exists():
        return "", ""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        columns = _sqlite_columns(conn, table_name)
        project_column = _first_existing_column(columns, ["프로젝트번호", "시험번호"])
        start_column = _first_existing_column(columns, ["시작일자", "시작일"])
        end_column = _first_existing_column(columns, ["종료일자", "종료일"])
        if not (project_column and start_column and end_column):
            return "", ""
        row = conn.execute(
            (
                f"SELECT {_quote_sqlite_identifier(start_column)}, {_quote_sqlite_identifier(end_column)} "
                f"FROM {_quote_sqlite_identifier(table_name)} "
                f"WHERE {_quote_sqlite_identifier(project_column)} = ? "
                "LIMIT 1"
            ),
            [project_number],
        ).fetchone()
    except sqlite3.Error:
        return "", ""
    finally:
        if conn is not None:
            conn.close()
    if not row:
        return "", ""
    return engine._format_dot_date(row[start_column]), engine._format_dot_date(row[end_column])


def _sqlite_columns(conn, table_name):
    try:
        rows = conn.execute(f"PRAGMA table_info({_quote_sqlite_identifier(table_name)})").fetchall()
    except sqlite3.Error:
        return set()
    return {row[1] for row in rows}


def _first_existing_column(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return ""


def _quote_sqlite_identifier(identifier):
    return '"' + str(identifier).replace('"', '""') + '"'


# ══════════════════════════════════════════════════════════════════════════════
# 결과 집계 / 임시파일 / 안전 검증
# ══════════════════════════════════════════════════════════════════════════════

def _artifact_results_from_evaluations(evaluations):
    results = {}
    for evaluation in evaluations:
        column = _artifact_column(evaluation.rule)
        if not column:
            continue
        value = "O" if evaluation.status == DownloadReviewRuleStatus.PASS else "X"
        previous = results.get(column)
        if previous == "X":
            continue
        results[column] = value
    return results


def _artifact_column(rule):
    config = (rule.config_json or {}) if rule is not None else {}
    configured = str(config.get("artifact_column") or "").strip()
    candidates = (configured, getattr(rule, "code", ""), getattr(rule, "name", ""))
    for candidate in candidates:
        if candidate in ARTIFACT_REVIEW_COLUMNS:
            return candidate
    return ""


def _find_temp_files(verify_result):
    """다운로드물에 포함된 ~$ 임시/잠금 파일 목록(점검 제외 전 원본 기준)."""
    found = []
    for file_info in list(verify_result.files or []):
        if _is_ignorable_file(file_info.name):
            found.append(file_info.name)
        if file_info.extension.lower() == ".zip":
            try:
                with ZipFile(file_info.path) as zip_file:
                    for entry in zip_file.infolist():
                        if entry.is_dir():
                            continue
                        inner_path = entry.filename.replace("\\", "/")
                        if _is_ignorable_file(PurePosixPath(inner_path).name):
                            found.append(inner_path)
            except (BadZipFile, OSError):
                pass
    return sorted(set(found))


def _validate_cleanup_target(project_number, base_dir, target):
    try:
        target.relative_to(base_dir)
    except ValueError as exc:
        raise DownloadReviewCleanupSafetyError(
            "다운로드 폴더가 허용된 기본 경로 밖에 있어 삭제하지 않았습니다."
        ) from exc

    if target == base_dir:
        raise DownloadReviewCleanupSafetyError("다운로드 기본 폴더 자체는 삭제할 수 없습니다.")
    if not target.is_dir() and target.exists():
        raise DownloadReviewCleanupSafetyError("삭제 대상이 폴더가 아닙니다.")
    if project_number not in target.name:
        raise DownloadReviewCleanupSafetyError(
            "삭제 대상 폴더명에 프로젝트번호가 없어 삭제하지 않았습니다."
        )


def _ensure_soffice_env():
    """엔진의 .doc→.docx 변환이 settings.AGENT_SOFFICE_PATH 를 쓰도록 환경변수로 전달."""
    configured = getattr(settings, "AGENT_SOFFICE_PATH", "")
    if configured and not os.environ.get("AGENT_SOFFICE_PATH"):
        os.environ["AGENT_SOFFICE_PATH"] = str(configured)


# ══════════════════════════════════════════════════════════════════════════════
# 산출물 저장 (웹 전용) — 엔진은 ArtifactSink 인터페이스로만 호출한다.
# ══════════════════════════════════════════════════════════════════════════════

class WebArtifactSink:
    """PDF 1페이지/원본/Excel 영역 캡처를 미디어 디렉터리에 저장하는 웹 sink."""

    def store_pdf_first_page(self, project, rule, file_info, *, artifact_id, label):
        data = engine._read_file_bytes(file_info)
        try:
            import fitz

            with fitz.open(stream=data, filetype="pdf") as document:
                if document.page_count < 1:
                    raise DownloadReviewInspectionError("PDF 첫 페이지가 없습니다.")
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                png_bytes = pixmap.tobytes("png")
        except DownloadReviewInspectionError:
            raise
        except Exception as exc:
            raise DownloadReviewInspectionError("PDF 1페이지 캡처를 생성할 수 없습니다.") from exc

        return _store_artifact_bytes(
            project, rule,
            artifact_id=artifact_id, label=label,
            file_suffix=".png", content_type="image/png",
            content_bytes=png_bytes, kind="image",
            source_file=engine._display_path(file_info.path, project.project_number),
            download=False,
        )

    def store_pdf_download(self, project, rule, file_info, *, artifact_id, label):
        data = engine._read_file_bytes(file_info)
        return _store_artifact_bytes(
            project, rule,
            artifact_id=artifact_id, label=label,
            file_suffix=".pdf", content_type="application/pdf",
            content_bytes=data, kind="file",
            source_file=engine._display_path(file_info.path, project.project_number),
            download=True,
        )

    def store_excel_area(self, project, rule, sheet, area, *, artifact_id, label, source_file):
        values = _excel_area_values(sheet.rows, area)
        if not values:
            raise DownloadReviewInspectionError("Excel 영역 이미지 대상 값이 없습니다.")
        png_bytes = _render_excel_area_png(values, title=f"{sheet.name} {area.get('range') or ''}".strip())
        return _store_artifact_bytes(
            project, rule,
            artifact_id=artifact_id, label=label,
            file_suffix=".png", content_type="image/png",
            content_bytes=png_bytes, kind="image",
            source_file=source_file, download=False,
        )


def _store_artifact_bytes(
    project, rule, *, artifact_id, label, file_suffix, content_type,
    content_bytes, kind, source_file, download,
):
    safe_artifact_id = engine._safe_artifact_id(artifact_id)
    safe_suffix = _safe_artifact_suffix(file_suffix)
    file_name = f"{rule.code}_{safe_artifact_id}{safe_suffix}"
    base_dir = _artifact_base_dir()
    relative_path = Path(str(project.id)) / file_name
    target_path = (base_dir / relative_path).resolve()
    try:
        target_path.relative_to(base_dir)
    except ValueError as exc:
        raise DownloadReviewInspectionError("산출물 저장 경로가 올바르지 않습니다.") from exc
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content_bytes)

    return {
        "id": safe_artifact_id,
        "label": label,
        "kind": kind,
        "content_type": content_type,
        "file_name": file_name,
        "relative_path": str(relative_path).replace("\\", "/"),
        "source_file": source_file,
        "download": download,
    }


def _artifact_base_dir():
    return Path(
        getattr(
            settings,
            "DOWNLOAD_REVIEW_ARTIFACT_DIR",
            Path(settings.BASE_DIR) / "main" / "data" / "download_review_artifacts",
        )
    ).resolve()


def _safe_artifact_suffix(value):
    import re

    suffix = str(value or "").strip().lower()
    if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
        return suffix
    return ".bin"


def _excel_area_values(rows, area):
    start_row = max(int(area.get("start_row") or 1) - 1, 0)
    end_row = max(int(area.get("end_row") or 0) - 1, start_row)
    start_col = max(int(area.get("start_column") or 1) - 1, 0)
    end_col = max(int(area.get("end_column") or 0) - 1, start_col)
    values = []
    for row_index in range(start_row, end_row + 1):
        row = rows[row_index] if row_index < len(rows) else []
        values.append([
            row[col_index] if col_index < len(row) else ""
            for col_index in range(start_col, end_col + 1)
        ])
    return values


def _render_excel_area_png(values, *, title):
    try:
        import fitz
    except Exception as exc:
        raise DownloadReviewInspectionError("Excel 영역 이미지를 생성하려면 PyMuPDF가 필요합니다.") from exc

    try:
        margin = 18
        title_height = 24 if title else 0
        row_height = 25
        font_size = 8.5
        col_widths = _excel_render_column_widths(values)
        width = max(sum(col_widths) + margin * 2, 240)
        height = max(len(values) * row_height + margin * 2 + title_height, 120)

        document = fitz.open()
        page = document.new_page(width=width, height=height)
        font_name = _insert_artifact_font(page)

        if title:
            page.insert_textbox(
                fitz.Rect(margin, margin - 2, width - margin, margin + title_height),
                title, fontsize=10, fontname=font_name, color=(0.1, 0.1, 0.1),
            )

        y = margin + title_height
        for row_index, row in enumerate(values):
            x = margin
            fill = (0.95, 0.96, 0.98) if row_index == 0 else None
            for col_index, cell in enumerate(row):
                cell_width = col_widths[col_index]
                rect = fitz.Rect(x, y, x + cell_width, y + row_height)
                page.draw_rect(rect, color=(0.68, 0.72, 0.78), fill=fill, width=0.5)
                page.insert_textbox(
                    rect + (4, 4, -4, -3),
                    _artifact_cell_text(cell),
                    fontsize=font_size, fontname=font_name, color=(0.08, 0.09, 0.11),
                )
                x += cell_width
            y += row_height

        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        png_bytes = pixmap.tobytes("png")
        document.close()
        return png_bytes
    except DownloadReviewInspectionError:
        raise
    except Exception as exc:
        raise DownloadReviewInspectionError("Excel 영역 이미지를 생성할 수 없습니다.") from exc


def _excel_render_column_widths(values):
    column_count = max((len(row) for row in values), default=0)
    widths = []
    for col_index in range(column_count):
        max_length = max(
            len(str(row[col_index])) if col_index < len(row) else 0
            for row in values
        )
        widths.append(min(max(70, max_length * 7 + 18), 220))
    return widths


def _insert_artifact_font(page):
    font_path = _artifact_font_path()
    if not font_path:
        return "helv"
    try:
        page.insert_font(fontname="gscert_cjk", fontfile=str(font_path))
        return "gscert_cjk"
    except Exception:
        return "helv"


def _artifact_font_path():
    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/malgunbd.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _artifact_cell_text(value):
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    return engine._normalize_spaces(text)
