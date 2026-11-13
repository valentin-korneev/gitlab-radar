import hashlib
import hmac
import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

_MASK = re.compile(r'\[masked-[a-f0-9]{32}\]')


def _digest(value: str, purpose: str, key: bytes) -> str:
    return hmac.new(key, f'{purpose}\0{value}'.encode(), hashlib.sha256).hexdigest()


def _mask(value: str, key: bytes) -> str:
    if _MASK.fullmatch(value):
        return value
    return f'[masked-{_digest(value, "segment", key)[:32]}]'


def public_webhook_url(value: str, masking_key: bytes) -> str:
    parsed = urlsplit(value if '://' in value else f'https://{value}')
    authority = parsed.netloc.rsplit('@', maxsplit=1)[-1]
    segments = parsed.path.split('/')
    hooks_index = next((index for index, segment in enumerate(segments) if segment.casefold() == 'hooks'), None)
    if hooks_index is not None:
        segments[hooks_index + 1 :] = [
            _mask(unquote_plus(segment), masking_key) if segment else '' for segment in segments[hooks_index + 1 :]
        ]
    parameters = []
    for parameter in parsed.query.split('&'):
        key, separator, content = parameter.partition('=')
        decoded_key = unquote_plus(key).casefold()
        masked_parameter = parameter
        if separator and ('token' in decoded_key or 'secret' in decoded_key):
            masked_parameter = f'{key}={_mask(unquote_plus(content), masking_key)}'
        parameters.append(masked_parameter)
    return urlunsplit((parsed.scheme, authority, '/'.join(segments), '&'.join(parameters), ''))


def public_webhook_identity(value: str, masking_key: bytes) -> str:
    return _digest(public_webhook_url(value, masking_key), 'identity', masking_key)
