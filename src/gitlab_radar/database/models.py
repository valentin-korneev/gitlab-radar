from tortoise import fields
from tortoise.models import Model


class ScanRun(Model):
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
    current_project = fields.CharField(max_length=500, null=True)
    error = fields.TextField(null=True)
    errors = fields.JSONField(default=list)
    published = fields.BooleanField(default=False, index=True)


class ProjectSnapshot(Model):
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


class ProjectFile(Model):
    id = fields.IntField(primary_key=True)
    project = fields.ForeignKeyField('models.ProjectSnapshot', related_name='files', on_delete=fields.CASCADE)
    path = fields.CharField(max_length=1000)
    local_path = fields.CharField(max_length=2000)
    size = fields.IntField()

    class Meta:
        unique_together = (('project', 'path'),)
