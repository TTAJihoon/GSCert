from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0013_retire_download_review_time_window"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServerTimeControl",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("idle", "Idle"), ("changing", "Changing"), ("active", "Active"), ("restoring", "Restoring"), ("recovery_failed", "Recovery failed")], db_index=True, default="idle", max_length=24)),
                ("revision", models.PositiveBigIntegerField(default=1)),
                ("pending_action", models.CharField(blank=True, max_length=16)),
                ("owner_name", models.CharField(blank=True, max_length=80)),
                ("pin_hash", models.CharField(blank=True, max_length=255)),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("target_time", models.DateTimeField(blank=True, null=True)),
                ("normal_time_before_change", models.DateTimeField(blank=True, null=True)),
                ("baseline_uptime_ms", models.PositiveBigIntegerField(blank=True, null=True)),
                ("expires_uptime_ms", models.PositiveBigIntegerField(blank=True, null=True)),
                ("w32time_was_running", models.BooleanField(default=True)),
                ("failed_pin_attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_pin_failure_uptime_ms", models.PositiveBigIntegerField(blank=True, null=True)),
                ("agent_heartbeat_uptime_ms", models.PositiveBigIntegerField(blank=True, null=True)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "server_time_control"},
        ),
        migrations.CreateModel(
            name="ServerTimeAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_code", models.CharField(db_index=True, max_length=40)),
                ("owner_name", models.CharField(blank=True, max_length=80)),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("revision", models.PositiveBigIntegerField(default=0)),
                ("observed_os_time", models.DateTimeField()),
                ("normal_time_estimate", models.DateTimeField(blank=True, null=True)),
                ("detail_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "server_time_audit", "ordering": ["id"]},
        ),
    ]
