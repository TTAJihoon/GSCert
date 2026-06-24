from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0002_downloadreview_center_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='SwData',
            fields=[
                ('serial_number', models.IntegerField(primary_key=True, serialize=False)),
                ('cert_number', models.TextField(blank=True, default='')),
                ('cert_date', models.TextField(blank=True, default='')),
                ('company', models.TextField(blank=True, default='')),
                ('product', models.TextField(blank=True, default='')),
                ('grade', models.TextField(blank=True, default='')),
                ('test_number', models.TextField(blank=True, default='')),
                ('sw_category', models.TextField(blank=True, default='')),
                ('product_desc', models.TextField(blank=True, default='')),
                ('total_wd', models.TextField(blank=True, default='')),
                ('renewal', models.TextField(blank=True, default='')),
                ('notes', models.TextField(blank=True, default='')),
                ('date_range', models.TextField(blank=True, default='')),
                ('test_lab', models.TextField(blank=True, default='')),
                ('start_date', models.TextField(blank=True, default='')),
                ('end_date', models.TextField(blank=True, default='')),
            ],
            options={
                'db_table': 'sw_data',
            },
        ),
    ]
