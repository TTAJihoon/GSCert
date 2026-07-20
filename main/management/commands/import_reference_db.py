import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import SwData
from main.utils.xlsx_to_sqlite import (
    _ensure_sw_category_column,
    _normalize_columns,
    normalize_cell_text,
    parse_korean_date_range,
)

SQLITE_COLUMNS = [
    "일련번호",
    "인증번호",
    "인증일자",
    "회사명",
    "제품",
    "등급",
    "시험번호",
    "SW분류",
    "제품설명",
    "총WD",
    "재계약",
    "특이사항",
    "시작날짜종료날짜",
    "시험원",
    "시작일자",
    "종료일자",
    "재인증구분",
    "기인증번호제품정보버전",
    "KOLAS",
]

MODEL_FIELDS = [
    "serial_number",
    "cert_number",
    "cert_date",
    "company",
    "product",
    "grade",
    "test_number",
    "sw_category",
    "product_desc",
    "total_wd",
    "renewal",
    "notes",
    "date_range",
    "test_lab",
    "start_date",
    "end_date",
    "recert_type",
    "prev_cert_info",
    "kolas",
]

BATCH_SIZE = 500


class Command(BaseCommand):
    help = "reference.db(sw_data)의 데이터를 PostgreSQL reference DB로 가져옵니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=None,
            help="SQLite 파일 경로 (기본: main/data/reference.db)",
        )
        parser.add_argument(
            "--source-xlsx",
            default=None,
            dest="source_xlsx",
            help="xlsx 파일 경로 (SQLite를 거치지 않고 직접 적재)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="가져오기 전에 기존 데이터를 모두 삭제합니다.",
        )

    def handle(self, *args, **options):
        source_xlsx = options.get("source_xlsx")

        if source_xlsx:
            xlsx_path = Path(source_xlsx)
            if not xlsx_path.exists():
                raise CommandError(f"xlsx 파일을 찾을 수 없습니다: {xlsx_path}")
            self.stdout.write(f"source xlsx: {xlsx_path}")
            rows = self._read_rows_from_xlsx(xlsx_path)
        else:
            source = options["source"]
            if source:
                db_path = Path(source)
            else:
                db_path = Path(settings.BASE_DIR) / "main" / "data" / "reference.db"

            if not db_path.exists():
                raise CommandError(f"reference.db 파일을 찾을 수 없습니다: {db_path}")

            self.stdout.write(f"source sqlite: {db_path}")

            conn = sqlite3.connect(str(db_path))
            conn.text_factory = bytes
            try:
                rows = self._read_rows(conn)
            finally:
                conn.close()

        self.stdout.write(f"읽은 행 수: {len(rows)}")

        if options["clear"]:
            deleted = SwData.objects.using("reference").all().delete()[0]
            self.stdout.write(f"기존 데이터 삭제: {deleted}개")

        self._bulk_import(rows)
        self.stdout.write(self.style.SUCCESS(f"가져오기 완료: {len(rows)}개 행"))

    def _read_rows_from_xlsx(self, xlsx_path):
        import pandas as pd

        df = pd.read_excel(
            str(xlsx_path),
            sheet_name=0,
            engine="openpyxl",
            dtype=object,
            keep_default_na=False,
        )
        df = _normalize_columns(df)
        df = _ensure_sw_category_column(df)

        date_col = None
        for c in ["시작날짜종료날짜", "시작날짜종료", "시작일자종료일자"]:
            if c in df.columns:
                date_col = c
                break
        if date_col is None:
            for c in df.columns:
                if "시작" in c and "종료" in c:
                    date_col = c
                    break

        if date_col is not None:
            df[["시작일자", "종료일자"]] = df[date_col].apply(
                lambda x: pd.Series(parse_korean_date_range(x))
            )
        else:
            df["시작일자"] = ""
            df["종료일자"] = ""

        def get_val(row_data, col):
            if col not in df.columns:
                return ""
            v = row_data[col]
            if hasattr(v, "iloc"):
                for item in v:
                    if item is not None and str(item).strip():
                        v = item
                        break
                else:
                    return ""
            if v is None or (isinstance(v, float) and str(v).lower() == "nan"):
                return ""
            return normalize_cell_text(str(v)).strip()

        def get_first_val(row_data, cols):
            for col in cols:
                value = get_val(row_data, col)
                if value:
                    return value
            return ""

        rows = []
        for _, row_data in df.iterrows():
            sn_str = get_val(row_data, "일련번호")
            if not sn_str:
                continue
            try:
                sn = int(float(sn_str))
            except (ValueError, TypeError):
                continue

            rows.append({
                "serial_number": sn,
                "cert_number": get_val(row_data, "인증번호"),
                "cert_date": get_val(row_data, "인증일자"),
                "company": get_val(row_data, "회사명"),
                "product": get_val(row_data, "제품"),
                "grade": get_val(row_data, "등급"),
                "test_number": get_val(row_data, "시험번호"),
                "sw_category": get_val(row_data, "SW분류"),
                "product_desc": get_val(row_data, "제품설명"),
                "total_wd": get_val(row_data, "총WD"),
                "renewal": get_val(row_data, "재계약"),
                "notes": get_val(row_data, "특이사항"),
                "date_range": get_val(row_data, date_col) if date_col else "",
                "test_lab": get_val(row_data, "시험원"),
                "start_date": get_val(row_data, "시작일자"),
                "end_date": get_val(row_data, "종료일자"),
                "recert_type": get_first_val(row_data, ["재인증구분", "재인증"]),
                "prev_cert_info": get_first_val(row_data, [
                    "기인증번호제품정보버전",
                    "기인증번호제품정보",
                    "기인증제품",
                ]),
                "kolas": get_val(row_data, "KOLAS"),
            })

        return rows

    def _read_rows(self, conn):
        cur = conn.execute("SELECT * FROM sw_data ORDER BY rowid")
        rows_raw = cur.fetchall()

        result = []
        for raw in rows_raw:
            obj = {}
            for i, field in enumerate(MODEL_FIELDS):
                val = raw[i] if i < len(raw) else None
                if isinstance(val, bytes):
                    try:
                        val = val.decode("utf-8")
                    except UnicodeDecodeError:
                        val = val.decode("cp949", errors="replace")
                obj[field] = normalize_cell_text(val) if val is not None else ""
            result.append(obj)
        return result

    def _bulk_import(self, rows):
        db_alias = "reference"
        total = 0

        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            objs = [SwData(**row) for row in batch]
            with transaction.atomic(using=db_alias):
                SwData.objects.using(db_alias).bulk_create(
                    objs,
                    update_conflicts=True,
                    update_fields=[f for f in MODEL_FIELDS if f != "serial_number"],
                    unique_fields=["serial_number"],
                )
            total += len(batch)
            self.stdout.write(f"  {total}/{len(rows)} 행 저장 완료")
