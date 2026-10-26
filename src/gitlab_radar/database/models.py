from tortoise import fields
from tortoise.models import Model


class RadarModel(Model):
    class Meta:
        abstract = True


class ScanRun(RadarModel):
    id = fields.IntField(primary_key=True)
    state = fields.CharField(max_length=20)
    phase = fields.CharField(max_length=20, default='idle')
    started_at = fields.DatetimeField()
    completed_at = fields.DatetimeField(null=True)
    projects_count = fields.IntField(default=0)
    total_steps = fields.IntField(default=0)
    completed_steps = fields.IntField(default=0)
    collected_projects = fields.IntField(default=0)
    analyzed_projects = fields.IntField(default=0)
    reused_projects = fields.IntField(default=0)
    skipped_projects = fields.IntField(default=0)
    gitlab_requests = fields.IntField(default=0)
    current_project = fields.CharField(max_length=500, null=True)
    error = fields.TextField(null=True)
    errors = fields.JSONField(default=list)
    published = fields.BooleanField(default=False, index=True)

class ProjectSnapshot(RadarModel):
    id = fields.IntField(primary_key=True)
    scan = fields.ForeignKeyField('models.ScanRun', related_name='projects', on_delete=fields.CASCADE)
    gitlab_id = fields.BigIntField(index=True)
    revision = fields.CharField(max_length=128, null=True, index=True)
    payload = fields.JSONField()
    collected = fields.BooleanField(default=False)
    analyzed = fields.BooleanField(default=False)
    reused = fields.BooleanField(default=False)
    error = fields.TextField(null=True)

    class Meta:
        unique_together = (('scan', 'gitlab_id'),)


class ProjectFile(RadarModel):
    id = fields.IntField(primary_key=True)
    project = fields.ForeignKeyField('models.ProjectSnapshot', related_name='files', on_delete=fields.CASCADE)
    path = fields.CharField(max_length=1000)
    content = fields.TextField()

    class Meta:
        unique_together = (('project', 'path'),)


class WebSocketTicket(RadarModel):
    token_hash = fields.CharField(max_length=64, primary_key=True)
    expires_at = fields.DatetimeField(index=True)


class AuthorizedUser(RadarModel):
    preferred_username = fields.CharField(max_length=255, primary_key=True)
    is_admin = fields.BooleanField(default=False)
    is_blocked = fields.BooleanField(default=False)

    class Meta:
        table = 'authorized_user'

class CompanyRequirementGroup(RadarModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)
    description = fields.TextField(default='')
    sort_order = fields.IntField(default=0)

class CompanyRequirement(RadarModel):
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=100, unique=True)
    title = fields.CharField(max_length=200)
    group = fields.ForeignKeyField(
        'models.CompanyRequirementGroup',
        related_name='requirements',
        on_delete=fields.RESTRICT,
    )
    description = fields.TextField(default='')
    condition = fields.JSONField()
    enabled = fields.BooleanField(default=True, index=True)
    sort_order = fields.IntField(default=0)

class ApplicationParameter(RadarModel):
    key = fields.CharField(max_length=100, primary_key=True)
    title = fields.CharField(max_length=200)
    description = fields.TextField(default='')
    value = fields.CharField(max_length=500)
    value_type = fields.CharField(max_length=30, default='string')
    min_value = fields.IntField(null=True)
    max_value = fields.IntField(null=True)
    sort_order = fields.IntField(default=0)

class DataFixture(RadarModel):
    name = fields.CharField(max_length=100, primary_key=True)
