import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """점검규칙(DownloadReviewRule)을 reference(PostgreSQL)로 이전한다.

    모델 상태(state)에는 0001_initial 에서 이미 DownloadReviewRule 이 존재하므로
    state_operations 는 비우고, 라우터가 reference 로만 허용하는 CreateModel 을
    database_operations 로 실행해 reference DB 에 inspection_rule 테이블을 만든다.

    - migrate --database=reference  : 이 CreateModel 이 실행되어 PG 에 테이블 생성
    - migrate (default) / --database=workflow : 라우터(allow_migrate)가 막아 건너뜀
      (workflow.db 의 기존 inspection_rule 은 더 이상 사용되지 않는 orphan 으로 남는다)
    """

    dependencies = [
        ('main', '0005_remove_downloadreviewruleresult_rule'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.CreateModel(
                    name='DownloadReviewRule',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('code', models.CharField(max_length=80, unique=True)),
                        ('name', models.CharField(max_length=255)),
                        ('target_file_pattern', models.CharField(blank=True, max_length=255)),
                        ('target_file_type', models.CharField(default='any', max_length=30)),
                        ('rule_type', models.CharField(blank=True, max_length=80)),
                        ('config_json', models.JSONField(blank=True, default=dict)),
                        ('severity', models.CharField(choices=[('error', 'Error'), ('warning', 'Warning'), ('info', 'Info')], default='error', max_length=20)),
                        ('enabled', models.BooleanField(db_index=True, default=True)),
                        ('version', models.CharField(default='1', max_length=40)),
                        ('sort_order', models.PositiveSmallIntegerField(default=0)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'db_table': 'inspection_rule',
                        'ordering': ['sort_order', 'name', 'id'],
                    },
                ),
            ],
        ),
    ]
