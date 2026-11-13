import functools
from enum import StrEnum
from json import dumps, loads

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class ProjectAnalysisStatus(StrEnum):
    PENDING = 'pending'
    SUCCESS = 'success'
    PARTIAL = 'partial'
    FAILED = 'failed'


class LanguageAnalysisStatus(StrEnum):
    PENDING = 'pending'
    DISABLED = 'disabled'
    UNSUPPORTED = 'unsupported'
    ANALYZED = 'analyzed'
    PARTIAL = 'partial'
    FAILED = 'failed'


class ScanItemState(StrEnum):
    PENDING = 'pending'
    COLLECTED = 'collected'
    SUCCESS = 'success'
    PARTIAL = 'partial'
    FAILED = 'failed'
    REUSED = 'reused'
    MISSING = 'missing'
    SKIPPED = 'skipped'


class ScanTargetKind(StrEnum):
    BRANCH = 'branch'
    MERGE_REQUEST = 'merge_request'


INITIAL_DATA = {
    'languages': [
        {'code': 'python', 'name': 'Python', 'enabled': True, 'oldest_current_version': '3.11'},
        {'code': 'java', 'name': 'Java', 'enabled': False, 'oldest_current_version': '8'},
        {'code': 'javascript', 'name': 'JavaScript', 'enabled': False, 'oldest_current_version': '22'},
        {'code': 'typescript', 'name': 'TypeScript', 'enabled': False, 'oldest_current_version': '22'},
    ],
    'managers': [
        {'code': 'pip', 'name': 'pip'},
        {'code': 'uv', 'name': 'uv'},
        {'code': 'maven', 'name': 'Maven'},
        {'code': 'gradle', 'name': 'Gradle'},
        {'code': 'npm', 'name': 'npm'},
        {'code': 'yarn', 'name': 'Yarn'},
        {'code': 'pnpm', 'name': 'pnpm'},
    ],
    'frameworks': [
        {
            'code': 'java-micronaut',
            'name': 'Micronaut',
            'language': 'java',
            'dependency_names': [
                'io.micronaut:*',
                'io.micronaut.*:*',
                'io.micronaut.application',
                'io.micronaut.library',
            ],
            'enabled': True,
        },
        {
            'code': 'java-quarkus',
            'name': 'Quarkus',
            'language': 'java',
            'dependency_names': ['io.quarkus:*', 'io.quarkus'],
            'enabled': True,
        },
        {
            'code': 'java-spring',
            'name': 'Spring',
            'language': 'java',
            'dependency_names': ['org.springframework:*', 'org.springframework.boot:*', 'org.springframework.boot'],
            'enabled': True,
        },
        {
            'code': 'javascript-svelte',
            'name': 'Svelte',
            'language': 'javascript',
            'dependency_names': ['svelte'],
            'enabled': True,
        },
        {
            'code': 'javascript-next',
            'name': 'Next.js',
            'language': 'javascript',
            'dependency_names': ['next'],
            'enabled': True,
        },
        {
            'code': 'javascript-angular',
            'name': 'Angular',
            'language': 'javascript',
            'dependency_names': ['@angular/core'],
            'enabled': True,
        },
        {
            'code': 'javascript-vue',
            'name': 'Vue',
            'language': 'javascript',
            'dependency_names': ['vue'],
            'enabled': True,
        },
        {
            'code': 'javascript-react',
            'name': 'React',
            'language': 'javascript',
            'dependency_names': ['react'],
            'enabled': True,
        },
        {
            'code': 'typescript-svelte',
            'name': 'Svelte',
            'language': 'typescript',
            'dependency_names': ['svelte'],
            'enabled': True,
        },
        {
            'code': 'typescript-next',
            'name': 'Next.js',
            'language': 'typescript',
            'dependency_names': ['next'],
            'enabled': True,
        },
        {
            'code': 'typescript-angular',
            'name': 'Angular',
            'language': 'typescript',
            'dependency_names': ['@angular/core'],
            'enabled': True,
        },
        {
            'code': 'typescript-vue',
            'name': 'Vue',
            'language': 'typescript',
            'dependency_names': ['vue'],
            'enabled': True,
        },
        {
            'code': 'typescript-react',
            'name': 'React',
            'language': 'typescript',
            'dependency_names': ['react'],
            'enabled': True,
        },
        {
            'code': 'starlette',
            'name': 'Starlette',
            'language': 'python',
            'dependency_names': ['starlette'],
            'enabled': True,
        },
        {'code': 'flask', 'name': 'Flask', 'language': 'python', 'dependency_names': ['flask'], 'enabled': True},
        {'code': 'django', 'name': 'Django', 'language': 'python', 'dependency_names': ['django'], 'enabled': True},
        {'code': 'fastapi', 'name': 'FastAPI', 'language': 'python', 'dependency_names': ['fastapi'], 'enabled': True},
    ],
    'language_managers': [
        {'language': 'python', 'manager': 'pip'},
        {'language': 'python', 'manager': 'uv'},
        {'language': 'java', 'manager': 'maven'},
        {'language': 'java', 'manager': 'gradle'},
        {'language': 'javascript', 'manager': 'npm'},
        {'language': 'typescript', 'manager': 'npm'},
        {'language': 'javascript', 'manager': 'yarn'},
        {'language': 'typescript', 'manager': 'yarn'},
        {'language': 'javascript', 'manager': 'pnpm'},
        {'language': 'typescript', 'manager': 'pnpm'},
    ],
}

import secrets


async def ensure_fresh_database(apps, schema_editor):
    rows = await schema_editor.client.execute_query_dict(
        "SELECT name FROM tortoise_migrations WHERE app = 'models'",
    )
    if rows:
        message = (
            'Свернутая миграция поддерживает пустую БД или БД с примененной 0012. '
            'Для частично обновленной БД сначала примените 0012 из предыдущей версии приложения.'
        )
        raise RuntimeError(message)


async def seed_defaults(apps, schema_editor):
    connection = schema_editor.client
    language_model = apps.get_model('models', 'ProgrammingLanguage')
    manager_model = apps.get_model('models', 'PackageManagerCatalog')
    languages = {}
    managers = {}
    for item in INITIAL_DATA['languages']:
        languages[item['code']] = await language_model.create(**item, using_db=connection)
    for item in INITIAL_DATA['managers']:
        managers[item['code']] = await manager_model.create(**item, using_db=connection)
    framework_model = apps.get_model('models', 'ProgrammingFramework')
    for item in INITIAL_DATA['frameworks']:
        values = {key: value for key, value in item.items() if key != 'language'}
        await framework_model.create(**values, language=languages[item['language']], using_db=connection)
    link_model = apps.get_model('models', 'LanguagePackageManager')
    for item in INITIAL_DATA['language_managers']:
        await link_model.create(
            language=languages[item['language']], package_manager=managers[item['manager']], using_db=connection
        )
    secret_model = apps.get_model('models', 'ApplicationSecret')
    await secret_model.create(name='webhook-masking', value=secrets.token_hex(32), using_db=connection)


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.RunPython(ensure_fresh_database),
        ops.CreateModel(
            name='AdminVisibilityPolicy',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(unique=True, max_length=100)),
            ],
            options={'table': 'adminvisibilitypolicy', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='AdminVisibilityPolicyRule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'policy',
                    fields.ForeignKeyField(
                        'models.AdminVisibilityPolicy',
                        source_field='policy_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='rules',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('action', fields.CharField(max_length=10)),
                ('pattern', fields.CharField(max_length=500)),
                ('sort_order', fields.IntField(default=0)),
                ('target', fields.CharField(default='path', db_default='path', max_length=20)),
            ],
            options={'table': 'adminvisibilitypolicyrule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='AnalysisResult',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('gitlab_id', fields.BigIntField(db_index=True)),
                ('source_revision', fields.CharField(null=True, max_length=128)),
                ('analysis_fingerprint', fields.CharField(db_index=True, max_length=64)),
                ('input_digest', fields.CharField(null=True, db_index=True, max_length=64)),
                ('cache_key', fields.CharField(null=True, unique=True, max_length=64)),
                ('identity_key', fields.CharField(unique=True, max_length=64)),
                (
                    'status',
                    fields.CharEnumField(
                        db_index=True,
                        description='PENDING: pending\nSUCCESS: success\nPARTIAL: partial\nFAILED: failed',
                        enum_type=ProjectAnalysisStatus,
                        max_length=20,
                    ),
                ),
                ('payload', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={
                'table': 'analysis_result',
                'app': 'models',
                'indexes': [Index(fields=['gitlab_id', 'source_revision', 'analysis_fingerprint'])],
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ApplicationSecret',
            fields=[
                ('name', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=100)),
                ('value', fields.TextField(unique=False)),
            ],
            options={'table': 'application_secret', 'app': 'models', 'pk_attr': 'name'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='AuthorizedUser',
            fields=[
                ('preferred_username', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=255)),
                ('is_admin', fields.BooleanField(default=False)),
                ('is_blocked', fields.BooleanField(default=False)),
            ],
            options={'table': 'authorized_user', 'app': 'models', 'pk_attr': 'preferred_username'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='AdminUserVisibilityRule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'user',
                    fields.ForeignKeyField(
                        'models.AuthorizedUser',
                        source_field='user_id',
                        db_constraint=True,
                        to_field='preferred_username',
                        related_name='admin_visibility_rules',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('action', fields.CharField(max_length=10)),
                ('pattern', fields.CharField(max_length=500)),
                ('sort_order', fields.IntField(default=0)),
                ('target', fields.CharField(default='path', db_default='path', max_length=20)),
            ],
            options={'table': 'adminuservisibilityrule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='AdminVisibilityPolicyAssignment',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'policy',
                    fields.ForeignKeyField(
                        'models.AdminVisibilityPolicy',
                        source_field='policy_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='assignments',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'user',
                    fields.ForeignKeyField(
                        'models.AuthorizedUser',
                        source_field='user_id',
                        db_constraint=True,
                        to_field='preferred_username',
                        related_name='visibility_policy_assignments',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
            ],
            options={
                'table': 'adminvisibilitypolicyassignment',
                'app': 'models',
                'unique_together': (('policy', 'user'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='CompanyRequirementGroup',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(unique=True, max_length=100)),
                ('description', fields.TextField(default='', unique=False)),
                ('sort_order', fields.IntField(default=0)),
            ],
            options={'table': 'companyrequirementgroup', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='CompanyRequirement',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(unique=True, max_length=100)),
                ('title', fields.CharField(max_length=200)),
                (
                    'group',
                    fields.ForeignKeyField(
                        'models.CompanyRequirementGroup',
                        source_field='group_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='requirements',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ('description', fields.TextField(default='', unique=False)),
                ('condition', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('enabled', fields.BooleanField(default=True, db_index=True)),
                ('sort_order', fields.IntField(default=0)),
            ],
            options={'table': 'companyrequirement', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='DataFixture',
            fields=[
                ('name', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=100)),
            ],
            options={'table': 'datafixture', 'app': 'models', 'pk_attr': 'name'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='PackageManagerCatalog',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(unique=True, max_length=100)),
                ('name', fields.CharField(max_length=100)),
            ],
            options={'table': 'package_manager', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProgrammingLanguage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(unique=True, max_length=100)),
                ('name', fields.CharField(unique=True, max_length=100)),
                ('enabled', fields.BooleanField(default=False, db_index=True)),
                ('oldest_current_version', fields.CharField(null=True, max_length=50)),
            ],
            options={'table': 'programming_language', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ApplicationParameter',
            fields=[
                ('key', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=100)),
                ('title', fields.CharField(max_length=200)),
                ('description', fields.TextField(default='', unique=False)),
                ('value', fields.CharField(max_length=500)),
                ('value_type', fields.CharField(default='string', max_length=30)),
                ('min_value', fields.IntField(null=True)),
                ('max_value', fields.IntField(null=True)),
                ('sort_order', fields.IntField(default=0)),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        null=True,
                        db_constraint=True,
                        related_name='application_parameters',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={'table': 'applicationparameter', 'app': 'models', 'pk_attr': 'key'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='CompanyRequirementLanguage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'requirement',
                    fields.ForeignKeyField(
                        'models.CompanyRequirement',
                        source_field='requirement_id',
                        db_constraint=True,
                        related_name='language_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        db_constraint=True,
                        related_name='requirement_links',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                'table': 'company_requirement_language',
                'app': 'models',
                'unique_together': (('requirement', 'language'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='LanguagePackageManager',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        db_constraint=True,
                        related_name='package_manager_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'package_manager',
                    fields.ForeignKeyField(
                        'models.PackageManagerCatalog',
                        source_field='package_manager_id',
                        db_constraint=True,
                        related_name='language_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
            ],
            options={
                'table': 'language_package_manager',
                'app': 'models',
                'unique_together': (('language', 'package_manager'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProgrammingFramework',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(unique=True, max_length=100)),
                ('name', fields.CharField(max_length=100)),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        db_constraint=True,
                        related_name='frameworks',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'dependency_names',
                    fields.JSONField(
                        default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                ('enabled', fields.BooleanField(default=True, db_index=True)),
            ],
            options={'table': 'programming_framework', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProjectBlacklistRule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('pattern', fields.CharField(unique=True, max_length=500)),
            ],
            options={'table': 'project_blacklist_rule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ResultLanguage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'result',
                    fields.ForeignKeyField(
                        'models.AnalysisResult',
                        source_field='result_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='languages',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='results',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                (
                    'analysis_status',
                    fields.CharEnumField(
                        description='PENDING: pending\nDISABLED: disabled\nUNSUPPORTED: unsupported\nANALYZED: analyzed\nPARTIAL: partial\nFAILED: failed',
                        enum_type=LanguageAnalysisStatus,
                        max_length=20,
                    ),
                ),
                ('analyzer_version', fields.CharField(null=True, max_length=50)),
                ('error', fields.TextField(null=True, unique=False)),
            ],
            options={
                'table': 'result_language',
                'app': 'models',
                'unique_together': (('result', 'language'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ResultModule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'result_language',
                    fields.ForeignKeyField(
                        'models.ResultLanguage',
                        source_field='result_language_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='modules',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('path', fields.CharField(max_length=1000)),
                ('payload', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
            ],
            options={
                'table': 'result_module',
                'app': 'models',
                'unique_together': (('result_language', 'path'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ResultModulePackageManager',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'module',
                    fields.ForeignKeyField(
                        'models.ResultModule',
                        source_field='module_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='package_manager_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'package_manager',
                    fields.ForeignKeyField(
                        'models.PackageManagerCatalog',
                        source_field='package_manager_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='result_module_links',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                'table': 'result_module_package_manager',
                'app': 'models',
                'unique_together': (('module', 'package_manager'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ScanRun',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('state', fields.CharField(max_length=20)),
                ('phase', fields.CharField(default='idle', max_length=20)),
                ('started_at', fields.DatetimeField(auto_now=False, auto_now_add=False)),
                ('completed_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('projects_count', fields.IntField(default=0)),
                ('total_steps', fields.IntField(default=0)),
                ('completed_steps', fields.IntField(default=0)),
                ('collected_projects', fields.IntField(default=0)),
                ('analyzed_projects', fields.IntField(default=0)),
                ('reused_projects', fields.IntField(default=0)),
                ('skipped_projects', fields.IntField(default=0)),
                ('gitlab_requests', fields.IntField(default=0)),
                ('current_project', fields.CharField(null=True, max_length=500)),
                ('error', fields.TextField(null=True, unique=False)),
                (
                    'errors',
                    fields.JSONField(
                        default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                ('published', fields.BooleanField(default=False, db_index=True)),
            ],
            options={'table': 'scanrun', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ScanTarget',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('gitlab_id', fields.BigIntField(db_index=True)),
                (
                    'kind',
                    fields.CharEnumField(
                        default=ScanTargetKind.BRANCH,
                        description='BRANCH: branch\nMERGE_REQUEST: merge_request',
                        enum_type=ScanTargetKind,
                        max_length=20,
                    ),
                ),
                ('ref', fields.CharField(max_length=500)),
                ('is_default', fields.BooleanField(default=True, db_index=True)),
                (
                    'successful_metadata',
                    fields.JSONField(
                        default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                (
                    'last_successful_result',
                    fields.ForeignKeyField(
                        'models.AnalysisResult',
                        source_field='last_successful_result_id',
                        null=True,
                        db_constraint=True,
                        to_field='id',
                        related_name=False,
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                'table': 'scan_target',
                'app': 'models',
                'unique_together': (('gitlab_id', 'kind', 'ref'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ScanItem',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'scan',
                    fields.ForeignKeyField(
                        'models.ScanRun',
                        source_field='scan_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='items',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'target',
                    fields.ForeignKeyField(
                        'models.ScanTarget',
                        source_field='target_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='items',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                (
                    'result',
                    fields.ForeignKeyField(
                        'models.AnalysisResult',
                        source_field='result_id',
                        null=True,
                        db_constraint=True,
                        to_field='id',
                        related_name='observations',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                (
                    'fallback_result',
                    fields.ForeignKeyField(
                        'models.AnalysisResult',
                        source_field='fallback_result_id',
                        null=True,
                        db_constraint=True,
                        to_field='id',
                        related_name='fallback_observations',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ('metadata', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                (
                    'fallback_metadata',
                    fields.JSONField(
                        default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                ('revision', fields.CharField(null=True, max_length=128)),
                ('analysis_fingerprint', fields.CharField(default='', max_length=64)),
                ('input_digest', fields.CharField(null=True, max_length=64)),
                (
                    'state',
                    fields.CharEnumField(
                        default=ScanItemState.PENDING,
                        db_index=True,
                        description='PENDING: pending\nCOLLECTED: collected\nSUCCESS: success\nPARTIAL: partial\nFAILED: failed\nREUSED: reused\nMISSING: missing\nSKIPPED: skipped',
                        enum_type=ScanItemState,
                        max_length=20,
                    ),
                ),
                ('error', fields.TextField(null=True, unique=False)),
                ('scanned_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
            ],
            options={
                'table': 'scan_item',
                'app': 'models',
                'unique_together': (('scan', 'target'),),
                'indexes': [Index(fields=['target_id', 'revision', 'analysis_fingerprint'])],
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ScanFile',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'item',
                    fields.ForeignKeyField(
                        'models.ScanItem',
                        source_field='item_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='files',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('path', fields.CharField(max_length=1000)),
                ('content', fields.TextField(unique=False)),
            ],
            options={'table': 'scan_file', 'app': 'models', 'unique_together': (('item', 'path'),), 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ScanFileUsage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'file',
                    fields.ForeignKeyField(
                        'models.ScanFile',
                        source_field='file_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='usages',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('language_code', fields.CharField(null=True, max_length=100)),
                ('analyzer_key', fields.CharField(max_length=100)),
                ('role', fields.CharField(max_length=30)),
            ],
            options={
                'table': 'scan_file_usage',
                'app': 'models',
                'unique_together': (('file', 'analyzer_key', 'role', 'language_code'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='UserVisibilityGroup',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'user',
                    fields.ForeignKeyField(
                        'models.AuthorizedUser',
                        source_field='user_id',
                        db_constraint=True,
                        to_field='preferred_username',
                        related_name='visibility_groups',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('name', fields.CharField(max_length=100)),
                ('is_active', fields.BooleanField(default=False, db_index=True)),
                ('sort_order', fields.IntField(default=0)),
            ],
            options={
                'table': 'uservisibilitygroup',
                'app': 'models',
                'unique_together': (('user', 'name'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='UserVisibilityRule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'group',
                    fields.ForeignKeyField(
                        'models.UserVisibilityGroup',
                        source_field='group_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='rules',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('action', fields.CharField(max_length=10)),
                ('pattern', fields.CharField(max_length=500)),
                ('sort_order', fields.IntField(default=0)),
                ('target', fields.CharField(default='path', db_default='path', max_length=20)),
            ],
            options={'table': 'uservisibilityrule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='WebSession',
            fields=[
                ('token_hash', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('encrypted_tokens', fields.TextField(unique=False)),
                ('csrf_hash', fields.CharField(max_length=64)),
                ('expires_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'websession', 'app': 'models', 'pk_attr': 'token_hash'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='WebSocketTicket',
            fields=[
                ('token_hash', fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64)),
                ('expires_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False)),
            ],
            options={'table': 'websocketticket', 'app': 'models', 'pk_attr': 'token_hash'},
            bases=['RadarModel'],
        ),
        ops.AddField(
            model_name='ScanTarget',
            name='last_attempt',
            field=fields.ForeignKeyField(
                'models.ScanItem',
                source_field='last_attempt_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name=False,
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.AddField(
            model_name='ScanTarget',
            name='last_completed_item',
            field=fields.ForeignKeyField(
                'models.ScanItem',
                source_field='last_completed_item_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name=False,
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.RunPython(seed_defaults),
    ]
