import hashlib
import hmac
import re
import secrets
from typing import ClassVar
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


async def mask_historical_webhooks(apps, schema_editor):
    secret_model = apps.get_model('models', 'ApplicationSecret')
    snapshot_model = apps.get_model('models', 'ProjectSnapshot')
    connection = schema_editor.client
    secret, _ = await secret_model.get_or_create(
        name='webhook-masking',
        defaults={'value': secrets.token_hex(32)},
        using_db=connection,
    )
    key = bytes.fromhex(secret.value)

    def digest(value, purpose):
        return hmac.new(key, f'{purpose}\0{value}'.encode(), hashlib.sha256).hexdigest()

    def mask(value):
        if re.fullmatch(r'\[masked-[a-f0-9]{32}\]', value):
            return value
        return f'[masked-{digest(value, "segment")[:32]}]'

    def safe_url(value):
        parsed = urlsplit(value if '://' in value else f'https://{value}')
        segments = parsed.path.split('/')
        hooks_index = next((i for i, segment in enumerate(segments) if segment.casefold() == 'hooks'), None)
        if hooks_index is not None:
            segments[hooks_index + 1:] = [mask(unquote_plus(segment)) if segment else ''
                                        for segment in segments[hooks_index + 1:]]
        parameters = []
        for parameter in parsed.query.split('&'):
            name, separator, value = parameter.partition('=')
            decoded = unquote_plus(name).casefold()
            parameters.append(f'{name}={mask(unquote_plus(value))}'
                              if separator and ('token' in decoded or 'secret' in decoded) else parameter)
        return urlunsplit((parsed.scheme, parsed.netloc.rsplit('@', maxsplit=1)[-1],
                           '/'.join(segments), '&'.join(parameters), ''))

    cursor = 0
    while True:
        rows = await snapshot_model.filter(id__gt=cursor).using_db(connection).order_by('id').limit(200)
        if not rows:
            break
        for row in rows:
            payload = dict(row.payload)
            hooks = payload.get('webhooks', [])
            if hooks:
                for hook in hooks:
                    url = safe_url(str(hook.get('url') or ''))
                    hook['identity'] = digest(url, 'identity')
                    hook['url'] = url
                await snapshot_model.filter(id=row.id).using_db(connection).update(payload=payload)
            cursor = row.id


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.CreateModel(
            name='ApplicationSecret',
            fields=[
                ('name', fields.CharField(max_length=100, primary_key=True, unique=True)),
                ('value', fields.TextField()),
            ],
            options={'table': 'application_secret', 'app': 'models', 'pk_attr': 'name'},
            bases=['RadarModel'],
        ),
        ops.RunPython(mask_historical_webhooks, reverse_code=ops.RunPython.noop),
    ]
