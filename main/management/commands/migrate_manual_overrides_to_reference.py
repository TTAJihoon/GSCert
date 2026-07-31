from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import DatabaseError

from main.models import DownloadReviewManualOverride


class Command(BaseCommand):
    help = "Copy manual pass overrides from the legacy workflow DB to the reference DB."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="workflow", help="Legacy source DB alias")
        parser.add_argument("--target", default="reference", help="Reference target DB alias")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        source = options["source"]
        target = options["target"]
        dry_run = options["dry_run"]
        if source == target:
            raise CommandError("source and target must be different aliases.")
        for alias in (source, target):
            if alias not in connections:
                raise CommandError(f"Unknown DB alias: {alias}")

        rows = self._source_rows(source)
        if not rows:
            self.stdout.write("No manual pass overrides to migrate.")
            return

        copied = 0
        for row in rows:
            if dry_run:
                copied += 1
                continue
            obj, _created = DownloadReviewManualOverride.objects.using(target).update_or_create(
                center_code=row.center_code,
                project_number=row.project_number,
                rule_code=row.rule_code,
                sub_check_key=getattr(row, "sub_check_key", ""),
                defaults={
                    "id": row.id,
                    "rule_name": row.rule_name,
                    "memo": row.memo,
                    "created_by": row.created_by,
                    "last_applied_at": row.last_applied_at,
                },
            )
            DownloadReviewManualOverride.objects.using(target).filter(id=obj.id).update(
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_applied_at=row.last_applied_at,
            )
            copied += 1

        action = "Would migrate" if dry_run else "Migrated"
        self.stdout.write(self.style.SUCCESS(f"{action} {copied} manual pass override(s)."))

    def _source_rows(self, source):
        connection = connections[source]
        table = DownloadReviewManualOverride._meta.db_table
        table_names = connection.introspection.table_names()
        if table not in table_names:
            self.stdout.write("Source manual pass override table does not exist; nothing to migrate.")
            return []

        try:
            with connection.cursor() as cursor:
                columns = {column.name for column in connection.introspection.get_table_description(cursor, table)}
                selected_columns = [
                    "id",
                    "center_code",
                    "project_number",
                    "rule_code",
                    "sub_check_key",
                    "rule_name",
                    "memo",
                    "created_by",
                    "created_at",
                    "updated_at",
                    "last_applied_at",
                ]
                select_sql = []
                quote = connection.ops.quote_name
                for column in selected_columns:
                    if column in columns:
                        select_sql.append(quote(column))
                    elif column == "sub_check_key":
                        select_sql.append("'' AS sub_check_key")
                    else:
                        select_sql.append(f"NULL AS {quote(column)}")
                cursor.execute(
                    f"SELECT {', '.join(select_sql)} FROM {quote(table)} ORDER BY {quote('created_at')}, {quote('id')}"
                )
                rows = cursor.fetchall()
            return [
                SimpleNamespace(**dict(zip(selected_columns, row)))
                for row in rows
            ]
        except DatabaseError as exc:
            message = str(exc).lower()
            if "inspection_manual_override" in message and (
                "no such table" in message
                or "does not exist" in message
                or "undefinedtable" in message
            ):
                self.stdout.write("Source manual pass override table does not exist; nothing to migrate.")
                return []
            raise
