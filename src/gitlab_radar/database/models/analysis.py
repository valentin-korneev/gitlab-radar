from tortoise import fields

from gitlab_radar.database.models.base import RadarModel
from gitlab_radar.schemas.project import LanguageAnalysisStatus, ProjectAnalysisStatus


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
