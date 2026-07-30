import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0009_similaranalysisjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="DownloadReviewManualOverride",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("center_code", models.CharField(db_index=True, max_length=20)),
                ("project_number", models.CharField(db_index=True, max_length=32)),
                ("rule_code", models.CharField(db_index=True, max_length=80)),
                ("rule_name", models.CharField(blank=True, max_length=255)),
                ("memo", models.TextField()),
                ("created_by", models.CharField(blank=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("last_applied_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "inspection_manual_override",
                "indexes": [
                    models.Index(
                        fields=["center_code", "project_number"],
                        name="dr_manual_override_project_idx",
                    ),
                    models.Index(
                        fields=["project_number", "rule_code"],
                        name="dr_manual_override_rule_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["center_code", "project_number", "rule_code"],
                        name="dr_manual_override_rule_uniq",
                    ),
                ],
            },
        ),
    ]
