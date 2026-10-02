import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """KOLAS 결과서 다운로드 진행 상황 기록(workflow DB, 서버마다 migrate --database=workflow)."""

    dependencies = [
        ("main", "0015_kolas_project_and_job_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="KolasReportTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("canceled", "Canceled"),
                        ],
                        db_index=True,
                        default="running",
                        max_length=20,
                    ),
                ),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("total_projects", models.PositiveIntegerField(default=0)),
                ("done_projects", models.PositiveIntegerField(default=0)),
                ("percent", models.PositiveSmallIntegerField(default=0)),
                ("current_project", models.CharField(blank=True, max_length=32)),
                ("current_step", models.CharField(blank=True, max_length=255)),
                ("complete_count", models.PositiveIntegerField(default=0)),
                ("partial_count", models.PositiveIntegerField(default=0)),
                ("none_count", models.PositiveIntegerField(default=0)),
                ("anonymous_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "kolas_report_task",
                "ordering": ["-started_at", "id"],
            },
        ),
    ]
