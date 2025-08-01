from django.core.management.base import BaseCommand
from main.utils.embedding_to_faiss import build_faiss_from_csv

class Command(BaseCommand):
    help = "DB 데이터를 FAISS로 임베딩합니다."

    def add_arguments(self, parser):
        parser.add_argument("db_path", type=str, help="DB 파일 경로")

    def handle(self, *args, **options):
        csv_path = options["db_path"]
        self.stdout.write(f"▶ DB 파일: {db_path}")
        build_faiss_from_db(db_path)
