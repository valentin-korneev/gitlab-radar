from tortoise import fields

from gitlab_radar.database.models.base import RadarModel
from gitlab_radar.schemas.scan import ScanItemState, ScanSource, ScanState, ScanTargetKind


class ScanRun(RadarModel):
    id = fields.IntField(primary_key=True)
    state = fields.CharEnumField(ScanState, max_length=20, default=ScanState.QUEUED)
    source = fields.CharEnumField(ScanSource, max_length=20, default=ScanSource.MANUAL)
    requested_by = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    owner_token = fields.UUIDField(null=True)
    lease_expires_at = fields.DatetimeField(null=True)
    heartbeat_at = fields.DatetimeField(null=True)
    stop_requested_at = fields.DatetimeField(null=True)
    updated_project_ids = fields.JSONField(default=list)
    phase = fields.CharField(max_length=20, default='idle')
    started_at = fields.DatetimeField(null=True)
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

    class Meta:
        table = 'scan_run'


class ScanTarget(RadarModel):
    id = fields.IntField(primary_key=True)
    gitlab_id = fields.BigIntField(index=True)
    kind = fields.CharEnumField(ScanTargetKind, max_length=20, default=ScanTargetKind.BRANCH)
    ref = fields.CharField(max_length=500)
    is_default = fields.BooleanField(default=True, index=True)
    successful_metadata = fields.JSONField(default=dict)
    last_attempt = fields.ForeignKeyField('models.ScanItem', related_name=False, null=True, on_delete=fields.SET_NULL)
    last_completed_item = fields.ForeignKeyField(
        'models.ScanItem', related_name=False, null=True, on_delete=fields.SET_NULL
    )
    last_successful_result = fields.ForeignKeyField(
        'models.AnalysisResult', related_name=False, null=True, on_delete=fields.RESTRICT
    )

    class Meta:
        table = 'scan_target'
        unique_together = (('gitlab_id', 'kind', 'ref'),)


class ScanItem(RadarModel):
    id = fields.IntField(primary_key=True)
    scan = fields.ForeignKeyField('models.ScanRun', related_name='items', on_delete=fields.CASCADE)
    target = fields.ForeignKeyField('models.ScanTarget', related_name='items', on_delete=fields.RESTRICT)
    result = fields.ForeignKeyField(
        'models.AnalysisResult', related_name='observations', null=True, on_delete=fields.RESTRICT
    )
    fallback_result = fields.ForeignKeyField(
        'models.AnalysisResult', related_name='fallback_observations', null=True, on_delete=fields.RESTRICT
    )
    metadata = fields.JSONField()
    fallback_metadata = fields.JSONField(default=dict)
    revision = fields.CharField(max_length=128, null=True)
    analysis_fingerprint = fields.CharField(max_length=64, default='')
    input_digest = fields.CharField(max_length=64, null=True)
    state = fields.CharEnumField(ScanItemState, max_length=20, default=ScanItemState.PENDING, index=True)
    error = fields.TextField(null=True)
    scanned_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'scan_item'
        unique_together = (('scan', 'target'),)
        indexes = (('target_id', 'revision', 'analysis_fingerprint'),)


class ScanFile(RadarModel):
    id = fields.IntField(primary_key=True)
    item = fields.ForeignKeyField('models.ScanItem', related_name='files', on_delete=fields.CASCADE)
    path = fields.CharField(max_length=1000)
    content = fields.TextField()

    class Meta:
        table = 'scan_file'
        unique_together = (('item', 'path'),)


class ScanFileUsage(RadarModel):
    id = fields.IntField(primary_key=True)
    file = fields.ForeignKeyField('models.ScanFile', related_name='usages', on_delete=fields.CASCADE)
    language_code = fields.CharField(max_length=100, null=True)
    analyzer_key = fields.CharField(max_length=100)
    role = fields.CharField(max_length=30)

    class Meta:
        table = 'scan_file_usage'
        unique_together = (('file', 'analyzer_key', 'role', 'language_code'),)
