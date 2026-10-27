from typing import ClassVar

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
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
            ],
            options={'table': 'uservisibilityrule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
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
            ],
            options={'table': 'adminvisibilitypolicyrule', 'app': 'models', 'pk_attr': 'id'},
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
            ],
            options={'table': 'adminuservisibilityrule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
    ]
