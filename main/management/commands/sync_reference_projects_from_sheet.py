from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from main.models import ReferenceCenterPl, ReferenceProject
from main.utils.ecm_reference_sheet import (
    CENTER_PL_NAMES,
    DEFAULT_GID,
    DEFAULT_SPREADSHEET_ID,
    build_pl_center_map,
    download_sheet_csv,
    parse_sheet_projects,
    read_csv_rows,
)


BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Google Sheet 인증위 프로젝트 목록을 PostgreSQL reference DB에 적재합니다."

    def add_arguments(self, parser):
        parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
        parser.add_argument("--gid", default=DEFAULT_GID)
        parser.add_argument("--source-csv", default=None, help="네트워크 대신 읽을 CSV 파일 경로")
        parser.add_argument("--database", default="reference", help="대상 DB alias")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--no-schema-check",
            action="store_true",
            help="대상 테이블 자동 생성 확인을 건너뜁니다.",
        )

    def handle(self, *args, **options):
        db_alias = options["database"]
        if not options["dry_run"] and db_alias not in connections:
            raise CommandError(f"설정에 없는 DB alias입니다: {db_alias}")

        if not options["dry_run"] and not options["no_schema_check"]:
            self._ensure_tables(db_alias)

        csv_text = self._load_csv(options)
        projects = parse_sheet_projects(read_csv_rows(csv_text), center_map=build_pl_center_map())
        if not projects:
            self.stdout.write("시트에서 적재할 프로젝트를 찾지 못했습니다.")
            return

        unknown = sorted({row.primary_tester for row in projects if row.center_code == "unknown"})
        if unknown:
            self.stdout.write(self.style.WARNING("센터 미분류 PL: " + ", ".join(unknown)))

        if options["dry_run"]:
            self.stdout.write(f"dry-run: 프로젝트 {len(projects)}건, PL 매핑 {self._pl_count()}건")
            self._print_center_summary(projects)
            return

        self._sync_pl_map(db_alias)
        inserted, updated = self._sync_projects(db_alias, projects, options["spreadsheet_id"], options["gid"])
        self._print_center_summary(projects)
        self.stdout.write(self.style.SUCCESS(f"적재 완료: 신규 {inserted}건, 갱신 {updated}건"))

    def _load_csv(self, options):
        source_csv = options.get("source_csv")
        if source_csv:
            with open(source_csv, "r", encoding="utf-8-sig", newline="") as file:
                return file.read()
        return download_sheet_csv(options["spreadsheet_id"], options["gid"])

    def _ensure_tables(self, db_alias):
        connection = connections[db_alias]
        existing = set(connection.introspection.table_names())
        models = [ReferenceCenterPl, ReferenceProject]
        missing = [model for model in models if model._meta.db_table not in existing]
        if not missing:
            self._ensure_center_views(connection)
            return
        with connection.schema_editor() as schema_editor:
            for model in missing:
                schema_editor.create_model(model)
                self.stdout.write(f"테이블 생성: {model._meta.db_table}")
        self._ensure_center_views(connection)

    def _ensure_center_views(self, connection):
        if connection.vendor != "postgresql":
            return
        view_names = {
            "sangam": "reference_project_sangam",
            "bundang": "reference_project_bundang",
            "yeongnam": "reference_project_yeongnam",
        }
        with connection.cursor() as cursor:
            for center_code, view_name in view_names.items():
                cursor.execute(
                    f"""
                    CREATE OR REPLACE VIEW {view_name} AS
                    SELECT *
                      FROM reference_project
                     WHERE center_code = %s
                    """,
                    [center_code],
                )

    def _sync_pl_map(self, db_alias):
        rows = []
        for center_code, definition in CENTER_PL_NAMES.items():
            for order, name in enumerate(definition["names"], start=1):
                rows.append(
                    ReferenceCenterPl(
                        center_code=center_code,
                        center_label=definition["label"],
                        name=name,
                        display_order=order,
                    )
                )

        with transaction.atomic(using=db_alias):
            ReferenceCenterPl.objects.using(db_alias).all().delete()
            ReferenceCenterPl.objects.using(db_alias).bulk_create(rows, batch_size=BATCH_SIZE)
        self.stdout.write(f"PL 센터 매핑 저장: {len(rows)}건")

    def _sync_projects(self, db_alias, projects, spreadsheet_id, gid):
        project_numbers = [row.project_number for row in projects]
        existing = set(
            ReferenceProject.objects.using(db_alias)
            .filter(project_number__in=project_numbers)
            .values_list("project_number", flat=True)
        )

        objs = [
            ReferenceProject(
                project_number=row.project_number,
                center_code=row.center_code,
                center_label=row.center_label,
                cert_date=row.cert_date,
                cert_committee_date=row.cert_committee_date,
                company=row.company,
                product=row.product,
                pl=row.pl,
                primary_tester=row.primary_tester,
                wd=row.wd,
                request_date=row.request_date,
                contract_date=row.contract_date,
                start_date=row.start_date,
                expected_end_date=row.expected_end_date,
                raw_company_product=row.raw_company_product,
                source_spreadsheet_id=spreadsheet_id,
                source_gid=gid,
                source_row_number=row.source_row_number,
                source_payload_json=row.source_payload,
            )
            for row in projects
        ]
        update_fields = [
            "center_code",
            "center_label",
            "cert_date",
            "cert_committee_date",
            "company",
            "product",
            "pl",
            "primary_tester",
            "wd",
            "request_date",
            "contract_date",
            "start_date",
            "expected_end_date",
            "raw_company_product",
            "source_spreadsheet_id",
            "source_gid",
            "source_row_number",
            "source_payload_json",
            "updated_at",
        ]

        for start in range(0, len(objs), BATCH_SIZE):
            batch = objs[start : start + BATCH_SIZE]
            with transaction.atomic(using=db_alias):
                ReferenceProject.objects.using(db_alias).bulk_create(
                    batch,
                    batch_size=BATCH_SIZE,
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=["project_number"],
                )

        inserted = len([row for row in projects if row.project_number not in existing])
        updated = len(projects) - inserted
        return inserted, updated

    def _print_center_summary(self, projects):
        counts = {}
        for row in projects:
            key = row.center_label or row.center_code
            counts[key] = counts.get(key, 0) + 1
        self.stdout.write("센터별 파싱 결과: " + ", ".join(f"{k} {v}건" for k, v in sorted(counts.items())))

    def _pl_count(self):
        return sum(len(definition["names"]) for definition in CENTER_PL_NAMES.values())
