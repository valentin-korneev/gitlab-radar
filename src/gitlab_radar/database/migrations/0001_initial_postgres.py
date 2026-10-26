import functools
from json import dumps, loads
from typing import ClassVar

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    initial = True

    operations: ClassVar[list[object]] = [
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
            ],
            options={'table': 'applicationparameter', 'app': 'models', 'pk_attr': 'key'},
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
            name='ProjectSnapshot',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'scan',
                    fields.ForeignKeyField(
                        'models.ScanRun',
                        source_field='scan_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='projects',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('gitlab_id', fields.BigIntField(db_index=True)),
                ('revision', fields.CharField(null=True, db_index=True, max_length=128)),
                ('payload', fields.JSONField(encoder=functools.partial(dumps, separators=(',', ':')), decoder=loads)),
                ('collected', fields.BooleanField(default=False)),
                ('analyzed', fields.BooleanField(default=False)),
                ('reused', fields.BooleanField(default=False)),
                ('error', fields.TextField(null=True, unique=False)),
            ],
            options={
                'table': 'projectsnapshot',
                'app': 'models',
                'unique_together': (('scan', 'gitlab_id'),),
                'pk_attr': 'id',
            },
            bases=['RadarModel'],
        ),
        ops.CreateModel(
            name='ProjectFile',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                (
                    'project',
                    fields.ForeignKeyField(
                        'models.ProjectSnapshot',
                        source_field='project_id',
                        db_constraint=True,
                        to_field='id',
                        related_name='files',
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ('path', fields.CharField(max_length=1000)),
                ('content', fields.TextField(unique=False)),
            ],
            options={
                'table': 'projectfile',
                'app': 'models',
                'unique_together': (('project', 'path'),),
                'pk_attr': 'id',
            },
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
    ]
