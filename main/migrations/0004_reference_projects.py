from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0003_swdata"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReferenceCenterPl",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("center_code", models.CharField(db_index=True, max_length=20)),
                ("center_label", models.CharField(max_length=20)),
                ("name", models.CharField(max_length=50, unique=True)),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "reference_center_pl",
                "ordering": ["center_code", "display_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="ReferenceProject",
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
                "db_table": "reference_project",
                "ordering": ["-cert_committee_date", "project_number"],
            },
        ),
        migrations.AddIndex(
            model_name="referencecenterpl",
            index=models.Index(fields=["center_code", "name"], name="ref_center_pl_code_name_idx"),
        ),
        migrations.AddIndex(
            model_name="referenceproject",
            index=models.Index(fields=["center_code", "cert_committee_date"], name="ref_project_center_date_idx"),
        ),
        migrations.AddIndex(
            model_name="referenceproject",
            index=models.Index(fields=["center_code", "project_number"], name="ref_project_center_number_idx"),
        ),
        migrations.AddIndex(
            model_name="referenceproject",
            index=models.Index(fields=["primary_tester"], name="ref_project_primary_tester_idx"),
        ),
    ]
