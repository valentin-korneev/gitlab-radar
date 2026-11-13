from tortoise import fields
from tortoise.models import Model

from gitlab_radar.schemas.project import LanguageAnalysisStatus, ProjectAnalysisStatus
from gitlab_radar.schemas.scan import ScanItemState, ScanTargetKind


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


class ProgrammingLanguage(RadarModel):
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=100, unique=True)
    name = fields.CharField(max_length=100, unique=True)
    enabled = fields.BooleanField(default=False, index=True)
    oldest_current_version = fields.CharField(max_length=50, null=True)

    class Meta:
        table = 'programming_language'


class ProgrammingFramework(RadarModel):
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=100, unique=True)
    name = fields.CharField(max_length=100)
    language = fields.ForeignKeyField('models.ProgrammingLanguage', related_name='frameworks', on_delete=fields.CASCADE)
    dependency_names = fields.JSONField(default=list)
    enabled = fields.BooleanField(default=True, index=True)

    class Meta:
        table = 'programming_framework'


class ProjectBlacklistRule(RadarModel):
    id = fields.IntField(primary_key=True)
    pattern = fields.CharField(max_length=500, unique=True)

    class Meta:
        table = 'project_blacklist_rule'


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


class AnalysisResult(RadarModel):
    id = fields.IntField(primary_key=True)
    gitlab_id = fields.BigIntField(index=True)
    source_revision = fields.CharField(max_length=128, null=True)
    analysis_fingerprint = fields.CharField(max_length=64, index=True)
    input_digest = fields.CharField(max_length=64, null=True, index=True)
    cache_key = fields.CharField(max_length=64, null=True, unique=True)
    identity_key = fields.CharField(max_length=64, unique=True)
    status = fields.CharEnumField(ProjectAnalysisStatus, max_length=20, index=True)
    payload = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'analysis_result'
        indexes = (('gitlab_id', 'source_revision', 'analysis_fingerprint'),)


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


class ResultLanguage(RadarModel):
    id = fields.IntField(primary_key=True)
    result = fields.ForeignKeyField('models.AnalysisResult', related_name='languages', on_delete=fields.CASCADE)
    language = fields.ForeignKeyField('models.ProgrammingLanguage', related_name='results', on_delete=fields.RESTRICT)
    analysis_status = fields.CharEnumField(LanguageAnalysisStatus, max_length=20)
    analyzer_version = fields.CharField(max_length=50, null=True)
    error = fields.TextField(null=True)

    class Meta:
        table = 'result_language'
        unique_together = (('result', 'language'),)


class ResultModule(RadarModel):
    id = fields.IntField(primary_key=True)
    result_language = fields.ForeignKeyField('models.ResultLanguage', related_name='modules', on_delete=fields.CASCADE)
    path = fields.CharField(max_length=1000)
    payload = fields.JSONField()

    class Meta:
        table = 'result_module'
        unique_together = (('result_language', 'path'),)


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


class WebSocketTicket(RadarModel):
    token_hash = fields.CharField(max_length=64, primary_key=True)
    expires_at = fields.DatetimeField(index=True)


class WebSession(RadarModel):
    token_hash = fields.CharField(max_length=64, primary_key=True)
    encrypted_tokens = fields.TextField()
    csrf_hash = fields.CharField(max_length=64)
    expires_at = fields.DatetimeField(index=True)


class AuthorizedUser(RadarModel):
    preferred_username = fields.CharField(max_length=255, primary_key=True)
    is_admin = fields.BooleanField(default=False)
    is_blocked = fields.BooleanField(default=False)

    class Meta:
        table = 'authorized_user'


class UserVisibilityGroup(RadarModel):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField('models.AuthorizedUser', related_name='visibility_groups', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=100)
    is_active = fields.BooleanField(default=False, index=True)
    sort_order = fields.IntField(default=0)

    class Meta:
        unique_together = (('user', 'name'),)


class UserVisibilityRule(RadarModel):
    id = fields.IntField(primary_key=True)
    group = fields.ForeignKeyField('models.UserVisibilityGroup', related_name='rules', on_delete=fields.CASCADE)
    action = fields.CharField(max_length=10)
    target = fields.CharField(max_length=20, default='path', db_default='path')
    pattern = fields.CharField(max_length=500)
    sort_order = fields.IntField(default=0)


class AdminVisibilityPolicy(RadarModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)


class AdminVisibilityPolicyRule(RadarModel):
    id = fields.IntField(primary_key=True)
    policy = fields.ForeignKeyField('models.AdminVisibilityPolicy', related_name='rules', on_delete=fields.CASCADE)
    action = fields.CharField(max_length=10)
    target = fields.CharField(max_length=20, default='path', db_default='path')
    pattern = fields.CharField(max_length=500)
    sort_order = fields.IntField(default=0)


class AdminVisibilityPolicyAssignment(RadarModel):
    id = fields.IntField(primary_key=True)
    policy = fields.ForeignKeyField(
        'models.AdminVisibilityPolicy', related_name='assignments', on_delete=fields.CASCADE
    )
    user = fields.ForeignKeyField(
        'models.AuthorizedUser', related_name='visibility_policy_assignments', on_delete=fields.CASCADE
    )

    class Meta:
        unique_together = (('policy', 'user'),)


class AdminUserVisibilityRule(RadarModel):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField(
        'models.AuthorizedUser', related_name='admin_visibility_rules', on_delete=fields.CASCADE
    )
    action = fields.CharField(max_length=10)
    target = fields.CharField(max_length=20, default='path', db_default='path')
    pattern = fields.CharField(max_length=500)
    sort_order = fields.IntField(default=0)


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


class CompanyRequirementLanguage(RadarModel):
    id = fields.IntField(primary_key=True)
    requirement = fields.ForeignKeyField(
        'models.CompanyRequirement', related_name='language_links', on_delete=fields.CASCADE
    )
    language = fields.ForeignKeyField(
        'models.ProgrammingLanguage', related_name='requirement_links', on_delete=fields.RESTRICT
    )

    class Meta:
        table = 'company_requirement_language'
        unique_together = (('requirement', 'language'),)


class ApplicationParameter(RadarModel):
    key = fields.CharField(max_length=100, primary_key=True)
    title = fields.CharField(max_length=200)
    description = fields.TextField(default='')
    value = fields.CharField(max_length=500)
    value_type = fields.CharField(max_length=30, default='string')
    min_value = fields.IntField(null=True)
    max_value = fields.IntField(null=True)
    sort_order = fields.IntField(default=0)
    language = fields.ForeignKeyField(
        'models.ProgrammingLanguage', related_name='application_parameters', null=True, on_delete=fields.RESTRICT
    )


class PackageManagerCatalog(RadarModel):
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=100, unique=True)
    name = fields.CharField(max_length=100)

    class Meta:
        table = 'package_manager'


class LanguagePackageManager(RadarModel):
    id = fields.IntField(primary_key=True)
    language = fields.ForeignKeyField(
        'models.ProgrammingLanguage', related_name='package_manager_links', on_delete=fields.CASCADE
    )
    package_manager = fields.ForeignKeyField(
        'models.PackageManagerCatalog', related_name='language_links', on_delete=fields.CASCADE
    )

    class Meta:
        table = 'language_package_manager'
        unique_together = (('language', 'package_manager'),)


class ResultModulePackageManager(RadarModel):
    id = fields.IntField(primary_key=True)
    module = fields.ForeignKeyField(
        'models.ResultModule', related_name='package_manager_links', on_delete=fields.CASCADE
    )
    package_manager = fields.ForeignKeyField(
        'models.PackageManagerCatalog', related_name='result_module_links', on_delete=fields.RESTRICT
    )

    class Meta:
        table = 'result_module_package_manager'
        unique_together = (('module', 'package_manager'),)


class ApplicationSecret(RadarModel):
    name = fields.CharField(max_length=100, primary_key=True)
    value = fields.TextField()

    class Meta:
        table = 'application_secret'


class DataFixture(RadarModel):
    name = fields.CharField(max_length=100, primary_key=True)
