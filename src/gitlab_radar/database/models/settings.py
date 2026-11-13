from tortoise import fields

from gitlab_radar.database.models.base import RadarModel


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

    class Meta:
        table = 'application_parameter'


class ApplicationSecret(RadarModel):
    name = fields.CharField(max_length=100, primary_key=True)
    value = fields.TextField()

    class Meta:
        table = 'application_secret'


class DataFixture(RadarModel):
    name = fields.CharField(max_length=100, primary_key=True)

    class Meta:
        table = 'data_fixture'


class ProjectBlacklistRule(RadarModel):
    id = fields.IntField(primary_key=True)
    pattern = fields.CharField(max_length=500, unique=True)

    class Meta:
        table = 'project_blacklist_rule'
