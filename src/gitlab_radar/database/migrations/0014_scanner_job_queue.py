import functools
from enum import StrEnum
from json import dumps, loads

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class ScanSource(StrEnum):
    MANUAL = 'manual'
    SCHEDULE = 'schedule'


class ScanState(StrEnum):
    IDLE = 'idle'
    QUEUED = 'queued'
    RUNNING = 'running'
    STOPPING = 'stopping'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'
    FAILED = 'failed'


class Migration(migrations.Migration):
    dependencies = [('models', '0013_snake_case_tables')]

    initial = False

    operations = [
        ops.AlterField(
            model_name='ScanRun',
            name='started_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AlterField(
            model_name='ScanRun',
            name='state',
            field=fields.CharEnumField(
                default=ScanState.QUEUED,
                description='IDLE: idle\nQUEUED: queued\nRUNNING: running\nSTOPPING: stopping\nCANCELLED: cancelled\nCOMPLETED: completed\nFAILED: failed',
                enum_type=ScanState,
                max_length=20,
            ),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='created_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=True),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='heartbeat_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='lease_expires_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='owner_token',
            field=fields.UUIDField(null=True),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='requested_by',
            field=fields.CharField(null=True, max_length=255),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='source',
            field=fields.CharEnumField(
                null=True,
                default=ScanSource.MANUAL,
                description='MANUAL: manual\nSCHEDULE: schedule',
                enum_type=ScanSource,
                max_length=20,
            ),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='stop_requested_at',
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name='ScanRun',
            name='updated_project_ids',
            field=fields.JSONField(
                null=True, default=list, encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads
            ),
        ),
        ops.RunSQL(
            "UPDATE scan_run SET created_at = COALESCE(started_at, NOW()), source = 'manual', updated_project_ids = '[]'::jsonb",
            reverse_sql='SELECT 1',
        ),
        ops.AlterField(model_name='ScanRun', name='created_at', field=fields.DatetimeField(auto_now_add=True)),
        ops.AlterField(
            model_name='ScanRun',
            name='source',
            field=fields.CharEnumField(ScanSource, default=ScanSource.MANUAL, max_length=20),
        ),
        ops.AlterField(model_name='ScanRun', name='updated_project_ids', field=fields.JSONField(default=list)),
    ]
