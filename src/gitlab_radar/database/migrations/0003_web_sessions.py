from typing import ClassVar

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.CreateModel(
            name='WebSession',
            fields=[
                ('token_hash', fields.CharField(max_length=64, primary_key=True, unique=True)),
                ('encrypted_tokens', fields.TextField()),
                ('csrf_hash', fields.CharField(max_length=64)),
                ('expires_at', fields.DatetimeField(db_index=True)),
            ],
            options={'table': 'websession', 'app': 'models', 'pk_attr': 'token_hash'},
            bases=['RadarModel'],
        ),
    ]
