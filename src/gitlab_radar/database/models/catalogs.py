from tortoise import fields

from gitlab_radar.database.models.base import RadarModel


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
