import json
import sqlite3
import tempfile
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

from django.core.management import call_command
from django.db.utils import DatabaseError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from main.models import (
    DownloadReviewJob,
    DownloadReviewJobStatus,
    DownloadReviewProject,
    DownloadReviewProjectReviewStatus,
    DownloadReviewProjectStatus,
    DownloadReviewRule,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
)
from main.views.review.ecm_reference_db import (
    ARTIFACT_REVIEW_COLUMNS,
    ReferenceDbError,
    ReferenceDbMissing,
    ReferenceQueryError,
    write_project_review_result,
)
from main.views.review.ecm_download_review_worker import run_worker_once
from main.views.review.ecm_download_review_inspection import (
    _list_mismatches,
    cleanup_download_dir,
    get_rule_output_variables,
    run_download_inspection,
)
from main.views.review.ecm_llm_review import (
    LlmReviewFileContext,
    LlmReviewRuleContext,
    build_llm_review_payload,
    parse_llm_review_response,
)
from main.views.review.ecm_download_verify import verify_downloaded_files
from main.views.review.ecm_download_review_api import (
    active_job,
    job_cancel,
    job_detail,
    job_project_results,
    job_projects,
    jobs,
    latest_project_results,
    projects,
    rule_result_artifact,
)


def _docx_bytes(*, paragraphs=None, tables=None, blocks=None, header=None, footer=None):
    paragraphs = paragraphs or []
    tables = tables or []
    body_parts = []
    for block in blocks or []:
        if block["type"] == "paragraph":
            body_parts.append(_docx_paragraph_xml(block["text"]))
        elif block["type"] == "table":
            body_parts.append(_docx_table_xml(block["rows"]))
    for paragraph in paragraphs:
        body_parts.append(_docx_paragraph_xml(paragraph))
    for table in tables:
        body_parts.append(_docx_table_xml(table))
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body_parts)
        + "</w:body></w:document>"
    )
    bytes_buffer = tempfile.SpooledTemporaryFile()
    with zipfile.ZipFile(bytes_buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml.encode("utf-8"))
        if header is not None:
            header_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                + _docx_paragraph_xml(header)
                + "</w:hdr>"
            )
            archive.writestr("word/header1.xml", header_xml.encode("utf-8"))
        if footer is not None:
            footer_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                + _docx_paragraph_xml(footer)
                + "</w:ftr>"
            )
            archive.writestr("word/footer1.xml", footer_xml.encode("utf-8"))
    bytes_buffer.seek(0)
    data = bytes_buffer.read()
    bytes_buffer.close()
    return data


def _docx_paragraph_xml(paragraph):
    return f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>"


def _docx_table_xml(table):
    rows_xml = []
    for row in table:
        cells_xml = []
        for cell in row:
            cells_xml.append(
                "<w:tc><w:p><w:r><w:t>"
                + escape(cell)
                + "</w:t></w:r></w:p></w:tc>"
            )
        rows_xml.append("<w:tr>" + "".join(cells_xml) + "</w:tr>")
    return "<w:tbl>" + "".join(rows_xml) + "</w:tbl>"


def _pdf_bytes(lines):
    import fitz

    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    data = document.tobytes()
    document.close()
    return data


def _xlsx_bytes(*, rows=None, sheet_name="Sheet1"):
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    for row in rows or []:
        worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _xlsx_workbook_bytes(sheets, *, header=None, footer=None):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in sheets:
        worksheet = workbook.create_sheet(sheet_name)
        if header is not None:
            worksheet.oddHeader.center.text = header
        if footer is not None:
            worksheet.oddFooter.center.text = footer
        for row in rows:
            worksheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _defect_report_xlsx(project_number, sheets, *, header=None, footer=None):
    rows_by_sheet = []
    for sheet_name in sheets:
        if sheet_name in ("최종결함리포트", "시험분석자료"):
            date_text = "2026년 05월 31일"
        elif sheet_name.startswith("1차"):
            date_text = "2026년 05월 10일"
        else:
            date_text = "2026년 05월 20일"

        rows = [
            [f"{project_number} {sheet_name} 보고일자: {date_text}", "시험환경 Windows 11"],
            [],
            [],
        ]
        if sheet_name == "최종결함리포트":
            rows.extend([
                [],
                ["", "", "", "", "", "", "품질특성"],
                ["", "", "", "", "", "", "잔여-1"],
                ["", "", "", "", "", "", "잔여-2"],
            ])
        elif sheet_name == "시험분석자료":
            rows.extend([
                ["", "", "High", "3"],
                ["", "", "수정전"],
                [],
                [],
                [],
                [],
                ["", "", "7"],
                ["", "", "결함-1", "", "H"],
                ["", "", "-", "", "H"],
                ["", "", "", "", "H"],
                ["", "", "결함-2", "", "H"],
                ["", "", "결함-3", "", "H"],
            ])
        rows_by_sheet.append((sheet_name, rows))
    return _xlsx_workbook_bytes(rows_by_sheet, header=header, footer=footer)


def _defect_report_xlsx_split_title(project_number, sheets, *, header=None, footer=None):
    rows_by_sheet = []
    for sheet_name in sheets:
        if sheet_name in ("최종결함리포트", "시험분석자료"):
            date_text = "2026.05.31."
        elif sheet_name.startswith("1차"):
            date_text = "2026.04.14."
        else:
            date_text = "2026.04.20."

        rows = [
            [project_number, "시험환경 Windows 11"],
            [sheet_name],
            [f"보고일자: {date_text}"],
            [],
            [],
        ]
        if sheet_name == "최종결함리포트":
            rows.extend([
                [],
                ["", "", "", "", "", "", "잔여특성"],
                ["", "", "", "", "", "", "잔여-1"],
                ["", "", "", "", "", "", "잔여-2"],
            ])
        elif sheet_name == "시험분석자료":
            rows.extend([
                ["", "", "High", "3"],
                ["", "", "수정전"],
                [],
                [],
                [],
                [],
                ["", "", "7"],
                ["", "", "결함-1", "", "H"],
                ["", "", "-", "", "H"],
                ["", "", "", "", "H"],
                ["", "", "결함-2", "", "H"],
                ["", "", "결함-3", "", "H"],
            ])
        rows_by_sheet.append((sheet_name, rows))
    return _xlsx_workbook_bytes(rows_by_sheet, header=header, footer=footer)


def _test_case_xlsx(
    project_number,
    *,
    pl="김준호",
    start_date="2026.05.01.",
    end_date="2026.05.31.",
    residual_count=2,
):
    rows = [
        [f"{project_number} 테스트케이스"],
        [f"작성자: {pl}"],
        ["검토자: 김진영"],
        [f"작성일: {start_date} ~ {end_date}"],
        [],
        ["TC ID", "상세 테스트 결과"],
    ]
    for index in range(residual_count):
        rows.append([f"TC-F-{index + 1}", "F"])
    rows.append(["TC-P-1", "P"])
    return _xlsx_bytes(rows=rows)


def _test_plan_docx(project_number, *, product="테스트제품", version="v1.0", pl="김준호", wd="10"):
    first_table = [
        ["시험시작일", "2026.05.01."],
        ["비고", ""],
        ["담당자", "김진영"],
        ["시험PL", pl],
    ]
    second_table = [
        ["소프트웨어 명", product],
        ["버전", version],
        ["시험신청번호", project_number],
    ]
    configuration_table = [
        ["구분", "형상항목 ID"],
        ["소스", f"{project_number}-SRC"],
        ["문서", f"{project_number}-DOC"],
    ]
    schedule_table = [
        ["구분", "WD"],
        ["준비", "1"],
        ["분석", "1"],
        ["시험", str(int(wd) - 3)],
        ["종료", "1"],
    ]
    spec_table = [["항목", "값"], ["OS", "Windows"]]
    return _docx_bytes(
        blocks=[
            {"type": "table", "rows": first_table},
            {"type": "table", "rows": second_table},
            {"type": "paragraph", "text": "5.1 형상항목 식별 규칙"},
            {"type": "table", "rows": configuration_table},
            {"type": "paragraph", "text": "2.2 시험일정"},
            {"type": "table", "rows": schedule_table},
            {"type": "paragraph", "text": "<세부사양>"},
            {"type": "table", "rows": spec_table},
        ],
        footer="Copyright 2026 TTA",
    )


def _inspection_checklist_xlsx(
    project_number,
    *,
    pl="김준호",
    wd="10",
    high="3",
    before="7",
    start_date="2026.05.01.",
    end_date="2026.05.31.",
):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)

    def sheet(name):
        worksheet = workbook.create_sheet(name)
        worksheet.oddHeader.center.text = f"프로젝트번호: {project_number}"
        worksheet.oddFooter.center.text = "한국정보통신기술협회"
        return worksheet

    cover = sheet("표지")
    cover["A1"] = f"{project_number} 점검표"
    cover["A2"] = f"{start_date} ~ {end_date}"
    cover["A3"] = f"김 진 영 / {pl}"

    feature = sheet("기능별 점검표")
    feature["A8"] = 1
    feature["B8"] = "대분류1"
    feature["C8"] = "중분류1"
    feature["D8"] = "기능1"
    feature["A9"] = 2
    feature["B9"] = "대분류2"
    feature["C9"] = "중분류2"
    feature["D9"] = "기능2"
    for row in range(8, 10):
        for column in range(5, 35):
            feature.cell(row=row, column=column, value="O")

    suitability = sheet("2. 기능적합성")
    suitability["A16"] = "대분류1"
    suitability["B16"] = "중분류1"
    suitability["C16"] = "기능1"
    suitability["D16"] = "O"
    suitability["A17"] = "대분류2"
    suitability["B17"] = "중분류2"
    suitability["C17"] = "기능2"
    suitability["D17"] = "O"

    reliability = sheet("6. 신뢰성")
    reliability["C5"] = wd
    reliability["C11"] = high
    reliability["E11"] = before

    scores = sheet("측정항목별 점수표")
    for index, row in enumerate(range(7, 91), start=1):
        scores.cell(row=row, column=4, value=f"score-{index}")

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _quality_inspection_table_xlsx(project_number, *, score_overrides=None):
    from openpyxl import Workbook

    score_overrides = score_overrides or {}
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = f"{project_number} 품질검사표"
    for index, row in enumerate(range(4, 88), start=1):
        worksheet.cell(row=row, column=4, value=score_overrides.get(index, f"score-{index}"))
    for index, row in enumerate(range(4, 37), start=1):
        worksheet.cell(row=row, column=5, value=f"quality-{index}")

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _quality_evaluation_report_docx(project_number, *, company="에이치소프트"):
    quality_values = [
        *[f"quality-{index}" for index in range(4, 27)],
        *[f"quality-{index}" for index in range(28, 34)],
        "quality-1",
        "quality-2",
        "quality-3",
    ]
    quality_table = [["품질특성", "구분", "평가결과", "비고"]]
    for index, value in enumerate(quality_values, start=1):
        quality_table.append([f"항목{index}", "", value, ""])

    paragraphs = [
        f"{project_number} 품질평가보고서",
        project_number,
        project_number,
        project_number,
        project_number,
        project_number,
        "성  명 : 김  성  희",
        "정  성  룡     (서명)",
        "신청일자 : 2026년 5월 2일",
        "계약일자 : 2026년 5월 3일",
        "제품시험평가 : 2026년 5월 1일 ~ 2026년 5월 31일",
        "품질인증심의위원회 : 2026년 6월 1일",
        "<품질특성별 세부 평가결과>",
    ]
    blocks = [
        *({"type": "paragraph", "text": paragraph} for paragraph in paragraphs),
        {"type": "table", "rows": [["목차", "페이지"], ["품질특성별 세부 평가결과", "12"]]},
        {"type": "table", "rows": quality_table},
        {"type": "table", "rows": [["회사(기관)명", company]]},
    ]
    return _docx_bytes(
        blocks=blocks,
    )


class DownloadVerifyTests(SimpleTestCase):
    def test_zero_byte_file_fails_verification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "TTA-26-00010_empty.pdf"
            file_path.write_bytes(b"")

            result = verify_downloaded_files(temp_dir, "TTA-26-00010")

        self.assertFalse(result.success)
        self.assertIn("0 byte", result.error_message)

    def test_missing_project_number_is_warning_not_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "downloaded-report.pdf"
            file_path.write_bytes(b"content")

            result = verify_downloaded_files(temp_dir, "TTA-26-00010")

        self.assertTrue(result.success)
        self.assertFalse(result.has_project_number_files)
        self.assertTrue(result.warnings)


class DownloadReviewInspectionCompareTests(SimpleTestCase):
    def test_list_mismatches_compares_numeric_text_by_value(self):
        mismatches = _list_mismatches(
            ["1", "1.0", "0.125", "1,000", "NA", "30분"],
            ["1.00", "1", "0.1250", "1000.00", "NA", "30"],
            start_index=2,
        )

        self.assertEqual(mismatches, [{"row": 7, "expected": "30분", "actual": "30"}])


class LlmReviewInterfaceTests(SimpleTestCase):
    def test_payload_builder_creates_provider_neutral_messages(self):
        payload = build_llm_review_payload(
            project={"project_number": "TTA-26-00010", "company": "Example"},
            rule=LlmReviewRuleContext(
                code="manual_llm_rule",
                name="Manual LLM rule",
                prompt="Check whether the report is acceptable.",
                artifact_column="Report",
            ),
            files=[
                LlmReviewFileContext(
                    name="TTA-26-00010_report.pdf",
                    path="TTA-26-00010/TTA-26-00010_report.pdf",
                    size=123,
                    extension=".pdf",
                )
            ],
        )

        data = payload.to_dict()

        self.assertEqual(data["schema_version"], "download-review-llm-v1")
        self.assertEqual(data["provider_hint"], "manual-claude")
        self.assertEqual(data["messages"][0]["role"], "system")
        self.assertIn("response_schema", data)
        self.assertEqual(data["files"][0]["path"], "TTA-26-00010/TTA-26-00010_report.pdf")

    def test_parser_accepts_fenced_json_response(self):
        parsed = parse_llm_review_response(
            """
            ```json
            {
              "status": "fail",
              "expected": "Company name matches",
              "actual": "Different company name",
              "message": "The supplied evidence does not match.",
              "evidence": [{"file_name": "report.pdf", "reason": "Mismatch"}],
              "confidence": 0.82
            }
            ```
            """
        )

        self.assertEqual(parsed.status, DownloadReviewRuleStatus.FAIL)
        self.assertEqual(parsed.confidence, 0.82)
        self.assertEqual(parsed.evidence[0]["file_name"], "report.pdf")

    def test_build_llm_review_prompt_command_outputs_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "TTA-26-00010_report.txt"
            report.write_text("sample document text", encoding="utf-8")
            out = StringIO()

            call_command(
                "build_llm_review_prompt",
                "--project-number",
                "TTA-26-00010",
                "--download-dir",
                temp_dir,
                "--rule-name",
                "Manual rule",
                "--rule-prompt",
                "Check the supplied document.",
                stdout=out,
            )

        data = json.loads(out.getvalue())

        self.assertEqual(data["schema_version"], "download-review-llm-v1")
        self.assertEqual(data["project"]["project_number"], "TTA-26-00010")
        self.assertEqual(data["files"][0]["name"], "TTA-26-00010_report.txt")
        self.assertEqual(data["rule"]["name"], "Manual rule")


class DownloadReviewRuleSeedCommandTests(TestCase):
    databases = {"default", "workflow"}

    def test_seed_creates_disabled_rules_by_default(self):
        out = StringIO()

        call_command("seed_download_review_rules", stdout=out)

        self.assertEqual(DownloadReviewRule.objects.count(), len(ARTIFACT_REVIEW_COLUMNS))
        first_rule = DownloadReviewRule.objects.order_by("sort_order").first()
        self.assertEqual(first_rule.code, "artifact_01")
        self.assertEqual(first_rule.config_json["artifact_column"], ARTIFACT_REVIEW_COLUMNS[0])
        self.assertFalse(first_rule.enabled)
        report_rule = DownloadReviewRule.objects.get(name="시험성적서(PDF)")
        defect_rule = DownloadReviewRule.objects.get(name="결함리포트")
        self.assertLess(report_rule.sort_order, defect_rule.sort_order)
        self.assertIn("created=", out.getvalue())

    def test_seed_can_enable_and_update_existing_rules(self):
        DownloadReviewRule.objects.create(code="artifact_01", name="old", enabled=False)
        out = StringIO()

        call_command("seed_download_review_rules", "--enable", "--update-existing", stdout=out)

        rule = DownloadReviewRule.objects.get(code="artifact_01")
        self.assertEqual(rule.name, ARTIFACT_REVIEW_COLUMNS[0])
        self.assertTrue(rule.enabled)
        self.assertIn("updated=", out.getvalue())

    def test_seed_only_real_creates_implemented_rules(self):
        out = StringIO()

        call_command("seed_download_review_rules", "--only-real", "--enable", stdout=out)

        self.assertEqual(DownloadReviewRule.objects.count(), 18)
        self.assertEqual(
            set(DownloadReviewRule.objects.values_list("name", flat=True)),
            {
                "계약서",
                "합의서(PDF)",
                "수수료산정표",
                "시험환경구성도",
                "품질특성별제품정보기재사항",
                "기능리스트",
                "시험계획서(PDF)",
                "최초/최종형상RawData",
                "테스트케이스",
                "결함리포트",
                "점검표(PDF)",
                "1차/2차/성능/보안RawData",
                "시험성적서(PDF)",
                "시험기록서",
                "품질평가보고서",
                "품질검사표",
                "SW저작권확인서",
                "홍보이미지",
            },
        )
        rule = DownloadReviewRule.objects.get(name="계약서")
        self.assertEqual(rule.rule_type, "required_artifact_file")
        self.assertTrue(rule.enabled)


class DownloadReviewProjectsApiTests(TestCase):
    databases = {"default", "workflow"}

    def setUp(self):
        self.factory = RequestFactory()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reference_db_path = Path(self.temp_dir.name) / "ecmlist.db"
        self.reference_db_path_2 = Path(self.temp_dir.name) / "ecmlist2.db"
        self._create_reference_db()
        self.reference_db_path_2.write_bytes(self.reference_db_path.read_bytes())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_projects_are_sorted_by_cert_date_desc_by_default(self):
        data = self._get_projects()

        self.assertEqual(data["pagination"]["total"], 3)
        self.assertEqual(
            [item["project_number"] for item in data["items"]],
            ["TTA-26-00010", "TTA-26-00009", "TTA-26-00008"],
        )
        self.assertTrue(data["items"][0]["selectable"])
        self.assertFalse(data["items"][1]["selectable"])
        self.assertEqual(data["items"][1]["active_state_label"], "완료")

    def test_projects_filter_uses_allowlisted_query_params(self):
        data = self._get_projects({"company": "우리", "limit": "1"})

        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(data["items"][0]["company"], "우리데이터 주식회사")

    def test_projects_reject_unknown_query_params(self):
        response = self._request({"raw_sql": "SELECT * FROM ecm_list"})
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "invalid_query")

    def test_projects_still_return_when_workflow_state_db_is_unavailable(self):
        class BrokenProjectManager:
            def select_related(self, *args):
                return self

            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args):
                return self

            def __iter__(self):
                raise DatabaseError("workflow database is unavailable")

        class BrokenDownloadReviewProject:
            objects = BrokenProjectManager()

        request = self.factory.get("/api/projects/", {"limit": "2"})
        with (
            self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"),
            patch(
                "main.views.review.ecm_download_review_jobs.DownloadReviewProject",
                BrokenDownloadReviewProject,
            ),
        ):
            response = projects(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["items"]), 2)
        self.assertIsNone(data["items"][0]["active_job_id"])
        self.assertEqual(data["items"][0]["active_state_label"], "")
        self.assertEqual(data["items"][1]["active_state_label"], "완료")

    def test_projects_show_latest_failed_held_result_as_failed(self):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.COMPLETED,
            requested_project_count=1,
            failed_project_count=1,
        )
        DownloadReviewProject.objects.create(
            job=job,
            center_code="sangam",
            project_number="TTA-26-00010",
            ecm_row_json={"project_number": "TTA-26-00010", "company": "에이치소프트"},
            status=DownloadReviewProjectStatus.FAILED,
            review_status=DownloadReviewProjectReviewStatus.HELD,
            current_step="다운로드 파일 확인",
            error_message="다운로드 파일을 찾을 수 없습니다.",
            completed_at=timezone.now(),
        )

        data = self._get_projects({"project_number": "TTA-26-00010"})

        self.assertEqual(data["items"][0]["review"], "실패")
        self.assertEqual(data["items"][0]["review_raw"], "실패")

    def test_projects_can_read_yeongnam_center_db(self):
        yeongnam_db_path = self.reference_db_path_2
        if yeongnam_db_path.exists():
            yeongnam_db_path.unlink()
        self._create_yeongnam_reference_db(yeongnam_db_path)

        request = self.factory.get("/api/projects/", {"center": "yeongnam"})
        with self.settings(REFERENCE_DB_PATH_2=yeongnam_db_path, REFERENCE_DB_TABLE="ecm_list"):
            response = projects(request)
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["items"][0]["center_code"], "yeongnam")
        self.assertEqual(data["items"][0]["center_label"], "영남")
        self.assertEqual(data["items"][0]["project_number"], "TTA-26-09999")

    def _get_projects(self, params=None):
        response = self._request(params or {})
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content.decode("utf-8"))

    def _request(self, params):
        request = self.factory.get("/api/projects/", params)
        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            return projects(request)

    def _create_reference_db(self):
        conn = sqlite3.connect(self.reference_db_path)
        try:
            conn.execute(
                """
                CREATE TABLE ecm_list (
                    "프로젝트번호" TEXT,
                    "인증일자" TEXT,
                    "회사명" TEXT,
                    "제품명" TEXT,
                    "시험PL" TEXT,
                    "점검결과" TEXT,
                    "점검날짜" TEXT
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO ecm_list (
                    "프로젝트번호",
                    "인증일자",
                    "회사명",
                    "제품명",
                    "시험PL",
                    "점검결과",
                    "점검날짜"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "TTA-26-00009",
                        "05/12",
                        "우리데이터 주식회사",
                        "우리데이터클리닝 V1.0",
                        "박지훈",
                        "O",
                        "2026.05.12 20:30",
                    ),
                    (
                        "TTA-26-00010",
                        "05/13",
                        "에이치소프트",
                        "SecureFlow 2.1",
                        "김준호",
                        "",
                        "",
                    ),
                    (
                        "TTA-26-00008",
                        "05/11",
                        "넥스트랩",
                        "NextLab QA Suite",
                        "최유진",
                        "X",
                        "2026.05.11 21:00",
                    ),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def _create_yeongnam_reference_db(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE ecm_list (
                    "프로젝트번호" TEXT,
                    "인증일자" TEXT,
                    "회사명" TEXT,
                    "제품명" TEXT,
                    "시험PL" TEXT,
                    "점검결과" TEXT,
                    "점검날짜" TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO ecm_list (
                    "프로젝트번호",
                    "인증일자",
                    "회사명",
                    "제품명",
                    "시험PL",
                    "점검결과",
                    "점검날짜"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("TTA-26-09999", "05/14", "영남테스트", "Yeongnam Suite", "김영남", "", ""),
            )
            conn.commit()
        finally:
            conn.close()


class DownloadReviewJobsApiTests(TestCase):
    databases = {"default", "workflow"}

    def setUp(self):
        self.factory = RequestFactory()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reference_db_path = Path(self.temp_dir.name) / "ecmlist.db"
        self.reference_db_path_2 = Path(self.temp_dir.name) / "ecmlist2.db"
        self._create_reference_db()
        self.reference_db_path_2.write_bytes(self.reference_db_path.read_bytes())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_job_request_creates_job_and_projects(self):
        response = self._post_job(["TTA-26-00010"])
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["requested_project_count"], 1)
        self.assertIn(data["status"], {"scheduled", "queued"})
        self.assertEqual(DownloadReviewJob.objects.count(), 1)
        self.assertEqual(DownloadReviewProject.objects.count(), 1)

    def test_job_request_uses_selected_center_without_cross_center_conflict(self):
        yeongnam_response = self._post_job(["TTA-26-00010"], center="yeongnam")
        yeongnam_data = json.loads(yeongnam_response.content.decode("utf-8"))

        sangam_response = self._post_job(["TTA-26-00010"], center="sangam")
        sangam_data = json.loads(sangam_response.content.decode("utf-8"))

        self.assertEqual(yeongnam_response.status_code, 201)
        self.assertEqual(yeongnam_data["center_code"], "yeongnam")
        self.assertEqual(sangam_response.status_code, 201)
        self.assertEqual(sangam_data["center_code"], "sangam")
        self.assertEqual(DownloadReviewJob.objects.count(), 2)
        self.assertEqual(
            set(DownloadReviewProject.objects.values_list("center_code", flat=True)),
            {"sangam", "yeongnam"},
        )

    def test_job_request_rejects_completed_projects(self):
        response = self._post_job(["TTA-26-00009"])
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "completed_project_not_allowed")
        self.assertEqual(data["details"]["completed_project_numbers"], ["TTA-26-00009"])
        self.assertEqual(DownloadReviewJob.objects.count(), 0)

    def test_job_request_rejects_active_duplicate_projects(self):
        first_response = self._post_job(["TTA-26-00010"])
        self.assertEqual(first_response.status_code, 201)

        response = self._post_job(["TTA-26-00010"])
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "active_project_conflict")
        self.assertEqual(data["details"]["conflicts"][0]["project_number"], "TTA-26-00010")
        self.assertEqual(DownloadReviewJob.objects.count(), 1)

    def test_active_job_returns_no_polling_when_empty(self):
        response = active_job(self.factory.get("/api/jobs/active/"))
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(data["active_job"])
        self.assertFalse(data["polling"]["should_poll"])
        self.assertIsNone(data["polling"]["recommended_interval_ms"])
        self.assertIsNone(data["polling"]["wake_at"])

    def test_active_job_and_detail_endpoints_return_created_job(self):
        created = json.loads(self._post_job(["TTA-26-00010"]).content.decode("utf-8"))

        active_response = active_job(self.factory.get("/api/jobs/active/"))
        active_data = json.loads(active_response.content.decode("utf-8"))
        detail_response = job_detail(
            self.factory.get(f"/api/jobs/{created['job_id']}/"),
            created["job_id"],
        )
        detail_data = json.loads(detail_response.content.decode("utf-8"))

        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(active_data["active_job"]["id"], created["job_id"])
        if active_data["active_job"]["status"] == "scheduled":
            self.assertFalse(active_data["polling"]["should_poll"])
            self.assertIsNone(active_data["polling"]["recommended_interval_ms"])
            self.assertIsNotNone(active_data["polling"]["wake_at"])
        else:
            self.assertTrue(active_data["polling"]["should_poll"])
            self.assertEqual(active_data["polling"]["recommended_interval_ms"], 3000)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_data["job"]["selected_project_numbers"], ["TTA-26-00010"])

    def test_active_job_endpoint_uses_global_worker_queue_even_with_center_query(self):
        sangam = DownloadReviewJob.objects.create(
            center_code="sangam",
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        yeongnam = DownloadReviewJob.objects.create(
            center_code="yeongnam",
            status=DownloadReviewJobStatus.SCHEDULED,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00011"],
        )

        response = active_job(self.factory.get("/api/jobs/active/", {"center": "yeongnam"}))
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["active_job"]["id"], str(sangam.id))
        self.assertNotEqual(data["active_job"]["id"], str(yeongnam.id))
        self.assertEqual(data["active_job_count"], 2)
        self.assertNotIn("center_active_job_count", data)

    def test_projects_api_marks_active_project_as_not_selectable(self):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.SCHEDULED,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            ecm_row_json={"project_number": "TTA-26-00010", "company": "에이치소프트"},
        )

        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            response = projects(
                self.factory.get("/api/projects/", {"project_number": "TTA-26-00010"}),
            )
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["items"][0]["active_job_id"], str(job.id))
        self.assertEqual(data["items"][0]["active_state_label"], "예약중")
        self.assertFalse(data["items"][0]["selectable"])

    def test_jobs_list_endpoint_returns_recent_jobs_and_filters_status(self):
        completed = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.COMPLETED,
            requested_project_count=2,
            completed_project_count=1,
            failed_project_count=1,
            selected_projects_json=["TTA-26-00010", "TTA-26-00011"],
        )
        DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.SCHEDULED,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00012"],
        )

        all_response = jobs(self.factory.get("/api/jobs/", {"status": "all", "limit": "10"}))
        all_data = json.loads(all_response.content.decode("utf-8"))
        finished_response = jobs(self.factory.get("/api/jobs/", {"status": "finished"}))
        finished_data = json.loads(finished_response.content.decode("utf-8"))
        completed_response = jobs(self.factory.get("/api/jobs/", {"status": "completed"}))
        completed_data = json.loads(completed_response.content.decode("utf-8"))

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(all_data["pagination"]["total"], 2)
        self.assertEqual(all_data["items"][0]["status"], DownloadReviewJobStatus.SCHEDULED)
        self.assertEqual(finished_response.status_code, 200)
        self.assertEqual(finished_data["pagination"]["total"], 1)
        self.assertEqual(finished_data["items"][0]["id"], str(completed.id))
        self.assertEqual(completed_response.status_code, 200)
        self.assertEqual(completed_data["pagination"]["total"], 1)
        self.assertEqual(completed_data["items"][0]["id"], str(completed.id))
        self.assertEqual(completed_data["items"][0]["completed_project_count"], 1)
        self.assertEqual(completed_data["items"][0]["failed_project_count"], 1)

    def test_jobs_list_endpoint_filters_center(self):
        DownloadReviewJob.objects.create(
            center_code="sangam",
            status=DownloadReviewJobStatus.COMPLETED,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        yeongnam = DownloadReviewJob.objects.create(
            center_code="yeongnam",
            status=DownloadReviewJobStatus.COMPLETED,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00011"],
        )

        response = jobs(self.factory.get("/api/jobs/", {"status": "all", "center": "yeongnam"}))
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["pagination"]["total"], 1)
        self.assertEqual(data["items"][0]["id"], str(yeongnam.id))
        self.assertEqual(data["items"][0]["center_code"], "yeongnam")

    def test_cancel_scheduled_job_marks_projects_skipped(self):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.SCHEDULED,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            ecm_row_json={"project_number": "TTA-26-00010", "company": "에이치소프트"},
        )

        response = job_cancel(self.factory.post(f"/api/jobs/{job.id}/cancel/"), job.id)
        data = json.loads(response.content.decode("utf-8"))
        job.refresh_from_db()
        project.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(job.status, DownloadReviewJobStatus.CANCELED)
        self.assertIsNotNone(job.canceled_at)
        self.assertEqual(project.status, DownloadReviewProjectStatus.SKIPPED)
        self.assertEqual(project.current_step, "사용자 취소")

    def test_cancel_running_job_is_rejected(self):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )

        response = job_cancel(self.factory.post(f"/api/jobs/{job.id}/cancel/"), job.id)
        data = json.loads(response.content.decode("utf-8"))
        job.refresh_from_db()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "job_cancel_not_allowed")
        self.assertEqual(job.status, DownloadReviewJobStatus.RUNNING)

    def test_jobs_list_endpoint_rejects_unknown_filters(self):
        cases = [
            {"raw_sql": "SELECT * FROM automation_job"},
            {"status": "unknown"},
            {"limit": "101"},
            {"offset": "-1"},
        ]

        for params in cases:
            with self.subTest(params=params):
                response = jobs(self.factory.get("/api/jobs/", params))
                data = json.loads(response.content.decode("utf-8"))

                self.assertEqual(response.status_code, 400)
                self.assertFalse(data["success"])
                self.assertEqual(data["error_code"], "invalid_job_request")

    def test_job_projects_and_results_endpoints_return_project_data(self):
        created = json.loads(self._post_job(["TTA-26-00010"]).content.decode("utf-8"))
        project = DownloadReviewProject.objects.get(project_number="TTA-26-00010")
        project.status = DownloadReviewProjectStatus.INSPECTING
        project.current_step = "zip 검사 중"
        project.save(update_fields=["status", "current_step"])
        DownloadReviewRuleResult.objects.create(
            job_project=project,
            rule_code="required-report",
            rule_name="시험성적서 PDF 존재",
            sequence=1,
            file_path="TTA-26-00010/시험성적서.pdf",
            file_name="시험성적서.pdf",
            status=DownloadReviewRuleStatus.PASS,
            expected="파일 존재",
            actual="파일 존재",
            message="정상 확인",
        )

        projects_response = job_projects(
            self.factory.get(f"/api/jobs/{created['job_id']}/projects/"),
            created["job_id"],
        )
        projects_data = json.loads(projects_response.content.decode("utf-8"))
        results_response = job_project_results(
            self.factory.get(f"/api/job-projects/{project.id}/results/"),
            project.id,
        )
        results_data = json.loads(results_response.content.decode("utf-8"))

        self.assertEqual(projects_response.status_code, 200)
        self.assertEqual(projects_data["items"][0]["project_number"], "TTA-26-00010")
        self.assertEqual(projects_data["items"][0]["status_label"], "검사중")
        self.assertEqual(results_response.status_code, 200)
        self.assertEqual(results_data["items"][0]["status_label"], "정상")

    def test_latest_project_results_endpoint_returns_most_recent_finished_project(self):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.COMPLETED,
            requested_project_count=1,
            completed_project_count=1,
            selected_projects_json=["TTA-26-00009"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00009",
            status=DownloadReviewProjectStatus.COMPLETED,
            review_status=DownloadReviewProjectReviewStatus.COMPLETED,
            ecm_row_json={
                "project_number": "TTA-26-00009",
                "company": "우리데이터 주식회사",
                "product": "우리데이터클리닝 V1.0",
            },
        )
        DownloadReviewRuleResult.objects.create(
            job_project=project,
            rule_code="required-report",
            rule_name="시험성적서 PDF 존재",
            sequence=1,
            file_path="TTA-26-00009/시험성적서.pdf",
            file_name="시험성적서.pdf",
            status=DownloadReviewRuleStatus.PASS,
            expected="파일 존재",
            actual="파일 존재",
            message="정상 확인",
        )

        response = latest_project_results(
            self.factory.get("/api/projects/TTA-26-00009/latest-results/"),
            "TTA-26-00009",
        )
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["project"]["project_number"], "TTA-26-00009")
        self.assertEqual(data["items"][0]["rule_name"], "시험성적서 PDF 존재")
        self.assertEqual(data["items"][0]["status_label"], "정상")

    def test_download_inspection_records_results_and_cleanup_deletes_download_dir(self):
        download_root = Path(self.temp_dir.name) / "downloads"
        project_dir = download_root / "TTA-26-00010_1"
        project_dir.mkdir(parents=True)
        (project_dir / "계약서_TTA-26-00010.pdf").write_bytes(b"contract")
        (project_dir / "readme.txt").write_bytes(b"readme")
        DownloadReviewRule.objects.create(
            code="계약서",
            name="계약서",
            rule_type="required_file_name_contains",
            config_json={"contains": "계약서", "artifact_column": "계약서"},
            sort_order=1,
        )
        DownloadReviewRule.objects.create(
            code="시험성적서(PDF)",
            name="시험성적서(PDF)",
            rule_type="required_file_name_contains",
            config_json={"contains": "시험성적서", "artifact_column": "시험성적서(PDF)"},
            sort_order=2,
        )
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={
                "project_number": "TTA-26-00010",
                "company": "에이치소프트",
                "pl": "김준호",
            },
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")
        file_summary = {
            "file_count": verify_result.file_count,
            "file_names": [file_info.name for file_info in verify_result.files],
        }

        with self.settings(
            AGENT_DOWNLOAD_BASE_DIR=download_root,
            REFERENCE_DB_PATH=self.reference_db_path,
            REFERENCE_DB_TABLE="ecm_list",
        ):
            outcome = run_download_inspection(project, verify_result, file_summary)
            write_project_review_result(
                project.project_number,
                outcome.reference_review,
                artifact_results=outcome.artifact_results,
            )
            cleanup = cleanup_download_dir(project)

        rows = self._reference_rows(
            ["TTA-26-00010"],
            ["점검결과", "계약서", "시험성적서(PDF)"],
        )
        project.refresh_from_db()

        self.assertEqual(outcome.reference_review, "X")
        self.assertEqual(outcome.failed_count, 1)
        self.assertGreaterEqual(DownloadReviewRuleResult.objects.filter(job_project=project).count(), 2)
        self.assertEqual(rows["TTA-26-00010"]["점검결과"], "X")
        self.assertEqual(rows["TTA-26-00010"]["계약서"], "O")
        self.assertEqual(rows["TTA-26-00010"]["시험성적서(PDF)"], "X")
        self.assertTrue(cleanup.deleted)
        self.assertFalse(project_dir.exists())
        self.assertIsNotNone(project.zip_deleted_at)

    def test_actual_artifact_rules_inspect_zip_entries(self):
        project_dir = Path(self.temp_dir.name) / "downloads"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference.db"
        self._create_master_reference_db(master_db_path)
        zip_path = project_dir / "TTA-26-00010.zip"
        rawdata_zip_path = project_dir / "TTA-26-00010 rawdata.zip"
        with zipfile.ZipFile(rawdata_zip_path, "w") as rawdata_archive:
            rawdata_archive.writestr("결함/raw.txt", b"defect")
            rawdata_archive.writestr("보안/1차/raw.txt", b"security")
            rawdata_archive.writestr("보안/2차/raw.txt", b"security")
            rawdata_archive.writestr("성능/1차/raw.txt", b"performance")
            rawdata_archive.writestr("성능/2차/raw.txt", b"performance")
            for folder_name in ("최초정상", "최종정상"):
                for index in range(5):
                    info = zipfile.ZipInfo(
                        f"3.설계/제품스크린샷/{folder_name}/image-{index}.png",
                        date_time=(2026, 5, 20, 12, 0, 0),
                    )
                    rawdata_archive.writestr(info, b"image")
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("2.계약/TTA-26-00010 계약서.pdf", b"contract")
            archive.writestr(
                "2.계약/TTA-26-00010 시험합의서.docx",
                _docx_bytes(
                    tables=[[["시험신청번호", "TTA-26-00010"]]],
                    header="TTA-26-00010",
                    footer="TIS-0101-3 (00)",
                ),
            )
            archive.writestr(
                "2.계약/TTA-26-00010 시험합의서.pdf",
                _pdf_bytes(["ApplicationNo", "TTA-26-00010"]),
            )
            archive.writestr("2.계약/TTA-26-00010 수수료산정표.xlsx", b"fee")
            archive.writestr("4.시험/가.계획/TTA-26-00010 시험환경구성도.pptx", b"diagram")
            archive.writestr(
                "4.시험/가.계획/TTA-26-00010 기능리스트.xlsx",
                _xlsx_bytes(
                    rows=[
                        ["TTA-26-00010 기능리스트"],
                        ["작성자: 김준호"],
                        ["대분류", "중분류", "기능"],
                        ["대분류1", "중분류1", "기능1"],
                    ],
                ),
            )
            archive.writestr(
                "4.시험/가.계획/TTA-26-00010 시험계획서.docx",
                _test_plan_docx("TTA-26-00010", product="테스트제품", version="v1.0", pl="김준호", wd="10"),
            )
            archive.writestr(
                "4.시험/가.계획/TTA-26-00010 시험계획서.pdf",
                _pdf_bytes(["TTA-26-00010 시험계획서"]),
            )
            archive.writestr(
                "4.시험/가.계획/TTA-26-00010 품질특성별 제품 정보 기재사항.docx",
                _docx_bytes(
                    paragraphs=[
                        "(TTA-26-00010) 품질특성별",
                        "(2026.5.28)",
                    ],
                ),
            )
            for folder_name in ("최초형상", "최종형상"):
                for index in range(5):
                    info = zipfile.ZipInfo(
                        f"3.설계/제품스크린샷/{folder_name}/image-{index}.png",
                        date_time=(2026, 5, 20, 12, 0, 0),
                    )
                    archive.writestr(info, b"image")
            archive.writestr(
                "3.설계/TTA-26-00010 테스트케이스.xlsx",
                _test_case_xlsx("TTA-26-00010", pl="김준호", residual_count=2),
            )
            archive.writestr(
                "3.설계/TTA-26-00010 점검표.xlsx",
                _inspection_checklist_xlsx("TTA-26-00010", pl="김준호", wd="10", high="3", before="7"),
            )
            archive.writestr(
                "3.설계/TTA-26-00010 점검표.pdf",
                _pdf_bytes(["TTA-26-00010 점검표"]),
            )
            archive.writestr("5.수행/결함리포트/raw.txt", b"defect")
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v1.0.xlsx",
                _defect_report_xlsx("TTA-26-00010", ["1차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v2.0.xlsx",
                _defect_report_xlsx("TTA-26-00010", ["1차 결함리포트", "2차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v3.0.xlsx",
                _defect_report_xlsx(
                    "TTA-26-00010",
                    ["1차 결함리포트", "2차 결함리포트", "최종결함리포트", "시험분석자료"],
                ),
            )
            archive.writestr("5.수행/보안/1차/raw.txt", b"security")
            archive.writestr("5.수행/보안/2차/raw.txt", b"security")
            archive.writestr("5.수행/성능/1차/raw.txt", b"performance")
            archive.writestr("5.수행/성능/2차/raw.txt", b"performance")
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험성적서.docx",
                _docx_bytes(
                    paragraphs=["<세부사양>"],
                    tables=[
                        [["항목", "값"], ["OS", "Windows"]],
                        [["결함리포트 송부 1차: 2026.05.10 2차: 2026.05.20"]],
                    ],
                ),
            )
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험성적서.pdf",
                _pdf_bytes(["TTA-26-00010 시험성적서"]),
            )
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험기록서.pdf",
                _pdf_bytes(["TTA-26-00010 시험기록서"]),
            )
            archive.writestr(
                "6.시험/나.종료/v2.0 2026.05.10. 변수확인.txt",
                b"variable probe",
            )
            archive.writestr(
                "6.시험/인증관련/TTA-26-00010 품질검사표.xlsx",
                _quality_inspection_table_xlsx("TTA-26-00010"),
            )
            archive.writestr(
                "6.시험/인증관련/TTA-26-00010 품질평가보고서.docx",
                _quality_evaluation_report_docx("TTA-26-00010"),
            )
            archive.writestr("6.시험/인증관련/SW저작권확인서.pdf", b"copyright")
            archive.writestr("7.홍보자료/promo.jpg", b"promo")

        call_command("seed_download_review_rules", "--only-real", "--enable", stdout=StringIO())
        agreement_rule = DownloadReviewRule.objects.get(name="합의서(PDF)")
        agreement_config = agreement_rule.config_json
        agreement_config["content_checks"][1]["label"] = "ApplicationNo"
        agreement_rule.config_json = agreement_config
        agreement_rule.save(update_fields=["config_json", "updated_at"])
        DownloadReviewRule.objects.create(
            code="variable_probe",
            name="변수 전달 테스트",
            rule_type="required_artifact_file",
            target_file_type="any",
            enabled=True,
            sort_order=900,
            config_json={
                "folder_keyword_chain": ["시험", "종료"],
                "filename_keywords": ["v{결함차수}.0", "{1차}"],
                "extensions": [".txt"],
                "min_count": 1,
                "pass_message": "이전 규칙 산출 변수를 확인했습니다.",
            },
        )
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={
                "project_number": "TTA-26-00010",
                "company": "에이치소프트",
                "product": "테스트제품 v1.0",
                "pl": "김준호",
                "wd": "10",
                "신청일": "2026.05.02.",
                "계약일": "2026.05.03.",
                "인증일자": "2026.06.01.",
            },
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")

        artifact_dir = Path(self.temp_dir.name) / "artifacts"
        with self.settings(
            DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path,
            DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir,
        ):
            outcome = run_download_inspection(project, verify_result, {})
        results = {
            result.rule_name: result
            for result in DownloadReviewRuleResult.objects.filter(job_project=project)
        }

        failed_rules = [
            (result.rule_name, result.message)
            for result in DownloadReviewRuleResult.objects.filter(job_project=project, status=DownloadReviewRuleStatus.FAIL)
        ]
        self.assertEqual(outcome.reference_review, "O", failed_rules)
        self.assertEqual(outcome.failed_count, 0)
        self.assertEqual(outcome.artifact_results["계약서"], "O")
        self.assertEqual(outcome.artifact_results["합의서(PDF)"], "O")
        self.assertEqual(outcome.artifact_results["수수료산정표"], "O")
        self.assertEqual(outcome.artifact_results["시험환경구성도"], "O")
        self.assertEqual(outcome.artifact_results["품질특성별제품정보기재사항"], "O")
        self.assertEqual(outcome.artifact_results["기능리스트"], "O")
        self.assertEqual(outcome.artifact_results["시험계획서(PDF)"], "O")
        self.assertEqual(outcome.artifact_results["최초/최종형상RawData"], "O")
        self.assertEqual(outcome.artifact_results["테스트케이스"], "O")
        self.assertEqual(outcome.artifact_results["결함리포트"], "O")
        self.assertEqual(outcome.artifact_results["점검표(PDF)"], "O")
        self.assertEqual(outcome.artifact_results["1차/2차/성능/보안RawData"], "O")
        self.assertEqual(outcome.artifact_results["시험성적서(PDF)"], "O")
        self.assertEqual(outcome.artifact_results["시험기록서"], "O")
        self.assertEqual(outcome.artifact_results["품질평가보고서"], "O")
        self.assertEqual(outcome.artifact_results["품질검사표"], "O")
        self.assertEqual(outcome.artifact_results["SW저작권확인서"], "O")
        self.assertEqual(outcome.artifact_results["홍보이미지"], "O")
        self.assertIn("2.계약", results["계약서"].file_path)
        self.assertIn("4.시험/가.계획", results["시험환경구성도"].file_path)
        agreement_result = results["합의서(PDF)"]
        feature_result = results["기능리스트"]
        plan_result = results["시험계획서(PDF)"]
        self.assertTrue(
            any(
                check.get("part") == "header" and check["passed"]
                for check in agreement_result.raw_detail_json["content_checks"]
            )
        )
        self.assertTrue(
            any(
                check.get("part") == "footer" and check["passed"]
                for check in agreement_result.raw_detail_json["content_checks"]
            )
        )
        self.assertEqual(results["변수 전달 테스트"].status, DownloadReviewRuleStatus.PASS)
        report_result = results["시험성적서(PDF)"]
        self.assertEqual(report_result.raw_detail_json["variables"]["결함차수"], 2)
        self.assertEqual(report_result.raw_detail_json["variables"]["1차"], "2026.05.10.")
        self.assertEqual(report_result.raw_detail_json["variables"]["2차"], "2026.05.20.")
        self.assertEqual(report_result.raw_detail_json["variables"]["시험성적서_세부사양표"], [["항목", "값"], ["OS", "Windows"]])
        self.assertEqual(get_rule_output_variables(project)["결함차수"], 2)
        self.assertTrue(
            any(
                check.get("details")
                and check["details"][0]["term"] == "TIS-"
                and check["details"][0]["passed"]
                for check in plan_result.raw_detail_json["checks"]
            )
        )
        self.assertEqual(plan_result.raw_detail_json["checks"][-1]["name"], "spec_table")
        self.assertTrue(plan_result.raw_detail_json["checks"][-1]["passed"])
        defect_result = results["결함리포트"]
        self.assertEqual(defect_result.raw_detail_json["variables"]["잔여결함수"], 2)
        self.assertEqual(defect_result.raw_detail_json["variables"]["H"], "3")
        self.assertEqual(defect_result.raw_detail_json["variables"]["R"], "7")
        self.assertTrue(defect_result.raw_detail_json["print_text_checks"]["forbidden_headers"]["passed"])
        self.assertTrue(defect_result.raw_detail_json["print_text_checks"]["forbidden_footers"]["passed"])
        test_case_result = results["테스트케이스"]
        self.assertTrue(test_case_result.raw_detail_json["footer_check"]["passed"])
        self.assertEqual(test_case_result.raw_detail_json["residual_defect_check"]["expected_count"], 2)
        self.assertEqual(test_case_result.raw_detail_json["residual_defect_check"]["actual_count"], 2)
        self.assertEqual(test_case_result.raw_detail_json["residual_defect_check"]["failed_rows"], [7, 8])
        checklist_result = results["점검표(PDF)"]
        self.assertTrue(checklist_result.raw_detail_json["footer_checks"]["forbidden"]["passed"])
        self.assertTrue(checklist_result.raw_detail_json["footer_checks"]["required"]["passed"])
        self.assertEqual(len(checklist_result.raw_detail_json["variables"]["측정항목별점수표"]), 84)
        self.assertEqual(checklist_result.raw_detail_json["variables"]["측정항목별점수표"][0], "score-1")
        quality_result = results["품질검사표"]
        quality_values = quality_result.raw_detail_json["variables"]["품질부특성측정값"]
        self.assertEqual(len(quality_values), 32)
        self.assertEqual(quality_values[0], "quality-4")
        self.assertNotIn("quality-27", quality_values)
        self.assertEqual(quality_values[-1], "quality-3")
        report_quality_result = results["품질평가보고서"]
        self.assertEqual(report_quality_result.raw_detail_json["project_number_count"], 6)
        self.assertEqual(len(report_quality_result.raw_detail_json["quality_value_check"]["actual_values"]), 32)
        for result in (agreement_result, feature_result, plan_result, report_result):
            self.assertEqual(len(result.raw_detail_json["artifacts"]), 1)
            self.assertTrue(
                (artifact_dir / result.raw_detail_json["artifacts"][0]["relative_path"]).is_file()
            )
        self.assertEqual(len(checklist_result.raw_detail_json["artifacts"]), 1)
        self.assertTrue(
            (artifact_dir / checklist_result.raw_detail_json["artifacts"][0]["relative_path"]).is_file()
        )
        test_record_result = results["시험기록서"]
        test_record_artifact = test_record_result.raw_detail_json["artifacts"][0]
        self.assertFalse(test_record_artifact["download"])
        self.assertEqual(test_record_artifact["content_type"], "image/png")
        self.assertTrue(
            (artifact_dir / test_record_artifact["relative_path"]).is_file()
        )
        with self.settings(DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir):
            artifact_response = rule_result_artifact(
                self.factory.get(f"/api/rule-results/{report_result.id}/artifacts/pdf_first_page/"),
                report_result.id,
                "pdf_first_page",
            )
        artifact_bytes = b"".join(artifact_response.streaming_content)
        self.assertEqual(artifact_response.status_code, 200)
        self.assertEqual(artifact_response["Content-Type"], "image/png")
        self.assertTrue(artifact_bytes.startswith(b"\x89PNG"))
        with self.settings(DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir):
            agreement_artifact_response = rule_result_artifact(
                self.factory.get(f"/api/rule-results/{agreement_result.id}/artifacts/pdf_first_page/"),
                agreement_result.id,
                "pdf_first_page",
            )
        agreement_artifact_bytes = b"".join(agreement_artifact_response.streaming_content)
        self.assertEqual(agreement_artifact_response.status_code, 200)
        self.assertEqual(agreement_artifact_response["Content-Type"], "image/png")
        self.assertTrue(agreement_artifact_bytes.startswith(b"\x89PNG"))
        with self.settings(DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir):
            feature_artifact_response = rule_result_artifact(
                self.factory.get(f"/api/rule-results/{feature_result.id}/artifacts/feature_list_area/"),
                feature_result.id,
                "feature_list_area",
            )
        feature_artifact_bytes = b"".join(feature_artifact_response.streaming_content)
        self.assertEqual(feature_artifact_response.status_code, 200)
        self.assertEqual(feature_artifact_response["Content-Type"], "image/png")
        self.assertTrue(feature_artifact_bytes.startswith(b"\x89PNG"))
        with self.settings(DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir):
            checklist_artifact_response = rule_result_artifact(
                self.factory.get(f"/api/rule-results/{checklist_result.id}/artifacts/pdf_first_page/"),
                checklist_result.id,
                "pdf_first_page",
            )
        checklist_artifact_bytes = b"".join(checklist_artifact_response.streaming_content)
        self.assertEqual(checklist_artifact_response.status_code, 200)
        self.assertEqual(checklist_artifact_response["Content-Type"], "image/png")
        self.assertTrue(checklist_artifact_bytes.startswith(b"\x89PNG"))
        results_response = job_project_results(
            self.factory.get(f"/api/job-projects/{project.id}/results/"),
            project.id,
        )
        results_payload = json.loads(results_response.content.decode("utf-8"))
        report_payload = next(
            item for item in results_payload["items"]
            if item["rule_name"] == "시험성적서(PDF)"
        )
        self.assertEqual(report_payload["artifacts"][0]["id"], "pdf_first_page")
        self.assertNotIn("relative_path", report_payload["artifacts"][0])
        self.assertNotIn("relative_path", report_payload["raw_detail"]["artifacts"][0])
        agreement_payload = next(
            item for item in results_payload["items"]
            if item["rule_name"] == "합의서(PDF)"
        )
        feature_payload = next(
            item for item in results_payload["items"]
            if item["rule_name"] == "기능리스트"
        )
        self.assertEqual(agreement_payload["artifacts"][0]["label"], "합의서 1페이지")
        self.assertEqual(feature_payload["artifacts"][0]["id"], "feature_list_area")

    def _write_valid_rawdata_zip(self, rawdata_zip_path):
        with zipfile.ZipFile(rawdata_zip_path, "w") as archive:
            archive.writestr("결함/raw.txt", b"defect")
            archive.writestr("보안/1차/raw.txt", b"security")
            archive.writestr("보안/2차/raw.txt", b"security")
            archive.writestr("성능/1차/raw.txt", b"performance")
            archive.writestr("성능/2차/raw.txt", b"performance")
            for folder_name in ("최초정상", "최종정상"):
                for index in range(5):
                    info = zipfile.ZipInfo(
                        f"3.설계/제품스크린샷/{folder_name}/image-{index}.png",
                        date_time=(2026, 5, 20, 12, 0, 0),
                    )
                    archive.writestr(info, b"image")

    def _rawdata_only_project(self, project_dir):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        return DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={
                "project_number": "TTA-26-00010",
                "company": "에이치소프트",
                "product": "테스트제품 v1.0",
                "pl": "김준수",
                "wd": "10",
                "신청일": "2026.05.02.",
                "계약일": "2026.05.03.",
                "인증일자": "2026.06.01.",
            },
        )

    def test_rawdata_rules_run_when_only_rawdata_zip_exists(self):
        project_dir = Path(self.temp_dir.name) / "rawdata_only"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference_rawdata_only.db"
        self._create_master_reference_db(master_db_path)
        self._write_valid_rawdata_zip(project_dir / "raw_data.zip")

        call_command("seed_download_review_rules", "--only-real", "--enable", stdout=StringIO())
        project = self._rawdata_only_project(project_dir)
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")

        artifact_dir = Path(self.temp_dir.name) / "artifacts_rawdata_only"
        with self.settings(
            DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path,
            DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir,
        ):
            outcome = run_download_inspection(project, verify_result, {})

        results = {
            result.rule_name: result
            for result in DownloadReviewRuleResult.objects.filter(job_project=project)
        }
        self.assertTrue(verify_result.success)
        self.assertFalse(verify_result.has_project_number_files)
        self.assertEqual(outcome.artifact_results["최초/최종형상RawData"], "O")
        self.assertEqual(outcome.artifact_results["1차/2차/성능/보안RawData"], "O")
        self.assertEqual(outcome.artifact_results["계약서"], "X")
        self.assertEqual(results["최초/최종형상RawData"].status, DownloadReviewRuleStatus.PASS)
        self.assertEqual(results["1차/2차/성능/보안RawData"].status, DownloadReviewRuleStatus.PASS)

    def test_rawdata_rules_continue_when_submission_zip_is_unreadable(self):
        project_dir = Path(self.temp_dir.name) / "corrupt_submission_with_rawdata"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference_corrupt_submission.db"
        self._create_master_reference_db(master_db_path)
        (project_dir / "TTA-26-00010.zip").write_bytes(b"not a zip")
        self._write_valid_rawdata_zip(project_dir / "TTA-26-00010 raw-data.zip")

        call_command("seed_download_review_rules", "--only-real", "--enable", stdout=StringIO())
        project = self._rawdata_only_project(project_dir)
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")

        artifact_dir = Path(self.temp_dir.name) / "artifacts_corrupt_submission"
        with self.settings(
            DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path,
            DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir,
        ):
            outcome = run_download_inspection(project, verify_result, {})

        results = {
            result.rule_name: result
            for result in DownloadReviewRuleResult.objects.filter(job_project=project)
        }
        self.assertTrue(verify_result.success)
        self.assertEqual(outcome.artifact_results["최초/최종형상RawData"], "O")
        self.assertEqual(outcome.artifact_results["1차/2차/성능/보안RawData"], "O")
        self.assertEqual(results["최초/최종형상RawData"].status, DownloadReviewRuleStatus.PASS)
        self.assertEqual(results["1차/2차/성능/보안RawData"].status, DownloadReviewRuleStatus.PASS)
        self.assertTrue(getattr(verify_result, "_inspection_zip_errors"))

    def test_image_screenshot_date_failure_lists_period_dates_and_count(self):
        project_dir = Path(self.temp_dir.name) / "downloads"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference.db"
        self._create_master_reference_db(master_db_path)
        zip_path = project_dir / "TTA-26-00010.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass
        rawdata_zip_path = project_dir / "TTA-26-00010 rawdata.zip"
        with zipfile.ZipFile(rawdata_zip_path, "w") as archive:
            for folder_name, date_time in (
                ("최초형상", (2026, 4, 30, 12, 0, 0)),
                ("최종형상", (2026, 6, 1, 12, 0, 0)),
            ):
                for index in range(5):
                    info = zipfile.ZipInfo(
                        f"3.설계/제품스크린샷/{folder_name}/image-{index}.png",
                        date_time=date_time,
                    )
                    archive.writestr(info, b"image")

        DownloadReviewRule.objects.create(
            code="artifact_8",
            name="최초/최종형상RawData",
            rule_type="image_screenshot_folder_date_check",
            target_file_type="any",
            enabled=True,
            sort_order=80,
            config_json={
                "artifact_column": "최초/최종형상RawData",
                "folder_keyword_chain": ["설계"],
                "min_images_per_folder": 5,
                "required_candidate_folder_count": 2,
            },
        )
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={"project_number": "TTA-26-00010"},
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")

        with self.settings(DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path):
            outcome = run_download_inspection(project, verify_result, {})

        result = DownloadReviewRuleResult.objects.get(
            job_project=project,
            rule_name="최초/최종형상RawData",
        )
        message = "시험기간은 2026.05.01.~2026.05.31.인데 수정일자가 2026.04.30. 또는 2026.06.01.인 이미지가 10개 존재함"
        self.assertEqual(outcome.failed_count, 1)
        self.assertEqual(result.status, DownloadReviewRuleStatus.FAIL)
        self.assertEqual(result.message, message)
        self.assertEqual(result.actual, message)
        self.assertEqual(result.raw_detail_json["out_of_range_date_counts"], {
            "2026.04.30.": 5,
            "2026.06.01.": 5,
        })

    def test_defect_report_count_mismatch_uses_test_report_message(self):
        project_dir = Path(self.temp_dir.name) / "downloads"
        project_dir.mkdir(parents=True)
        zip_path = project_dir / "TTA-26-00010.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험성적서.docx",
                _docx_bytes(
                    tables=[
                        [["결함리포트 송부 1차: 2026.05.10 2차: 2026.05.20"]],
                    ],
                ),
            )
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험성적서.pdf",
                _pdf_bytes(["TTA-26-00010 시험성적서"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v1.0.xlsx",
                _defect_report_xlsx("TTA-26-00010", ["1차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v2.0.xlsx",
                _defect_report_xlsx("TTA-26-00010", ["1차 결함리포트", "2차 결함리포트"]),
            )

        DownloadReviewRule.objects.create(
            code="artifact_13",
            name="시험성적서(PDF)",
            rule_type="test_report_document_check",
            target_file_type="any",
            enabled=True,
            sort_order=95,
            config_json={
                "artifact_column": "시험성적서(PDF)",
                "folder_keyword_chain": ["시험", "종료"],
                "filename_keywords": ["시험성적서", "{project_number}"],
                "required_files": [
                    {"extensions": [".docx"], "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "spec_marker": "<세부사양>",
                "pdf_artifact_label": "시험성적서 1페이지",
            },
        )
        DownloadReviewRule.objects.create(
            code="artifact_10",
            name="결함리포트",
            rule_type="defect_report_check",
            target_file_type="any",
            enabled=True,
            sort_order=100,
            config_json={
                "artifact_column": "결함리포트",
                "folder_keyword_chain": ["수행"],
                "filename_keywords": ["결함리포트", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "count_mismatch_message": "시험성적서의 결함 차수와 결함리포트 개수가 다름",
            },
        )
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={"project_number": "TTA-26-00010"},
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")
        artifact_dir = Path(self.temp_dir.name) / "artifacts"

        with self.settings(DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir):
            outcome = run_download_inspection(project, verify_result, {})

        result = DownloadReviewRuleResult.objects.get(job_project=project, rule_name="결함리포트")
        self.assertEqual(outcome.failed_count, 1)
        self.assertEqual(result.status, DownloadReviewRuleStatus.FAIL)
        self.assertEqual(result.message, "시험성적서의 결함 차수와 결함리포트 개수가 다름")
        self.assertEqual(result.actual, "결함리포트 Excel 파일 2개")

    def test_defect_report_dates_accept_split_title_and_report_date_cells(self):
        project_dir = Path(self.temp_dir.name) / "downloads"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference.db"
        self._create_master_reference_db(master_db_path)
        zip_path = project_dir / "TTA-26-00010.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v1.0.xlsx",
                _defect_report_xlsx_split_title("TTA-26-00010", ["1차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v2.0.xlsx",
                _defect_report_xlsx_split_title("TTA-26-00010", ["1차 결함리포트", "2차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v3.0.xlsx",
                _defect_report_xlsx_split_title(
                    "TTA-26-00010",
                    ["1차 결함리포트", "2차 결함리포트", "최종결함리포트", "시험분석자료"],
                ),
            )
            archive.writestr(
                "6.시험/다.종료/TTA-26-00010 시험성적서.docx",
                _docx_bytes(
                    tables=[
                        [["결함리포트 송부 1차: 2026.04.14 2차: 2026.04.20"]],
                    ],
                ),
            )
            archive.writestr(
                "6.시험/다.종료/TTA-26-00010 시험성적서.pdf",
                _pdf_bytes(["TTA-26-00010 시험성적서"]),
            )

        DownloadReviewRule.objects.create(
            code="artifact_13",
            name="시험성적서(PDF)",
            rule_type="test_report_document_check",
            target_file_type="any",
            enabled=True,
            sort_order=95,
            config_json={
                "artifact_column": "시험성적서(PDF)",
                "folder_keyword_chain": ["시험", "종료"],
                "filename_keywords": ["시험성적서", "{project_number}"],
                "required_files": [
                    {"extensions": [".docx"], "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "spec_marker": "<일반사항>",
                "pdf_artifact_label": "시험성적서 1페이지",
            },
        )
        DownloadReviewRule.objects.create(
            code="artifact_10",
            name="결함리포트",
            rule_type="defect_report_check",
            target_file_type="any",
            enabled=True,
            sort_order=100,
            config_json={
                "artifact_column": "결함리포트",
                "folder_keyword_chain": ["수행"],
                "filename_keywords": ["결함리포트", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "count_mismatch_message": "시험성적서의 결함 차수와 결함리포트 개수가 다름",
                "report_date_message": "프로젝트 번호, 결함 차시, 보고일자 중 잘못된 값이 작성됨",
            },
        )
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={"project_number": "TTA-26-00010"},
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")
        artifact_dir = Path(self.temp_dir.name) / "artifacts"

        with self.settings(
            DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path,
            DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir,
        ):
            run_download_inspection(project, verify_result, {})

        result = DownloadReviewRuleResult.objects.get(job_project=project, rule_name="결함리포트")
        self.assertEqual(result.status, DownloadReviewRuleStatus.PASS, result.raw_detail_json["report_date_checks"])
        self.assertEqual(result.raw_detail_json["report_date_checks"][0]["sheet_text"], "1차 결함리포트")
        self.assertEqual(result.raw_detail_json["report_date_checks"][0]["actual_date"], "2026.04.14.")

    def test_defect_report_variables_are_kept_when_print_text_check_fails(self):
        project_dir = Path(self.temp_dir.name) / "downloads"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference.db"
        self._create_master_reference_db(master_db_path)
        zip_path = project_dir / "TTA-26-00010.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "4.시험/나.설계/TTA-26-00010 테스트케이스.xlsx",
                _test_case_xlsx("TTA-26-00010", pl="김준호"),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v1.0.xlsx",
                _defect_report_xlsx("TTA-26-00010", ["1차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v2.0.xlsx",
                _defect_report_xlsx("TTA-26-00010", ["1차 결함리포트", "2차 결함리포트"]),
            )
            archive.writestr(
                "5.수행/TTA-26-00010 결함리포트 v3.0.xlsx",
                _defect_report_xlsx(
                    "TTA-26-00010",
                    ["1차 결함리포트", "2차 결함리포트", "최종결함리포트", "시험분석자료"],
                    footer="소프트웨어시험인증연구소",
                ),
            )
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험성적서.docx",
                _docx_bytes(
                    tables=[
                        [["결함리포트 송부 1차: 2026.05.10 2차: 2026.05.20"]],
                    ],
                ),
            )
            archive.writestr(
                "6.시험/나.종료/TTA-26-00010 시험성적서.pdf",
                _pdf_bytes(["TTA-26-00010 시험성적서"]),
            )

        DownloadReviewRule.objects.create(
            code="artifact_13",
            name="시험성적서(PDF)",
            rule_type="test_report_document_check",
            target_file_type="any",
            enabled=True,
            sort_order=95,
            config_json={
                "artifact_column": "시험성적서(PDF)",
                "folder_keyword_chain": ["시험", "종료"],
                "filename_keywords": ["시험성적서", "{project_number}"],
                "required_files": [
                    {"extensions": [".docx"], "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "spec_marker": "<세부사양>",
                "pdf_artifact_label": "시험성적서 1페이지",
            },
        )
        DownloadReviewRule.objects.create(
            code="artifact_10",
            name="결함리포트",
            rule_type="defect_report_check",
            target_file_type="any",
            enabled=True,
            sort_order=100,
            config_json={
                "artifact_column": "결함리포트",
                "folder_keyword_chain": ["수행"],
                "filename_keywords": ["결함리포트", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "version_pattern": r"(?i)v(\d+)\.0",
                "forbidden_footer_terms": [
                    {
                        "text": "소프트웨어시험인증연구소",
                        "message": "결함리포트 바닥글에 '소프트웨어시험인증연구소'라는 단어가 잘못 작성됨",
                    },
                ],
            },
        )
        DownloadReviewRule.objects.create(
            code="artifact_9",
            name="테스트케이스",
            rule_type="test_case_check",
            target_file_type="any",
            enabled=True,
            sort_order=110,
            config_json={
                "artifact_column": "테스트케이스",
                "folder_keyword_chain": ["설계"],
                "filename_keywords": ["테스트케이스", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "exact_count": 1,
                "title_text": "{project_number} 테스트케이스",
                "author_label": "작성자:",
                "reviewer_label": "검토자:",
                "reviewer_expected": "김진영",
                "date_text": "작성일: {시작일} ~ {종료일}",
                "result_header": "상세 테스트 결과",
                "residual_message": "잔여 결함이 작성되지 않음",
            },
        )
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={
                "project_number": "TTA-26-00010",
                "product": "테스트제품 v1.0",
                "pl": "김준호",
            },
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")
        artifact_dir = Path(self.temp_dir.name) / "artifacts"

        with self.settings(
            DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path,
            DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir,
        ):
            outcome = run_download_inspection(project, verify_result, {})

        results = {
            result.rule_name: result
            for result in DownloadReviewRuleResult.objects.filter(job_project=project)
        }
        defect_result = results["결함리포트"]
        test_case_result = results["테스트케이스"]

        self.assertEqual(outcome.failed_count, 1)
        self.assertEqual(defect_result.status, DownloadReviewRuleStatus.FAIL)
        self.assertEqual(defect_result.raw_detail_json["variables"]["잔여결함수"], 2)
        self.assertEqual(defect_result.raw_detail_json["variables"]["H"], "3")
        self.assertEqual(defect_result.raw_detail_json["variables"]["R"], "7")
        self.assertEqual(test_case_result.status, DownloadReviewRuleStatus.PASS)
        self.assertEqual(test_case_result.raw_detail_json["residual_defect_check"]["expected_count"], 2)
        self.assertEqual(get_rule_output_variables(project)["잔여결함수"], 2)

    def test_quality_report_still_uses_quality_values_when_quality_table_score_compare_fails(self):
        project_dir = Path(self.temp_dir.name) / "downloads"
        project_dir.mkdir(parents=True)
        master_db_path = Path(self.temp_dir.name) / "reference.db"
        self._create_master_reference_db(master_db_path)
        zip_path = project_dir / "TTA-26-00010.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "4.시험/나.설계/TTA-26-00010 점검표.xlsx",
                _inspection_checklist_xlsx("TTA-26-00010", pl="김준호", wd="10", high="", before=""),
            )
            archive.writestr(
                "4.시험/나.설계/TTA-26-00010 점검표.pdf",
                _pdf_bytes(["TTA-26-00010 점검표"]),
            )
            archive.writestr(
                "6.시험/인증관련/TTA-26-00010 품질검사표.xlsx",
                _quality_inspection_table_xlsx("TTA-26-00010", score_overrides={21: "NA"}),
            )
            archive.writestr(
                "6.시험/인증관련/TTA-26-00010 품질평가보고서.docx",
                _quality_evaluation_report_docx("TTA-26-00010"),
            )

        call_command("seed_download_review_rules", "--only-real", "--enable", stdout=StringIO())
        DownloadReviewRule.objects.exclude(
            name__in=["점검표(PDF)", "품질검사표", "품질평가보고서"]
        ).update(enabled=False)
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.RUNNING,
            requested_project_count=1,
            selected_projects_json=["TTA-26-00010"],
        )
        project = DownloadReviewProject.objects.create(
            job=job,
            project_number="TTA-26-00010",
            download_dir=str(project_dir),
            ecm_row_json={
                "project_number": "TTA-26-00010",
                "company": "에이치소프트",
                "product": "테스트제품 v1.0",
                "pl": "김준호",
                "wd": "10",
                "request_date": "2026.05.02.",
                "contract_date": "2026.05.03.",
                "cert_date": "2026.06.01.",
            },
        )
        verify_result = verify_downloaded_files(str(project_dir), "TTA-26-00010")
        artifact_dir = Path(self.temp_dir.name) / "artifacts"

        with self.settings(
            DOWNLOAD_REVIEW_REFERENCE_MASTER_DB_PATH=master_db_path,
            DOWNLOAD_REVIEW_ARTIFACT_DIR=artifact_dir,
        ):
            outcome = run_download_inspection(project, verify_result, {})

        results = {
            result.rule_name: result
            for result in DownloadReviewRuleResult.objects.filter(job_project=project)
        }
        quality_table_result = results["품질검사표"]
        quality_report_result = results["품질평가보고서"]

        self.assertEqual(outcome.failed_count, 1)
        self.assertEqual(quality_table_result.status, DownloadReviewRuleStatus.FAIL)
        self.assertEqual(
            quality_table_result.message,
            "점검표와 품질검사표의 품질부특성 값이 총 84개의 값 중에 1개의 값이 다름",
        )
        self.assertEqual(quality_table_result.raw_detail_json["score_compare"]["total_count"], 84)
        self.assertEqual(quality_table_result.raw_detail_json["score_compare"]["mismatch_count"], 1)
        self.assertEqual(len(quality_table_result.raw_detail_json["variables"]["품질부특성측정값"]), 32)
        self.assertNotIn("quality-27", quality_table_result.raw_detail_json["variables"]["품질부특성측정값"])
        self.assertEqual(quality_report_result.status, DownloadReviewRuleStatus.PASS)
        self.assertTrue(quality_report_result.raw_detail_json["quality_value_check"]["passed"])
        self.assertEqual(len(quality_report_result.raw_detail_json["quality_value_check"]["actual_values"]), 32)
        self.assertIn("품질부특성측정값", get_rule_output_variables(project))

    def test_dry_run_worker_completes_job_with_mixed_project_results(self):
        job = DownloadReviewJob.objects.create(
            status=DownloadReviewJobStatus.QUEUED,
            requested_project_count=3,
            selected_projects_json=["TTA-26-00010", "TTA-26-00011", "TTA-26-00012"],
            progress_message="대기열 등록 완료",
        )
        DownloadReviewProject.objects.bulk_create(
            [
                DownloadReviewProject(
                    job=job,
                    project_number="TTA-26-00010",
                    ecm_row_json={"project_number": "TTA-26-00010", "company": "에이치소프트"},
                ),
                DownloadReviewProject(
                    job=job,
                    project_number="TTA-26-00011",
                    ecm_row_json={"project_number": "TTA-26-00011", "company": "브릿지웨어"},
                ),
                DownloadReviewProject(
                    job=job,
                    project_number="TTA-26-00012",
                    ecm_row_json={"project_number": "TTA-26-00012", "company": "넥스트랩"},
                ),
            ]
        )

        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            result = run_worker_once(dry_run=True)
        job.refresh_from_db()
        job_projects = list(job.projects.order_by("project_number"))
        reference_rows = self._reference_rows(
            ["TTA-26-00010", "TTA-26-00011", "TTA-26-00012"],
            ["점검결과", "점검날짜", "회사명", "계약서", "시험성적서(PDF)"],
        )
        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            projects_response = projects(
                self.factory.get("/api/projects/", {"project_number": "TTA-26-00010"}),
            )
        projects_data = json.loads(projects_response.content.decode("utf-8"))

        self.assertTrue(result.processed)
        self.assertEqual(result.status, "completed")
        self.assertEqual(job.status, DownloadReviewJobStatus.COMPLETED)
        self.assertEqual(job.completed_project_count, 2)
        self.assertEqual(job.failed_project_count, 1)
        self.assertEqual(job_projects[0].review_status, DownloadReviewProjectReviewStatus.COMPLETED)
        self.assertEqual(job_projects[1].review_status, DownloadReviewProjectReviewStatus.NEEDS_FIX)
        self.assertEqual(job_projects[2].review_status, DownloadReviewProjectReviewStatus.HELD)
        self.assertEqual(DownloadReviewRuleResult.objects.filter(job_project=job_projects[0]).count(), 30)
        self.assertEqual(
            DownloadReviewRuleResult.objects.filter(
                job_project=job_projects[1],
                status=DownloadReviewRuleStatus.FAIL,
            ).count(),
            1,
        )
        self.assertEqual(DownloadReviewRuleResult.objects.filter(job_project=job_projects[2]).count(), 0)
        self.assertEqual(reference_rows["TTA-26-00010"]["점검결과"], "O")
        self.assertEqual(reference_rows["TTA-26-00010"]["회사명"], "에이치소프트")
        self.assertEqual(reference_rows["TTA-26-00010"]["계약서"], "O")
        self.assertEqual(reference_rows["TTA-26-00010"]["시험성적서(PDF)"], "O")
        self.assertNotEqual(reference_rows["TTA-26-00010"]["점검날짜"], "")
        self.assertFalse(projects_data["items"][0]["selectable"])
        self.assertEqual(reference_rows["TTA-26-00011"]["점검결과"], "X")
        self.assertEqual(reference_rows["TTA-26-00011"]["시험성적서(PDF)"], "X")
        self.assertEqual(reference_rows["TTA-26-00012"]["점검결과"], "")
        self.assertEqual(reference_rows["TTA-26-00012"]["계약서"], "")

    def test_write_back_rejects_non_review_columns(self):
        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            with self.assertRaises(ReferenceQueryError):
                write_project_review_result(
                    "TTA-26-00010",
                    "완료",
                    artifact_results={"회사명": "변조된 회사명"},
                )

        row = self._reference_rows(["TTA-26-00010"], ["점검결과", "회사명"])["TTA-26-00010"]
        self.assertEqual(row["점검결과"], "")
        self.assertEqual(row["회사명"], "에이치소프트")

    def test_write_back_rejects_missing_db_without_creating_file(self):
        missing_db_path = Path(self.temp_dir.name) / "missing.db"

        with self.settings(REFERENCE_DB_PATH=missing_db_path, REFERENCE_DB_TABLE="ecm_list"):
            with self.assertRaises(ReferenceDbMissing):
                write_project_review_result("TTA-26-00010", "완료")

        self.assertFalse(missing_db_path.exists())

    def test_write_back_rejects_duplicate_project_numbers_and_rolls_back(self):
        conn = sqlite3.connect(self.reference_db_path)
        try:
            conn.execute(
                """
                INSERT INTO ecm_list (
                    "프로젝트번호",
                    "인증일자",
                    "회사명",
                    "제품명",
                    "시험PL",
                    "점검결과",
                    "점검날짜"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "TTA-26-00010",
                    "05/13",
                    "에이치소프트 복제",
                    "SecureFlow 2.1",
                    "김준호",
                    "",
                    "",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            with self.assertRaises(ReferenceDbError):
                write_project_review_result("TTA-26-00010", "완료")

        rows = self._reference_rows_by_number("TTA-26-00010", ["점검결과"])
        self.assertEqual([row["점검결과"] for row in rows], ["", ""])

    def test_write_back_accepts_failed_review_result(self):
        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            result = write_project_review_result("TTA-26-00010", "실패")
            response = projects(self.factory.get("/api/projects/", {"project_number": "TTA-26-00010"}))

        row = self._reference_rows(["TTA-26-00010"], ["점검결과"])["TTA-26-00010"]
        data = json.loads(response.content.decode("utf-8"))

        self.assertEqual(result["updated_columns"], ["점검결과"])
        self.assertEqual(row["점검결과"], "실패")
        self.assertEqual(data["items"][0]["review"], "실패")

    def test_write_back_succeeds_without_optional_inspection_date_column(self):
        no_date_db_path = Path(self.temp_dir.name) / "no_date.db"
        self._create_reference_db_without_inspection_date(no_date_db_path)

        with self.settings(REFERENCE_DB_PATH=no_date_db_path, REFERENCE_DB_TABLE="ecm_list"):
            result = write_project_review_result(
                "TTA-26-09999",
                "완료",
                artifact_results={"계약서": "정상"},
                inspected_at="2026.05.12 20:00",
            )

        conn = sqlite3.connect(no_date_db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                'SELECT "점검결과", "계약서" FROM ecm_list WHERE "프로젝트번호" = ?',
                ["TTA-26-09999"],
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(result["updated_columns"], ["점검결과", "계약서"])
        self.assertEqual(row["점검결과"], "O")
        self.assertEqual(row["계약서"], "O")

    def _post_job(self, project_numbers, *, center=None):
        payload = {"project_numbers": project_numbers}
        if center:
            payload["center"] = center
        request = self.factory.post(
            "/api/jobs/",
            data=json.dumps(payload),
            content_type="application/json",
            REMOTE_ADDR="127.0.0.1",
        )
        with self.settings(
            REFERENCE_DB_PATH=self.reference_db_path,
            REFERENCE_DB_PATH_2=self.reference_db_path_2,
            REFERENCE_DB_TABLE="ecm_list",
        ):
            return jobs(request)

    def _create_reference_db(self):
        conn = sqlite3.connect(self.reference_db_path)
        try:
            artifact_columns_sql = ",\n".join(
                f'"{column}" TEXT DEFAULT \'\''
                for column in ARTIFACT_REVIEW_COLUMNS
            )
            conn.execute(
                f"""
                CREATE TABLE ecm_list (
                    "프로젝트번호" TEXT,
                    "인증일자" TEXT,
                    "회사명" TEXT,
                    "제품명" TEXT,
                    "시험PL" TEXT,
                    "점검결과" TEXT,
                    "점검날짜" TEXT,
                    {artifact_columns_sql}
                )
                """
            )
            conn.executemany(
                """
                INSERT INTO ecm_list (
                    "프로젝트번호",
                    "인증일자",
                    "회사명",
                    "제품명",
                    "시험PL",
                    "점검결과",
                    "점검날짜"
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "TTA-26-00009",
                        "05/12",
                        "우리데이터 주식회사",
                        "우리데이터클리닝 V1.0",
                        "박지훈",
                        "O",
                        "2026.05.12 20:30",
                    ),
                    (
                        "TTA-26-00010",
                        "05/13",
                        "에이치소프트",
                        "SecureFlow 2.1",
                        "김준호",
                        "",
                        "",
                    ),
                    (
                        "TTA-26-00011",
                        "05/14",
                        "브릿지웨어",
                        "BridgeHub",
                        "박지훈",
                        "",
                        "",
                    ),
                    (
                        "TTA-26-00012",
                        "05/15",
                        "넥스트랩",
                        "NextLab QA Suite",
                        "최유진",
                        "",
                        "",
                    ),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def _create_master_reference_db(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE sw_data (
                    "시험번호" TEXT,
                    "시작일자" TEXT,
                    "종료일자" TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO sw_data ("시험번호", "시작일자", "종료일자")
                VALUES (?, ?, ?)
                """,
                ("TTA-26-00010", "2026-05-01", "2026-05-31"),
            )
            conn.commit()
        finally:
            conn.close()

    def _reference_rows(self, project_numbers, columns):
        conn = sqlite3.connect(self.reference_db_path)
        conn.row_factory = sqlite3.Row
        try:
            select_columns = ["프로젝트번호", *columns]
            placeholders = ", ".join("?" for _ in project_numbers)
            sql = (
                "SELECT "
                + ", ".join(f'"{column}"' for column in select_columns)
                + f' FROM ecm_list WHERE "프로젝트번호" IN ({placeholders})'
            )
            rows = conn.execute(sql, project_numbers).fetchall()
            return {
                row["프로젝트번호"]: {column: row[column] for column in columns}
                for row in rows
            }
        finally:
            conn.close()

    def _reference_rows_by_number(self, project_number, columns):
        conn = sqlite3.connect(self.reference_db_path)
        conn.row_factory = sqlite3.Row
        try:
            select_columns = ["프로젝트번호", *columns]
            sql = (
                "SELECT "
                + ", ".join(f'"{column}"' for column in select_columns)
                + ' FROM ecm_list WHERE "프로젝트번호" = ? ORDER BY rowid'
            )
            return [
                {column: row[column] for column in columns}
                for row in conn.execute(sql, [project_number]).fetchall()
            ]
        finally:
            conn.close()

    def _create_reference_db_without_inspection_date(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            artifact_columns_sql = ",\n".join(
                f'"{column}" TEXT DEFAULT \'\''
                for column in ARTIFACT_REVIEW_COLUMNS
            )
            conn.execute(
                f"""
                CREATE TABLE ecm_list (
                    "프로젝트번호" TEXT,
                    "인증일자" TEXT,
                    "회사명" TEXT,
                    "제품명" TEXT,
                    "시험PL" TEXT,
                    "점검결과" TEXT,
                    {artifact_columns_sql}
                )
                """
            )
            conn.execute(
                """
                INSERT INTO ecm_list (
                    "프로젝트번호",
                    "인증일자",
                    "회사명",
                    "제품명",
                    "시험PL",
                    "점검결과"
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("TTA-26-09999", "05/12", "옵션테스트", "NoDate", "박지훈", ""),
            )
            conn.commit()
        finally:
            conn.close()
