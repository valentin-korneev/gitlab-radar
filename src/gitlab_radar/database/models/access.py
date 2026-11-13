from tortoise import fields

from gitlab_radar.database.models.base import RadarModel


class WebSocketTicket(RadarModel):
    token_hash = fields.CharField(max_length=64, primary_key=True)
    expires_at = fields.DatetimeField(index=True)

    class Meta:
        table = 'websocket_ticket'


class WebSession(RadarModel):
    token_hash = fields.CharField(max_length=64, primary_key=True)
    encrypted_tokens = fields.TextField()
    csrf_hash = fields.CharField(max_length=64)
    expires_at = fields.DatetimeField(index=True)

    class Meta:
        table = 'web_session'


class AuthorizedUser(RadarModel):
    preferred_username = fields.CharField(max_length=255, primary_key=True)
    is_admin = fields.BooleanField(default=False)
    is_blocked = fields.BooleanField(default=False)

    class Meta:
        table = 'authorized_user'
