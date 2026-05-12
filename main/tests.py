import json
import sqlite3
import tempfile
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase, TestCase

from main.models import (
    DownloadReviewJob,
    DownloadReviewJobStatus,
    DownloadReviewProject,
    DownloadReviewProjectReviewStatus,
    DownloadReviewProjectStatus,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
)
from main.services.reference_db import (
    ARTIFACT_REVIEW_COLUMNS,
    ReferenceDbError,
    ReferenceDbMissing,
    ReferenceQueryError,
    write_project_review_result,
)
from main.services.download_review_worker import run_worker_once
from main.services.download_verify import verify_downloaded_files
from main.views.download_review_api import (
    active_job,
    job_detail,
    job_project_results,
    job_projects,
    jobs,
    projects,
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


class DownloadReviewProjectsApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reference_db_path = Path(self.temp_dir.name) / "ecmlist.db"
        self._create_reference_db()

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
                        "완료",
                        "2026.05.12 20:30",
                    ),
                    (
                        "TTA-26-00010",
                        "05/13",
                        "에이치소프트",
                        "SecureFlow 2.1",
                        "김준호",
                        "미점검",
                        "",
                    ),
                    (
                        "TTA-26-00008",
                        "05/11",
                        "넥스트랩",
                        "NextLab QA Suite",
                        "최유진",
                        "수정 필요",
                        "2026.05.11 21:00",
                    ),
                ],
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
        self._create_reference_db()

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
        self.assertEqual(reference_rows["TTA-26-00010"]["점검결과"], "완료")
        self.assertEqual(reference_rows["TTA-26-00010"]["회사명"], "에이치소프트")
        self.assertEqual(reference_rows["TTA-26-00010"]["계약서"], "정상")
        self.assertEqual(reference_rows["TTA-26-00010"]["시험성적서(PDF)"], "정상")
        self.assertNotEqual(reference_rows["TTA-26-00010"]["점검날짜"], "")
        self.assertFalse(projects_data["items"][0]["selectable"])
        self.assertEqual(reference_rows["TTA-26-00011"]["점검결과"], "수정 필요")
        self.assertEqual(reference_rows["TTA-26-00011"]["시험성적서(PDF)"], "부적합")
        self.assertEqual(reference_rows["TTA-26-00012"]["점검결과"], "보류")
        self.assertEqual(reference_rows["TTA-26-00012"]["계약서"], "X")

    def test_write_back_rejects_non_review_columns(self):
        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            with self.assertRaises(ReferenceQueryError):
                write_project_review_result(
                    "TTA-26-00010",
                    "완료",
                    artifact_results={"회사명": "변조된 회사명"},
                )

        row = self._reference_rows(["TTA-26-00010"], ["점검결과", "회사명"])["TTA-26-00010"]
        self.assertEqual(row["점검결과"], "미점검")
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
                    "미점검",
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
        self.assertEqual([row["점검결과"] for row in rows], ["미점검", "미점검"])

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
        self.assertEqual(row["점검결과"], "완료")
        self.assertEqual(row["계약서"], "정상")

    def _post_job(self, project_numbers):
        request = self.factory.post(
            "/api/jobs/",
            data=json.dumps({"project_numbers": project_numbers}),
            content_type="application/json",
            REMOTE_ADDR="127.0.0.1",
        )
        with self.settings(REFERENCE_DB_PATH=self.reference_db_path, REFERENCE_DB_TABLE="ecm_list"):
            return jobs(request)

    def _create_reference_db(self):
        conn = sqlite3.connect(self.reference_db_path)
        try:
            artifact_columns_sql = ",\n".join(
                f'"{column}" TEXT DEFAULT \'X\''
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
                        "완료",
                        "2026.05.12 20:30",
                    ),
                    (
                        "TTA-26-00010",
                        "05/13",
                        "에이치소프트",
                        "SecureFlow 2.1",
                        "김준호",
                        "미점검",
                        "",
                    ),
                    (
                        "TTA-26-00011",
                        "05/14",
                        "브릿지웨어",
                        "BridgeHub",
                        "박지훈",
                        "미점검",
                        "",
                    ),
                    (
                        "TTA-26-00012",
                        "05/15",
                        "넥스트랩",
                        "NextLab QA Suite",
                        "최유진",
                        "미점검",
                        "",
                    ),
                ],
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
                f'"{column}" TEXT DEFAULT \'X\''
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
                ("TTA-26-09999", "05/12", "옵션테스트", "NoDate", "박지훈", "미점검"),
            )
            conn.commit()
        finally:
            conn.close()
