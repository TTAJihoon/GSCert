from django.core.management.base import BaseCommand
from main.utils.n_gram_to_faiss import build_ngram_table

class Command(BaseCommand):
    help = "DB 데이터를 FAISS로 임베딩합니다."

    def add_arguments(self, parser):
        parser.add_argument("db_path", type=str, help="DB 파일 경로")

    def handle(self, *args, **options):
        db_path = options["db_path"]
        self.stdout.write(f"▶ DB 파일: {db_path}")
        build_ngram_table(db_path)
