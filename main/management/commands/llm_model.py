from django.core.management.base import BaseCommand, CommandError

from main.utils.llm_models import list_llm_models, select_llm_model


class Command(BaseCommand):
    help = "서버 공통 LLM 모델 목록을 조회하거나 현재 모델을 전환합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            nargs="?",
            choices=("list", "select"),
            default="list",
        )
        parser.add_argument("--index", type=int, help="목록의 1부터 시작하는 모델 번호")
        parser.add_argument("--key", help="provider:model 형식의 모델 키")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "list":
            self._write_models()
            return

        models = list_llm_models()
        key = str(options.get("key") or "").strip()
        index = options.get("index")
        if not key and index is not None:
            if index < 1 or index > len(models):
                raise CommandError(f"모델 번호는 1~{len(models)} 사이여야 합니다.")
            key = models[index - 1]["key"]
        if not key:
            raise CommandError("--index 또는 --key를 입력해 주세요.")

        try:
            selected = select_llm_model(key)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"[OK] 사용 LLM을 {selected['label']} 모델로 전환했습니다.")
        )

    def _write_models(self):
        models = list_llm_models()
        self.stdout.write("사용 가능한 LLM 모델 목록")
        if not models:
            self.stdout.write("  등록된 모델이 없습니다.")
            return
        for index, model in enumerate(models, start=1):
            markers = []
            if model["active"]:
                markers.append("사용 중")
            if not model["available"]:
                markers.append("API 키 미설정")
            suffix = f" [{', '.join(markers)}]" if markers else ""
            self.stdout.write(f"  {index}. {model['label']}{suffix}")
