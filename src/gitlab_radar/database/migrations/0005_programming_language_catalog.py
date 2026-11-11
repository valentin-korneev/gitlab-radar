from typing import ClassVar

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.CreateModel(
            name='ProgrammingLanguage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(max_length=100, unique=True)),
                ('name', fields.CharField(max_length=100, unique=True)),
                ('enabled', fields.BooleanField(default=False, db_index=True)),
                ('oldest_current_version', fields.CharField(max_length=50, null=True)),
            ],
            options={'table': 'programming_language', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProgrammingFramework',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(max_length=100, unique=True)),
                ('name', fields.CharField(max_length=100)),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        related_name='frameworks',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('dependency_names', fields.JSONField(default=list)),
                ('enabled', fields.BooleanField(default=True, db_index=True)),
            ],
            options={'table': 'programming_framework', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.AddField(
            model_name='ProjectSnapshot',
            name='analysis_fingerprint',
            field=fields.CharField(max_length=64, default='', db_default='', db_index=True),
        ),
        ops.CreateModel(
            name='ProjectSnapshotLanguage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'project',
                    fields.ForeignKeyField(
                        'models.ProjectSnapshot',
                        source_field='project_id',
                        related_name='languages',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
                        related_name='project_snapshots',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ('percentage', fields.DecimalField(max_digits=7, decimal_places=4)),
                ('analysis_status', fields.CharField(max_length=20, default='pending', db_index=True)),
                ('analyzer_version', fields.CharField(max_length=50, null=True)),
                ('error', fields.TextField(null=True)),
            ],
            options={
                'table': 'project_snapshot_language',
                'app': 'models',
                'unique_together': (('project', 'language'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProjectFileUsage',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'file',
                    fields.ForeignKeyField(
                        'models.ProjectFile',
                        source_field='file_id',
                        related_name='usages',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'project_language',
                    fields.ForeignKeyField(
                        'models.ProjectSnapshotLanguage',
                        source_field='project_language_id',
                        related_name='file_usages',
                        null=True,
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('analyzer_key', fields.CharField(max_length=100)),
                ('role', fields.CharField(max_length=30)),
            ],
            options={
                'table': 'project_file_usage',
                'app': 'models',
                'unique_together': (('file', 'analyzer_key', 'role', 'project_language'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProjectModule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'project_language',
                    fields.ForeignKeyField(
                        'models.ProjectSnapshotLanguage',
                        source_field='project_language_id',
                        related_name='modules',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('path', fields.CharField(max_length=1000)),
                ('payload', fields.JSONField()),
            ],
            options={
                'table': 'project_module',
                'app': 'models',
                'unique_together': (('project_language', 'path'),),
                'pk_attr': 'id',
            },
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
                        related_name='language_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'language',
                    fields.ForeignKeyField(
                        'models.ProgrammingLanguage',
                        source_field='language_id',
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
        ops.AddField(
            model_name='ApplicationParameter',
            name='language',
            field=fields.ForeignKeyField(
                'models.ProgrammingLanguage',
                source_field='language_id',
                related_name='application_parameters',
                null=True,
                on_delete=OnDelete.RESTRICT,
            ),
        ),
        ops.CreateModel(
            name='PackageManagerCatalog',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('code', fields.CharField(max_length=100, unique=True)),
                ('name', fields.CharField(max_length=100)),
            ],
            options={'table': 'package_manager', 'app': 'models', 'pk_attr': 'id'},
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
                        related_name='package_manager_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'package_manager',
                    fields.ForeignKeyField(
                        'models.PackageManagerCatalog',
                        source_field='package_manager_id',
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
            name='ModulePackageManager',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'module',
                    fields.ForeignKeyField(
                        'models.ProjectModule',
                        source_field='module_id',
                        related_name='package_manager_links',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                (
                    'package_manager',
                    fields.ForeignKeyField(
                        'models.PackageManagerCatalog',
                        source_field='package_manager_id',
                        related_name='module_links',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                'table': 'module_package_manager',
                'app': 'models',
                'unique_together': (('module', 'package_manager'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.RunSQL(
            sql=(
                'INSERT INTO programming_language (code, name, enabled) VALUES '
                "('python', 'Python', TRUE), "
                "('java', 'Java', FALSE), "
                "('javascript', 'JavaScript', FALSE), "
                "('typescript', 'TypeScript', FALSE) "
                'ON CONFLICT (code) DO NOTHING; '
                "UPDATE programming_language SET oldest_current_version = COALESCE(("
                "SELECT value FROM applicationparameter WHERE key = 'python_oldest_current_version'"
                "), '3.11') WHERE code = 'python'; "
                'INSERT INTO company_requirement_language (requirement_id, language_id) '
                'SELECT requirement.id, language.id FROM companyrequirement requirement '
                'JOIN programming_language language ON language.code = requirement.language '
                'WHERE requirement.language IS NOT NULL; '
                "DELETE FROM applicationparameter WHERE key = 'python_oldest_current_version'; "
                "INSERT INTO package_manager (code, name) VALUES ('pip', 'pip'), ('uv', 'uv') "
                'ON CONFLICT (code) DO NOTHING; '
                'INSERT INTO language_package_manager (language_id, package_manager_id) '
                'SELECT language.id, manager.id FROM programming_language language '
                "CROSS JOIN package_manager manager WHERE language.code = 'python' AND manager.code IN ('pip', 'uv') "
                'ON CONFLICT (language_id, package_manager_id) DO NOTHING; '
                'INSERT INTO programming_framework '
                '(code, name, language_id, dependency_names, enabled) '
                'SELECT definitions.code, definitions.name, language.id, '
                'definitions.dependencies::jsonb, TRUE '
                'FROM (VALUES '
                "('fastapi', 'FastAPI', 'python', '[\"fastapi\"]'), "
                "('django', 'Django', 'python', '[\"django\"]'), "
                "('flask', 'Flask', 'python', '[\"flask\"]'), "
                "('starlette', 'Starlette', 'python', '[\"starlette\"]'), "
                "('java-spring', 'Spring', 'java', "
                "'[\"org.springframework:spring-core\", \"org.springframework.boot:spring-boot\"]'), "
                "('java-quarkus', 'Quarkus', 'java', '[\"io.quarkus:quarkus-core\"]'), "
                "('java-micronaut', 'Micronaut', 'java', '[\"io.micronaut:micronaut-core\"]'), "
                "('javascript-react', 'React', 'javascript', '[\"react\"]'), "
                "('javascript-vue', 'Vue', 'javascript', '[\"vue\"]'), "
                "('javascript-angular', 'Angular', 'javascript', '[\"@angular/core\"]'), "
                "('javascript-next', 'Next.js', 'javascript', '[\"next\"]'), "
                "('javascript-svelte', 'Svelte', 'javascript', '[\"svelte\"]'), "
                "('typescript-react', 'React', 'typescript', '[\"react\"]'), "
                "('typescript-vue', 'Vue', 'typescript', '[\"vue\"]'), "
                "('typescript-angular', 'Angular', 'typescript', '[\"@angular/core\"]'), "
                "('typescript-next', 'Next.js', 'typescript', '[\"next\"]'), "
                "('typescript-svelte', 'Svelte', 'typescript', '[\"svelte\"]')"
                ') AS definitions(code, name, language_code, dependencies) '
                'JOIN programming_language language ON language.code = definitions.language_code '
                'ON CONFLICT (code) DO NOTHING; '
                'ALTER TABLE companyrequirement DROP COLUMN language'
            ),
            reverse_sql=(
                'ALTER TABLE companyrequirement ADD COLUMN language VARCHAR(50); '
                'UPDATE companyrequirement SET language = programming_language.code '
                'FROM company_requirement_language link '
                'JOIN programming_language ON programming_language.id = link.language_id '
                'WHERE link.requirement_id = companyrequirement.id; '
                'INSERT INTO applicationparameter '
                '(key, title, description, value, value_type, min_value, max_value, sort_order, language_id) '
                "SELECT 'python_oldest_current_version', 'Самая старая актуальная версия Python', "
                "'Эта версия помечается предупреждением, более ранние — как устаревшие, более новые — как актуальные.', "
                "COALESCE(oldest_current_version, '3.11'), 'version', NULL, NULL, 1, id "
                "FROM programming_language WHERE code = 'python' ON CONFLICT (key) DO NOTHING"
            ),
        ),
    ]
