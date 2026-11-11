from typing import ClassVar

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.AddField(
            model_name='CompanyRequirement',
            name='language',
            field=fields.CharField(max_length=50, null=True, db_index=True),
        ),
        ops.RunSQL(
            sql=(
                "UPDATE companyrequirement SET language = 'python' "
                "WHERE code IN ('uv-required', 'ruff-required', 'bandit-required', 'pylint-required', "
                "'python-linters-component-required', 'python-version-current')"
            ),
            reverse_sql='UPDATE companyrequirement SET language = NULL',
        ),
        ops.AddField(
            model_name='UserVisibilityRule',
            name='target',
            field=fields.CharField(max_length=20, default='path', db_default='path'),
        ),
        ops.AddField(
            model_name='AdminVisibilityPolicyRule',
            name='target',
            field=fields.CharField(max_length=20, default='path', db_default='path'),
        ),
        ops.AddField(
            model_name='AdminUserVisibilityRule',
            name='target',
            field=fields.CharField(max_length=20, default='path', db_default='path'),
        ),
    ]
