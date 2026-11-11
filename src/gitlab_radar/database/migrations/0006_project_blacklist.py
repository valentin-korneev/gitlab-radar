from typing import ClassVar

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.CreateModel(
            name='ProjectBlacklistRule',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('pattern', fields.CharField(max_length=500, unique=True)),
            ],
            options={'table': 'project_blacklist_rule', 'app': 'models', 'pk_attr': 'id'},
            bases=['RadarModel'],
        ),
    ]
