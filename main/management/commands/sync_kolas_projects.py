from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from main.models import KolasProject, ReferenceCenterPl
from main.utils.ecm_reference_sheet import (
    build_pl_center_map,
    download_sheet_csv,
    normalize_person_name,
    read_csv_rows,
)
from main.utils.kolas_sheet import (
    KOLAS_SHEETS,
    RANGE_END,
    RANGE_START,
    SPREADSHEET_ID,
    filter_by_expected_end,
    merge_sheets,
    parse_kolas_sheet,
)
from main.views.review.ecm_reference_db import copy_reference_results_to_kolas

BATCH_SIZE = 500
# 기존 DB 점검결과 컬럼은 동기화가 덮어쓰지 않는다(결과는 점검 작업/복사 단계에서만 바뀐다).
RESULT_FIELDS = {"review_result", "inspection_date", "artifact_results_json"}


class Command(BaseCommand):
    help = (
        "KOLAS 점검 페이지(/kolas/) 프로젝트 목록을 구글시트(2025/2026)에서 종료예정일 기준으로 "
        "kolas_project 테이블에 적재하고, 기존 DB(reference_project)의 점검결과를 복사합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("--database", default=getattr(settings, "REFERENCE_DATABASE_ALIAS", "reference"))
        parser.add_argument("--start", default=RANGE_START.isoformat(), help="종료예정일 시작(YYYY-MM-DD)")
        parser.add_argument("--end", default=RANGE_END.isoformat(), help="종료예정일 끝(YYYY-MM-DD)")
        parser.add_argument("--csv-2026", default=None, help="네트워크 대신 읽을 2026 시트 CSV 경로")
        parser.add_argument("--csv-2025", default=None, help="네트워크 대신 읽을 2025 시트 CSV 경로")
        parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 파싱 결과만 출력")
        parser.add_argument(
            "--prune",
            action="store_true",
            help="이번 대상에 없는 기존 KOLAS 행(점검결과 없는 것만)을 삭제합니다.",
        )
        parser.add_argument(
            "--prune-results",
            action="store_true",
            help="--prune 과 함께 쓰면 점검결과가 있는 행도 삭제합니다(번호 규칙이 바뀌어 잘못된 번호로 남은 행 정리용. "
            "점검결과는 reference_project 의 복사본이라 다시 동기화하면 복원됩니다).",
        )
        parser.add_argument("--no-schema-check", action="store_true", help="테이블 자동 생성 확인을 건너뜁니다.")

    def handle(self, *args, **options):
        from datetime import date

        alias = options["database"]
        try:
            start = date.fromisoformat(options["start"])
            end = date.fromisoformat(options["end"])
        except ValueError as exc:
            raise CommandError(f"날짜 형식이 올바르지 않습니다: {exc}") from exc
        if not options["dry_run"] and alias not in connections:
            raise CommandError(f"설정에 없는 DB alias입니다: {alias}")

        center_map = build_pl_center_map()
        if not options["dry_run"]:
            if not options["no_schema_check"]:
                self._ensure_table(alias)
            center_map.update(self._stored_pl_center_map(alias))

        csv_paths = {"2026": options["csv_2026"], "2025": options["csv_2025"]}
        parsed_by_sheet = []
        for label, gid in KOLAS_SHEETS:
            rows = read_csv_rows(self._load_csv(csv_paths.get(label), gid))
            sheet_rows, warnings = parse_kolas_sheet(rows, gid=gid, center_map=center_map)
            for warning in warnings:
                self.stdout.write(self.style.WARNING(warning))
            self.stdout.write(f"{label}년 시트(gid={gid}): 파싱 {len(sheet_rows)}건")
            parsed_by_sheet.append(sheet_rows)

        merged, dropped = merge_sheets(parsed_by_sheet)
        selected, undated = filter_by_expected_end(merged, start, end)
        self.stdout.write(
            f"중복 제거 후 {len(merged)}건 (중복으로 제외 {len(dropped)}건) → "
            f"종료예정일 {start}~{end} 대상 {len(selected)}건"
        )
        for number, kept, excluded in dropped:
            self.stdout.write(f"  중복 {number}: 채택 {kept} / 제외 {excluded}")
        if undated:
            self.stdout.write(self.style.WARNING(
                f"종료예정일을 읽지 못해 제외한 건: {len(undated)}건 - "
                + ", ".join(row.project_number for row in undated[:20])
            ))
        self._print_center_summary(selected)
        self._report_stale(alias, selected, dry_run=options["dry_run"])

        if options["dry_run"]:
            self.stdout.write("dry-run: DB는 변경하지 않았습니다.")
            return

        inserted, updated = self._upsert(alias, selected)
        pruned = self._prune(alias, selected, include_results=options["prune_results"]) if options["prune"] else 0
        copied = copy_reference_results_to_kolas()
        self.stdout.write(self.style.SUCCESS(
            f"적재 완료: 신규 {inserted}건, 갱신 {updated}건, 삭제 {pruned}건, 기존 DB 점검결과 복사 {copied}건"
        ))

    def _load_csv(self, path, gid):
        if path:
            with open(path, "r", encoding="utf-8-sig", newline="") as file:
                return file.read()
        return download_sheet_csv(SPREADSHEET_ID, gid)

    def _ensure_table(self, alias):
        connection = connections[alias]
        if KolasProject._meta.db_table in set(connection.introspection.table_names()):
            return
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(KolasProject)
        self.stdout.write(f"테이블 생성: {KolasProject._meta.db_table}")

    def _stored_pl_center_map(self, alias):
        """웹 'PL 배정 목록'에서 재배정한 값이 시트 기본 목록보다 우선한다."""
        mapping = {}
        for row in ReferenceCenterPl.objects.using(alias).all():
            mapping[normalize_person_name(row.name)] = (row.center_code, row.center_label)
        return mapping

    def _upsert(self, alias, rows):
        numbers = [row.project_number for row in rows]
        existing = set(
            KolasProject.objects.using(alias)
            .filter(project_number__in=numbers)
            .values_list("project_number", flat=True)
        )
        objs = [
            KolasProject(
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
                expected_end_on=row.expected_end_on,
                raw_company_product=row.raw_company_product,
                source_spreadsheet_id=SPREADSHEET_ID,
                source_gid=row.source_gid,
                source_row_number=row.source_row_number,
                source_payload_json=row.source_payload,
            )
            for row in rows
        ]
        update_fields = [
            field.name
            for field in KolasProject._meta.concrete_fields
            if field.name not in RESULT_FIELDS
            and field.name not in {"id", "project_number", "created_at"}
        ]
        for start in range(0, len(objs), BATCH_SIZE):
            with transaction.atomic(using=alias):
                KolasProject.objects.using(alias).bulk_create(
                    objs[start:start + BATCH_SIZE],
                    batch_size=BATCH_SIZE,
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=["project_number"],
                )
        inserted = len([number for number in numbers if number not in existing])
        return inserted, len(numbers) - inserted

    def _stale_rows(self, alias, rows):
        """이번 대상에는 없지만 DB 에 남아 있는 행 [(번호, 점검결과)]. 번호 규칙이 바뀌었거나 종료예정일이 범위를 벗어난 경우."""
        keep = {row.project_number for row in rows}
        return list(
            KolasProject.objects.using(alias)
            .exclude(project_number__in=keep)
            .values_list("project_number", "review_result")
            .order_by("project_number")
        )

    def _report_stale(self, alias, rows, *, dry_run):
        try:
            if dry_run and alias not in connections:
                return
            stale = self._stale_rows(alias, rows)
        except Exception as exc:  # 테이블이 아직 없는 등. 동기화 자체는 계속한다.
            self.stdout.write(f"(목록에서 빠진 기존 행 확인 생략: {exc})")
            return
        if not stale:
            return
        deletable = [number for number, review in stale if not review]
        kept = [number for number, review in stale if review]
        self.stdout.write(self.style.WARNING(
            f"이번 대상에는 없지만 DB 에 남아 있는 행 {len(stale)}건 "
            f"(점검결과 없음 {len(deletable)}건 / 점검결과 있어 보존 {len(kept)}건): "
            + ", ".join(number for number, _review in stale[:20]) + (" ..." if len(stale) > 20 else "")
        ))
        self.stdout.write("  점검결과 없는 행을 지우려면 --prune 을 붙여 실행하세요.")

    def _prune(self, alias, rows, *, include_results=False):
        keep = {row.project_number for row in rows}
        stale = KolasProject.objects.using(alias).exclude(project_number__in=keep)
        if not include_results:
            stale = stale.filter(review_result="")
        count = stale.count()
        stale.delete()
        return count

    def _print_center_summary(self, rows):
        counts = {}
        for row in rows:
            key = row.center_label or row.center_code
            counts[key] = counts.get(key, 0) + 1
        self.stdout.write("센터별: " + ", ".join(f"{k} {v}건" for k, v in sorted(counts.items())))
        unknown = {}
        for row in rows:
            if row.center_code == "unknown":
                unknown[row.primary_tester] = unknown.get(row.primary_tester, 0) + 1
        if unknown:
            top = sorted(unknown.items(), key=lambda item: (-item[1], item[0]))
            self.stdout.write(self.style.WARNING(
                "센터 미배정 PL (KOLAS 페이지의 'PL 배정 목록'에서 배정): "
                + ", ".join(f"{name}({count})" for name, count in top)
            ))
