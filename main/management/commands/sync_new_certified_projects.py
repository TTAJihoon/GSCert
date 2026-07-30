from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from main.models import ReferenceCenterPl, ReferenceProject, SwData
from main.utils.ecm_reference_sheet import (
    DEFAULT_GID,
    DEFAULT_SPREADSHEET_ID,
    download_sheet_csv,
    first_tester_name,
    normalize_person_name,
    parse_sheet_projects,
    read_csv_rows,
)


class Command(BaseCommand):
    """weekly(W) 동기화가 SwData(인증획득목록 엑셀)에 새로 적재한 건을 ReferenceProject에 반영한다.

    회사명/제품명/PL/WD/시험기간은 SwData(기준 원본)를 그대로 쓰고, SwData에는 없는
    신청일/계약일만 인증위 구글시트에서 프로젝트번호로 찾아 보완한다. 구글시트에서
    프로젝트번호를 못 찾으면(오래돼서 시트에서 지워진 경우 등) 그 건은 건너뛰고
    경고만 남긴다 - 부분적인 값으로 ReferenceProject를 만들지 않는다.

    센터는 SwData.test_lab(담당자)의 첫 이름을 ReferenceCenterPl에서 찾아 정한다.
    매핑이 없으면(신규/미배정 PL) center_code='unknown'으로 두고 'PL 배정 목록'
    화면에서 배정하게 한다. 이미 존재하는 ReferenceProject 행은 review_result 등
    점검 결과 필드는 건드리지 않고 나머지 값만 최신화한다.
    """

    help = "SwData 신규 건을 구글시트(신청일/계약일 보완)와 매칭해 ReferenceProject에 반영합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since-serial",
            type=int,
            required=True,
            help="이 일련번호보다 큰 SwData 행만 대상으로 함(weekly.py의 직전 master 마지막 일련번호).",
        )
        parser.add_argument("--database", default="reference", help="대상 DB alias")
        parser.add_argument("--spreadsheet-id", default=DEFAULT_SPREADSHEET_ID)
        parser.add_argument("--gid", default=DEFAULT_GID)
        parser.add_argument("--source-csv", default=None, help="네트워크 대신 읽을 CSV 파일 경로(테스트용)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        db_alias = options["database"]
        if db_alias not in connections:
            raise CommandError(f"설정에 없는 DB alias입니다: {db_alias}")

        new_rows = list(
            SwData.objects.using(db_alias)
            .filter(serial_number__gt=options["since_serial"])
            .exclude(test_number="")
        )
        if not new_rows:
            self.stdout.write("SwData에 새로 반영할 행이 없습니다.")
            return

        csv_text = self._load_csv(options)
        sheet_projects = {
            row.project_number: row for row in parse_sheet_projects(read_csv_rows(csv_text))
        }
        center_map = {
            normalize_person_name(row.name): (row.center_code, row.center_label)
            for row in ReferenceCenterPl.objects.using(db_alias).all()
        }

        updated = 0
        skipped = []
        for sw_row in new_rows:
            project_number = sw_row.test_number.strip()
            sheet_row = sheet_projects.get(project_number)
            if not sheet_row:
                skipped.append(project_number)
                continue

            primary_tester = first_tester_name(sw_row.test_lab)
            center_code, center_label = center_map.get(
                normalize_person_name(primary_tester), ("unknown", "미분류")
            )
            raw_company_product = "-".join(part for part in (sw_row.company, sw_row.product) if part)

            if not options["dry_run"]:
                ReferenceProject.objects.using(db_alias).update_or_create(
                    project_number=project_number,
                    defaults=dict(
                        center_code=center_code,
                        center_label=center_label,
                        cert_date=sw_row.cert_date,
                        company=sw_row.company,
                        product=sw_row.product,
                        pl=sw_row.test_lab,
                        primary_tester=primary_tester,
                        wd=sw_row.total_wd,
                        request_date=sheet_row.request_date,
                        contract_date=sheet_row.contract_date,
                        start_date=sw_row.start_date,
                        expected_end_date=sw_row.end_date,
                        raw_company_product=raw_company_product,
                    ),
                )
            updated += 1

        self.stdout.write(
            f"ReferenceProject 반영: {updated}건"
            + (" (dry-run)" if options["dry_run"] else "")
        )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    "구글시트에서 프로젝트번호를 찾지 못해 건너뜀: " + ", ".join(skipped)
                )
            )

    def _load_csv(self, options):
        source_csv = options.get("source_csv")
        if source_csv:
            with open(source_csv, "r", encoding="utf-8-sig", newline="") as file:
                return file.read()
        return download_sheet_csv(options["spreadsheet_id"], options["gid"])
