from gitlab_radar.database.models import ApplicationSecret


async def webhook_masking_key() -> bytes:
    secret = await ApplicationSecret.get(name='webhook-masking')
    return bytes.fromhex(secret.value)
