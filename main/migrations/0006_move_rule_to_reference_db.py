from django.db import migrations, router


def create_rule_table_if_missing(apps, schema_editor):
    """점검규칙 테이블(inspection_rule)을 라우팅된 home alias 에 *없을 때만* 만든다.

    배경: 0001_initial 이 이미 일반 CreateModel 로 inspection_rule 을 생성한다.
    이 0006 의 원래 목적은 *기존 운영 배포*에서 테이블을 reference(PostgreSQL)로
    옮기는 것뿐이며, fresh DB(테스트 러너가 매번 만드는 DB) 에서는 0001 이 이미
    home alias 에 테이블을 만들어 두므로 0006 은 건너뛰어야 한다.

    과거 구현은 `database_operations=[CreateModel(...)]` 로 무조건 재생성해서,
    fresh 빌드(특히 ui_mock_settings 의 workflow alias)에서 "table already exists"
    로 전체 테스트가 깨졌다. 라우터 게이트 + 존재 여부 확인으로 멱등하게 만든다.
    """
    Model = apps.get_model("main", "DownloadReviewRule")
    alias = schema_editor.connection.alias
    # 라우터가 이 alias 에 이 모델 생성을 허용하지 않으면 skip
    # (운영: reference 만, ui_mock: workflow 만 — 0001 의 self-gating 과 동일 동작).
    if not router.allow_migrate_model(alias, Model):
        return
    table = Model._meta.db_table
    if table in schema_editor.connection.introspection.table_names():
        return  # 0001 에서 이미 생성됨(fresh 빌드) → 멱등 no-op
    schema_editor.create_model(Model)


class Migration(migrations.Migration):
    """점검규칙(DownloadReviewRule)을 reference(PostgreSQL)로 이전한다(멱등).

    모델 상태(state)에는 0001_initial 에서 이미 DownloadReviewRule 이 존재하므로
    상태는 건드리지 않고(RunPython 은 state 무변경), DB 작업만 수행한다.

    - migrate --database=reference : reference 에 테이블이 없으면 생성(최초 이전)
    - migrate (default)/--database=workflow : 라우터(allow_migrate)가 막아 skip
    - fresh DB(테스트) : 0001 이 이미 home alias 에 생성 → 존재 확인 후 no-op
    """

    dependencies = [
        ("main", "0005_remove_downloadreviewruleresult_rule"),
    ]

    operations = [
        # reverse 는 noop: inspection_rule 은 migration state 상 0001 에서 추가되어
        # 0005 로 롤백해도 여전히 존재해야 한다. 0006 의 정방향은 legacy 배포용 DB
        # 보정(state 무변경)이므로, 그 역방향에서 0001 의 테이블을 지우면 state 와
        # 실제 DB 가 어긋난다. 따라서 reverse 에서는 아무것도 하지 않는다.
        migrations.RunPython(
            create_rule_table_if_missing,
            migrations.RunPython.noop,
        ),
    ]
