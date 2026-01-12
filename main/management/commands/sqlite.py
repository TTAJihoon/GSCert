from django.core.management.base import BaseCommand
from main.utils.xlsx_to_sqlite import convert_xlsx_to_sqlite

class Command(BaseCommand):
    help = "XLSX 파일을 SQLite DB로 변환하여 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str, help="입력 XLSX 파일 경로")
        parser.add_argument("db_path", type=str, help="출력 SQLite DB 파일 경로")

    def handle(self, *args, **options):
        xlsx_path = options["xlsx_path"]
        db_path = options["db_path"]

        self.stdout.write(f"▶ XLSX 파일: {xlsx_path}")
        self.stdout.write(f"▶ SQLite DB: {db_path}")
        
        convert_xlsx_to_sqlite(xlsx_path, db_path)
