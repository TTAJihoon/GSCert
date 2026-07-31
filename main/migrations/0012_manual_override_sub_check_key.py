from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0011_manual_override_reference_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="downloadreviewmanualoverride",
            name="sub_check_key",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.RemoveConstraint(
            model_name="downloadreviewmanualoverride",
            name="dr_manual_override_rule_uniq",
        ),
        migrations.AddConstraint(
            model_name="downloadreviewmanualoverride",
            constraint=models.UniqueConstraint(
                fields=["center_code", "project_number", "rule_code", "sub_check_key"],
                name="dr_manual_override_scope_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="downloadreviewmanualoverride",
            index=models.Index(
                fields=["project_number", "rule_code", "sub_check_key"],
                name="dr_manual_override_scope_idx",
            ),
        ),
    ]
