from django.db import migrations, models


class Migration(migrations.Migration):
    """KOLAS 점검 페이지(/kolas/) 지원.

    - KolasProject: reference DB(PostgreSQL)에 생성되는 KOLAS 전용 프로젝트 목록.
    - DownloadReviewJob.source: workflow DB(각 서버 SQLite)의 작업 요청 화면 구분 컬럼.
    적용: migrate --database=reference, migrate --database=workflow (서버마다).
    """

    dependencies = [
        ("main", "0014_server_time_control"),
    ]

    operations = [
        migrations.CreateModel(
            name="KolasProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("project_number", models.CharField(db_index=True, max_length=32, unique=True)),
                ("center_code", models.CharField(db_index=True, max_length=20)),
                ("center_label", models.CharField(blank=True, default="", max_length=20)),
                ("cert_date", models.CharField(blank=True, default="", max_length=20)),
                ("cert_committee_date", models.DateField(blank=True, db_index=True, null=True)),
                ("company", models.TextField(blank=True, default="")),
                ("product", models.TextField(blank=True, default="")),
                ("pl", models.TextField(blank=True, default="")),
                ("primary_tester", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("wd", models.TextField(blank=True, default="")),
                ("request_date", models.TextField(blank=True, default="")),
                ("contract_date", models.TextField(blank=True, default="")),
                ("start_date", models.TextField(blank=True, default="")),
                ("expected_end_date", models.TextField(blank=True, default="")),
                ("expected_end_on", models.DateField(blank=True, db_index=True, null=True)),
                ("review_result", models.CharField(blank=True, default="", max_length=20)),
                ("inspection_date", models.TextField(blank=True, default="")),
                ("artifact_results_json", models.JSONField(blank=True, default=dict)),
                ("raw_company_product", models.TextField(blank=True, default="")),
                ("source_spreadsheet_id", models.CharField(blank=True, default="", max_length=120)),
                ("source_gid", models.CharField(blank=True, default="", max_length=40)),
                ("source_row_number", models.PositiveIntegerField(blank=True, null=True)),
                ("source_payload_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "kolas_project",
                "ordering": ["-expected_end_on", "project_number"],
                "indexes": [
                    models.Index(fields=["center_code", "expected_end_on"], name="kolas_project_center_end_idx"),
                    models.Index(fields=["center_code", "project_number"], name="kolas_project_center_num_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="downloadreviewjob",
            name="source",
            field=models.CharField(db_index=True, default="ecm", max_length=20),
        ),
    ]
