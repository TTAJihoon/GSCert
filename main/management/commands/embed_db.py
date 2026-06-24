from django.core.management.base import BaseCommand

from main.utils.embedding_to_faiss import (
    DEFAULT_INDEX_PATH,
    build_faiss_from_db,
    build_faiss_from_pg,
)


class Command(BaseCommand):
    help = "DB 데이터를 FAISS로 임베딩합니다. db_path 생략 시 PostgreSQL reference DB를 사용합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "db_path",
            nargs="?",
            default=None,
            type=str,
            help="SQLite DB 파일 경로 (생략 시 PostgreSQL reference DB 사용)",
        )
        parser.add_argument(
            "--index-path",
            default=str(DEFAULT_INDEX_PATH),
            help="FAISS 인덱스 파일 경로",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="기존 인덱스를 무시하고 전체 데이터를 다시 임베딩합니다.",
        )

    def handle(self, *args, **options):
        db_path = options["db_path"]
        index_path = options["index_path"]
        force_rebuild = options["rebuild"]

        if db_path:
            self.stdout.write(f"▶ DB 소스(SQLite): {db_path}")
            self.stdout.write(f"▶ FAISS 인덱스: {index_path}")
            result = build_faiss_from_db(
                db_path,
                index_path=index_path,
                force_rebuild=force_rebuild,
            )
        else:
            self.stdout.write("▶ DB 소스: PostgreSQL reference DB")
            self.stdout.write(f"▶ FAISS 인덱스: {index_path}")
            result = build_faiss_from_pg(
                index_path=index_path,
                force_rebuild=force_rebuild,
            )

        if result:
            self.stdout.write(
                self.style.SUCCESS(
                    "FAISS 처리 완료: "
                    f"mode={result['mode']}, added={result['added']}, "
                    f"total={result['total']}"
                )
            )
