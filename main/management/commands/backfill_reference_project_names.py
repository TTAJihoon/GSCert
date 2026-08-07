from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from main.models import ReferenceProject, SwData


class Command(BaseCommand):
    """과거에 ReferenceProject.company/product에 전처리(예: 영문명 괄호 제거)된
    값이 저장된 기존 행을, 항상 원본 그대로인 SwData(인증획득목록 엑셀 적재본) 값으로
    되돌린다.

    sync_new_certified_projects는 이번 실행으로 새로 들어온 SwData 행만 반영하므로,
    그 이전에(예: 구글시트 전체 동기화 시절) 이미 만들어진 ReferenceProject 행은
    구버전 전처리 값을 그대로 유지한 채 남아 있다. 이 명령은 project_number로
    SwData.test_number를 매칭해 company/product가 다른 행만 골라 SwData 값으로
    덮어쓴다(신청일/계약일 등 구글시트 보완 필드는 건드리지 않는다).
    """

    help = "ReferenceProject.company/product를 SwData 원본 값으로 재동기화합니다(구버전 전처리 값 복구)."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="reference", help="대상 DB alias")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="지정하지 않으면 dry-run(변경 없이 차이만 출력)으로 동작합니다.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="dry-run 출력 시 보여줄 최대 건수(0이면 전체 출력).",
        )

    def handle(self, *args, **options):
        db_alias = options["database"]
        if db_alias not in connections:
            raise CommandError(f"설정에 없는 DB alias입니다: {db_alias}")
        apply_changes = options["apply"]
        limit = options["limit"]

        sw_by_number = {
            row.test_number.strip(): row
            for row in SwData.objects.using(db_alias).exclude(test_number="")
        }

        diffs = []
        unmatched = []
        for project in ReferenceProject.objects.using(db_alias).all():
            sw_row = sw_by_number.get(project.project_number)
            if not sw_row:
                unmatched.append(project.project_number)
                continue
            if project.company == sw_row.company and project.product == sw_row.product:
                continue
            diffs.append((project, sw_row))

        self.stdout.write(
            f"ReferenceProject 총 {ReferenceProject.objects.using(db_alias).count()}건 중 "
            f"SwData 매칭 없음 {len(unmatched)}건, company/product 불일치 {len(diffs)}건"
        )

        preview = diffs[:limit] if limit else diffs
        for project, sw_row in preview:
            self.stdout.write(
                f"- {project.project_number}: "
                f"company {project.company!r} -> {sw_row.company!r} / "
                f"product {project.product!r} -> {sw_row.product!r}"
            )
        if limit and len(diffs) > limit:
            self.stdout.write(f"  ... 외 {len(diffs) - limit}건")

        if not apply_changes:
            self.stdout.write(self.style.WARNING("dry-run입니다. 실제로 반영하려면 --apply를 추가하세요."))
            return

        for project, sw_row in diffs:
            project.company = sw_row.company
            project.product = sw_row.product
            project.save(using=db_alias, update_fields=["company", "product", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"{len(diffs)}건 반영 완료."))
