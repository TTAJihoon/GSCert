from django.db import migrations, models


def queue_legacy_scheduled_jobs(apps, schema_editor):
    DownloadReviewJob = apps.get_model("main", "DownloadReviewJob")
    DownloadReviewJob.objects.filter(status="scheduled").update(
        status="queued",
        queued_at=models.F("requested_at"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0012_manual_override_sub_check_key"),
    ]

    operations = [
        migrations.AlterField(
            model_name="downloadreviewjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "Scheduled"),
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("canceled", "Canceled"),
                ],
                db_index=True,
                default="queued",
                max_length=20,
            ),
        ),
        migrations.RunPython(queue_legacy_scheduled_jobs, migrations.RunPython.noop),
    ]
