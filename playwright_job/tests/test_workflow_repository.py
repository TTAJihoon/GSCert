import tempfile
import unittest
from pathlib import Path

from playwright_job.workflow_repository import (
    WorkflowJobNotFound,
    WorkflowRepository,
)


class WorkflowRepositoryTests(unittest.TestCase):
    def test_create_job_with_projects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = WorkflowRepository(Path(tmp_dir) / "workflow.db")

            job_id = repo.create_job(
                ["TTA-26-00009", "TTA-26-00010"],
                ecm_rows_by_project={
                    "TTA-26-00009": {"회사명": "우리데이터 주식회사"},
                },
            )

            job = repo.get_job(job_id)
            projects = repo.list_job_projects(job_id)

            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "pending")
            self.assertEqual(job["requested_project_count"], "2")
            self.assertEqual(len(projects), 2)
            self.assertEqual(projects[0]["project_number"], "TTA-26-00009")

    def test_update_job_and_project_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = WorkflowRepository(Path(tmp_dir) / "workflow.db")
            job_id = repo.create_job(["TTA-26-00009"])

            repo.update_job_status(job_id, "running", progress_message="다운로드 준비")
            repo.update_project_status(
                job_id,
                "TTA-26-00009",
                "completed",
                current_step="검사 완료",
                zip_path="C:\\Downloads\\TTA-26-00009.zip",
            )
            repo.refresh_job_counts(job_id)

            job = repo.get_job(job_id)
            project = repo.list_job_projects(job_id)[0]

            self.assertEqual(job["status"], "running")
            self.assertEqual(job["completed_project_count"], "1")
            self.assertEqual(project["status"], "completed")
            self.assertEqual(project["zip_path"], "C:\\Downloads\\TTA-26-00009.zip")

    def test_try_acquire_lock_blocks_second_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = WorkflowRepository(Path(tmp_dir) / "workflow.db")
            first_job_id = repo.create_job(["TTA-26-00009"])
            second_job_id = repo.create_job(["TTA-26-00010"])

            self.assertTrue(repo.try_acquire_lock(first_job_id))
            self.assertFalse(repo.try_acquire_lock(second_job_id))

            lock = repo.get_lock()
            self.assertEqual(lock["locked"], "Y")
            self.assertEqual(lock["job_id"], first_job_id)

            self.assertTrue(repo.release_lock(first_job_id))
            self.assertTrue(repo.try_acquire_lock(second_job_id))

    def test_release_lock_requires_same_job_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = WorkflowRepository(Path(tmp_dir) / "workflow.db")
            job_id = repo.create_job(["TTA-26-00009"])

            self.assertTrue(repo.try_acquire_lock(job_id))
            self.assertFalse(repo.release_lock("other-job"))
            self.assertEqual(repo.get_lock()["locked"], "Y")

    def test_update_unknown_job_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = WorkflowRepository(Path(tmp_dir) / "workflow.db")
            repo.initialize_schema()

            with self.assertRaises(WorkflowJobNotFound):
                repo.update_job_status("missing", "running")


if __name__ == "__main__":
    unittest.main()
