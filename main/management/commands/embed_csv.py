# main/management/commands/embed_csv.py

from django.core.management.base import BaseCommand
from main.utils.embedding_to_faiss import build_faiss_from_csv

class Command(BaseCommand):
    help = "CSV 파일을 FAISS로 임베딩합니다."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="CSV 파일 경로")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        self.stdout.write(f"▶ CSV 파일: {csv_path}")
        build_faiss_from_csv(csv_path)
