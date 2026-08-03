"""점검규칙/세부항목 on-off 콘솔 명령.

서버 관리 콘솔(launcher.ps1)의 D 메뉴 → "2) 수정"에서 호출한다. 사람이 직접
manage.py로 실행해도 된다.

    manage.py rule_toggle list-rules
    manage.py rule_toggle toggle-rule --code artifact_12 --enable|--disable
    manage.py rule_toggle list-sub-checks --code artifact_11
    manage.py rule_toggle toggle-sub-check --code artifact_11 --position 9 --enable|--disable

규칙 전체 on/off는 DownloadReviewRule.enabled 필드를 그대로 쓴다.
세부항목 on/off는 DownloadReviewRule.config_json["disabled_sub_checks"](1-based
위치 번호 문자열 목록)에 저장하며, gscert_review_core.engine._apply_disabled_sub_checks
가 매 점검 실행 시 이 목록을 읽어 해당 위치의 sub_check를 결과에서 완전히 제외한다.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from main.models import DownloadReviewRule
from main.rule_sub_check_catalog import RULE_SUB_CHECK_CATALOG


class Command(BaseCommand):
    help = "점검규칙/세부항목 on-off 조회 및 변경."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", required=True)

        subparsers.add_parser("list-rules", help="전체 규칙 목록과 enabled 상태를 표시한다.")

        toggle_rule = subparsers.add_parser("toggle-rule", help="규칙 전체를 켜거나 끈다.")
        toggle_rule.add_argument("--code", required=True, help="예: artifact_12")
        toggle_state = toggle_rule.add_mutually_exclusive_group(required=True)
        toggle_state.add_argument("--enable", action="store_true")
        toggle_state.add_argument("--disable", action="store_true")

        list_sub = subparsers.add_parser(
            "list-sub-checks", help="규칙 하나의 세부항목 목록과 on/off 상태를 표시한다."
        )
        list_sub.add_argument("--code", required=True, help="예: artifact_11")

        toggle_sub = subparsers.add_parser(
            "toggle-sub-check", help="세부항목 하나를 켜거나 끈다."
        )
        toggle_sub.add_argument("--code", required=True)
        toggle_sub.add_argument("--position", required=True, type=int, help="1부터 시작하는 세부항목 순번")
        toggle_sub_state = toggle_sub.add_mutually_exclusive_group(required=True)
        toggle_sub_state.add_argument("--enable", action="store_true")
        toggle_sub_state.add_argument("--disable", action="store_true")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "list-rules":
            self._list_rules()
        elif action == "toggle-rule":
            self._toggle_rule(options["code"], enable=options["enable"])
        elif action == "list-sub-checks":
            self._list_sub_checks(options["code"])
        elif action == "toggle-sub-check":
            self._toggle_sub_check(options["code"], options["position"], enable=options["enable"])

    def _list_rules(self):
        rules = DownloadReviewRule.objects.order_by("sort_order", "name", "id")
        if not rules:
            self.stdout.write("등록된 규칙이 없습니다.")
            return
        for rule in rules:
            state = "ON " if rule.enabled else "OFF"
            disabled = (rule.config_json or {}).get("disabled_sub_checks") or []
            disabled_note = f" (세부항목 {len(disabled)}개 꺼짐)" if disabled else ""
            self.stdout.write(f"[{state}] {rule.code:<14} {rule.name}{disabled_note}")

    def _get_rule(self, code):
        rule = DownloadReviewRule.objects.filter(code=code).first()
        if not rule:
            raise CommandError(f"규칙을 찾을 수 없습니다: {code}")
        return rule

    def _toggle_rule(self, code, *, enable):
        rule = self._get_rule(code)
        rule.enabled = enable
        rule.save(update_fields=["enabled"])
        self.stdout.write(f"{rule.code} ({rule.name}) → {'ON' if enable else 'OFF'}")

    def _list_sub_checks(self, code):
        rule = self._get_rule(code)
        catalog = RULE_SUB_CHECK_CATALOG.get(code)
        if not catalog:
            raise CommandError(f"{code}에 대한 세부항목 카탈로그가 없습니다.")
        disabled = {str(item).strip() for item in (rule.config_json or {}).get("disabled_sub_checks") or []}
        self.stdout.write(f"{rule.code} ({rule.name}) 세부항목:")
        for position, label in catalog:
            state = "OFF" if str(position) in disabled else "ON "
            self.stdout.write(f"  [{state}] {position}. {label}")

    def _toggle_sub_check(self, code, position, *, enable):
        rule = self._get_rule(code)
        catalog = RULE_SUB_CHECK_CATALOG.get(code) or []
        if not any(item_position == position for item_position, _label in catalog):
            raise CommandError(f"{code}에 {position}번 세부항목이 없습니다.")

        config = dict(rule.config_json or {})
        disabled = {str(item).strip() for item in config.get("disabled_sub_checks") or []}
        position_key = str(position)
        if enable:
            disabled.discard(position_key)
        else:
            disabled.add(position_key)
        config["disabled_sub_checks"] = sorted(disabled, key=int)
        rule.config_json = config
        rule.save(update_fields=["config_json"])

        label = next(label for item_position, label in catalog if item_position == position)
        self.stdout.write(f"{rule.code} {position}.{label} → {'ON' if enable else 'OFF'}")
