from django.core.management.base import BaseCommand
from main.utils.csv_to_sqlite import convert_csv_to_sqlite

class Command(BaseCommand):
    help = "CSV파일을 SQLite DB로 변환하여 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="입력 CSV 파일 경로")
        parser.add_argument("db_path", type=str, help="출력 SQLite DB 파일 경로")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        db_path = options["db_path"]

        self.stdout.write(f"▶ CSV 파일: {csv_path}")
        self.stdout.write(f"▶ SQLite DB: {db_path}")

        convert_csv_to_sqlite(csv_path, db_path)
