from django.db import migrations, router


def create_manual_override_table_if_missing(apps, schema_editor):
    Model = apps.get_model("main", "DownloadReviewManualOverride")
    alias = schema_editor.connection.alias
    if not router.allow_migrate_model(alias, Model):
        return
    table = Model._meta.db_table
    if table in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(Model)


class Migration(migrations.Migration):
    """Ensure manual pass overrides live in the routed reference database.

    0010 introduced the model while it was still routed to workflow. On a
    reference database, that migration may already be recorded as applied
    without creating the table. This DB-only, idempotent migration creates the
    table on the current routed alias when it is missing.
    """

    dependencies = [
        ("main", "0010_downloadreviewmanualoverride"),
    ]

    operations = [
        migrations.RunPython(
            create_manual_override_table_if_missing,
            migrations.RunPython.noop,
        ),
    ]
