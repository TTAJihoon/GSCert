import csv
import io
import json
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.http import QueryDict
from asgiref.sync import async_to_sync
from django.test import AsyncRequestFactory, RequestFactory, SimpleTestCase, TestCase, override_settings

from main.models import DownloadReviewJob, KolasProject, ReferenceCenterPl, ReferenceProject
from main.utils import kolas_sheet
from main.views.init import kolas_review
from main.views.review import kolas_report_download as report
from main.views.review.ecm_download_review_jobs import (
    DownloadReviewJobRequestError,
    create_download_review_job,
    get_jobs_payload,
    parse_project_numbers,
)
from main.views.review.ecm_pl_assignment import apply_pl_assignment_changes, get_pl_assignment_payload
from main.views.review.ecm_reference_db import (
    ReferenceDbError,
    copy_reference_results_to_kolas,
    list_kolas_projects,
    write_project_review_result,
)
from main.views.review import kolas_report_cache as report_cache
from main.views.review.kolas_api import kolas_projects, kolas_report_download

HEADER = ["순번", "회사(제품)", "WD", "신청일", "계약일", "시작일", "종료\n예정일", "시험원", "프로젝트 번호", "상담자"]


def _round_2025_layout(committee, rows):
    """2025년 시트 서식: '일시' 행과 헤더 사이에 빈 줄이 2줄 더 있다."""
    out = [
        ["", "제25-59차 품질인증심의위원회"],
        ["가. 일시", committee],
        ["나. 장소", "TTA B1층 고객상담실"],
        ["다. 안건", "SW에 대한 품질인증심의"],
        [],
        [],
        HEADER,
    ]
    for index, (company, end, tester, number) in enumerate(rows, start=1):
        out.append([str(index), company, "10", "25/10/14,화", "25/10/13,월", "25/11/27,목", end, tester, number, "상담자"])
    out.append([])
    return out


def _round_2026_layout(committee, rows):
    """2026년 시트 서식: '일시' 3행 아래가 헤더."""
    out = [
        ["가. 일시", committee],
        ["나. 장소", "TTA B1층 고객상담실"],
        ["다. 안건", "SW에 대한 품질인증심의"],
        HEADER,
    ]
    for index, (company, end, tester, number) in enumerate(rows, start=1):
        out.append([str(index), company, "17", "26/05/28,목", "26/06/17,수", "26/08/28,금", end, tester, number, "상담자"])
    out.append([])
    return out


def _csv_text(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


CENTER_MAP = {"김진영": ("sangam", "상암"), "임우섭": ("bundang", "분당")}


class KolasSheetParserTests(SimpleTestCase):
    def test_reads_both_sheet_layouts_and_number_formats(self):
        rows = _round_2025_layout(
            "2025년 12월 29일(월)",
            [("(주)에이-제품A", "25/12/17,수", "김진영", "GS-C-25-0077")],
        ) + _round_2026_layout(
            "2026. 9. 28",
            [("㈜비-제품B", "26/09/21,월", "임우섭", "TTA-26-01716")],
        )

        parsed, warnings = kolas_sheet.parse_kolas_sheet(rows, gid="g", center_map=CENTER_MAP)

        self.assertEqual(warnings, [])
        by_number = {row.project_number: row for row in parsed}
        self.assertEqual(set(by_number), {"GS-C-25-0077", "TTA-26-01716"})
        self.assertEqual(by_number["GS-C-25-0077"].expected_end_on, date(2025, 12, 17))
        self.assertEqual(by_number["GS-C-25-0077"].cert_committee_date, date(2025, 12, 29))
        self.assertEqual(by_number["GS-C-25-0077"].center_code, "sangam")
        self.assertEqual(by_number["GS-C-25-0077"].company, "(주)에이")
        self.assertEqual(by_number["TTA-26-01716"].center_code, "bundang")
        self.assertEqual(by_number["TTA-26-01716"].cert_committee_date, date(2026, 9, 28))

    def test_round_without_header_is_reported_not_silently_dropped(self):
        rows = [["가. 일시", "2025년 12월 29일(월)"], ["나. 장소", "x"], [], ["1", "회사-제품", "", "", "", "", "25/12/17,수", "김진영", "GS-C-25-0077"]]

        parsed, warnings = kolas_sheet.parse_kolas_sheet(rows, gid="g", center_map=CENTER_MAP)

        self.assertEqual(parsed, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("헤더", warnings[0])

    def test_tester_cell_variants_resolve_to_assigned_pl(self):
        resolve = kolas_sheet.resolve_primary_tester
        self.assertEqual(resolve("황현후,김진영", {"김진영": 1}), "김진영")
        self.assertEqual(resolve("우수진.김진영", {"김진영": 1}), "김진영")
        self.assertEqual(resolve("장세헌(공공)", {}), "장세헌")
        self.assertEqual(resolve("", {}), "")

    def test_duplicate_numbers_keep_smaller_row_and_prefer_newer_sheet(self):
        def row(number, gid, row_no):
            return kolas_sheet.KolasSheetRow(
                project_number=number, cert_date="1/1", cert_committee_date=date(2025, 1, 1),
                company="", product="", wd="", request_date="", contract_date="", start_date="",
                expected_end_date="", expected_end_on=date(2025, 6, 1), pl="", primary_tester="",
                center_code="unknown", center_label="미분류", raw_company_product="",
                source_gid=gid, source_row_number=row_no,
            )

        sheet_2026 = [row("GS-A-25-0001", "2026", 50)]
        sheet_2025 = [row("GS-A-25-0001", "2025", 5), row("GS-A-25-0070", "2025", 638), row("GS-A-25-0070", "2025", 610)]

        merged, dropped = kolas_sheet.merge_sheets([sheet_2026, sheet_2025])

        chosen = {item.project_number: item for item in merged}
        self.assertEqual(chosen["GS-A-25-0001"].source_gid, "2026")
        self.assertEqual(chosen["GS-A-25-0070"].source_row_number, 610)
        self.assertEqual(len(dropped), 2)

    def test_filter_uses_expected_end_date_inclusive_and_reports_undated(self):
        def row(number, end):
            return kolas_sheet.KolasSheetRow(
                project_number=number, cert_date="", cert_committee_date=date(2026, 1, 1),
                company="", product="", wd="", request_date="", contract_date="", start_date="",
                expected_end_date="", expected_end_on=end, pl="", primary_tester="",
                center_code="unknown", center_label="", raw_company_product="",
                source_gid="g", source_row_number=1,
            )

        rows = [
            row("A", date(2025, 5, 14)), row("B", date(2026, 9, 23)),
            row("C", date(2025, 5, 13)), row("D", date(2026, 9, 24)), row("E", None),
        ]

        selected, undated = kolas_sheet.filter_by_expected_end(rows)

        self.assertEqual([item.project_number for item in selected], ["A", "B"])
        self.assertEqual([item.project_number for item in undated], ["E"])


class KolasDbTestCase(TestCase):
    databases = {"default", "workflow", "reference"}

    def _kolas(self, number, **overrides):
        fields = dict(
            project_number=number, center_code="sangam", center_label="상암", company="회사", product="제품",
            pl="김진영", primary_tester="김진영", expected_end_on=date(2025, 12, 1),
            cert_committee_date=date(2025, 12, 29), cert_date="12/29",
        )
        fields.update(overrides)
        return KolasProject.objects.using("reference").create(**fields)

    def _reference(self, number, **overrides):
        fields = dict(project_number=number, center_code="sangam", center_label="상암", company="회사", product="제품", pl="김진영")
        fields.update(overrides)
        return ReferenceProject.objects.using("reference").create(**fields)


class KolasSyncCommandTests(KolasDbTestCase):
    def _run_sync(self, rows_2026, rows_2025, **options):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_2026 = Path(temp_dir) / "2026.csv"
            path_2025 = Path(temp_dir) / "2025.csv"
            path_2026.write_text(_csv_text(rows_2026), encoding="utf-8")
            path_2025.write_text(_csv_text(rows_2025), encoding="utf-8")
            call_command(
                "sync_kolas_projects", csv_2026=str(path_2026), csv_2025=str(path_2025),
                stdout=io.StringIO(), **options,
            )

    def _sheets(self):
        rows_2026 = _round_2026_layout("2026. 9. 7", [
            ("회사B-제품B", "26/09/21,월", "김진영", "TTA-26-01716"),
            ("회사X-범위밖", "26/10/01,목", "김진영", "TTA-26-01800"),
        ])
        rows_2025 = _round_2025_layout("2025년 12월 29일(월)", [
            ("회사A-제품A", "25/12/17,수", "임우섭", "GS-C-25-0077"),
            ("회사Y-범위밖", "25/05/13,화", "임우섭", "GS-C-25-0001"),
        ])
        return rows_2026, rows_2025

    def test_sync_loads_only_expected_end_range_and_does_not_touch_reference_table(self):
        self._run_sync(*self._sheets())

        numbers = set(KolasProject.objects.using("reference").values_list("project_number", flat=True))
        self.assertEqual(numbers, {"TTA-26-01716", "GS-C-25-0077"})
        self.assertFalse(ReferenceProject.objects.using("reference").exists())
        row = KolasProject.objects.using("reference").get(project_number="GS-C-25-0077")
        self.assertEqual(row.center_code, "bundang")  # 시트의 '임우섭'은 기본 PL 목록상 분당
        self.assertEqual(row.expected_end_on, date(2025, 12, 17))

    def test_sync_copies_existing_reference_results_and_keeps_results_on_resync(self):
        self._reference(
            "GS-C-25-0077", review_result="O", inspection_date="2025.12.30 10:00",
            artifact_results_json={"계약서": "O"},
        )

        self._run_sync(*self._sheets())

        row = KolasProject.objects.using("reference").get(project_number="GS-C-25-0077")
        self.assertEqual(row.review_result, "O")
        self.assertEqual(row.inspection_date, "2025.12.30 10:00")
        self.assertEqual(row.artifact_results_json, {"계약서": "O"})
        untouched = KolasProject.objects.using("reference").get(project_number="TTA-26-01716")
        self.assertEqual(untouched.review_result, "")

        # KOLAS 에서 직접 점검한 결과는 재동기화로 지워지지 않는다.
        KolasProject.objects.using("reference").filter(project_number="TTA-26-01716").update(review_result="X")
        self._run_sync(*self._sheets())
        untouched.refresh_from_db(using="reference")
        self.assertEqual(untouched.review_result, "X")

    def test_stored_pl_assignment_is_used_for_center(self):
        ReferenceCenterPl.objects.using("reference").create(center_code="yeongnam", center_label="영남", name="임우섭")

        self._run_sync(*self._sheets())

        row = KolasProject.objects.using("reference").get(project_number="GS-C-25-0077")
        self.assertEqual(row.center_code, "yeongnam")

    def test_dry_run_changes_nothing(self):
        self._run_sync(*self._sheets(), dry_run=True)

        self.assertFalse(KolasProject.objects.using("reference").exists())


class KolasSharedResultTests(KolasDbTestCase):
    def test_result_written_to_both_when_project_exists_in_reference_db(self):
        self._reference("GS-A-25-0001", artifact_results_json={"계약서": "O"})
        self._kolas("GS-A-25-0001")

        write_project_review_result(
            "GS-A-25-0001", "O", artifact_results={"기능리스트": "X"},
            inspected_at=date(2026, 9, 1), center_code="sangam",
        )

        reference = ReferenceProject.objects.using("reference").get(project_number="GS-A-25-0001")
        kolas = KolasProject.objects.using("reference").get(project_number="GS-A-25-0001")
        for row in (reference, kolas):
            self.assertEqual(row.review_result, "O")
            self.assertEqual(row.artifact_results_json, {"계약서": "O", "기능리스트": "X"})
            self.assertEqual(row.inspection_date, "2026.09.01 00:00")

    def test_result_written_only_to_kolas_when_not_in_reference_db(self):
        self._kolas("GS-A-25-0002")

        write_project_review_result("GS-A-25-0002", "X", artifact_results={"계약서": "X"}, center_code="sangam")

        kolas = KolasProject.objects.using("reference").get(project_number="GS-A-25-0002")
        self.assertEqual(kolas.review_result, "X")
        self.assertEqual(kolas.artifact_results_json, {"계약서": "X"})
        self.assertFalse(ReferenceProject.objects.using("reference").filter(project_number="GS-A-25-0002").exists())

    def test_ecm_page_jobs_are_mirrored_to_kolas_row_but_never_create_one(self):
        self._reference("TTA-26-00001")
        self._kolas("TTA-26-00001")
        self._reference("TTA-26-00002")

        write_project_review_result("TTA-26-00001", "O", center_code="sangam")
        write_project_review_result("TTA-26-00002", "O", center_code="sangam")

        self.assertEqual(
            KolasProject.objects.using("reference").get(project_number="TTA-26-00001").review_result, "O"
        )
        self.assertFalse(KolasProject.objects.using("reference").filter(project_number="TTA-26-00002").exists())

    def test_missing_everywhere_raises(self):
        with self.assertRaises(ReferenceDbError):
            write_project_review_result("GS-A-25-9999", "O", center_code="sangam")

    def test_copy_skips_reference_rows_without_result(self):
        self._reference("GS-A-25-0003")  # 결과 없음
        self._kolas("GS-A-25-0003", review_result="X")

        copied = copy_reference_results_to_kolas()

        self.assertEqual(copied, 0)
        self.assertEqual(KolasProject.objects.using("reference").get(project_number="GS-A-25-0003").review_result, "X")


class KolasProjectsApiTests(KolasDbTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self._kolas("GS-A-25-0001", company="가나다")
        self._kolas("GS-A-25-0002", center_code="unknown", center_label="미분류", company="라마바")
        self._kolas("GS-A-25-0003", center_code="bundang", center_label="분당", review_result="O")
        self._reference("TTA-26-00001")  # 기존 목록은 KOLAS 목록에 보이지 않는다

    def _get(self, **params):
        response = kolas_projects(self.factory.get("/kolas/api/projects/", params, HTTP_HOST="testserver"))
        return response.status_code, json.loads(response.content)

    def test_lists_only_kolas_projects_for_center(self):
        status, payload = self._get(center="sangam")

        self.assertEqual(status, 200)
        self.assertEqual([item["project_number"] for item in payload["items"]], ["GS-A-25-0001"])

    def test_unassigned_center_is_listed(self):
        status, payload = self._get(center="unknown")

        self.assertEqual(status, 200)
        self.assertEqual([item["project_number"] for item in payload["items"]], ["GS-A-25-0002"])

    def test_completed_project_is_listed_but_not_job_selectable(self):
        _status, payload = self._get(center="bundang")

        item = payload["items"][0]
        self.assertEqual(item["review"], "완료")
        self.assertFalse(item["selectable"])

    def test_invalid_center_is_rejected(self):
        status, payload = self._get(center="nowhere")

        self.assertEqual(status, 400)
        self.assertFalse(payload["success"])

    def test_filters_apply(self):
        query = QueryDict("center=sangam&company=가나", mutable=False)
        self.assertEqual(len(list_kolas_projects(query)["items"]), 1)
        query = QueryDict("center=sangam&company=없음", mutable=False)
        self.assertEqual(list_kolas_projects(query)["items"], [])


class KolasJobTests(KolasDbTestCase):
    def test_kolas_job_uses_kolas_list_and_accepts_gs_numbers(self):
        self._kolas("GS-A-25-0001")

        payload = create_download_review_job({"center": "sangam", "project_numbers": ["GS-A-25-0001"], "source": "kolas"})

        job = DownloadReviewJob.objects.get(id=payload["job_id"])
        self.assertEqual(job.source, "kolas")
        self.assertEqual(job.projects.get().project_number, "GS-A-25-0001")

    def test_kolas_job_rejects_project_not_in_kolas_list(self):
        self._reference("TTA-26-00001")

        with self.assertRaises(DownloadReviewJobRequestError):
            create_download_review_job({"center": "sangam", "project_numbers": ["TTA-26-00001"], "source": "kolas"})

    def test_ecm_job_cannot_use_kolas_only_project(self):
        self._kolas("GS-A-25-0001")

        with self.assertRaises(DownloadReviewJobRequestError):
            create_download_review_job({"center": "sangam", "project_numbers": ["GS-A-25-0001"]})

    def test_unassigned_center_cannot_request_job(self):
        self._kolas("GS-A-25-0004", center_code="unknown")

        with self.assertRaises(DownloadReviewJobRequestError):
            create_download_review_job({"center": "unknown", "project_numbers": ["GS-A-25-0004"], "source": "kolas"})

    def test_job_lists_are_separated_by_source(self):
        self._kolas("GS-A-25-0001")
        self._reference("TTA-26-00001")
        kolas_job = create_download_review_job({"center": "sangam", "project_numbers": ["GS-A-25-0001"], "source": "kolas"})
        ecm_job = create_download_review_job({"center": "sangam", "project_numbers": ["TTA-26-00001"]})

        default_ids = {item["id"] for item in get_jobs_payload(QueryDict(""))["items"]}
        kolas_ids = {item["id"] for item in get_jobs_payload(QueryDict("source=kolas"))["items"]}

        self.assertEqual(default_ids, {ecm_job["job_id"]})
        self.assertEqual(kolas_ids, {kolas_job["job_id"]})

    def test_project_number_formats(self):
        numbers = parse_project_numbers({"project_numbers": ["TTA-26-00009", "GS-A-25-0077", "GS-C-23-0336"]})
        self.assertEqual(len(numbers), 3)
        with self.assertRaises(DownloadReviewJobRequestError):
            parse_project_numbers({"project_numbers": ["BAD-1"]})


class KolasPlAssignmentTests(KolasDbTestCase):
    def test_unassigned_pl_moves_in_both_lists_and_counts_follow_page(self):
        self._kolas("GS-A-25-0001", center_code="unknown", center_label="미분류", primary_tester="신규PL")
        self._kolas("GS-A-25-0002", center_code="unknown", center_label="미분류", primary_tester="신규PL")
        self._reference("TTA-26-00001", center_code="unknown", center_label="미분류", primary_tester="신규PL")

        before = get_pl_assignment_payload(kolas=True)
        self.assertEqual(before["assignments"]["unknown"], [{"name": "신규PL", "project_count": 2}])

        after = apply_pl_assignment_changes(
            [{"name": "신규PL", "from_center": "unknown", "to_center": "sangam"}], kolas=True,
        )

        self.assertEqual(after["moved_project_count"], 2)
        self.assertEqual(
            set(KolasProject.objects.using("reference").values_list("center_code", flat=True)), {"sangam"}
        )
        self.assertEqual(
            ReferenceProject.objects.using("reference").get(project_number="TTA-26-00001").center_code, "sangam"
        )


class _FakeClient:
    """ECM 없이 폴더 트리를 흉내 낸다. tree: {oid: {"folders": [(name, oid)], "files": [meta]}}"""

    def __init__(self, tree, project_folder=None, blobs=None):
        self.tree = tree
        self.project_folder = project_folder
        self.blobs = blobs or {}
        self.downloaded = []

    oid = staticmethod(lambda row: row.get("OID", ""))

    def login(self):
        return None

    def children(self, oid):
        return [{"name": name, "OID": child} for name, child in self.tree.get(oid, {}).get("folders", [])]

    def files(self, oid):
        return list(self.tree.get(oid, {}).get("files", []))

    def walk_files(self, oid, _rel=None):
        node = self.tree.get(oid, {})
        for meta in node.get("files", []):
            yield [], meta
        for _name, child in node.get("folders", []):
            yield from self.walk_files(child)

    def find_full_project_folder(self, test_no, cert_date="", center_code=""):
        return self.project_folder.get(test_no) if self.project_folder else None

    def download_bytes(self, meta):
        self.downloaded.append(meta["fileName"])
        return self.blobs[meta["fileName"]]


def _meta(name, size=0):
    return {"fileName": name, "fileOID": name, "storageFileID": name, "fileSize": size}


PDF_BYTES = b"%PDF-1.4 fake pdf!"
DOCX_BYTES = b"PK\x03\x04 fake docx"


class _TempCacheMixin:
    """결과서 저장소를 임시 폴더로 돌린다. 실제 서버 저장소를 건드리지 않는다."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.cache_dir = Path(self._tmp.name) / "kolas"
        override = override_settings(KOLAS_REPORT_CACHE_DIR=str(self.cache_dir))
        override.enable()
        self.addCleanup(override.disable)


class KolasReportDownloadTests(_TempCacheMixin, SimpleTestCase):
    def test_classify_report_files(self):
        classify = report.classify_report_file
        self.assertEqual(classify("GS-A-25-0077 시험성적서.docx"), "word")
        self.assertEqual(classify("시험성적서.DOC"), "word")
        self.assertEqual(classify("GS-A-25-0077 시험성적서.pdf"), "pdf")
        self.assertIsNone(classify("시험계획서.pdf"))
        self.assertIsNone(classify("시험성적서.xlsx"))

    def test_finds_reports_in_test_end_folder_before_falling_back(self):
        tree = {
            "P": {"folders": [("01 계약", "c"), ("05 시험", "t")], "files": [_meta("시험성적서_엉뚱한위치.pdf")]},
            "t": {"folders": [("진행", "t1"), ("종료", "t2")], "files": []},
            "t1": {"folders": [], "files": [_meta("시험성적서_진행중.docx")]},
            "t2": {"folders": [], "files": [_meta("시험성적서.docx"), _meta("시험성적서.pdf"), _meta("결함리포트.xlsx")]},
        }
        found = report.find_report_files(_FakeClient(tree), "P")
        self.assertEqual(sorted((kind, meta["fileName"]) for kind, meta in found),
                         [("pdf", "시험성적서.pdf"), ("word", "시험성적서.docx")])

    def test_falls_back_to_whole_project_folder(self):
        tree = {
            "P": {"folders": [("기타", "x")], "files": []},
            "x": {"folders": [], "files": [_meta("최종 시험성적서.pdf")]},
        }
        found = report.find_report_files(_FakeClient(tree), "P")
        self.assertEqual([(kind, meta["fileName"]) for kind, meta in found], [("pdf", "최종 시험성적서.pdf")])

    def test_zip_splits_word_and_pdf_and_records_missing(self):
        tree = {
            "P1": {"folders": [("시험", "t")], "files": []},
            "t": {"folders": [("종료", "e")], "files": []},
            "e": {"folders": [], "files": [_meta("GS-A-25-0077 시험성적서.docx"), _meta("GS-A-25-0077 시험성적서.pdf")]},
            "P2": {"folders": [], "files": []},
        }
        client = _FakeClient(
            tree,
            project_folder={
                "GS-A-25-0077": {"oid": "P1", "name": "GS-A-25-0077 회사"},
                "GS-A-25-0078": {"oid": "P2", "name": "GS-A-25-0078 회사"},
            },
            blobs={"GS-A-25-0077 시험성적서.docx": DOCX_BYTES, "GS-A-25-0077 시험성적서.pdf": PDF_BYTES},
        )
        pool = report._ClientPool(factory=lambda center: client)
        projects = [
            {"project_number": "GS-A-25-0077", "center_code": "sangam", "cert_date_full": "2025-12-29"},
            {"project_number": "GS-A-25-0078", "center_code": "sangam", "cert_date_full": "2025-12-29"},
            {"project_number": "GS-A-25-0079", "center_code": "unknown", "cert_date_full": ""},
        ]

        data = b"".join(report.iter_report_zip(projects, missing_numbers=["GS-A-25-0099"], pool=pool))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertIsNone(zf.testzip())
            names = set(zf.namelist())
            self.assertEqual(names, {
                "word/GS-A-25-0077 시험성적서.docx",
                "pdf/GS-A-25-0077 시험성적서.pdf",
                report.SUMMARY_NAME,
            })
            self.assertEqual(zf.read("word/GS-A-25-0077 시험성적서.docx"), DOCX_BYTES)
            summary = zf.read(report.SUMMARY_NAME).decode("utf-8-sig")
        self.assertIn("성공 프로젝트: 1건", summary)
        self.assertIn("GS-A-25-0078", summary)  # 폴더는 있으나 성적서 없음
        self.assertIn("GS-A-25-0079", summary)  # 폴더 자체를 못 찾음
        self.assertIn("GS-A-25-0099", summary)  # KOLAS 목록에 없음

    def test_name_without_project_number_gets_prefix_and_duplicates_are_unique(self):
        tree = {"P": {"folders": [], "files": [_meta("시험성적서.pdf")]}}
        client = _FakeClient(tree, {"GS-A-25-0077": {"oid": "P", "name": "x"}}, {"시험성적서.pdf": PDF_BYTES})
        pool = report._ClientPool(factory=lambda center: client)

        data = b"".join(report.iter_report_zip(
            [{"project_number": "GS-A-25-0077", "center_code": "sangam"}], pool=pool,
        ))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertIn("pdf/GS-A-25-0077_시험성적서.pdf", zf.namelist())

    def test_corrupted_file_is_reported_and_other_files_still_saved(self):
        tree = {"P": {"folders": [], "files": [_meta("A 시험성적서.pdf"), _meta("A 시험성적서.docx")]}}
        client = _FakeClient(tree, {"A": {"oid": "P", "name": "x"}}, {"A 시험성적서.pdf": b"not a pdf", "A 시험성적서.docx": DOCX_BYTES})
        pool = report._ClientPool(factory=lambda center: client)

        data = b"".join(report.iter_report_zip([{"project_number": "A", "center_code": "sangam"}], pool=pool))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            summary = zf.read(report.SUMMARY_NAME).decode("utf-8-sig")
        self.assertIn("word/A 시험성적서.docx", names)
        self.assertNotIn("pdf/A 시험성적서.pdf", names)
        self.assertIn("무결성", summary)

    def test_center_try_order_puts_project_center_first(self):
        self.assertEqual(report.center_try_order("sangam"), ["sangam", "bundang", "yeongnam"])
        self.assertEqual(report.center_try_order("unknown"), ["bundang", "sangam", "yeongnam"])

    def test_failing_center_login_falls_through_to_next_center(self):
        good = _FakeClient(
            {"P": {"folders": [], "files": [_meta("B 시험성적서.pdf")]}},
            {"B": {"oid": "P", "name": "x"}}, {"B 시험성적서.pdf": PDF_BYTES},
        )

        def factory(center):
            if center == "bundang":
                raise RuntimeError("자격증명 없음")
            return good

        pool = report._ClientPool(factory=factory)

        data = b"".join(report.iter_report_zip([{"project_number": "B", "center_code": "unknown"}], pool=pool))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertIn("pdf/B 시험성적서.pdf", zf.namelist())


class KolasReportServerStorageTests(_TempCacheMixin, SimpleTestCase):
    PROJECT = {"project_number": "GS-A-25-0077", "center_code": "sangam", "cert_date_full": "2025-12-29"}
    DOCX = "GS-A-25-0077 시험성적서.docx"
    PDF = "GS-A-25-0077 시험성적서.pdf"

    def _client(self, blobs=None):
        tree = {"P": {"folders": [], "files": [_meta(self.DOCX), _meta(self.PDF)]}}
        return _FakeClient(
            tree,
            {"GS-A-25-0077": {"oid": "P", "name": "GS-A-25-0077 회사"}},
            blobs or {self.DOCX: DOCX_BYTES, self.PDF: PDF_BYTES},
        )

    def _run(self, client, projects=None, **kwargs):
        calls = []

        def factory(center):
            calls.append(center)
            return client

        pool = report._ClientPool(factory=factory)
        data = b"".join(report.iter_report_zip(projects or [self.PROJECT], pool=pool, **kwargs))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            files = {name: zf.read(name) for name in zf.namelist()}
        return files, calls

    def test_first_request_downloads_from_ecm_and_stores_by_project_number(self):
        files, calls = self._run(self._client())

        self.assertEqual(files[f"word/{self.DOCX}"], DOCX_BYTES)
        # 성공 이력은 로그에 쓰지 않는다
        self.assertIn("없음 (모든 프로젝트의 word·pdf 시험성적서를 정상으로 받았습니다)", files[report.SUMMARY_NAME].decode("utf-8-sig"))
        folder = self.cache_dir / "GS-A-25-0077"
        self.assertEqual((folder / "word" / self.DOCX).read_bytes(), DOCX_BYTES)
        self.assertEqual((folder / "pdf" / self.PDF).read_bytes(), PDF_BYTES)
        meta = json.loads((folder / "_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["project_number"], "GS-A-25-0077")
        self.assertEqual(len(meta["files"]), 2)
        self.assertEqual(calls, ["sangam"])
        # 임시 폴더 잔여물이 없어야 한다.
        self.assertEqual([item.name for item in self.cache_dir.iterdir()], ["GS-A-25-0077"])

    def test_second_request_is_served_from_storage_without_touching_ecm(self):
        self._run(self._client())
        second_client = self._client()

        files, calls = self._run(second_client)

        self.assertEqual(calls, [])  # ECM 로그인/조회 없음
        self.assertEqual(second_client.downloaded, [])
        self.assertEqual(files[f"word/{self.DOCX}"], DOCX_BYTES)
        self.assertEqual(files[f"pdf/{self.PDF}"], PDF_BYTES)
        self.assertNotIn("있음 (", files[report.SUMMARY_NAME].decode("utf-8-sig"))

    def test_mixed_request_uses_storage_for_known_and_ecm_for_new(self):
        self._run(self._client())
        other = {"project_number": "GS-A-25-0078", "center_code": "sangam", "cert_date_full": ""}
        client = _FakeClient(
            {"P2": {"folders": [], "files": [_meta("GS-A-25-0078 시험성적서.pdf")]}},
            {"GS-A-25-0078": {"oid": "P2", "name": "x"}},
            {"GS-A-25-0078 시험성적서.pdf": PDF_BYTES},
        )

        files, _calls = self._run(client, projects=[self.PROJECT, other])

        summary = files[report.SUMMARY_NAME].decode("utf-8-sig")
        # 정상으로 받은 이력은 쓰지 않는다. GS-A-25-0078 은 word 가 없었던 사실만 남는다.
        self.assertNotIn("GS-A-25-0077 word", summary)
        self.assertNotIn("GS-A-25-0077 pdf", summary)
        self.assertIn("GS-A-25-0078 word 시험성적서 찾을 수 없음", summary)
        self.assertNotIn("GS-A-25-0078 pdf", summary)
        self.assertEqual(client.downloaded, ["GS-A-25-0078 시험성적서.pdf"])

    def test_partial_failure_is_not_stored_so_next_request_retries(self):
        broken = self._client({self.DOCX: DOCX_BYTES, self.PDF: b"not a pdf"})

        files, _calls = self._run(broken)

        self.assertIn(f"word/{self.DOCX}", files)  # 받은 것은 그대로 전달
        self.assertFalse((self.cache_dir / "GS-A-25-0077").exists())
        _files, calls = self._run(self._client())
        self.assertEqual(calls, ["sangam"])
        self.assertTrue((self.cache_dir / "GS-A-25-0077" / "_meta.json").exists())

    def test_not_found_is_not_stored(self):
        files, _calls = self._run(_FakeClient({}, {}))

        self.assertEqual(list(files), [report.SUMMARY_NAME])
        self.assertFalse(self.cache_dir.exists() and any(self.cache_dir.iterdir()))

    def test_corrupted_storage_is_discarded_and_refetched(self):
        self._run(self._client())
        (self.cache_dir / "GS-A-25-0077" / "pdf" / self.PDF).write_bytes(b"truncated")

        files, calls = self._run(self._client())

        self.assertEqual(calls, ["sangam"])
        self.assertEqual(files[f"pdf/{self.PDF}"], PDF_BYTES)
        self.assertEqual((self.cache_dir / "GS-A-25-0077" / "pdf" / self.PDF).read_bytes(), PDF_BYTES)

    def test_refresh_ignores_storage_and_replaces_it(self):
        self._run(self._client())
        newer = b"%PDF-1.7 newer version!!"

        files, calls = self._run(self._client({self.DOCX: DOCX_BYTES, self.PDF: newer}), refresh=True)

        self.assertEqual(calls, ["sangam"])
        self.assertEqual(files[f"pdf/{self.PDF}"], newer)
        self.assertEqual((self.cache_dir / "GS-A-25-0077" / "pdf" / self.PDF).read_bytes(), newer)
        files, calls = self._run(self._client())
        self.assertEqual(calls, [])  # 교체된 저장본이 이후 요청에 쓰인다
        self.assertEqual(files[f"pdf/{self.PDF}"], newer)

    def test_unwritable_storage_does_not_break_download(self):
        blocker = Path(self._tmp.name) / "not_a_dir"
        blocker.write_text("file blocks directory creation")

        files, _calls = self._run(self._client(), cache_dir=blocker / "kolas")

        self.assertEqual(files[f"word/{self.DOCX}"], DOCX_BYTES)

    def test_default_storage_location(self):
        sep = chr(92)
        self.assertEqual(report_cache.DEFAULT_CACHE_DIR, sep.join(["C:", "Users", "Administrator", "kolas"]))


class KolasReportEndpointTests(_TempCacheMixin, KolasDbTestCase):
    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def _post(self, numbers):
        request = self.factory.post("/kolas/api/report-download/", {"pn": numbers}, HTTP_HOST="testserver")
        request._dont_enforce_csrf_checks = True
        return kolas_report_download(request)

    def _zip_names(self, response):
        data = b"".join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.namelist(), zf

    def test_no_selection_returns_error_zip(self):
        response = self._post([])
        names, _zf = self._zip_names(response)
        self.assertEqual(names, ["다운로드 오류.txt"])

    def test_invalid_numbers_are_ignored(self):
        names, _zf = self._zip_names(self._post(["../etc/passwd", "BAD"]))
        self.assertEqual(names, ["다운로드 오류.txt"])

    @override_settings(KOLAS_REPORT_MAX_PROJECTS=2)
    def test_limit_is_enforced(self):
        names, _zf = self._zip_names(self._post(["GS-A-25-0001", "GS-A-25-0002", "GS-A-25-0003"]))
        self.assertEqual(names, ["다운로드 오류.txt"])

    def test_only_kolas_listed_projects_are_looked_up(self):
        self._kolas("GS-A-25-0001", center_code="bundang")
        seen = []

        def fake_iter(projects, *, missing_numbers=(), pool=None, refresh=False, reporter=None):
            seen.append((projects, list(missing_numbers)))
            return iter([b"PK\x05\x06" + b"\x00" * 18])

        with mock.patch("main.views.review.kolas_api.iter_report_zip", fake_iter):
            response = self._post(["GS-A-25-0001", "GS-A-25-0002", "GS-A-25-0001"])
            b"".join(response.streaming_content)

        projects, missing = seen[0]
        self.assertEqual([item["project_number"] for item in projects], ["GS-A-25-0001"])
        self.assertEqual(projects[0]["center_code"], "bundang")
        self.assertEqual(projects[0]["cert_date_full"], "2025-12-29")
        self.assertEqual(missing, ["GS-A-25-0002"])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/zip")

    def test_asgi_request_streams_chunks_before_generator_finishes(self):
        """ASGI(Daphne)에서 동기 생성기를 그대로 주면 Django 가 전부 모은 뒤 보내므로, 비동기로 감싸 점진 전송해야 한다."""
        self._kolas("GS-A-25-0001")
        progress = []

        def fake_iter(projects, *, missing_numbers=(), pool=None, refresh=False, reporter=None):
            for index in range(3):
                progress.append(f"produced{index}")
                yield f"chunk{index}".encode()

        request = AsyncRequestFactory().post("/kolas/api/report-download/", {"pn": ["GS-A-25-0001"]}, HTTP_HOST="testserver")
        request._dont_enforce_csrf_checks = True
        seen_when_received = []

        async def consume(response):
            self.assertTrue(response.is_async)
            async for part in response:
                seen_when_received.append((part, len(progress)))

        # 다른 스레드(ASGI)에서 메모리 SQLite 에 쓰면 테스트 환경에서만 락이 걸리므로 진행 기록기는 대체한다.
        with mock.patch("main.views.review.kolas_api.iter_report_zip", fake_iter),                 mock.patch("main.views.review.kolas_api.ReportTaskReporter.start", return_value=mock.MagicMock()):
            response = kolas_report_download(request)
            async_to_sync(consume)(response)

        self.assertEqual([part for part, _ in seen_when_received], [b"chunk0", b"chunk1", b"chunk2"])
        # 조각을 받을 때마다 생성기는 그만큼만 진행돼 있다(한꺼번에 모은 뒤 전송하지 않음).
        self.assertEqual([count for _, count in seen_when_received], [1, 2, 3])

    def test_wsgi_request_keeps_sync_iterator(self):
        self._kolas("GS-A-25-0001")
        with mock.patch("main.views.review.kolas_api.iter_report_zip", lambda *a, **k: iter([b"x"])):
            response = self._post(["GS-A-25-0001"])
        self.assertFalse(response.is_async)
        self.assertEqual(b"".join(response.streaming_content), b"x")

    def test_get_is_not_allowed(self):
        request = self.factory.get("/kolas/api/report-download/")
        self.assertEqual(kolas_report_download(request).status_code, 405)


@override_settings(
    DOWNLOAD_REVIEW_DEFAULT_CENTER="sangam",
    DOWNLOAD_REVIEW_DEFAULT_CENTER_BY_HOST={"testserver": "sangam"},
    DOWNLOAD_REVIEW_ALLOWED_CENTERS_BY_HOST={"testserver": {"sangam", "bundang", "yeongnam"}},
    DOWNLOAD_REVIEW_CENTER_ROUTES_BY_HOST={"testserver": {"sangam": "http://other/download-review/"}},
)
class KolasPageTests(SimpleTestCase):
    def test_kolas_page_has_report_button_and_kolas_config(self):
        request = RequestFactory().get("/kolas/", HTTP_HOST="testserver", REMOTE_ADDR="10.0.0.1")
        html = kolas_review(request).content.decode("utf-8")

        self.assertIn('id="downloadReports"', html)
        self.assertIn('id="downloadReviewPageConfig"', html)
        self.assertIn('"kolas": true', html)
        self.assertIn('data-center-tab="unknown"', html)
        self.assertIn("KOLAS 시험성적서 점검", html)
        # 다른 서버로 넘기는 라우트도 KOLAS 페이지를 가리킨다.
        self.assertIn("http://other/kolas/", html)
        self.assertNotIn("http://other/download-review/", html)

    def test_ecm_page_is_unchanged(self):
        from main.views.init import download_review

        request = RequestFactory().get("/download-review/", HTTP_HOST="testserver", REMOTE_ADDR="10.0.0.1")
        html = download_review(request).content.decode("utf-8")

        self.assertNotIn('id="downloadReports"', html)
        self.assertNotIn("downloadReviewPageConfig", html)
        self.assertNotIn('data-center-tab="unknown"', html)
        self.assertIn("ECM 제출물 자동 점검", html)


# ---------------------------------------------------------------------------
# ECM zip 내부 부분 읽기(HTTP Range)
# ---------------------------------------------------------------------------
import os as _os
import time as _time

from main.views.review import ecm_zip_range
from main.views.review.ecm_http_client import DestinyECM, EcmRangeUnsupported


class _RangeClient:
    """메모리 zip 에서 Range 구간만 돌려주는 가짜 ECM 클라이언트."""

    def __init__(self, data):
        self.data = data
        self.ranges = []

    def blob_range(self, file_meta, start, end):
        self.ranges.append((start, end))
        return self.data[start:end + 1]


def _build_zip(entries, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buffer.getvalue()


class EcmZipRangeTests(SimpleTestCase):
    def test_lists_and_reads_one_entry_while_fetching_a_small_fraction(self):
        filler = _os.urandom(2 * 1024 * 1024)  # 압축되지 않는 큰 파일들
        entries = [(f"폴더/큰파일{i}.bin", filler) for i in range(8)]
        entries.insert(5, ("폴더/GS-A-25-0077 시험성적서.pdf", b"%PDF-1.4 report body"))
        data = _build_zip(entries)
        client = _RangeClient(data)
        meta = {"fileName": "all.zip", "fileSize": len(data)}

        zf, remote = ecm_zip_range.open_remote_zip(client, meta, block_size=64 * 1024)
        names = [name for name, _ in ecm_zip_range.iter_entries(zf)]
        target = next(info for name, info in ecm_zip_range.iter_entries(zf) if "시험성적서" in name)
        content = zf.open(target).read()

        self.assertEqual(len(names), 9)
        self.assertEqual(content, b"%PDF-1.4 report body")
        self.assertGreater(len(data), 16 * 1024 * 1024)
        # 16MB 이상 zip 에서 목록 + 항목 1개만 받으므로 전송량은 전체의 몇 % 이하여야 한다.
        self.assertLess(remote.bytes_fetched, len(data) * 0.05)
        self.assertEqual(remote.requests, len(client.ranges))
        self.assertTrue(all(0 <= start <= end < len(data) for start, end in client.ranges))

    def test_cp949_names_without_utf8_flag_are_restored(self):
        placeholder = "X" * len("시험성적서.docx".encode("cp949"))
        data = bytearray(_build_zip([(f"{placeholder}", b"PK\x03\x04docx")]))
        real = "시험성적서.docx".encode("cp949")
        raw = bytes(data).replace(placeholder.encode(), real)
        self.assertNotEqual(raw, bytes(data))
        client = _RangeClient(raw)

        zf, _remote = ecm_zip_range.open_remote_zip(client, {"fileName": "k.zip", "fileSize": len(raw)})
        decoded = [name for name, _ in ecm_zip_range.iter_entries(zf)]

        self.assertEqual(decoded, ["시험성적서.docx"])
        self.assertEqual(report.classify_report_file(decoded[0]), "word")

    def test_utf8_flagged_names_are_left_alone(self):
        data = _build_zip([("한글/시험성적서.pdf", b"%PDF-1")])
        zf, _remote = ecm_zip_range.open_remote_zip(_RangeClient(data), {"fileName": "u.zip", "fileSize": len(data)})
        self.assertEqual([name for name, _ in ecm_zip_range.iter_entries(zf)], ["한글/시험성적서.pdf"])

    def test_byte_budget_stops_runaway_reads(self):
        data = _build_zip([("a.bin", _os.urandom(1024 * 1024))])
        client = _RangeClient(data)
        remote = ecm_zip_range.EcmRangeFile(client, {"fileName": "b.zip", "fileSize": len(data)}, block_size=64 * 1024, max_bytes=100 * 1024)

        remote.seek(0)
        remote.read(64 * 1024)
        with self.assertRaises(ecm_zip_range.RangeBudgetExceeded):
            remote.read(128 * 1024)

    def test_unknown_size_is_rejected(self):
        with self.assertRaises(ValueError):
            ecm_zip_range.EcmRangeFile(_RangeClient(b""), {"fileName": "x.zip", "fileSize": 0})


class _FakeResponse:
    def __init__(self, status, content=b"", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}
        self.url = "http://ecm/servlet/blob"
        self.closed = False

    def close(self):
        self.closed = True


class _FakeCookies:
    def get(self, key, default=""):
        return "SESSION" if key == "SESSION_KEY" else default


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.cookies = _FakeCookies()
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def _ecm_with(response):
    ecm = DestinyECM("http://ecm", "ROOT", "u", "p")
    ecm.session = _FakeSession(response)
    return ecm


class EcmBlobRangeClientTests(SimpleTestCase):
    META = {"fileName": "all.zip", "storageFileID": "SID", "fileSize": 1000, "fileOID": "F"}

    def test_range_header_is_sent_and_206_body_returned(self):
        ecm = _ecm_with(_FakeResponse(206, b"PK\x03\x04", {"Content-Range": "bytes 0-3/1000"}))

        data = ecm.blob_range(self.META, 0, 3)

        self.assertEqual(data, b"PK\x03\x04")
        url, kwargs = ecm.session.calls[0]
        self.assertEqual(kwargs["headers"]["Range"], "bytes=0-3")
        self.assertTrue(kwargs["stream"])
        self.assertIn("encryptionClient=false", url)

    def test_200_response_means_range_unsupported_and_body_is_not_read(self):
        response = _FakeResponse(200, b"FULL FILE", {"Content-Length": "1000"})
        ecm = _ecm_with(response)

        with self.assertRaises(EcmRangeUnsupported) as ctx:
            ecm.blob_range(self.META, 0, 3)

        self.assertIn("HTTP 200", str(ctx.exception))
        self.assertTrue(response.closed)  # 전체 본문을 받지 않고 연결을 닫는다

    def test_download_bytes_still_downloads_whole_file_without_range(self):
        ecm = _ecm_with(_FakeResponse(200, b"WHOLE"))

        self.assertEqual(ecm.download_bytes(self.META), b"WHOLE")
        _url, kwargs = ecm.session.calls[0]
        self.assertNotIn("Range", kwargs["headers"])
        self.assertFalse(kwargs["stream"])

    def test_download_bytes_raises_on_http_error(self):
        ecm = _ecm_with(_FakeResponse(500))

        with self.assertRaises(Exception):
            ecm.download_bytes(self.META)


# ---------------------------------------------------------------------------
# zip 스트리밍 해석 / 프로젝트 전체가 zip 으로 올라간 경우
# ---------------------------------------------------------------------------
import struct as _struct

from main.views.review import ecm_zip_stream as zs


class _NonSeekable(io.RawIOBase):
    """쓰기만 되는 스트림 - zipfile 이 데이터 디스크립터(bit 3) 방식으로 쓰게 만든다."""

    def __init__(self):
        super().__init__()
        self.buffer = bytearray()

    def writable(self):
        return True

    def write(self, data):
        self.buffer += data
        return len(data)

    def tell(self):
        raise OSError("not seekable")


def _stream_zip(entries, compression=zipfile.ZIP_DEFLATED):
    sink = _NonSeekable()
    with zipfile.ZipFile(sink, "w", compression=compression) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return bytes(sink.buffer)


def _chunks(data, size=700):
    for index in range(0, len(data), size):
        yield data[index:index + size]


def _want_reports(name):
    return report.classify_report_file(name.replace(chr(92), "/").rsplit("/", 1)[-1]) is not None


PROJECT_ENTRIES = [
    ("1.시험인증신청/신청서.docx", b"PK\x03\x04 application " * 50),
    ("2.계약/계약서.pdf", b"%PDF-1.4 contract " * 400),
    ("4.시험/나.설계/rawdata/a.png", _os.urandom(200_000)),
    ("4.시험/라.종료/GS-C-25-0091 시험성적서.docx", b"PK\x03\x04 report word " * 100),
    ("4.시험/라.종료/GS-C-25-0091 시험성적서.pdf", b"%PDF-1.7 report pdf " * 300),
    ("4.시험/라.종료/결함리포트.xlsx", b"PK\x03\x04 defects"),
]


class EcmZipStreamTests(SimpleTestCase):
    def test_extracts_only_wanted_entries_from_chunked_stream(self):
        data = _build_zip(PROJECT_ENTRIES, compression=zipfile.ZIP_DEFLATED)

        result = zs.extract_matching(_chunks(data, 513), _want_reports)

        names = [name for name, _ in result.files]
        self.assertEqual(names, ["4.시험/라.종료/GS-C-25-0091 시험성적서.docx", "4.시험/라.종료/GS-C-25-0091 시험성적서.pdf"])
        self.assertEqual(dict(result.files)["4.시험/라.종료/GS-C-25-0091 시험성적서.pdf"], b"%PDF-1.7 report pdf " * 300)
        self.assertEqual(result.entries_seen, len(PROJECT_ENTRIES))
        self.assertLessEqual(result.bytes_read, len(data))

    def test_data_descriptor_streamed_zip(self):
        data = _stream_zip(PROJECT_ENTRIES)
        self.assertTrue(zipfile.ZipFile(io.BytesIO(data)).infolist()[0].flag_bits & 0x8)  # 디스크립터 사용 확인

        result = zs.extract_matching(_chunks(data, 333), _want_reports)

        self.assertEqual(len(result.files), 2)
        self.assertEqual(dict(result.files)["4.시험/라.종료/GS-C-25-0091 시험성적서.docx"], b"PK\x03\x04 report word " * 100)

    def test_zip64_local_headers(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in PROJECT_ENTRIES:
                with zf.open(name, "w", force_zip64=True) as handle:
                    handle.write(content)
        data = buffer.getvalue()

        result = zs.extract_matching(_chunks(data, 411), _want_reports)

        self.assertEqual(len(result.files), 2)

    def test_cp949_names_without_utf8_flag(self):
        real = "4.시험/시험성적서.pdf"
        placeholder = "X" * len(real.encode("cp949"))
        raw = _build_zip([(placeholder, b"%PDF-1.4 cp949 named")]).replace(placeholder.encode(), real.encode("cp949"))

        result = zs.extract_matching(_chunks(raw, 100), _want_reports)

        self.assertEqual([name for name, _ in result.files], [real])

    def test_stored_with_descriptor_is_unsupported_but_tempfile_fallback_works(self):
        data = _stream_zip(PROJECT_ENTRIES, compression=zipfile.ZIP_STORED)

        with self.assertRaises(zs.ZipStreamUnsupported):
            zs.extract_matching(_chunks(data), _want_reports)
        result = zs.extract_via_tempfile(_chunks(data), _want_reports)

        self.assertEqual(len(result.files), 2)

    def test_tempfile_fallback_removes_its_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            zs.extract_via_tempfile(_chunks(_build_zip(PROJECT_ENTRIES)), _want_reports, temp_dir=temp_dir)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_encrypted_entry_is_skipped_and_reported(self):
        data = bytearray(_build_zip([("a/시험성적서.pdf", b"%PDF-1 secret"), ("b/시험성적서.docx", b"PK\x03\x04 ok")]))
        # 첫 로컬 헤더의 일반 목적 비트 플래그(offset 6)에 암호화 비트를 세운다.
        flag = _struct.unpack_from("<H", data, 6)[0]
        _struct.pack_into("<H", data, 6, flag | 0x1)

        result = zs.extract_matching(_chunks(bytes(data)), _want_reports)

        self.assertEqual([name for name, _ in result.files], ["b/시험성적서.docx"])
        self.assertEqual(result.skipped[0][1], "암호화된 항목")

    def test_corrupted_entry_is_detected_by_crc(self):
        content = b"%PDF-1.4 " + b"A" * 200
        data = bytearray(_build_zip([("시험성적서.pdf", content)], compression=zipfile.ZIP_STORED))
        position = bytes(data).index(content) + 20
        data[position] ^= 0xFF  # 본문 한 바이트 변조

        with self.assertRaises(zs.ZipStreamUnsupported):
            zs.extract_matching(_chunks(bytes(data)), _want_reports)

    def test_stream_budget_is_enforced(self):
        data = _build_zip([("a.bin", _os.urandom(500_000))], compression=zipfile.ZIP_STORED)

        with self.assertRaises(zs.ZipStreamBudgetExceeded):
            zs.extract_matching(_chunks(data, 10_000), _want_reports, max_stream_bytes=100_000)

    def test_oversized_wanted_entry_is_skipped_without_buffering(self):
        data = _build_zip([("큰/시험성적서.pdf", b"%PDF-1 " + b"B" * 5000)], compression=zipfile.ZIP_STORED)

        result = zs.extract_matching(_chunks(data), _want_reports, max_entry_bytes=1000)

        self.assertEqual(result.files, [])
        self.assertIn("너무 큼", result.skipped[0][1])

    def test_truncated_stream_raises_eof(self):
        data = _build_zip(PROJECT_ENTRIES)

        with self.assertRaises(EOFError):
            zs.extract_matching(_chunks(data[: len(data) // 2]), _want_reports)


class _StreamResponse:
    def __init__(self, data):
        self._data = data
        self.closed = False

    def iter_content(self, chunk_size=1024 * 1024):
        for index in range(0, len(self._data), 4096):
            yield self._data[index:index + 4096]

    def close(self):
        self.closed = True


class _ZipProjectClient(_FakeClient):
    """프로젝트 폴더에 시험성적서가 직접 없고 zip 만 있는 ECM."""

    def __init__(self, zips):
        files = [_meta(name, size=len(data)) for name, data in zips.items()]
        super().__init__(
            {"P": {"folders": [], "files": files}},
            {"GS-C-25-0091": {"oid": "P", "name": "GS-C-25-0091 회사"}},
            {},
        )
        self.zip_blobs = zips
        self.streams = []
        self.responses = []

    def blob_stream(self, meta):
        self.streams.append(meta["fileName"])
        response = _StreamResponse(self.zip_blobs[meta["fileName"]])
        self.responses.append(response)
        return response


class KolasProjectZipTests(_TempCacheMixin, SimpleTestCase):
    PROJECT = {"project_number": "GS-C-25-0091", "center_code": "yeongnam", "cert_date_full": "2025-12-29"}
    WORD = "GS-C-25-0091 시험성적서.docx"
    PDF = "GS-C-25-0091 시험성적서.pdf"

    def _run(self, client, **kwargs):
        pool = report._ClientPool(factory=lambda center: client)
        data = b"".join(report.iter_report_zip([self.PROJECT], pool=pool, **kwargs))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return {name: zf.read(name) for name in zf.namelist()}

    def test_report_files_are_taken_from_inside_the_big_zip(self):
        client = _ZipProjectClient({"GS-C-25-0091.zip": _build_zip(PROJECT_ENTRIES)})

        files = self._run(client)

        self.assertEqual(files[f"word/{self.WORD}"], b"PK\x03\x04 report word " * 100)
        self.assertEqual(files[f"pdf/{self.PDF}"], b"%PDF-1.7 report pdf " * 300)
        summary = files[report.SUMMARY_NAME].decode("utf-8-sig")
        self.assertNotIn("GS-C-25-0091 word", summary)
        self.assertNotIn("GS-C-25-0091 pdf", summary)
        self.assertEqual(client.streams, ["GS-C-25-0091.zip"])
        self.assertTrue(all(response.closed for response in client.responses))
        # 다른 항목(신청서·계약서·rawdata 등)은 결과 zip 에 들어가지 않는다.
        self.assertEqual({name.split("/")[0] for name in files}, {"word", "pdf", report.SUMMARY_NAME})

    def test_extracted_reports_are_stored_so_next_request_skips_ecm_entirely(self):
        self._run(_ZipProjectClient({"GS-C-25-0091.zip": _build_zip(PROJECT_ENTRIES)}))
        second = _ZipProjectClient({"GS-C-25-0091.zip": _build_zip(PROJECT_ENTRIES)})

        files = self._run(second)

        self.assertEqual(second.streams, [])
        self.assertNotIn("있음 (", files[report.SUMMARY_NAME].decode("utf-8-sig"))
        self.assertEqual(files[f"pdf/{self.PDF}"], b"%PDF-1.7 report pdf " * 300)
        # 서버 저장소에는 시험성적서 2개와 메타만 남고 zip 원본은 저장되지 않는다.
        stored = sorted(path.name for path in (self.cache_dir / "GS-C-25-0091").rglob("*") if path.is_file())
        self.assertEqual(stored, sorted([self.WORD, self.PDF, "_meta.json"]))

    def test_zip_that_cannot_be_streamed_falls_back_to_temp_file(self):
        client = _ZipProjectClient({"GS-C-25-0091.zip": _stream_zip(PROJECT_ENTRIES, compression=zipfile.ZIP_STORED)})

        files = self._run(client)

        self.assertIn(f"word/{self.WORD}", files)
        self.assertEqual(client.streams, ["GS-C-25-0091.zip", "GS-C-25-0091.zip"])  # 스트리밍 시도 + 임시 파일 방식

    def test_direct_reports_win_and_zip_is_never_opened(self):
        client = _ZipProjectClient({"x.zip": b""})
        client.tree = {"P": {"folders": [], "files": [_meta(self.WORD), _meta("rawdata.zip", 10)]}}
        client.blobs = {self.WORD: DOCX_BYTES}

        files = self._run(client)

        self.assertEqual(files[f"word/{self.WORD}"], DOCX_BYTES)
        self.assertEqual(client.streams, [])

    def test_zip_without_reports_is_reported_with_reason(self):
        other = _build_zip([("계약/계약서.pdf", b"%PDF-1 x"), ("rawdata/a.bin", b"1234")])
        client = _ZipProjectClient({"GS-C-25-0091.zip": other})

        files = self._run(client)

        self.assertEqual(list(files), [report.SUMMARY_NAME])
        self.assertIn("안에 시험성적서 Word/PDF 없음", files[report.SUMMARY_NAME].decode("utf-8-sig"))
        self.assertFalse(self.cache_dir.exists() and any(self.cache_dir.iterdir()))

    def test_candidates_are_ordered_main_zip_first_and_aux_zips_last(self):
        zips = [
            ("4.시험/나.설계", _meta("rawdata.zip", 5)),
            ("", _meta("GS-C-25-0091.zip", 100)),
            ("6.홍보", _meta("홍보자료.zip", 50)),
            ("4.시험/라.종료", _meta("GS-C-25-0091 시험 산출물.zip", 80)),
        ]

        ordered = [meta["fileName"] for _rel, meta in report.order_zip_candidates(zips, "GS-C-25-0091")]

        self.assertEqual(ordered[:2], ["GS-C-25-0091.zip", "GS-C-25-0091 시험 산출물.zip"])
        self.assertEqual(set(ordered[2:]), {"rawdata.zip", "홍보자료.zip"})

    def test_aux_zips_are_opened_only_when_main_zip_has_nothing(self):
        main_zip = _build_zip([("계약/계약서.pdf", b"%PDF-1 x")])
        aux_zip = _build_zip([("rawdata/시험성적서.pdf", b"%PDF-1.4 hidden in aux")])
        client = _ZipProjectClient({"GS-C-25-0091.zip": main_zip, "rawdata.zip": aux_zip})

        files = self._run(client)

        self.assertEqual(client.streams, ["GS-C-25-0091.zip", "rawdata.zip"])
        self.assertEqual(files["pdf/GS-C-25-0091_시험성적서.pdf"], b"%PDF-1.4 hidden in aux")

    @override_settings(KOLAS_ZIP_SCAN_MAX_MB=0)
    def test_scan_budget_zero_does_not_open_any_zip(self):
        client = _ZipProjectClient({"GS-C-25-0091.zip": _build_zip(PROJECT_ENTRIES)})

        files = self._run(client)

        self.assertEqual(client.streams, [])
        self.assertIn("탐색 한도", files[report.SUMMARY_NAME].decode("utf-8-sig"))


class EcmBlobStreamClientTests(SimpleTestCase):
    META = {"fileName": "all.zip", "storageFileID": "SID", "fileSize": 1000, "fileOID": "F"}

    def test_blob_stream_returns_open_streaming_response(self):
        response = _FakeResponse(200, b"x")
        ecm = _ecm_with(response)

        self.assertIs(ecm.blob_stream(self.META), response)
        self.assertTrue(ecm.session.calls[0][1]["stream"])
        self.assertFalse(response.closed)

    def test_blob_stream_raises_and_closes_on_error(self):
        response = _FakeResponse(500)
        ecm = _ecm_with(response)

        with self.assertRaises(Exception):
            ecm.blob_stream(self.META)
        self.assertTrue(response.closed)


# ---------------------------------------------------------------------------
# 시험성적서 미업로드 -> 분당 ECM 익명본(Word) 대체
# ---------------------------------------------------------------------------
from datetime import datetime as _datetime, timedelta as _timedelta


class _CommitteeClient(_FakeClient):
    """분당 ECM 흉내: 인증위원회 트리(committee)와 분당 프로젝트 폴더를 둘 다 가진다."""

    def __init__(self, tree, committee=None, project_folder=None, blobs=None):
        super().__init__(tree, project_folder or {}, blobs or {})
        self.committee = committee or {}
        self.committee_calls = []

    def find_committee_test_folder(self, test_no, cert_date):
        self.committee_calls.append((test_no, cert_date))
        return self.committee.get(test_no)


ANON_WORD = b"PK\x03\x04 anonymous word report"


class AnonymousSelectionTests(SimpleTestCase):
    def _names(self, *names):
        return [_meta(name) for name in names]

    def test_only_anonymous_word_test_reports_are_selected(self):
        metas = self._names(
            "GS-B-25-0133 시험성적서 v1.0_익명.docx",
            "(익명) GS-C-25-0091 시험성적서 v1.0.docx",
            "GS-C-25-0108 시험성적서 v1.0 (익명).docx",
            "GS-A-25-0099 시험성적서 v1.0_KOLAS비인정TTA마크_v20250801 - 익명.docx",
            "GS-B-25-0068 시험성적서 및 시험결과서 v1.0_익명.doc",
            "GS-B-25-0133 품질평가보고서 v1.0_익명.doc",       # 품질평가보고서 - 대상 아님
            "GS-B-25-0133 시험성적서 v1.0.docx",                 # 익명 아님
            "GS-B-25-0133 시험성적서 v1.0_익명.pdf",             # 익명은 Word 만
        )

        selected = [meta["fileName"] for meta in report.select_anonymous_report_files(metas)]

        self.assertEqual(len(selected), 5)
        self.assertNotIn("GS-B-25-0133 품질평가보고서 v1.0_익명.doc", selected)
        self.assertNotIn("GS-B-25-0133 시험성적서 v1.0.docx", selected)
        self.assertNotIn("GS-B-25-0133 시험성적서 v1.0_익명.pdf", selected)

    def test_duplicates_by_storage_id_are_removed(self):
        meta = _meta("A 시험성적서 - 익명.docx")
        self.assertEqual(len(report.select_anonymous_report_files([meta, dict(meta)])), 1)


class KolasAnonymousFallbackTests(_TempCacheMixin, SimpleTestCase):
    NUMBER = "GS-B-25-0133"
    PROJECT = {"project_number": NUMBER, "center_code": "sangam", "cert_date_full": "2025-10-27"}
    ANON_NAME = "GS-B-25-0133 시험성적서 v1.0_익명.docx"

    def _clients(self, *, sangam_files=(), with_committee=True, anon_in_bundang_project=False):
        sangam = _FakeClient(
            {"S": {"folders": [], "files": [_meta(name) for name in sangam_files]}},
            {self.NUMBER: {"oid": "S", "name": f"{self.NUMBER} 상암 프로젝트"}},
            {},
        )
        bundang_tree = {
            "C": {"folders": [], "files": [
                _meta(self.ANON_NAME),
                _meta("GS-B-25-0133 품질평가보고서 v1.0_익명.doc"),
            ]},
            "B": {"folders": [], "files": [_meta("GS-B-25-0133 시험성적서 - 익명.docx")]},
        }
        bundang = _CommitteeClient(
            bundang_tree,
            committee={self.NUMBER: {"oid": "C", "name": f"마. {self.NUMBER}"}} if with_committee else {},
            project_folder={self.NUMBER: {"oid": "B", "name": "분당 프로젝트"}} if anon_in_bundang_project else {},
            blobs={self.ANON_NAME: ANON_WORD, "GS-B-25-0133 시험성적서 - 익명.docx": ANON_WORD},
        )
        return {"sangam": sangam, "bundang": bundang, "yeongnam": _FakeClient({}, {}, {})}

    def _run(self, clients, projects=None, **kwargs):
        pool = report._ClientPool(factory=lambda center: clients[center])
        data = b"".join(report.iter_report_zip(projects or [self.PROJECT], pool=pool, **kwargs))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return {name: zf.read(name) for name in zf.namelist()}

    def test_missing_report_falls_back_to_bundang_anonymous_word_in_anonymous_folder(self):
        clients = self._clients()

        files = self._run(clients)

        self.assertEqual(files[f"익명/{self.ANON_NAME}"], ANON_WORD)
        self.assertEqual(sorted(name for name in files if name != report.SUMMARY_NAME), [f"익명/{self.ANON_NAME}"])
        self.assertEqual(clients["bundang"].committee_calls, [(self.NUMBER, "2025-10-27")])
        summary = files[report.SUMMARY_NAME].decode("utf-8-sig")
        self.assertIn("분당 ECM 익명본으로 대체", summary)

    def test_anonymous_fallback_is_never_stored_on_the_server(self):
        self._run(self._clients())

        self.assertFalse(self.cache_dir.exists() and any(self.cache_dir.iterdir()))

    def test_original_report_wins_and_anonymous_is_not_even_looked_up(self):
        original = "GS-B-25-0133 시험성적서.docx"
        clients = self._clients(sangam_files=[original])
        clients["sangam"].blobs = {original: DOCX_BYTES}

        files = self._run(clients)

        self.assertEqual(files[f"word/{original}"], DOCX_BYTES)
        self.assertFalse(any(name.startswith("익명/") for name in files))
        self.assertEqual(clients["bundang"].committee_calls, [])

    def test_anonymous_file_next_to_the_original_is_not_mistaken_for_the_original(self):
        """분당 프로젝트 폴더에는 원본 시험성적서와 '- 익명.docx' 가 함께 있다. word/ 에는 원본만 들어가야 한다."""
        original = "GS-B-25-0133 시험성적서.docx"
        clients = self._clients(sangam_files=[original, self.ANON_NAME])
        clients["sangam"].blobs = {original: DOCX_BYTES, self.ANON_NAME: ANON_WORD}

        files = self._run(clients)

        self.assertEqual(files[f"word/{original}"], DOCX_BYTES)
        self.assertFalse(any("익명" in name for name in files if name != report.SUMMARY_NAME))
        self.assertEqual(clients["bundang"].committee_calls, [])
        self.assertEqual(clients["sangam"].downloaded, [original])

    def test_classify_excludes_anonymous_names_but_selection_keeps_them(self):
        self.assertIsNone(report.classify_report_file("GS-A-25-0099 시험성적서 v1.0 - 익명.docx"))
        self.assertIsNone(report.classify_report_file("(익명) GS-C-25-0091 시험성적서 v1.0.docx"))
        self.assertEqual(report.classify_report_file("GS-A-25-0099 시험성적서 v1.0.docx"), "word")
        kept = report.select_anonymous_report_files([_meta("(익명) GS-C-25-0091 시험성적서 v1.0.docx")])
        self.assertEqual(len(kept), 1)

    def test_falls_back_to_bundang_project_folder_when_committee_tree_has_nothing(self):
        clients = self._clients(with_committee=False, anon_in_bundang_project=True)

        files = self._run(clients)

        self.assertEqual(files["익명/GS-B-25-0133 시험성적서 - 익명.docx"], ANON_WORD)

    def test_without_committee_date_only_project_folder_is_tried(self):
        clients = self._clients(anon_in_bundang_project=True)
        project = dict(self.PROJECT, cert_date_full="")

        files = self._run(clients, projects=[project])

        self.assertEqual(clients["bundang"].committee_calls, [])
        self.assertIn("익명/GS-B-25-0133 시험성적서 - 익명.docx", files)

    def test_when_neither_original_nor_anonymous_exists_both_reasons_are_reported(self):
        clients = self._clients(with_committee=False)

        files = self._run(clients)

        self.assertEqual(list(files), [report.SUMMARY_NAME])
        summary = files[report.SUMMARY_NAME].decode("utf-8-sig")
        self.assertIn("익명본 대체도 실패", summary)
        self.assertIn("인증위원회 트리에 시험번호 폴더 없음", summary)
        self.assertFalse(self.cache_dir.exists() and any(self.cache_dir.iterdir()))

    def test_bundang_login_failure_is_reported_without_breaking_download(self):
        def factory(center):
            if center == "bundang":
                raise RuntimeError("자격증명 없음")
            return self._clients()[center]

        pool = report._ClientPool(factory=factory)
        data = b"".join(report.iter_report_zip([self.PROJECT], pool=pool))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            summary = zf.read(report.SUMMARY_NAME).decode("utf-8-sig")
        self.assertIn("분당 ECM 접속 실패", summary)

    def test_every_request_searches_the_original_center_first_and_falls_back_to_anonymous_again(self):
        first = self._clients()
        second = self._clients()

        self._run(first)
        files = self._run(second)

        for clients in (first, second):
            self.assertEqual(clients["bundang"].committee_calls, [(self.NUMBER, "2025-10-27")])
        self.assertEqual(files[f"익명/{self.ANON_NAME}"], ANON_WORD)
        self.assertIn(f"{self.NUMBER} word 시험성적서 찾을 수 없음", files[report.SUMMARY_NAME].decode("utf-8-sig"))  # 매번 원본을 다시 찾는다

    def test_original_report_uploaded_later_is_served_and_stored_as_final(self):
        self._run(self._clients())  # 처음에는 원본이 없어 익명본으로 대체(저장 안 됨)
        original = "GS-B-25-0133 시험성적서.docx"
        later = self._clients(sangam_files=[original])
        later["sangam"].blobs = {original: DOCX_BYTES}

        files = self._run(later)

        self.assertEqual(files[f"word/{original}"], DOCX_BYTES)
        self.assertFalse(any(name.startswith("익명/") for name in files))
        self.assertEqual(later["bundang"].committee_calls, [])
        self.assertTrue((self.cache_dir / self.NUMBER / "word" / original).exists())
        # 최종본이 저장된 뒤에는 ECM 없이 저장본으로 서빙된다.
        again = self._clients()
        files = self._run(again)
        self.assertEqual(files[f"word/{original}"], DOCX_BYTES)
        self.assertEqual(again["bundang"].committee_calls, [])
        self.assertNotIn("있음 (", files[report.SUMMARY_NAME].decode("utf-8-sig"))


# ---------------------------------------------------------------------------
# 결과 로그(_다운로드_결과.txt): 프로젝트별 word/pdf 유무
# ---------------------------------------------------------------------------
class KolasResultLogTests(_TempCacheMixin, SimpleTestCase):
    """로그(_다운로드_결과.txt)에는 정상으로 받은 word/pdf 이력을 쓰지 않는다. 못 찾음·다운로드 실패·익명 대체만 쓴다."""

    NUMBER = "TTA-26-00001"
    WORD = "TTA-26-00001 시험성적서.docx"
    PDF = "TTA-26-00001 시험성적서.pdf"
    NONE_MSG = "없음 (모든 프로젝트의 word·pdf 시험성적서를 정상으로 받았습니다)"

    def _project(self, number=None, center="sangam"):
        return {"project_number": number or self.NUMBER, "center_code": center, "cert_date_full": "2026-05-12"}

    def _client(self, names, blobs=None, number=None):
        number = number or self.NUMBER
        tree = {"P": {"folders": [], "files": [_meta(name) for name in names]}}
        return _FakeClient(tree, {number: {"oid": "P", "name": f"{number} 회사"}}, blobs or {})

    def _log(self, projects, client=None, **kwargs):
        pool = report._ClientPool(factory=lambda center: client or _FakeClient({}, {}, {}))
        data = b"".join(report.iter_report_zip(projects, pool=pool, **kwargs))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read(report.SUMMARY_NAME).decode("utf-8-sig")

    def _issues(self, log):
        section = log.split("[확인 필요 이력]\n")[1].split("\n\n")[0]
        return section.splitlines()

    def test_word_success_and_pdf_missing_logs_only_the_pdf(self):
        client = self._client([self.WORD], {self.WORD: DOCX_BYTES})

        log = self._log([self._project()], client)

        self.assertEqual(self._issues(log), [f"{self.NUMBER} pdf 시험성적서 찾을 수 없음"])
        self.assertNotIn("word", "\n".join(self._issues(log)))
        self.assertIn("일부만 있음 1건", log)

    def test_both_success_writes_nothing_for_the_project(self):
        client = self._client([self.WORD, self.PDF], {self.WORD: DOCX_BYTES, self.PDF: PDF_BYTES})

        log = self._log([self._project()], client)

        self.assertEqual(self._issues(log), [self.NONE_MSG])
        self.assertNotIn(self.NUMBER, log.split("[확인 필요 이력]")[1])
        self.assertIn("word·pdf 모두 있음 1건", log)

    def test_pdf_only_logs_only_word_missing(self):
        client = self._client([self.PDF], {self.PDF: PDF_BYTES})

        log = self._log([self._project()], client)

        self.assertEqual(self._issues(log), [f"{self.NUMBER} word 시험성적서 찾을 수 없음"])

    def test_found_but_unreadable_file_is_logged_as_download_failure_not_as_missing(self):
        client = self._client([self.WORD, self.PDF], {self.WORD: DOCX_BYTES, self.PDF: b"not a pdf"})

        issues = self._issues(self._log([self._project()], client))

        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0].startswith(f"{self.NUMBER} pdf 시험성적서 다운로드 실패 ("))
        self.assertNotIn("찾을 수 없음", issues[0])

    def test_storage_hit_success_is_not_logged(self):
        client = self._client([self.WORD, self.PDF], {self.WORD: DOCX_BYTES, self.PDF: PDF_BYTES})
        self._log([self._project()], client)

        log = self._log([self._project()], self._client([]))

        self.assertEqual(self._issues(log), [self.NONE_MSG])

    def test_nothing_found_logs_word_and_pdf_missing(self):
        issues = self._issues(self._log([self._project()], self._client([])))

        self.assertEqual(issues[:2], [f"{self.NUMBER} word 시험성적서 찾을 수 없음", f"{self.NUMBER} pdf 시험성적서 찾을 수 없음"])

    def test_extracted_from_zip_success_is_not_logged_only_the_missing_kind(self):
        number = "GS-C-25-0091"
        archive = _build_zip([("4.시험/라.종료/GS-C-25-0091 시험성적서.docx", DOCX_BYTES)])
        client = _ZipProjectClient({"GS-C-25-0091.zip": archive})

        issues = self._issues(self._log([self._project(number, "yeongnam")], client))

        self.assertEqual(issues[:1], [f"{number} pdf 시험성적서 찾을 수 없음"])
        self.assertFalse(any(" word " in line for line in issues))

    def test_anonymous_fallback_logs_word_pdf_missing_and_anonymous_download(self):
        anon = "TTA-26-00001 시험성적서 v1.0 (익명).docx"
        sangam = self._client([])
        bundang = _CommitteeClient(
            {"C": {"folders": [], "files": [_meta(anon)]}},
            committee={self.NUMBER: {"oid": "C", "name": "가. TTA-26-00001"}},
            blobs={anon: ANON_WORD},
        )
        clients = {"sangam": sangam, "bundang": bundang, "yeongnam": _FakeClient({}, {}, {})}
        pool = report._ClientPool(factory=lambda center: clients[center])

        data = b"".join(report.iter_report_zip([self._project()], pool=pool))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            log = zf.read(report.SUMMARY_NAME).decode("utf-8-sig")
        issues = self._issues(log)
        self.assertEqual(issues[0], f"{self.NUMBER} word 시험성적서 찾을 수 없음")
        self.assertEqual(issues[1], f"{self.NUMBER} pdf 시험성적서 찾을 수 없음")
        self.assertTrue(issues[2].startswith(f"{self.NUMBER} 익명 시험성적서(word) 다운로드 (1개, 분당 ECM 익명본으로 대체"))
        self.assertEqual(len(issues), 3)
        self.assertIn("익명본 대체 1건", log)

    def test_anonymous_lookup_failure_is_logged(self):
        issues = self._issues(self._log([self._project()], self._client([])))

        self.assertTrue(any(line.startswith(f"{self.NUMBER} 익명 시험성적서(word) 찾을 수 없음") for line in issues))

    def test_project_not_in_kolas_list_is_logged_as_unverifiable(self):
        log = self._log([], self._client([]), missing_numbers=["GS-A-25-9999"])

        self.assertIn("GS-A-25-9999 word 시험성적서 확인 불가 (KOLAS 프로젝트 목록에 없음)", log)
        self.assertIn("GS-A-25-9999 pdf 시험성적서 확인 불가 (KOLAS 프로젝트 목록에 없음)", log)
        self.assertIn("확인 불가 1건", log)

    def test_only_projects_with_issues_appear_in_request_order(self):
        names = {"TTA-26-00001": [], "TTA-26-00002": None, "TTA-26-00003": []}
        folders, tree, blobs = {}, {}, {}
        for number in names:
            files = [f"{number} 시험성적서.docx", f"{number} 시험성적서.pdf"] if number == "TTA-26-00002" else []
            tree[number] = {"folders": [], "files": [_meta(name) for name in files]}
            folders[number] = {"oid": number, "name": f"{number} 회사"}
            blobs[f"{number} 시험성적서.docx"] = DOCX_BYTES
            blobs[f"{number} 시험성적서.pdf"] = PDF_BYTES
        client = _FakeClient(tree, folders, blobs)

        log = self._log([self._project(n) for n in names], client, missing_numbers=["GS-A-25-9999"])

        listed = [line.split(" ")[0] for line in self._issues(log)]
        self.assertNotIn("TTA-26-00002", listed)  # 정상이라 이력 없음
        order = []
        for number in listed:
            if number not in order:
                order.append(number)
        self.assertEqual(order, ["TTA-26-00001", "TTA-26-00003", "GS-A-25-9999"])
        self.assertIn("요청 프로젝트 4건", log)

    def test_no_success_section_and_no_per_project_success_lines(self):
        client = self._client([self.WORD, self.PDF], {self.WORD: DOCX_BYTES, self.PDF: PDF_BYTES})

        log = self._log([self._project()], client)

        self.assertNotIn("[성공]", log)
        self.assertNotIn("있음 (", log)
        self.assertNotIn("개 파일", log)

    def test_failure_section_keeps_reasons(self):
        log = self._log([self._project()], self._client([]))

        self.assertIn("[실패·누락]", log)
        self.assertIn(f"{self.NUMBER}: 프로젝트 폴더는 찾았으나", log)

    def test_build_summary_is_stable_for_a_fixed_time(self):
        row = report.ProjectRow("TTA-26-00001", {"word": 1, "pdf": 0, "anon": 0}, source=report.SOURCE_ECM)

        text = report.build_summary([("TTA-26-00001", ["word/a.docx"], report.SOURCE_ECM)], [], [row], now=_datetime(2026, 10, 1, 20, 30, 12))

        self.assertEqual(text.splitlines()[:2], ["KOLAS 시험성적서 다운로드 결과", "생성 시각: 2026-10-01 20:30:12"])
        self.assertIn("TTA-26-00001 pdf 시험성적서 찾을 수 없음", text)

    def test_second_file_failure_of_the_same_kind_is_logged_even_when_one_succeeded(self):
        row = report.ProjectRow(
            "TTA-26-00001", {"word": 1, "pdf": 1, "anon": 0}, source=report.SOURCE_ECM,
            kind_errors={"word": "TTA-26-00001 시험성적서 복사본.docx: 무결성 검증 실패"},
        )

        lines = report.row_lines(row)

        self.assertEqual(len(lines), 1)
        self.assertIn("word 시험성적서 다운로드 실패", lines[0])
        self.assertIn("같은 형식의 다른 파일은 받음", lines[0])


class OfficeTempFileTests(_TempCacheMixin, SimpleTestCase):
    """zip/폴더에 함께 올라온 Office 임시(잠금) 파일 `~$...docx` 는 시험성적서로 보지 않는다."""

    def test_temp_file_names_are_detected(self):
        for name in ("~$-B-25-0110 시험성적서 v1.0.docx", "~$_X_XX_XXX_시험성적서_및_시험결과서1.docx", "~WRL0001.tmp",
                     "._GS-B-25-0110 시험성적서.docx", ".~lock.시험성적서.docx#", "폴더/~$GS-B-25-0110 시험성적서.docx"):
            self.assertTrue(report.is_temp_file_name(name), name)
        self.assertFalse(report.is_temp_file_name("GS-B-25-0110 시험성적서 v1.0.docx"))

    def test_temp_files_are_not_classified_as_reports_or_anonymous_reports(self):
        self.assertIsNone(report.classify_report_file("~$-B-25-0110 시험성적서 v1.0.docx"))
        self.assertIsNone(report.classify_report_file("~$ 시험성적서 - 익명.docx"))
        self.assertEqual(report.select_anonymous_report_files([_meta("~$ 시험성적서 - 익명.docx")]), [])

    def test_lock_files_inside_a_zip_do_not_cause_failures_and_the_project_is_stored(self):
        number = "GS-C-25-0091"
        lock = b"\x03TTA" + b"\x00" * 158  # 162바이트짜리 Office 소유자 파일
        archive = _build_zip([
            ("4.시험/라.종료/GS-C-25-0091 시험성적서 v1.0.docx", DOCX_BYTES),
            ("4.시험/라.종료/GS-C-25-0091 시험성적서 v1.0.pdf", PDF_BYTES),
            ("4.시험/라.종료/~$-B-25-0110 시험성적서 v1.0.docx", lock),
            ("4.시험/라.종료/~$_X_XX_XXX_시험성적서_및_시험결과서1_KOLAS비인정TTA마크_v1_0.docx", lock),
        ])
        client = _ZipProjectClient({f"{number}.zip": archive})
        pool = report._ClientPool(factory=lambda center: client)

        data = b"".join(report.iter_report_zip(
            [{"project_number": number, "center_code": "sangam", "cert_date_full": "2025-12-29"}], pool=pool,
        ))

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = sorted(name for name in zf.namelist() if name != report.SUMMARY_NAME)
            log = zf.read(report.SUMMARY_NAME).decode("utf-8-sig")
        self.assertEqual(names, [f"pdf/{number} 시험성적서 v1.0.pdf", f"word/{number} 시험성적서 v1.0.docx"])
        self.assertNotIn("실패", log.replace("실패·누락: 0건", ""))
        self.assertIn("실패·누락: 0건", log)
        # 실패가 없으니 서버 저장소에도 저장된다(이전에는 잠금 파일 때문에 저장되지 않았다).
        self.assertTrue((self.cache_dir / number / "_meta.json").exists())

    def test_lock_file_in_an_ecm_folder_is_ignored(self):
        number = "TTA-26-00001"
        names = [f"{number} 시험성적서.docx", f"{number} 시험성적서.pdf", f"~${number[1:]} 시험성적서.docx"]
        tree = {"P": {"folders": [], "files": [_meta(name) for name in names]}}
        client = _FakeClient(tree, {number: {"oid": "P", "name": "x"}}, {names[0]: DOCX_BYTES, names[1]: PDF_BYTES})
        pool = report._ClientPool(factory=lambda center: client)

        b"".join(report.iter_report_zip([{"project_number": number, "center_code": "sangam", "cert_date_full": ""}], pool=pool))

        self.assertEqual(sorted(client.downloaded), sorted(names[:2]))
        self.assertTrue((self.cache_dir / number / "_meta.json").exists())


# ---------------------------------------------------------------------------
# 결과서 다운로드 진행률 (KolasReportTask / 진행률 progress bar)
# ---------------------------------------------------------------------------
import uuid as _uuid

from main.models import KolasReportTask
from main.views.review import kolas_report_task as task_mod
from main.views.review.kolas_api import kolas_report_tasks


class _RecordingReporter:
    """iter_report_zip 이 호출하는 진행 기록 인터페이스만 흉내 내는 기록기."""

    def __init__(self, total):
        self.total = total
        self.events = []
        self.finished_rows = None

    def percent(self, index, fraction):
        return min(99, int((index + fraction) / self.total * 100))

    def step(self, index, number, text, fraction):
        self.events.append(("step", index, number, text, self.percent(index, fraction)))

    def project_done(self, index, number, text="완료"):
        self.events.append(("done", index, number, text, self.percent(index + 1, 0)))

    def finish(self, rows):
        self.finished_rows = rows
        self.events.append(("finish", None, None, "완료", 100))


class KolasReportProgressTests(_TempCacheMixin, TestCase):
    databases = {"default", "workflow", "reference"}

    def _project(self, number):
        return {"project_number": number, "center_code": "sangam", "cert_date_full": "2026-05-12"}

    def _client_for(self, numbers, with_pdf=True):
        folders, tree, blobs = {}, {}, {}
        for number in numbers:
            names = [f"{number} 시험성적서.docx"] + ([f"{number} 시험성적서.pdf"] if with_pdf else [])
            tree[number] = {"folders": [], "files": [_meta(name) for name in names]}
            folders[number] = {"oid": number, "name": f"{number} 회사"}
            blobs[f"{number} 시험성적서.docx"] = DOCX_BYTES
            blobs[f"{number} 시험성적서.pdf"] = PDF_BYTES
        return _FakeClient(tree, folders, blobs)

    def _run(self, projects, client, reporter, missing=()):
        pool = report._ClientPool(factory=lambda center: client)
        return b"".join(report.iter_report_zip(projects, missing_numbers=missing, pool=pool, reporter=reporter))

    # ----- 진행률 계산 -----
    def test_percent_is_rough_but_bounded_and_monotonic_per_project(self):
        reporter = task_mod.ReportTaskReporter(_uuid.uuid4(), 4)

        self.assertEqual(reporter.percent_for(0, 0.0), 0)
        self.assertEqual(reporter.percent_for(0, 0.5), 12)
        self.assertEqual(reporter.percent_for(2, 0.0), 50)
        self.assertEqual(reporter.percent_for(3, 1.0), 99)  # 정상 종료 전에는 100% 를 넘기지 않는다
        self.assertEqual(reporter.percent_for(0, 5.0), 25)   # 단계 비율은 0~1 로 보정
        self.assertEqual(task_mod.ReportTaskReporter(_uuid.uuid4(), 0).percent_for(0, 0.5), 0)

    def test_iter_reports_progress_for_every_project_and_ends_at_100(self):
        numbers = ["TTA-26-00001", "TTA-26-00002", "TTA-26-00003"]
        recorder = _RecordingReporter(total=4)

        self._run([self._project(n) for n in numbers], self._client_for(numbers), recorder, missing=["GS-A-25-9999"])

        percents = [event[4] for event in recorder.events]
        self.assertEqual(percents, sorted(percents))  # 거꾸로 가지 않는다
        done_indexes = [event[1] for event in recorder.events if event[0] == "done"]
        self.assertEqual(done_indexes, [0, 1, 2, 3])  # 프로젝트 3건 + 목록에 없는 번호 1건
        self.assertEqual(recorder.events[-1][0], "finish")
        self.assertLess(max(event[4] for event in recorder.events[:-1]), 101)
        self.assertEqual(len(recorder.finished_rows), 4)
        steps = {event[3] for event in recorder.events if event[0] == "step"}
        self.assertIn("ECM 프로젝트 폴더·zip 탐색 중", steps)
        self.assertTrue(any(text.startswith("시험성적서 받는 중") for text in steps))

    def test_storage_hit_reports_fast_path_steps(self):
        number = "TTA-26-00001"
        self._run([self._project(number)], self._client_for([number]), _RecordingReporter(1))
        recorder = _RecordingReporter(1)

        self._run([self._project(number)], self._client_for([number]), recorder)

        texts = [event[3] for event in recorder.events]
        self.assertIn("서버 저장본 전달 중", texts)
        self.assertNotIn("ECM 프로젝트 폴더·zip 탐색 중", texts)

    def test_failed_project_still_advances_progress(self):
        recorder = _RecordingReporter(total=2)

        self._run(
            [self._project("TTA-26-00001"), self._project("TTA-26-00002")],
            _FakeClient({}, {}, {}),  # 어떤 프로젝트도 ECM 에 없음
            recorder,
        )

        self.assertEqual([event[1] for event in recorder.events if event[0] == "done"], [0, 1])
        self.assertEqual(recorder.events[-1][4], 100)

    # ----- DB 기록 -----
    def test_real_reporter_writes_task_row_through_completion(self):
        task_id = _uuid.uuid4()
        numbers = ["TTA-26-00001", "TTA-26-00002"]
        reporter = task_mod.ReportTaskReporter.start(task_id, 2, requested_ip="10.0.0.5", min_interval=0)

        self._run([self._project(n) for n in numbers], self._client_for(numbers, with_pdf=False), reporter)

        task = KolasReportTask.objects.using("workflow").get(pk=task_id)
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.percent, 100)
        self.assertEqual((task.total_projects, task.done_projects), (2, 2))
        self.assertEqual((task.complete_count, task.partial_count, task.none_count), (0, 2, 0))
        self.assertEqual(task.requested_ip, "10.0.0.5")
        self.assertIsNotNone(task.finished_at)

    def test_running_task_is_visible_with_partial_progress(self):
        task_id = _uuid.uuid4()
        reporter = task_mod.ReportTaskReporter.start(task_id, 4, min_interval=0)

        reporter.step(1, "TTA-26-00002", "시험성적서 받는 중 (1/2)", 0.5)

        task = KolasReportTask.objects.using("workflow").get(pk=task_id)
        self.assertEqual(task.status, "running")
        self.assertEqual(task.percent, 37)  # (1 + 0.5) / 4
        self.assertEqual(task.current_project, "TTA-26-00002")
        self.assertEqual(task.done_projects, 1)

    def test_tracked_stream_marks_canceled_when_browser_stops_downloading(self):
        task_id = _uuid.uuid4()
        reporter = task_mod.ReportTaskReporter.start(task_id, 3)

        stream = task_mod.tracked_stream(iter([b"a", b"b", b"c"]), reporter)
        next(stream)
        stream.close()

        task = KolasReportTask.objects.using("workflow").get(pk=task_id)
        self.assertEqual(task.status, "canceled")
        self.assertIsNotNone(task.finished_at)

    def test_tracked_stream_marks_failed_on_exception(self):
        task_id = _uuid.uuid4()
        reporter = task_mod.ReportTaskReporter.start(task_id, 3)

        def broken():
            yield b"a"
            raise RuntimeError("ECM 연결 끊김")

        with self.assertRaises(RuntimeError):
            list(task_mod.tracked_stream(broken(), reporter))

        task = KolasReportTask.objects.using("workflow").get(pk=task_id)
        self.assertEqual(task.status, "failed")
        self.assertIn("ECM 연결 끊김", task.error_message)

    def test_completed_task_is_not_overwritten_by_late_cancel(self):
        task_id = _uuid.uuid4()
        reporter = task_mod.ReportTaskReporter.start(task_id, 1)
        reporter.finish([])

        reporter.cancel()

        self.assertEqual(KolasReportTask.objects.using("workflow").get(pk=task_id).status, "completed")

    def test_progress_writes_are_throttled_for_the_same_project(self):
        clock = [0.0]
        task_id = _uuid.uuid4()
        reporter = task_mod.ReportTaskReporter.start(task_id, 10, min_interval=1.0, clock=lambda: clock[0])
        reporter.step(0, "A", "단계1", 0.1)
        clock[0] = 0.2
        reporter.step(0, "A", "단계2", 0.5)  # 0.2초 뒤 같은 프로젝트: 건너뜀
        self.assertEqual(KolasReportTask.objects.using("workflow").get(pk=task_id).current_step, "단계1")
        clock[0] = 1.5
        reporter.step(0, "A", "단계3", 0.6)
        self.assertEqual(KolasReportTask.objects.using("workflow").get(pk=task_id).current_step, "단계3")
        clock[0] = 1.6
        reporter.step(1, "B", "다른 프로젝트", 0.0)  # 프로젝트가 바뀌면 즉시 기록
        self.assertEqual(KolasReportTask.objects.using("workflow").get(pk=task_id).current_project, "B")

    def test_database_write_failure_never_breaks_the_download(self):
        reporter = task_mod.ReportTaskReporter(_uuid.uuid4(), 1, min_interval=0)

        with mock.patch.object(task_mod.KolasReportTask.objects, "using", side_effect=RuntimeError("db down")):
            reporter.step(0, "A", "x", 0.5)
            reporter.project_done(0, "A")
            reporter.finish([])
            reporter.cancel()
            reporter.fail("x")

    def test_stale_running_tasks_are_closed_when_listing(self):
        task = KolasReportTask.objects.using("workflow").create(status="running", total_projects=3, percent=40)
        KolasReportTask.objects.using("workflow").filter(pk=task.pk).update(
            updated_at=task_mod.timezone.now() - task_mod.timedelta(seconds=task_mod.STALE_AFTER_SECONDS + 60)
        )

        items = task_mod.list_tasks()

        self.assertEqual(items[0]["status"], "failed")
        self.assertIn("중단", items[0]["current_step"])

    # ----- API -----
    def test_tasks_endpoint_lists_newest_first_with_progress_fields(self):
        old = KolasReportTask.objects.using("workflow").create(status="completed", percent=100, total_projects=2, done_projects=2)
        new = KolasReportTask.objects.using("workflow").create(
            status="running", percent=40, total_projects=5, done_projects=2, current_project="TTA-26-00003", current_step="시험성적서 받는 중 (1/2)",
        )
        KolasReportTask.objects.using("workflow").filter(pk=old.pk).update(started_at=task_mod.timezone.now() - task_mod.timedelta(minutes=5))

        response = kolas_report_tasks(RequestFactory().get("/kolas/api/report-tasks/"))
        items = json.loads(response.content)["items"]

        self.assertEqual([item["id"] for item in items], [str(new.id), str(old.id)])
        first = items[0]
        self.assertEqual(
            (first["status"], first["status_label"], first["percent"], first["done_projects"], first["total_projects"]),
            ("running", "진행 중", 40, 2, 5),
        )
        self.assertEqual(first["current_project"], "TTA-26-00003")

    def test_tasks_endpoint_returns_empty_list_when_table_is_missing(self):
        with mock.patch.object(task_mod.KolasReportTask.objects, "using", side_effect=RuntimeError("no such table")):
            response = kolas_report_tasks(RequestFactory().get("/kolas/api/report-tasks/"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["items"], [])

    def test_tasks_endpoint_limit_and_bad_limit(self):
        for _ in range(3):
            KolasReportTask.objects.using("workflow").create(status="completed", percent=100)

        limited = json.loads(kolas_report_tasks(RequestFactory().get("/x", {"limit": "2"})).content)["items"]
        bad = json.loads(kolas_report_tasks(RequestFactory().get("/x", {"limit": "abc"})).content)["items"]

        self.assertEqual(len(limited), 2)
        self.assertEqual(len(bad), 3)

    def test_download_view_creates_task_with_client_supplied_id_and_finishes_it(self):
        KolasProject.objects.using("reference").create(
            project_number="GS-A-25-0001", center_code="sangam", cert_committee_date=date(2025, 12, 29),
        )
        task_id = str(_uuid.uuid4())

        def fake_iter(projects, *, missing_numbers=(), pool=None, refresh=False, reporter=None):
            reporter.step(0, "GS-A-25-0001", "시험성적서 받는 중", 0.5)
            reporter.project_done(0, "GS-A-25-0001")
            reporter.finish([])
            yield b"PK\x05\x06" + b"\x00" * 18

        request = RequestFactory().post(
            "/kolas/api/report-download/", {"pn": ["GS-A-25-0001"], "task_id": task_id}, HTTP_HOST="testserver", REMOTE_ADDR="10.1.2.3",
        )
        request._dont_enforce_csrf_checks = True
        with mock.patch("main.views.review.kolas_api.iter_report_zip", fake_iter):
            response = kolas_report_download(request)
            self.assertEqual(KolasReportTask.objects.using("workflow").get(pk=task_id).status, "running")
            b"".join(response.streaming_content)

        task = KolasReportTask.objects.using("workflow").get(pk=task_id)
        self.assertEqual((task.status, task.percent, task.total_projects), ("completed", 100, 1))
        self.assertEqual(task.requested_ip, "10.1.2.3")

    def test_download_view_generates_id_when_client_id_is_invalid_and_counts_missing_projects(self):
        KolasProject.objects.using("reference").create(project_number="GS-A-25-0001", center_code="sangam")

        def fake_iter(projects, *, missing_numbers=(), pool=None, refresh=False, reporter=None):
            reporter.finish([])
            yield b"x"

        request = RequestFactory().post(
            "/kolas/api/report-download/", {"pn": ["GS-A-25-0001", "GS-A-25-0002"], "task_id": "not-a-uuid"}, HTTP_HOST="testserver",
        )
        request._dont_enforce_csrf_checks = True
        with mock.patch("main.views.review.kolas_api.iter_report_zip", fake_iter):
            b"".join(kolas_report_download(request).streaming_content)

        task = KolasReportTask.objects.using("workflow").get()
        self.assertEqual(task.total_projects, 2)  # 목록에 있는 1건 + 없는 1건

    def test_no_task_is_created_for_rejected_requests(self):
        request = RequestFactory().post("/kolas/api/report-download/", {"pn": []}, HTTP_HOST="testserver")
        request._dont_enforce_csrf_checks = True

        b"".join(kolas_report_download(request).streaming_content)

        self.assertFalse(KolasReportTask.objects.using("workflow").exists())

    def test_parse_task_id(self):
        valid = str(_uuid.uuid4())
        self.assertEqual(str(task_mod.parse_task_id(valid)), valid)
        self.assertIsInstance(task_mod.parse_task_id(""), _uuid.UUID)
        self.assertIsInstance(task_mod.parse_task_id("'; DROP TABLE x;--"), _uuid.UUID)


# ---------------------------------------------------------------------------
# 한 셀에 프로젝트 번호가 여러 줄(원시험 + 추가시험)인 경우: 마지막 줄 번호를 쓴다
# ---------------------------------------------------------------------------
def _custom_round(committee, data_rows):
    """data_rows: 각 행의 [회사(제품), WD, 신청일, 계약일, 시작일, 종료예정일, 시험원, 프로젝트번호] (셀 안 줄바꿈 허용)."""
    out = [
        ["가. 일시", committee],
        ["나. 장소", "TTA B1층 고객상담실"],
        ["다. 안건", "SW에 대한 품질인증심의"],
        HEADER,
    ]
    for index, (company, wd, request, contract, start, end, tester, number) in enumerate(data_rows, start=1):
        out.append([str(index), company, wd, request, contract, start, end, tester, number, "상담자"])
    out.append([])
    return out


MULTI_CENTER_MAP = {"송현경": ("sangam", "상암"), "방영규": ("bundang", "분당"), "정은하": ("yeongnam", "영남")}


class LastProjectNumberInCellTests(SimpleTestCase):
    def _parse(self, *data_rows):
        parsed, warnings = kolas_sheet.parse_kolas_sheet(
            _custom_round("2026. 9. 7", data_rows), gid="g", center_map=MULTI_CENTER_MAP,
        )
        self.assertEqual(warnings, [])
        return parsed

    def test_only_the_last_project_number_of_a_multi_line_cell_becomes_a_project(self):
        parsed = self._parse(
            ("㈜모노플로우-MonoGPT v1.0(MonoGPT v1.0)", "20\n3", "26/03/03,화\n26/08/05,수", "26/06/15,월\n26/08/18,화",
             "26/08/03,월\n26/09/01,화", "26/08/31,월\n26/09/03, 목", "송현경(공공)", "TTA-26-00681\nTTA-26-02872"),
        )

        self.assertEqual([row.project_number for row in parsed], ["TTA-26-02872"])  # 첫 줄 TTA-26-00681 은 만들지 않는다

    def test_other_cells_use_the_last_line_so_the_end_date_filter_follows_the_last_project(self):
        (row,) = self._parse(
            ("㈜모노플로우-MonoGPT v1.0(MonoGPT v1.0)", "20\n3", "26/03/03,화\n26/08/05,수", "26/06/15,월\n26/08/18,화",
             "26/08/03,월\n26/09/01,화", "26/08/31,월\n26/09/03, 목", "송현경(공공)", "TTA-26-00681\nTTA-26-02872"),
        )

        self.assertEqual(row.wd, "3")
        self.assertEqual(row.request_date, "26/08/05,수")
        self.assertEqual(row.contract_date, "26/08/18,화")
        self.assertEqual(row.start_date, "26/09/01,화")
        self.assertEqual(row.expected_end_date, "26/09/03, 목")
        self.assertEqual(row.expected_end_on, date(2026, 9, 3))  # 첫 줄(8/31)이 아니라 마지막 줄

    def test_three_numbers_pick_the_third(self):
        (row,) = self._parse(
            ("주식회사 새움-SLPR-Cloud V3.0\n(SLPR-Cloud V3.0)", "13\n14\n3", "26/03/09,월\n26/06/05,금\n26/07/06,월",
             "26/03/25,수\n26/06/09,화\n26/07/07,화", "26/05/26,화\n26/06/15,월\n26/07/13,월",
             "26/06/12,금\n26/07/02,목\n26/07/15,수", "방영규", "TTA-26-00774\nTTA-26-01825\nTTA-26-02244"),
        )

        self.assertEqual(row.project_number, "TTA-26-02244")
        self.assertEqual(row.wd, "3")
        self.assertEqual(row.expected_end_on, date(2026, 7, 15))
        # 회사(제품) 칸은 2줄(번호는 3개)이라 프로젝트별 줄이 아니므로 자르지 않는다.
        self.assertIn("SLPR-Cloud", row.product)
        self.assertIn("주식회사 새움", row.company)

    def test_dates_joined_by_space_instead_of_newline_are_split(self):
        (row,) = self._parse(
            ("㈜니어네트웍스-링크칼 v1", "14\n3", "25/09/04,목\n25/10/02,목", "25/09/04,목\n25/10/13,월",
             "25/09/16,화\n25/11/04,화", "25/10/10,금 25/11/06,목", "방영규", "GS-C-25-0064\nGS-C-25-0074"),
        )

        self.assertEqual(row.project_number, "GS-C-25-0074")
        self.assertEqual(row.expected_end_date, "25/11/06,목")
        self.assertEqual(row.expected_end_on, date(2025, 11, 6))

    def test_shared_single_value_cells_are_kept_for_the_last_project(self):
        (row,) = self._parse(
            ("(주)한일환경테크-EMS Monitoring System", "10\n2", "25/11/21,금", "25/11/28,금",
             "25/11/05,수\n25/12/01,월", "25/11/19,수\n25/12/02,화", "방영규", "GS-C-25-0076\nGS-C-25-0098"),
        )

        self.assertEqual(row.request_date, "25/11/21,금")  # 두 프로젝트가 같은 칸을 공유
        self.assertEqual(row.contract_date, "25/11/28,금")
        self.assertEqual(row.expected_end_on, date(2025, 12, 2))

    def test_tester_cell_with_one_line_per_project_uses_the_last_testers_center(self):
        (row,) = self._parse(
            ("㈜제이콥시스템-ATZone v2.0(ATZone v2.0)", "18\n6", "25/12/29,월", "25/12/29,월\n26/03/31,화",
             "26/02/27,금\n26/04/10,금", "26/03/25,수\n26/04/17,금", "정은하\n방영규", "GS-A-25-0280\nTTA-26-00979"),
        )

        self.assertEqual(row.project_number, "TTA-26-00979")
        self.assertEqual(row.primary_tester, "방영규")
        self.assertEqual(row.center_code, "bundang")  # 첫 줄 시험원(정은하/영남)이 아니라 마지막 줄 시험원

    def test_comma_separated_testers_stay_whole(self):
        (row,) = self._parse(
            ("주식회사 제이솔루션-JSOL-CMS(CMS솔루션) v1.0", "14\n1", "25/02/21,금\n26/01/23,금", "25/12/26,금\n26/01/27,화",
             "26/01/27,화\n26/02/19,목", "26/02/13,금\n26/02/19,목", "송현경, 방영규", "GS-C-25-0110\nTTA-26-00321"),
        )

        self.assertEqual(row.pl, "송현경, 방영규")
        self.assertEqual(row.primary_tester, "송현경")  # 줄이 번호 수와 맞지 않으면 시험원 칸은 그대로 둔다
        self.assertEqual(row.project_number, "TTA-26-00321")

    def test_single_number_rows_are_unchanged_and_still_use_the_first_line(self):
        (row,) = self._parse(
            ("㈜에이-제품A", "17\n(추가)", "26/05/28,목\n메모", "26/06/17,수", "26/08/28,금", "26/09/21,월\n26/09/22,화", "송현경", "TTA-26-01716"),
        )

        self.assertEqual(row.project_number, "TTA-26-01716")
        self.assertEqual(row.wd, "17")
        self.assertEqual(row.expected_end_date, "26/09/21,월")

    def test_range_filter_uses_the_last_lines_end_date(self):
        rows = self._parse(
            # 첫 줄 종료예정일은 범위 밖(2025-05-01), 마지막 줄은 범위 안(2025-12-02)
            ("회사A-제품A", "10\n2", "25/04/01,화", "25/04/02,수", "25/04/10,목\n25/11/05,수", "25/05/01,목\n25/12/02,화", "방영규", "GS-C-25-0100\nGS-C-25-0101"),
        )

        selected, undated = kolas_sheet.filter_by_expected_end(rows)

        self.assertEqual([row.project_number for row in selected], ["GS-C-25-0101"])
        self.assertEqual(undated, [])

    def test_duplicate_numbers_in_one_cell_count_once(self):
        parsed = self._parse(
            ("회사-제품", "10", "25/04/01,화", "25/04/02,수", "25/04/10,목", "25/12/02,화", "방영규", "GS-C-25-0101\nGS-C-25-0101"),
        )

        self.assertEqual([row.project_number for row in parsed], ["GS-C-25-0101"])


class KolasSyncMultiNumberTests(KolasDbTestCase):
    def _write_csvs(self, directory):
        rows_2026 = _custom_round("2026. 9. 7", [
            ("㈜모노플로우-MonoGPT v1.0", "20\n3", "26/03/03,화\n26/08/05,수", "26/06/15,월\n26/08/18,화",
             "26/08/03,월\n26/09/01,화", "26/08/31,월\n26/09/03, 목", "송현경", "TTA-26-00681\nTTA-26-02872"),
        ])
        rows_2025 = _round_2025_layout("2025년 12월 29일(월)", [("회사B-제품B", "25/12/17,수", "임우섭", "GS-C-25-0077")])
        path_2026 = Path(directory) / "2026.csv"
        path_2025 = Path(directory) / "2025.csv"
        path_2026.write_text(_csv_text(rows_2026), encoding="utf-8")
        path_2025.write_text(_csv_text(rows_2025), encoding="utf-8")
        return str(path_2026), str(path_2025)

    def _sync(self, **options):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path_2026, path_2025 = self._write_csvs(directory)
            call_command("sync_kolas_projects", csv_2026=path_2026, csv_2025=path_2025, stdout=out, **options)
        return out.getvalue()

    def _numbers(self):
        return set(KolasProject.objects.using("reference").values_list("project_number", flat=True))

    def test_sync_loads_only_the_last_number_of_a_multi_number_cell(self):
        self._sync()

        self.assertEqual(self._numbers(), {"TTA-26-02872", "GS-C-25-0077"})

    def test_previously_loaded_first_line_number_is_reported_and_removed_by_prune(self):
        self._kolas("TTA-26-00681", expected_end_on=date(2026, 8, 31))  # 이전 규칙으로 적재된 첫 줄 번호

        report_text = self._sync()
        self.assertIn("이번 대상에는 없지만 DB 에 남아 있는 행 1건", report_text)
        self.assertIn("TTA-26-00681", report_text)
        self.assertIn("TTA-26-00681", self._numbers())  # --prune 이 없으면 지우지 않는다

        pruned = self._sync(prune=True)
        self.assertIn("삭제 1건", pruned)
        self.assertNotIn("TTA-26-00681", self._numbers())

    def test_prune_keeps_stale_rows_that_already_have_a_review_result(self):
        self._kolas("TTA-26-00681", expected_end_on=date(2026, 8, 31), review_result="O")

        text = self._sync(prune=True)

        self.assertIn("점검결과 있어 보존 1건", text)
        self.assertIn("TTA-26-00681", self._numbers())

    def test_dry_run_reports_stale_rows_without_deleting(self):
        self._kolas("TTA-26-00681", expected_end_on=date(2026, 8, 31))

        text = self._sync(dry_run=True, prune=True)

        self.assertIn("이번 대상에는 없지만 DB 에 남아 있는 행 1건", text)
        self.assertIn("TTA-26-00681", self._numbers())
