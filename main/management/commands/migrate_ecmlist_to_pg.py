import re
import sqlite3
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from main.models import ReferenceProject
from main.views.review.ecm_download_review_centers import (
    CENTER_BUNDANG,
    CENTER_SANGAM,
    CENTER_YEONGNAM,
    center_label,
    reference_db_path,
)

ARTIFACT_COLUMNS = (
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
)


def _parse_cert_date(value):
    if not value:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.match(r"^(\d{4})-(\d{2})$", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            pass
    return None


class Command(BaseCommand):
    help = "ecmlist.db (SQLite) 데이터를 PostgreSQL reference_project 테이블로 이전합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--db-alias",
            default=getattr(settings, "REFERENCE_DATABASE_ALIAS", "reference"),
            help="대상 Django DB alias (기본: reference)",
        )
        parser.add_argument(
            "--center",
            default=None,
            help="이전할 센터 코드 (생략 시 모든 센터)",
        )

    def handle(self, *args, **options):
        alias = options["db_alias"]
        target = options["center"]

        centers = [CENTER_SANGAM, CENTER_YEONGNAM, CENTER_BUNDANG]
        if target:
            centers = [target]

        total_created = total_updated = 0
        for center_code in centers:
            db_path = Path(reference_db_path(center_code))
            if not db_path.exists():
                self.stdout.write(f"  [건너뜀] {center_code}: {db_path} 없음")
                continue

            self.stdout.write(f"▶ {center_code} ← {db_path}")
            created, updated = self._migrate_center(db_path, center_code, alias)
            self.stdout.write(f"  신규 {created}건, 갱신 {updated}건")
            total_created += created
            total_updated += updated

        self.stdout.write(
            self.style.SUCCESS(f"이전 완료: 신규 {total_created}건, 갱신 {total_updated}건")
        )

    def _migrate_center(self, db_path, center_code, alias):
        table = getattr(settings, "REFERENCE_DB_TABLE", "ecm_list")
        label = center_label(center_code)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        finally:
            conn.close()

        def col(row, name, default=""):
            return (row[name] or default).strip() if name in columns else default

        created = updated = 0
        for row in rows:
            project_number = col(row, "프로젝트번호")
            if not project_number:
                continue

            cert_date_str = col(row, "인증일자")
            artifact_json = {c: col(row, c, "X") for c in ARTIFACT_COLUMNS}

            defaults = {
                "center_label": label,
                "cert_date": cert_date_str,
                "cert_committee_date": _parse_cert_date(cert_date_str),
                "company": col(row, "회사명"),
                "product": col(row, "제품명"),
                "pl": col(row, "시험PL"),
                "wd": col(row, "WD"),
                "request_date": col(row, "신청일"),
                "contract_date": col(row, "계약일"),
                "review_result": col(row, "점검결과"),
                "inspection_date": col(row, "점검날짜"),
                "artifact_results_json": artifact_json,
            }

            _, is_created = ReferenceProject.objects.using(alias).update_or_create(
                project_number=project_number,
                center_code=center_code,
                defaults=defaults,
            )
            if is_created:
                created += 1
            else:
                updated += 1

        return created, updated
