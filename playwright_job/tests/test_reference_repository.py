import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from playwright_job.reference_repository import (
    ECM_COLUMNS,
    EcmProjectRepository,
    ReferenceColumnMismatch,
    ReferenceDbNotFound,
)


def create_reference_db(path: Path, columns: tuple[str, ...] = ECM_COLUMNS) -> None:
    quoted_columns = ", ".join(f'"{column}" TEXT' for column in columns)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f'CREATE TABLE ecm ({quoted_columns})')
        conn.commit()


def insert_project(path: Path, **values: str) -> None:
    columns = tuple(values.keys())
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            f"INSERT INTO ecm ({quoted_columns}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )
        conn.commit()


class EcmProjectRepositoryTests(unittest.TestCase):
    def test_validate_schema_accepts_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "reference.db"
            create_reference_db(db_path)

            EcmProjectRepository(db_path).validate_schema()

    def test_validate_schema_rejects_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "reference.db"
            create_reference_db(db_path, ECM_COLUMNS[:-1])

            with self.assertRaises(ReferenceColumnMismatch):
                EcmProjectRepository(db_path).validate_schema()

    def test_missing_db_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "reference.db"

            with self.assertRaises(ReferenceDbNotFound):
                EcmProjectRepository(db_path).count_projects()

    def test_get_project_by_project_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "reference.db"
            create_reference_db(db_path)
            insert_project(
                db_path,
                번호="9",
                인증일자="2026-01-31",
                프로젝트번호="TTA-26-00009",
                회사명="우리데이터 주식회사",
                제품명="우리데이터클리닉 V1.0",
                시험PL="홍길동",
                점검결과="완료",
            )

            project = EcmProjectRepository(db_path).get_project("TTA-26-00009")

            self.assertIsNotNone(project)
            self.assertEqual(project["프로젝트번호"], "TTA-26-00009")
            self.assertEqual(project["회사명"], "우리데이터 주식회사")

    def test_list_projects_filters_with_like(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "reference.db"
            create_reference_db(db_path)
            insert_project(
                db_path,
                번호="9",
                인증일자="2026-01-31",
                프로젝트번호="TTA-26-00009",
                회사명="우리데이터 주식회사",
                제품명="우리데이터클리닉 V1.0",
                시험PL="홍길동",
                점검결과="완료",
            )
            insert_project(
                db_path,
                번호="10",
                인증일자="2026-02-01",
                프로젝트번호="TTA-26-00010",
                회사명="다른회사",
                제품명="다른제품",
                시험PL="김철수",
                점검결과="대기",
            )

            repo = EcmProjectRepository(db_path)
            projects = repo.list_projects({"company": "우리데이터"})

            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0]["프로젝트번호"], "TTA-26-00009")
            self.assertEqual(repo.count_projects({"company": "우리데이터"}), 1)


if __name__ == "__main__":
    unittest.main()
