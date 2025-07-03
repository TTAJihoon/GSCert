from django.core.management.base import BaseCommand
from main.utils.embedding_to_chroma import build_chroma_from_csv

class Command(BaseCommand):
    help = "CSV 파일을 Chroma DB로 임베딩합니다."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="CSV 파일 경로")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        self.stdout.write(f"▶ CSV 파일: {csv_path}")
        build_chroma_from_csv(csv_path)  # 👉 여기서 호출됨
