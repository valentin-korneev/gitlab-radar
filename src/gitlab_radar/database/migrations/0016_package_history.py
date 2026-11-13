from tortoise import migrations
from tortoise.migrations import operations as ops
import functools
from json import dumps, loads
from tortoise.fields.base import OnDelete
from tortoise import fields
from tortoise.indexes import Index


class Migration(migrations.Migration):
    dependencies = [('models', '0015_scan_schedules')]

    initial = False

    operations = [
        ops.CreateModel(
            name='PackageHistoryHead',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'target',
                    fields.ForeignKeyField(
                        'models.ScanTarget',
                        source_field='target_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='package_history_heads',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ('language', fields.CharField(max_length=100)),
                (
                    'last_scan',
                    fields.ForeignKeyField(
                        'models.ScanRun',
                        source_field='last_scan_id',
                        db_constraint=True,
                        to_field='id',
                        related_name=False,
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                'table': 'package_history_head',
                'app': 'models',
                'unique_together': (('target', 'language'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='PackagePeriod',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'target',
                    fields.ForeignKeyField(
                        'models.ScanTarget',
                        source_field='target_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='package_periods',
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ('package_key', fields.CharField(max_length=64)),
                ('language', fields.CharField(max_length=100)),
                ('module_path', fields.TextField(unique=False)),
                ('scope', fields.TextField(unique=False)),
                ('name', fields.TextField(unique=False)),
                (
                    'versions',
                    fields.JSONField(
                        default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                (
                    'scan_from',
                    fields.ForeignKeyField(
                        'models.ScanRun',
                        source_field='scan_from_id',
                        db_constraint=True,
                        to_field='id',
                        related_name=False,
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                (
                    'scan_to',
                    fields.ForeignKeyField(
                        'models.ScanRun',
                        source_field='scan_to_id',
                        db_constraint=True,
                        to_field='id',
                        related_name=False,
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                (
                    'closed_in',
                    fields.ForeignKeyField(
                        'models.ScanRun',
                        source_field='closed_in_id',
                        null=True,
                        db_constraint=True,
                        to_field='id',
                        related_name=False,
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
                ('baseline', fields.BooleanField(default=False)),
            ],
            options={
                'table': 'package_period',
                'app': 'models',
                'unique_together': (('target', 'package_key', 'scan_from'),),
                'indexes': [
                    Index(fields=['target_id', 'closed_in_id']),
                    Index(fields=['target_id', 'scan_from_id', 'package_key']),
                    Index(fields=['target_id', 'closed_in_id', 'package_key']),
                ],
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.AddField(
            model_name='ScanItem',
            name='added_packages',
            field=fields.IntField(null=True, default=0),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='baseline_languages',
            field=fields.JSONField(
                null=True, default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='carried_forward',
            field=fields.BooleanField(null=True, default=False),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='diagnostic_summary',
            field=fields.JSONField(
                null=True, default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='history_recorded',
            field=fields.BooleanField(null=True, default=False),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='observed_languages',
            field=fields.JSONField(
                null=True, default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='removed_packages',
            field=fields.IntField(null=True, default=0),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='results_archived',
            field=fields.BooleanField(null=True, default=False),
        ),
        ops.AddField(
            model_name='ScanItem',
            name='updated_packages',
            field=fields.IntField(null=True, default=0),
        ),
        ops.AddIndex(
            model_name='ScanItem',
            index=Index(fields=['target_id', 'history_recorded', 'scan_id']),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='results_archived',
            field=fields.BooleanField(null=True, default=False),
        ),
        ops.RunSQL('UPDATE scan_item SET added_packages = 0 WHERE added_packages IS NULL', reverse_sql='SELECT 1'),
        ops.AlterField(
            model_name='ScanItem',
            name='added_packages',
            field=fields.IntField(default=0),
        ),
        ops.RunSQL(
            "UPDATE scan_item SET baseline_languages = '[]'::jsonb WHERE baseline_languages IS NULL",
            reverse_sql='SELECT 1',
        ),
        ops.AlterField(
            model_name='ScanItem',
            name='baseline_languages',
            field=fields.JSONField(
                default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.RunSQL(
            'UPDATE scan_item SET carried_forward = FALSE WHERE carried_forward IS NULL', reverse_sql='SELECT 1'
        ),
        ops.AlterField(
            model_name='ScanItem',
            name='carried_forward',
            field=fields.BooleanField(default=False),
        ),
        ops.RunSQL(
            "UPDATE scan_item SET diagnostic_summary = '[]'::jsonb WHERE diagnostic_summary IS NULL",
            reverse_sql='SELECT 1',
        ),
        ops.AlterField(
            model_name='ScanItem',
            name='diagnostic_summary',
            field=fields.JSONField(
                default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.RunSQL(
            'UPDATE scan_item SET history_recorded = FALSE WHERE history_recorded IS NULL', reverse_sql='SELECT 1'
        ),
        ops.AlterField(
            model_name='ScanItem',
            name='history_recorded',
            field=fields.BooleanField(default=False),
        ),
        ops.RunSQL(
            "UPDATE scan_item SET observed_languages = '[]'::jsonb WHERE observed_languages IS NULL",
            reverse_sql='SELECT 1',
        ),
        ops.AlterField(
            model_name='ScanItem',
            name='observed_languages',
            field=fields.JSONField(
                default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.RunSQL('UPDATE scan_item SET removed_packages = 0 WHERE removed_packages IS NULL', reverse_sql='SELECT 1'),
        ops.AlterField(
            model_name='ScanItem',
            name='removed_packages',
            field=fields.IntField(default=0),
        ),
        ops.RunSQL(
            'UPDATE scan_item SET results_archived = FALSE WHERE results_archived IS NULL', reverse_sql='SELECT 1'
        ),
        ops.AlterField(
            model_name='ScanItem',
            name='results_archived',
            field=fields.BooleanField(default=False),
        ),
        ops.RunSQL('UPDATE scan_item SET updated_packages = 0 WHERE updated_packages IS NULL', reverse_sql='SELECT 1'),
        ops.AlterField(
            model_name='ScanItem',
            name='updated_packages',
            field=fields.IntField(default=0),
        ),
        ops.RunSQL(
            'UPDATE scan_run SET results_archived = FALSE WHERE results_archived IS NULL', reverse_sql='SELECT 1'
        ),
        ops.AlterField(
            model_name='ScanRun',
            name='results_archived',
            field=fields.BooleanField(default=False),
        ),
        ops.RunSQL(
            "UPDATE scan_item AS item SET carried_forward = TRUE FROM scan_run AS run, scan_target AS target WHERE item.scan_id = run.id AND item.target_id = target.id AND jsonb_typeof(run.options->'project_ids') = 'array' AND NOT (run.options->'project_ids' @> jsonb_build_array(target.gitlab_id))",
            reverse_sql='SELECT 1',
        ),
        ops.RunSQL(
            "UPDATE application_parameter SET description = 'Полные данные последних опубликованных снимков и завершенных запусков. Журнал и история пакетов сохраняются после очистки.' WHERE key = 'retained_scan_count'",
            reverse_sql="UPDATE application_parameter SET description = 'После публикации нового сканирования более старые результаты удаляются.' WHERE key = 'retained_scan_count'",
        ),
        ops.AddIndex(model_name='ScanRun', index=Index(fields=['results_archived', 'id'])),
        ops.AddIndex(model_name='ScanItem', index=Index(fields=['history_recorded', 'scan_id', 'id'])),
        ops.AddIndex(model_name='ScanItem', index=Index(fields=['results_archived', 'scan_id', 'id'])),
    ]
