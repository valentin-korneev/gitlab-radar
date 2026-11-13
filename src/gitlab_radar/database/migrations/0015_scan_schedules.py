from tortoise import migrations
from tortoise.migrations import operations as ops
import functools
from json import dumps, loads
from tortoise.fields.base import OnDelete
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [('models', '0014_scanner_job_queue')]

    initial = False

    operations = [
        ops.CreateModel(
            name='ScanSchedule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('name', fields.CharField(max_length=100)),
                ('enabled', fields.BooleanField(default=False)),
                ('time_of_day', fields.CharField(max_length=5)),
                (
                    'weekdays',
                    fields.JSONField(
                        default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                (
                    'options',
                    fields.JSONField(
                        default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
                    ),
                ),
                ('next_run_at', fields.DatetimeField(null=True, db_index=True, auto_now=False, auto_now_add=False)),
                ('last_run_at', fields.DatetimeField(null=True, auto_now=False, auto_now_add=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'scan_schedule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
        ops.AddField(
            model_name='ScanRun',
            name='options',
            field=fields.JSONField(
                null=True, default=dict, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.RunSQL("UPDATE scan_run SET options = '{}'::jsonb WHERE options IS NULL", reverse_sql='SELECT 1'),
        ops.AlterField(model_name='ScanRun', name='options', field=fields.JSONField(default=dict)),
        ops.AddField(
            model_name='ScanRun',
            name='retry_of',
            field=fields.ForeignKeyField(
                'models.ScanRun',
                source_field='retry_of_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name=False,
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='schedule',
            field=fields.ForeignKeyField(
                'models.ScanSchedule',
                source_field='schedule_id',
                null=True,
                db_constraint=True,
                to_field='id',
                related_name='runs',
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='schedule_name',
            field=fields.CharField(null=True, max_length=100),
        ),
    ]
