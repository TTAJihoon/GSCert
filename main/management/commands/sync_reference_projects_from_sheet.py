from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from main.models import ReferenceCenterPl, ReferenceProject
from main.utils.ecm_reference_sheet import (
    CENTER_PL_NAMES,
    DEFAULT_GID,
    DEFAULT_SPREADSHEET_ID,
    build_pl_center_map,
    download_sheet_csv,
    normalize_person_name,
    parse_sheet_projects,
    read_csv_rows,
)


BATCH_SIZE = 500
CENTER_INPUT_ALIASES = {
    "1": "bundang",
    "b": "bundang",
    "bundang": "bundang",
    "분당": "bundang",
    "2": "sangam",
    "s": "sangam",
    "sangam": "sangam",
    "상암": "sangam",
    "3": "yeongnam",
    "y": "yeongnam",
    "yeongnam": "yeongnam",
    "영남": "yeongnam",
}


class Command(BaseCommand):
    help = "Google Sheet 인증위 프로젝트 목록을 PostgreSQL reference DB에 적재합니다."

    def add_arguments(self, parser):
        parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
        parser.add_argument("--gid", default=DEFAULT_GID)
        parser.add_argument("--source-csv", default=None, help="네트워크 대신 읽을 CSV 파일 경로")
        parser.add_argument("--database", default="reference", help="대상 DB alias")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--assign-unknown-pl",
            action="store_true",
            help="센터 미분류 PL을 번호로 선택해 동기화 중 즉시 센터에 배정합니다.",
        )
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
        csv_rows = read_csv_rows(csv_text)
        center_map = build_pl_center_map()
        if not options["dry_run"]:
            center_map.update(self._stored_pl_center_map(db_alias))

        projects = parse_sheet_projects(csv_rows, center_map=center_map)
        if not projects:
            self.stdout.write("시트에서 적재할 프로젝트를 찾지 못했습니다.")
            return

        unknown_counts = self._unknown_pl_counts(projects)
        new_assignments = {}
        if unknown_counts and options["assign_unknown_pl"]:
            new_assignments = self._prompt_unknown_pl_assignments(unknown_counts)
            if new_assignments:
                for name, center_code in new_assignments.items():
                    center_map[normalize_person_name(name)] = (
                        center_code,
                        self._center_label(center_code),
                    )
                projects = parse_sheet_projects(csv_rows, center_map=center_map)
                unknown_counts = self._unknown_pl_counts(projects)

        if unknown_counts:
            self.stdout.write(self.style.WARNING("센터 미분류 PL: " + ", ".join(unknown_counts.keys())))

        if options["dry_run"]:
            self.stdout.write(f"dry-run: 프로젝트 {len(projects)}건, PL 매핑 {self._pl_count(new_assignments)}건")
            self._print_center_summary(projects)
            return

        self._sync_pl_map(db_alias, new_assignments)
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

    def _stored_pl_center_map(self, db_alias):
        mapping = {}
        for row in ReferenceCenterPl.objects.using(db_alias).all():
            center_code = self._normalize_center_code(row.center_code)
            if not center_code:
                continue
            mapping[normalize_person_name(row.name)] = (
                row.name,
                center_code,
                row.center_label or self._center_label(center_code),
            )
        return mapping

    def _sync_pl_map(self, db_alias, new_assignments=None):
        """이름 -> (이름, 센터코드, 센터라벨) 최종 배정을 계산해 다시 적재한다.

        우선순위: 이번 실행에서 새로 받은 배정(new_assignments, --assign-unknown-pl)
        > 기존 저장값(existing_custom — 관리자가 웹 'PL 배정 목록'이나 이전
        --assign-unknown-pl 로 재배정한 값 포함) > 하드코딩 기본값(CENTER_PL_NAMES).
        예전에는 하드코딩 기본값에 있는 이름은 기존 저장값을 무시하고 무조건
        기본값으로 되돌렸기 때문에, 관리자가 재배정해도 다음 동기화 때 원복되는
        문제가 있었다.
        """
        new_assignments = new_assignments or {}
        existing_custom = self._stored_pl_center_map(db_alias)

        desired = {}
        for center_code, definition in CENTER_PL_NAMES.items():
            for name in definition["names"]:
                desired[normalize_person_name(name)] = (name, center_code, definition["label"])

        for normalized_name, (name, center_code, label) in existing_custom.items():
            desired[normalized_name] = (name, center_code, label)

        for name, center_code in new_assignments.items():
            normalized_center = self._normalize_center_code(center_code)
            if not normalized_center:
                continue
            desired[normalize_person_name(name)] = (name, normalized_center, self._center_label(normalized_center))

        next_order = {}
        rows = []
        for name, center_code, label in sorted(desired.values(), key=lambda item: (item[1], item[0])):
            next_order[center_code] = next_order.get(center_code, 0) + 1
            rows.append(
                ReferenceCenterPl(
                    center_code=center_code,
                    center_label=label,
                    name=name,
                    display_order=next_order[center_code],
                )
            )

        with transaction.atomic(using=db_alias):
            ReferenceCenterPl.objects.using(db_alias).all().delete()
            ReferenceCenterPl.objects.using(db_alias).bulk_create(rows, batch_size=BATCH_SIZE)
        self.stdout.write(f"PL 센터 매핑 저장: {len(rows)}건")

    def _prompt_unknown_pl_assignments(self, unknown_counts):
        pending = list(unknown_counts.items())
        assignments = {}
        while pending:
            self.stdout.write("")
            self.stdout.write("센터 미분류 PL:")
            for index, (name, count) in enumerate(pending, start=1):
                self.stdout.write(f"  {index}. {name} ({count}건)")

            selected = self._read_input("배정할 PL 번호 입력(Enter=건너뜀): ")
            if not selected:
                break
            if not selected.isdigit() or not 1 <= int(selected) <= len(pending):
                self.stdout.write(self.style.WARNING("목록에 있는 번호를 입력해 주세요."))
                continue

            name, _count = pending[int(selected) - 1]
            center_input = self._read_input("센터명 입력(분당/상암/영남 또는 1/2/3): ")
            center_code = self._normalize_center_code(center_input)
            if not center_code:
                self.stdout.write(self.style.WARNING("센터는 분당, 상암, 영남 중 하나로 입력해 주세요."))
                continue

            assignments[name] = center_code
            pending.pop(int(selected) - 1)
            self.stdout.write(f"배정: {name} -> {self._center_label(center_code)}")
        return assignments

    def _read_input(self, prompt):
        try:
            return input(prompt).strip()
        except EOFError:
            return ""

    def _unknown_pl_counts(self, projects):
        counts = {}
        for row in projects:
            if row.center_code == "unknown":
                counts[row.primary_tester] = counts.get(row.primary_tester, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def _normalize_center_code(self, value):
        key = normalize_person_name(value).lower()
        return CENTER_INPUT_ALIASES.get(key)

    def _center_label(self, center_code):
        return CENTER_PL_NAMES[center_code]["label"]

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

    def _pl_count(self, new_assignments=None):
        names = {
            normalize_person_name(name)
            for definition in CENTER_PL_NAMES.values()
            for name in definition["names"]
        }
        names.update(normalize_person_name(name) for name in (new_assignments or {}))
        return len([name for name in names if name])
