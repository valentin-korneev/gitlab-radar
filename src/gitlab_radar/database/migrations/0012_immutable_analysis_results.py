import functools
import hashlib
import json
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


METADATA_FIELDS = {
    'id',
    'name',
    'path_with_namespace',
    'default_branch',
    'web_url',
    'last_activity_at',
    'scanned_at',
    'webhooks',
    'webhooks_accessible',
    'gitlab_access_level',
    'revision',
    'is_empty',
}
DERIVED_FIELDS = {'frameworks', 'data_status', 'company_compliance_percentage', 'company_rule_results'}


class LegacyTransfer:
    def __init__(self, apps, connection):
        self.apps = apps
        self.connection = connection

    def model(self, name):
        return self.apps.get_model('models', name)

    async def result(self, row, status, *, fallback=False):
        payload = {key: value for key, value in row.payload.items() if key not in METADATA_FIELDS | DERIVED_FIELDS}
        payload['languages'] = [
            {key: value for key, value in language.items() if key != 'percentage'}
            for language in row.payload.get('languages', [])
        ]
        payload['subprojects'] = [
            {key: value for key, value in module.items() if key not in DERIVED_FIELDS}
            for module in row.payload.get('subprojects', [])
        ]
        payload['analysis_status'] = status.value
        if fallback:
            payload['scan_error'] = None
            payload['analysis_diagnostics'] = []
        identity = hashlib.sha256(
            json.dumps(
                [row.gitlab_id, None, row.analysis_fingerprint, payload],
                sort_keys=True,
                separators=(',', ':'),
            ).encode()
        ).hexdigest()
        result, created = await self.model('AnalysisResult').get_or_create(
            identity_key=identity,
            defaults={
                'gitlab_id': row.gitlab_id,
                'source_revision': row.payload.get('revision') or row.revision,
                'analysis_fingerprint': row.analysis_fingerprint,
                'status': status,
                'payload': payload,
            },
            using_db=self.connection,
        )
        if created:
            await self.languages(row.id, result.id)
        return result.id

    async def languages(self, snapshot_id, result_id):
        rows = await self.model('ProjectSnapshotLanguage').filter(project_id=snapshot_id).using_db(self.connection)
        for row in rows:
            language = await self.model('ResultLanguage').create(
                result_id=result_id,
                language_id=row.language_id,
                analysis_status=row.analysis_status,
                analyzer_version=row.analyzer_version,
                error=row.error,
                using_db=self.connection,
            )
            modules = await self.model('ProjectModule').filter(project_language_id=row.id).using_db(self.connection)
            for old in modules:
                module = await self.model('ResultModule').create(
                    result_language_id=language.id,
                    path=old.path,
                    payload={key: value for key, value in old.payload.items() if key not in DERIVED_FIELDS},
                    using_db=self.connection,
                )
                managers = await self.model('ModulePackageManager').filter(module_id=old.id).using_db(self.connection)
                for manager in managers:
                    await self.model('ResultModulePackageManager').create(
                        module_id=module.id,
                        package_manager_id=manager.package_manager_id,
                        using_db=self.connection,
                    )

    async def observation(self, row):
        metadata = {key: value for key, value in row.payload.items() if key in METADATA_FIELDS}
        metadata['languages'] = row.payload.get('languages', [])
        target, _ = await self.model('ScanTarget').get_or_create(
            gitlab_id=row.gitlab_id,
            kind=ScanTargetKind.BRANCH,
            ref=row.payload.get('default_branch') or '',
            using_db=self.connection,
        )
        await (
            self.model('ScanTarget')
            .filter(gitlab_id=row.gitlab_id)
            .exclude(id=target.id)
            .using_db(
                self.connection,
            )
            .update(is_default=False)
        )
        error = row.error or row.payload.get('scan_error')
        status = ProjectAnalysisStatus.PARTIAL if error else ProjectAnalysisStatus.SUCCESS
        result_id = None
        fallback_id = target.last_successful_result_id
        fallback_metadata = target.successful_metadata
        if row.analyzed:
            result_id = await self.result(row, status)
            state = ScanItemState.REUSED if row.reused and not error else ScanItemState(status.value)
        elif error:
            state = ScanItemState.FAILED
            if fallback_id is None and row.payload.get('subprojects'):
                fallback_id = await self.result(row, ProjectAnalysisStatus.PARTIAL, fallback=True)
                fallback_metadata = metadata
        else:
            state = ScanItemState.COLLECTED if row.collected else ScanItemState.PENDING
        if row.payload.get('data_status') == 'missing':
            state = ScanItemState.MISSING
        item = await self.model('ScanItem').create(
            scan_id=row.scan_id,
            target=target,
            result_id=result_id,
            fallback_result_id=fallback_id,
            metadata=metadata,
            fallback_metadata=fallback_metadata,
            revision=row.revision,
            analysis_fingerprint=row.analysis_fingerprint,
            state=state,
            error=error,
            scanned_at=row.payload.get('scanned_at'),
            using_db=self.connection,
        )
        pointers = {'is_default': True}
        if state != ScanItemState.MISSING:
            pointers['last_attempt_id'] = item.id
        if state not in {ScanItemState.PENDING, ScanItemState.COLLECTED}:
            pointers['last_completed_item_id'] = item.id
        if row.analyzed and not error and state != ScanItemState.MISSING:
            pointers.update(last_successful_result_id=result_id, successful_metadata=metadata)
        await self.model('ScanTarget').filter(id=target.id).using_db(self.connection).update(**pointers)
        await self.files(row.id, item.id)

    async def files(self, snapshot_id, item_id):
        rows = await self.model('ProjectFile').filter(project_id=snapshot_id).using_db(self.connection)
        for row in rows:
            file = await self.model('ScanFile').create(
                item_id=item_id,
                path=row.path,
                content=row.content,
                using_db=self.connection,
            )
            usages = (
                await self.model('ProjectFileUsage')
                .filter(file_id=row.id)
                .using_db(
                    self.connection,
                )
                .prefetch_related('project_language__language')
            )
            for usage in usages:
                code = usage.project_language.language.code if usage.project_language_id else None
                await self.model('ScanFileUsage').create(
                    file=file,
                    language_code=code,
                    analyzer_key=usage.analyzer_key,
                    role=usage.role,
                    using_db=self.connection,
                )


async def transfer_legacy_results(apps, schema_editor):
    transfer = LegacyTransfer(apps, schema_editor.client)
    cursor = 0
    while True:
        rows = (
            await transfer.model('ProjectSnapshot')
            .filter(id__gt=cursor)
            .using_db(
                schema_editor.client,
            )
            .order_by('id')
            .limit(200)
        )
        if not rows:
            break
        for row in rows:
            await transfer.observation(row)
            cursor = row.id


class RemoveLegacyLanguageState(ops.RemoveField):
    """Migration 0005 already removed this column through SQL; reconcile only ORM state."""

    async def database_forward(self, app_label, old_state, new_state, state_editor=None):
        return None

    async def database_backward(self, app_label, old_state, new_state, state_editor=None):
        return None


class Migration(migrations.Migration):
    dependencies = [('models', '0011_webhook_privacy')]

    operations = [
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
        ops.AddField(
            model_name='ScanTarget',
            name='last_successful_result',
            field=fields.ForeignKeyField(
                'models.AnalysisResult',
                source_field='last_successful_result_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name=False,
                on_delete=OnDelete.RESTRICT,
            ),
        ),
        ops.RunPython(transfer_legacy_results),
        RemoveLegacyLanguageState(model_name='CompanyRequirement', name='language'),
        ops.DeleteModel(name='ModulePackageManager'),
        ops.DeleteModel(name='ProjectFileUsage'),
        ops.DeleteModel(name='ProjectFile'),
        ops.DeleteModel(name='ProjectModule'),
        ops.DeleteModel(name='ProjectSnapshotLanguage'),
        ops.DeleteModel(name='ProjectSnapshot'),
    ]
